"""Meaningful Part 3 checks with real MySQL/Qdrant and explicit test-only AI doubles.

No real OpenAI requests are made. Run: python -m unittest -v test_rag
"""
import io
import asyncio
import os
import unittest
from unittest.mock import patch
from uuid import uuid4

import httpx
from langchain_core.embeddings import Embeddings
from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableLambda
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject
from sqlalchemy import delete, select

from app import app, token_for
from database import Base, DocumentRecord, User, engine, sessions
from document_processing import extract_pages, split_pages
from rag_routes import get_rag_service
from rag_service import RagService
from rag_cli import ask_forever


def sample_pdf():
    writer = PdfWriter()
    page = writer.add_blank_page(width=612, height=792)
    font = DictionaryObject({NameObject('/Type'): NameObject('/Font'), NameObject('/Subtype'): NameObject('/Type1'), NameObject('/BaseFont'): NameObject('/Helvetica')})
    page[NameObject('/Resources')] = DictionaryObject({NameObject('/Font'): DictionaryObject({NameObject('/F1'): writer._add_object(font)})})
    stream = DecodedStreamObject()
    stream.set_data(b'BT /F1 12 Tf 72 720 Td (Orion launch code is 742.) Tj ET')
    page[NameObject('/Contents')] = writer._add_object(stream)
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


class ControlledEmbeddings(Embeddings):
    def __init__(self):
        self.queries = []

    def embed_documents(self, texts):
        return [self.embed_query(text) for text in texts]

    def embed_query(self, text):
        self.queries.append(text)
        return [1.0, 1.0 if 'orion' in text.lower() else 0.0, 1.0 if 'nebula' in text.lower() else 0.0, 0.1]


class ParsingTests(unittest.TestCase):
    def test_cli_exit(self):
        def handler(request):
            self.assertEqual(request.url.path, '/api/rag/conversations')
            return httpx.Response(201, json={'id': str(uuid4())})
        with httpx.Client(base_url='http://test', transport=httpx.MockTransport(handler)) as client:
            output = io.StringIO()
            with patch('builtins.input', return_value='exit'), patch('sys.stdout', output):
                ask_forever(client, [])
            self.assertIn('Goodbye.', output.getvalue())

    def test_real_pdf_extraction_and_hard_chunk_limit(self):
        self.assertIn('742', extract_pages('orion.pdf', sample_pdf())[0][1])
        text = 'x' * 1300
        chunks = split_pages([(7, text)])
        self.assertEqual([len(c['content']) for c in chunks], [500, 500, 500])
        self.assertTrue(all(c['page'] == 7 for c in chunks))
        self.assertEqual(chunks[0]['content'][-100:], chunks[1]['content'][:100])

    def test_invalid_and_scanned_documents(self):
        for name, data in [('bad.exe', b'anything'), ('bad.pdf', b'not a PDF'), ('empty.txt', b'')]:
            with self.subTest(name=name), self.assertRaises(ValueError):
                extract_pages(name, data)
        writer = PdfWriter()
        writer.add_blank_page(width=612, height=792)
        output = io.BytesIO()
        writer.write(output)
        with self.assertRaisesRegex(ValueError, 'OCR'):
            extract_pages('scan.pdf', output.getvalue())


class RagIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        self.seen_prompts = []

        def answer(prompt):
            self.seen_prompts.append(prompt.to_messages())
            return AIMessage(content='The Orion launch code is 742. [1]')

        self.service = RagService(collection='test_' + uuid4().hex, embeddings=ControlledEmbeddings(), chat_model=RunnableLambda(answer))
        self.users = []
        async with sessions() as session:
            for _ in range(2):
                user = User(username='rag_test_' + uuid4().hex[:16], password_hash='test-only-not-a-login-password')
                session.add(user)
                self.users.append(user)
            await session.commit()
        app.dependency_overrides[get_rag_service] = lambda: self.service
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test')
        self.auth = [{'Authorization': 'Bearer ' + token_for(user)['token']} for user in self.users]

    async def asyncTearDown(self):
        app.dependency_overrides.clear()
        await self.client.aclose()
        if await self.service.qdrant.collection_exists(self.service.collection):
            await self.service.qdrant.delete_collection(self.service.collection)
        await self.service.close()
        async with sessions() as session:
            await session.execute(delete(User).where(User.id.in_([u.id for u in self.users])))
            await session.commit()
        await engine.dispose()

    async def test_upload_index_retrieve_memory_and_owner_isolation(self):
        self.assertIn((await self.client.get('/api/documents')).status_code, (401, 403))
        result = await self.client.post('/api/documents', headers=self.auth[0], files=[('files', ('orion.pdf', sample_pdf(), 'application/pdf')), ('files', ('second.pdf', sample_pdf(), 'application/pdf')), ('files', ('notes.txt', b'Use text chunks of size 500. Orion mission briefing. ' + b'The launch code is 742. ' * 60, 'text/plain'))])
        self.assertEqual(result.status_code, 201, result.text)
        docs = result.json()['documents']
        self.assertEqual(len(docs), 3)
        doc_id = docs[0]['id']
        preview = await self.client.get(f'/api/documents/{doc_id}/chunks', headers=self.auth[0])
        self.assertIn('742', preview.json()['chunks'][0]['text'])
        self.assertEqual((await self.client.get(f'/api/documents/{doc_id}/chunks', headers=self.auth[1])).status_code, 404)
        self.assertEqual((await self.client.delete(f'/api/documents/{doc_id}', headers=self.auth[1])).status_code, 404)
        self.assertEqual((await self.client.get('/api/documents', headers=self.auth[1])).json()['documents'], [])
        note = docs[2]
        neighbors = await self.service.expand_sources([{'document_id': note['id'], 'filename': note['filename'], 'page': 1, 'chunk_index': 1, 'text': 'retrieval seed', 'score': 0.9}])
        self.assertEqual([source['chunk_index'] for source in neighbors], [0, 1, 2])
        self.assertIn('size 500', neighbors[0]['text'])
        self.assertIsNone(neighbors[0]['score'])
        # Keyless uploads work, but a real production service must not silently use test vectors.
        keyless = RagService(collection=self.service.collection)
        try:
            with patch.dict(os.environ, {'OPENAI_API_KEY': ''}):
                app.dependency_overrides[get_rag_service] = lambda: keyless
                rejected = await self.client.post(f'/api/documents/{doc_id}/index', headers=self.auth[0])
                self.assertEqual(rejected.status_code, 503)
                self.assertIn('OPENAI_API_KEY', rejected.json()['detail'])
        finally:
            app.dependency_overrides[get_rag_service] = lambda: self.service
            await keyless.close()
        for doc in docs:
            self.assertEqual((await self.client.post(f'/api/documents/{doc["id"]}/index', headers=self.auth[0])).status_code, 202)
        await asyncio.gather(*list(self.service.jobs.values()))
        listing = (await self.client.get('/api/documents', headers=self.auth[0])).json()['documents']
        self.assertTrue(all(doc['status'] == 'indexed' for doc in listing), listing)
        other = await self.service.ingest(self.users[1].id, 'private.txt', b'Nebula private code is 999. Do not share with another account.')
        await self.service.index_document(self.users[1].id, other['id'])
        conversation = (await self.client.post('/api/rag/conversations', headers=self.auth[0])).json()['id']
        self.assertEqual((await self.client.get('/api/rag/conversations/' + conversation, headers=self.auth[1])).status_code, 404)
        payload = {'conversation_id': conversation, 'question': 'What is the Orion launch code?', 'document_ids': [doc_id]}
        first = await self.client.post('/api/rag/ask', headers=self.auth[0], json=payload)
        self.assertEqual(first.status_code, 200, first.text)
        self.assertIn('742', first.json()['answer'])
        self.assertTrue(all(source['document_id'] == doc_id for source in first.json()['sources']))
        payload['question'] = 'Repeat that code.'
        second = await self.client.post('/api/rag/ask', headers=self.auth[0], json=payload)
        self.assertEqual(second.status_code, 200, second.text)
        messages = self.seen_prompts[-1]
        self.assertTrue(any('What is the Orion launch code?' in message.content for message in messages))
        self.assertFalse(any('Nebula private' in message.content for message in messages))
        self.assertIn('What is the Orion launch code?', self.service.embeddings().queries[-1])
        payload['question'] = 'Which text splitter is required for Part 3?'
        changed_topic = await self.client.post('/api/rag/ask', headers=self.auth[0], json=payload)
        self.assertEqual(changed_topic.status_code, 200)
        self.assertEqual(self.service.embeddings().queries[-1], payload['question'])
        history = (await self.client.get('/api/rag/conversations/' + conversation, headers=self.auth[0])).json()['turns']
        self.assertEqual(len(history), 3)
        payload['document_ids'] = [other['id']]
        self.assertEqual((await self.client.post('/api/rag/ask', headers=self.auth[0], json=payload)).status_code, 422)
        with patch.dict(os.environ, {'RAG_MIN_SCORE': '1.1'}):
            payload['document_ids'] = [doc_id]
            no_match = await self.client.post('/api/rag/ask', headers=self.auth[0], json=payload)
            self.assertEqual(no_match.json()['sources'], [])
            self.assertIn('do not know', no_match.json()['answer'])
        # A failed external embedding request is visible and can be retried
        # without duplicate vectors or exposure of the provider's raw error.
        original = self.service._embeddings
        class FailingEmbeddings(ControlledEmbeddings):
            async def aembed_documents(self, texts):
                raise RuntimeError('private-provider-error-must-not-be-returned')
        self.service._embeddings = FailingEmbeddings()
        await self.client.post(f'/api/documents/{doc_id}/index', headers=self.auth[0])
        await asyncio.gather(*list(self.service.jobs.values()))
        failed = next(doc for doc in (await self.client.get('/api/documents', headers=self.auth[0])).json()['documents'] if doc['id'] == doc_id)
        self.assertEqual(failed['status'], 'failed')
        self.assertNotIn('private-provider-error', failed['error'])
        self.service._embeddings = original
        await self.client.post(f'/api/documents/{doc_id}/index', headers=self.auth[0])
        await asyncio.gather(*list(self.service.jobs.values()))
        from qdrant_client import models as qm
        query_filter = qm.Filter(must=[qm.FieldCondition(key='document_id', match=qm.MatchValue(value=doc_id))])
        count = await self.service.qdrant.count(self.service.collection, count_filter=query_filter, exact=True)
        self.assertEqual(count.count, docs[0]['chunks'])
        self.assertEqual((await self.client.delete(f'/api/documents/{doc_id}', headers=self.auth[0])).status_code, 200)
        count = await self.service.qdrant.count(self.service.collection, count_filter=query_filter, exact=True)
        self.assertEqual(count.count, 0)
        self.assertEqual((await self.client.get(f'/api/documents/{doc_id}/chunks', headers=self.auth[0])).status_code, 404)


if __name__ == '__main__':
    unittest.main()

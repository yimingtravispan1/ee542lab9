"""Read-only shared DMV library; conversations remain private to each learner."""
from functools import lru_cache
import json
import asyncio
import logging
import os
import re

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import and_, or_, select

from database import ROOT, DocumentChunk, DocumentRecord, User, sessions
from rag_routes import RagQuestion, api_call
from rag_service import RagError, RagService

LIBRARY_USER = '__dmv_curated_library__'
COLLECTION = 'ee542_driving'
CATALOG = ROOT / 'knowledge/dmv/catalog.json'
logger = logging.getLogger('uvicorn.error')


class DrivingService(RagService):
    def __init__(self, **kwargs):
        super().__init__(collection=COLLECTION, **kwargs)
        self.retrieval_method = os.getenv(
            'DRIVING_RETRIEVER', 'word2vec_k64_idf'
        ).strip().lower()
        if self.retrieval_method not in {'openai', 'word2vec_k64_idf'}:
            raise ValueError('DRIVING_RETRIEVER must be openai or word2vec_k64_idf.')
        self._histogram_index = None
        self._histogram_lock = asyncio.Lock()

    async def library_owner(self):
        async with sessions() as session:
            owner = await session.scalar(select(User).where(User.username == LIBRARY_USER))
        if owner is None:
            raise RagError('The driving library has not been prepared. Run seed_driving.py on the server.', 503)
        return owner.id

    async def _ask(self, user_id, conversation_id, question, document_ids):
        result = await super()._ask(
            user_id, conversation_id, question, [],
            knowledge_user_id=await self.library_owner(),
        )
        result['retrieval_method'] = self.retrieval_method
        return result

    async def histogram_index(self):
        # Lazy loading keeps the original OpenAI mode usable without artifacts.
        async with self._histogram_lock:
            if self._histogram_index is None:
                from query_word_histogram import load_index
                path = ROOT / 'artifacts/part5/baseline_k64'
                try:
                    index = await asyncio.to_thread(load_index, path)
                except (OSError, ValueError, KeyError) as error:
                    logger.exception('Part 5 index could not be loaded')
                    raise RagError(
                        'Part 5 index is missing or invalid. Run '
                        'python build_word_histogram.py --k 64 inside the backend.',
                        503,
                    ) from error
                if index[0].k != 64:
                    raise RagError('Part 5 requires the K=64 index.', 503)
                self._histogram_index = index
                logger.info('Part5 index loaded: method=%s chunks=%d dimension=64',
                            self.retrieval_method, len(index[2]))
            return self._histogram_index

    async def retrieve_sources(self, owner_id, query, document_ids):
        if self.retrieval_method == 'openai':
            return await super().retrieve_sources(owner_id, query, document_ids)

        from query_word_histogram import retrieve
        embedder, histograms, chunks = await self.histogram_index()
        _, details = embedder.encode(query)
        if details['known_words'] == 0:
            logger.info('Part5 retrieval: method=%s known_words=0 sources=0',
                        self.retrieval_method)
            return []

        report = await asyncio.to_thread(
            retrieve, query, embedder, histograms, chunks,
            top_k=4, use_idf=True,
        )
        matches = report['results']

        # Validate persisted IDs and text against the CURRENT shared SQL library.
        # This detects stale artifacts and prevents private uploads being used.
        filenames = {
            source['filename'] for source in
            json.loads(CATALOG.read_text(encoding='utf-8'))['sources']
        }
        ids = [match['id'] for match in matches]
        async with sessions() as session:
            rows = (await session.execute(
                select(DocumentChunk, DocumentRecord.filename)
                .join(DocumentRecord,
                      DocumentChunk.document_id == DocumentRecord.id)
                .where(
                    DocumentChunk.id.in_(ids),
                    DocumentRecord.user_id == owner_id,
                    DocumentRecord.filename.in_(filenames),
                    DocumentRecord.status == 'indexed',
                )
            )).all()
        actual = {chunk.id: (chunk, filename) for chunk, filename in rows}
        sources = []
        for match in matches:
            current = actual.get(match['id'])
            if current is None:
                raise RagError('Part 5 index does not match the shared library. '
                               'Rebuild it from the current database.', 409)
            chunk, filename = current
            if (chunk.document_id != match['document_id']
                    or chunk.content != match['text']
                    or chunk.page != match['page']
                    or chunk.chunk_index != match['chunk_index']
                    or filename != match['filename']):
                raise RagError('Part 5 index is stale. Rebuild it from the '
                               'current database.', 409)
            sources.append({
                'document_id': chunk.document_id,
                'filename': filename,
                'page': chunk.page,
                'chunk_index': chunk.chunk_index,
                'text': chunk.content,
                'score': round(match['score'], 4),
                'match_type': 'word2vec_histogram_idf',
            })

        logger.info(
            'Part5 retrieval: method=%s known_words=%d/%d seeds=%s',
            self.retrieval_method, details['known_words'], details['total_words'],
            [(s['filename'], s['page'], s['chunk_index']) for s in sources],
        )
        return sources

    def retrieval_query(self, turns, question):
        # "Give a question with its answer" is a standalone request, not a
        # reference to the preceding topic. Reserve memory for clear follow-ups.
        followup = re.match(r'^\s*(why[?!.\s]*$|how[?!.\s]*$|what else|what about that|explain (that|it)|repeat|and (what|how|why)|what does (that|it) mean)', question, re.IGNORECASE)
        return '\n'.join([turns[-1].question, question])[-6000:] if turns and followup else question

    async def expand_sources(self, sources):
        if not sources:
            return []
        # DMV checklists span page boundaries. Retrieve parent pages (and the
        # following page), keeping exact page/chunk provenance for each excerpt.
        # The fixed curated checklist occupies PDF pages 7-10 of DL 955.
        conditions = []
        for source in sources:
            start, end = source['page'], source['page'] + 1
            if source['filename'] == 'Driving_Test_Criteria.pdf' and 7 <= start <= 10:
                start, end = 7, 10
            conditions.append(and_(DocumentChunk.document_id == source['document_id'], DocumentChunk.page.between(start, end)))
        async with sessions() as session:
            chunks = (await session.scalars(select(DocumentChunk).where(or_(*conditions)).order_by(DocumentChunk.document_id, DocumentChunk.chunk_index))).all()
        seeds = {(s['document_id'], s['chunk_index']): s for s in sources}
        filenames = {s['document_id']: s['filename'] for s in sources}
        return [seeds.get((c.document_id, c.chunk_index)) or {'document_id': c.document_id, 'filename': filenames[c.document_id], 'page': c.page, 'chunk_index': c.chunk_index, 'text': c.content, 'score': None, 'match_type': 'page_context'} for c in chunks]

    def answer_instructions(self):
        return super().answer_instructions() + ' You are California Driving Test Assistant for new noncommercial Class C learners, including learners unfamiliar with English road-test instructions. Keep answers concise and practical. Only discuss California driving rules, test preparation, and examiner instructions supported by context. For unrelated topics, decline briefly. Never promise a passing score or describe generated questions as official exam questions. When asked for practice, give one clearly labeled unofficial practice question with its answer and cited explanation. The curated source versions are Driver_Handbook.pdf (June 2025), Driving_Test_Criteria.pdf (October 2017), and Additional Testing Materials.pdf / DL 80 (March 2022). If using Driving_Test_Criteria.pdf, explicitly mention that it is the 2017 edition and current DMV procedures may differ. Do not claim these documents establish current law or current fees. When asked about current or latest requirements, explain the version limit and direct the learner to the official DMV website. Never infer a traffic sign solely from an image absent from the text.'


@lru_cache
def get_driving_service():
    return DrivingService()


def create_driving_router(current_user):
    router = APIRouter(prefix='/api/driving', tags=['Driving study'])

    @router.get('/library')
    async def library(user=Depends(current_user), service=Depends(get_driving_service)):
        catalog = json.loads(CATALOG.read_text(encoding='utf-8'))
        owner = await api_call(service.library_owner())
        docs = await api_call(service.list_documents(owner))
        # Expose only curated records, never another learner's uploads.
        docs = [d for d in docs if d['filename'] in {s['filename'] for s in catalog['sources']}]
        return {**catalog, 'retrieval_method': service.retrieval_method, 'documents': docs, 'ready': len(docs) == len(catalog['sources']) and all(d['status'] == 'indexed' for d in docs)}

    @router.post('/ask')
    async def ask(data: RagQuestion, user=Depends(current_user), service=Depends(get_driving_service)):
        question = data.question.strip()
        if not question:
            raise HTTPException(422, 'Question cannot be blank.')
        return await api_call(service.ask(user.id, data.conversation_id, question, []))

    return router

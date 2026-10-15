"""Opt-in real API validation using lab8.pdf and lab9.pdf in docs/labs.

Run only when authorized to use the configured OpenAI API key.
Existing admin-owned uploads are reused; documents and answers remain available.
No API key, password, or JWT is written to the report.
"""
import argparse
import asyncio
import json
import re
from pathlib import Path
import time

import httpx
from sqlalchemy import select

from app import token_for
from database import ROOT, User, engine, sessions

REPORT = ROOT / 'artifacts/reports/Part3-real-validation.json'


async def admin_token():
    async with sessions() as session:
        admin = await session.scalar(select(User).where(User.username == 'admin'))
    await engine.dispose()
    if admin is None:
        raise RuntimeError('The existing admin account is required for this validation.')
    return token_for(admin)['token']


def call(client, method, path, **kwargs):
    response = client.request(method, '/api' + path, **kwargs)
    if response.is_error:
        raise RuntimeError(f'{path}: HTTP {response.status_code}: {response.json().get("detail", "Request failed")}')
    return response.json()


def save(report):
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, indent=2, ensure_ascii=True) + '\n', encoding='utf-8')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--index-only', action='store_true')
    args = parser.parse_args()
    report = {'documents': [], 'cases': []}
    with httpx.Client(base_url='http://127.0.0.1:8000', headers={'Authorization': 'Bearer ' + asyncio.run(admin_token())}, timeout=180) as client:
        report['configuration'] = call(client, 'GET', '/rag/status')
        if not report['configuration']['openai_configured']:
            raise RuntimeError('Restart the backend to load OPENAI_API_KEY.')
        existing = call(client, 'GET', '/documents')['documents']
        for filename in ('lab8.pdf', 'lab9.pdf'):
            matches = [doc for doc in existing if doc['filename'] == filename]
            if matches:
                doc = matches[0]
            else:
                with (ROOT.parent / 'docs/labs' / filename).open('rb') as file:
                    uploaded = call(client, 'POST', '/documents', files=[('files', (filename, file, 'application/pdf'))])
                if uploaded['errors']:
                    raise RuntimeError(str(uploaded['errors']))
                doc = uploaded['documents'][0]
            report['documents'].append(doc)
            save(report)
            if doc['status'] != 'indexed':
                call(client, 'POST', f'/documents/{doc["id"]}/index')
            print(f'{filename}: uploaded, {doc["pages"]} pages, {doc["chunks"]} chunks.', flush=True)
        ids = {doc['id'] for doc in report['documents']}
        deadline = time.monotonic() + 600
        last_status = None
        while time.monotonic() < deadline:
            docs = [doc for doc in call(client, 'GET', '/documents')['documents'] if doc['id'] in ids]
            status = [(doc['filename'], doc['status']) for doc in docs]
            if status != last_status:
                print('Indexing:', status, flush=True)
                last_status = status
            report['documents'] = docs
            save(report)
            failures = [doc for doc in docs if doc['status'] == 'failed']
            if failures:
                raise RuntimeError('; '.join(doc['filename'] + ': ' + (doc['error'] or 'Indexing failed') for doc in failures))
            if len(docs) == 2 and all(doc['status'] == 'indexed' for doc in docs):
                break
            time.sleep(2)
        else:
            raise RuntimeError('Indexing did not complete within 10 minutes.')
        if args.index_only:
            print('PASS: both PDFs indexed using the real OpenAI embedding API.', flush=True)
            return
        by_name = {doc['filename']: doc for doc in report['documents']}
        lab8_session = call(client, 'POST', '/rag/conversations')['id']
        lab9_session = call(client, 'POST', '/rag/conversations')['id']
        unknown_session = call(client, 'POST', '/rag/conversations')['id']
        cases = [
            ('lab8_setup', lab8_session, ['lab8.pdf'], 'In Step 1.1 of the CNN and DOCA lab, which GPU, operating system, and boot disk size are suggested?', ['L4', '22.04', '100']),
            ('lab8_followup', lab8_session, ['lab8.pdf'], 'Why does that setup need a full virtual machine rather than a GPU container?', ['Docker']),
            ('lab9_chunking', lab9_session, ['lab9.pdf'], 'In Part 3, what text chunk size and LangChain splitter are required?', ['500', 'CharacterTextSplitter']),
            ('lab9_server_options', lab9_session, ['lab9.pdf'], 'Which two self-hosted Llama server options are described in lab9.pdf?', ['llama.cpp', 'vLLM']),
            ('unknown_answer', unknown_session, ['lab8.pdf', 'lab9.pdf'], 'What is the instructor\'s favorite ice cream flavor?', ['do not know']),
        ]
        for name, conversation, filenames, question, expected in cases:
            result = call(client, 'POST', '/rag/ask', json={'conversation_id': conversation, 'question': question, 'document_ids': [by_name[filename]['id'] for filename in filenames]})
            answer = result['answer']
            passed = bool(answer.strip()) and all(value.lower() in answer.lower() for value in expected)
            passed = passed and all(source['filename'] in filenames for source in result['sources'])
            if name != 'unknown_answer':
                citations = re.findall(r'\[(\d+)\]', answer)
                passed = passed and bool(result['sources']) and bool(citations) and 'do not know' not in answer.lower()
                passed = passed and all(1 <= int(citation) <= len(result['sources']) for citation in citations)
            report['cases'].append({'name': name, 'question': question, 'passed': passed, **result})
            save(report)
            print(f'{name}: {"PASS" if passed else "REVIEW"}\n{answer}\n', flush=True)
        if not all(case['passed'] for case in report['cases']):
            raise RuntimeError('One or more answers need review; see the saved report.')
        print('PASS: real embeddings, factual answers, citations, follow-up memory, document filtering, and unknown-answer behavior.', flush=True)


if __name__ == '__main__':
    main()

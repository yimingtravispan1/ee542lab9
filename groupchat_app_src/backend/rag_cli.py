"""Interactive document RAG driver backed by the same authenticated web APIs."""
import argparse
from getpass import getpass
from pathlib import Path
import time

import httpx

from document_processing import SUPPORTED_SUFFIXES


def request(client, method, path, **kwargs):
    response = client.request(method, path, **kwargs)
    if response.is_error:
        data = response.json()
        raise RuntimeError(str(data.get('detail', f'HTTP {response.status_code}')))
    return response.json()


def upload_folder(client, folder):
    paths = sorted(p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in SUPPORTED_SUFFIXES)
    if not paths:
        raise RuntimeError('No supported documents found in the folder.')
    ids = []
    for path in paths:
        with path.open('rb') as file:
            result = request(client, 'POST', '/api/documents', files=[('files', (path.name, file))])
        for error in result['errors']:
            print(f'{error["filename"]}: {error["error"]}')
        for doc in result['documents']:
            ids.append(doc['id'])
            print(f'Extracted {doc["filename"]}: {doc["chunks"]} chunks.')
    if not ids:
        raise RuntimeError('No documents were extracted successfully. Check the upload errors above.')
    return ids


def wait_for_indexes(client, ids):
    for doc_id in ids:
        request(client, 'POST', f'/api/documents/{doc_id}/index')
    deadline = time.monotonic() + 1800
    while time.monotonic() < deadline:
        docs = request(client, 'GET', '/api/documents')['documents']
        selected = [doc for doc in docs if doc['id'] in ids]
        if any(doc['status'] == 'failed' for doc in selected):
            raise RuntimeError('; '.join(doc['error'] or 'Indexing failed.' for doc in selected if doc['status'] == 'failed'))
        if len(selected) == len(ids) and all(doc['status'] == 'indexed' for doc in selected):
            return
        time.sleep(2)
    raise RuntimeError('Indexing is still running. Check the document status in the browser.')


def ask_forever(client, document_ids):
    conversation = request(client, 'POST', '/api/rag/conversations')['id']
    print('Ask questions about your documents. Type exit to quit.')
    while True:
        try:
            question = input('You: ').strip()
        except (EOFError, KeyboardInterrupt):
            print('\nGoodbye.')
            return
        if question.lower() == 'exit':
            print('Goodbye.')
            return
        if not question:
            continue
        try:
            result = request(client, 'POST', '/api/rag/ask', json={'conversation_id': conversation, 'question': question, 'document_ids': document_ids})
            print('Assistant:', result['answer'])
            for index, source in enumerate(result['sources'], 1):
                print(f'[{index}] {source["filename"]}, page {source["page"]}, chunk {source["chunk_index"] + 1}')
        except RuntimeError as error:
            print('Error:', error)


def main():
    parser = argparse.ArgumentParser(description='Upload a document folder and run a memory-aware document Q&A session.')
    parser.add_argument('--url', default='http://127.0.0.1:8000')
    parser.add_argument('--username', required=True)
    parser.add_argument('--folder', type=Path, help='Optional folder of PDF/TXT/MD/DOCX files to extract and index.')
    args = parser.parse_args()
    try:
        with httpx.Client(base_url=args.url, timeout=180) as client:
            token = request(client, 'POST', '/api/login', json={'username': args.username, 'password': getpass('Password: ')})['token']
            client.headers['Authorization'] = 'Bearer ' + token
            ids = upload_folder(client, args.folder) if args.folder else []
            status = request(client, 'GET', '/api/rag/status')
            if not status['openai_configured']:
                raise RuntimeError('Fill OPENAI_API_KEY in groupchat_app_src/.env and restart the backend. Uploaded text remains saved.')
            if ids:
                print('Waiting for document embeddings...')
                wait_for_indexes(client, ids)
            ask_forever(client, ids)
    except (RuntimeError, httpx.HTTPError, OSError) as error:
        parser.exit(1, f'Error: {error}\n')


if __name__ == '__main__':
    main()

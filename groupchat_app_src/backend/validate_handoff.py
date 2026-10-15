"""Acceptance for a fresh, disposable handoff Compose project (no OpenAI calls).

Run AFTER setup-dev.ps1 with a separate env file and project name. This test
intentionally interrupts an import in that test database. It refuses the normal
project name. No credentials are included in its report.
"""
import argparse
import gzip
import json
from pathlib import Path
import secrets
import struct
import subprocess
import time
from uuid import uuid4

import httpx
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parent.parent


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--project', required=True)
    parser.add_argument('--env-file', type=Path, required=True)
    args = parser.parse_args()
    if not args.project.startswith('ee542-part5-check'):
        parser.error('Only a disposable ee542-part5-check* project is allowed.')
    config = dotenv_values(args.env_file)
    if config.get('OPENAI_API_KEY'):
        parser.error('Use a test env with an EMPTY OpenAI key to prove offline restoration.')
    compose = ['docker', 'compose', '--env-file', str(args.env_file.resolve()), '-f', str(ROOT / 'compose.yaml'), '--project-name', args.project]

    def run(*command, code=None):
        result = subprocess.run([*compose, *command], input=code, capture_output=True, text=True)
        if result.returncode:
            raise RuntimeError(result.stderr[-2000:] + result.stdout[-2000:])
        return result.stdout

    def inside(code):
        return run('exec', '-T', 'backend', 'python', '-', code=code)

    state_code = '''
import asyncio,json
from sqlalchemy import select,func
from database import User,DocumentRecord,DocumentChunk,RagConversation,Message,RagTurn,LibraryImport,engine,sessions
async def main():
 async with sessions() as s:
  counts={model.__tablename__:await s.scalar(select(func.count()).select_from(model)) for model in (User,DocumentRecord,DocumentChunk,RagConversation,Message,RagTurn)}
  counts['import_status']=await s.scalar(select(LibraryImport.status))
 print(json.dumps(counts))
 await engine.dispose()
asyncio.run(main())
'''
    state = json.loads(inside(state_code))
    assert state == {'users': 1, 'documents': 3, 'document_chunks': 483, 'rag_conversations': 0, 'messages': 0, 'rag_turns': 0, 'import_status': 'complete'}, state
    report = {'fresh_restore': True, 'no_original_accounts_or_conversations': True, 'openai_key_empty': True}
    base = 'http://127.0.0.1:' + str(config.get('APP_PORT', '8000'))
    vector_base = 'http://127.0.0.1:' + str(config.get('QDRANT_PORT', '6333'))
    with httpx.Client(base_url=base, timeout=30) as client, httpx.Client(base_url=vector_base, timeout=30) as vector:
        signup = client.post('/api/signup', json={'username': 'handoff_' + uuid4().hex[:12], 'password': secrets.token_urlsafe(24)})
        signup.raise_for_status()
        client.headers['Authorization'] = 'Bearer ' + signup.json()['token']
        status = client.get('/api/rag/status').json()
        assert not status['openai_configured'] and status['qdrant_ready']
        library = client.get('/api/driving/library').json()
        assert library['ready'] and sum(d['chunks'] for d in library['documents']) == 483
        assert not client.get('/api/documents').json()['documents']
        assert client.post('/api/documents', files={'files': ('private.txt', b'Keep my Part 5 development notes.', 'text/plain')}).status_code == 201
        assert client.post('/api/rag/conversations').status_code == 201
        sentinel = 'part5_preservation_check'
        response = vector.put('/collections/' + sentinel, json={'vectors': {'size': 3, 'distance': 'Cosine'}})
        response.raise_for_status()
        vector.put('/collections/' + sentinel + '/points?wait=true', json={'points': [{'id': 1, 'vector': [1, 0, 0], 'payload': {'purpose': 'Part 5 work'}}]}).raise_for_status()
        before = json.loads(inside(state_code))
        assert 'already initialized' in run('exec', '-T', 'backend', 'python', 'bootstrap_library.py')
        assert json.loads(inside(state_code)) == before
        report['repeated_import_preserves_accounts_uploads_and_conversations'] = True

        # Simulate a failed first import, in this disposable database only.
        inside('''
import asyncio
from sqlalchemy import select
from database import LibraryImport,DocumentRecord,engine,sessions
from driving import DrivingService
from bootstrap_library import load_bundle
from qdrant_client import models as qm
async def main():
 b,_=load_bundle(); service=DrivingService()
 try:
  async with sessions() as s:
   marker=await s.get(LibraryImport,b['library_id']);marker.status='pending'
   doc=await s.get(DocumentRecord,b['documents'][0]['id']);doc.status='pending'
   await s.commit()
  await service.qdrant.delete(service.collection,points_selector=qm.PointIdsList(points=[b['points'][0]['id']]),wait=True)
 finally: await service.close();await engine.dispose()
asyncio.run(main())
''')
        assert 'baseline ready' in run('exec', '-T', 'backend', 'python', 'bootstrap_library.py')
        assert json.loads(inside(state_code)) == before
        report['interrupted_import_resumes'] = True
        output = inside('''
import asyncio
from database import engine
from driving import DrivingService
from bootstrap_library import load_bundle,restore
async def main():
 service=DrivingService();bundle,_=load_bundle()
 try:
  try: await restore(service,bundle,'0'*64)
  except RuntimeError as e:
   assert 'different baseline' in str(e);print('CONFLICT_REJECTED')
  else: raise AssertionError('A changed bundle must be rejected')
 finally: await service.close();await engine.dispose()
asyncio.run(main())
''')
        assert 'CONFLICT_REJECTED' in output and json.loads(inside(state_code)) == before
        report['changed_baseline_rejected_without_overwrite'] = True
        response = vector.post('/collections/' + sentinel + '/points/count', json={'exact': True})
        assert response.json()['result']['count'] == 1
        report['separate_part5_collection_preserved'] = True

        # Confirm every restored vector exactly matches the exported float32 data.
        bundle = json.loads(gzip.decompress((ROOT / 'knowledge/dmv/bootstrap/library.json.gz').read_bytes()))
        points, offset = {}, None
        while True:
            body = {'limit': 128, 'with_payload': True, 'with_vector': True}
            if offset is not None:
                body['offset'] = offset
            response = vector.post('/collections/ee542_driving/points/scroll', json=body)
            response.raise_for_status()
            data = response.json()['result']
            points.update({p['id']: p for p in data['points']})
            offset = data['next_page_offset']
            if offset is None:
                break
        assert len(points) == 483
        for point in bundle['points']:
            restored = points[point['id']]
            assert struct.pack('<1536f', *restored['vector']) == struct.pack('<1536f', *point['vector'])
            assert restored['payload']['user_id'] == 1
        report['all_483_vectors_exact_and_owner_remapped'] = True

        # WatchFiles should reload on a local source edit without an image build.
        startup_count = run('logs', '--no-color', 'backend').count('Application startup complete.')
        probe = ROOT / 'backend/_handoff_reload_probe.py'
        if probe.exists():
            raise RuntimeError('Reload probe already exists; refusing to replace it.')
        try:
            probe.write_bytes(b'# Temporary handoff development reload check.\n')
            deadline = time.monotonic() + 45
            while time.monotonic() < deadline:
                if run('logs', '--no-color', 'backend').count('Application startup complete.') > startup_count:
                    break
                time.sleep(1)
            else:
                raise RuntimeError('Source edits did not reload the container backend.')
            report['source_edit_auto_reload'] = True
        finally:
            probe.unlink()
        report['passed'] = True
        path = ROOT / 'artifacts/reports/Backend-handoff-validation.json'
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes((json.dumps(report, indent=2) + '\n').encode('utf-8'))
        print(json.dumps(report, indent=2), flush=True)


if __name__ == '__main__':
    main()

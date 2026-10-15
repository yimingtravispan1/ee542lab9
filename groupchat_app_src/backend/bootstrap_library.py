"""Restore the shared DMV baseline without OpenAI calls or private user data.

Repeated starts preserve existing data. Interrupted first imports can resume;
changed bundles or conflicting records fail rather than overwrite user work.
"""
import asyncio
import gzip
import hashlib
import json
import math
import os
import secrets

from pwdlib import PasswordHash
from qdrant_client import models as qm
from sqlalchemy import select, text

from database import ROOT, Base, DocumentChunk, DocumentRecord, LibraryImport, User, engine, sessions
from driving import CATALOG, COLLECTION, LIBRARY_USER, DrivingService

BUNDLE_DIR = ROOT / 'knowledge/dmv/bootstrap'


def load_bundle():
    raw = gzip.decompress((BUNDLE_DIR / 'library.json.gz').read_bytes())
    manifest = json.loads((BUNDLE_DIR / 'manifest.json').read_text(encoding='utf-8'))
    checksum = hashlib.sha256(raw).hexdigest()
    if checksum != manifest['sha256']:
        raise RuntimeError('DMV bundle checksum mismatch.')
    bundle = json.loads(raw)
    if bundle['format_version'] != 1 or bundle['collection'] != COLLECTION:
        raise RuntimeError('Unsupported DMV bundle format or collection.')
    if bundle['embedding_model'] != os.getenv('OPENAI_EMBEDDING_MODEL', 'text-embedding-3-small'):
        raise RuntimeError('The baseline requires OPENAI_EMBEDDING_MODEL=text-embedding-3-small. Keep Part 5 embeddings in a separate collection.')
    catalog = json.loads(CATALOG.read_text(encoding='utf-8'))
    filenames = {s['filename'] for s in catalog['sources']}
    if {s['filename'] for s in bundle['sources']} != filenames or {d['filename'] for d in bundle['documents']} != filenames:
        raise RuntimeError('The bundle must contain only the curated DMV sources.')
    for source in bundle['sources']:
        data = (ROOT / 'knowledge/dmv/sources' / source['filename']).read_bytes()
        if hashlib.sha256(data).hexdigest() != source['sha256']:
            raise RuntimeError('DMV source file differs from the bundled baseline: ' + source['filename'])
    docs = {d['id']: d for d in bundle['documents']}
    chunks = {c['id']: c for c in bundle['chunks']}
    points = {p['id']: p for p in bundle['points']}
    if len(docs) != 3 or len(chunks) != len(bundle['chunks']) or set(chunks) != set(points) or len(points) != len(bundle['points']):
        raise RuntimeError('Invalid document, chunk, or vector IDs in the bundle.')
    for doc in docs.values():
        rows = [c for c in chunks.values() if c['document_id'] == doc['id']]
        if len(rows) != doc['chunk_count'] or sorted(c['chunk_index'] for c in rows) != list(range(len(rows))):
            raise RuntimeError('Incomplete DMV document chunks.')
    for chunk in chunks.values():
        if chunk['document_id'] not in docs or len(chunk['content']) > 500 or not 1 <= chunk['page'] <= docs[chunk['document_id']]['page_count']:
            raise RuntimeError('Invalid DMV chunk content or provenance.')
    for point in points.values():
        if len(point['vector']) != bundle['dimensions'] or not all(isinstance(x, (int, float)) and math.isfinite(x) for x in point['vector']):
            raise RuntimeError('Invalid DMV vector dimensions or values.')
    return bundle, checksum


async def restore(service, bundle, checksum):
    docs = {d['id']: d for d in bundle['documents']}
    chunks = {c['id']: c for c in bundle['chunks']}
    await service.ensure_collection(bundle['dimensions'])
    async with sessions() as session:
        marker = await session.get(LibraryImport, bundle['library_id'])
        if marker and marker.checksum != checksum:
            raise RuntimeError('A different baseline was already imported. Existing data was preserved; review the new bundle explicitly.')
        owner = await session.scalar(select(User).where(User.username == LIBRARY_USER))
        if owner is None:
            owner = User(username=LIBRARY_USER, password_hash=PasswordHash.recommended().hash(secrets.token_urlsafe(64)))
            session.add(owner)
            await session.flush()
        existing = (await session.scalars(select(DocumentRecord).where(DocumentRecord.user_id == owner.id))).all()
        if any(d.filename in {s['filename'] for s in bundle['sources']} and d.id not in docs for d in existing):
            raise RuntimeError('An existing curated library has different document IDs. It was preserved; do not overwrite it automatically.')
        all_indexed = True
        for entry in docs.values():
            record = await session.get(DocumentRecord, entry['id'])
            if record:
                if record.user_id != owner.id or any(getattr(record, k) != v for k, v in entry.items()):
                    raise RuntimeError('An existing document differs from the baseline. Existing data was preserved.')
                if record.status != 'indexed' or record.embedding_model != bundle['embedding_model'] or record.vector_collection != service.collection:
                    all_indexed = False
            else:
                all_indexed = False
                session.add(DocumentRecord(**entry, user_id=owner.id, status='pending', embedding_model=bundle['embedding_model'], vector_collection=service.collection))
        await session.flush()
        existing_chunks = (await session.scalars(select(DocumentChunk).where(DocumentChunk.document_id.in_(docs)))).all()
        if any(c.id not in chunks for c in existing_chunks):
            raise RuntimeError('The existing library has additional chunks. Existing data was preserved.')
        for entry in chunks.values():
            record = await session.get(DocumentChunk, entry['id'])
            if record:
                if any(getattr(record, k) != v for k, v in entry.items()):
                    raise RuntimeError('An existing chunk differs from the baseline. Existing data was preserved.')
            else:
                all_indexed = False
                session.add(DocumentChunk(**entry))
        query_filter = qm.Filter(must=[qm.FieldCondition(key='user_id', match=qm.MatchValue(value=owner.id)), qm.FieldCondition(key='document_id', match=qm.MatchAny(any=list(docs)))])
        count = (await service.qdrant.count(service.collection, count_filter=query_filter, exact=True)).count
        if marker and marker.status == 'complete':
            if not all_indexed or count != len(chunks):
                raise RuntimeError('The previously restored baseline changed or is incomplete. Existing work was preserved; repair it explicitly.')
            print('DMV baseline already initialized; existing data preserved.', flush=True)
            return
        if marker is None:
            marker = LibraryImport(id=bundle['library_id'], checksum=checksum, status='pending')
            session.add(marker)
        await session.commit()
        owner_id = owner.id
        # A matching existing installation needs only its import marker, not a
        # rewrite of its vectors. Partial imports retry the same IDs safely.
        if not (all_indexed and count == len(chunks)):
            # Refuse global point-ID collisions with another library owner.
            for start in range(0, len(bundle['points']), 64):
                batch = bundle['points'][start:start + 64]
                existing_points = await service.qdrant.retrieve(service.collection, ids=[p['id'] for p in batch], with_payload=True, with_vectors=False)
                if any(p.payload.get('user_id') != owner_id or p.payload.get('document_id') not in docs for p in existing_points):
                    raise RuntimeError('A vector ID belongs to other data; refusing to overwrite it.')
            for start in range(0, len(bundle['points']), 64):
                points = []
                for point in bundle['points'][start:start + 64]:
                    c = chunks[point['id']]
                    payload = {'user_id': owner_id, 'document_id': c['document_id'], 'filename': docs[c['document_id']]['filename'], 'page': c['page'], 'chunk_index': c['chunk_index'], 'text': c['content'], 'embedding_model': bundle['embedding_model']}
                    points.append(qm.PointStruct(id=point['id'], vector=point['vector'], payload=payload))
                await service.qdrant.upsert(service.collection, points=points, wait=True)
        for doc_id in docs:
            record = await session.get(DocumentRecord, doc_id)
            record.status = 'indexed'
            record.error = None
        marker.status = 'complete'
        await session.commit()
        print(f'DMV baseline ready: {len(docs)} documents, {len(chunks)} text chunks and vectors. No OpenAI calls.', flush=True)


async def main():
    bundle, checksum = load_bundle()
    service = DrivingService()
    try:
        for attempt in range(60):
            try:
                async with engine.connect() as connection:
                    await connection.execute(text('SELECT 1'))
                await service.qdrant.get_collections()
                break
            except Exception:
                if attempt == 59:
                    raise RuntimeError('MySQL or Qdrant did not become ready within 120 seconds.') from None
                await asyncio.sleep(2)
        async with engine.connect() as lock:
            if await lock.scalar(text("SELECT GET_LOCK('dmv_baseline_import', 60)")) != 1:
                raise RuntimeError('Another DMV initialization is still running; retry later.')
            try:
                async with engine.begin() as connection:
                    await connection.run_sync(Base.metadata.create_all)
                await restore(service, bundle, checksum)
            finally:
                await lock.execute(text("SELECT RELEASE_LOCK('dmv_baseline_import')"))
    finally:
        await service.close()
        await engine.dispose()


if __name__ == '__main__':
    asyncio.run(main())

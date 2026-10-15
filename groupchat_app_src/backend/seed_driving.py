"""Curate local DMV PDFs into a shared read-only Docker Qdrant collection.

This opt-in command uses real OpenAI embeddings. Reuses identical indexed files.
Source fingerprints provide a reviewable record of exactly what was embedded.
"""
import asyncio
import hashlib
import json
import secrets

from pwdlib import PasswordHash
from sqlalchemy import select

from database import ROOT, Base, User, engine, sessions
from driving import CATALOG, LIBRARY_USER, DrivingService


async def main():
    service = DrivingService()
    try:
        service.require_key()
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        async with sessions() as session:
            owner = await session.scalar(select(User).where(User.username == LIBRARY_USER))
            if owner is None:
                owner = User(username=LIBRARY_USER, password_hash=PasswordHash.recommended().hash(secrets.token_urlsafe(64)))
                session.add(owner)
                await session.commit()
        catalog = json.loads(CATALOG.read_text(encoding='utf-8'))
        report_path = ROOT / 'knowledge/dmv/ingestion.json'
        previous = json.loads(report_path.read_text(encoding='utf-8')) if report_path.exists() else {'sources': []}
        fingerprints = {s['filename']: s for s in previous['sources']}
        report = {'collection': service.collection, 'embedding_model': service.embedding_model, 'chunk_size': 500, 'overlap': 100, 'sources': previous['sources'].copy()}
        for source in catalog['sources']:
            data = (ROOT.parent / source['filename']).read_bytes()
            digest = hashlib.sha256(data).hexdigest()
            docs = await service.list_documents(owner.id)
            old = fingerprints.get(source['filename'], {})
            matches = [d for d in docs if d['filename'] == source['filename']]
            if matches and old.get('sha256') != digest:
                raise RuntimeError('An existing source changed. Review and explicitly remove its old library record before reseeding.')
            doc = matches[0] if matches else await service.ingest(owner.id, source['filename'], data, max_file_bytes=64 * 1024 * 1024)
            report['sources'] = [s for s in report['sources'] if s['filename'] != source['filename']]
            report['sources'].append({**source, **doc, 'sha256': digest})
            # Persist fingerprints before indexing so a failed run can safely resume.
            report_path.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
            if doc['status'] != 'indexed' or doc.get('embedding_model') != service.embedding_model:
                await service.index_document(owner.id, doc['id'])
                doc = next(d for d in await service.list_documents(owner.id) if d['id'] == doc['id'])
                report['sources'][-1].update(doc)
                report_path.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
            if doc['status'] != 'indexed':
                raise RuntimeError(doc['error'] or 'Indexing failed')
            print(f"{doc['filename']}: indexed, {doc['pages']} pages, {doc['chunks']} chunks", flush=True)
    finally:
        await service.close()
        await engine.dispose()


if __name__ == '__main__':
    asyncio.run(main())

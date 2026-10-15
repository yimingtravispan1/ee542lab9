"""Export only the curated DMV text and vectors; never accounts or conversations."""
import asyncio
import gzip
import hashlib
import json

from qdrant_client import models as qm
from sqlalchemy import select

from database import ROOT, DocumentChunk, DocumentRecord, engine, sessions
from driving import CATALOG, DrivingService

BUNDLE_DIR = ROOT / 'knowledge/dmv/bootstrap'


async def main():
    service = DrivingService()
    try:
        owner = await service.library_owner()
        catalog = json.loads(CATALOG.read_text(encoding='utf-8'))
        filenames = {s['filename'] for s in catalog['sources']}
        async with sessions() as session:
            docs = (await session.scalars(select(DocumentRecord).where(DocumentRecord.user_id == owner, DocumentRecord.filename.in_(filenames)).order_by(DocumentRecord.filename))).all()
            if len(docs) != len(filenames) or any(d.status != 'indexed' or d.vector_collection != service.collection or d.embedding_model != service.embedding_model for d in docs):
                raise RuntimeError('Export requires exactly the three indexed curated DMV documents.')
            chunks = (await session.scalars(select(DocumentChunk).where(DocumentChunk.document_id.in_([d.id for d in docs])).order_by(DocumentChunk.document_id, DocumentChunk.chunk_index))).all()
        points, offset = [], None
        while True:
            batch, offset = await service.qdrant.scroll(service.collection, scroll_filter=qm.Filter(must=[qm.FieldCondition(key='user_id', match=qm.MatchValue(value=owner)), qm.FieldCondition(key='document_id', match=qm.MatchAny(any=[d.id for d in docs]))]), limit=128, offset=offset, with_payload=False, with_vectors=True)
            # Rebuild payloads from curated SQL records on import; no source user IDs.
            points.extend({'id': str(p.id), 'vector': p.vector} for p in batch)
            if offset is None:
                break
        if {p['id'] for p in points} != {c.id for c in chunks}:
            raise RuntimeError('Vector IDs do not match curated text chunks.')
        bundle = {
            'format_version': 1, 'library_id': 'california-dmv-class-c-v1',
            'collection': service.collection, 'embedding_model': service.embedding_model,
            'dimensions': len(points[0]['vector']),
            'sources': [{'filename': s['filename'], 'sha256': hashlib.sha256((ROOT / 'knowledge/dmv/sources' / s['filename']).read_bytes()).hexdigest()} for s in catalog['sources']],
            'documents': [{'id': d.id, 'filename': d.filename, 'extracted_text': d.extracted_text, 'page_count': d.page_count, 'chunk_count': d.chunk_count} for d in docs],
            'chunks': [{'id': c.id, 'document_id': c.document_id, 'chunk_index': c.chunk_index, 'page': c.page, 'content': c.content} for c in chunks],
            'points': sorted(points, key=lambda p: p['id'])}
        data = json.dumps(bundle, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8')
        manifest = {k: bundle[k] for k in ('format_version', 'library_id', 'collection', 'embedding_model', 'dimensions')}
        manifest.update({'sha256': hashlib.sha256(data).hexdigest(), 'documents': len(docs), 'chunks': len(chunks), 'vectors': len(points), 'source_files': bundle['sources']})
        BUNDLE_DIR.mkdir(parents=True, exist_ok=True)
        output = gzip.compress(data, mtime=0)
        (BUNDLE_DIR / 'library.json.gz').write_bytes(output)
        (BUNDLE_DIR / 'manifest.json').write_bytes((json.dumps(manifest, indent=2) + '\n').encode('utf-8'))
        print(f'Exported {len(docs)} documents and {len(points)} vectors; {len(output) / 1048576:.2f} MiB. No accounts, passwords, keys, or conversations.', flush=True)
    finally:
        await service.close()
        await engine.dispose()


if __name__ == '__main__':
    asyncio.run(main())

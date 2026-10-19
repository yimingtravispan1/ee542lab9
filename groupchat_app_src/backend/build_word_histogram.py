"""Train Part 5 embeddings using the existing shared DMV chunks."""

import argparse
import asyncio
import hashlib
import json
from pathlib import Path

import numpy as np
from sqlalchemy import select

from database import DocumentChunk, DocumentRecord, User, sessions
from word_histogram import WordHistogramEmbedder


ROOT = Path(__file__).resolve().parent.parent
LIBRARY_USER = "__dmv_curated_library__"


async def load_chunks():
    """Read only the shared curated library, not private user uploads."""
    catalog_path = ROOT / "knowledge" / "dmv" / "catalog.json"
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    filenames = [source["filename"] for source in catalog["sources"]]

    async with sessions() as session:
        owner = await session.scalar(
            select(User).where(User.username == LIBRARY_USER)
        )

        if owner is None:
            raise RuntimeError("Shared DMV library has not been restored.")

        statement = (
            select(DocumentChunk, DocumentRecord.filename)
            .join(
                DocumentRecord,
                DocumentChunk.document_id == DocumentRecord.id,
            )
            .where(
                DocumentRecord.user_id == owner.id,
                DocumentRecord.filename.in_(filenames),
                DocumentRecord.status == "indexed",
            )
            .order_by(
                DocumentRecord.filename,
                DocumentChunk.chunk_index,
            )
        )

        rows = (await session.execute(statement)).all()

    if not rows:
        raise RuntimeError("No indexed DMV chunks found.")

    return [
        {
            "id": chunk.id,
            "document_id": chunk.document_id,
            "filename": filename,
            "page": chunk.page,
            "chunk_index": chunk.chunk_index,
            "text": chunk.content,
        }
        for chunk, filename in rows
    ]


def write_json(path, data):
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--k", type=int, default=32)
    parser.add_argument("--dimension", type=int, default=100)
    parser.add_argument("--epochs", type=int, default=50)
    args = parser.parse_args()

    output = ROOT / "artifacts" / "part5" / f"baseline_k{args.k}"

    # Avoid accidentally replacing an earlier experiment.
    if output.exists() and any(output.iterdir()):
        raise RuntimeError(
            f"Output directory already contains files: {output}. "
            "Keep or rename the earlier results before rerunning."
        )

    chunks = await load_chunks()
    texts = [chunk["text"] for chunk in chunks]

    print(f"Loaded {len(chunks)} DMV chunks.", flush=True)
    print("Training Word2Vec and custom K-means...", flush=True)

    embedder = WordHistogramEmbedder(
        vector_size=args.dimension,
        k=args.k,
        seed=42,
    )
    embedder.fit(texts, epochs=args.epochs)

    histograms = embedder.transform(texts)
    sums = histograms.sum(axis=1)

    if not np.isfinite(histograms).all():
        raise RuntimeError("Embeddings contain NaN or infinity.")
    if not np.all(histograms >= 0):
        raise RuntimeError("Histogram values must be nonnegative.")
    if not np.allclose(sums, 1.0, atol=1e-6):
        raise RuntimeError("Some training chunks have empty/invalid histograms.")

    output.mkdir(parents=True, exist_ok=True)

    embedder.model.save(str(output / "word2vec.model"))
    np.save(output / "centers.npy", embedder.centers)
    np.save(output / "histograms.npy", histograms)
    write_json(output / "chunks.json", chunks)
    write_json(output / "word_to_cluster.json", embedder.word_to_cluster)

    corpus_hash = hashlib.sha256(
        json.dumps(texts, ensure_ascii=False).encode("utf-8")
    ).hexdigest()

    summary = {
        **embedder.training_info,
        "chunk_count": len(chunks),
        "epochs": args.epochs,
        "seed": 42,
        "corpus_sha256": corpus_hash,
        "histogram_shape": list(histograms.shape),
        "histogram_sum_min": float(sums.min()),
        "histogram_sum_max": float(sums.max()),
        "normalization": "cluster counts / total token count",
    }
    write_json(output / "summary.json", summary)

    vector, details = embedder.encode(texts[0])
    example = {
        **chunks[0],
        **details,
        "histogram": vector.tolist(),
    }
    write_json(output / "example_embedding.json", example)

    print(json.dumps(summary, indent=2))
    print(f"Saved results to: {output}")
    print("Real-data embedding checks passed.")


if __name__ == "__main__":
    asyncio.run(main())
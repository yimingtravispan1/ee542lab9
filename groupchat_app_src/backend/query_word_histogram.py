"""Retrieve DMV chunks using saved Word2Vec histogram embeddings."""

import argparse
import json
from pathlib import Path

import numpy as np
from gensim.models import Word2Vec

from word_histogram import WordHistogramEmbedder


ROOT = Path(__file__).resolve().parent.parent


def load_index(index_dir):
    """Load the exact model and cluster mapping used for documents."""
    summary = json.loads(
        (index_dir / "summary.json").read_text(encoding="utf-8")
    )

    embedder = WordHistogramEmbedder(
        vector_size=summary["word_vector_dimension"],
        k=summary["histogram_dimension"],
        seed=summary["seed"],
    )
    embedder.model = Word2Vec.load(
        str(index_dir / "word2vec.model")
    )
    embedder.centers = np.load(
        index_dir / "centers.npy",
        allow_pickle=False,
    )
    embedder.word_to_cluster = json.loads(
        (index_dir / "word_to_cluster.json").read_text(encoding="utf-8")
    )

    histograms = np.load(
        index_dir / "histograms.npy",
        allow_pickle=False,
    )
    chunks = json.loads(
        (index_dir / "chunks.json").read_text(encoding="utf-8")
    )

    if histograms.shape != (len(chunks), embedder.k):
        raise ValueError("Chunk count or embedding dimension does not match.")
    if not np.isfinite(histograms).all():
        raise ValueError("Stored embeddings contain invalid numbers.")

    return embedder, histograms, chunks


def retrieve(
    question,
    embedder,
    histograms,
    chunks,
    top_k=4,
    use_idf=False,
):
    """Rank chunks using plain or cluster-IDF-weighted histograms."""
    query_vector, details = embedder.encode(question)

    if np.linalg.norm(query_vector) == 0:
        raise ValueError(
            "The question contains no words recognized by this model. "
            "Try an English question using DMV-related terms."
        )

    # Keep the original normalized histograms unchanged.
    document_vectors = histograms
    query_for_search = query_vector.copy()

    if use_idf:
        # Count how many chunks contain each word cluster.
        document_frequency = np.count_nonzero(histograms > 0, axis=0)
        number_of_documents = len(histograms)

        # Smoothed inverse document frequency, calculated from documents only.
        idf = np.log(
            (1 + number_of_documents) / (1 + document_frequency)
        ) + 1.0

        # Documents and questions MUST use the same weights.
        document_vectors = histograms * idf
        query_for_search = query_vector * idf

    query_norm = np.linalg.norm(query_for_search)
    document_norms = np.linalg.norm(document_vectors, axis=1)
    denominator = document_norms * query_norm

    scores = np.divide(
        document_vectors @ query_for_search,
        denominator,
        out=np.zeros(len(histograms), dtype=np.float64),
        where=denominator > 0,
    )

    ranked_indices = np.argsort(-scores, kind="stable")[:top_k]

    results = [
        {
            "rank": rank,
            "score": float(scores[index]),
            **chunks[int(index)],
        }
        for rank, index in enumerate(ranked_indices, start=1)
    ]

    return {
        "question": question,
        "method": "cluster_idf" if use_idf else "plain_histogram",
        "query_histogram": query_vector.tolist(),
        "query_details": details,
        "results": results,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--question", required=True)
    parser.add_argument("--k", type=int, default=32)
    parser.add_argument("--top-k", type=int, default=4)
    parser.add_argument("--output", default=None)
    parser.add_argument("--idf", action="store_true")
    args = parser.parse_args()

    if args.top_k < 1:
        parser.error("--top-k must be at least 1.")

    index_dir = ROOT / "artifacts" / "part5" / f"baseline_k{args.k}"
    embedder, histograms, chunks = load_index(index_dir)

    report = retrieve(
    args.question,
    embedder,
    histograms,
    chunks,
    top_k=args.top_k,
    use_idf=args.idf,
)

    details = report["query_details"]
    print("Question:", report["question"])
    print("Method:", report["method"])
    print(
        f"Known words: {details['known_words']} / "
        f"{details['total_words']}"
    )
    print("Unknown words:", details["unknown_words"])
    print("Query histogram sum:", details["histogram_sum"])

    for result in report["results"]:
        print()
        print(
            f"Rank {result['rank']} | "
            f"Cosine similarity: {result['score']:.4f}"
        )
        print(
            f"Source: {result['filename']} | "
            f"PDF page: {result['page']} | "
            f"Chunk: {result['chunk_index']}"
        )
        print(result["text"])

    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"\nReport saved to: {output_path}")


if __name__ == "__main__":
    main()
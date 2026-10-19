"""Part 5: Word2Vec + custom K-means + normalized histograms."""

import re
from pathlib import Path

import numpy as np
from gensim.models import Word2Vec


def tokenize(text):
    """Use the same tokenization for documents and questions."""
    return re.findall(r"[a-z]+(?:'[a-z]+)?|\d+", text.lower())


def squared_distances(vectors, centers):
    """Return squared Euclidean distances: shape (num_vectors, K)."""
    distances = (
        np.sum(vectors * vectors, axis=1, keepdims=True)
        + np.sum(centers * centers, axis=1)[None, :]
        - 2 * vectors @ centers.T
    )
    return np.maximum(distances, 0.0)


def custom_kmeans(vectors, k, seed=42, max_iter=100, tolerance=1e-5):
    """Cluster word vectors without using sklearn's KMeans."""
    vectors = np.asarray(vectors, dtype=np.float32)

    if not 1 <= k <= len(vectors):
        raise ValueError("K must be between 1 and vocabulary size.")

    rng = np.random.default_rng(seed)

    # Choose K distinct word vectors as initial centers.
    indices = rng.choice(len(vectors), size=k, replace=False)
    centers = vectors[indices].copy()

    for iteration in range(max_iter):
        distances = squared_distances(vectors, centers)

        # Assign each word to its nearest center.
        labels = np.argmin(distances, axis=1)

        new_centers = centers.copy()
        nearest_distances = distances[np.arange(len(vectors)), labels]
        farthest = np.argsort(nearest_distances)[::-1]
        replacement_index = 0

        for cluster_id in range(k):
            members = vectors[labels == cluster_id]

            if len(members):
                # A centroid is the mean of the assigned word vectors.
                new_centers[cluster_id] = members.mean(axis=0)
            else:
                # Restart an empty cluster at a poorly represented word.
                new_centers[cluster_id] = vectors[
                    farthest[replacement_index]
                ]
                replacement_index += 1

        movement = np.linalg.norm(new_centers - centers)
        centers = new_centers

        if movement < tolerance:
            break

    final_distances = squared_distances(vectors, centers)
    inertia = float(np.min(final_distances, axis=1).sum())

    return centers, {
        "iterations": iteration + 1,
        "inertia": inertia,
    }


class WordHistogramEmbedder:
    def __init__(self, vector_size=100, k=32, seed=42):
        self.vector_size = vector_size
        self.k = k
        self.seed = seed
        self.model = None
        self.centers = None
        self.word_to_cluster = {}
        self.training_info = {}

    def fit(self, texts, epochs=50):
        sentences = [tokenize(text) for text in texts]
        sentences = [tokens for tokens in sentences if tokens]

        if not sentences:
            raise ValueError("No usable words in the training data.")

        self.model = Word2Vec(
            sentences=sentences,
            vector_size=self.vector_size,
            window=5,
            min_count=1,
            workers=1,
            sg=1,
            seed=self.seed,
            epochs=epochs,
        )

        words = self.model.wv.index_to_key
        vectors = self.model.wv.vectors

        self.centers, clustering_info = custom_kmeans(
            vectors,
            k=self.k,
            seed=self.seed,
        )

        labels = np.argmin(
            squared_distances(vectors, self.centers),
            axis=1,
        )

        self.word_to_cluster = {
            word: int(label)
            for word, label in zip(words, labels)
        }

        self.training_info = {
            "vocabulary_size": len(words),
            "word_vector_dimension": self.vector_size,
            "histogram_dimension": self.k,
            **clustering_info,
        }
        return self

    def encode(self, text):
        if self.model is None or self.centers is None:
            raise RuntimeError("Call fit() before encode().")

        tokens = tokenize(text)
        counts = np.zeros(self.k, dtype=np.float32)
        known_words = 0

        for word in tokens:
            cluster_id = self.word_to_cluster.get(word)

            if cluster_id is not None:
                counts[cluster_id] += 1
                known_words += 1

        # Assignment requirement: divide by total words in the chunk.
        histogram = counts / len(tokens) if tokens else counts.copy()

        details = {
            "total_words": len(tokens),
            "known_words": known_words,
            "unknown_words": len(tokens) - known_words,
            "counts": counts.tolist(),
            "histogram_sum": float(histogram.sum()),
        }

        return histogram, details

    def transform(self, texts):
        vectors = [self.encode(text)[0] for text in texts]

        if not vectors:
            return np.empty((0, self.k), dtype=np.float32)

        return np.stack(vectors)


def demo():
    # This is a smoke test, not the final DMV experiment.
    texts = [
        "The driver checks mirrors before changing lanes.",
        "Use a turn signal before moving into another lane.",
        "Watch for pedestrians near a crossing.",
        "Keep enough space between your vehicle and other vehicles.",
    ]

    embedder = WordHistogramEmbedder(vector_size=100, k=4)
    embedder.fit(texts)

    vector, details = embedder.encode(texts[0])

    print("Training:", embedder.training_info)
    print("Text:", texts[0])
    print("Word counts:", details["counts"])
    print("Normalized histogram:", vector.tolist())
    print("Histogram shape:", vector.shape)
    print("Histogram sum:", details["histogram_sum"])

    assert vector.shape == (4,)
    assert np.all(vector >= 0)
    assert np.isclose(vector.sum(), 1.0)

    # Unknown words must not silently receive arbitrary cluster assignments.
    unknown_vector, _ = embedder.encode("zzzzunknownword")
    assert np.all(unknown_vector == 0)

    print("Basic checks passed.")


if __name__ == "__main__":
    demo()
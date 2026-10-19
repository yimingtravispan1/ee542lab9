"""Compare three histogram retrieval configurations on fixed questions."""

import csv
import json
import time
from pathlib import Path

from query_word_histogram import load_index, retrieve


ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "artifacts" / "part5" / "evaluation"

# The lane-change question was used during development.
# The remaining questions provide broader exploratory coverage.
QUESTIONS = [
    ("Q01", "What should I do before changing lanes?"),
    ("Q02", "What should I do when an emergency vehicle approaches with a siren?"),
    ("Q03", "What should I do when approaching a pedestrian at a crosswalk?"),
    ("Q04", "How should I enter and drive through a roundabout?"),
    ("Q05", "How much following distance should I leave behind another vehicle?"),
    ("Q06", "What should I do when driving in fog?"),
    ("Q07", "What should I do when a school bus flashes red lights?"),
    ("Q08", "How should I position my wheels when parking uphill next to a curb?"),
    ("Q09", "What does a flashing red traffic signal mean?"),
    ("Q10", "What vehicle safety equipment is checked before the driving test?"),
    ("Q11", "What does the examiner mean by pulling over to the curb?"),
    ("Q12", "When should headlights be used?"),
]

CONFIGURATIONS = [
    ("k32_plain", 32, False),
    ("k64_plain", 64, False),
    ("k64_idf", 64, True),
]


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)

    review_path = OUTPUT / "manual_review.csv"
    if review_path.exists():
        raise RuntimeError(
            "manual_review.csv already exists. "
            "Keep or rename it before rerunning to preserve your labels."
        )

    reports = []
    review_rows = []

    for name, k, use_idf in CONFIGURATIONS:
        index_dir = ROOT / "artifacts" / "part5" / f"baseline_k{k}"
        embedder, histograms, chunks = load_index(index_dir)

        # Warm up; exclude loading and this call from measured query time.
        retrieve(
            QUESTIONS[0][1],
            embedder,
            histograms,
            chunks,
            use_idf=use_idf,
        )

        for question_id, question in QUESTIONS:
            start = time.perf_counter()

            report = retrieve(
                question,
                embedder,
                histograms,
                chunks,
                top_k=4,
                use_idf=use_idf,
            )

            elapsed_ms = (time.perf_counter() - start) * 1000
            report.update({
                "question_id": question_id,
                "configuration": name,
                "query_time_ms": elapsed_ms,
            })
            reports.append(report)

            for result in report["results"]:
                review_rows.append({
                    "question_id": question_id,
                    "question": question,
                    "configuration": name,
                    "rank": result["rank"],
                    "score": result["score"],
                    "filename": result["filename"],
                    "page": result["page"],
                    "chunk_index": result["chunk_index"],
                    "text": result["text"],
                    "relevance": "",
                    "notes": "",
                })

            print(
                f"{name} | {question_id} | "
                f"{elapsed_ms:.2f} ms | "
                f"top result: {report['results'][0]['filename']}"
            )

    (OUTPUT / "retrieval_results.json").write_text(
        json.dumps(reports, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    with review_path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(review_rows[0]))
        writer.writeheader()
        writer.writerows(review_rows)

    print(f"\nSaved {len(reports)} query runs.")
    print(f"Saved {len(review_rows)} passages for manual review.")
    print(f"Output directory: {OUTPUT}")
    print("Relevance labels are blank; no accuracy has been calculated.")


if __name__ == "__main__":
    main()
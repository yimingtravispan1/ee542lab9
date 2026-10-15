# EE 542 Lab 9: California Driving Test Assistant

An English web and Android assistant with a curated California DMV knowledge
base, cited answers, private document Q&A, and local Llama group chat.

See the [application README](groupchat_app_src/README.md) for configuration,
startup commands, Android builds, and validation.

## Repository Layout

```text
docs/
  labs/                       Lab assignment and validation PDFs
  report.md                   Lab report
examples/
  embedding/                  Original course-provided embedding example
groupchat_app_src/
  backend/                    FastAPI, retrieval, ingestion, and validation
  frontend/                   English website and Android site association
  knowledge/dmv/
    sources/                  Original DMV PDFs
    catalog.json              Source metadata and edition information
    ingestion.json            File fingerprints and indexing results
  artifacts/
    reports/                  Sanitized validation reports tracked in Git
    screenshots/              Local screenshots, ignored by Git
    apks/                     Local Android builds, ignored by Git
  models/                     Local Llama model and download instructions
  sql/                        MySQL schema
  twa_android_src/            Android Studio project
  logs/                       Local runtime logs, ignored by Git
  tools/                      Local downloaded tools, ignored by Git
  compose.yaml               MySQL, Qdrant, and optional Llama services
  .env.example               Configuration template without real secrets
  start-backend.ps1           Windows backend launcher
```

The local `.env`, Python virtual environment, model weights, signing keys, and
build outputs are excluded from Git. Preserve the existing application directory
when using its configured virtual environment and local Android setup.

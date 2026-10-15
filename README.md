# EE 542 Lab 9: California Driving Test Assistant

An English web and Android assistant with a curated California DMV knowledge
base, cited answers, private document Q&A, and local Llama group chat.

See the [application README](groupchat_app_src/README.md) for configuration,
startup commands, Android builds, and validation.

## Start Developing Part 5

Only Docker Desktop is needed on the host; Python and databases run in containers.
From the repository root in PowerShell:

```powershell
Copy-Item groupchat_app_src/.env.example groupchat_app_src/.env
# Edit groupchat_app_src/.env and fill your own OPENAI_API_KEY.
.\scripts\setup-dev.ps1
```

Copy the template only for a new clone; keep an existing `.env`. The script
generates local database passwords and a JWT secret, builds the backend, starts
MySQL/Qdrant, and restores the bundled DMV text and vectors without OpenAI calls.
Open http://localhost:8000 and register your own account. The API key is needed
for questions and answers, not data restoration. No original user accounts,
passwords, private uploads, or conversations are included in the bundle.

The development server reloads when backend source changes. See the
[Part 5 development notes](groupchat_app_src/README.md#part-5-development) for the
embedding extension points. Llama and Android Studio are optional for this step.
For blocked PowerShell scripts, use
`powershell -ExecutionPolicy Bypass -File .\scripts\setup-dev.ps1`.

## Repository Layout

```text
docs/
  labs/                       Lab assignment and validation PDFs
scripts/
  setup-dev.ps1               One-command Windows development setup
groupchat_app_src/
  backend/                    FastAPI, retrieval, ingestion, and validation
  frontend/                   English website and Android site association
  knowledge/dmv/
    sources/                  Original DMV PDFs
    bootstrap/                Portable, sanitized text/vector data and checksum
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
  compose.yaml               Backend, MySQL, Qdrant, and optional Llama services
  .env.example               Configuration template without real secrets
```

The backend runs in Docker; no host Python virtual environment is required.
The local `.env`, model weights, signing keys, and build outputs are excluded
from Git. Android Studio and the temporary HTTPS tunnel remain optional host tools.

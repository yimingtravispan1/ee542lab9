# Group Chat Web App + LLM Bot

Windows / Docker setup and current Part 1 status: [PART1_SETUP.md](PART1_SETUP.md).
Android APK, HTTPS, signing, and remaining TWA validation: [PART2_SETUP.md](PART2_SETUP.md).
Document upload, Docker Qdrant, and OpenAI key configuration: [PART3_SETUP.md](PART3_SETUP.md).
Real OpenAI validation using lab8.pdf and lab9.pdf: [PART3_VALIDATION.md](PART3_VALIDATION.md).

FastAPI + MySQL + vanilla HTML/JS group chat with LLM bot (OpenAI-compatible server such as self-hosted Llama 3 via llama.cpp).

## Quick Start (Dev)

```bash
# 1) MySQL
# create DB & user, or run sql/schema.sql

# 2) Backend
cd backend
python -m venv .venv && source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# copy env and edit values
cp ../.env.example ../.env

# 3) Run app
uvicorn app:app --host 0.0.0.0 --port 8000
```

Open http://localhost:8000

LLM endpoint defaults to http://localhost:8001/v1 (llama.cpp server). Set `LLM_API_BASE`, `LLM_MODEL`, `LLM_API_KEY` if needed in `.env`.

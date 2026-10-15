# Part 1: Setup and Status

## Completed

- MySQL 8.4 container: `ee542-lab9-mysql-1`, port `127.0.0.1:3306`.
- Database `groupchat`, user `chatuser`, and tables `users` and `messages`, using utf8mb4.
- Persistent volume: `ee542-lab9_mysql_data`.
- Generated database passwords and JWT secret in the local, Git-ignored `.env`.
- FastAPI backend, Python virtual environment, and dependencies.
- Signup/login, JWT authentication, Argon2 hashing, history, and WebSocket broadcasts.
- SHA-256 verified Llama 3.2 3B Instruct Q4_K_M running on CPU in Docker.
- Real inference, bot broadcasts, and saved replies tested: `What is 2 + 2?` returned `4`.
- MySQL 8 authentication dependency `cryptography` installed.
- English interface, status messages, timestamps, documentation, and model response instructions.

## Start and Use

Open http://localhost:8000 and register with a password of at least 8 characters.
From `groupchat_app_src`:

```powershell
docker compose --profile llm up -d --wait mysql llama
.\start-backend.ps1
```

If script execution is blocked, start directly from `backend`:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app:app --host 127.0.0.1 --port 8000
```

Avoid starting another backend on the same port. Logs are in `logs/`.
Restart the backend after rebooting the computer or changing `.env`.
Press Ctrl+C to stop a foreground backend.
See [PART2_SETUP.md](PART2_SETUP.md) for Android access through HTTPS.

Stop containers with `docker compose --profile llm stop mysql llama`.
Keep the persistent volume to preserve accounts and history.
MySQL environment variables initialize credentials only on the first volume setup.
Later password changes must also be applied inside MySQL.

Restore tested dependencies from `backend`:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.lock.txt
```

## Model

- File: `models/Llama-3.2-3B-Instruct-Q4_K_M.gguf`, approximately 2.02 GB.
- Container: `ee542-lab9-llama-1`, image `ghcr.io/ggml-org/llama.cpp:server`.
- API: `http://127.0.0.1:8001/v1`, alias `llama-3.2-3b-instruct`.
- Context size argument: 4096; CPU inference, no GPU required.
- Logs: `docker compose logs -f llama`.
- Source, revision, checksum, and restore instructions: [models/README.md](models/README.md).

Include a question mark to trigger a bot reply; ASCII and full-width question marks are supported.
The UI shows a waiting indicator. Long CPU replies can take over a minute.
Reconnecting reloads history and deduplicates messages by ID.
The selected model replaces the larger PDF examples at the user's request.

## Verification

From `backend`, with all services running:

```powershell
.\.venv\Scripts\python.exe smoke_test.py --expect-model
```

Checks cover real database reads/writes, signup/login, duplicate accounts, invalid input,
unauthorized access, two-client broadcasts, password hashing, real inference, and saved bot replies.
Omit `--expect-model` only when testing the unavailable-model error.
Browser flows have also been verified in Edge and Android Chrome.

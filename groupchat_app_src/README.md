# California Driving Test Assistant

An English web and Android study assistant for new California Class C drivers.
Driving Study answers questions from curated DMV documents with page citations.
Group Chat uses local Llama inference; Document Q&A supports private uploads.

## Configuration

Edit the existing local `.env` next to `compose.yaml`. For a fresh installation,
copy `.env.example` to `.env` and configure:

- `MYSQL_ROOT_PASSWORD` and `MYSQL_PASSWORD`: database credentials. Set
  `DATABASE_URL` to the matching `chatuser` password and `groupchat` database.
- `JWT_SECRET`: a random secret of at least 32 characters.
- `OPENAI_API_KEY`: the key for backend embeddings and study answers.
- `OPENAI_EMBEDDING_MODEL` and `OPENAI_CHAT_MODEL`: the current installation uses
  `text-embedding-3-small` and `gpt-6-luna`.
- `QDRANT_URL`: `http://127.0.0.1:6333`.
- `LLM_API_BASE`: `http://127.0.0.1:8001/v1`; `LLM_MODEL`: `llama-3.2-3b-instruct`.

Restart the backend after changing settings. The actual `.env` is ignored by Git;
never put credentials in frontend files or Android resources. MySQL credentials
initialize on first volume creation; later changes must also update the database.

## Run on Windows

From `groupchat_app_src`, with Docker Desktop running:

```powershell
docker compose up -d mysql qdrant
.\start-backend.ps1
```

Open http://localhost:8000 and register or log in. Driving Study opens by default.
Keep Docker volumes to preserve accounts, documents, and vectors.

To restore dependencies or start the backend directly, run from `backend`:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.lock.txt
.\.venv\Scripts\python.exe -m uvicorn app:app --host 127.0.0.1 --port 8000
```

Run only one backend on port 8000. Background-server logs are in `logs/`.
For Group Chat, obtain the model using [models/README.md](models/README.md), then
run `docker compose --profile llm up -d mysql qdrant llama`. Include a question
mark to trigger a group-chat bot reply; CPU inference can take over a minute.
Study and document questions do not require a question mark.

## Knowledge and Private Documents

Keep these PDFs in `knowledge/dmv/sources/`:

| File | Edition | Pages |
|---|---|---:|
| Driver_Handbook.pdf | DL 600, June 2025 | 92 |
| Driving_Test_Criteria.pdf | DL 955, October 2017 | 40 |
| Additional Testing Materials.pdf | DL 80, March 2022 | 2 |

From `backend`, run `.\.venv\Scripts\python.exe seed_driving.py` to prepare the
shared library. This uses real OpenAI embeddings and reuses identical indexed
sources. The Docker Qdrant collection `ee542_driving` contains 483 chunks of at
most 500 characters with 100-character overlap. Official URLs, editions, and
file fingerprints are recorded in `knowledge/dmv/`.

Source documents are credited to the California Department of Motor Vehicles.
This independent study project is not affiliated with DMV. Historical editions
cannot establish current requirements; verify those on the official DMV website.
Practice questions are unofficial. Image-only content is not part of retrieval.

For personal files, select Document Q&A, upload PDF/TXT/MD/DOCX files (10 MB each),
click Index, select indexed files, and ask a question. Personal documents and
study conversations are private to each account. The shared DMV library does
not include private uploads or the earlier lab8/lab9 test documents.

## Android and HTTPS

Android Studio project: `twa_android_src`. Launcher name: **CA Driving Study**.
Package: `com.helloworld.groupchat.twa`. Local APK:
`artifacts/apks/CA-Driving-Study-debug.apk` (ignored by Git).

The current temporary HTTPS origin is in `logs/tunnel-url.txt`. Keep the computer,
Docker services, backend, and tunnel running. To replace the temporary tunnel,
run from `groupchat_app_src`:

```powershell
.\tools\cloudflared.exe tunnel --url http://127.0.0.1:8000 --protocol http2 --no-autoupdate
```

If the origin changes, run `configure_site.py` from `twa_android_src` with
`--url NEW_HTTPS_ORIGIN --sha256 SIGNING_CERTIFICATE_SHA256`, then rebuild and
reinstall the APK. Use the matching signing certificate and keep private keys
out of Git. Website-only changes do not require rebuilding the APK.

From `twa_android_src`:

```powershell
$env:JAVA_HOME = 'D:\AndroidStudio\software\jbr'
.\gradlew.bat :app:assembleDebug :app:lintDebug --no-daemon --console plain
adb -s emulator-5554 install -r .\app\build\outputs\apk\debug\app-debug.apk
```

Full TWA mode requires a compatible Chrome browser. Emulator testing confirmed
cited study answers and restored login/history after reopening the app.

## Validation

From `backend`, run `.\.venv\Scripts\python.exe -m unittest -v test_rag` for the
regression suite using real MySQL/Qdrant and test-only AI doubles.

Opt-in checks using the configured OpenAI account:

```powershell
.\.venv\Scripts\python.exe validate_part3_real.py
.\.venv\Scripts\python.exe validate_part4_real.py
.\.venv\Scripts\python.exe validate_part4_ui.py
```

UI checks additionally require Playwright and installed Edge. Android UI checks
use `validate_part4_ui.py --android` after forwarding the active Chrome debugging
socket to localhost:9223. Remove the forward after testing. Sanitized validation
reports are in `artifacts/reports/`; APKs in `artifacts/apks/` and screenshots in
`artifacts/screenshots/` are local ignored outputs. The lab8/lab9 validation inputs
are in the repository's `docs/labs/` directory.
Part 5 custom Word2Vec embeddings are outside the current scope.

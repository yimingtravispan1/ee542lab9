# California Driving Test Assistant

An English web and Android study assistant for new California Class C drivers.
Driving Study answers questions from curated DMV documents with page citations.
Group Chat uses local Llama inference; Document Q&A supports private uploads.

## Configuration

For a new teammate's clone, the recommended workflow from the repository root is:

```powershell
Copy-Item groupchat_app_src/.env.example groupchat_app_src/.env
# Fill OPENAI_API_KEY and select an available OPENAI_CHAT_MODEL in the .env file.
.\scripts\setup-dev.ps1
```

Do not overwrite an existing `.env`. The setup script generates missing database
passwords and JWT secrets, then builds and starts the complete backend. No host
Python installation, model download, manual SQL import, or re-embedding is needed.
The backend and its Python dependencies run in Docker. No local `.venv` is used.

Edit the existing local `.env` next to `compose.yaml`. For a fresh installation,
copy `.env.example` to `.env` and configure:

- `MYSQL_ROOT_PASSWORD` and `MYSQL_PASSWORD`: database credentials, generated
  automatically by the setup script when blank.
- `JWT_SECRET`: a random secret of at least 32 characters.
- `OPENAI_API_KEY`: the key for backend embeddings and study answers.
- `OPENAI_EMBEDDING_MODEL` and `OPENAI_CHAT_MODEL`: the current installation uses
  `text-embedding-3-small` and `gpt-6-luna`.
- `LLM_MODEL`: `llama-3.2-3b-instruct` for the optional local group-chat model.

Compose configures the internal MySQL, Qdrant, and Llama hostnames automatically;
`DATABASE_URL`, `QDRANT_URL`, and `LLM_API_BASE` in the template are compatibility
settings and do not need changing for the container workflow.

Restart the backend after changing settings. The actual `.env` is ignored by Git;
never put credentials in frontend files or Android resources. MySQL credentials
initialize on first volume creation; later changes must also update the database.

## Run and Maintain the Backend

Use `scripts/setup-dev.ps1` from the repository root for initial setup or after
changing the local environment configuration. From `groupchat_app_src`:

```powershell
docker compose up -d --build --wait mysql qdrant backend
docker compose logs -f backend
docker compose stop
```

Open http://localhost:8000 and register or log in. Driving Study opens by default.
Keep Docker volumes to preserve accounts, documents, and vectors. Container logs
are available through Docker; no host Python server or virtual environment is used.

For Group Chat, obtain the model using [models/README.md](models/README.md), then
run `docker compose --profile llm up -d mysql qdrant backend llama`. Include a
question mark to trigger a group-chat bot reply; CPU inference can take over a
minute. Study and document questions do not require a question mark.

## Knowledge and Private Documents

Keep these PDFs in `knowledge/dmv/sources/`:

| File | Edition | Pages |
|---|---|---:|
| Driver_Handbook.pdf | DL 600, June 2025 | 92 |
| Driving_Test_Criteria.pdf | DL 955, October 2017 | 40 |
| Additional Testing Materials.pdf | DL 80, March 2022 | 2 |

The container restores the shared library automatically from
`knowledge/dmv/bootstrap/library.json.gz` (approximately 3.36 MiB), checking its
SHA-256 and the original PDFs. It contains only the three DMV documents, text
chunks, and existing vectors; account IDs are remapped to a fresh internal library
owner with a randomly generated password. No original accounts or conversations
are shipped. The Docker Qdrant collection `ee542_driving` contains 483 chunks of at
most 500 characters with 100-character overlap. Official URLs, editions, and
file fingerprints are recorded in `knowledge/dmv/`.

Repeated starts preserve existing data. Interrupted first imports can resume;
conflicting records or changed bundles cause a clear error rather than overwrite
work. Docker volumes retain data across container rebuilds and `docker compose
down`; `down -v` deletes volumes and must not be used to stop normal development.
Restoration requires no API key, but each question still calls OpenAI for its
query embedding and answer. Keep `OPENAI_EMBEDDING_MODEL=text-embedding-3-small`
for the restored baseline.

To intentionally generate fresh OpenAI embeddings instead, the existing
`docker compose exec backend python seed_driving.py` command remains available;
it uses real API credits. Do not run it as part of a normal teammate setup.

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
reinstall the APK. This optional Android configuration helper uses only the
Python standard library and does not require a virtual environment. Use the
matching signing certificate and keep private keys
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

From `groupchat_app_src`, the normal checks run inside the backend container:

```powershell
docker compose exec backend python -m unittest -v test_rag
docker compose exec backend python smoke_test.py --expect-model
```

The regression suite uses real MySQL/Qdrant and test-only AI doubles. The smoke
test needs the optional Llama service running and cleans up its temporary records.

Opt-in checks using the configured OpenAI account:

```powershell
docker compose exec backend python validate_part3_real.py
docker compose exec backend python validate_part4_real.py
```

These maintainer checks expect the existing `admin` account. A fresh teammate
installation does not need to run them or create an admin account to use the app.
Validation reports are in `artifacts/reports/`; APKs in `artifacts/apks/` and final
screenshots in `artifacts/screenshots/` are local ignored outputs. The lab8/lab9
inputs are in the repository's `docs/labs/` directory, mounted into the container.

`validate_part4_ui.py` is an optional advanced browser check. It requires a
separate Playwright/Chrome test environment; browser tooling is not installed in
the application image. Android checks additionally need an emulator and a Chrome
debugging connection. These tools are not required for normal Part 5 development.
Part 5 custom Word2Vec embeddings are outside the current scope.

## Part 5 Development

The initial baseline is ready for comparison; Word2Vec and histogram embeddings
are the teammate's implementation task, not part of the bootstrap bundle.

- Reuse `document_processing.py` and the imported `DocumentChunk` records for the
  same curated text and 500-character chunks.
- Implement Word2Vec, word clustering, centroids, and normalized histograms in a
  separate backend module. Transform questions with the same trained pipeline.
- Use a separate Qdrant collection, for example `ee542_driving_word2vec`, with
  dimension K. Preserve the existing 1536-dimensional `ee542_driving` baseline.
  Keep the restored document IDs, text, and baseline index metadata unchanged;
  use separate Word2Vec index metadata or an adapter that selects the shared
  chunks independently of the baseline's `vector_collection` field.
- `rag_service.py` supplies the embedding, retrieval, and answer-chain extension
  points; `driving.py` connects the curated library to the authenticated API.
  The Word2Vec version must change both document and question embedding paths.
- Modify local backend files: the bind-mounted source reloads automatically.
  Frontend edits also appear after refreshing. Python dependencies are installed
  in the image; update the dependency files and rebuild
  with `docker compose up -d --build backend` when adding packages.

From `groupchat_app_src`:

```powershell
docker compose logs -f backend
docker compose exec backend python -m unittest -v test_rag
docker compose stop
```

All services bind to loopback by default. `APP_PORT`, `MYSQL_PORT`, and
`QDRANT_PORT` in `.env` change host ports without changing container connections.
The container derives its MySQL URL from `MYSQL_PASSWORD` and the service hostname,
so passwords with URL-reserved characters are supported. It uses `qdrant:6333`
internally. The host only needs Docker for backend development.

If another backend already occupies port 8000, stop that backend or choose a
different `APP_PORT` before setup. Do not change initialized database passwords
without also changing them inside MySQL. Rerunning setup preserves nonempty
credentials and restarts services with updated OpenAI configuration.

On Linux/macOS without PowerShell, copy `.env.example` to `.env`, fill strong
`MYSQL_ROOT_PASSWORD`, `MYSQL_PASSWORD`, `JWT_SECRET` (32+ characters), and your
OpenAI key, then run `docker compose up -d --build --wait mysql qdrant backend`
from this directory. With either workflow, Llama remains behind the optional
`llm` profile and is not downloaded during the default Part 5 setup.

## Maintainer Data Export and Handoff Checks

`export_library.py` exports only the internal curated library from SQL and Qdrant.
It uses explicit fields and excludes users, credentials, private uploads, and
conversations. Run it against the source installation only when intentionally
refreshing the baseline, then review the bundle and `manifest.json` before sharing.
The importer refuses an updated checksum on a previously initialized installation;
test a changed baseline with fresh, separately named development volumes.

The sanitized acceptance report is
`artifacts/reports/Backend-handoff-validation.json`. It records successful fresh
restoration, repeat initialization, interrupted-import recovery, preservation of
existing data, exact vectors, and automatic source reload.

`validate_handoff.py` is an optional maintainer orchestration tool for a fresh,
disposable `ee542-part5-check*` Compose project. It requires Docker CLI plus a
separate Python tooling environment with `httpx` and `python-dotenv`; it is not
part of the application startup or the normal container regression suite. The
recorded handoff checks have already passed. No local tooling environment needs
to be kept just to run the backend or begin Part 5.

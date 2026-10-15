# Part 3: Document Embeddings and Q&A

## Fill in the OpenAI API Key

Edit **`groupchat_app_src/.env`** (the existing local file next to `compose.yaml`):

```dotenv
OPENAI_API_KEY=YOUR_ACTUAL_OPENAI_API_KEY
OPENAI_EMBEDDING_MODEL=text-embedding-3-small
OPENAI_CHAT_MODEL=gpt-4.1-mini
QDRANT_URL=http://127.0.0.1:6333
QDRANT_COLLECTION=ee542_documents
RAG_TOP_K=4
RAG_MIN_SCORE=0.25
```

Replace the key value, then **restart the FastAPI backend**. Keep the actual key out of
`.env.example`, frontend JavaScript, Android resources, and Git. The local `.env` is ignored.
The API key is used only by the backend. Valid API access and sufficient quota are required;
account/model availability can only be confirmed with a real key.

Part 1 continues to use the local Llama service. Part 3 uses OpenAI embeddings and OpenAI chat
through LangChain, as requested by the PDF. These settings are independent.

## Start Services

From `groupchat_app_src`:

```powershell
docker compose up -d mysql qdrant
.\start-backend.ps1
```

If the backend is already running, stop that process and start it again rather than launching
a second instance on port 8000. To include the optional Part 1 Llama service:

```powershell
docker compose --profile llm up -d mysql qdrant llama
```

Install dependencies from `backend` when restoring the project:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.lock.txt
```

Qdrant runs in `ee542-lab9-qdrant-1`, using image `qdrant/qdrant:v1.19.2`.
The database is bound only to `127.0.0.1:6333` and persists in the Docker volume
`ee542-lab9_qdrant_data`. Its local dashboard is http://127.0.0.1:6333/dashboard.
The collection is created lazily when the first real embedding batch is indexed.
Do not remove the volume if you want to retain vectors.

## Browser Workflow

1. Open http://localhost:8000 and register/log in.
2. Select **Document Q&A**.
3. In the sidebar, choose one or more PDF, TXT, MD, or DOCX files and click **Upload Documents**.
4. Use **Preview** to inspect extracted text and the first ten chunks.
5. Click **Index** for each document and wait until its status is **indexed**.
6. Select the indexed documents to search, then enter a question and click **Ask**.
7. Expand the source references below each answer to inspect filename, page, chunk, similarity,
   and the exact retrieved passage. Use **New Conversation** to start with fresh memory.

Document Q&A does not require a question mark. The separate Group Chat tab retains its
question-mark trigger for Llama replies. Both tabs are served by the same site, so the
existing Android TWA loads the new feature without rebuilding the APK; refresh it if cached.

Each upload accepts up to ten files, at most 10 MB per file. Text files must use UTF-8.
Scanned PDFs need OCR before upload; encrypted PDFs are rejected. DOCX/TXT/MD use one logical
page, while PDF chunks retain the actual source page number. Extraction is limited to
1,000,000 characters per document.

Without an API key, upload, extraction, SQL storage, and preview work. Indexing and document
answers return an explicit configuration error. No fake embeddings or answers are used in
the live application. Indexing sends extracted text to OpenAI; answering sends the question,
bounded conversation history, and retrieved passages.

## Storage and Retrieval

- MySQL `documents`: owner, filename, extracted text, page/chunk counts, indexing status, errors,
  embedding model, and collection.
- MySQL `document_chunks`: text, stable vector UUID, document ID, source page, and chunk index.
- MySQL `rag_conversations` and `rag_turns`: owner-scoped conversations and persisted questions,
  answers, and retrieved source references.
- Qdrant: cosine vectors with owner/document/model filters and source metadata.
- Chunker: LangChain `CharacterTextSplitter`, 500 characters, 100-character overlap. An empty
  separator guarantees the size limit even for long unbroken PDF lines.
- Retrieval: embed standalone questions directly; only explicit follow-ups inherit the previous
  question to avoid contamination from unrelated earlier topics. Retrieve up to
  `RAG_TOP_K` passages above `RAG_MIN_SCORE`, then invoke a LangChain prompt/model/parser chain.
  Immediate same-page neighbors are included as additional cited context to preserve facts
  across chunk boundaries; they are labeled adjacent context rather than assigned a fake
  similarity score. The stored and embedded chunks still have at most 500 characters.
- Memory: reload up to six prior turns from SQL into the prompt. This provides bounded,
  persistent conversation memory without deprecated `ConversationBufferMemory` APIs.
- Grounding: the prompt instructs English answers based only on retrieved passages, with
  citations. No matching passages produces an explicit "I do not know" answer. Real grounding
  quality still needs evaluation with the user's documents and a real OpenAI key.
- Documents, previews, vectors, and conversations are scoped to the authenticated owner.
  Document chat is private and is not broadcast into the shared group chat.

Indexing runs in background tasks so the web request returns promptly. Failed jobs can be
retried, using stable point IDs to avoid duplicate vectors. Interrupted jobs are marked
failed after a backend restart. Changing embedding models or collection settings requires
re-indexing; changing vector dimensions requires a new collection name.

## Command-Line Driver

Start the backend first. From `backend`:

```powershell
.\.venv\Scripts\python.exe rag_cli.py --username admin --folder "D:\path\to\documents"
```

The driver prompts for the password without displaying it, iterates supported files in the
folder, uploads/extracts them, starts embedding jobs, waits for indexing, and then runs a
conversation loop. Type **`exit`** to quit. Omit `--folder` to use all of your previously
indexed documents. Use `--url` to select a different backend address.

## Validation and Remaining Work

From `backend`, with MySQL and Qdrant running:

```powershell
.\.venv\Scripts\python.exe -m unittest -v test_rag
.\.venv\Scripts\python.exe smoke_test.py --expect-model
```

The first suite uses **explicit test-only embedding/model doubles**, real PDF extraction,
and real Docker MySQL/Qdrant. It verifies multiple uploads, hard chunk limits, owner isolation,
vector search, selected-document filtering, conversation memory, no-match behavior, missing-key
errors, indexing failure/retry, vector cleanup, and CLI exit. It does not claim real OpenAI
inference. The second suite verifies the existing live Llama group-chat flow.

Browser checks cover uploads, preview, missing-key feedback, English labels, and mobile/desktop
layout. Temporary test accounts, documents, and collections are cleaned up.

Real API validation using the repository's lab8.pdf and lab9.pdf is recorded in
[PART3_VALIDATION.md](PART3_VALIDATION.md). The local key has now been supplied; the current
configured chat model is `gpt-6-luna`. The app preserves that selection, omits unsupported
temperature settings for reasoning models, and uses reasoning effort `none` by default for
GPT-6 Luna. Optional settings: `OPENAI_REASONING_EFFORT` and `RAG_MAX_OUTPUT_TOKENS` (default 1200).
An empty model response is reported as an error and is not saved as a successful answer.

## Official References

- https://developers.openai.com/api/docs/guides/embeddings
- https://developers.openai.com/api/docs/models/gpt-4.1-mini
- https://docs.langchain.com/oss/python/integrations/splitters/character_text_splitter
- https://docs.langchain.com/oss/python/integrations/chat/openai
- https://qdrant.tech/documentation/quickstart/

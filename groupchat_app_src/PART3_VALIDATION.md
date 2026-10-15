# Part 3: Real API Validation

Validated on October 15, 2026 (America/Los_Angeles).

## Configuration

- Owner: existing `admin` account; documents and answers remain available in its private Document Q&A area.
- Embeddings: `text-embedding-3-small`, real OpenAI API.
- Chat: `gpt-6-luna`, real OpenAI API, reasoning effort `none`.
- Vector store: Docker Qdrant, collection `ee542_documents`.
- No test doubles or locally generated replacement embeddings were used for this validation.

## Uploaded Documents

| File | Pages | Chunks | Status |
| --- | ---: | ---: | --- |
| lab8.pdf | 10 | 71 | indexed |
| lab9.pdf | 6 | 26 | indexed |

All 97 vectors have 1536 dimensions. The count was checked after restarting the Qdrant container; all vectors persisted.

## Real Questions and Answers

### lab8_setup (PASS)

**Question:** In Step 1.1 of the CNN and DOCA lab, which GPU, operating system, and boot disk size are suggested?

**Answer:** Step 1.1 suggests an NVIDIA L4 GPU (a T4 also works), Ubuntu 22.04 LTS, and a 100 GB boot disk. [5]

**Retrieved files:** lab8.pdf

### lab8_followup (PASS)

**Question:** Why does that setup need a full virtual machine rather than a GPU container?

**Answer:** The setup needs a full virtual machine because Part 6 runs Docker. [2]

**Retrieved files:** lab8.pdf

### lab9_chunking (PASS)

**Question:** In Part 3, what text chunk size and LangChain splitter are required?

**Answer:** Use chunks of size 500 with LangChain’s `CharacterTextSplitter`. [1][2]

**Retrieved files:** lab9.pdf

### lab9_server_options (PASS)

**Question:** Which two self-hosted Llama server options are described in lab9.pdf?

**Answer:** The two options are:

- **Option A:** `llama.cpp` with a GGUF model, served using `llama-server`. [1][4]
- **Option B:** **vLLM**, using its OpenAI-compatible API server. [2]

**Retrieved files:** lab9.pdf

### unknown_answer (PASS)

**Question:** What is the instructor's favorite ice cream flavor?

**Answer:** I do not know based on the uploaded documents.

**Retrieved files:** None.

## Browser and CLI Checks

- Browser restored saved conversation history, selected only lab9.pdf, and submitted a new question after changing topics.
- The answer correctly identified chunk size 500 and displayed lab9.pdf source passages.
- Desktop and mobile layouts passed without JavaScript errors or horizontal overflow.
- The authenticated command-line loop returned a real document answer and exited on `exit`.
- Existing API tests also passed, covering account isolation, size limits, failure/retry, deletion, and no-match handling.

## Fixes Confirmed by Real Validation

- Reasoning models omit unsupported temperature settings. GPT-6 Luna uses reasoning effort none by default; model selection remains user-configured.
- Standalone retrieval queries no longer concatenate unrelated previous questions. Explicit follow-ups retain the previous question as context.
- Retrieved chunks are supplemented with immediate same-page neighbors to preserve facts split across chunk boundaries. Neighbor passages keep their actual chunk/page reference and are labeled adjacent context, without a fabricated similarity score.
- Stored chunks remain at most 500 characters with 100-character overlap; existing 97 vectors did not need replacement.

## Artifacts

- Structured results and a real vector sample: `artifacts/Part3-real-validation.json`.
- Desktop screenshot: `artifacts/Part3-real-desktop.png`.
- Mobile screenshot: `artifacts/Part3-real-mobile.png`.
- Opt-in reproducible API validation: `backend/validate_part3_real.py`.

No key, JWT, or password is recorded in this report. This is a targeted validation against these PDFs, not a guarantee that every possible document question will be answered correctly.

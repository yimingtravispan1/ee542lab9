# EE 542 Lab Report: Parts 1–4

**Project:** California Driving Test Assistant  
**Date:** October 15, 2026

This report addresses the implementation requirements in [the lab PDF](docs/labs/lab9.pdf). Parts 1–4 contain no separate list of written questions; the required technical points and results are answered below.

## Part 1: Web Application

- **Database/security:** MySQL 8.4 stores accounts and messages in `groupchat` with utf8mb4. A dedicated database user, generated passwords, Argon2 hashes, and JWT authentication protect access. Secrets remain in the ignored `.env`.
- **Interfaces:** FastAPI serves HTML/CSS/JavaScript. REST handles registration, login, history, and message submission; WebSockets broadcast messages. History persists after reconnecting.
- **Model/server:** We selected llama.cpp, using **Llama 3.2 3B Instruct Q4_K_M** on CPU with a 4096-token context, replacing the PDF's larger examples. Its Docker endpoint is `http://llama:8001/v1`. Messages containing `?` trigger replies. The alternative vLLM option was not needed.
- **Result:** Authentication, invalid-input rejection, two-client broadcasts, persistence, and real inference passed. “What is 2 + 2?” returned **4**, with the reply saved and broadcast.

## Part 2: Mobile Application Wrapper

Built and installed the Android TWA app **CA Driving Study**, package `com.helloworld.groupchat.twa`. An HTTPS origin and [Digital Asset Links](groupchat_app_src/frontend/.well-known/assetlinks.json) associate the website with the matching package and signing-certificate SHA-256 fingerprint, enabling full TWA without a browser address bar.

**Result:** Android Studio emulator testing with Chrome verified registration/login, chatbot responses, and restored sessions/history after reopening. The older Android 8.1 phone lacked a compatible browser; full TWA acceptance therefore used the permitted emulator option.

**Fresh verification (October 15, 2026):** The APK was rebuilt for a renewed HTTPS origin; Gradle build/lint passed. Against the Docker backend, emulator registration/login, group-message persistence, a real cited driving answer, and session/history restoration after restarting the app and browser passed. The native UI hierarchy confirmed no browser address bar; see [the fresh Android evidence](groupchat_app_src/artifacts/reports/Android-docker-validation.json).

**Limits:** The temporary Cloudflare hostname may change, requiring Android reconfiguration and rebuilding. ADB screenshots were black in this run; the saved page screenshot uses Chrome DevTools, so fresh native visual screenshot evidence remains unavailable.

## Part 3: Content Embeddings and LLM

1. **Collect:** A sidebar supports single/multiple PDF uploads plus TXT/MD/DOCX. The CLI processes a document folder. Extracted text, page provenance, and chunks are stored in MySQL.
2. **Chunk:** LangChain `CharacterTextSplitter` uses a **500-character maximum**, **100-character overlap**, and an empty separator. Overlap preserves boundary context; final chunks may be shorter.
3. **Embed/store:** OpenAI `text-embedding-3-small` creates **1536-dimensional** vectors stored in Docker Qdrant, filtered by document owner.
4. **Retrieve/answer:** Questions use the same embedding model. Cosine similarity retrieves matching chunks, with adjacent context expansion. A LangChain conversation chain uses **gpt-6-luna**, retrieved passages, and six recent turns. SQL-backed bounded memory implements the requested conversation-memory behavior. Answers cite sources and acknowledge insufficient evidence.
5. **Driver:** `rag_cli.py` repeatedly reads questions, prints answers/sources, and stops when the user types `exit`.

**Results:** `lab8.pdf` yielded 71 chunks from 10 pages; `lab9.pdf` yielded 26 from 6 pages. All **97 vectors** survived a Qdrant restart. Five real-API cases, browser checks, and the authenticated CLI passed. The system correctly answered **CharacterTextSplitter, 500 characters** and declined an unsupported question about the instructor's favorite ice-cream flavor.

**Actual embedding example:** A chunk from `lab8.pdf`, PDF page 4, contains `rte_eth_rx_burst(...)`; its vector begins `[-0.030346941, -0.028088849, -0.0205517, -0.024610166, ...]`. This previews 1536 dimensions. Full provenance and test results are in the [Part 3 evidence](groupchat_app_src/artifacts/reports/Part3-real-validation.json).

## Part 4: Custom Content Chatbot App

**Topic/audience:** California Class C driving-test preparation for new drivers, including learners studying English examiner instructions. Official DMV sources provide focused coverage of rules, road-test preparation, and vocabulary.

| Source | Edition | Pages | Chunks |
|---|---|---:|---:|
| California Driver's Handbook | June 2025 | 92 | 373 |
| Driving Test Criteria | October 2017 | 40 | 104 |
| Words and Phrases for Class C Driving Tests | March 2022 | 2 | 6 |
| **Total** | | **134** | **483** |

The shared `ee542_driving` library powers Driving Study on the website and Android app. Features include suggested questions, citations, source passages, edition notices, unofficial practice, and private conversations. Cross-page checklist retrieval improves safety-check answers.

**Results:** [Eight cases passed](groupchat_app_src/artifacts/reports/Part4-real-validation.json), covering rules, safety checks, vocabulary, unknown facts, practice, version limits, new-user access, and unrelated-topic rejection. A lane-change answer explained signaling, mirrors/traffic, blind spots, and available space with citations. [Web/mobile and emulator checks](groupchat_app_src/artifacts/reports/Part4-ui-validation.json) verified answers and restored history.

**Limits:** The historical editions, especially the 2017 criteria, cannot establish current requirements. Users are directed to DMV for updates. Practice is unofficial; image-only content is not indexed.

## Reproducibility and Missing Deliverables

Docker Compose runs FastAPI, MySQL, and Qdrant; Llama is optional for group chat. The **3.36 MiB** DMV bundle restores existing vectors without re-embedding or sharing accounts/keys. Fresh setup, repeat initialization, recovery, data preservation, source reload, four regression tests, and real cited answers passed; see the [handoff evidence](groupchat_app_src/artifacts/reports/Backend-handoff-validation.json) and [startup instructions](README.md).

**Parts 1–4 functionality is complete.** No video log was found in the project, so the PDF's required video demonstration cannot be claimed as submitted. **Part 5 Word2Vec, clustering, histogram embeddings, and improvement results remain outside this report.** Final APKs/screenshots are local ignored artifacts; attach them separately if required.

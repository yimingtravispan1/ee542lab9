(() => {
  let active = false;
  let timer;
  let documents = [];
  let selected = new Set();
  let initialized = false;
  let conversationId = null;
  let busy = false;
  let generation = 0;

  function storageKey() {
    return "ragConversation:" + JSON.parse(atob(token.split(".")[1].replace(/-/g, "+").replace(/_/g, "/"))).sub;
  }

  function setMode(showDocuments) {
    active = showDocuments;
    $("groupPanel").classList.toggle("hidden", active);
    $("documentsPanel").classList.toggle("hidden", !active);
    $("groupTab").setAttribute("aria-pressed", String(!active));
    $("documentsTab").setAttribute("aria-pressed", String(active));
    clearTimeout(timer);
    if (active) refresh();
  }

  function addTurn(kind, text, sources = []) {
    const message = document.createElement("div");
    message.className = "message" + (kind === "assistant" ? " bot" : "");
    const heading = document.createElement("div");
    heading.className = "meta";
    heading.textContent = kind === "assistant" ? "Document Assistant" : "You";
    const body = document.createElement("div");
    body.textContent = text;
    message.append(heading, body);
    if (sources.length) {
      const list = document.createElement("div");
      list.className = "sources";
      sources.forEach((source, i) => {
        const details = document.createElement("details");
        const label = document.createElement("summary");
        const match = source.score === null ? "adjacent context" : `score ${source.score}`;
        label.textContent = `[${i + 1}] ${source.filename} / page ${source.page} / chunk ${source.chunk_index + 1} / ${match}`;
        const passage = document.createElement("p");
        passage.textContent = source.text;
        details.append(label, passage);
        list.append(details);
      });
      message.append(list);
    }
    $("ragMessages").append(message);
    $("ragMessages").scrollTop = $("ragMessages").scrollHeight;
  }

  async function restoreConversation() {
    const current = generation;
    const key = storageKey();
    conversationId = localStorage.getItem(key);
    $("ragMessages").replaceChildren();
    if (!conversationId) return;
    try {
      const history = await callAPI("/rag/conversations/" + conversationId);
      if (current !== generation) return;
      history.turns.forEach(turn => {
        addTurn("user", turn.question);
        addTurn("assistant", turn.answer, turn.sources);
      });
    } catch (error) {
      if (current !== generation) return;
      conversationId = null;
      localStorage.removeItem(key);
      $("ragStatus").textContent = error.message;
    }
  }

  function renderDocuments() {
    const list = $("documentList");
    list.replaceChildren();
    if (!documents.length) {
      list.textContent = "No documents uploaded yet.";
      return;
    }
    documents.forEach(doc => {
      const card = document.createElement("div");
      card.className = "document-card";
      const label = document.createElement("label");
      const checkbox = document.createElement("input");
      checkbox.type = "checkbox";
      checkbox.checked = selected.has(doc.id);
      checkbox.disabled = doc.status !== "indexed";
      checkbox.onchange = () => checkbox.checked ? selected.add(doc.id) : selected.delete(doc.id);
      const name = document.createElement("strong");
      name.textContent = doc.filename;
      label.append(checkbox, name);
      const status = document.createElement("p");
      status.className = "hint";
      status.textContent = `${doc.status} / ${doc.pages} pages / ${doc.chunks} chunks`;
      card.append(label, status);
      if (doc.error) {
        const error = document.createElement("p");
        error.className = "msg";
        error.textContent = doc.error;
        card.append(error);
      }
      const actions = document.createElement("div");
      actions.className = "document-actions";
      function action(text, run) {
        const button = document.createElement("button");
        button.textContent = text;
        button.disabled = doc.status === "indexing";
        button.onclick = async () => {
          button.disabled = true;
          try { await run(); }
          catch (error) { $("uploadStatus").textContent = error.message; }
          finally { button.disabled = false; }
        };
        actions.append(button);
      }
      action(doc.status === "indexed" ? "Re-index" : "Index", async () => {
        await callAPI(`/documents/${doc.id}/index`, "POST");
        selected.add(doc.id);
        $("uploadStatus").textContent = "Indexing started. This can take a few minutes.";
        await refresh();
      });
      action("Preview", async () => {
        const data = await callAPI(`/documents/${doc.id}/chunks`);
        $("chunkPreviewText").textContent = data.chunks.map(chunk => `Page ${chunk.page}, chunk ${chunk.index + 1} (${chunk.text.length} characters)\n${chunk.text}`).join("\n\n");
        $("chunkPreview").classList.remove("hidden");
        $("chunkPreview").open = true;
      });
      action("Delete", async () => {
        if (!confirm(`Delete ${doc.filename} and its vectors?`)) return;
        await callAPI(`/documents/${doc.id}`, "DELETE");
        selected.delete(doc.id);
        await refresh();
      });
      card.append(actions);
      list.append(card);
    });
  }

  async function refresh() {
    clearTimeout(timer);
    if (!active || !token) return;
    const current = generation;
    try {
      const [status, listing] = await Promise.all([callAPI("/rag/status"), callAPI("/documents")]);
      if (current !== generation) return;
      documents = listing.documents;
      if (!initialized) {
        selected = new Set(documents.map(doc => doc.id));
        initialized = true;
      }
      const states = [status.openai_configured ? "OpenAI key configured" : "OpenAI key missing: uploads and previews work; indexing and answers require server configuration.", status.qdrant_ready ? "Vector database connected" : "Vector database unavailable"];
      $("ragServiceStatus").textContent = states.join(" / ");
      renderDocuments();
    } catch (error) {
      $("ragServiceStatus").textContent = error.message;
    } finally {
      if (active && token && current === generation) timer = setTimeout(refresh, 4000);
    }
  }

  $("chooseDocumentsBtn").onclick = () => $("documentFiles").click();
  $("documentFiles").onchange = () => {
    const files = Array.from($("documentFiles").files);
    $("selectedFileNames").textContent = files.length ? files.map(file => file.name).join(", ") : "No files selected.";
  };
  $("uploadDocumentsBtn").onclick = async () => {
    const current = generation;
    const files = Array.from($("documentFiles").files);
    if (!files.length || files.length > 10) {
      $("uploadStatus").textContent = "Choose between 1 and 10 documents.";
      return;
    }
    if (files.some(file => file.size > 10 * 1024 * 1024)) {
      $("uploadStatus").textContent = "Each file must be 10 MB or smaller.";
      return;
    }
    const form = new FormData();
    files.forEach(file => form.append("files", file));
    $("uploadDocumentsBtn").disabled = true;
    $("uploadStatus").textContent = "Extracting and saving document text...";
    try {
      const response = await fetch(API + "/documents", {method: "POST", headers: {Authorization: "Bearer " + token}, body: form});
      const data = await response.json();
      if (current !== generation) return;
      if (!response.ok) throw new Error(typeof data.detail === "string" ? data.detail : "Upload failed.");
      data.documents.forEach(doc => selected.add(doc.id));
      $("uploadStatus").textContent = `Saved ${data.documents.length} documents. Click Index to create embeddings. ` + data.errors.map(error => `${error.filename}: ${error.error}`).join(" ");
      $("documentFiles").value = "";
      $("selectedFileNames").textContent = "No files selected.";
      await refresh();
    } catch (error) {
      if (current === generation) $("uploadStatus").textContent = error.message;
    } finally {
      $("uploadDocumentsBtn").disabled = false;
    }
  };

  $("ragQuestionForm").onsubmit = async event => {
    event.preventDefault();
    if (busy) return;
    const question = $("ragQuestion").value.trim();
    if (!question) return;
    const ids = documents.filter(doc => doc.status === "indexed" && selected.has(doc.id)).map(doc => doc.id);
    if (!ids.length) {
      $("ragStatus").textContent = "Select at least one indexed document first.";
      return;
    }
    busy = true;
    $("askRagBtn").disabled = true;
    $("newRagChatBtn").disabled = true;
    $("ragStatus").textContent = "Searching documents and generating an answer...";
    const current = generation;
    try {
      if (!conversationId) {
        conversationId = (await callAPI("/rag/conversations", "POST")).id;
        localStorage.setItem(storageKey(), conversationId);
      }
      const data = await callAPI("/rag/ask", "POST", {conversation_id: conversationId, question, document_ids: ids});
      if (current !== generation) return;
      addTurn("user", question);
      addTurn("assistant", data.answer, data.sources);
      $("ragQuestion").value = "";
      $("ragStatus").textContent = "";
    } catch (error) {
      if (current === generation) $("ragStatus").textContent = error.message;
    } finally {
      busy = false;
      $("askRagBtn").disabled = false;
      $("newRagChatBtn").disabled = false;
    }
  };

  $("newRagChatBtn").onclick = () => {
    conversationId = null;
    localStorage.removeItem(storageKey());
    $("ragMessages").replaceChildren();
    $("ragStatus").textContent = "New conversation started.";
  };
  $("groupTab").onclick = () => setMode(false);
  $("documentsTab").onclick = () => setMode(true);
  document.addEventListener("signedin", () => {
    generation++;
    initialized = false;
    restoreConversation();
  });
  document.addEventListener("signedout", () => {
    generation++;
    clearTimeout(timer);
    documents = [];
    selected.clear();
    initialized = false;
    conversationId = null;
    $("ragMessages").replaceChildren();
    $("documentList").replaceChildren();
    $("chunkPreviewText").textContent = "";
    $("uploadStatus").textContent = "";
    $("ragStatus").textContent = "";
    $("documentFiles").value = "";
    $("selectedFileNames").textContent = "No files selected.";
    $("chunkPreview").classList.add("hidden");
    setMode(false);
  });
})();

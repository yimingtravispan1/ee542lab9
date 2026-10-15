(() => {
  let conversation = null;
  let generation = 0;
  let busy = false;
  let ready = false;
  let catalog = [];
  const key = () => 'drivingConversation:' + JSON.parse(atob(token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/'))).sub;

  function showDriving() {
    document.dispatchEvent(new Event('drivingmode'));
    ['groupPanel', 'documentsPanel'].forEach(id => $(id).classList.add('hidden'));
    $('drivingPanel').classList.remove('hidden');
    ['groupTab', 'documentsTab'].forEach(id => $(id).setAttribute('aria-pressed', 'false'));
    $('drivingTab').setAttribute('aria-pressed', 'true');
  }

  function addTurn(kind, text, sources = []) {
    const message = document.createElement('div');
    message.className = 'message' + (kind === 'assistant' ? ' bot' : '');
    const heading = document.createElement('div');
    heading.className = 'meta';
    heading.textContent = kind === 'assistant' ? 'Driving Study Assistant' : 'You';
    const body = document.createElement('div');
    body.textContent = text;
    message.append(heading, body);
    const list = document.createElement('details');
    list.className = 'sources';
    const sourceHeading = document.createElement('summary');
    sourceHeading.textContent = `Sources (${sources.length} passages)`;
    list.append(sourceHeading);
    sources.forEach((source, index) => {
      const details = document.createElement('details');
      const summary = document.createElement('summary');
      summary.textContent = `[${index + 1}] ${source.filename} / PDF page ${source.page}`;
      const excerpt = document.createElement('p');
      excerpt.textContent = source.text;
      details.append(summary, excerpt);
      const entry = catalog.find(item => item.filename === source.filename);
      if (entry) {
        const link = document.createElement('a');
        link.href = entry.current_reference || entry.url;
        link.textContent = 'View official DMV source';
        link.target = '_blank';
        link.rel = 'noopener noreferrer';
        details.append(link);
      }
      list.append(details);
    });
    if (sources.length) message.append(list);
    $('drivingMessages').append(message);
    $('drivingMessages').scrollTop = $('drivingMessages').scrollHeight;
  }

  async function initialize() {
    const current = ++generation;
    ready = false;
    showDriving();
    $('drivingMessages').replaceChildren();
    $('drivingLibrary').replaceChildren();
    $('drivingStatus').textContent = 'Loading the driving library...';
    conversation = localStorage.getItem(key());
    try {
      const library = await callAPI('/driving/library');
      if (current !== generation) return;
      catalog = library.sources;
      ready = library.ready;
      $('drivingNotice').textContent = library.notice;
      catalog.forEach(source => {
        const card = document.createElement('p');
        const link = document.createElement('a');
        link.href = source.url;
        link.target = '_blank';
        link.rel = 'noopener noreferrer';
        link.textContent = source.title;
        const detail = document.createElement('span');
        const doc = library.documents.find(d => d.filename === source.filename);
        detail.textContent = ` — ${source.edition}; ${doc ? doc.pages + ' pages / ' + doc.status : 'not indexed'}. ${source.purpose}`;
        card.append(link, detail);
        $('drivingLibrary').append(card);
      });
      $('drivingStatus').textContent = ready ? '' : 'The driving library is being prepared. Please retry later.';
      if (conversation) {
        try {
          const history = await callAPI('/rag/conversations/' + conversation);
          if (current !== generation) return;
          history.turns.forEach(turn => {
            addTurn('user', turn.question);
            addTurn('assistant', turn.answer, turn.sources);
          });
        } catch (error) {
          if (current !== generation) return;
          conversation = null;
          localStorage.removeItem(key());
          $('drivingStatus').textContent = error.message;
        }
      }
    } catch (error) {
      if (current === generation) $('drivingStatus').textContent = error.message;
    }
  }

  $('drivingQuestionForm').onsubmit = async event => {
    event.preventDefault();
    if (busy) return;
    if (!ready) { $('drivingStatus').textContent = 'The driving library is not ready. Log in again after it is indexed.'; return; }
    const question = $('drivingQuestion').value.trim();
    if (!question) return;
    const current = generation;
    const storageKey = key();
    busy = true;
    $('askDrivingBtn').disabled = true;
    $('newDrivingChatBtn').disabled = true;
    $('drivingStatus').textContent = 'Searching the DMV library and preparing your answer...';
    try {
      if (!conversation) {
        const created = await callAPI('/rag/conversations', 'POST');
        if (current !== generation) return;
        conversation = created.id;
        localStorage.setItem(storageKey, conversation);
      }
      const result = await callAPI('/driving/ask', 'POST', {conversation_id: conversation, question});
      if (current !== generation) return;
      addTurn('user', question);
      addTurn('assistant', result.answer, result.sources);
      $('drivingQuestion').value = '';
      $('drivingStatus').textContent = '';
    } catch (error) {
      if (current === generation) $('drivingStatus').textContent = error.message;
    } finally {
      busy = false;
      $('askDrivingBtn').disabled = false;
      $('newDrivingChatBtn').disabled = false;
    }
  };
  $('newDrivingChatBtn').onclick = () => {
    conversation = null;
    localStorage.removeItem(key());
    $('drivingMessages').replaceChildren();
    $('drivingStatus').textContent = 'New study conversation started.';
  };
  document.querySelectorAll('[data-study-question]').forEach(button => {
    button.onclick = () => { $('drivingQuestion').value = button.dataset.studyQuestion; $('drivingQuestion').focus(); };
  });
  $('drivingTab').onclick = showDriving;
  document.addEventListener('signedin', initialize);
  document.addEventListener('signedout', () => {
    generation++;
    ready = false;
    conversation = null;
    catalog = [];
    $('drivingMessages').replaceChildren();
    $('drivingLibrary').replaceChildren();
    $('drivingQuestion').value = '';
    $('drivingStatus').textContent = '';
  });
})();

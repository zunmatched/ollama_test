const $ = (id) => document.getElementById(id);
let running = false;
let toolCount = 0;
function setText(id, text) { $(id).textContent = text; }

// Render the model's Markdown using DOM nodes only; model output is never treated as HTML.
function renderInline(text, parent) {
  const pattern = /\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)|\*\*(.+?)\*\*|__(.+?)__|`([^`]+)`|\*(?!\s)(.+?)(?<!\s)\*|_(?!\s)(.+?)(?<!\s)_/g;
  let start = 0;
  for (const match of text.matchAll(pattern)) {
    parent.append(document.createTextNode(text.slice(start, match.index)));
    let node;
    if (match[1] !== undefined) {
      node = document.createElement('a'); node.href = match[2];
      node.target = '_blank'; node.rel = 'noopener noreferrer';
      node.textContent = match[1];
    } else if (match[3] !== undefined || match[4] !== undefined) {
      node = document.createElement('strong'); node.textContent = match[3] ?? match[4];
    } else if (match[5] !== undefined) {
      node = document.createElement('code'); node.textContent = match[5];
    } else {
      node = document.createElement('em'); node.textContent = match[6] ?? match[7];
    }
    parent.append(node);
    start = match.index + match[0].length;
  }
  parent.append(document.createTextNode(text.slice(start)));
}

function renderMarkdown(target, markdown) {
  target.replaceChildren();
  const lines = String(markdown).replace(/\r\n?/g, '\n').split('\n');
  let paragraph = [], list = null, listIndent = 0, code = null;
  const flushParagraph = () => {
    if (!paragraph.length) return;
    const p = document.createElement('p');
    paragraph.forEach((line, index) => {
      if (index) p.append(document.createElement('br'));
      renderInline(line, p);
    });
    target.append(p); paragraph = [];
  };
  const flushList = () => { if (list) target.append(list); list = null; };
  for (const line of lines) {
    if (code) {
      if (/^\s*```/.test(line)) { target.append(code); code = null; }
      else code.firstChild.textContent += (code.firstChild.textContent ? '\n' : '') + line;
      continue;
    }
    if (/^\s*```/.test(line)) {
      flushParagraph(); flushList();
      code = document.createElement('pre');
      const codeNode = document.createElement('code'); code.append(codeNode);
      continue;
    }
    if (!line.trim()) { flushParagraph(); flushList(); continue; }
    const heading = line.match(/^\s*(#{1,3})\s+(.+?)\s*#*\s*$/);
    if (heading) {
      flushParagraph(); flushList();
      const node = document.createElement(`h${heading[1].length}`);
      renderInline(heading[2], node); target.append(node); continue;
    }
    const item = line.match(/^(\s*)([-+*]|\d+[.)])\s+(.+)$/);
    if (item) {
      flushParagraph();
      const type = /^\d/.test(item[2]) ? 'ol' : 'ul';
      if (!list || list.tagName.toLowerCase() !== type) { flushList(); list = document.createElement(type); }
      const li = document.createElement('li');
      listIndent = Math.min(3, Math.floor(item[1].length / 2));
      if (listIndent) li.style.marginLeft = `${listIndent * 1.2}rem`;
      renderInline(item[3], li); list.append(li); continue;
    }
    flushList(); paragraph.push(line);
  }
  flushParagraph(); flushList();
  if (code) target.append(code);
}

async function refreshStatus() {
  try {
    const response = await fetch('/api/status');
    const data = await response.json();
    const snapshot = data.snapshot;
    setText('database-backend', snapshot.database_backend || 'SQLite 快照');
    const ready = data.ollama.ready && !snapshot.error;
    setText('connection', ready ? '● 本機服務就緒' : '● 等待模型或資料');
    $('connection').className = 'connection' + (ready ? ' ready' : '');
    const modelNames = { 'stock-agent:4b': 'Qwen3 4B Instruct', 'qwen3.5:4b': 'Qwen3.5 4B' };
    setText('model', modelNames[data.ollama.model] || data.ollama.model);
    setText('latest', snapshot.price_last_date || '尚未匯入');
    setText('price-count', (snapshot.price_rows || 0).toLocaleString());
    setText('news-count', (snapshot.news_rows || 0).toLocaleString());
    const model = data.ollama.loaded.find(m => m.name === data.ollama.model ||
      (data.ollama.model === 'stock-agent:4b' && m.name === 'qwen3:4b-instruct-2507-q4_K_M'));
    setText('gpu', model ? `${(model.size_vram / 1024 ** 3).toFixed(1)} GiB 顯存` : '首次查詢時載入');
    setText('stock-list', snapshot.stocks ? snapshot.stocks.map(s => `${s.ticker} ${s.name}`).join(' ／ ') : snapshot.error);
    if (!$('examples').children.length && snapshot.price_last_date) {
      const end = snapshot.price_last_date;
      const start = end.slice(0, 8) + '01';
      const examples = [
        ['查行情', '查詢台積電（2330）最近五個交易日的收盤價。'],
        ['比較價格', `比較 2330 和 2303 在 ${start} 至 ${end} 的價格變動百分比。`],
        ['找新聞', '搜尋「記憶體」最近三則新聞，整理重點並附來源日期。'],
        ['資料不足', '查詢 2330 在 2030-01-01 的收盤價，只查這一天。'],
      ];
      for (const [label, question] of examples) {
        const button = document.createElement('button');
        button.type = 'button'; button.className = 'example'; button.textContent = label;
        button.addEventListener('click', () => { if (!running) { $('question').value = question; $('question').focus(); } });
        $('examples').append(button);
      }
    }
  } catch { setText('connection', '● 無法連線本機服務'); }
}

function eventReceived(event) {
  if (event.type === 'status') {
    setText('status', event.text);
    if (event.text.startsWith('檢查')) {
      const note = document.createElement('div'); note.className = 'trace-note';
      note.textContent = '✓ ' + event.text; $('trace').append(note);
    }
  }
  if (event.type === 'tool_start') setText('status', `正在執行 ${event.name}`);
  if (event.type === 'tool_result') {
    toolCount++;
    setText('tool-count', `${toolCount} 次工具呼叫`);
    const card = document.createElement('details'); card.className = 'trace-card'; card.open = toolCount === 1;
    const summary = document.createElement('summary');
    summary.textContent = `${String(toolCount).padStart(2, '0')}  ${event.name} · ${event.elapsed_ms} ms`;
    const pre = document.createElement('pre');
    pre.textContent = JSON.stringify({arguments: event.arguments, result: event.result}, null, 2);
    card.append(summary, pre);
    for (const row of event.result.rows || []) {
      if (!row.url) continue;
      try {
        const url = new URL(row.url);
        if (!['http:', 'https:'].includes(url.protocol)) continue;
        const link = document.createElement('a'); link.className = 'source-link';
        link.href = url.href; link.target = '_blank'; link.rel = 'noopener noreferrer';
        link.textContent = `↗ 原文（需網路）：${row.title || row.id}`;
        card.append(link);
      } catch { /* Invalid source URLs are displayed as text only in tool output. */ }
    }
    $('trace').append(card);
  }
  if (event.type === 'answer') { $('answer').className = 'answer'; renderMarkdown($('answer'), event.text); }
  if (event.type === 'done') {
    setText('status', '查詢完成');
    for (const text of [`總耗時 ${event.elapsed_s} 秒`, `${event.tool_calls} 次工具呼叫`, `生成速度 ${event.generation_tokens_per_s ?? '—'} tokens/s`]) {
      const span = document.createElement('span'); span.className = 'metric'; span.textContent = text; $('metrics').append(span);
    }
  }
  if (event.type === 'error') { $('answer').className = 'answer'; setText('answer', event.text); setText('status', '未完成'); }
}

$('ask-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  const question = $('question').value.trim();
  if (running || !question) return;
  running = true; toolCount = 0;
  $('submit').disabled = true;
  $('trace').replaceChildren(); $('metrics').replaceChildren();
  setText('tool-count', '0 次工具呼叫'); setText('answer', '正在查詢，首次載入模型可能需要稍候…');
  $('answer').className = 'answer empty'; setText('status', '連線模型');
  try {
    const response = await fetch('/api/chat', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({question})});
    if (!response.ok) { const body = await response.json(); throw new Error(typeof body.detail === 'string' ? body.detail : '請求失敗'); }
    const reader = response.body.getReader(); const decoder = new TextDecoder(); let buffer = '';
    while (true) {
      const {value, done} = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, {stream: true});
      const lines = buffer.split('\n'); buffer = lines.pop();
      for (const line of lines) if (line.trim()) eventReceived(JSON.parse(line));
    }
    buffer += decoder.decode();
    if (buffer.trim()) eventReceived(JSON.parse(buffer));
  } catch (error) { setText('answer', error.message || '連線失敗'); setText('status', '未完成'); }
  finally { running = false; $('submit').disabled = false; refreshStatus(); }
});
refreshStatus();

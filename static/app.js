const $ = (id) => document.getElementById(id);
let lastSnapshot = null;
let busy = false;

async function request(path, body) {
  const response = await fetch(path, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: body === undefined ? '{}' : JSON.stringify(body)});
  const data = await response.json();
  if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'Request failed');
  return data;
}

function message(text, error = false) {
  $('message').textContent = text;
  $('message').classList.toggle('error', error);
}

function bytes(value) {
  if (value == null) return '—';
  const units = ['B', 'KB', 'MB', 'GB'];
  let index = 0;
  while (value >= 1024 && index < units.length - 1) { value /= 1024; index++; }
  return `${value.toFixed(index ? 1 : 0)} ${units[index]}`;
}

function make(tag, className, content) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (content != null) node.textContent = content;
  return node;
}

function jobElement(job) {
  const row = make('div', 'job');
  const top = make('div', 'job-top');
  top.append(make('div', 'job-title', job.title || 'Waiting for information'));
  top.append(make('div', 'job-meta', `${job.platform || '—'} · ${job.url}`));
  row.append(top);
  const side = make('div', 'job-side');
  side.append(make('span', `status ${job.status}`, job.cancel_requested ? 'Cancelling…' : job.status));
  const controls = make('div', 'job-controls');
  if (['queued', 'fetching', 'downloading', 'processing'].includes(job.status)) {
    const button = make('button', '', 'Cancel');
    button.disabled = job.cancel_requested;
    button.onclick = () => action(`/api/jobs/${job.id}/cancel`);
    controls.append(button);
  } else if (job.status === 'failed') {
    const button = make('button', '', 'Retry');
    button.onclick = () => action(`/api/jobs/${job.id}/retry`);
    controls.append(button);
  }
  side.append(controls); row.append(side);
  if (job.status === 'downloading' || job.status === 'processing') {
    const detail = make('div', 'job-detail');
    const percent = job.percent == null ? 'Progress unknown' : `${job.percent.toFixed(1)}%`;
    detail.append(make('span', '', `${percent} · ${bytes(job.downloaded_bytes)} / ${bytes(job.total_bytes)}`));
    const speed = job.speed ? `${bytes(job.speed)}/s` : '';
    const eta = job.eta != null ? ` · ${Math.ceil(job.eta)}s left` : '';
    detail.append(make('span', '', speed + eta)); row.append(detail);
    const bar = make('div', 'progress');
    const fill = make('span'); fill.style.width = `${job.percent || 0}%`; bar.append(fill); row.append(bar);
  } else if (job.status === 'completed') {
    row.append(make('div', 'job-detail', job.file_path));
  } else if (job.error) {
    row.append(make('div', 'job-detail error', job.error));
  }
  return row;
}

function render(data) {
  lastSnapshot = data;
  $('queued-count').textContent = data.counts.queued;
  $('active-count').textContent = data.active;
  $('completed-count').textContent = data.counts.completed;
  $('failed-count').textContent = data.counts.failed;
  $('concurrency').value = String(data.concurrency);
  $('queue-subtitle').textContent = data.jobs.length ? `${data.jobs.length} items · ${data.download_folder}` : 'Your videos will appear here.';
  $('clear').disabled = !data.counts.completed;
  const list = $('jobs'); list.replaceChildren();
  if (!data.jobs.length) {
    const empty = make('div', 'empty');
    empty.append(make('div', 'empty-icon', '↓'), make('strong', '', 'Nothing in the queue yet'), make('span', '', 'Add a link above to get started.'));
    list.append(empty);
  } else {
    for (const job of [...data.jobs].reverse()) list.append(jobElement(job));
  }
}

async function refresh() {
  try { const response = await fetch('/api/jobs'); if (!response.ok) throw new Error('Server unavailable'); render(await response.json()); }
  catch { message('Connection to the local server was lost. Restart the app if needed.', true); }
}

async function action(path, body) {
  try { const data = await request(path, body); if (data.jobs) render(data); else await refresh(); return data; }
  catch (error) { message(error.message, true); return null; }
}

function showInvalid(items) {
  const box = $('invalid'); box.replaceChildren(); box.hidden = !items.length;
  if (!items.length) return;
  box.append(make('strong', '', `${items.length} link${items.length === 1 ? '' : 's'} skipped`));
  for (const item of items) box.append(make('div', '', `Line ${item.line}: ${item.error} — ${item.url}`));
}

$('add').onclick = async () => {
  if (busy) return;
  const urls = $('urls').value;
  if (!urls.trim()) { message('Paste at least one video URL.', true); return; }
  busy = true; $('add').disabled = true;
  try {
    const result = await request('/api/jobs', {urls, quality: $('quality').value});
    showInvalid(result.invalid);
    if (result.added.length) $('urls').value = '';
    message(`${result.added.length} added to the queue${result.invalid.length ? `; ${result.invalid.length} skipped` : ''}.`);
    await refresh();
  } catch (error) { message(error.message, true); }
  finally { busy = false; $('add').disabled = false; }
};

$('start').onclick = async () => {
  if ($('urls').value.trim()) await $('add').onclick();
  const result = await action('/api/start');
  if (result) message('Downloads started. Add more links at any time.');
};
$('concurrency').onchange = async () => {
  const result = await action('/api/settings', {concurrency: Number($('concurrency').value)});
  if (result) message(`Downloading up to ${result.concurrency} at once.`);
};
$('clear').onclick = () => action('/api/clear-completed');
$('open-folder').onclick = () => action('/api/open-folder');
refresh(); setInterval(refresh, 1000);

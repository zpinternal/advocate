let currentSessionId = null;
let currentRemoteCwd = '.';

function writeApi(payload) {
  document.getElementById('apiOut').textContent = JSON.stringify(payload, null, 2);
}

async function api(url, options = {}) {
  const resp = await fetch(url, options);
  const body = await resp.json();
  writeApi(body);
  if (!resp.ok || !body.ok) {
    throw new Error(body.error?.message || `Request failed: ${resp.status}`);
  }
  return body.data;
}

function sessionQuery() {
  return currentSessionId ? `session_id=${encodeURIComponent(currentSessionId)}` : '';
}

function renderItems(items) {
  const tbody = document.querySelector('#ftpTable tbody');
  tbody.innerHTML = '';
  items.forEach((item) => {
    const tr = document.createElement('tr');
    const name = document.createElement('td');
    name.textContent = item.name;
    const path = document.createElement('td');
    path.textContent = item.path;
    const actions = document.createElement('td');

    const browse = document.createElement('button');
    browse.className = 'small-btn';
    browse.textContent = 'Browse';
    browse.addEventListener('click', () => loadListing(item.path));

    const download = document.createElement('a');
    download.className = 'small-btn';
    download.textContent = 'Download';
    const qp = sessionQuery();
    const prefix = qp ? `${qp}&` : '';
    download.href = `/ftp/download?${prefix}remote_path=${encodeURIComponent(item.path)}`;

    actions.append(browse, download);
    tr.append(name, path, actions);
    tbody.appendChild(tr);
  });
}

async function loadListing(path = currentRemoteCwd) {
  const query = new URLSearchParams({ path });
  if (currentSessionId) {
    query.set('session_id', currentSessionId);
  }
  const data = await api(`/ftp/browse?${query.toString()}`);
  currentRemoteCwd = data.cwd;
  document.getElementById('browsePath').value = currentRemoteCwd;
  document.getElementById('cwdLabel').textContent = `Remote listing: ${currentRemoteCwd}`;
  renderItems(data.items);
}

async function restoreSession() {
  const data = await api('/ftp/session');
  if (!data.session) {
    return;
  }
  currentSessionId = data.session.id;
  document.getElementById('host').value = data.session.host;
  document.getElementById('port').value = data.session.port;
  document.getElementById('username').value = data.session.username;
  document.getElementById('password').value = '';
  document.getElementById('useSsl').checked = data.session.use_ssl;
  document.getElementById('passive').checked = data.session.passive;
  await loadListing('.');
}

document.getElementById('loginBtn').addEventListener('click', async () => {
  const payload = {
    host: document.getElementById('host').value.trim(),
    port: Number(document.getElementById('port').value || '21'),
    username: document.getElementById('username').value.trim(),
    password: document.getElementById('password').value,
    use_ssl: document.getElementById('useSsl').checked,
    passive: document.getElementById('passive').checked,
  };
  const data = await api('/ftp/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  currentSessionId = data.session_id;
  currentRemoteCwd = data.cwd;
  await loadListing(data.cwd);
});

document.getElementById('restoreBtn').addEventListener('click', () => {
  restoreSession().catch((error) => writeApi({ ok: false, error: String(error) }));
});

document.getElementById('browseBtn').addEventListener('click', () => {
  loadListing(document.getElementById('browsePath').value.trim() || '.').catch((error) =>
    writeApi({ ok: false, error: String(error) })
  );
});

document.getElementById('uploadBtn').addEventListener('click', async () => {
  const input = document.getElementById('uploadFile');
  if (!input.files.length) return;
  const form = new FormData();
  if (currentSessionId) form.set('session_id', currentSessionId);
  form.set('remote_path', document.getElementById('remoteUploadPath').value.trim());
  form.set('file', input.files[0]);
  await api('/ftp/upload', { method: 'POST', body: form });
  input.value = '';
  await loadListing(currentRemoteCwd);
});

document.getElementById('archiveBtn').addEventListener('click', async () => {
  const payload = {
    session_id: currentSessionId,
    path: document.getElementById('archivePath').value.trim(),
    output_name: document.getElementById('archiveName').value.trim() || 'archive.tar',
  };
  const data = await api('/ftp/archive-download', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (data['download-url']) {
    window.open(data['download-url'], '_blank');
  }
});

restoreSession().catch(() => writeApi({ ok: true, note: 'No saved FTP session found yet.' }));

const SERVER = 'http://127.0.0.1:8765';
const $ = id => document.getElementById(id);

async function activeTab() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  return tab;
}

async function checkServer() {
  try {
    const r = await fetch(`${SERVER}/status`);
    const s = await r.json();
    const per = Object.entries(s.per_class).filter(([, n]) => n > 0).map(([k, n]) => `${k}: ${n}`).join('\n');
    $('server').textContent = `Server OK – ${s.total} images\n${per}`;
  } catch {
    $('server').textContent = 'Server NOT running.\nRun: python collector/collector_server.py';
  }
}

function showStatus(s) {
  if (!s) return;
  const extra = s.saved !== undefined ? `\nsaved ${s.saved} · skipped ${s.skipped}` : '';
  $('status').textContent = s.text + extra;
}

chrome.storage.local.get('status').then(({ status }) => showStatus(status));
chrome.storage.onChanged.addListener(ch => { if (ch.status) { showStatus(ch.status.newValue); checkServer(); } });

$('preview').onclick = async () => {
  const tab = await activeTab();
  const r = await chrome.runtime.sendMessage({ type: 'preview', tabId: tab.id });
  $('status').textContent = r && r.count !== undefined ? `Found ${r.count} elements:\n${[...new Set(r.classes)].join(', ')}` : `Error: ${r && r.error}`;
};
$('once').onclick = async () => {
  const tab = await activeTab();
  await chrome.runtime.sendMessage({ type: 'once', tabId: tab.id });
};
$('start').onclick = async () => {
  const tab = await activeTab();
  const opts = {
    count: parseInt($('count').value, 10) || 300,
    navigate: $('navigate').checked,
    sidebar: $('sidebar').checked,
    zoom: $('zoom').checked,
    resize: $('resize').checked,
  };
  await chrome.runtime.sendMessage({ type: 'start', tabId: tab.id, opts });
};
$('stop').onclick = () => chrome.runtime.sendMessage({ type: 'stop' });

checkServer();

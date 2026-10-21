// Kola collector — background service worker.
// Pairs DOM labels with a screenshot and sends them to the local Python server.
const SERVER = 'http://127.0.0.1:8765';

const SEARCHES = ['claude code', 'lofi music', 'python tutorial', 'gaming highlights', 'pasta recipe',
  'football highlights', 'ai agents', 'travel vlog', 'minecraft', 'guitar lesson', 'space documentary',
  'sri lanka travel', 'react tutorial', 'cricket', 'chess', 'nature 4k', 'podcast', 'news'];

let running = false;
const sleep = ms => new Promise(r => setTimeout(r, ms));
const pick = a => a[Math.floor(Math.random() * a.length)];
const randInt = (a, b) => Math.floor(a + Math.random() * (b - a));

function randomPage() {
  const q = encodeURIComponent(pick(SEARCHES));
  return pick([
    'https://www.youtube.com/',
    'https://www.youtube.com/',
    'https://www.youtube.com/',
    `https://www.youtube.com/results?search_query=${q}`,
    `https://www.youtube.com/results?search_query=${q}`,
    'https://www.youtube.com/feed/subscriptions',
  ]);
}

async function status(text, extra = {}) {
  await chrome.storage.local.set({ status: { text, time: Date.now(), running, ...extra } });
}

async function ensureContent(tabId) {
  try {
    await chrome.tabs.sendMessage(tabId, { type: 'ping' });
  } catch {
    await chrome.scripting.executeScript({ target: { tabId }, files: ['labeler.js'] });
    await sleep(300);
  }
}

function waitLoaded(tabId, timeout = 12000) {
  return new Promise(resolve => {
    const t = setTimeout(() => { chrome.tabs.onUpdated.removeListener(fn); resolve(); }, timeout);
    function fn(id, info) {
      if (id === tabId && info.status === 'complete') {
        clearTimeout(t); chrome.tabs.onUpdated.removeListener(fn); resolve();
      }
    }
    chrome.tabs.onUpdated.addListener(fn);
  });
}

// Boxes moved between the two label reads => page was animating; skip that frame.
function stable(a, b) {
  if (!a || !b || a.boxes.length !== b.boxes.length || a.vw !== b.vw || a.vh !== b.vh) return false;
  for (let i = 0; i < a.boxes.length; i++) {
    const p = a.boxes[i], q = b.boxes[i];
    if (p.cls !== q.cls) return false;
    if (Math.abs(p.x1 - q.x1) > 3 || Math.abs(p.y1 - q.y1) > 3 || Math.abs(p.x2 - q.x2) > 3 || Math.abs(p.y2 - q.y2) > 3) return false;
  }
  return true;
}

async function captureOnce(tabId) {
  const tab = await chrome.tabs.get(tabId);
  if (!tab.url || !tab.url.startsWith('https://www.youtube.com/')) throw new Error('Active tab is not YouTube');
  await ensureContent(tabId);
  const before = await chrome.tabs.sendMessage(tabId, { type: 'labels' });
  const image = await chrome.tabs.captureVisibleTab(tab.windowId, { format: 'jpeg', quality: 90 });
  const after = await chrome.tabs.sendMessage(tabId, { type: 'labels' });
  if (!stable(before, after)) return { saved: false, reason: 'page moving' };
  if (!after.boxes.length) return { saved: false, reason: 'no elements' };
  const res = await fetch(`${SERVER}/save`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ image, ...after }),
  });
  return await res.json();
}

async function autoRun(tabId, opts) {
  running = true;
  let saved = 0, skipped = 0;
  const tab = await chrome.tabs.get(tabId);
  const winId = tab.windowId;
  await status('Auto collection started', { saved, skipped });

  for (let i = 0; i < opts.count && running; i++) {
    try {
      if (opts.navigate && i > 0 && i % 12 === 0) {
        await chrome.tabs.update(tabId, { url: randomPage() });
        await waitLoaded(tabId);
        await sleep(3500);
        await ensureContent(tabId);
      }
      if (opts.zoom && Math.random() < 0.25) {
        await chrome.tabs.setZoom(tabId, pick([0.8, 0.9, 1, 1, 1, 1.1, 1.25]));
        await sleep(900);
      }
      if (opts.resize && Math.random() < 0.12) {
        await chrome.windows.update(winId, { state: 'normal', width: randInt(1050, 1920), height: randInt(700, 1080) });
        await sleep(1200);
      }
      if (opts.sidebar && Math.random() < 0.2) {
        await chrome.tabs.sendMessage(tabId, { type: 'toggleSidebar' });
        await sleep(1000);
      }
      await chrome.tabs.sendMessage(tabId, { type: 'scroll', y: Math.random() < 0.4 ? 0 : 'random' });
      await sleep(1600); // let thumbnails render

      const r = await captureOnce(tabId);
      if (r.saved) saved++; else skipped++;
      await status(`#${i + 1}/${opts.count}: ${r.saved ? `saved (${r.boxes} boxes)` : `skipped – ${r.reason}`}`, { saved, skipped, total: r.total });
    } catch (e) {
      skipped++;
      await status(`#${i + 1}: error – ${e.message}`, { saved, skipped });
      await sleep(1500);
    }
    await sleep(500); // captureVisibleTab is rate-limited
  }
  running = false;
  try { await chrome.tabs.setZoom(tabId, 1); } catch {}
  await status(`Finished. Saved ${saved}, skipped ${skipped}.`, { saved, skipped });
}

chrome.runtime.onMessage.addListener((msg, _sender, send) => {
  (async () => {
    try {
      if (msg.type === 'once') {
        const r = await captureOnce(msg.tabId);
        await status(r.saved ? `Saved (${r.boxes} boxes). Dataset: ${r.total}` : `Skipped – ${r.reason}`, { total: r.total });
        send(r);
      } else if (msg.type === 'start') {
        if (!running) autoRun(msg.tabId, msg.opts);
        send({ ok: true });
      } else if (msg.type === 'stop') {
        running = false;
        await status('Stopping…');
        send({ ok: true });
      } else if (msg.type === 'preview') {
        await ensureContent(msg.tabId);
        send(await chrome.tabs.sendMessage(msg.tabId, { type: 'preview' }));
      }
    } catch (e) {
      await status(`Error – ${e.message}`);
      send({ ok: false, error: e.message });
    }
  })();
  return true; // async response
});

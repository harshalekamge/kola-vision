// Kola labeler — runs inside YouTube pages.
// Finds UI elements in the live page (DOM), keeps only the ones a person can
// actually see, and returns their boxes in viewport CSS pixels. The background
// script pairs these boxes with a screenshot to make a YOLO training sample.
// The trained model never sees the DOM — only pixels. The DOM is just the labeler.
(() => {
  if (window.__kolaLabeler) return;
  window.__kolaLabeler = true;

  const SIDEBAR_SCOPE = 'ytd-guide-renderer, ytd-mini-guide-renderer';
  const SHORTS_SEL = 'ytm-shorts-lockup-view-model-v2, ytm-shorts-lockup-view-model, ytd-reel-item-renderer';
  const SHORTS_SHELF_SEL = 'ytd-rich-shelf-renderer[is-shorts], ytd-reel-shelf-renderer, grid-shelf-view-model';
  const AD_SEL = 'ytd-ad-slot-renderer, ytd-in-feed-ad-layout-renderer, ytd-promoted-sparkles-web-renderer, ytd-display-ad-renderer, ytd-promoted-video-renderer';
  const VIDEO_SEL = 'ytd-rich-item-renderer, ytd-video-renderer, yt-lockup-view-model, ytd-grid-video-renderer';
  const CHIP_SEL = 'yt-chip-cloud-chip-renderer';
  const MIN_VISIBLE = 0.6; // keep an element only if >= 60% of it is inside the viewport

  // ---------- helpers ----------
  function sidebarClass(href) {
    if (!href) return null;
    let u;
    try { u = new URL(href, location.origin); } catch { return null; }
    const p = u.pathname;
    if (p === '/') return 'home';
    if (p.startsWith('/shorts')) return 'shorts';
    if (p.startsWith('/feed/subscriptions')) return 'subscriptions';
    if (p.startsWith('/feed/history')) return 'history';
    if (p === '/playlist' && u.searchParams.get('list') === 'WL') return 'watch_later';
    return null;
  }

  // true if node t is el or inside el (crosses shadow roots)
  function within(el, t) {
    while (t) {
      if (t === el) return true;
      t = t.parentNode || t.host || null;
    }
    return false;
  }

  function visibleBox(el) {
    const r = el.getBoundingClientRect();
    if (r.width < 4 || r.height < 4) return null;
    const vw = window.innerWidth, vh = window.innerHeight;
    const x1 = Math.max(0, r.left), y1 = Math.max(0, r.top);
    const x2 = Math.min(vw, r.right), y2 = Math.min(vh, r.bottom);
    if (x2 - x1 < 4 || y2 - y1 < 4) return null;
    if (((x2 - x1) * (y2 - y1)) / (r.width * r.height) < MIN_VISIBLE) return null;
    const cs = getComputedStyle(el);
    if (cs.visibility === 'hidden' || cs.display === 'none' || parseFloat(cs.opacity) < 0.1) return null;
    // Occlusion test: at least 2 of 3 probe points must hit this element.
    const cy = (y1 + y2) / 2;
    const probes = [[(x1 + x2) / 2, cy], [x1 + (x2 - x1) * 0.25, cy], [x1 + (x2 - x1) * 0.75, cy]];
    let hits = 0;
    for (const [px, py] of probes) {
      const t = document.elementFromPoint(px, py);
      if (t && within(el, t)) hits++;
    }
    if (hits < 2) return null;
    return { x1, y1, x2, y2 };
  }

  const area = b => (b.x2 - b.x1) * (b.y2 - b.y1);
  const containsBox = (a, b, tol = 3) =>
    b.x1 >= a.x1 - tol && b.y1 >= a.y1 - tol && b.x2 <= a.x2 + tol && b.y2 <= a.y2 + tol;

  // ---------- collection ----------
  function collect() {
    const out = [];
    const seen = new Set();
    const add = (cls, el) => {
      if (!el || seen.has(el)) return;
      seen.add(el);
      const b = visibleBox(el);
      if (b) out.push({ cls, ...b });
    };

    // Sidebar destinations (full guide and mini guide)
    document.querySelectorAll(SIDEBAR_SCOPE).forEach(scope => {
      scope.querySelectorAll('a[href]').forEach(a => {
        const c = sidebarClass(a.getAttribute('href'));
        if (!c) return;
        add(c, a.closest('ytd-guide-entry-renderer, ytd-mini-guide-entry-renderer') || a);
      });
    });

    // Hamburger menu
    const mb = document.querySelector('ytd-masthead #guide-button, #masthead #guide-button');
    if (mb) add('menu_button', mb.querySelector('button') || mb);

    // Search box + search button
    const input = document.querySelector('input[name="search_query"]');
    if (input) {
      const sb = input.closest('yt-searchbox, ytd-searchbox');
      const box = (sb && sb.querySelector('.ytSearchboxComponentInputBox, #container')) || input.closest('form') || input;
      add('search_box', box);
      let btn = sb && sb.querySelector('button.ytSearchboxComponentSearchButton, #search-icon-legacy');
      if (!btn && sb) {
        const bs = [...sb.querySelectorAll('button')].filter(b => !box.contains(b));
        bs.sort((a, b) => b.getBoundingClientRect().right - a.getBoundingClientRect().right);
        btn = bs[0];
      }
      if (btn) add('search_button', btn);
    }

    // Topic chips
    document.querySelectorAll(CHIP_SEL).forEach(el => add('chip', el));

    // Feed cards
    document.querySelectorAll(AD_SEL).forEach(el => add('sponsored_card', el));
    document.querySelectorAll(SHORTS_SEL).forEach(el => add('short_card', el));
    document.querySelectorAll(VIDEO_SEL).forEach(el => {
      if (el.closest(AD_SEL) || el.querySelector(AD_SEL)) return;
      if (el.querySelector(SHORTS_SEL) || el.closest(SHORTS_SHELF_SEL)) return;
      if (el.closest(SIDEBAR_SCOPE)) return;
      add('video_card', el);
    });

    // Remove same-class boxes nested inside another (e.g. lockup inside rich-item): keep the outer one.
    const keep = out.filter((a, i) => !out.some((b, j) =>
      j !== i && b.cls === a.cls && containsBox(b, a) && (area(b) > area(a) || (area(b) === area(a) && j < i))));

    return {
      vw: window.innerWidth,
      vh: window.innerHeight,
      dpr: window.devicePixelRatio,
      url: location.href,
      theme: document.documentElement.hasAttribute('dark') ? 'dark' : 'light',
      boxes: keep,
    };
  }

  // ---------- live preview (only when you press "Preview labels"; never in screenshots) ----------
  const COLORS = ['#e6194b', '#3cb44b', '#4363d8', '#f58231', '#911eb4', '#46f0f0', '#f032e6', '#bcf60c', '#fabebe', '#008080', '#9a6324', '#800000'];
  function preview(ms = 4000) {
    const data = collect();
    const layer = document.createElement('div');
    layer.style.cssText = 'position:fixed;inset:0;pointer-events:none;z-index:2147483647';
    const names = [...new Set(data.boxes.map(b => b.cls))];
    data.boxes.forEach(b => {
      const c = COLORS[names.indexOf(b.cls) % COLORS.length];
      const d = document.createElement('div');
      d.style.cssText = `position:absolute;left:${b.x1}px;top:${b.y1}px;width:${b.x2 - b.x1}px;height:${b.y2 - b.y1}px;border:2px solid ${c};box-sizing:border-box`;
      const t = document.createElement('span');
      t.textContent = b.cls;
      t.style.cssText = `position:absolute;left:0;top:-16px;font:11px monospace;background:${c};color:#fff;padding:0 3px`;
      d.appendChild(t);
      layer.appendChild(d);
    });
    document.body.appendChild(layer);
    setTimeout(() => layer.remove(), ms);
    return data;
  }

  // ---------- messages from the extension ----------
  chrome.runtime.onMessage.addListener((msg, _sender, send) => {
    switch (msg.type) {
      case 'ping': send({ ok: true }); break;
      case 'labels': send(collect()); break;
      case 'preview': { const d = preview(); send({ count: d.boxes.length, classes: d.boxes.map(b => b.cls) }); break; }
      case 'scroll': {
        let y = msg.y;
        if (y === 'random') {
          const max = Math.max(0, document.documentElement.scrollHeight - window.innerHeight);
          y = Math.random() * Math.min(max, 4000);
        }
        window.scrollTo(0, y);
        send({ ok: true });
        break;
      }
      case 'toggleSidebar': {
        const b = document.querySelector('ytd-masthead #guide-button button, #masthead #guide-button button, #guide-button');
        if (b) b.click();
        send({ ok: !!b });
        break;
      }
      default: send({ ok: false });
    }
    return false;
  });
})();

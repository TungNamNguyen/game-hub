/* Tiện ích DOM dùng chung.
 *
 * Quy tắc an toàn của cả frontend: KHÔNG ghép chuỗi người dùng vào innerHTML.
 * Dùng h() để dựng element và .textContent để đặt chữ. Chỗ nào buộc phải dùng
 * innerHTML thì chỉ được chứa markup do chính ta viết, và mọi giá trị từ người
 * dùng phải đi qua esc().
 */

import { locale, t } from './i18n.js';

export function h(tag, props = {}, ...children) {
  const el = document.createElement(tag);
  for (const [key, value] of Object.entries(props || {})) {
    if (value === null || value === undefined || value === false) continue;
    if (key === 'class') el.className = value;
    else if (key === 'style' && typeof value === 'object') Object.assign(el.style, value);
    else if (key === 'dataset') Object.assign(el.dataset, value);
    else if (key.startsWith('on') && typeof value === 'function') {
      el.addEventListener(key.slice(2).toLowerCase(), value);
    } else if (key === 'html') el.innerHTML = value;   // chỉ cho markup của ta
    else if (key in el && key !== 'list') el[key] = value;
    else el.setAttribute(key, value);
  }
  add(el, children);
  return el;
}

function add(parent, children) {
  for (const child of children) {
    if (child === null || child === undefined || child === false) continue;
    if (Array.isArray(child)) add(parent, child);
    else if (child instanceof Node) parent.appendChild(child);
    else parent.appendChild(document.createTextNode(String(child)));
  }
}

export function esc(text) {
  return String(text ?? '').replace(/[&<>"']/g, (ch) =>
    ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch]));
}

export function clear(el) {
  while (el.firstChild) el.removeChild(el.firstChild);
  return el;
}

function flattenChildren(children, out = []) {
  for (const child of children) {
    if (child === null || child === undefined || child === false) continue;
    if (Array.isArray(child)) flattenChildren(child, out);
    else if (child instanceof Node) out.push(child);
    else out.push(document.createTextNode(String(child)));
  }
  return out;
}

export function mount(parent, ...children) {
  const nextNodes = flattenChildren(children);
  const keepSet = new Set(nextNodes);
  for (let c = parent.firstChild; c; ) {
    const next = c.nextSibling;
    if (!keepSet.has(c)) parent.removeChild(c);
    c = next;
  }
  let cursor = parent.firstChild;
  for (const node of nextNodes) {
    if (node === cursor) {
      cursor = cursor.nextSibling;
    } else {
      parent.insertBefore(node, cursor);
    }
  }
  return parent;
}

/** Icon SVG nội tuyến, không phụ thuộc CDN nào. */
const ICONS = {
  home: '<path d="M3 10.5 12 3l9 7.5V20a1 1 0 0 1-1 1h-5v-6H10v6H5a1 1 0 0 1-1-1Z"/>',
  chat: '<path d="M21 11.5a8.4 8.4 0 0 1-8.5 8.5 9 9 0 0 1-3.8-.8L3 21l1.9-4.9A8.3 8.3 0 0 1 4 11.5 8.4 8.4 0 0 1 12.5 3 8.4 8.4 0 0 1 21 11.5Z"/>',
  caro: '<path d="M3 3h18v18H3zM9 3v18M15 3v18M3 9h18M3 15h18"/>',
  cards: '<rect x="3" y="6" width="11" height="15" rx="2"/>'
       + '<path d="M8 6V4a1 1 0 0 1 1.3-1l9 2.6A1 1 0 0 1 19 7l-2 8"/>'
       + '<path d="M8.5 13.5 11 11l2.5 2.5"/>',
  skull: '<path d="M12 3a7 7 0 0 0-7 7v3l-1 3 3 1v3h10v-3l3-1-1-3v-3a7 7 0 0 0-7-7Z"/>'
       + '<path d="M9.5 11h.01M14.5 11h.01M12 14l-1 3h2l-1-3"/>',
  chess: '<path d="M6 21h12M9 21c0-3.5 1.8-4.5 1.8-6.5H8.5L9.6 10h4.8l1.1 4.5h-2.3c0 2 1.8 3 1.8 6.5"/><path d="M12 3.5v4M10 5.5h4"/>',
  face: '<circle cx="12" cy="12" r="9"/><path d="M8.5 14.5s1.3 1.8 3.5 1.8 3.5-1.8 3.5-1.8"/><path d="M9 10h.01M15 10h.01"/><path d="M4 9c2.5-4 13.5-4 16 0"/>',
  xiangqi: '<circle cx="12" cy="12" r="9"/><path d="M8 9.2h8M12 9.2v6M9.2 15.2h5.6"/>',
  bell: '<path d="M18 16.5V11a6 6 0 0 0-12 0v5.5L4 19.5h16Z"/><path d="M10 22a2.2 2.2 0 0 0 4 0"/>',
  bellOff: '<path d="M18 16.5V11a6 6 0 0 0-8.5-5.4M6 9.5V11v5.5L4 19.5h13"/><path d="M3 3l18 18"/>',
  ship: '<path d="M3 17h18l-2 4H5ZM5 17V9l7-5 7 5v8M9 9h6M12 4v13"/>',
  send: '<path d="m22 2-7 20-4-9-9-4Z"/>',
  image: '<rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8.5" cy="8.5" r="1.5"/><path d="m21 15-5-5L5 21"/>',
  smile: '<circle cx="12" cy="12" r="9"/><path d="M8 14s1.5 2 4 2 4-2 4-2"/><path d="M9 9h.01M15 9h.01"/>',
  reply: '<path d="M9 17 4 12l5-5"/><path d="M20 18v-2a4 4 0 0 0-4-4H4"/>',
  trash: '<path d="M3 6h18M8 6V4h8v2M19 6l-1 14H6L5 6"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  close: '<path d="M18 6 6 18M6 6l12 12"/>',
  copy: '<rect x="9" y="9" width="12" height="12" rx="2"/><path d="M5 15V5a2 2 0 0 1 2-2h8"/>',
  play: '<path d="m6 3 14 9-14 9Z"/>',
  refresh: '<path d="M21 12a9 9 0 1 1-3-6.7"/><path d="M21 3v6h-6"/>',
  target: '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="4"/><path d="M12 1v4M12 19v4M1 12h4M19 12h4"/>',
  flag: '<path d="M4 21V4h11l-1 3 6 1v9H8l1-3H4"/>',
  users: '<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.9"/>',
  check: '<path d="M20 6 9 17l-5-5"/>',
  dice: '<rect x="3" y="3" width="18" height="18" rx="3"/><path d="M8 8h.01M16 16h.01M12 12h.01"/>',
  settings: '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.6 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.6a1.65 1.65 0 0 0 1-1.51V3a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 1 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1Z"/>',
  upload: '<path d="M12 21V9M7 13l5-5 5 5M4 21h16"/>',
  book: '<path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z"/><path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z"/>',
  globe: '<circle cx="12" cy="12" r="10"/><path d="M12 2a14.5 14.5 0 0 0 0 20 14.5 14.5 0 0 0 0-20"/><path d="M2 12h20"/>',
  gamepad: '<line x1="6" y1="11" x2="10" y2="11"/><line x1="8" y1="9" x2="8" y2="13"/><line x1="15" y1="12" x2="15.01" y2="12"/><line x1="18" y1="10" x2="18.01" y2="10"/><path d="M17.32 5H6.68a4 4 0 0 0-3.978 3.59c-.006.052-.01.101-.017.152C2.604 9.416 2 14.456 2 16a3 3 0 0 0 3 3c1 0 1.5-.5 2-1l1.414-1.414A2 2 0 0 1 9.828 16h4.344a2 2 0 0 1 1.414.586L17 18c.5.5 1 1 2 1a3 3 0 0 0 3-3c0-1.545-.604-6.584-.685-7.258-.007-.05-.011-.1-.017-.151A4 4 0 0 0 17.32 5Z"/>',
  palette: '<circle cx="13.5" cy="6.5" r=".5" fill="currentColor"/><circle cx="17.5" cy="10.5" r=".5" fill="currentColor"/><circle cx="8.5" cy="7.5" r=".5" fill="currentColor"/><circle cx="6.5" cy="12.5" r=".5" fill="currentColor"/><path d="M12 2C6.5 2 2 6.5 2 12s4.5 10 10 10c.926 0 1.648-.746 1.648-1.688 0-.437-.18-.835-.437-1.125-.29-.289-.438-.652-.438-1.125a1.64 1.64 0 0 1 1.668-1.668h1.996c3.051 0 5.555-2.503 5.555-5.554C21.965 6.012 17.461 2 12 2Z"/>',
  sun: '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M6.34 17.66l-1.41 1.41M19.07 4.93l-1.41 1.41"/>',
  moon: '<path d="M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9Z"/>',
  monitor: '<rect x="2" y="3" width="20" height="14" rx="2"/><line x1="8" y1="21" x2="16" y2="21"/><line x1="12" y1="17" x2="12" y2="21"/>',
  volumeOn: '<polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"/><path d="M15.54 8.46a5 5 0 0 1 0 7.07"/><path d="M19.07 4.93a10 10 0 0 1 0 14.14"/>',
  volumeOff: '<polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"/><line x1="22" y1="9" x2="16" y2="15"/><line x1="16" y1="9" x2="22" y2="15"/>',
  arrowRight: '<path d="M5 12h14"/><path d="m12 5 7 7-7 7"/>',
  arrowLeft: '<path d="M19 12H5"/><path d="m12 19-7-7 7-7"/>',
  paperclip: '<path d="m21.44 11.05-9.19 9.19a6 6 0 0 1-8.49-8.49l8.57-8.57A4 4 0 1 1 18 8.84l-8.59 8.57a2 2 0 0 1-2.83-2.83l8.49-8.48"/>',
  file: '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8Z"/><path d="M14 2v6h6"/>',
  download: '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/>',
  sparkles: '<path d="m12 3-1.912 5.813a2 2 0 0 1-1.275 1.275L3 12l5.813 1.912a2 2 0 0 1 1.275 1.275L12 21l1.912-5.813a2 2 0 0 1 1.275-1.275L21 12l-5.813-1.912a2 2 0 0 1-1.275-1.275L12 3Z"/>',
  chevronDown: '<polyline points="6 9 12 15 18 9"/>',
  horse: '<path d="M18 20H6v-2c0-1.2 1.2-2.2 2.5-2.8l1.2-3.2c-1.1.3-2.5.3-3.5-.4-.7-.5-.9-1.4-.4-2.2L8.5 5.5 7.8 3.2c1.4.2 2.6.8 3.5 1.8.8-.3 1.7-.4 2.6-.3 2.5.3 4.3 2.5 4.1 5.2-.1 1.8-.8 3.6-1.5 5.2l1.2 2.5c.3.7.3 1.4.3 2.4Z"/>',
};

export function icon(name, size = 18) {
  const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  svg.setAttribute('viewBox', '0 0 24 24');
  svg.setAttribute('width', size);
  svg.setAttribute('height', size);
  svg.setAttribute('fill', 'none');
  svg.setAttribute('stroke', 'currentColor');
  svg.setAttribute('stroke-width', '1.9');
  svg.setAttribute('stroke-linecap', 'round');
  svg.setAttribute('stroke-linejoin', 'round');
  svg.setAttribute('aria-hidden', 'true');
  svg.innerHTML = ICONS[name] || ICONS.home;
  return svg;
}

/** Chữ viết tắt cho avatar: lấy đầu của hai từ đầu tiên. */
export function initials(name) {
  const parts = String(name || '?').trim().split(/\s+/).filter(Boolean);
  if (!parts.length) return '?';
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}

function botAvatarNode(user, size = '') {
  const rawAccent = String(user?.color || '#38bdf8');
  const accent = /^[#a-zA-Z0-9(),.%\s-]+$/.test(rawAccent) ? rawAccent : '#38bdf8';
  const wrap = h('div', {
    class: 'avatar avatar-bot' + (size ? ' ' + size : ''),
    title: user?.name || 'Bot',
  });
  wrap.innerHTML = `<svg viewBox="0 0 40 40" width="100%" height="100%" aria-hidden="true">`
    + `<line x1="20" y1="6" x2="20" y2="11" stroke="#94a3b8" stroke-width="2" stroke-linecap="round"/>`
    + `<circle cx="20" cy="5.5" r="2.4" fill="${accent}"/>`
    + `<rect x="6" y="18" width="4" height="8" rx="1.8" fill="#64748b"/>`
    + `<rect x="30" y="18" width="4" height="8" rx="1.8" fill="#64748b"/>`
    + `<rect x="9" y="11" width="22" height="21" rx="6" fill="#cbd5e1"/>`
    + `<rect x="12" y="15" width="16" height="9" rx="3.2" fill="#0f172a"/>`
    + `<circle cx="16.5" cy="19.5" r="2.1" fill="${accent}"/>`
    + `<circle cx="23.5" cy="19.5" r="2.1" fill="${accent}"/>`
    + `<rect x="14.5" y="26.5" width="11" height="2.6" rx="1.3" fill="#475569"/>`
    + `<line x1="17.5" y1="26.5" x2="17.5" y2="29.1" stroke="#cbd5e1" stroke-width="1"/>`
    + `<line x1="20" y1="26.5" x2="20" y2="29.1" stroke="#cbd5e1" stroke-width="1"/>`
    + `<line x1="22.5" y1="26.5" x2="22.5" y2="29.1" stroke="#cbd5e1" stroke-width="1"/>`
    + `</svg>`;
  return wrap;
}

export function avatar(user, size = '') {
  const isBot = Boolean(user?.bot || String(user?.uid || '').startsWith('__bot__'));
  if (isBot) {
    return botAvatarNode(user, size);
  }
  if (user?.avatar) {
    return h('img', {
      class: 'avatar' + (size ? ' ' + size : ''),
      src: user.avatar,
      alt: '',
      title: user?.name || '',
    });
  }
  return h('div', {
    class: 'avatar' + (size ? ' ' + size : ''),
    style: { background: user?.color || '#6366f1' },
    title: user?.name || '',
  }, initials(user?.name));
}

/* ------------------------------------------------------------- thời gian -- */
export function timeOf(ts) {
  return new Date(ts * 1000).toLocaleTimeString(locale(),
    { hour: '2-digit', minute: '2-digit' });
}

export function dayOf(ts) {
  const date = new Date(ts * 1000);
  const today = new Date();
  const same = date.toDateString() === today.toDateString();
  if (same) return t('notify.today');
  const yesterday = new Date(today.getTime() - 86400000);
  if (date.toDateString() === yesterday.toDateString()) return t('notify.yesterday');
  return date.toLocaleDateString(locale(), { day: '2-digit', month: '2-digit', year: 'numeric' });
}

export function agoOf(ts) {
  const seconds = Math.max(0, Date.now() / 1000 - ts);
  if (seconds < 60) return t('notify.justNow');
  if (seconds < 3600) return t('notify.minAgo', { n: Math.floor(seconds / 60) });
  if (seconds < 86400) return t('notify.hourAgo', { n: Math.floor(seconds / 3600) });
  return t('notify.dayAgo', { n: Math.floor(seconds / 86400) });
}

export function numberOf(value) {
  return Number(value || 0).toLocaleString(locale());
}

/* ------------------------------------------------------------------ HTTP -- */
export async function api(path, options) {
  const res = await fetch(path, options);
  if (!res.ok) {
    let detail = t('notify.errStatus', { status: res.status });
    try {
      const body = await res.json();
      detail = body.detail || detail;
    } catch { /* body không phải JSON */ }
    throw new Error(detail);
  }
  return res.json();
}

export function postJSON(path, body, extraHeaders = {}) {
  return api(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...extraHeaders },
    body: JSON.stringify(body),
  });
}

/** Copy chuỗi. navigator.clipboard không tồn tại trên http://<ip-LAN> vì đó
 *  không phải secure context, nên phải có đường lui. */
export async function copyText(text) {
  try {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(text);
      return true;
    }
  } catch { /* rơi xuống cách dưới */ }
  const area = h('textarea', { value: text, style: { position: 'fixed', opacity: '0' } });
  document.body.appendChild(area);
  area.select();
  let ok = false;
  try { ok = document.execCommand('copy'); } catch { ok = false; }
  area.remove();
  return ok;
}

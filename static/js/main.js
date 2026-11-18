/* Vỏ ứng dụng: danh tính, router, sidebar, presence.
 *
 * Router dùng hash (#/caro/ABCD) để link mời chạy được mà không cần server
 * rewrite URL. Mỗi view là một module export { mount(root, ctx, params) } và
 * trả về hàm dọn dẹp; vỏ luôn gọi hàm đó trước khi đổi sang view khác, nhờ vậy
 * không có listener hay timer nào sót lại.
 */

import './themes.js';   // áp data-theme đã lưu lên <html> càng sớm càng tốt
import { api, avatar, clear, h, icon, mount } from './dom.js';
import { appDesc, appName as appTitle, onLangChange, t, toggleLang } from './i18n.js';
import { Net } from './net.js';
import { inviteCard, isMuted, notify, pageVisible, setTitleBadge, shouldInvite } from './notify.js';
import { cycleTheme, getThemeMeta, onThemeChange } from './themes.js';
import { onSoundChange, openSettings, openThemePopover, prompt, resizeImageFile, sfx,
         soundEnabled, toast, toggleSound } from './ui.js';

import homeView from './views/home.js';
import chatView from './views/chat.js';
import caroView from './views/caro.js';
import chessView from './views/chess.js';
import xiangqiView from './views/xiangqi.js';
import shipView from './views/ship.js';
import bluffView from './views/bluff.js';
import pokerView from './views/poker.js';
import geoView from './views/geo.js';
import flagsView from './views/flags.js';
import facesView from './views/faces.js';

const VIEWS = {
  home: homeView, chat: chatView, caro: caroView, chess: chessView,
  xiangqi: xiangqiView, ship: shipView, bluff: bluffView, poker: pokerView,
  geo: geoView, flags: flagsView, faces: facesView,
};
const NAV_ICON = {
  home: 'home', chat: 'chat', caro: 'caro', chess: 'chess',
  xiangqi: 'xiangqi', ship: 'ship', bluff: 'cards', poker: 'cards',
  geo: 'globe', flags: 'flag', faces: 'face',
};

const el = (id) => document.getElementById(id);

/* ----------------------------------------------------------- danh tính ---- */
/** UUID dự phòng khi crypto.randomUUID không có (hub chạy qua http://<ip-LAN>
 *  không phải secure context, nên API này bị trình duyệt tắt). Chỉ dùng
 *  [A-Za-z0-9-], không có dấu chấm — khớp với UID_RE phía server (avatar.py),
 *  vì uid còn được dùng làm tên file trên đĩa. */
function fallbackUuid() {
  const hex = () => Math.floor(Math.random() * 16).toString(16);
  const block = (n) => Array.from({ length: n }, hex).join('');
  return `${block(8)}-${block(4)}-${block(4)}-${block(4)}-${block(12)}`;
}

// Phải khớp UID_RE ở avatar.py: uid được dùng trực tiếp làm tên file trên đĩa.
const UID_RE = /^[A-Za-z0-9_-]{1,64}$/;

function loadUid() {
  let uid = localStorage.getItem('hub.uid');
  // uid cũ có thể chứa dấu chấm (sinh ra từ Math.random() trước khi hub.js
  // được sửa) — những uid đó không đổi được avatar vì server từ chối làm tên
  // file. Phát hiện và sinh lại uid hợp lệ, không cần người dùng tự xoá cache.
  if (!uid || !UID_RE.test(uid)) {
    uid = (crypto.randomUUID ? crypto.randomUUID() : fallbackUuid()).slice(0, 36);
    localStorage.setItem('hub.uid', uid);
  }
  return uid;
}

function loadToken() {
  let token = localStorage.getItem('hub.token');
  if (!token || token.length < 16) {
    token = (crypto.randomUUID ? crypto.randomUUID().replace(/-/g, '') : fallbackUuid().replace(/-/g, ''))
          + (crypto.randomUUID ? crypto.randomUUID().replace(/-/g, '').slice(0, 16) : fallbackUuid().replace(/-/g, '').slice(0, 16));
    localStorage.setItem('hub.token', token);
  }
  return token;
}

const me = {
  uid: loadUid(),
  token: loadToken(),
  name: localStorage.getItem('hub.name') || '',
  color: '#6366f1',
  avatar: null,
};

const net = new Net();

const ctx = {
  net,
  me,
  toast,
  apps: [],
  reactions: [],
  presence: [],
  navigate,
  setTopbar,
  chatChannels: [],
  // Kênh chat đang mở trên máy này ('' nếu không ở view chat). View chat tự
  // cập nhật; vỏ dùng nó để biết tin nhắn nào KHÔNG cần thông báo, vì người
  // dùng đang trực tiếp nhìn thấy nó rồi.
  chatActive: '',
  // View chat gọi sau khi tắt/bật thông báo một kênh, để huy hiệu sidebar và
  // tiêu đề tab tính lại ngay mà không cần chờ gói 'channels' kế tiếp.
  refreshBadges: () => refreshUnreadBadges(),
  // Tab Tạo avatar gọi để đặt ảnh đại diện. Đi qua đúng hàm mà modal Cài đặt
  // dùng, nên avatar mới cũng được phát cho mọi người như khi tự chọn file.
  setAvatar: (file) => uploadAvatar(file),
  // uid -> {name, color, avatar} MỚI NHẤT của mọi người đã từng xuất hiện
  // trong hub, kể cả người hiện không online. Dùng để chat hiển thị tên/màu/
  // avatar hiện tại trên toàn bộ lịch sử, thay vì đóng băng theo lúc gửi tin.
  directory: {},
  roomCounts: {},
  openThemePopover: (anchor) => openThemePopover(anchor),
  openProfileSettings: () => openSettingsModal(),
  syncRoomCounts: (roomsMap) => applyRoomCounts(roomsMap),
};

/* -------------------------------------------------------------- router ---- */
let current = { id: null, cleanup: null };

function parseHash() {
  const raw = (location.hash || '').replace(/^#\/?/, '');
  const [id, ...rest] = raw.split('/').filter(Boolean);
  return { id: VIEWS[id] ? id : 'home', param: rest.join('/') || '' };
}

function navigate(path) {
  const next = path.startsWith('#') ? path : `#/${path}`;
  if (location.hash === next) render();
  else location.hash = next;
}

function setTopbar(...children) {
  mount(el('topbarSlot'), ...children);
}

async function render() {
  const { id, param } = parseHash();

  if (current.cleanup) {
    try { current.cleanup(); } catch (err) { console.error('cleanup lỗi', err); }
  }
  current = { id, cleanup: null };

  document.body.classList.remove('nav-open');
  highlightNav(id);
  setTopbar();

  const root = el('view');
  root.className = 'view';
  clear(root);

  net.send('hub', 'app', { app: id });

  try {
    current.cleanup = (await VIEWS[id].mount(root, ctx, param)) || null;
  } catch (err) {
    console.error('mount lỗi', id, err);
    mount(root, h('div', { class: 'banner danger' },
      t('shell.openAppFailed', { err: err.message || err })));
  }
}

/* ------------------------------------------------------------- sidebar ---- */
const NAV_GROUPS = [
  { key: 'nav.groupExplore', ids: new Set(['home', 'chat']) },
  { key: 'nav.groupCustom', ids: new Set(['faces']) },
];

function navGroupFor(appId) {
  for (const g of NAV_GROUPS) {
    if (g.ids.has(appId)) return g.key;
  }
  return 'nav.groupGames';
}

function buildNav() {
  const nav = clear(el('nav'));
  const ordered = [
    ...ctx.apps.filter((a) => navGroupFor(a.id) === 'nav.groupExplore'),
    ...ctx.apps.filter((a) => navGroupFor(a.id) === 'nav.groupGames'),
    ...ctx.apps.filter((a) => navGroupFor(a.id) === 'nav.groupCustom'),
  ];
  let lastGroup = '';
  for (const app of ordered) {
    const group = navGroupFor(app.id);
    if (group !== lastGroup) {
      nav.appendChild(h('div', { class: 'nav-group-label' }, t(group)));
      lastGroup = group;
    }
    const title = appTitle(app.id, app.name);
    const desc = appDesc(app.id, app.desc || '');
    const isChat = app.id === 'chat';
    const badge = h('span', {
      class: 'nav-badge hidden' + (isChat ? '' : ' room-pill'),
      dataset: { badge: app.id },
    }, '0');
    nav.appendChild(h('button', {
      class: 'nav-item',
      dataset: { nav: app.id },
      title: desc || title,
      onclick: () => navigate(app.id),
    }, icon(NAV_ICON[app.id] || 'home'), h('span', { class: 'nav-label' }, title), badge));
  }
  highlightNav(parseHash().id);
  refreshUnreadBadges();
  applyRoomCounts(ctx.roomCounts);
}

function applyRoomCounts(roomsMap = {}) {
  ctx.roomCounts = roomsMap || {};
  for (const app of ctx.apps) {
    if (app.id === 'home' || app.id === 'chat' || app.id === 'faces') continue;
    const count = Array.isArray(ctx.roomCounts[app.id]) ? ctx.roomCounts[app.id].length : 0;
    const badge = document.querySelector(`[data-badge="${app.id}"]`);
    if (!badge) continue;
    badge.textContent = count > 99 ? '99+' : String(count);
    badge.title = count ? t('nav.roomsLive', { count }) : '';
    badge.classList.toggle('hidden', !count);
  }
}

async function pollRoomCounts() {
  try {
    const data = await api('/api/rooms');
    applyRoomCounts(data.rooms || {});
  } catch { /* bỏ qua lỗi mạng tạm thời */ }
}

function highlightNav(id) {
  for (const item of document.querySelectorAll('[data-nav]')) {
    item.classList.toggle('active', item.dataset.nav === id);
  }
}

export function setNavBadge(appId, count) {
  const badge = document.querySelector(`[data-badge="${appId}"]`);
  if (!badge) return;
  badge.textContent = count > 99 ? '99+' : String(count);
  badge.classList.toggle('hidden', !count);
}

function renderMe() {
  // meAvatar có thể cần chuyển từ <div> (initials) sang <img> (ảnh thật) hoặc
  // ngược lại, nên vẽ lại toàn bộ node thay vì chỉnh thuộc tính tại chỗ.
  const node = el('meAvatar');
  const fresh = avatar(me, node.classList.contains('lg') ? 'lg' : '');
  fresh.id = 'meAvatar';
  node.replaceWith(fresh);
  el('meName').textContent = me.name || t('shell.unnamed');
}

function renderPresence(users) {
  ctx.presence = users;
  const countNode = el('onlineCount');
  if (countNode) countNode.textContent = String(users.length);
  const list = clear(el('presenceList'));
  const getAppName = (id) => {
    const found = ctx.apps.find((a) => a.id === id);
    return found ? appTitle(id, found.name) : '';
  };
  for (const user of users) {
    const where = user.uid === me.uid ? t('shell.youShort') : getAppName(user.app);
    list.appendChild(h('div', { class: 'presence-row' },
      avatar(user, 'sm'),
      h('span', { class: 'grow nowrap' }, user.name),
      where ? h('span', { class: 'tiny muted nowrap' }, where) : null));
  }
  if (!users.length) list.appendChild(h('div', { class: 'tiny muted' }, t('shell.noOneOnline')));
}

// Trước khi thử kết nối lần đầu thì chưa có gì "mất", đừng làm người dùng lo.
let connectAttempted = false;
let lastConnOk = false;
let lastConnMode = 'ws';

function setConn(ok, mode = lastConnMode) {
  lastConnOk = ok;
  if (mode) lastConnMode = mode;
  const label = el('connLabel');
  if (!label) return;
  const textNode = label.querySelector('.conn-text') || label;
  label.classList.toggle('ok', Boolean(ok));
  label.classList.toggle('warn', !ok && connectAttempted);
  if (ok) {
    const modeTag = lastConnMode === 'poll' ? ' (HTTP)' : lastConnMode === 'sse' ? ' (SSE)' : '';
    textNode.textContent = t('shell.connected') + modeTag;
    label.title = lastConnMode === 'poll'
      ? t('shell.connTitlePoll')
      : lastConnMode === 'sse'
        ? t('shell.connTitleSse')
        : t('shell.connTitleWs');
    label.style.color = 'var(--text-muted)';
  } else {
    textNode.textContent = connectAttempted ? t('shell.reconnecting') : t('shell.connecting');
    label.title = '';
    label.style.color = connectAttempted ? 'var(--warn)' : 'var(--text-muted)';
  }
}

function renderTopbarActions() {
  const host = el('topbarActions');
  if (!host) return;
  const on = soundEnabled();
  const themeMeta = getThemeMeta();

  const soundBtn = h('button', {
    id: 'soundBtn',
    type: 'button',
    class: 'topbar-btn icon-only' + (on ? '' : ' muted-sound'),
    title: on ? t('shell.soundOn') : t('shell.soundOff'),
    'aria-label': on ? t('shell.soundOn') : t('shell.soundOff'),
    'aria-pressed': String(on),
    onclick: () => {
      const next = toggleSound();
      if (next) sfx.message();
      toast(next ? t('shell.soundUnmutedToast') : t('shell.soundMutedToast'));
    },
  }, icon(on ? 'volumeOn' : 'volumeOff', 16));

  const themeBtn = h('button', {
    id: 'themeBtn',
    type: 'button',
    class: 'topbar-btn theme-trigger',
    title: t('theme.quickTitle'),
    'aria-label': t('theme.quickTitle'),
    onclick: (event) => {
      event.stopPropagation();
      openThemePopover(themeBtn);
    },
  },
    h('span', { class: 'theme-dot', 'aria-hidden': 'true' }),
    h('span', { class: 'theme-trigger-label' }, themeMeta.name));

  mount(host, soundBtn, themeBtn);
}

function applyShellI18n() {
  const nav = el('nav');
  if (nav) nav.setAttribute('aria-label', t('shell.navAria'));
  const toggle = el('navToggle');
  if (toggle) {
    toggle.setAttribute('aria-label', t('shell.menuToggle'));
    toggle.setAttribute('title', t('shell.menuToggle'));
  }
  const onlineHeader = el('onlineHeader');
  if (onlineHeader) {
    const count = ctx.presence.length;
    onlineHeader.innerHTML = '';
    const parts = t('shell.onlineCount', { count: '__COUNT__' }).split('__COUNT__');
    onlineHeader.append(
      parts[0] || '',
      h('span', { id: 'onlineCount' }, String(count)),
      parts[1] || '',
    );
  }
  const thisIsYou = el('thisIsYou');
  if (thisIsYou) thisIsYou.textContent = t('shell.thisIsYou');
  const settingsBtn = el('settingsBtn');
  if (settingsBtn) {
    settingsBtn.setAttribute('title', t('shell.settings'));
    settingsBtn.setAttribute('aria-label', t('shell.settings'));
  }
  const langBtn = el('langBtn');
  if (langBtn) {
    langBtn.textContent = t('shell.langShort');
    langBtn.setAttribute('title', t('shell.langSwitchTitle'));
  }
  buildNav();
  renderMe();
  renderPresence(ctx.presence);
  renderTopbarActions();
  setConn(lastConnOk);
}

/* ------------------------------------------------------- kênh hub chung --- */
net.on('hub', (msg) => {
  if (msg.t === 'welcome') {
    me.name = msg.you.name;
    me.color = msg.you.color;
    me.avatar = msg.you.avatar || null;
    localStorage.setItem('hub.name', me.name);
    if (msg.apps) {
      ctx.apps = msg.apps;
      buildNav();
    }
    if (msg.reactions) ctx.reactions = msg.reactions;
    renderMe();
  } else if (msg.t === 'presence') {
    renderPresence(msg.users);
  } else if (msg.t === 'fatal') {
    if (msg.code === 'uid_conflict') {
      localStorage.removeItem('hub.uid');
      localStorage.removeItem('hub.token');
      me.uid = loadUid();
      me.token = loadToken();
      net.identify(me.uid, me.name, me.token);
      toast(msg.message, 'warn');
      return;
    }
    toast(msg.message, 'danger');
  }

  // directory (name/color mới nhất theo uid) và avatar-changed đều ảnh hưởng
  // tới cách chat hiển thị lịch sử cũ. Merge ở tầng vỏ để mọi view đọc chung
  // ctx.directory; view chat tự nghe lại 'hub' để biết lúc nào cần vẽ lại.
  if ((msg.t === 'welcome' || msg.t === 'directory') && msg.directory) {
    // directory từ server chỉ có {name, color} (avatar tra riêng, xem dưới).
    // Merge từng uid để không xoá avatar đã biết từ trước.
    for (const [uid, profile] of Object.entries(msg.directory)) {
      ctx.directory[uid] = { ...(ctx.directory[uid] || {}), ...profile };
    }
  } else if (msg.t === 'avatar-changed') {
    ctx.directory[msg.uid] = { ...(ctx.directory[msg.uid] || {}), avatar: msg.avatar };
  } else if (msg.t === 'notify') {
    handleNotify(msg);
  }
});

/* ------------------------------------------------------------ thông báo --- */
/* Server phát gói 'notify' cho mọi người trừ người gửi, vì nó chỉ biết ai đang
 * ở app nào — không biết tab có đang hiện, cửa sổ có đang focus, hay người dùng
 * đã tắt thông báo. Toàn bộ phần lọc nằm ở đây. */
function handleNotify(msg) {
  if (msg.kind !== 'chat') return;

  // Kênh đã tắt thông báo thì im hoàn toàn: không tiếng, không thẻ, không
  // pop-up. Tin vẫn về và vẫn đếm chưa đọc ở cột kênh — tắt thông báo chứ
  // không phải bỏ qua tin.
  if (isMuted(msg.room)) return;

  // Tiếng "ting" phát ở đây cho MỌI tin nhắn đến, kể cả khi view chat không
  // được mount — nên view chat không phát tiếng nữa, tránh kêu hai lần.
  sfx.message();

  // Chỉ bỏ qua khi người dùng đang mở ĐÚNG kênh đó và cửa sổ đang được focus:
  // lúc ấy tin nhắn hiện ngay trước mắt nên thông báo chỉ là nhiễu. Tin của
  // kênh khác vẫn báo, kể cả khi đang ở trong app chat — huy hiệu nhỏ ở cột
  // kênh rất dễ bỏ sót. ctx.chatActive rỗng khi không ở view chat, nên đang
  // chơi cờ thì không điều kiện nào chặn thông báo.
  if (pageVisible() && ctx.chatActive === msg.room) return;

  notify({
    who: { name: msg.name, color: msg.color, avatar: msg.avatar },
    title: `${msg.name} · #${msg.roomTitle || msg.room}`,
    body: msg.text || t('shell.notifyMsgBody'),
    tag: `chat:${msg.room}`,
    onOpen: () => navigate(`chat/${msg.room}`),
  });
}

/* Badge chưa đọc của chat phải cập nhật kể cả khi đang ở app khác, nên nghe ở
 * tầng vỏ chứ không phải trong view chat. */
net.on('chat', (msg) => {
  if (msg.t !== 'channels') return;
  ctx.chatChannels = msg.channels;
  // Kênh đã tắt không được kéo huy hiệu sidebar / tiêu đề tab lên: mục đích
  // của tắt thông báo là để kênh đó thôi đòi bạn chú ý.
  const unread = msg.channels.reduce(
    (sum, c) => sum + (isMuted(c.name) ? 0 : (c.unread || 0)), 0);
  const onChat = parseHash().id === 'chat';
  setNavBadge('chat', onChat ? 0 : unread);
  setTitleBadge(unread && !onChat ? `(${unread})` : '');
});

/** Vẽ lại huy hiệu khi người dùng vừa tắt/bật thông báo một kênh.
 *  View chat gọi qua ctx.refreshBadges() — không import chéo main.js để tránh
 *  vòng phụ thuộc giữa vỏ và view. */
function refreshUnreadBadges() {
  const unread = (ctx.chatChannels || []).reduce(
    (sum, c) => sum + (isMuted(c.name) ? 0 : (c.unread || 0)), 0);
  const onChat = parseHash().id === 'chat';
  setNavBadge('chat', onChat ? 0 : unread);
  setTitleBadge(unread && !onChat ? `(${unread})` : '');
}

net.onStatus(setConn);

/* ------------------------------------------------------------ đổi avatar -- */
/** Tải ảnh lên làm avatar rồi đồng bộ lại mọi nơi đang hiện nó.
 *
 * Dùng chung cho modal Cài đặt (người dùng chọn file) và tab Tạo avatar (ảnh
 * PNG do máy vẽ). Một đường duy nhất nên không có chỗ nào quên gọi
 * net.send('hub','avatar') — thiếu gói đó thì avatar mới không hiện trên máy
 * người khác cho tới khi họ tải lại trang.
 */
async function uploadAvatar(file) {
  const prepared = await resizeImageFile(file, 512, 0.88);
  const form = new FormData();
  form.append('file', prepared);
  const res = await fetch(
    `/api/avatar?uid=${encodeURIComponent(me.uid)}&token=${encodeURIComponent(me.token || '')}`,
    { method: 'POST', body: form });
  if (!res.ok) {
    let detail = t('shell.uploadFailed');
    try { detail = (await res.json()).detail || detail; } catch { /* trống */ }
    throw new Error(detail);
  }
  const info = await res.json();
  me.avatar = info.url;
  renderMe();
  net.send('hub', 'avatar');
  return info.url;
}

/* --------------------------------------------------------------- khởi động */
async function askName() {
  const name = await prompt({
    title: t('shell.helloTitle'),
    label: t('shell.helloLabel'),
    placeholder: t('shell.helloPlaceholder'),
    okText: t('shell.helloOk'),
    maxlength: 24,
  });
  return name || t('shell.guestPrefix') + me.uid.slice(0, 4).toUpperCase();
}

function openSettingsModal() {
  openSettings({
    me,
    channels: ctx.chatChannels,
    onMuteChange: () => { refreshUnreadBadges(); render(); },
    onRename: (name) => {
      me.name = name;
      localStorage.setItem('hub.name', name);
      renderMe();
      net.identify(me.uid, name, me.token);
      net.send('hub', 'rename', { name });
    },
    onAvatarChange: uploadAvatar,
    onOpenStudio: () => navigate('faces'),
  });
}

async function boot() {
  applyShellI18n();
  const langBtn = el('langBtn');
  if (langBtn) langBtn.onclick = () => toggleLang();
  onLangChange(() => {
    applyShellI18n();
    render();
  });
  onThemeChange(() => renderTopbarActions());
  onSoundChange(() => renderTopbarActions());

  // Phím tắt Alt+T để đổi nhanh theme ở mọi màn hình.
  document.addEventListener('keydown', (event) => {
    if (!event.altKey || event.ctrlKey || event.metaKey || event.key.toLowerCase() !== 't') return;
    const tag = (event.target?.tagName || '').toLowerCase();
    if (tag === 'input' || tag === 'textarea' || tag === 'select') return;
    event.preventDefault();
    cycleTheme();
    toast(t('theme.switchedToast', { name: getThemeMeta().name }));
  });

  if (!me.name) me.name = await askName();
  localStorage.setItem('hub.name', me.name);
  renderMe();

  // Nạp danh sách app qua HTTP trước để sidebar có ngay, không chờ WebSocket.
  try {
    const info = await api('/api/apps');
    ctx.apps = info.apps;
    buildNav();
  } catch { /* welcome qua WS sẽ dựng lại nav */ }

  net.identify(me.uid, me.name, me.token);
  connectAttempted = true;
  net.connect();

  el('settingsBtn').onclick = openSettingsModal;
  const meProfileBtn = el('meProfileBtn');
  if (meProfileBtn) meProfileBtn.onclick = openSettingsModal;

  if (localStorage.getItem('hub.sidebar') === '0') {
    document.body.classList.add('sidebar-collapsed');
  }

  const navToggle = el('navToggle');
  const syncNavLabel = () => {
    const label = window.innerWidth <= 860 ? t('shell.menuToggle') : t('shell.sidebarToggle');
    navToggle.title = label;
    navToggle.setAttribute('aria-label', label);
  };
  syncNavLabel();
  window.addEventListener('resize', syncNavLabel);

  navToggle.onclick = () => {
    if (window.innerWidth <= 860) {
      document.body.classList.toggle('nav-open');
      return;
    }
    const collapsed = document.body.classList.toggle('sidebar-collapsed');
    localStorage.setItem('hub.sidebar', collapsed ? '0' : '1');
  };
  const navScrim = el('navScrim');
  if (navScrim) navScrim.onclick = () => document.body.classList.remove('nav-open');

  window.addEventListener('hashchange', render);
  if (!location.hash) location.hash = '#/home';
  await render();

  pollRoomCounts();
  setInterval(pollRoomCounts, 12000);

  // Mời bật thông báo, nhưng chỉ sau khi UI đã yên: hộp nhập tên vừa đóng mà
  // đã đẩy tiếp một thẻ nữa thì rất khó chịu. Chỉ hiện một lần cho mỗi
  // trình duyệt, và chỉ khi trình duyệt hỗ trợ Notification API.
  if (shouldInvite()) {
    setTimeout(() => {
      if (!shouldInvite()) return;    // người dùng có thể đã tự bật trong Cài đặt
      inviteCard({
        onResult: (result) => {
          if (result === 'granted') toast(t('shell.notifyInviteOk'), 'ok');
          else if (result === 'denied') {
            toast(t('shell.notifyInviteDenied'), 'danger');
          }
        },
      });
    }, 2500);
  }
}

// Giúp cho việc kiểm thử tự động quan sát được trạng thái thật của app.
window.hub = { ctx, net, me, navigate, parseHash };

boot();

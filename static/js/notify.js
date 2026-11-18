/* Thông báo khi có tin nhắn mới.
 *
 * Ba lớp, dùng cùng lúc vì mỗi lớp chỉ giải quyết được một tình huống:
 *
 *   1. Thẻ nổi trong trang (#notices) — dùng khi tab đang mở nhưng người dùng
 *      đang ở app khác (đang chơi cờ chẳng hạn). Bấm vào là nhảy thẳng tới
 *      kênh chat đó.
 *   2. Notification của hệ điều hành — dùng khi tab bị ẩn hoặc cửa sổ không
 *      focus. Đây là lớp duy nhất còn nhìn thấy được khi người dùng đã
 *      alt-tab sang việc khác.
 *   3. Nhấp nháy <title> — đường lui khi trình duyệt chặn notification. Luôn
 *      chạy được, không cần xin quyền gì.
 *
 * Lưu ý quyền: Notification.requestPermission() bắt buộc phải gọi từ trong một
 * cử chỉ của người dùng (click). Vì vậy module này KHÔNG tự xin quyền lúc nạp
 * trang — có nút trong modal Cài đặt, và một lời mời hiện một lần duy nhất
 * (xem inviteCard) để người dùng không phải tự đi tìm.
 *
 * Lớp 2 chỉ hoạt động khi trang là "secure context" (HTTPS hoặc localhost).
 * Khi không có quyền hệ thống thì lớp 1 + 3 vẫn luôn hoạt động bình thường.
 */

import { avatar, clear, h, icon } from './dom.js';
import { t } from './i18n.js';

const PREF_KEY = 'hub.notify';          // bật/tắt toàn bộ thông báo
const MUTE_KEY = 'hub.notify.mute';     // danh sách kênh đã tắt riêng
const INVITED_KEY = 'hub.notify.asked'; // đã hiện lời mời bật thông báo chưa
const MAX_CARDS = 4;
const CARD_MS = 6000;

/* ------------------------------------------------------------ tuỳ chọn ---- */
export function supported() {
  return typeof window !== 'undefined' && 'Notification' in window;
}

/** Người dùng có muốn nhận thông báo không (mặc định: có). */
export function wanted() {
  return localStorage.getItem(PREF_KEY) !== '0';
}

export function setWanted(on) {
  localStorage.setItem(PREF_KEY, on ? '1' : '0');
  return on;
}

/** 'unsupported' | 'default' | 'granted' | 'denied' */
export function permission() {
  if (!supported()) return 'unsupported';
  return Notification.permission;
}

/** Xin quyền. Phải gọi từ trong một click, nếu không trình duyệt bỏ qua. */
export async function requestPermission() {
  if (!supported()) return 'unsupported';
  if (Notification.permission !== 'default') return Notification.permission;
  try {
    return await Notification.requestPermission();
  } catch {
    return Notification.permission;
  }
}

/* --------------------------------------------------- tắt theo từng kênh --- */
/* Lưu ở localStorage chứ không phải trên server: hub không có đăng nhập, danh
 * tính vốn đã gắn với từng trình duyệt (hub.uid cũng nằm ở localStorage), nên
 * lưu ở server cũng không đồng bộ được sang máy khác. Giữ ở client cho gọn. */
function readMuted() {
  try {
    const raw = JSON.parse(localStorage.getItem(MUTE_KEY) || '[]');
    return Array.isArray(raw) ? raw.filter((name) => typeof name === 'string') : [];
  } catch {
    return [];
  }
}

/** Danh sách tên kênh đang bị tắt thông báo. */
export function mutedChannels() {
  return readMuted();
}

export function isMuted(channel) {
  return Boolean(channel) && readMuted().includes(channel);
}

export function setMuted(channel, on) {
  if (!channel) return false;
  const next = new Set(readMuted());
  if (on) next.add(channel);
  else next.delete(channel);
  localStorage.setItem(MUTE_KEY, JSON.stringify([...next]));
  return on;
}

/** Đảo trạng thái tắt/bật của một kênh, trả về trạng thái mới. */
export function toggleMuted(channel) {
  return setMuted(channel, !isMuted(channel));
}

/* ----------------------------------------------------- huy hiệu tiêu đề --- */
const BASE_TITLE = document.title;
let badgeText = '';
let flashTimer = null;

/** Tab đang hiện thì ghi tĩnh; tab bị ẩn thì nhấp nháy để lọt vào tầm mắt. */
function applyTitle() {
  clearInterval(flashTimer);
  flashTimer = null;
  if (!badgeText) {
    document.title = BASE_TITLE;
    return;
  }
  const marked = `${badgeText} ${BASE_TITLE}`;
  document.title = marked;
  if (document.hidden) {
    let on = false;
    flashTimer = setInterval(() => {
      on = !on;
      document.title = on ? BASE_TITLE : marked;
    }, 1400);
  }
}

/** Đặt huy hiệu trên tiêu đề tab, ví dụ "(3)". Chuỗi rỗng = xoá. */
export function setTitleBadge(text) {
  badgeText = text || '';
  applyTitle();
}

document.addEventListener('visibilitychange', applyTitle);

/* --------------------------------------------------- thẻ nổi trong trang -- */
function noticeRoot() {
  let root = document.getElementById('notices');
  if (!root) {
    root = h('div', { id: 'notices' });
    document.body.appendChild(root);
  }
  return root;
}

/** Thẻ thông báo trong trang. `onOpen` chạy khi người dùng bấm vào thẻ. */
export function noticeCard({ who, title, body, onOpen }) {
  const root = noticeRoot();
  while (root.childElementCount >= MAX_CARDS) root.firstChild.remove();

  const close = (node) => {
    node.style.opacity = '0';
    node.style.transform = 'translateX(14px)';
    setTimeout(() => node.remove(), 200);
  };

  const card = h('div', { class: 'notice', role: 'status' },
    who ? avatar(who) : h('div', { class: 'notice-icon' }, icon('bell', 16)),
    h('div', { class: 'notice-body' },
      h('div', { class: 'notice-title nowrap' }, title),
      h('div', { class: 'notice-text' }, body)),
    h('button', {
      class: 'icon ghost xs', 'aria-label': t('notify.closeAria'),
      onclick: (event) => { event.stopPropagation(); close(card); },
    }, icon('close', 14)));

  card.addEventListener('click', () => {
    close(card);
    if (onOpen) onOpen();
  });

  root.appendChild(card);
  setTimeout(() => { if (card.isConnected) close(card); }, CARD_MS);
  return card;
}

/* ------------------------------------------------ lời mời bật thông báo --- */
/** Thẻ mời bật thông báo hệ điều hành, KHÔNG tự tắt sau vài giây.
 *
 * Tồn tại vì quyền thông báo chỉ xin được từ trong một cú click, mà không ai
 * tự mò vào Cài đặt để bật. Hiện đúng một lần cho mỗi trình duyệt: bấm gì
 * cũng ghi nhớ, kể cả "Để sau", để không thành thứ đeo bám người dùng.
 */
export function inviteCard({ onResult } = {}) {
  const root = noticeRoot();
  const card = h('div', { class: 'notice notice-invite', role: 'status' },
    h('div', { class: 'notice-icon' }, icon('bell', 16)),
    h('div', { class: 'notice-body' },
      h('div', { class: 'notice-title' }, t('notify.inviteTitle')),
      h('div', { class: 'notice-text' },
        t('notify.inviteBody')),
      h('div', { class: 'row', style: { marginTop: '8px' } },
        h('button', {
          class: 'sm primary',
          onclick: async (event) => {
            event.stopPropagation();
            const result = await requestPermission();
            card.remove();
            if (onResult) onResult(result);
          },
        }, t('notify.inviteBtn')),
        h('button', {
          class: 'sm ghost',
          onclick: (event) => {
            event.stopPropagation();
            card.remove();
            if (onResult) onResult('dismissed');
          },
        }, t('notify.laterBtn')))));

  localStorage.setItem(INVITED_KEY, '1');
  root.appendChild(card);
  return card;
}

/** Có nên mời bật thông báo không: chỉ khi thật sự mời được và chưa mời lần nào. */
export function shouldInvite() {
  return supported() && wanted()
    && Notification.permission === 'default'
    && localStorage.getItem(INVITED_KEY) !== '1';
}

/* ------------------------------------------- notification của hệ điều hành */
const liveNotifications = new Map();   // tag -> Notification, để thay thế bản cũ

function systemNotice({ title, body, tag, iconUrl, onOpen }) {
  if (!supported() || Notification.permission !== 'granted') return null;
  try {
    // Cùng tag thì bản mới thay bản cũ, không xếp chồng 20 thông báo của cùng
    // một kênh chat.
    const old = liveNotifications.get(tag);
    if (old) { try { old.close(); } catch { /* đã tự đóng */ } }

    const note = new Notification(title, {
      body,
      tag,
      icon: iconUrl || undefined,
      silent: true,          // âm thanh do sfx của hub lo, tránh kêu hai lần
    });
    liveNotifications.set(tag, note);
    note.onclick = () => {
      window.focus();
      note.close();
      if (onOpen) onOpen();
    };
    note.onclose = () => {
      if (liveNotifications.get(tag) === note) liveNotifications.delete(tag);
    };
    return note;
  } catch {
    return null;           // một số trình duyệt chặn new Notification() ngoài SW
  }
}

/* -------------------------------------------------------------- cửa ngõ --- */
/** Người dùng có đang thật sự nhìn thấy trang không. */
export function pageVisible() {
  return !document.hidden && document.hasFocus();
}

/**
 * Hiện thông báo qua mọi kênh phù hợp.
 *
 * @param {object} opts
 * @param {object} [opts.who]     {name, color, avatar} để vẽ avatar trên thẻ
 * @param {string} opts.title     dòng đầu, ví dụ "Tùng · #cong-viec"
 * @param {string} opts.body      nội dung rút gọn
 * @param {string} opts.tag       khoá gộp, ví dụ "chat:cong-viec"
 * @param {function} [opts.onOpen] hành động khi bấm vào thông báo
 */
export function notify({ who, title, body, tag, onOpen }) {
  if (!wanted()) return;

  noticeCard({ who, title, body, onOpen });

  // Thẻ nổi vô dụng khi tab đang bị ẩn — lúc đó mới cần tới hệ điều hành.
  if (!pageVisible()) {
    systemNotice({ title, body, tag, iconUrl: who?.avatar, onOpen });
  }
}

export function clearNotices() {
  clear(noticeRoot());
}

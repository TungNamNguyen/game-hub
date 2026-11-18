/* Thông báo nổi, hộp thoại, cài đặt (theme + avatar), và âm thanh nhẹ. */

import { avatar, clear, h, icon } from './dom.js';
import { getLang, setLang, t, themeDesc } from './i18n.js';
import { mutedChannels as mutedList, permission as notifyPermission,
         requestPermission as askNotify, setMuted as setChannelMuted,
         setWanted as setNotifyWanted, supported as notifySupported,
         wanted as notifyWanted } from './notify.js';
import { applyTheme, currentTheme, getThemeMeta, isAutoTheme, onThemeChange, THEMES } from './themes.js';

const toastRoot = () => document.getElementById('toasts');

export function toast(message, level = '') {
  const node = h('div', { class: 'toast' + (level ? ' ' + level : ''), role: 'status' }, message);
  toastRoot().appendChild(node);
  setTimeout(() => {
    node.style.transition = 'opacity .2s';
    node.style.opacity = '0';
    setTimeout(() => node.remove(), 220);
  }, 3200);
}

/** Hộp thoại nhập một dòng. Trả về chuỗi, hoặc null nếu bấm Huỷ. */
export function prompt({ title, label, value = '', placeholder = '', okText = '', maxlength = 60 }) {
  return new Promise((resolve) => {
    const root = document.getElementById('modalRoot');
    const input = h('input', { value, placeholder, maxlength });
    const okLabel = okText || t('ui.done');

    const done = (result) => { clear(root); resolve(result); };
    const form = h('form', {
      class: 'modal',
      onsubmit: (event) => { event.preventDefault(); done(input.value.trim() || null); },
    },
      h('h2', {}, title),
      label ? h('label', { class: 'small dim' }, label) : null,
      input,
      h('div', { class: 'row', style: { justifyContent: 'flex-end' } },
        h('button', { type: 'button', class: 'ghost', onclick: () => done(null) }, t('ui.cancel')),
        h('button', { type: 'submit', class: 'primary' }, okLabel)));

    const back = h('div', {
      class: 'modal-back',
      onclick: (event) => { if (event.target === back) done(null); },
    }, form);

    back.addEventListener('keydown', (event) => { if (event.key === 'Escape') done(null); });
    clear(root).appendChild(back);
    input.focus();
    input.select();
  });
}

export function confirmBox({ title, body, okText = '', danger = false }) {
  return new Promise((resolve) => {
    const root = document.getElementById('modalRoot');
    const done = (result) => { clear(root); resolve(result); };
    const okLabel = okText || t('ui.ok');
    const box = h('div', { class: 'modal' },
      h('h2', {}, title),
      body ? h('p', { class: 'dim small' }, body) : null,
      h('div', { class: 'row', style: { justifyContent: 'flex-end' } },
        h('button', { class: 'ghost', onclick: () => done(false) }, t('ui.cancel')),
        h('button', { class: danger ? 'danger' : 'primary', onclick: () => done(true) }, okLabel)));
    const back = h('div', {
      class: 'modal-back',
      onclick: (event) => { if (event.target === back) done(false); },
    }, box);
    clear(root).appendChild(back);
    box.querySelector('button:last-child').focus();
  });
}

/** Hộp thoại chọn một trong nhiều lựa chọn to, dễ bấm.
 *
 * `options` = [{ id, label, glyph }]. Trả về `id` đã chọn, hoặc `fallback` nếu
 * người dùng đóng hộp thoại. Dùng cho phong cấp trong cờ vua, nơi bắt buộc
 * phải có một lựa chọn để nước đi hoàn tất.
 */
export function chooseBox({ title, body, options, fallback = null }) {
  return new Promise((resolve) => {
    const root = document.getElementById('modalRoot');
    const done = (result) => { clear(root); resolve(result); };

    const grid = h('div', { class: 'choice-grid' },
      options.map((option) => h('button', {
        type: 'button', class: 'choice', title: option.label,
        onclick: () => done(option.id),
      },
        option.glyph ? h('span', { class: 'choice-glyph' }, option.glyph) : null,
        h('span', { class: 'choice-label' }, option.label))));

    const box = h('div', { class: 'modal' },
      h('h2', {}, title),
      body ? h('p', { class: 'dim small' }, body) : null,
      grid);

    const back = h('div', {
      class: 'modal-back',
      onclick: (event) => { if (event.target === back) done(fallback); },
    }, box);
    back.addEventListener('keydown', (event) => {
      if (event.key === 'Escape') done(fallback);
    });
    clear(root).appendChild(back);
    grid.firstElementChild?.focus();
  });
}

export function emptyState(text, iconName = 'home', extra = null) {
  return h('div', { class: 'empty' }, icon(iconName, 34), h('p', {}, text), extra);
}

/* ------------------------------------------------------ bộ chọn theme ----- */
function themePreviewCard(theme, onPick) {
  const [bg, surface, accent, accentSoft, text = '#f1f5f9'] = theme.swatch;
  const check = h('span', { class: 'theme-check hidden' }, icon('check', 11));
  const btn = h('button', {
    type: 'button',
    class: 'theme-card',
    'data-theme-id': theme.id,
    'aria-pressed': 'false',
    onclick: () => {
      applyTheme(theme.id);
      onPick?.(theme);
    },
  },
    h('div', {
      class: 'theme-preview-frame',
      style: { background: bg },
    },
      h('div', { class: 'theme-preview-row' },
        h('span', { class: 'theme-preview-dot', style: { background: accent } }),
        h('span', { class: 'theme-preview-pill', style: { background: surface } }),
        h('span', {
          class: 'theme-preview-aa',
          style: { color: text, background: surface },
        }, 'Aa')),
      h('div', { class: 'theme-preview-row' },
        h('span', {
          class: 'theme-preview-bar',
          style: { background: `linear-gradient(90deg, ${accent}, ${accentSoft})` },
        }),
        h('span', { class: 'theme-preview-dot', style: { background: accentSoft } }))),
    h('div', { class: 'theme-card-meta' },
      h('div', { style: { minWidth: '0' } },
        h('div', { class: 'theme-card-name nowrap' }, theme.name),
        h('div', { class: 'theme-card-desc nowrap' }, themeDesc(theme.id, theme.desc))),
      check));

  return { id: theme.id, node: btn, check };
}

export function createThemePicker({ onPick } = {}) {
  const darkThemes = THEMES.filter((item) => item.scheme === 'dark');
  const lightThemes = THEMES.filter((item) => item.scheme === 'light');
  let filter = 'all';

  const autoCheck = h('span', { class: 'theme-check hidden' }, icon('check', 11));
  const autoBtn = h('button', {
    type: 'button',
    class: 'theme-auto-btn',
    'aria-pressed': 'false',
    onclick: () => {
      applyTheme('auto');
      syncSelection();
      onPick?.({ id: 'auto', meta: getThemeMeta() });
    },
  },
    icon('monitor', 16),
    h('div', { class: 'grow', style: { minWidth: '0' } },
      h('div', { class: 'theme-card-name' }, t('theme.auto')),
      h('div', { class: 'theme-card-desc' }, t('theme.autoDesc'))),
    autoCheck);

  const cards = [];
  const makeCard = (item) => {
    const card = themePreviewCard(item, (picked) => {
      syncSelection();
      onPick?.({ id: picked.id, meta: picked });
    });
    cards.push(card);
    return card.node;
  };

  const darkSection = h('div', { class: 'theme-section' },
    h('div', { class: 'theme-group-head' }, icon('moon', 12), t('theme.darkGroup')),
    h('div', { class: 'theme-grid' }, darkThemes.map(makeCard)));

  const lightSection = h('div', { class: 'theme-section' },
    h('div', { class: 'theme-group-head' }, icon('sun', 12), t('theme.lightGroup')),
    h('div', { class: 'theme-grid' }, lightThemes.map(makeCard)));

  const filterMeta = [
    ['all', t('theme.filterAll', { n: THEMES.length })],
    ['dark', t('theme.filterDark', { n: darkThemes.length })],
    ['light', t('theme.filterLight', { n: lightThemes.length })],
  ];
  const filterBtns = filterMeta.map(([mode, label]) => h('button', {
    type: 'button',
    class: 'theme-filter-btn' + (mode === filter ? ' active' : ''),
    'aria-pressed': String(mode === filter),
    onclick: () => setFilter(mode),
  }, label));

  function setFilter(mode) {
    filter = mode;
    filterBtns.forEach((btn, idx) => {
      const on = filterMeta[idx][0] === filter;
      btn.classList.toggle('active', on);
      btn.setAttribute('aria-pressed', String(on));
    });
    darkSection.classList.toggle('hidden', filter === 'light');
    lightSection.classList.toggle('hidden', filter === 'dark');
  }

  // Cập nhật trạng thái chọn tại chỗ (không clear/rebuild DOM) để giữ nguyên vị trí cuộn.
  function syncSelection() {
    const pref = currentTheme();
    const auto = isAutoTheme();
    const activeId = auto ? '' : pref;

    autoBtn.classList.toggle('active', auto);
    autoBtn.setAttribute('aria-pressed', String(auto));
    autoCheck.classList.toggle('hidden', !auto);

    for (const card of cards) {
      const on = card.id === activeId;
      card.node.classList.toggle('active', on);
      card.node.setAttribute('aria-pressed', String(on));
      card.check.classList.toggle('hidden', !on);
    }
  }

  const wrap = h('div', { class: 'theme-picker' },
    autoBtn,
    h('div', { class: 'theme-filters', role: 'tablist' }, filterBtns),
    darkSection,
    lightSection);

  syncSelection();
  return { node: wrap, refresh: syncSelection };
}

let activePopoverCleanup = null;

export function closeThemePopover() {
  if (activePopoverCleanup) {
    activePopoverCleanup();
    activePopoverCleanup = null;
  }
}

export function openThemePopover(anchorEl = null) {
  const root = document.getElementById('popoverRoot');
  if (!root) return;
  if (activePopoverCleanup) {
    closeThemePopover();
    return;
  }

  if (anchorEl) anchorEl.classList.add('open');
  const picker = createThemePicker();

  const close = () => {
    clear(root);
    if (anchorEl) anchorEl.classList.remove('open');
    document.removeEventListener('keydown', onKey);
    stopThemeWatch();
    activePopoverCleanup = null;
  };
  const onKey = (event) => {
    if (event.key === 'Escape') close();
  };
  const stopThemeWatch = onThemeChange(() => picker.refresh());

  const panel = h('div', {
    class: 'theme-popover',
    role: 'dialog',
    'aria-label': t('theme.quickTitle'),
  },
    h('div', { class: 'theme-popover-head' },
      h('div', { class: 'row', style: { gap: '8px' } },
        icon('palette', 16),
        h('strong', { style: { fontSize: '14px' } }, t('theme.quickTitle'))),
      h('button', {
        class: 'icon ghost xs', type: 'button',
        'aria-label': t('ui.close'), onclick: close,
      }, icon('close', 15))),
    h('div', { class: 'theme-popover-body' }, picker.node),
    h('div', { class: 'theme-popover-foot' },
      h('span', {}, t('theme.shortcutHint'))));

  const back = h('div', {
    class: 'theme-popover-back',
    onclick: (event) => { if (event.target === back) close(); },
  }, panel);

  document.addEventListener('keydown', onKey);
  clear(root).appendChild(back);
  activePopoverCleanup = close;
}

/** Modal cài đặt: đổi tên, avatar, giao diện, ngôn ngữ, thông báo. */
export function openSettings({ me, onRename, onAvatarChange,
                               channels = [], onMuteChange, onOpenStudio }) {
  closeThemePopover();
  const root = document.getElementById('modalRoot');
  const stopThemeWatch = onThemeChange(() => themePicker.refresh());
  const stopSoundWatch = onSoundChange(() => renderNotify());

  const done = () => {
    stopThemeWatch();
    stopSoundWatch();
    clear(root);
  };

  const nameInput = h('input', { value: me.name, maxlength: 24, placeholder: t('ui.displayNamePlaceholder') });
  let avatarBusy = false;

  const avatarPreview = h('div', { class: 'settings-avatar-preview' },
    avatar({ ...me, name: me.name }, 'lg'));

  const fileInput = h('input', {
    type: 'file', accept: 'image/*',
    class: 'hidden',
    onchange: async (event) => {
      const file = event.target.files?.[0];
      event.target.value = '';
      if (!file || avatarBusy) return;
      avatarBusy = true;
      try {
        const url = await onAvatarChange(file);
        clear(avatarPreview).appendChild(avatar({ ...me, avatar: url }, 'lg'));
        toast(t('ui.avatarSaved'), 'ok');
      } catch (err) {
        toast(err.message || t('ui.avatarFailed'), 'danger');
      } finally {
        avatarBusy = false;
      }
    },
  });

  /* ---- thông báo + âm thanh -------------------------------------------- */
  const notifyBox = h('div', { class: 'col', style: { gap: '8px' } });

  function notifyHint() {
    if (!notifySupported()) return t('ui.notifyUnsupported');
    const state = notifyPermission();
    if (state === 'granted') return t('ui.notifyGranted');
    if (state === 'denied') return t('ui.notifyBlocked');
    return t('ui.notifyAsk');
  }

  function renderNotify() {
    const on = notifyWanted();
    const state = notifySupported() ? notifyPermission() : 'unsupported';

    clear(notifyBox);
    notifyBox.appendChild(h('label', { class: 'check' },
      h('input', {
        type: 'checkbox', checked: on,
        onchange: (event) => { setNotifyWanted(event.target.checked); renderNotify(); },
      }),
      h('span', {}, t('ui.notifyWanted'))));

    notifyBox.appendChild(h('label', { class: 'check' },
      h('input', {
        type: 'checkbox', checked: soundEnabled(),
        onchange: () => { toggleSound(); sfx.message(); },
      }),
      h('span', {}, t('ui.sound'))));

    if (on && state === 'default') {
      notifyBox.appendChild(h('div', { class: 'row' },
        h('button', {
          class: 'sm', type: 'button',
          onclick: async () => {
            const result = await askNotify();
            renderNotify();
            if (result === 'granted') toast(t('ui.sysNotifyOn'), 'ok');
            else if (result === 'denied') toast(t('ui.sysNotifyDenied'), 'danger');
          },
        }, icon('bell', 14), ' ' + t('ui.allowSysNotify'))));
    }

    const level = state === 'granted' ? 'ok' : state === 'denied' ? 'danger' : '';
    notifyBox.appendChild(h('div', { class: 'hint' }, notifyHint()));

    if (on && notifySupported()) {
      notifyBox.appendChild(h('span', { class: 'chip' + (level ? ' ' + level : '') },
        icon(state === 'granted' ? 'bell' : 'bellOff', 13),
        state === 'granted' ? t('ui.sysStatusGranted')
          : state === 'denied' ? t('ui.sysStatusDenied')
          : t('ui.sysStatusDefault')));
    }

    const muted = mutedList();
    if (muted.length) {
      const title = (name) =>
        (channels.find((c) => c.name === name) || {}).title || '#' + name;
      notifyBox.appendChild(h('div', { class: 'muted-list' },
        h('div', { class: 'tiny muted' }, t('ui.mutedCount', { count: muted.length })),
        muted.map((name) => h('div', { class: 'muted-row' },
          icon('bellOff', 13),
          h('span', { class: 'grow nowrap' }, title(name)),
          h('button', {
            class: 'xs ghost', type: 'button',
            onclick: () => {
              setChannelMuted(name, false);
              renderNotify();
              onMuteChange?.();
              toast(t('ui.unmutedToast', { name: title(name) }), 'ok');
            },
          }, t('ui.unmuteBtn'))))));
    }
  }
  renderNotify();

  const langBox = h('div', { class: 'segmented', role: 'group', 'aria-label': t('ui.languageLabel') });
  function renderLangBox() {
    const activeLang = getLang();
    clear(langBox);
    langBox.append(
      h('button', {
        type: 'button',
        class: activeLang === 'vi' ? 'active' : '',
        onclick: () => {
          if (getLang() !== 'vi') {
            setLang('vi');
            done();
            openSettings({ me, onRename, onAvatarChange, channels, onMuteChange, onOpenStudio });
          }
        },
      }, t('ui.langVi')),
      h('button', {
        type: 'button',
        class: activeLang === 'en' ? 'active' : '',
        onclick: () => {
          if (getLang() !== 'en') {
            setLang('en');
            done();
            openSettings({ me, onRename, onAvatarChange, channels, onMuteChange, onOpenStudio });
          }
        },
      }, t('ui.langEn')),
    );
  }
  renderLangBox();

  const themePicker = createThemePicker();

  const saveName = () => {
    const name = nameInput.value.trim();
    if (!name) { toast(t('ui.nameEmpty'), 'danger'); return; }
    onRename(name);
    toast(t('ui.nameSaved'), 'ok');
  };

  const box = h('div', { class: 'modal settings-modal' },
    h('div', { class: 'spread settings-head' },
      h('h2', {}, t('ui.settingsTitle')),
      h('button', { class: 'icon ghost xs', type: 'button', onclick: done, 'aria-label': t('ui.close') },
        icon('close', 16))),

    h('div', { class: 'settings-body' },
      h('div', { class: 'settings-section' },
        h('div', { class: 'settings-section-title' }, t('ui.profileSection')),
        h('div', { class: 'field' },
          h('label', {}, t('ui.displayName')),
          h('form', {
            class: 'row',
            onsubmit: (event) => { event.preventDefault(); saveName(); },
          },
            nameInput,
            h('button', { class: 'sm primary', type: 'submit' }, t('ui.save')))),
        h('div', { class: 'field' },
          h('label', {}, t('ui.avatarLabel')),
          h('div', { class: 'row-wrap', style: { alignItems: 'center' } },
            avatarPreview,
            h('button', {
              class: 'sm', type: 'button',
              onclick: () => fileInput.click(),
            }, icon('upload', 14), ' ' + t('ui.chooseImage')),
            onOpenStudio
              ? h('button', {
                  class: 'sm ghost', type: 'button',
                  onclick: () => { done(); onOpenStudio(); },
                }, icon('sparkles', 14), ' ' + t('ui.openAvatarStudio'))
              : null,
            fileInput))),

      h('div', { class: 'settings-section' },
        h('div', { class: 'settings-section-title' }, t('ui.appearanceSection')),
        h('div', { class: 'field' },
          h('label', {}, t('ui.languageLabel')),
          langBox),
        h('div', { class: 'field' },
          h('label', {}, t('ui.themeLabel')),
          themePicker.node)),

      h('div', { class: 'settings-section' },
        h('div', { class: 'settings-section-title' }, t('ui.notifySection')),
        notifyBox)));

  const back = h('div', {
    class: 'modal-back',
    onclick: (event) => { if (event.target === back) done(); },
  }, box);
  back.addEventListener('keydown', (event) => { if (event.key === 'Escape') done(); });
  clear(root).appendChild(back);
  nameInput.focus();
}

/* ------------------------------------------------------------- âm thanh --- */
let audioCtx = null;
let soundOn = localStorage.getItem('hub.sound') !== '0';
const soundListeners = new Set();

export function soundEnabled() { return soundOn; }

export function onSoundChange(fn) {
  soundListeners.add(fn);
  return () => soundListeners.delete(fn);
}

export function toggleSound() {
  soundOn = !soundOn;
  localStorage.setItem('hub.sound', soundOn ? '1' : '0');
  for (const fn of [...soundListeners]) {
    try { fn(soundOn); } catch { /* ignore */ }
  }
  return soundOn;
}

function beep(freq, duration, peak = 0.12) {
  if (!soundOn) return;
  try {
    audioCtx = audioCtx || new (window.AudioContext || window.webkitAudioContext)();
    const osc = audioCtx.createOscillator();
    const gain = audioCtx.createGain();
    osc.type = 'sine';
    osc.frequency.value = freq;
    gain.gain.setValueAtTime(0, audioCtx.currentTime);
    gain.gain.linearRampToValueAtTime(peak, audioCtx.currentTime + 0.01);
    gain.gain.exponentialRampToValueAtTime(0.0001, audioCtx.currentTime + duration);
    osc.connect(gain).connect(audioCtx.destination);
    osc.start();
    osc.stop(audioCtx.currentTime + duration);
  } catch { /* trình duyệt chặn audio trước khi có tương tác, bỏ qua */ }
}

export const sfx = {
  move: () => beep(520, 0.08),
  message: () => beep(660, 0.07, 0.09),
  hit: () => { beep(320, 0.1, 0.14); setTimeout(() => beep(220, 0.16, 0.12), 80); },
  miss: () => beep(180, 0.12, 0.09),
  win: () => { beep(660, 0.12, 0.14); setTimeout(() => beep(880, 0.2, 0.14), 120); },
  lose: () => beep(200, 0.3, 0.11),
};

/* ----------------------------------------------------------- nén ảnh ------ */
/** Thu nhỏ ảnh trên trình duyệt trước khi upload để tiết kiệm RAM server. */
export async function resizeImageFile(file, maxDim = 2000, quality = 0.85) {
  if (!file || file.type === 'image/gif' || !file.type?.startsWith('image/')) {
    return file;
  }
  let bmp = null;
  let objUrl = null;
  try {
    let width = 0;
    let height = 0;
    let source = null;
    if (typeof createImageBitmap === 'function') {
      bmp = await createImageBitmap(file);
      width = bmp.width;
      height = bmp.height;
      source = bmp;
    } else {
      objUrl = URL.createObjectURL(file);
      const img = await new Promise((resolve, reject) => {
        const el = new Image();
        el.onload = () => resolve(el);
        el.onerror = reject;
        el.src = objUrl;
      });
      width = img.naturalWidth || img.width;
      height = img.naturalHeight || img.height;
      source = img;
    }

    const longest = Math.max(width, height);
    if (longest <= maxDim && file.size <= 350 * 1024) {
      return file;
    }

    const scale = longest > maxDim ? maxDim / longest : 1;
    const targetW = Math.max(1, Math.round(width * scale));
    const targetH = Math.max(1, Math.round(height * scale));
    const canvas = document.createElement('canvas');
    canvas.width = targetW;
    canvas.height = targetH;
    const ctx = canvas.getContext('2d');
    if (!ctx) return file;
    ctx.drawImage(source, 0, 0, targetW, targetH);

    const toBlob = (mime) => new Promise((resolve) => canvas.toBlob(resolve, mime, quality));
    let blob = await toBlob('image/webp');
    let ext = 'webp';
    if (!blob || blob.type !== 'image/webp') {
      blob = await toBlob('image/jpeg');
      ext = 'jpg';
    }
    if (!blob || (longest <= maxDim && blob.size >= file.size)) {
      return file;
    }
    return new File([blob], `image.${ext}`, { type: blob.type });
  } catch {
    return file;
  } finally {
    if (bmp && typeof bmp.close === 'function') bmp.close();
    if (objUrl) URL.revokeObjectURL(objUrl);
  }
}

/* ----------------------------------------------------- custom dropdown --- */
/** Dropdown đồng bộ theo 16 theme thay cho thẻ <select> mặc định của OS. */
export function createSelect({ options = [], value = '', onChange = null, ariaLabel = '' } = {}) {
  let items = options.map((opt) => ({
    value: String(opt?.value ?? ''),
    label: String(opt?.label ?? opt?.value ?? ''),
  }));
  let current = items.some((o) => o.value === String(value))
    ? String(value)
    : (items[0]?.value ?? '');
  let open = false;
  let optionBtns = [];

  const labelEl = h('span', { class: 'ui-select-label nowrap' });
  const caretEl = h('span', { class: 'ui-select-caret', 'aria-hidden': 'true' }, icon('chevronDown', 16));
  const trigger = h('button', {
    type: 'button',
    class: 'ui-select-trigger',
    'aria-haspopup': 'listbox',
    'aria-expanded': 'false',
    ...(ariaLabel ? { 'aria-label': ariaLabel } : {}),
  }, labelEl, caretEl);

  const menu = h('div', { class: 'ui-select-menu hidden', role: 'listbox' });
  const wrap = h('div', { class: 'ui-select' }, trigger, menu);

  function syncLabel() {
    const found = items.find((o) => o.value === current);
    labelEl.textContent = found ? found.label : (items[0]?.label || '');
  }

  function renderOptions() {
    clear(menu);
    optionBtns = items.map((opt) => {
      const selected = opt.value === current;
      const btn = h('button', {
        type: 'button',
        role: 'option',
        class: 'ui-select-option' + (selected ? ' active' : ''),
        'aria-selected': String(selected),
        onclick: () => {
          const changed = opt.value !== current;
          current = opt.value;
          syncActive();
          setOpen(false);
          trigger.focus();
          if (changed) onChange?.(current);
        },
      },
        h('span', { class: 'nowrap grow', style: { textAlign: 'left' } }, opt.label),
        h('span', { class: 'ui-select-check' + (selected ? '' : ' hidden') }, icon('check', 14)));
      return { value: opt.value, btn };
    });
    menu.append(...optionBtns.map((x) => x.btn));
    syncLabel();
  }

  function syncActive() {
    syncLabel();
    for (const entry of optionBtns) {
      const selected = entry.value === current;
      entry.btn.classList.toggle('active', selected);
      entry.btn.setAttribute('aria-selected', String(selected));
      entry.btn.lastChild?.classList.toggle('hidden', !selected);
    }
  }

  const onOutside = (event) => {
    if (!wrap.isConnected) {
      document.removeEventListener('pointerdown', onOutside, true);
      return;
    }
    if (!wrap.contains(event.target)) setOpen(false);
  };

  function setOpen(next) {
    open = Boolean(next);
    wrap.classList.toggle('open', open);
    trigger.setAttribute('aria-expanded', String(open));
    menu.classList.toggle('hidden', !open);
    if (open) {
      const rect = trigger.getBoundingClientRect();
      const flipUp = rect.bottom + 240 > window.innerHeight && rect.top > 180;
      menu.classList.toggle('up', flipUp);
      document.addEventListener('pointerdown', onOutside, true);
    } else {
      document.removeEventListener('pointerdown', onOutside, true);
    }
  }

  trigger.addEventListener('click', (event) => {
    event.stopPropagation();
    setOpen(!open);
  });

  wrap.addEventListener('keydown', (event) => {
    if (event.key === 'Escape' && open) {
      event.preventDefault();
      setOpen(false);
      trigger.focus();
      return;
    }
    if ((event.key === 'ArrowDown' || event.key === 'ArrowUp') && items.length) {
      event.preventDefault();
      if (!open) {
        setOpen(true);
        return;
      }
      const idx = Math.max(0, items.findIndex((o) => o.value === current));
      const nextIdx = (idx + (event.key === 'ArrowDown' ? 1 : -1) + items.length) % items.length;
      const nextVal = items[nextIdx].value;
      if (nextVal !== current) {
        current = nextVal;
        syncActive();
        onChange?.(current);
      }
    }
  });

  Object.defineProperty(wrap, 'value', {
    get: () => current,
    set: (v) => {
      const next = String(v ?? '');
      if (items.some((o) => o.value === next)) {
        current = next;
        syncActive();
      }
    },
  });
  wrap.setOptions = (newOptions) => {
    items = newOptions.map((opt) => ({
      value: String(opt?.value ?? ''),
      label: String(opt?.label ?? opt?.value ?? ''),
    }));
    if (!items.some((o) => o.value === current)) current = items[0]?.value ?? '';
    renderOptions();
  };

  renderOptions();
  return wrap;
}

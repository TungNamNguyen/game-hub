/* Quản lý theme toàn hệ thống: hỗ trợ chế độ Tự động (theo OS), 16 Dark & Light themes,
 * đồng bộ thuộc tính <html>, color-scheme và <meta name="theme-color">.
 */

export const THEMES = [
  // ---- Dark themes (10) ----
  {
    id: 'midnight',
    name: 'Midnight',
    scheme: 'dark',
    desc: 'Bóng đêm tối giản',
    swatch: ['#0a0d14', '#151a26', '#6366f1', '#a855f7', '#e8ebf2'],
    themeColor: '#0f131c',
  },
  {
    id: 'tokyo',
    name: 'Tokyo Night',
    scheme: 'dark',
    desc: 'Đêm Tokyo dịu mắt',
    swatch: ['#13141c', '#1a1b26', '#7aa2f7', '#bb9af7', '#c0caf5'],
    themeColor: '#16161e',
  },
  {
    id: 'cyberpunk',
    name: 'Cyberpunk Neon',
    scheme: 'dark',
    desc: 'Công nghệ tương lai',
    swatch: ['#0d0221', '#190a3a', '#ff007f', '#00f0ff', '#f3e8ff'],
    themeColor: '#120433',
  },
  {
    id: 'synthwave',
    name: 'Synthwave 80s',
    scheme: 'dark',
    desc: 'Hoài cổ điện quang',
    swatch: ['#140724', '#24113b', '#f97316', '#ec4899', '#fdf4ff'],
    themeColor: '#1c0b2e',
  },
  {
    id: 'dracula',
    name: 'Dracula Noir',
    scheme: 'dark',
    desc: 'Dịu mắt ban đêm',
    swatch: ['#191a24', '#282a36', '#bd93f9', '#ff79c6', '#f8f8f2'],
    themeColor: '#21222c',
  },
  {
    id: 'aurora',
    name: 'Aurora Borealis',
    scheme: 'dark',
    desc: 'Cực quang ngọc bích',
    swatch: ['#061317', '#0c2026', '#14b8a6', '#38bdf8', '#e6faf8'],
    themeColor: '#09191f',
  },
  {
    id: 'crimson',
    name: 'Crimson Velvet',
    scheme: 'dark',
    desc: 'Đỏ nhung quyền lực',
    swatch: ['#14070a', '#210c12', '#e11d48', '#fb923c', '#fff1f2'],
    themeColor: '#1b090e',
  },
  {
    id: 'casino',
    name: 'Royal Casino',
    scheme: 'dark',
    desc: 'Vàng kim sang trọng',
    swatch: ['#080f0b', '#132219', '#eab308', '#10b981', '#f7f5eb'],
    themeColor: '#0e1913',
  },
  {
    id: 'ocean',
    name: 'Deep Ocean',
    scheme: 'dark',
    desc: 'Đại dương sâu',
    swatch: ['#0b192c', '#183252', '#0284c7', '#38bdf8', '#eaf6ff'],
    themeColor: '#0f2138',
  },
  {
    id: 'forest',
    name: 'Emerald Forest',
    scheme: 'dark',
    desc: 'Rừng đêm phát sáng',
    swatch: ['#0c1b11', '#173120', '#16a34a', '#84cc16', '#eaf7ec'],
    themeColor: '#112418',
  },

  // ---- Light themes (6) ----
  {
    id: 'corporate',
    name: 'Nordic Light',
    scheme: 'light',
    desc: 'Sáng thanh lịch',
    swatch: ['#f8fafc', '#ffffff', '#2563eb', '#0ea5e9', '#0f172a'],
    themeColor: '#f8fafc',
  },
  {
    id: 'matcha',
    name: 'Matcha Latte',
    scheme: 'light',
    desc: 'Trà xanh thanh mát',
    swatch: ['#f4f7f2', '#ffffff', '#4d7c0f', '#84cc16', '#1c2b17'],
    themeColor: '#f4f7f2',
  },
  {
    id: 'lavender',
    name: 'Lavender Mist',
    scheme: 'light',
    desc: 'Oải hương dịu nhẹ',
    swatch: ['#f6f4ff', '#ffffff', '#7c3aed', '#a78bfa', '#26174a'],
    themeColor: '#f6f4ff',
  },
  {
    id: 'sunset',
    name: 'Sunset Warm',
    scheme: 'light',
    desc: 'Hoàng hôn cát ấm',
    swatch: ['#fff7ed', '#ffffff', '#ea580c', '#fbbf24', '#431407'],
    themeColor: '#fff7ed',
  },
  {
    id: 'sakura',
    name: 'Sakura Pastel',
    scheme: 'light',
    desc: 'Hoa anh đào pastel',
    swatch: ['#fdf2f8', '#ffffff', '#ec4899', '#c084fc', '#701a45'],
    themeColor: '#fdf2f8',
  },
  {
    id: 'retro',
    name: 'Retro Coffee',
    scheme: 'light',
    desc: 'Giấy kem cà phê',
    swatch: ['#f5f0eb', '#faf7f4', '#7f5539', '#b08968', '#3d2b1f'],
    themeColor: '#f5f0eb',
  },
];

const KEY = 'hub.theme';
const BY_ID = new Map(THEMES.map((t) => [t.id, t]));
const listeners = new Set();

const mediaQuery = typeof window !== 'undefined' && window.matchMedia
  ? window.matchMedia('(prefers-color-scheme: dark)')
  : null;

function systemThemeId() {
  return mediaQuery && !mediaQuery.matches ? 'corporate' : 'midnight';
}

export function currentTheme() {
  try {
    const saved = localStorage.getItem(KEY);
    if (saved === 'auto' || BY_ID.has(saved)) return saved;
  } catch { /* private mode */ }
  return 'midnight';
}

export function isAutoTheme() {
  return currentTheme() === 'auto';
}

export function resolvedTheme(id = currentTheme()) {
  if (id === 'auto') return systemThemeId();
  return BY_ID.has(id) ? id : 'midnight';
}

export function getThemeMeta(id = resolvedTheme()) {
  return BY_ID.get(resolvedTheme(id)) || THEMES[0];
}

function syncDocument(preference, notify = true) {
  const activeId = resolvedTheme(preference);
  const meta = BY_ID.get(activeId) || THEMES[0];
  const root = document.documentElement;

  if (activeId === 'midnight') {
    root.removeAttribute('data-theme');
  } else {
    root.setAttribute('data-theme', activeId);
  }
  root.setAttribute('data-theme-scheme', meta.scheme);
  root.style.colorScheme = meta.scheme;

  const metaEl = document.querySelector('meta[name="theme-color"]');
  if (metaEl) metaEl.setAttribute('content', meta.themeColor);

  if (notify) {
    for (const fn of [...listeners]) {
      try { fn({ preference, activeId, meta }); } catch (err) { console.error('theme listener error', err); }
    }
  }
  return { preference, activeId, meta };
}

export function applyTheme(id) {
  const preference = id === 'auto' || BY_ID.has(id) ? id : 'midnight';
  try { localStorage.setItem(KEY, preference); } catch { /* ignore */ }
  const info = syncDocument(preference, true);
  return info.preference;
}

export function cycleTheme() {
  const cur = resolvedTheme();
  const idx = THEMES.findIndex((t) => t.id === cur);
  const next = THEMES[(idx + 1) % THEMES.length];
  return applyTheme(next.id);
}

export function onThemeChange(fn) {
  listeners.add(fn);
  return () => listeners.delete(fn);
}

if (mediaQuery) {
  const handleOsChange = () => {
    if (currentTheme() === 'auto') syncDocument('auto', true);
  };
  if (typeof mediaQuery.addEventListener === 'function') {
    mediaQuery.addEventListener('change', handleOsChange);
  } else if (typeof mediaQuery.addListener === 'function') {
    mediaQuery.addListener(handleOsChange);
  }
}

syncDocument(currentTheme(), false);

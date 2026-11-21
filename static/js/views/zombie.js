/* Đêm Tử Thần (Zombie Outbreak 3.0) — Game Bắn Súng Sinh Tồn Zombie Multiplayer 1–6 người Co-op & AI Bots.
 * Đồ họa 2.5D Tactical Canvas 60 FPS: Persistent HUD DOM (0 lag), Local Movement Prediction, Instant Local Aim,
 * 6 Bản đồ 2.5D, 8 Vũ khí nâng cấp Mk.I–III + SVG Icons, Lựu đạn Băng/EMP, Mìn Từ Trường, Thùng Phuy Nổ,
 * Trụ Súng có HP, Hiệu ứng Vết Cào & Viền Máu, Mini-Boss & Boss Đột Biến.
 */

import { avatar, clear, h, mount } from '../dom.js';
import { modeLabel, t } from '../i18n.js';
import { soundEnabled, toast } from '../ui.js';
import { renderLobby, roomCard, roomChat, roomTopbar } from './gameroom.js';

const CHANNEL = 'zombie';
const CLASS_IDS = ['assault', 'medic', 'engineer', 'vanguard'];
const MAP_IDS = ['outpost', 'lab', 'metro', 'dock', 'reactor', 'endless'];
const DIFF_IDS = ['easy', 'normal', 'hard'];

const CLASS_META = {
  assault: { icon: '🔫', color: '#38bdf8', desc: '+20% Sát thương · Thay đạn nhanh · SMG' },
  medic: { icon: '⚕️', color: '#4ade80', desc: 'Hào quang hồi máu · Cứu đồng đội ×2 nhanh' },
  engineer: { icon: '🛠️', color: '#fbbf24', desc: 'Tặng 1 Trụ Súng + 1 Mìn · Trụ trâu & mạnh +35%' },
  vanguard: { icon: '🛡️', color: '#f87171', desc: '150 HP + 55 Giáp · Shotgun · Dash nhanh' },
};

const PERK_DESC = {
  damage: '+20% Sát thương đạn',
  reload: '+30% Băng đạn · -18% Thay đạn',
  speed: '+12% Tốc độ di chuyển',
  armor: '+30 HP tối đa · +20 Trần Giáp & +45 Giáp',
  vamp: '+4 HP mỗi khi hạ Zombie',
};

const PERK_ICON = { damage: '💥', reload: '🔄', speed: '👟', armor: '🛡️', vamp: '🩸' };
const ITEM_ICON = {
  medkit: '🩹', shield: '🛡️', ammo: '📦', stim: '💉',
  grenade: '💣', cryo: '❄️', emp: '🌩️', mine: '🚨', turret: '🛰️', repair: '🔧',
};

const WEAPON_SHORT = {
  pistol: 'M1911', smg: 'VECTOR', shotgun: 'M870', rifle: 'AK-47',
  launcher: 'M79', flamer: 'FLAMER', tesla: 'TESLA', railgun: 'RAILGUN',
};

const SHOP_TABS = [
  ['all', 'Tất cả'],
  ['weapons', '🔫 Vũ khí'],
  ['gadget', '💣 Lựu đạn & CC'],
  ['supply', '⚡ Kỹ năng & Tiếp tế'],
];

/* ------------------------------------------- SVG Weapon Silhouette Icons -- */
const WEAPON_SVG_MARKUP = {
  pistol: `<svg viewBox="0 0 64 28" class="z-wsvg" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 8h34v7H27l-3 10h-8l3-10h-5z" fill="currentColor" fill-opacity="0.22"/><path d="M27 15h6l-1 4h-5"/><line x1="48" y1="10" x2="54" y2="10"/></svg>`,
  smg: `<svg viewBox="0 0 64 28" class="z-wsvg" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M8 9h38v8H34l-2 9h-6l1-9H16l-2 7H9l2-7H8z" fill="currentColor" fill-opacity="0.22"/><line x1="46" y1="12" x2="58" y2="12"/><line x1="22" y1="6" x2="34" y2="6"/></svg>`,
  shotgun: `<svg viewBox="0 0 64 28" class="z-wsvg" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 15l12-4h40v4H34l-3 4H22l-4 5H6z" fill="currentColor" fill-opacity="0.22"/><rect x="33" y="15" width="14" height="4" rx="1" fill="currentColor" fill-opacity="0.45"/><line x1="56" y1="12" x2="60" y2="12"/></svg>`,
  rifle: `<svg viewBox="0 0 64 28" class="z-wsvg" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 13l12-2h34v5H38l4 9h-6l-4-9h-6l-2 7h-5l1-7H14l-10 3z" fill="currentColor" fill-opacity="0.22"/><line x1="50" y1="12" x2="61" y2="12"/><line x1="26" y1="8" x2="36" y2="8"/></svg>`,
  launcher: `<svg viewBox="0 0 64 28" class="z-wsvg" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M6 15l12-4h32v9H28l-3 5h-6l2-5h-5L6 21z" fill="currentColor" fill-opacity="0.22"/><rect x="26" y="8" width="26" height="9" rx="2" fill="currentColor" fill-opacity="0.32"/><circle cx="55" cy="12.5" r="2.5" fill="currentColor"/></svg>`,
  flamer: `<svg viewBox="0 0 64 28" class="z-wsvg" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="10" y="9" width="32" height="10" rx="3" fill="currentColor" fill-opacity="0.22"/><rect x="16" y="19" width="16" height="6" rx="2" fill="currentColor" fill-opacity="0.4"/><line x1="42" y1="13" x2="54" y2="13"/><path d="M55 9c3 2 5 4 5 5s-2 3-5 5c1-2 1-4 0-5 1-1 1-3 0-5z" fill="#fb923c" stroke="#fb923c"/></svg>`,
  tesla: `<svg viewBox="0 0 64 28" class="z-wsvg" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M6 13h20l4-4h16v10H28l-4-3h-8l-2 7H9l2-7H6z" fill="currentColor" fill-opacity="0.22"/><line x1="34" y1="7" x2="34" y2="21"/><line x1="40" y1="7" x2="40" y2="21"/><path d="M48 14l4-5 2 4 5-3-4 6-2-3-5 1z" fill="#93c5fd" stroke="#93c5fd"/></svg>`,
  railgun: `<svg viewBox="0 0 64 28" class="z-wsvg" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 12h18l4-4h34v4H34v4h26v4H26l-4-4H16l-3 8H7l2-8H4z" fill="currentColor" fill-opacity="0.22"/><line x1="28" y1="14" x2="58" y2="14" stroke="#e0f2fe" stroke-width="2.5"/></svg>`,
};

function makeWeaponIcon(wid, color) {
  const wrap = h('span', { class: 'z-wicon-wrap', style: { color: color || '#e2e8f0' } });
  wrap.innerHTML = WEAPON_SVG_MARKUP[wid] || WEAPON_SVG_MARKUP.pistol;
  return wrap;
}

function lerpAngle(a, b, f) {
  const diff = ((b - a + Math.PI * 3) % (Math.PI * 2)) - Math.PI;
  return a + diff * f;
}

function clamp(v, lo, hi) {
  return v < lo ? lo : (v > hi ? hi : v);
}

function resolveCircleObsClient(x, y, r, obs, aw, ah) {
  x = clamp(x, r + 10, aw - r - 10);
  y = clamp(y, r + 10, ah - r - 10);
  for (let i = 0; i < obs.length; i++) {
    const ob = obs[i];
    const cx = clamp(x, ob.x, ob.x + ob.w);
    const cy = clamp(y, ob.y, ob.y + ob.h);
    const dx = x - cx;
    const dy = y - cy;
    const d2 = dx * dx + dy * dy;
    if (d2 < r * r) {
      if (d2 > 1e-6) {
        const d = Math.sqrt(d2);
        const push = r - d;
        x += (dx / d) * push;
        y += (dy / d) * push;
      }
    }
  }
  return [clamp(x, r + 10, aw - r - 10), clamp(y, r + 10, ah - r - 10)];
}

/* ------------------------------------------- WebAudio Procedural SFX ----- */
let audioCtx = null;
function getAudio() {
  if (!soundEnabled()) return null;
  if (!audioCtx && typeof window !== 'undefined') {
    const AC = window.AudioContext || window.webkitAudioContext;
    if (AC) audioCtx = new AC();
  }
  if (audioCtx && audioCtx.state === 'suspended') audioCtx.resume().catch(() => {});
  return audioCtx;
}

function playGunSfx(weapon, gainScale = 1.0) {
  const scale = clamp(Number.isFinite(gainScale) ? gainScale : 1.0, 0, 1);
  if (scale < 0.03) return;
  const ctx = getAudio();
  if (!ctx) return;
  const now = ctx.currentTime;
  try {
    if (weapon === 'railgun' || weapon === 'tesla') {
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.type = 'sawtooth';
      osc.frequency.setValueAtTime(weapon === 'tesla' ? 1280 : 920, now);
      osc.frequency.exponentialRampToValueAtTime(weapon === 'tesla' ? 220 : 110, now + 0.2);
      gain.gain.setValueAtTime(Math.max(0.002, 0.12 * scale), now);
      gain.gain.exponentialRampToValueAtTime(0.001, now + 0.22);
      osc.connect(gain).connect(ctx.destination);
      osc.start(now);
      osc.stop(now + 0.23);
      return;
    }
    if (weapon === 'launcher') {
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.type = 'triangle';
      osc.frequency.setValueAtTime(220, now);
      osc.frequency.exponentialRampToValueAtTime(55, now + 0.18);
      gain.gain.setValueAtTime(Math.max(0.002, 0.18 * scale), now);
      gain.gain.exponentialRampToValueAtTime(0.001, now + 0.19);
      osc.connect(gain).connect(ctx.destination);
      osc.start(now);
      osc.stop(now + 0.2);
      return;
    }
    const dur = weapon === 'shotgun' ? 0.15 : weapon === 'rifle' ? 0.095 : 0.065;
    const buf = ctx.createBuffer(1, Math.floor(ctx.sampleRate * dur), ctx.sampleRate);
    const data = buf.getChannelData(0);
    for (let i = 0; i < data.length; i++) data[i] = (Math.random() * 2 - 1) * Math.pow(1 - i / data.length, 1.6);
    const src = ctx.createBufferSource();
    src.buffer = buf;
    const flt = ctx.createBiquadFilter();
    flt.type = weapon === 'flamer' ? 'bandpass' : 'lowpass';
    flt.frequency.value = weapon === 'shotgun' ? 900 : weapon === 'flamer' ? 500 : weapon === 'smg' ? 2200 : weapon === 'turret' ? 2600 : 1500;
    const gain = ctx.createGain();
    const vol = (weapon === 'shotgun' ? 0.16 : weapon === 'turret' ? 0.045 : 0.095) * scale;
    gain.gain.setValueAtTime(Math.max(0.002, vol), now);
    gain.gain.exponentialRampToValueAtTime(0.001, now + dur);
    src.connect(flt).connect(gain).connect(ctx.destination);
    src.start(now);
  } catch (_) {}
}

function playBoomSfx(gainScale = 1.0) {
  const scale = clamp(Number.isFinite(gainScale) ? gainScale : 1.0, 0, 1);
  if (scale < 0.03) return;
  const ctx = getAudio();
  if (!ctx) return;
  const now = ctx.currentTime;
  try {
    const dur = 0.4;
    const buf = ctx.createBuffer(1, Math.floor(ctx.sampleRate * dur), ctx.sampleRate);
    const data = buf.getChannelData(0);
    for (let i = 0; i < data.length; i++) data[i] = (Math.random() * 2 - 1) * Math.pow(1 - i / data.length, 1.4);
    const src = ctx.createBufferSource();
    src.buffer = buf;
    const flt = ctx.createBiquadFilter();
    flt.type = 'lowpass';
    flt.frequency.setValueAtTime(420, now);
    flt.frequency.exponentialRampToValueAtTime(70, now + dur);
    const gain = ctx.createGain();
    gain.gain.setValueAtTime(Math.max(0.002, 0.22 * scale), now);
    gain.gain.exponentialRampToValueAtTime(0.001, now + dur);
    src.connect(flt).connect(gain).connect(ctx.destination);
    src.start(now);
  } catch (_) {}
}

function playHurtSfx() {
  const ctx = getAudio();
  if (!ctx) return;
  const now = ctx.currentTime;
  try {
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.type = 'sawtooth';
    osc.frequency.setValueAtTime(160, now);
    osc.frequency.exponentialRampToValueAtTime(48, now + 0.14);
    gain.gain.setValueAtTime(0.16, now);
    gain.gain.exponentialRampToValueAtTime(0.001, now + 0.15);
    osc.connect(gain).connect(ctx.destination);
    osc.start(now);
    osc.stop(now + 0.16);
  } catch (_) {}
}

function playBuySfx(upgrade = false) {
  const ctx = getAudio();
  if (!ctx) return;
  const now = ctx.currentTime;
  try {
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.type = upgrade ? 'triangle' : 'sine';
    osc.frequency.setValueAtTime(upgrade ? 520 : 660, now);
    osc.frequency.exponentialRampToValueAtTime(upgrade ? 1040 : 880, now + (upgrade ? 0.18 : 0.09));
    gain.gain.setValueAtTime(0.11, now);
    gain.gain.exponentialRampToValueAtTime(0.001, now + (upgrade ? 0.2 : 0.1));
    osc.connect(gain).connect(ctx.destination);
    osc.start(now);
    osc.stop(now + 0.22);
  } catch (_) {}
}

/* ------------------------------------------- Offscreen Arena Floor Cache -- */
function buildFloorCanvas(mode, w, h) {
  const c = document.createElement('canvas');
  c.width = w;
  c.height = h;
  const g = c.getContext('2d');

  const themes = {
    outpost: { bg: '#10161e', grid: 'rgba(148,163,184,0.075)', accent: 'rgba(250,204,21,0.16)', border: 'rgba(250,204,21,0.28)' },
    lab: { bg: '#09141d', grid: 'rgba(34,211,238,0.085)', accent: 'rgba(34,211,238,0.18)', border: 'rgba(34,211,238,0.32)' },
    metro: { bg: '#121318', grid: 'rgba(148,163,184,0.06)', accent: 'rgba(251,146,60,0.16)', border: 'rgba(251,146,60,0.28)' },
    dock: { bg: '#0c1620', grid: 'rgba(56,189,248,0.075)', accent: 'rgba(56,189,248,0.16)', border: 'rgba(56,189,248,0.28)' },
    reactor: { bg: '#130e17', grid: 'rgba(168,85,247,0.08)', accent: 'rgba(244,63,94,0.18)', border: 'rgba(244,63,94,0.32)' },
    endless: { bg: '#170b0f', grid: 'rgba(244,63,94,0.075)', accent: 'rgba(239,68,68,0.18)', border: 'rgba(239,68,68,0.3)' },
  };
  const th = themes[mode] || themes.outpost;
  g.fillStyle = th.bg;
  g.fillRect(0, 0, w, h);

  // Lưới sàn chiến thuật
  const tile = 70;
  g.strokeStyle = th.grid;
  g.lineWidth = 1;
  for (let x = 0; x <= w; x += tile) {
    g.beginPath(); g.moveTo(x, 0); g.lineTo(x, h); g.stroke();
  }
  for (let y = 0; y <= h; y += tile) {
    g.beginPath(); g.moveTo(0, y); g.lineTo(w, y); g.stroke();
  }

  // Chi tiết đặc trưng từng bản đồ
  if (mode === 'metro') {
    // 2 tuyến đường ray tàu điện ngầm chạy ngang trên và dưới
    for (const ry of [212, 686]) {
      g.fillStyle = 'rgba(0,0,0,0.38)';
      g.fillRect(20, ry - 32, w - 40, 64);
      g.fillStyle = 'rgba(100,116,139,0.28)';
      for (let rx = 30; rx < w - 30; rx += 26) g.fillRect(rx, ry - 26, 8, 52);
      g.strokeStyle = 'rgba(203,213,225,0.35)';
      g.lineWidth = 3;
      g.beginPath();
      g.moveTo(20, ry - 16); g.lineTo(w - 20, ry - 16);
      g.moveTo(20, ry + 16); g.lineTo(w - 20, ry + 16);
      g.stroke();
    }
  } else if (mode === 'dock') {
    // Vạch sơn bốc xếp hàng hóa bến cảng
    g.strokeStyle = 'rgba(250,204,21,0.14)';
    g.lineWidth = 3;
    g.setLineDash([24, 16]);
    g.strokeRect(180, 160, w - 360, h - 320);
    g.setLineDash([]);
  } else if (mode === 'reactor') {
    // Đường ống năng lượng tỏa ra từ Lò Phản Ứng trung tâm
    g.strokeStyle = 'rgba(244,63,94,0.14)';
    g.lineWidth = 14;
    g.beginPath();
    g.moveTo(w / 2, 40); g.lineTo(w / 2, h - 40);
    g.moveTo(40, h / 2); g.lineTo(w - 40, h / 2);
    g.stroke();
  }

  // Vân nền vật liệu bê tông / thép
  let seed = mode.charCodeAt(0) * 131 + mode.length * 17;
  const rand = () => {
    seed = (seed * 1664525 + 1013904223) >>> 0;
    return seed / 4294967296;
  };
  for (let i = 0; i < 280; i++) {
    const px = rand() * w;
    const py = rand() * h;
    const r = 1 + rand() * 3.2;
    g.fillStyle = rand() > 0.5 ? 'rgba(255,255,255,0.025)' : 'rgba(0,0,0,0.22)';
    g.fillRect(px, py, r * 2, r);
  }

  // Vòng tròn sân đáp trung tâm
  const cx = w * 0.5;
  const cy = h * 0.5;
  g.save();
  g.strokeStyle = th.accent;
  g.lineWidth = 4;
  g.setLineDash([18, 12]);
  g.beginPath();
  g.arc(cx, cy, 175, 0, Math.PI * 2);
  g.stroke();
  g.setLineDash([]);
  g.lineWidth = 2;
  g.beginPath();
  g.arc(cx, cy, 245, 0, Math.PI * 2);
  g.stroke();
  g.restore();

  // Viền cảnh báo quanh chu vi bản đồ
  g.strokeStyle = th.border;
  g.lineWidth = 6;
  g.strokeRect(10, 10, w - 20, h - 20);
  return c;
}

export default {
  async mount(root, ctx, param) {
    if (!param) {
      return renderLobby(root, ctx, CHANNEL, {
        title: t('zombie.title'),
        blurb: t('zombie.blurb'),
        iconName: 'skull',
        onEnter: (code) => ctx.navigate(`${CHANNEL}/${code}`),
      });
    }

    const { net } = ctx;
    const roomCode = param.toUpperCase();
    let state = null;
    let botLevelPick = localStorage.getItem(`hub.level.${CHANNEL}`) || 'normal';
    let shopOpen = false;
    let shopTab = 'all';
    let autoShopWave = -1;
    let currentMatchId = -1;
    let lastEventSeq = 0;
    let lastTopbarKey = '';
    let lastLobbyKey = '';
    let lastShopKey = '';
    let lastBossKey = '';
    let lastWeaponsListKey = '';
    let lastSquadKey = '';
    let floorCache = { mode: '', canvas: null };

    // Live 60 FPS cooldown & blood vignette trackers
    let localDashEndMs = 0;
    let localDashTotal = 3.4;
    let localReloadEndMs = 0;
    let localReloadTotal = 1.2;
    let hurtVignette = 0;

    // Entity interpolation & visual effects state
    const lerpSurv = new Map();
    const lerpZomb = new Map();
    const lerpTurret = new Map();
    const tracers = [];
    const chains = [];
    const particles = [];
    const casings = [];
    const decals = [];
    const slashes = [];
    const floatTexts = [];
    const shockwaves = [];
    const fireballs = [];
    let shakePower = 0;
    let lastAllyGunSfxAt = 0;

    // Local input state
    const keys = new Set();
    let hasMouseMoved = false;
    let mouseScreenX = 0;
    let mouseScreenY = 0;
    let mouseWorldX = 760;
    let mouseWorldY = 450;
    let mouseDown = false;
    let touchMove = { vx: 0, vy: 0 };

    const send = (action, extra = {}) => net.send(CHANNEL, action, extra);

    function resetMatchVisuals() {
      decals.length = 0;
      particles.length = 0;
      casings.length = 0;
      tracers.length = 0;
      chains.length = 0;
      slashes.length = 0;
      floatTexts.length = 0;
      shockwaves.length = 0;
      fireballs.length = 0;
      lerpSurv.clear();
      lerpZomb.clear();
      lerpTurret.clear();
      shakePower = 0;
      hurtVignette = 0;
      autoShopWave = -1;
      shopOpen = false;
      lastShopKey = '';
      lastBossKey = '';
      lastWeaponsListKey = '';
      lastSquadKey = '';
      lastEventSeq = 0;
      lastAllyGunSfxAt = 0;
      localDashEndMs = 0;
      localReloadEndMs = 0;
      mouseDown = false;
    }

    /* -------------------------------------------------- DOM Skeleton ----- */
    const lobbyWrap = h('div', { class: 'zombie-lobby-layout' });
    const stageWrap = h('div', { class: 'zombie-stage-wrap hidden' });
    const finishWrap = h('div', { class: 'zombie-finish-wrap hidden' });
    const rootBox = h('div', { class: 'zombie-root' }, lobbyWrap, stageWrap, finishWrap);
    root.className = 'view';
    mount(root, rootBox);

    // Waiting lobby elements
    const cfgCard = h('div', { class: 'card col', style: { gap: '14px' } });
    const seatsCard = h('div', { class: 'card col', style: { gap: '10px' } });
    const infoCard = h('div', {});
    const chatLobbySlot = h('div', {});
    lobbyWrap.append(
      h('div', { class: 'col', style: { gap: '14px' } }, cfgCard),
      h('div', { class: 'col', style: { gap: '14px' } }, seatsCard, infoCard, chatLobbySlot),
    );

    // Playing stage elements
    const canvas = h('canvas', { class: 'zombie-canvas' });
    const g2d = canvas.getContext('2d');
    const hurtOverlay = h('div', { class: 'zombie-hurt-vignette' });

    /* ---------------- Persistent Zero-Allocation HUD DOM (No GC lag!) ---- */
    const hudWavePill = h('div', { class: 'z-hud-pill accent' }, '☣️ ĐỢT 1');
    const hudCountPill = h('div', { class: 'z-hud-pill danger' }, '🧟 Còn lại: 0');
    const hudKillsPill = h('div', { class: 'z-hud-pill' }, '💀 Diệt: 0');
    const hudBuffPill = h('div', { class: 'z-hud-pill warn hidden' }, '');
    const hudShopBtn = h('button', {
      type: 'button',
      class: 'xs primary',
      onclick: () => { shopOpen = !shopOpen; renderShopModal(true); },
    }, '🛒 Shop (B)');
    const hudIntermissionHint = h('div', { class: 'z-hud-pill ok hidden' }, '🏃 Tự do di chuyển nhặt đồ · [B] mở Trạm Tiếp Tế');
    const topHud = h('div', { class: 'zombie-top-hud' },
      hudWavePill, hudCountPill, hudKillsPill, hudBuffPill, hudShopBtn, hudIntermissionHint);

    const bossHud = h('div', { class: 'zombie-boss-hud hidden' });

    // Bottom HUD persistent nodes
    const hudHpTxt = h('strong', {}, '❤️ 100/100');
    const hudArmorTxt = h('span', { style: { color: '#38bdf8', fontWeight: '700' } }, '🛡️ 20/80');
    const hudStimTxt = h('span', { class: 'hidden', style: { color: '#22d3ee', fontWeight: '700' } }, '');
    const hudHpFill = h('div', { style: { width: '100%' } });
    const hudArmorFill = h('div', { style: { width: '25%' } });
    const vitalsBox = h('div', { class: 'z-hud-box z-vitals' },
      h('div', { class: 'spread tiny', style: { gap: '6px' } }, hudHpTxt, hudArmorTxt, hudStimTxt),
      h('div', { class: 'z-bar hp' }, hudHpFill),
      h('div', { class: 'z-bar armor' }, hudArmorFill));

    const hudWeaponIconSlot = h('span', { class: 'z-wicon-slot' });
    const hudWeaponName = h('strong', { class: 'z-weapon-name' }, 'Súng Lục');
    const hudAmmoTxt = h('strong', { class: 'z-ammo-txt' }, '15 / ∞');
    const hudWeaponBtns = h('div', { class: 'row', style: { gap: '4px', marginTop: '5px', flexWrap: 'wrap' } });
    const weaponsBox = h('div', { class: 'z-hud-box z-weapons' },
      h('div', { class: 'z-weapon-head tiny' },
        h('div', { class: 'row', style: { gap: '6px', alignItems: 'center', minWidth: '0', flex: '1 1 auto' } }, hudWeaponIconSlot, hudWeaponName),
        hudAmmoTxt),
      hudWeaponBtns);

    const hudMoneyChip = h('span', { class: 'chip warn', style: { fontWeight: '800', fontVariantNumeric: 'tabular-nums' } }, '💰 $180');
    const dashFillEl = h('div', { class: 'z-cd-fill', style: { width: '0%' } });
    const dashTextEl = h('span', { class: 'z-cd-text' }, '⚡ Dash [Spc]');
    const dashBtnEl = h('button', {
      type: 'button',
      class: 'z-skill-btn z-dash-btn ready',
      onclick: () => send('dash'),
    }, dashFillEl, dashTextEl);

    const grenadeTxtEl = h('span', { class: 'z-cd-text' }, '💣×2 [G]');
    const grenadeBtnEl = h('button', {
      type: 'button',
      class: 'z-skill-btn ready',
      onclick: () => throwGadget('grenade'),
    }, grenadeTxtEl);

    const cryoTxtEl = h('span', { class: 'z-cd-text' }, '❄️×1 [F]');
    const cryoBtnEl = h('button', {
      type: 'button',
      class: 'z-skill-btn ready',
      onclick: () => throwGadget('cryo'),
    }, cryoTxtEl);

    const empTxtEl = h('span', { class: 'z-cd-text' }, '🌩️×1 [Q]');
    const empBtnEl = h('button', {
      type: 'button',
      class: 'z-skill-btn ready',
      onclick: () => throwGadget('emp'),
    }, empTxtEl);

    const mineTxtEl = h('span', { class: 'z-cd-text' }, '🚨×0 [C]');
    const mineBtnEl = h('button', {
      type: 'button',
      class: 'z-skill-btn',
      onclick: () => send('mine'),
    }, mineTxtEl);

    const turretTxtEl = h('span', { class: 'z-cd-text' }, '🛰️×0 [E]');
    const turretBtnEl = h('button', {
      type: 'button',
      class: 'z-skill-btn',
      onclick: () => send('turret'),
    }, turretTxtEl);

    const tacticalBox = h('div', { class: 'z-hud-box z-tactical' },
      hudMoneyChip, dashBtnEl, grenadeBtnEl, cryoBtnEl, empBtnEl, mineBtnEl, turretBtnEl);

    const squadBox = h('div', { class: 'z-hud-box z-squad' });
    const bottomHud = h('div', { class: 'zombie-bottom-hud' }, vitalsBox, weaponsBox, tacticalBox, squadBox);

    /* ---------------- Persistent Shop Modal Container (Zero Scroll Jump!) */
    const shopTitleEl = h('h2', {}, '🛒 Trạm Tiếp Tế');
    const shopMoneyEl = h('span', { class: 'chip warn', style: { fontSize: '14px', fontWeight: '800' } }, '💰 $0');
    const shopReadyBtn = h('button', {
      type: 'button',
      class: 'sm primary hidden',
      onclick: () => {
        send('ready_shop');
        shopOpen = false;
        shopOverlay.classList.add('hidden');
      },
    }, 'Sẵn sàng ngay');
    const shopCloseBtn = h('button', {
      type: 'button',
      class: 'sm ghost',
      onclick: () => { shopOpen = false; shopOverlay.classList.add('hidden'); },
    }, 'Đóng (B)');
    const shopLockBanner = h('div', { class: 'z-shop-lock-banner hidden' }, '🔒 Trạm Tiếp Tế chỉ mở mua sắm khi đang chờ đợt tiếp theo (giữa các đợt).');
    const shopTabsBar = h('div', { class: 'z-shop-tabs' });
    const shopBodyEl = h('div', { class: 'z-shop-body col', style: { gap: '12px' } });
    const shopModalBox = h('div', { class: 'zombie-shop-modal card col', style: { gap: '10px' } },
      h('div', { class: 'spread', style: { gap: '8px', flexWrap: 'wrap' } },
        shopTitleEl,
        h('div', { class: 'row', style: { gap: '8px', alignItems: 'center', flexWrap: 'wrap' } }, shopMoneyEl, shopReadyBtn, shopCloseBtn)),
      shopLockBanner,
      shopTabsBar,
      shopBodyEl);
    const shopOverlay = h('div', { class: 'zombie-shop-overlay hidden' }, shopModalBox);

    function throwGadget(kind) {
      updateMouseWorld();
      const me = (state?.survivors || []).find((x) => x.mark === state?.you?.mark);
      const tx = hasMouseMoved ? mouseWorldX : (me ? me.x + Math.cos(me.aim || 0) * 200 : 700);
      const ty = hasMouseMoved ? mouseWorldY : (me ? me.y + Math.sin(me.aim || 0) * 200 : 450);
      send(kind, { tx, ty });
    }

    const touchControls = h('div', { class: 'zombie-touch-bar' },
      h('button', { type: 'button', class: 'z-tbtn', onclick: () => send('dash') }, '⚡ Dash'),
      h('button', { type: 'button', class: 'z-tbtn', onclick: () => throwGadget('grenade') }, '💣 Bom'),
      h('button', { type: 'button', class: 'z-tbtn', onclick: () => throwGadget('cryo') }, '❄️ Băng'),
      h('button', { type: 'button', class: 'z-tbtn', onclick: () => throwGadget('emp') }, '🌩️ EMP'),
      h('button', { type: 'button', class: 'z-tbtn', onclick: () => send('mine') }, '🚨 Mìn'),
      h('button', { type: 'button', class: 'z-tbtn', onclick: () => send('turret') }, '🛰️ Trụ'),
      h('button', { type: 'button', class: 'z-tbtn', onclick: () => { shopOpen = !shopOpen; renderShopModal(true); } }, '🛒 Shop'),
    );

    stageWrap.append(canvas, hurtOverlay, topHud, bossHud, bottomHud, touchControls, shopOverlay);

    /* ------------------------------------------- VFX Helpers ------------- */
    function addParticles(x, y, count, color, speedMin, speedMax, sizeMin, sizeMax, lifeMin, lifeMax) {
      for (let i = 0; i < count; i++) {
        const ang = Math.random() * Math.PI * 2;
        const spd = speedMin + Math.random() * (speedMax - speedMin);
        particles.push({
          x, y,
          vx: Math.cos(ang) * spd,
          vy: Math.sin(ang) * spd,
          size: sizeMin + Math.random() * (sizeMax - sizeMin),
          color,
          life: lifeMin + Math.random() * (lifeMax - lifeMin),
          maxLife: lifeMax,
        });
      }
      if (particles.length > 320) particles.splice(0, particles.length - 320);
    }

    function addCasing(x, y, aim) {
      const side = aim + Math.PI * 0.5 + (Math.random() - 0.5) * 0.6;
      const spd = 45 + Math.random() * 55;
      casings.push({
        x, y,
        vx: Math.cos(side) * spd,
        vy: Math.sin(side) * spd,
        rot: Math.random() * Math.PI * 2,
        vrot: (Math.random() - 0.5) * 18,
        life: 0.75,
      });
      if (casings.length > 60) casings.shift();
    }

    function addDecal(x, y, r, color) {
      decals.push({ x, y, r, color, alpha: 0.48, life: 16.0, maxLife: 16.0 });
      if (decals.length > 70) decals.shift();
    }

    function getListenerPos() {
      const myMark = state?.you?.mark;
      if (myMark) {
        const pos = lerpSurv.get(myMark) || (state?.survivors || []).find((s) => s.mark === myMark);
        if (pos && Number.isFinite(pos.x) && Number.isFinite(pos.y)) return pos;
      }
      const aw = state?.arena?.w || 1600;
      const ah = state?.arena?.h || 900;
      return { x: aw * 0.5, y: ah * 0.5 };
    }

    function allyGunGain(x, y) {
      if (!Number.isFinite(x) || !Number.isFinite(y)) return 0.28;
      const p = getListenerPos();
      const d = Math.hypot(x - p.x, y - p.y);
      const maxDist = 1150;
      if (d >= maxDist) return 0;
      const t = 1 - d / maxDist;
      return 0.1 + 0.48 * t * t;
    }

    function boomGain(x, y) {
      if (!Number.isFinite(x) || !Number.isFinite(y)) return 0.85;
      const p = getListenerPos();
      const d = Math.hypot(x - p.x, y - p.y);
      const t = clamp(1 - d / 1450, 0, 1);
      return 0.42 + 0.58 * t;
    }

    function playAllyGunSfx(weapon, x, y) {
      const g = allyGunGain(x, y);
      if (g <= 0) return;
      const nowMs = performance.now();
      const minGap = (weapon === 'launcher' || weapon === 'railgun' || weapon === 'shotgun') ? 32 : 52;
      if (nowMs - lastAllyGunSfxAt < minGap) return;
      lastAllyGunSfxAt = nowMs;
      playGunSfx(weapon, g);
    }

    function ingestEvents(events) {
      if (!Array.isArray(events) || !events.length) return;
      if (events[events.length - 1].seq < lastEventSeq) lastEventSeq = 0;
      for (const ev of events) {
        if (!ev || ev.seq <= lastEventSeq) continue;
        lastEventSeq = ev.seq;

        if (ev.t === 'shot') {
          const pts = ev.pts || [];
          for (const pt of pts) {
            tracers.push({
              x1: ev.x, y1: ev.y,
              x2: pt[0], y2: pt[1],
              color: ev.color || '#fde047',
              weapon: ev.weapon,
              lv: ev.lv || 1,
              life: ev.weapon === 'railgun' ? 0.24 : ev.weapon === 'flamer' ? 0.14 : 0.085,
              maxLife: ev.weapon === 'railgun' ? 0.24 : 0.10,
            });
          }
          if (ev.weapon !== 'flamer' && ev.weapon !== 'railgun' && ev.weapon !== 'turret') {
            addCasing(ev.x, ev.y, ev.aim || 0);
          }
          addParticles(ev.x, ev.y, ev.weapon === 'shotgun' ? 6 : 3, ev.color || '#fde047', 60, 180, 2, 4.5, 0.08, 0.18);
          if (ev.mark === state?.you?.mark) {
            if (ev.weapon === 'shotgun' || ev.weapon === 'launcher') shakePower = Math.max(shakePower, 6.0);
            else if (ev.weapon === 'railgun') shakePower = Math.max(shakePower, 8.5);
            else if (ev.weapon === 'rifle') shakePower = Math.max(shakePower, 2.0);
            playGunSfx(ev.weapon, 1.0);
          } else {
            playAllyGunSfx(ev.weapon, ev.x, ev.y);
          }
        } else if (ev.t === 'chain') {
          chains.push({ pts: ev.pts || [], color: ev.color || '#60a5fa', life: 0.22, maxLife: 0.22 });
          if (ev.mark === state?.you?.mark) {
            shakePower = Math.max(shakePower, 3.2);
            playGunSfx('tesla', 1.0);
          } else {
            const orig = ev.pts && ev.pts[0];
            playAllyGunSfx('tesla', orig?.[0], orig?.[1]);
          }
        } else if (ev.t === 'hurt') {
          const ang = Math.atan2(ev.y - (ev.sy ?? ev.y), ev.x - (ev.sx ?? ev.x));
          slashes.push({ x: ev.x, y: ev.y, ang, kind: ev.kind || 'melee', life: 0.28, maxLife: 0.28 });
          addParticles(ev.x, ev.y, ev.shieldDmg > 0 ? 7 : 5, ev.shieldDmg > 0 ? '#38bdf8' : '#ef4444', 55, 175, 2.5, 5, 0.18, 0.38);
          floatTexts.push({
            x: ev.x + (Math.random() * 14 - 7),
            y: ev.y - 22,
            text: `-${ev.dmg}`,
            color: '#f87171',
            big: ev.dmg >= 25,
            life: 0.72,
            maxLife: 0.72,
          });
          if (ev.mark === state?.you?.mark) {
            hurtVignette = Math.min(0.92, hurtVignette + 0.36 + Math.min(0.4, (ev.dmg || 10) / 50));
            shakePower = Math.max(shakePower, Math.min(10, 4 + (ev.dmg || 10) * 0.16));
            if (ev.kind !== 'acid') playHurtSfx();
          }
        } else if (ev.t === 'hit') {
          addParticles(ev.x, ev.y, ev.crit ? 7 : 4, ev.crit ? '#38bdf8' : '#22c55e', 45, 160, 2, 4.2, 0.15, 0.34);
          floatTexts.push({
            x: ev.x + (Math.random() * 14 - 7),
            y: ev.y - 14,
            text: ev.crit ? `-${ev.dmg}!` : `-${ev.dmg}`,
            color: ev.crit ? '#38bdf8' : '#fef08a',
            big: !!ev.crit,
            life: 0.65,
            maxLife: 0.65,
          });
        } else if (ev.t === 'kill') {
          const isBig = ev.kind === 'boss' || ev.kind === 'titan';
          const isMini = ev.kind === 'butcher' || ev.kind === 'queen';
          const blood = (ev.kind === 'bloater' || ev.kind === 'spitter' || ev.kind === 'queen')
            ? '#4ade80'
            : (isBig || ev.kind === 'butcher') ? '#f43f5e' : '#16a34a';
          addDecal(ev.x, ev.y, isBig ? 42 : isMini ? 28 : ev.kind === 'brute' ? 22 : 13, blood);
          addParticles(ev.x, ev.y, isBig ? 34 : isMini ? 20 : 12, blood, 60, 240, 3, 6.2, 0.25, 0.6);
          if (isBig || isMini) {
            shockwaves.push({ x: ev.x, y: ev.y, r: 20, maxR: isBig ? 230 : 150, color: blood, life: 0.5, maxLife: 0.5 });
            shakePower = Math.max(shakePower, isBig ? 13 : 8.5);
            playBoomSfx();
          }
        } else if (ev.t === 'boom' || ev.t === 'turret_boom') {
          const rad = ev.radius || 75;
          const isBarrel = ev.kind === 'barrel';
          addDecal(ev.x, ev.y, Math.min(48, rad * 0.34), isBarrel ? '#0f172a' : '#1e293b');
          fireballs.push({
            x: ev.x, y: ev.y,
            r: 14,
            maxR: rad * (isBarrel ? 0.92 : 0.72),
            life: isBarrel ? 0.44 : 0.32,
            maxLife: isBarrel ? 0.44 : 0.32,
            isBarrel,
          });
          addParticles(ev.x, ev.y, isBarrel ? 36 : 26, '#fb923c', 70, isBarrel ? 380 : 300, 3, isBarrel ? 8.5 : 7, 0.24, isBarrel ? 0.7 : 0.56);
          addParticles(ev.x, ev.y, isBarrel ? 20 : 12, '#fef08a', 40, 240, 2.5, 5.5, 0.16, 0.42);
          addParticles(ev.x, ev.y, isBarrel ? 18 : 8, '#334155', 25, 160, 5, 11, 0.38, 0.85);
          if (isBarrel) {
            addParticles(ev.x, ev.y, 12, '#dc2626', 110, 340, 2.5, 5.2, 0.28, 0.62);
            shockwaves.push({ x: ev.x, y: ev.y, r: 10, maxR: rad * 0.72, color: '#fef08a', life: 0.26, maxLife: 0.26 });
            floatTexts.push({ x: ev.x, y: ev.y - 24, text: '💥 BÙM!', color: '#fde047', big: true, life: 0.95, maxLife: 0.95 });
          }
          shockwaves.push({ x: ev.x, y: ev.y, r: 16, maxR: rad, color: isBarrel ? '#f97316' : '#fb923c', life: isBarrel ? 0.42 : 0.35, maxLife: isBarrel ? 0.42 : 0.35 });
          shakePower = Math.max(shakePower, isBarrel ? 14 : ev.t === 'boom' ? 11 : 6);
          playBoomSfx(boomGain(ev.x, ev.y));
        } else if (ev.t === 'barrel_hit') {
          addParticles(ev.x, ev.y, 9, '#fde047', 65, 210, 1.8, 3.8, 0.12, 0.28);
          addParticles(ev.x, ev.y, 5, '#fb923c', 40, 140, 2, 4.2, 0.15, 0.32);
        } else if (ev.t === 'cryo') {
          shockwaves.push({ x: ev.x, y: ev.y, r: 14, maxR: ev.radius || 145, color: '#38bdf8', life: 0.42, maxLife: 0.42 });
          addParticles(ev.x, ev.y, 26, '#bae6fd', 50, 210, 2.5, 6, 0.25, 0.65);
          floatTexts.push({ x: ev.x, y: ev.y - 20, text: '❄️ ĐÓNG BĂNG!', color: '#7dd3fc', big: true, life: 0.9, maxLife: 0.9 });
          playBoomSfx(boomGain(ev.x, ev.y) * 0.85);
        } else if (ev.t === 'emp') {
          shockwaves.push({ x: ev.x, y: ev.y, r: 14, maxR: ev.radius || 155, color: '#a78bfa', life: 0.4, maxLife: 0.4 });
          addParticles(ev.x, ev.y, 26, '#c4b5fd', 70, 260, 2, 5, 0.2, 0.5);
          floatTexts.push({ x: ev.x, y: ev.y - 20, text: '🌩️ CHOÁNG EMP!', color: '#c4b5fd', big: true, life: 0.95, maxLife: 0.95 });
          playGunSfx('tesla', boomGain(ev.x, ev.y));
        } else if (ev.t === 'nuke') {
          shockwaves.push({ x: ev.x, y: ev.y, r: 24, maxR: 620, color: '#fde047', life: 0.75, maxLife: 0.75 });
          shakePower = Math.max(shakePower, 16);
          playBoomSfx(1.0);
          toast('☢️ BOM HẠT NHÂN CHIẾN THUẬT ĐÃ KÍCH HOẠT!', 'ok');
        } else if (ev.t === 'turret_hit') {
          addParticles(ev.x, ev.y, 6, '#fbbf24', 50, 150, 2, 4, 0.15, 0.35);
        } else if (ev.t === 'slam' || ev.t === 'orbital') {
          const col = ev.t === 'orbital' ? '#f43f5e' : '#fb923c';
          addDecal(ev.x, ev.y, 32, '#3f121e');
          addParticles(ev.x, ev.y, 22, col, 90, 280, 3, 6.5, 0.22, 0.5);
          shockwaves.push({ x: ev.x, y: ev.y, r: 14, maxR: ev.radius || 110, color: col, life: 0.38, maxLife: 0.38 });
          shakePower = Math.max(shakePower, 9.5);
          playBoomSfx(boomGain(ev.x, ev.y));
        } else if (ev.t === 'acid') {
          shockwaves.push({ x: ev.x, y: ev.y, r: 12, maxR: ev.radius || 68, color: '#4ade80', life: 0.32, maxLife: 0.32 });
          addParticles(ev.x, ev.y, 14, '#86efac', 40, 150, 3, 5.5, 0.2, 0.45);
        } else if (ev.t === 'dash') {
          shockwaves.push({ x: ev.x, y: ev.y, r: 8, maxR: 46, color: '#38bdf8', life: 0.22, maxLife: 0.22 });
          addParticles(ev.x, ev.y, 8, '#7dd3fc', 30, 120, 2, 4, 0.15, 0.3);
        } else if (ev.t === 'upgrade') {
          shockwaves.push({ x: ev.x, y: ev.y, r: 10, maxR: 65, color: '#e879f9', life: 0.4, maxLife: 0.4 });
          floatTexts.push({ x: ev.x, y: ev.y - 26, text: `⚡ NÂNG CẤP Mk.${ev.lv}!`, color: '#e879f9', big: true, life: 1.0, maxLife: 1.0 });
          if (ev.mark === state?.you?.mark) playBuySfx(true);
        } else if (ev.t === 'stim') {
          shockwaves.push({ x: ev.x, y: ev.y, r: 8, maxR: 60, color: '#22d3ee', life: 0.35, maxLife: 0.35 });
          floatTexts.push({ x: ev.x, y: ev.y - 24, text: '💉 CUỒNG PHONG!', color: '#22d3ee', big: true, life: 0.9, maxLife: 0.9 });
        } else if (ev.t === 'revive') {
          shockwaves.push({ x: ev.x, y: ev.y, r: 10, maxR: 85, color: '#4ade80', life: 0.45, maxLife: 0.45 });
          floatTexts.push({ x: ev.x, y: ev.y - 24, text: '💚 CỨU SỐNG!', color: '#4ade80', big: true, life: 1.1, maxLife: 1.1 });
        } else if (ev.t === 'pickup') {
          const mapLbl = {
            med: ['+32 HP', '#4ade80'], ammo: ['+ĐẠN', '#38bdf8'], cash: ['+$75', '#facc15'],
            double_dmg: ['🔥 ×1.5 DMG!', '#fb923c'], inf_ammo: ['♾️ VÔ HẠN ĐẠN!', '#22d3ee'], nuke: ['☢️ NUKE!', '#fde047'],
          };
          const [lbl, col] = mapLbl[ev.kind] || ['+ITEM', '#facc15'];
          floatTexts.push({ x: ev.x, y: ev.y - 16, text: lbl, color: col, big: ev.kind.length > 4, life: 0.95, maxLife: 0.95 });
        } else if (ev.t === 'wave') {
          if (ev.boss) toast(`⚠️ ĐỢT ${ev.wave} — BOSS ${ev.bossTitle || 'CHÚA TỂ'} XUẤT HIỆN!`, 'danger');
          else if (ev.miniBoss) toast(`🔥 ĐỢT ${ev.wave} — MINI-BOSS ${ev.bossTitle || 'TINH ANH'} XUẤT HIỆN!`, 'danger');
          else toast(`☣️ Đợt ${ev.wave} bắt đầu!`, 'ok');
        }
      }
    }

    /* ------------------------------------------- Waiting Lobby UI -------- */
    function renderLobbyUi() {
      const s = state;
      if (!s || s.status !== 'waiting') return;
      const myMark = s.you?.mark || '';
      const seated = !!myMark;
      const myCls = (s.seatClasses || {})[myMark] || 'assault';
      const maxSeats = s.maxSeats || (s.seatOrder || []).length || 6;

      clear(cfgCard);
      const mkPills = (label, opts, current, onPick) => h('div', { class: 'geo-cfg-row' },
        h('span', { class: 'geo-cfg-label' }, label),
        h('div', { class: 'geo-cfg-pills' }, opts.map(([val, txt]) => h('button', {
          type: 'button',
          class: 'xs ' + (current === val ? 'primary' : 'ghost'),
          disabled: !seated,
          onclick: () => onPick(val),
        }, txt))));

      const classGrid = h('div', { class: 'zombie-class-grid' },
        CLASS_IDS.map((cid) => {
          const cm = CLASS_META[cid];
          const spec = s.catalog?.classes?.[cid] || {};
          const active = myCls === cid;
          return h('button', {
            type: 'button',
            class: 'zombie-class-card' + (active ? ' active' : ''),
            disabled: !seated,
            style: active ? { borderColor: cm.color } : {},
            onclick: () => send('class', { cls: cid }),
          },
            h('div', { class: 'row', style: { gap: '8px', alignItems: 'center' } },
              h('span', { style: { fontSize: '20px' } }, cm.icon),
              h('strong', {}, spec.label || cid)),
            h('div', { class: 'tiny muted', style: { textAlign: 'left', marginTop: '4px' } }, cm.desc));
        }));

      cfgCard.append(
        h('div', { class: 'spread' },
          h('h2', {}, '🧟 ' + t('zombie.cfgTitle')),
          h('span', { class: 'chip accent' }, modeLabel(CHANNEL, s.mode, s.label))),
        mkPills(t('zombie.cfgMap'), MAP_IDS.map((id) => [id, modeLabel(CHANNEL, id, id)]), s.mode, (v) => send('config', { mode: v })),
        mkPills(t('zombie.cfgDiff'), DIFF_IDS.map((id) => [id, t('zombie.diff.' + id)]), s.config?.difficulty || 'normal', (v) => send('config', { difficulty: v })),
        h('div', { class: 'col', style: { gap: '6px' } },
          h('span', { class: 'small muted', style: { fontWeight: '600' } }, t('zombie.chooseClass')),
          classGrid),
        h('div', { class: 'tiny muted' },
          '⌨️ WASD di chuyển · Chuột bắn · 1–8 đổi súng · R thay đạn · Space Dash · G Bom Nổ · F Bom Băng · Q Bom EMP · C Mìn · E Trụ · B Shop (giữa đợt)'),
        h('button', {
          type: 'button',
          class: 'primary',
          disabled: !seated,
          onclick: () => send('start'),
        }, `🚀 ${t('zombie.startBtn')} (${s.seatedCount || 0}/${maxSeats})`),
      );

      clear(seatsCard);
      const botSelect = seated
        ? h('select', {
            class: 'ludo-bot-lvl',
            value: botLevelPick,
            onchange: (e) => {
              botLevelPick = e.target.value;
              localStorage.setItem(`hub.level.${CHANNEL}`, botLevelPick);
            },
          },
            h('option', { value: 'easy', selected: botLevelPick === 'easy' }, '🤖 Dễ'),
            h('option', { value: 'normal', selected: botLevelPick === 'normal' }, '🤖 Thường'),
            h('option', { value: 'hard', selected: botLevelPick === 'hard' }, '🤖 Khó'))
        : null;

      seatsCard.append(
        h('div', { class: 'spread' },
          h('div', { class: 'card-title', style: { margin: '0' } }, `Đội hình (${s.seatedCount || 0}/${maxSeats})`),
          botSelect),
      );

      for (const m of (s.seatOrder || ['1', '2', '3', '4', '5', '6'])) {
        const seat = s.seats?.[m];
        const clsId = (s.seatClasses || {})[m] || 'assault';
        const cm = CLASS_META[clsId] || CLASS_META.assault;
        if (!seat) {
          seatsCard.append(h('div', { class: 'geo-seat empty' },
            h('span', { class: 'small muted grow' }, `Chiến binh ${m} (trống)`),
            !seated ? h('button', { type: 'button', class: 'xs ghost', onclick: () => send('sit') }, 'Ngồi') : null,
            seated ? h('button', {
              type: 'button',
              class: 'xs ghost',
              onclick: () => send('add_bot', { mark: m, level: botLevelPick }),
            }, '+ 🤖') : null));
          continue;
        }
        const isMe = myMark === m;
        seatsCard.append(h('div', { class: 'geo-seat' + (isMe ? ' me' : '') },
          avatar(seat, 'sm'),
          h('div', { class: 'col grow', style: { gap: '1px', minWidth: '0' } },
            h('span', { class: 'nowrap', style: { fontWeight: isMe ? '700' : '500', fontSize: '13px' } }, seat.name),
            h('span', { class: 'tiny muted' }, `${cm.icon} ${s.catalog?.classes?.[clsId]?.label || clsId}`)),
          seated && seat.bot
            ? h('button', {
                type: 'button',
                class: 'xs ghost',
                title: 'Đổi lớp cho Bot',
                onclick: () => {
                  const nextCls = CLASS_IDS[(CLASS_IDS.indexOf(clsId) + 1) % CLASS_IDS.length];
                  send('class', { mark: m, cls: nextCls });
                },
              }, '↻')
            : null,
          seated && seat.bot
            ? h('button', { type: 'button', class: 'xs ghost', onclick: () => send('remove_bot', { mark: m }) }, '✕')
            : null));
      }

      mount(infoCard, roomCard(s, CHANNEL));
      mount(chatLobbySlot, roomChat(s, net, CHANNEL));
    }

    /* ------------------------------------------- Armory Shop 3.0 --------- */
    function renderShopModal(force = false) {
      const s = state;
      if (!s || !shopOpen || s.status !== 'playing') {
        shopOverlay.classList.add('hidden');
        return;
      }
      const me = (s.survivors || []).find((x) => x.mark === s.you?.mark);
      if (!me) {
        shopOverlay.classList.add('hidden');
        return;
      }
      shopOverlay.classList.remove('hidden');

      const inShopPhase = s.phase === 'shop';
      shopTitleEl.textContent = inShopPhase
        ? `🛒 Trạm Tiếp Tế — Đợt ${s.wave + 1} sắp bắt đầu`
        : '🛒 Kho Vũ Khí (Xem trước — Chỉ mua giữa đợt)';
      shopMoneyEl.textContent = `💰 $${me.money}`;
      shopLockBanner.classList.toggle('hidden', inShopPhase);
      shopReadyBtn.classList.toggle('hidden', !inShopPhase);
      if (inShopPhase) {
        shopReadyBtn.disabled = !!me.readyShop;
        shopReadyBtn.textContent = me.readyShop ? 'Đã sẵn sàng…' : `Sẵn sàng ngay (${Math.ceil(s.shopLeft)}s)`;
      }

      const myTurretCount = (s.turrets || []).length;
      const shopKey = JSON.stringify([
        inShopPhase, shopTab, me.money, me.weapons, me.weaponLv, me.perks,
        me.grenades, me.cryos, me.emps, me.mines, me.turrets, myTurretCount,
        Math.round(me.hp), Math.round(me.armor), Math.round(me.maxArmor),
      ]);
      if (!force && shopKey === lastShopKey) return;
      lastShopKey = shopKey;

      // Lưu chính xác vị trí cuộn trước khi cập nhật nội dung để KHÔNG BAO GIỜ nhảy lên đầu trang!
      const savedScroll = shopBodyEl.scrollTop;

      clear(shopTabsBar);
      for (const [tid, label] of SHOP_TABS) {
        shopTabsBar.append(h('button', {
          type: 'button',
          class: 'xs ' + (shopTab === tid ? 'primary' : 'ghost'),
          onclick: () => {
            shopTab = tid;
            shopBodyEl.scrollTop = 0;
            renderShopModal(true);
          },
        }, label));
      }

      clear(shopBodyEl);
      const cat = s.catalog || {};
      const maxLv = cat.maxWeaponLv || 3;
      const weaponOrder = cat.weaponOrder || ['pistol', 'smg', 'shotgun', 'rifle', 'launcher', 'flamer', 'tesla', 'railgun'];

      const mkStatBar = (label, pct, color) => h('div', { class: 'z-stat-row' },
        h('span', { class: 'z-stat-lbl' }, label),
        h('div', { class: 'z-stat-track' },
          h('div', { class: 'z-stat-fill', style: { width: `${Math.max(8, Math.min(100, pct))}%`, background: color } })));

      if (shopTab === 'all' || shopTab === 'weapons') {
        const wGrid = h('div', { class: 'zombie-shop-wgrid' },
          weaponOrder.map((wid) => {
            const w = cat.weapons?.[wid];
            if (!w) return null;
            const owned = (me.weapons || []).includes(wid);
            const curLv = (me.weaponLv || {})[wid] || 1;
            const lvMult = 1 + 0.28 * (curLv - 1);
            const effDmg = Math.round(w.dmg * (w.pellets || 1) * lvMult);
            const dmgPct = (effDmg / 230) * 100;
            const ratePct = ((1 / Math.max(0.08, w.rate || 0.25)) / 11) * 100;
            const rangePct = ((w.range || 500) / 1000) * 100;

            const refillCost = Math.max(80, Math.floor((w.cost || 0) / 3));
            const upgCost = Math.round(Math.max(180, w.cost || 0) * (curLv === 1 ? 0.75 : 1.25));
            const canBuyNew = inShopPhase && !owned && me.money >= w.cost;
            const canRefill = inShopPhase && owned && wid !== 'pistol' && me.money >= refillCost;
            const canUpgrade = inShopPhase && owned && curLv < maxLv && me.money >= upgCost;

            const actions = [];
            if (!owned) {
              actions.push(h('button', {
                type: 'button',
                class: 'xs ' + (canBuyNew ? 'primary' : 'ghost'),
                disabled: !canBuyNew,
                onclick: () => { send('buy', { item: wid }); playBuySfx(false); },
              }, `Mua $${w.cost}`));
            } else {
              if (curLv < maxLv) {
                actions.push(h('button', {
                  type: 'button',
                  class: 'xs ' + (canUpgrade ? 'primary' : 'ghost'),
                  disabled: !canUpgrade,
                  onclick: () => { send('buy', { item: `upgrade:${wid}` }); playBuySfx(true); },
                }, `⬆ Mk.${curLv + 1} ($${upgCost})`));
              } else {
                actions.push(h('span', { class: 'chip ok' }, 'MAX Mk.3'));
              }
              if (wid !== 'pistol') {
                actions.push(h('button', {
                  type: 'button',
                  class: 'xs ghost',
                  disabled: !canRefill,
                  onclick: () => { send('buy', { item: wid }); playBuySfx(false); },
                }, `Nạp đạn $${refillCost}`));
              }
            }

            return h('div', { class: 'zombie-shop-wcard' + (owned ? ' owned' : '') + (me.weapon === wid ? ' equipped' : '') },
              h('div', { class: 'spread', style: { width: '100%', gap: '6px' } },
                h('strong', { style: { color: w.color, fontSize: '13px' } }, w.name),
                owned ? h('span', { class: 'z-mk-badge' + (curLv >= 3 ? ' max' : '') }, `Mk.${curLv}`) : null),
              h('div', { class: 'z-wcard-art' },
                makeWeaponIcon(wid, curLv >= 3 ? '#e879f9' : w.color),
                h('div', { class: 'z-wcard-tags' },
                  w.chain > 0 ? h('span', { class: 'tiny', style: { color: '#93c5fd' } }, `⚡ Giật ${w.chain} quái`) : null,
                  w.splash > 0 ? h('span', { class: 'tiny', style: { color: '#f43f5e' } }, '💥 Nổ lan') : null,
                  w.burn > 0 ? h('span', { class: 'tiny', style: { color: '#fb923c' } }, '🔥 Thiêu đốt') : null,
                  w.pierce > 1 ? h('span', { class: 'tiny', style: { color: '#22d3ee' } }, `⚡ Xuyên ${w.pierce}`) : null,
                  (w.pellets || 1) > 1 ? h('span', { class: 'tiny', style: { color: '#fbbf24' } }, `×${w.pellets} tia`) : null)),
              h('div', { class: 'z-wcard-stats' },
                mkStatBar('DMG', dmgPct, w.color),
                mkStatBar('TỐC', ratePct, '#38bdf8'),
                mkStatBar('TẦM', rangePct, '#4ade80')),
              h('div', { class: 'row', style: { gap: '6px', width: '100%', marginTop: '4px', flexWrap: 'wrap' } }, actions));
          }));
        shopBodyEl.append(
          h('div', { class: 'small muted', style: { fontWeight: '700' } }, '🔫 Vũ Khí & Nâng Cấp Mk.I – Mk.III'),
          wGrid);
      }

      const allItems = Object.entries(cat.items || {});
      if (shopTab === 'all' || shopTab === 'gadget') {
        const gadgets = allItems.filter(([, it]) => it.cat === 'gadget');
        shopBodyEl.append(
          h('div', { class: 'small muted', style: { fontWeight: '700' } }, '💣 Lựu Đạn Khống Chế (Băng / EMP), Mìn & Trụ Súng'),
          h('div', { class: 'zombie-shop-grid' }, gadgets.map(([iid, it]) => {
            const canBuy = inShopPhase && me.money >= it.cost;
            return h('button', {
              type: 'button',
              class: 'zombie-shop-item',
              disabled: !canBuy,
              onclick: () => { send('buy', { item: iid }); playBuySfx(false); },
            },
              h('div', { class: 'row', style: { gap: '6px', alignItems: 'center' } },
                h('span', { style: { fontSize: '16px' } }, ITEM_ICON[iid] || '🧰'),
                h('strong', { style: { fontSize: '12.5px' } }, it.name)),
              it.desc ? h('span', { class: 'tiny muted' }, it.desc) : null,
              h('span', { class: 'chip ' + (canBuy ? 'ok' : '') }, `$${it.cost}`));
          })));
      }

      if (shopTab === 'all' || shopTab === 'supply') {
        const supplies = allItems.filter(([, it]) => it.cat !== 'gadget');
        shopBodyEl.append(
          h('div', { class: 'small muted', style: { fontWeight: '700' } }, '🩹 Hồi Phục, Giáp (Shield) & Tiếp Đạn'),
          h('div', { class: 'zombie-shop-grid' }, supplies.map(([iid, it]) => {
            const shieldFull = iid === 'shield' && me.armor >= me.maxArmor - 0.5;
            const canBuy = inShopPhase && !shieldFull && me.money >= it.cost;
            return h('button', {
              type: 'button',
              class: 'zombie-shop-item' + (shieldFull ? ' owned' : ''),
              disabled: !canBuy,
              onclick: () => { send('buy', { item: iid }); playBuySfx(false); },
            },
              h('div', { class: 'row', style: { gap: '6px', alignItems: 'center' } },
                h('span', { style: { fontSize: '16px' } }, ITEM_ICON[iid] || '🧰'),
                h('strong', { style: { fontSize: '12.5px' } }, it.name)),
              it.desc ? h('span', { class: 'tiny muted' }, it.desc) : null,
              h('span', { class: 'chip ' + (canBuy ? 'ok' : '') }, shieldFull ? 'ĐẦY 100%' : `$${it.cost}`));
          })),
          h('div', { class: 'small muted', style: { fontWeight: '700' } }, '⚡ Nâng Cấp Kỹ Năng (Perks)'),
          h('div', { class: 'zombie-shop-grid' }, Object.entries(cat.perks || {}).map(([pid, pk]) => {
            const cur = (me.perks || {})[pid] || 0;
            const maxed = cur >= pk.max;
            const cost = pk.cost + cur * 110;
            const canBuy = inShopPhase && !maxed && me.money >= cost;
            return h('button', {
              type: 'button',
              class: 'zombie-shop-item' + (maxed ? ' owned' : ''),
              disabled: !canBuy,
              onclick: () => { send('buy', { item: pid }); playBuySfx(true); },
            },
              h('div', { class: 'row', style: { gap: '6px', alignItems: 'center' } },
                h('span', { style: { fontSize: '15px' } }, PERK_ICON[pid] || '⚡'),
                h('strong', { style: { fontSize: '12.5px' } }, `${pk.name} (${cur}/${pk.max})`)),
              h('span', { class: 'tiny muted' }, PERK_DESC[pid] || ''),
              h('span', { class: 'chip ' + (canBuy ? 'ok' : '') }, maxed ? 'MAX' : `$${cost}`));
          })));
      }

      // Khôi phục vị trí cuộn tức thì!
      shopBodyEl.scrollTop = savedScroll;
    }

    /* ------------------------------------------- Persistent HUD Update --- */
    function updateHud() {
      const s = state;
      if (!s || s.status !== 'playing') return;
      const me = (s.survivors || []).find((x) => x.mark === s.you?.mark);

      if (me) {
        const nowPerf = performance.now();
        localDashTotal = me.dashTotal || 3.4;
        if (me.dashReady > 0.05) {
          const targetEnd = nowPerf + me.dashReady * 1000;
          if (Math.abs(targetEnd - localDashEndMs) > 220) localDashEndMs = targetEnd;
        } else {
          localDashEndMs = 0;
        }
        if (me.reloading && me.reloadLeft > 0.05) {
          localReloadTotal = me.reloadTotal || 1.2;
          const targetRel = nowPerf + me.reloadLeft * 1000;
          if (Math.abs(targetRel - localReloadEndMs) > 220) localReloadEndMs = targetRel;
        } else {
          localReloadEndMs = 0;
        }
      }

      // 1. Top HUD text-only updates (ZERO DOM recreation!)
      const waveLabel = s.maxWaves > 0 ? `☣️ ĐỢT ${s.wave} / ${s.maxWaves}` : `☣️ ĐỢT ${s.wave}`;
      if (hudWavePill.textContent !== waveLabel) hudWavePill.textContent = waveLabel;

      const isShop = s.phase === 'shop';
      const countText = isShop ? `🛒 Tiếp tế: ${Math.ceil(s.shopLeft)}s` : `🧟 Còn lại: ${s.zombiesLeft}`;
      if (hudCountPill.textContent !== countText) hudCountPill.textContent = countText;
      hudCountPill.className = 'z-hud-pill ' + (isShop ? 'warn' : 'danger');
      hudIntermissionHint.classList.toggle('hidden', !isShop || shopOpen);
      hudShopBtn.className = 'xs ' + (isShop ? 'primary' : 'ghost');
      hudShopBtn.textContent = isShop ? '🛒 Trạm Tiếp Tế (B)' : '🔒 Shop (B)';

      const killsText = `💀 Diệt: ${s.totalKills}`;
      if (hudKillsPill.textContent !== killsText) hudKillsPill.textContent = killsText;

      const buffs = s.buffs || {};
      const buffParts = [];
      if (buffs.doubleDmg > 0) buffParts.push(`🔥 ×1.5 DMG ${Math.ceil(buffs.doubleDmg)}s`);
      if (buffs.infAmmo > 0) buffParts.push(`♾️ VÔ HẠN ĐẠN ${Math.ceil(buffs.infAmmo)}s`);
      if (buffParts.length) {
        hudBuffPill.classList.remove('hidden');
        hudBuffPill.textContent = buffParts.join(' · ');
      } else {
        hudBuffPill.classList.add('hidden');
      }

      // 2. Boss HUD (rebuilt only when boss hp/skill changes)
      const bosses = s.bosses || (s.boss ? [s.boss] : []);
      const bKey = JSON.stringify(bosses.map((b) => [b.id, Math.ceil(b.hp), b.enraged, b.skill]));
      if (bKey !== lastBossKey) {
        lastBossKey = bKey;
        if (bosses.length > 0) {
          bossHud.classList.remove('hidden');
          clear(bossHud);
          for (const b of bosses) {
            const pct = clamp((b.hp / Math.max(1, b.maxHp)) * 100, 0, 100);
            const tag = b.isMini ? '🔥 MINI-BOSS' : '☠️ BOSS CHÚA TỂ';
            bossHud.append(
              h('div', { class: 'z-boss-entry' + (b.isMini ? ' mini' : '') + (b.enraged ? ' enraged' : '') },
                h('div', { class: 'spread', style: { gap: '8px', marginBottom: '4px' } },
                  h('span', { class: 'z-boss-label', style: { margin: '0' } }, `${tag}: ${b.title || 'Đột Biến'}${b.enraged ? ' ⚡ CUỒNG BẠO' : ''}`),
                  h('span', { class: 'tiny', style: { color: '#fecdd3', fontWeight: '700' } }, `${Math.ceil(b.hp)} / ${Math.ceil(b.maxHp)}`)),
                h('div', { class: 'z-boss-bar' },
                  h('div', { class: 'z-boss-fill' + (b.isMini ? ' mini' : ''), style: { width: `${pct}%` } })),
                b.skill ? h('div', { class: 'z-boss-skill' }, `⚠️ ĐANG VẬN CHIÊU: ${b.skill}`) : null));
          }
        } else {
          bossHud.classList.add('hidden');
        }
      }

      // 3. Bottom HUD text/width updates (ZERO DOM recreation!)
      if (me) {
        vitalsBox.classList.remove('hidden');
        weaponsBox.classList.remove('hidden');
        tacticalBox.classList.remove('hidden');

        hudHpTxt.textContent = `❤️ ${Math.ceil(me.hp)}/${Math.ceil(me.maxHp)}`;
        hudArmorTxt.textContent = `🛡️ ${Math.ceil(me.armor)}/${Math.ceil(me.maxArmor)}`;
        hudHpFill.style.width = `${clamp((me.hp / Math.max(1, me.maxHp)) * 100, 0, 100)}%`;
        hudArmorFill.style.width = `${clamp((me.armor / Math.max(1, me.maxArmor)) * 100, 0, 100)}%`;
        if (me.stimLeft > 0) {
          hudStimTxt.classList.remove('hidden');
          hudStimTxt.textContent = `💉${Math.ceil(me.stimLeft)}s`;
        } else {
          hudStimTxt.classList.add('hidden');
        }

        const wInfo = s.catalog?.weapons?.[me.weapon] || {};
        const curLv = (me.weaponLv || {})[me.weapon] || 1;
        const curMag = me.mag?.[me.weapon] ?? 0;
        const curRes = me.reserve?.[me.weapon];
        hudWeaponName.textContent = `${wInfo.name || me.weapon}${curLv > 1 ? ` Mk.${curLv}` : ''}`;
        hudWeaponName.style.color = curLv >= 3 ? '#e879f9' : (wInfo.color || '#fde047');
        if (!me.reloading) {
          hudAmmoTxt.textContent = buffs.infAmmo > 0 ? '♾️ / ∞' : `${curMag} / ${curRes === -1 ? '∞' : (curRes ?? 0)}`;
          hudAmmoTxt.style.color = buffs.infAmmo > 0 ? '#22d3ee' : '#f8fafc';
        } else if (!localReloadEndMs) {
          hudAmmoTxt.textContent = '🔄 Nạp…';
          hudAmmoTxt.style.color = '#fbbf24';
        }

        const wListKey = JSON.stringify([me.weapon, me.weapons, me.weaponLv]);
        if (wListKey !== lastWeaponsListKey) {
          lastWeaponsListKey = wListKey;
          clear(hudWeaponIconSlot);
          hudWeaponIconSlot.append(makeWeaponIcon(me.weapon, curLv >= 3 ? '#e879f9' : (wInfo.color || '#fde047')));
          clear(hudWeaponBtns);
          (me.weapons || []).forEach((wid, idx) => {
            const lv = (me.weaponLv || {})[wid] || 1;
            hudWeaponBtns.append(h('button', {
              type: 'button',
              class: 'xs ' + (wid === me.weapon ? 'primary' : 'ghost'),
              onclick: () => send('switch', { weapon: wid }),
            }, `${idx + 1}:${WEAPON_SHORT[wid] || wid.toUpperCase()}${lv > 1 ? `★${lv}` : ''}`));
          });
        }

        hudMoneyChip.textContent = `💰 $${me.money}`;
        grenadeTxtEl.textContent = `💣×${me.grenades} [G]`;
        grenadeBtnEl.className = 'z-skill-btn' + (me.grenades > 0 ? ' ready' : '');
        cryoTxtEl.textContent = `❄️×${me.cryos || 0} [F]`;
        cryoBtnEl.className = 'z-skill-btn' + ((me.cryos || 0) > 0 ? ' ready cryo' : '');
        empTxtEl.textContent = `🌩️×${me.emps || 0} [Q]`;
        empBtnEl.className = 'z-skill-btn' + ((me.emps || 0) > 0 ? ' ready emp' : '');
        mineTxtEl.textContent = `🚨×${me.mines || 0} [C]`;
        mineBtnEl.className = 'z-skill-btn' + ((me.mines || 0) > 0 ? ' ready' : '');
        turretTxtEl.textContent = `🛰️×${me.turrets} [E]`;
        turretBtnEl.className = 'z-skill-btn' + (me.turrets > 0 ? ' ready' : '');
      } else {
        vitalsBox.classList.add('hidden');
        weaponsBox.classList.add('hidden');
        tacticalBox.classList.add('hidden');
      }

      // 4. Squad box (rebuilt only when squad HP/kills/status actually changes)
      const sqKey = JSON.stringify((s.survivors || []).map((sv) => [sv.mark, Math.ceil(sv.hp), sv.downed, sv.alive, Math.ceil(sv.bleedout || 0), sv.kills]));
      if (sqKey !== lastSquadKey) {
        lastSquadKey = sqKey;
        squadBox.className = 'z-hud-box z-squad' + ((s.survivors || []).length > 4 ? ' six-col' : '');
        clear(squadBox);
        for (const sv of (s.survivors || [])) {
          squadBox.append(h('div', { class: 'z-squad-row' + (sv.downed ? ' downed' : !sv.alive ? ' dead' : '') },
            h('span', { class: 'geo-dot', style: { background: sv.color } }),
            h('span', { class: 'nowrap', style: { fontSize: '11.5px', fontWeight: sv.mark === s.you?.mark ? '700' : '500', maxWidth: '86px', overflow: 'hidden', textOverflow: 'ellipsis' } }, sv.name),
            h('span', { class: 'tiny muted' }, sv.downed ? `🆘${Math.ceil(sv.bleedout)}s` : !sv.alive ? '💀' : `❤️${Math.ceil(sv.hp)}`),
            h('span', { class: 'tiny', style: { color: '#facc15', marginLeft: 'auto' } }, `💀${sv.kills}`)));
        }
      }

      if (shopOpen) renderShopModal();
    }

    /* ------------------------------------------- Finish Screen ----------- */
    function renderFinish() {
      const s = state;
      if (!s || s.status !== 'finished') return;
      clear(finishWrap);
      const myVoted = (s.rematch || []).includes(s.you?.mark);
      const sorted = [...(s.survivors || [])].sort((a, b) => b.score - a.score);
      finishWrap.append(
        h('div', { class: 'card col', style: { maxWidth: '580px', margin: '24px auto', gap: '14px' } },
          h('h2', {}, s.victory
            ? `🏆 CHIẾN THẮNG! Đã trụ vững ${s.wave} đợt tấn công!`
            : `💀 THẤT THỦ TẠI ĐỢT ${s.wave}`),
          h('div', { class: 'row-wrap', style: { gap: '8px' } },
            h('span', { class: 'chip accent' }, modeLabel(CHANNEL, s.mode, s.label)),
            h('span', { class: 'chip warn' }, `💀 Tổng tiêu diệt: ${s.totalKills}`)),
          h('div', { class: 'col', style: { gap: '8px' } },
            sorted.map((sv, i) => h('div', { class: 'geo-podium-row' + (i === 0 ? ' top' : '') },
              h('span', { class: 'geo-medal' }, ['🥇', '🥈', '🥉'][i] || `#${i + 1}`),
              h('span', { class: 'geo-dot', style: { background: sv.color } }),
              h('span', { class: 'geo-pname' }, sv.name),
              h('span', { class: 'tiny muted' }, `💀 ${sv.kills} · 💚 Cứu ${sv.revives}`),
              h('strong', { style: { color: '#facc15' } }, `${sv.score.toLocaleString()}đ`)))),
          h('div', { class: 'row', style: { gap: '10px' } },
            s.you?.mark
              ? h('button', {
                  type: 'button',
                  class: 'primary grow',
                  disabled: myVoted,
                  onclick: () => send('rematch'),
                }, myVoted ? 'Đang chờ đồng đội…' : '🔄 Chơi ván mới')
              : null,
            h('button', {
              type: 'button',
              class: 'ghost',
              onclick: () => ctx.navigate(CHANNEL),
            }, 'Về sảnh'))));
    }

    /* ------------------------------------------- 60 FPS 2.5D Engine ------ */
    let rafId = 0;
    let lastFrameAt = performance.now();

    function getTransform() {
      const aw = state?.arena?.w || 1400;
      const ah = state?.arena?.h || 900;
      const cw = canvas.width;
      const ch = canvas.height;
      const scale = Math.min(cw / aw, ch / ah);
      const ox = (cw - aw * scale) * 0.5;
      const oy = (ch - ah * scale) * 0.5;
      return { scale, ox, oy, aw, ah };
    }

    function updateMouseWorld() {
      if (!hasMouseMoved) return;
      const rect = canvas.getBoundingClientRect();
      if (!rect.width || !rect.height) return;
      const dpr = Math.min(2, window.devicePixelRatio || 1);
      const cx = (mouseScreenX - rect.left) * dpr;
      const cy = (mouseScreenY - rect.top) * dpr;
      const { scale, ox, oy } = getTransform();
      mouseWorldX = (cx - ox) / Math.max(0.01, scale);
      mouseWorldY = (cy - oy) / Math.max(0.01, scale);
    }

    function drawObstacle25D(g, ob, mode, tSec) {
      const { x, y, w, h, kind } = ob;
      const depth = kind === 'bunker' || kind === 'reactor' || kind === 'cooling_tower' ? 16 : 11;

      // Đổ bóng mềm nghiêng 2.5D
      g.fillStyle = 'rgba(0,0,0,0.45)';
      g.fillRect(x + 9, y + depth + 4, w, h);

      // Mặt tường đứng phía Nam (tạo chiều cao 3D thật)
      const wallCol = kind === 'biotank' ? '#083344'
        : kind === 'reactor' ? '#3b0718'
        : kind === 'container' ? '#1e3a5f'
        : kind === 'train_car' ? '#27272a'
        : '#151d28';
      g.fillStyle = wallCol;
      g.fillRect(x, y + h - depth, w, depth + 4);

      if (kind === 'biotank') {
        g.fillStyle = '#0f3d4c';
        g.fillRect(x, y, w, h - depth);
        g.fillStyle = '#155e75';
        g.fillRect(x + 6, y + 6, w - 12, h - depth - 12);
        // Dung dịch sinh học phát sáng & bọt khí
        g.fillStyle = `rgba(34, 211, 238, ${0.28 + 0.14 * Math.sin(tSec * 3.2 + x)})`;
        g.fillRect(x + 10, y + 10, w - 20, h - depth - 20);
        g.fillStyle = 'rgba(224,242,254,0.45)';
        const by = y + 18 + ((tSec * 28 + x) % Math.max(20, h - depth - 32));
        g.beginPath(); g.arc(x + w * 0.4, by, 4, 0, Math.PI * 2); g.arc(x + w * 0.65, by - 12, 2.5, 0, Math.PI * 2); g.fill();
        g.strokeStyle = '#22d3ee';
        g.lineWidth = 2;
        g.strokeRect(x + 1, y + 1, w - 2, h - depth - 2);
      } else if (kind === 'reactor') {
        g.fillStyle = '#2b101b';
        g.fillRect(x, y, w, h - depth);
        const cx = x + w * 0.5;
        const cy = y + (h - depth) * 0.5;
        const pulse = 0.5 + 0.35 * Math.sin(tSec * 5);
        g.fillStyle = `rgba(244,63,94,${pulse * 0.45})`;
        g.beginPath(); g.arc(cx, cy, Math.min(w, h) * 0.38, 0, Math.PI * 2); g.fill();
        g.fillStyle = '#fb7185';
        g.beginPath(); g.arc(cx, cy, Math.min(w, h) * 0.18, 0, Math.PI * 2); g.fill();
        // Cánh tua-bin xoay
        g.save();
        g.translate(cx, cy);
        g.rotate(tSec * 2.2);
        g.strokeStyle = '#fda4af';
        g.lineWidth = 3;
        g.beginPath();
        g.moveTo(-22, 0); g.lineTo(22, 0);
        g.moveTo(0, -22); g.lineTo(0, 22);
        g.stroke();
        g.restore();
        g.strokeStyle = '#fb7185';
        g.lineWidth = 2.5;
        g.strokeRect(x + 2, y + 2, w - 4, h - depth - 4);
      } else if (kind === 'cooling_tower') {
        g.fillStyle = '#1e293b';
        g.fillRect(x, y, w, h - depth);
        const cx = x + w * 0.5;
        const cy = y + (h - depth) * 0.5;
        g.fillStyle = '#0f172a';
        g.beginPath(); g.arc(cx, cy, 26, 0, Math.PI * 2); g.fill();
        g.save();
        g.translate(cx, cy);
        g.rotate(-tSec * 3.8);
        g.strokeStyle = '#64748b';
        g.lineWidth = 4;
        for (let k = 0; k < 3; k++) {
          g.rotate(Math.PI / 3);
          g.beginPath(); g.moveTo(-22, 0); g.lineTo(22, 0); g.stroke();
        }
        g.restore();
        g.strokeStyle = '#38bdf8';
        g.lineWidth = 2;
        g.strokeRect(x + 2, y + 2, w - 4, h - depth - 4);
      } else if (kind === 'train_car') {
        // Toa tàu điện ngầm 2.5D với mái thép & cửa sổ kính
        g.fillStyle = '#3f3f46';
        g.fillRect(x, y, w, h - depth);
        g.fillStyle = '#52525b';
        g.fillRect(x + 8, y + 6, w - 16, h - depth - 14);
        // Sọc cam thân tàu & cửa sổ
        g.fillStyle = '#f97316';
        g.fillRect(x + 2, y + h - depth - 5, w - 4, 4);
        g.fillStyle = '#0f172a';
        for (let wx = x + 18; wx < x + w - 26; wx += 34) {
          g.fillRect(wx, y + 12, 22, 16);
        }
        g.strokeStyle = '#a1a1aa';
        g.lineWidth = 2;
        g.strokeRect(x + 1, y + 1, w - 2, h - depth - 2);
      } else if (kind === 'container') {
        // Thùng container hàng hải có gân thép sóng
        const isBlue = (x + y) % 2 === 0;
        g.fillStyle = isBlue ? '#1d4ed8' : '#991b1b';
        g.fillRect(x, y, w, h - depth);
        g.fillStyle = isBlue ? '#2563eb' : '#b91c1c';
        g.fillRect(x + 4, y + 4, w - 8, h - depth - 8);
        g.strokeStyle = 'rgba(0,0,0,0.3)';
        g.lineWidth = 2;
        for (let rx = x + 14; rx < x + w - 10; rx += 14) {
          g.beginPath(); g.moveTo(rx, y + 4); g.lineTo(rx, y + h - depth - 4); g.stroke();
        }
        g.strokeStyle = 'rgba(255,255,255,0.28)';
        g.lineWidth = 1.5;
        g.strokeRect(x + 1, y + 1, w - 2, h - depth - 2);
      } else if (kind === 'bunker') {
        g.fillStyle = '#1e293b';
        g.fillRect(x, y, w, h - depth);
        g.fillStyle = '#334155';
        g.fillRect(x + 8, y + 8, w - 16, h - depth - 16);
        // Lỗ châu mai + Radar xoay trên mái Bunker
        g.fillStyle = '#0f172a';
        g.fillRect(x + 22, y + h - depth - 4, w - 44, 6);
        const cx = x + w * 0.5;
        const cy = y + (h - depth) * 0.5;
        g.strokeStyle = 'rgba(56,189,248,0.45)';
        g.lineWidth = 2;
        g.beginPath(); g.arc(cx, cy, 18, 0, Math.PI * 2); g.stroke();
        g.beginPath(); g.moveTo(cx, cy); g.lineTo(cx + Math.cos(tSec * 2.5) * 18, cy + Math.sin(tSec * 2.5) * 18); g.stroke();
        g.strokeStyle = '#64748b';
        g.lineWidth = 2;
        g.strokeRect(x + 1, y + 1, w - 2, h - depth - 2);
      } else {
        // Barricade / Console / Crate / Pillar 2.5D
        g.fillStyle = mode === 'lab' ? '#1e293b' : '#2a3444';
        g.fillRect(x, y, w, h - depth);
        g.fillStyle = mode === 'lab' ? '#334155' : '#3d4a5e';
        g.fillRect(x + 5, y + 5, w - 10, h - depth - 10);
        // Đèn LED nhấp nháy trên console / vạch vàng đen trên barricade
        if (kind === 'console') {
          g.fillStyle = Math.sin(tSec * 6 + x) > 0 ? '#22d3ee' : '#38bdf8';
          g.fillRect(x + 14, y + 12, 24, 6);
          g.fillStyle = '#4ade80';
          g.fillRect(x + w - 26, y + 12, 10, 6);
        }
        g.strokeStyle = mode === 'lab' ? '#38bdf8' : '#f59e0b';
        g.lineWidth = 1.6;
        g.strokeRect(x + 1, y + 1, w - 2, h - depth - 2);
      }
    }

    function drawSurvivor(g, sv, sx, sy, aimAngle, tSec, isMe, nowMs) {
      g.save();
      g.translate(sx, sy);

      if (sv.cls === 'medic' && sv.alive && !sv.downed) {
        g.strokeStyle = `rgba(74, 222, 128, ${0.14 + 0.08 * Math.sin(tSec * 4)})`;
        g.lineWidth = 2;
        g.beginPath(); g.arc(0, 0, 140, 0, Math.PI * 2); g.stroke();
      }
      if (sv.stimLeft > 0 && sv.alive && !sv.downed) {
        g.strokeStyle = `rgba(34, 211, 238, ${0.48 + 0.25 * Math.sin(tSec * 10)})`;
        g.lineWidth = 2.5;
        g.beginPath(); g.arc(0, 0, 23, 0, Math.PI * 2); g.stroke();
      }
      if (sv.downed) {
        g.fillStyle = 'rgba(239, 68, 68, 0.22)';
        g.beginPath(); g.arc(0, 0, 32 + Math.sin(tSec * 7) * 5, 0, Math.PI * 2); g.fill();
        g.strokeStyle = '#ef4444';
        g.lineWidth = 2.5;
        g.beginPath(); g.arc(0, 0, 26, 0, Math.PI * 2); g.stroke();
        if (sv.reviveProg > 0) {
          g.strokeStyle = '#4ade80';
          g.lineWidth = 5;
          g.beginPath(); g.arc(0, 0, 32, -Math.PI / 2, -Math.PI / 2 + Math.PI * 2 * sv.reviveProg); g.stroke();
        }
      }

      // Đèn pin chiến thuật (Flashlight Cone — xoay 60 FPS tức thì)
      if (sv.alive && !sv.downed) {
        g.save();
        g.rotate(aimAngle);
        const fl = g.createRadialGradient(14, 0, 6, 14, 0, 285);
        fl.addColorStop(0, 'rgba(255, 250, 220, 0.20)');
        fl.addColorStop(0.55, 'rgba(255, 245, 200, 0.065)');
        fl.addColorStop(1, 'rgba(255, 245, 200, 0)');
        g.fillStyle = fl;
        g.beginPath(); g.moveTo(10, 0); g.arc(10, 0, 285, -0.35, 0.35); g.closePath(); g.fill();
        g.restore();
      }

      // Đổ bóng chân
      g.fillStyle = 'rgba(0,0,0,0.45)';
      g.beginPath(); g.ellipse(3, 6, 17, 14, 0, 0, Math.PI * 2); g.fill();

      // Thân, ba-lô lớp nhân vật & súng chi tiết
      g.save();
      g.rotate(aimAngle);

      if (sv.dashing) {
        g.fillStyle = 'rgba(56,189,248,0.28)';
        g.beginPath(); g.arc(-6, 0, 24, 0, Math.PI * 2); g.fill();
      }

      // Ba-lô sau lưng theo lớp nhân vật
      g.fillStyle = sv.cls === 'medic' ? '#166534' : sv.cls === 'engineer' ? '#92400e' : '#1e293b';
      g.fillRect(-16, -9, 7, 18);
      if (sv.cls === 'medic') {
        g.fillStyle = '#4ade80';
        g.fillRect(-14, -2, 3, 4);
      }

      // Vai & áo giáp
      g.fillStyle = sv.downed ? '#64748b' : (sv.color || '#38bdf8');
      g.beginPath();
      g.roundRect(-11, -15, 21, 30, 8);
      g.fill();
      g.strokeStyle = isMe ? '#ffffff' : 'rgba(255,255,255,0.45)';
      g.lineWidth = isMe ? 2.2 : 1.3;
      g.stroke();

      // Hai cánh tay vươn ra cầm súng
      g.fillStyle = '#1e293b';
      g.fillRect(4, -10, 10, 5);
      g.fillRect(6, 5, 10, 5);

      // Hình dáng súng chi tiết theo loại vũ khí & cấp độ Mk.I–III
      const wid = sv.weapon || 'pistol';
      const wLv = (sv.weaponLv || {})[wid] || 1;
      const wCol = wLv >= 3 ? '#e879f9' : wid === 'railgun' ? '#22d3ee' : wid === 'tesla' ? '#60a5fa' : wid === 'flamer' ? '#f97316' : wid === 'launcher' ? '#f43f5e' : '#cbd5e1';
      g.fillStyle = wCol;
      if (wid === 'tesla') {
        g.fillRect(6, -3.5, 22, 7);
        g.fillStyle = '#93c5fd';
        g.fillRect(16, -5.5, 3, 11);
        g.fillRect(22, -5.5, 3, 11);
      } else if (wid === 'railgun') {
        g.fillRect(6, -4.5, 26, 3);
        g.fillRect(6, 1.5, 26, 3);
        g.fillStyle = '#e0f2fe';
        g.fillRect(10, -1, 20, 2);
      } else if (wid === 'shotgun' || wid === 'rifle') {
        g.fillRect(6, -3, 25, 6);
        g.fillStyle = '#0f172a';
        g.fillRect(10, -2, 8, 4);
      } else if (wid === 'flamer' || wid === 'launcher') {
        g.fillRect(6, -4.5, 23, 9);
        g.fillStyle = wid === 'launcher' ? '#fb7185' : '#fbbf24';
        g.fillRect(24, -3.5, 5, 7);
      } else {
        g.fillRect(8, -2.5, 16, 5);
      }

      // Mũ bảo hộ chiến thuật & kính Visor
      g.fillStyle = '#0f172a';
      g.beginPath(); g.arc(0, 0, 10, 0, Math.PI * 2); g.fill();
      g.fillStyle = CLASS_META[sv.cls]?.color || '#38bdf8';
      g.beginPath(); g.roundRect(4, -5.5, 5.5, 11, 2); g.fill();
      g.restore();

      // Thanh tiến trình thay đạn (60 FPS) dưới chân bản thân
      if (isMe && localReloadEndMs > nowMs) {
        const rem = Math.max(0, (localReloadEndMs - nowMs) / 1000);
        const prog = 1 - Math.min(1, rem / Math.max(0.2, localReloadTotal));
        g.fillStyle = 'rgba(0,0,0,0.75)';
        g.fillRect(-20, 22, 40, 4.5);
        g.fillStyle = '#fbbf24';
        g.fillRect(-20, 22, 40 * prog, 4.5);
      }

      // Thanh Máu & Giáp nhỏ trên đầu
      const barW = 36;
      const hpRatio = clamp(sv.hp / Math.max(1, sv.maxHp), 0, 1);
      g.fillStyle = 'rgba(0,0,0,0.68)';
      g.fillRect(-barW / 2, -29, barW, 5);
      g.fillStyle = sv.downed ? '#ef4444' : hpRatio > 0.4 ? '#4ade80' : '#f97316';
      g.fillRect(-barW / 2, -29, barW * hpRatio, 5);

      g.font = '600 11px system-ui, sans-serif';
      g.textAlign = 'center';
      g.fillStyle = '#f8fafc';
      g.fillText(sv.name, 0, -34);
      g.restore();
    }

    function drawZombie(g, z, zx, zy, facing, tSec) {
      g.save();
      g.translate(zx, zy);

      const r = z.r || 16;
      const isMajor = z.kind === 'boss' || z.kind === 'titan';
      const isMini = z.kind === 'butcher' || z.kind === 'queen';

      // Hào quang Boss / Mini-Boss / Enraged (vẽ vòng alpha nhẹ siêu mượt không dùng shadowBlur)
      if (isMajor || isMini) {
        g.fillStyle = z.kind === 'queen' ? 'rgba(52,211,153,0.18)'
          : z.kind === 'butcher' ? 'rgba(251,146,60,0.18)'
          : z.enraged ? 'rgba(244,63,94,0.28)' : 'rgba(244,63,94,0.18)';
        g.beginPath(); g.arc(0, 0, r * (z.enraged ? 1.9 : 1.6), 0, Math.PI * 2); g.fill();
      } else if (z.charging) {
        g.strokeStyle = 'rgba(248,113,113,0.85)';
        g.lineWidth = 3;
        g.beginPath(); g.arc(0, 0, r + 6, 0, Math.PI * 2); g.stroke();
      }

      // Bóng
      g.fillStyle = 'rgba(0,0,0,0.44)';
      g.beginPath(); g.ellipse(3, 6, r * 1.05, r * 0.82, 0, 0, Math.PI * 2); g.fill();

      // Thân có vai & hai cánh tay cử động theo hướng di chuyển
      g.save();
      g.rotate(facing);
      const speedMag = Math.hypot(z.vx || 0, z.vy || 0);
      const swing = z.stun ? 0 : Math.sin(tSec * (z.kind === 'runner' ? 16 : 8.5) + z.id) * (speedMag > 5 ? 4.5 : 1.2);

      const palette = {
        walker: '#4d7c0f', runner: '#dc2626', bloater: '#65a30d', spitter: '#10b981',
        brute: '#7c2d12', butcher: '#c2410c', queen: '#0d9488', boss: '#9f1239', titan: '#7f1d1d',
      };
      const baseCol = z.flash ? '#ffffff' : (z.slow ? '#38bdf8' : (palette[z.kind] || '#4d7c0f'));

      // Hai cánh tay vươn về phía trước
      g.fillStyle = baseCol;
      g.strokeStyle = 'rgba(0,0,0,0.55)';
      g.lineWidth = 1.6;
      g.beginPath();
      g.roundRect(r * 0.15 + swing, -r * 0.92, r * 0.95, r * 0.36, 4);
      g.roundRect(r * 0.15 - swing, r * 0.56, r * 0.95, r * 0.36, 4);
      g.fill();
      g.stroke();

      // Dao phay khổng lồ của Đao Đồ Tể
      if (z.kind === 'butcher') {
        g.fillStyle = '#e2e8f0';
        g.fillRect(r * 0.55 - swing, r * 0.52, 22, 9);
        g.fillStyle = '#ef4444';
        g.fillRect(r * 0.55 + 14 - swing, r * 0.52, 8, 9);
      }

      // Vai & thân chính
      g.fillStyle = baseCol;
      g.beginPath();
      g.ellipse(0, 0, r * 0.88, r * 1.02, 0, 0, Math.PI * 2);
      g.fill();
      g.strokeStyle = z.enraged ? '#fde047' : z.burn ? '#fb923c' : z.slow ? '#bae6fd' : 'rgba(0,0,0,0.65)';
      g.lineWidth = (z.enraged || z.burn || z.slow || isMajor) ? 3 : 2;
      g.stroke();

      // Đầu Zombie
      g.fillStyle = z.flash ? '#ffffff' : (z.slow ? '#7dd3fc' : baseCol);
      g.beginPath(); g.arc(r * 0.16, 0, r * 0.62, 0, Math.PI * 2); g.fill();
      g.strokeStyle = 'rgba(0,0,0,0.55)';
      g.lineWidth = 1.5;
      g.stroke();

      // Chi tiết đặc trưng (Bướu axit, lõi hạt nhân Titan, mắt phát sáng)
      if (z.kind === 'bloater' || z.kind === 'queen') {
        g.fillStyle = `rgba(163,230,53,${0.65 + 0.3 * Math.sin(tSec * 8 + z.id)})`;
        g.beginPath();
        g.arc(-r * 0.32, -r * 0.25, r * 0.24, 0, Math.PI * 2);
        g.arc(-r * 0.28, r * 0.28, r * 0.2, 0, Math.PI * 2);
        g.fill();
      } else if (z.kind === 'titan') {
        g.fillStyle = z.enraged ? '#fef08a' : '#fb7185';
        g.beginPath(); g.arc(-r * 0.12, 0, r * 0.34 + Math.sin(tSec * 9) * 2, 0, Math.PI * 2); g.fill();
      }

      // Đôi mắt phát sáng hướng về phía trước
      g.fillStyle = z.kind === 'queen' ? '#5eead4' : (isMajor || isMini || z.kind === 'brute' ? '#fde047' : (z.kind === 'runner' ? '#fef08a' : '#bef264'));
      const er = isMajor ? 4.2 : (isMini ? 3.2 : 2.3);
      g.beginPath();
      g.arc(r * 0.45, -r * 0.22, er, 0, Math.PI * 2);
      g.arc(r * 0.45, r * 0.22, er, 0, Math.PI * 2);
      g.fill();
      g.restore();

      // Hiệu ứng CHOÁNG (EMP / Tesla Stun): vòng sét zíc-zắc + biểu tượng ⚡
      if (z.stun) {
        g.strokeStyle = '#c4b5fd';
        g.lineWidth = 2.2;
        g.beginPath();
        g.arc(0, 0, r + 5, tSec * 8, tSec * 8 + Math.PI * 1.4);
        g.stroke();
        g.font = '800 12px system-ui, sans-serif';
        g.textAlign = 'center';
        g.fillStyle = '#e9d5ff';
        g.fillText('⚡', 0, -r - 14);
      }

      // Thanh máu Zombie
      if (z.hp < z.maxHp || z.kind === 'brute' || isMini || isMajor) {
        const bw = Math.max(26, r * 1.7);
        const pct = clamp(z.hp / Math.max(1, z.maxHp), 0, 1);
        g.fillStyle = 'rgba(0,0,0,0.72)';
        g.fillRect(-bw / 2, -r - 11, bw, 4.5);
        g.fillStyle = isMajor ? '#f43f5e' : isMini ? '#fb923c' : '#ef4444';
        g.fillRect(-bw / 2, -r - 11, bw * pct, 4.5);
      }
      g.restore();
    }

    function drawBarrel25D(g, b, tSec) {
      const r = b.r || 16;
      const bodyH = 15;
      const damaged = b.hp < (b.maxHp || 35) - 0.5;
      const hpRatio = clamp((b.hp ?? 35) / Math.max(1, b.maxHp || 35), 0, 1);

      g.save();
      g.translate(b.x, b.y);

      // 1. Vòng hào quang nguy hiểm nhấp nháy khi thùng phuy bị bắn rò rỉ nhiên liệu
      if (damaged) {
        const pulse = 0.25 + 0.22 * Math.abs(Math.sin(tSec * 14 + b.id));
        g.fillStyle = `rgba(251, 146, 60, ${pulse})`;
        g.beginPath(); g.arc(0, 0, r + 9, 0, Math.PI * 2); g.fill();
      }

      // 2. Bóng đổ nghiêng 2.5D trên sàn
      g.fillStyle = 'rgba(0,0,0,0.48)';
      g.beginPath();
      g.ellipse(4, bodyH * 0.55 + 4, r * 1.12, r * 0.68, 0, 0, Math.PI * 2);
      g.fill();

      // 3. Thân trụ thép hình ống 2.5D có đổ bóng kim loại (gradient trái -> sáng -> phải)
      const cylGrad = g.createLinearGradient(-r, 0, r, 0);
      cylGrad.addColorStop(0, '#5c1111');
      cylGrad.addColorStop(0.28, '#dc2626');
      cylGrad.addColorStop(0.55, '#ef4444');
      cylGrad.addColorStop(0.85, '#991b1b');
      cylGrad.addColorStop(1, '#450a0a');
      g.fillStyle = cylGrad;
      g.beginPath();
      g.moveTo(-r, -3);
      g.lineTo(-r, bodyH * 0.5);
      g.ellipse(0, bodyH * 0.5, r, r * 0.52, 0, Math.PI, 0, true);
      g.lineTo(r, -3);
      g.closePath();
      g.fill();

      // Dải sọc cảnh báo vàng-đen công nghiệp giữa thân thùng
      g.fillStyle = '#facc15';
      g.fillRect(-r + 1.5, 1.5, (r - 1.5) * 2, 4.5);
      g.fillStyle = '#18181b';
      for (let sx = -r + 3; sx < r - 3; sx += 7) {
        g.fillRect(sx, 1.5, 3, 4.5);
      }

      // Gân thép cường lực nổi quanh thân trụ
      g.strokeStyle = 'rgba(255,255,255,0.22)';
      g.lineWidth = 1.2;
      g.beginPath();
      g.ellipse(0, 7.5, r - 0.5, r * 0.44, 0, 0.15, Math.PI - 0.15);
      g.stroke();

      // Viền thân trụ dưới
      g.strokeStyle = 'rgba(15,23,42,0.75)';
      g.lineWidth = 1.4;
      g.beginPath();
      g.ellipse(0, bodyH * 0.5, r, r * 0.52, 0, 0, Math.PI);
      g.stroke();

      // 4. Nắp trên thùng phuy (vành thép nổi + lòng nắp chìm)
      const lidY = -4;
      g.fillStyle = '#7f1d1d';
      g.beginPath();
      g.ellipse(0, lidY, r, r * 0.62, 0, 0, Math.PI * 2);
      g.fill();
      g.strokeStyle = '#fca5a5';
      g.lineWidth = 1.8;
      g.stroke();

      const lidGrad = g.createRadialGradient(-4, lidY - 3, 2, 0, lidY, r * 0.85);
      lidGrad.addColorStop(0, '#ef4444');
      lidGrad.addColorStop(0.7, '#b91c1c');
      lidGrad.addColorStop(1, '#7f1d1d');
      g.fillStyle = lidGrad;
      g.beginPath();
      g.ellipse(0, lidY, r * 0.82, r * 0.5, 0, 0, Math.PI * 2);
      g.fill();

      // 2 Nắp vặn kim loại (Bung caps) trên nắp thùng
      g.fillStyle = '#cbd5e1';
      g.strokeStyle = '#334155';
      g.lineWidth = 1;
      g.beginPath(); g.arc(-r * 0.42, lidY - 1.5, 2.7, 0, Math.PI * 2); g.fill(); g.stroke();
      g.beginPath(); g.arc(r * 0.42, lidY + 1.5, 1.9, 0, Math.PI * 2); g.fill(); g.stroke();

      // Biểu tượng hình thoi cảnh báo cháy nổ sắc nét (Vector Canvas, không dùng emoji mờ)
      g.save();
      g.translate(0, lidY);
      g.fillStyle = '#facc15';
      g.strokeStyle = '#18181b';
      g.lineWidth = 1.1;
      g.beginPath();
      g.moveTo(0, -5.5);
      g.lineTo(5.5, 0);
      g.lineTo(0, 5.5);
      g.lineTo(-5.5, 0);
      g.closePath();
      g.fill();
      g.stroke();
      // Ngọn lửa nhỏ đen/đỏ ở tâm hình thoi
      g.fillStyle = '#b91c1c';
      g.beginPath();
      g.moveTo(0, -3.2);
      g.quadraticCurveTo(2.4, -0.4, 0, 2.8);
      g.quadraticCurveTo(-2.4, -0.4, 0, -3.2);
      g.fill();
      g.restore();

      // Tia lửa xì ra + thanh HP nhỏ khi thùng đã bị trúng đạn
      if (damaged) {
        const sparkR = 2.5 + 1.5 * Math.sin(tSec * 24 + b.id);
        g.fillStyle = '#fef08a';
        g.beginPath(); g.arc(-r * 0.3, lidY - 4, sparkR, 0, Math.PI * 2); g.fill();
        g.fillStyle = 'rgba(0,0,0,0.75)';
        g.fillRect(-16, lidY - 16, 32, 4);
        g.fillStyle = hpRatio > 0.4 ? '#fb923c' : '#ef4444';
        g.fillRect(-16, lidY - 16, 32 * hpRatio, 4);
      }

      g.restore();
    }

    function renderFrame(nowMs) {
      rafId = requestAnimationFrame(renderFrame);
      const dt = Math.min(0.05, Math.max(0.001, (nowMs - lastFrameAt) / 1000));
      lastFrameAt = nowMs;
      if (!state || state.status !== 'playing') return;

      // 1. Cập nhật thanh hồi chiêu Dash & đếm ngược Thay đạn 60 FPS trực tiếp (không đổi kích thước HUD!)
      if (localDashEndMs > nowMs) {
        const rem = (localDashEndMs - nowMs) / 1000;
        const pct = Math.min(100, (rem / Math.max(0.5, localDashTotal)) * 100);
        dashFillEl.style.width = `${pct.toFixed(1)}%`;
        dashTextEl.textContent = `⚡ ${rem.toFixed(1)}s`;
        dashBtnEl.className = 'z-skill-btn z-dash-btn cooling';
      } else if (dashFillEl.style.width !== '0%') {
        dashFillEl.style.width = '0%';
        dashTextEl.textContent = '⚡ Dash [Spc]';
        dashBtnEl.className = 'z-skill-btn z-dash-btn ready';
      }
      if (localReloadEndMs > nowMs) {
        const remRel = Math.max(0.1, (localReloadEndMs - nowMs) / 1000);
        const relTxt = `🔄 ${remRel.toFixed(1)}s`;
        if (hudAmmoTxt.textContent !== relTxt) {
          hudAmmoTxt.textContent = relTxt;
          hudAmmoTxt.style.color = '#fbbf24';
        }
      }

      // 2. Cập nhật Viền Máu Cảnh Báo (Blood Vignette Overlay) 60 FPS
      const me = (state.survivors || []).find((x) => x.mark === state.you?.mark);
      const lowHpPulse = (me && me.alive && !me.downed && me.hp < me.maxHp * 0.3)
        ? (0.24 + 0.14 * Math.abs(Math.sin(nowMs * 0.005)))
        : 0;
      if (hurtVignette > 0.005) hurtVignette = Math.max(0, hurtVignette - dt * 1.4);
      const vigAlpha = Math.max(hurtVignette, lowHpPulse);
      hurtOverlay.style.opacity = vigAlpha > 0.01 ? vigAlpha.toFixed(2) : '0';

      const rect = stageWrap.getBoundingClientRect();
      const dpr = Math.min(2, window.devicePixelRatio || 1);
      const targetW = Math.max(320, Math.floor(rect.width * dpr));
      const targetH = Math.max(240, Math.floor(rect.height * dpr));
      if (canvas.width !== targetW || canvas.height !== targetH) {
        canvas.width = targetW;
        canvas.height = targetH;
      }

      const { scale, ox, oy, aw, ah } = getTransform();
      if (floorCache.mode !== state.mode || !floorCache.canvas) {
        floorCache = { mode: state.mode, canvas: buildFloorCanvas(state.mode, aw, ah) };
      }

      const tSec = nowMs / 1000;
      g2d.save();
      g2d.fillStyle = '#06090e';
      g2d.fillRect(0, 0, canvas.width, canvas.height);

      let sxOff = 0;
      let syOff = 0;
      if (shakePower > 0.1) {
        sxOff = (Math.random() * 2 - 1) * shakePower;
        syOff = (Math.random() * 2 - 1) * shakePower;
        shakePower = Math.max(0, shakePower - dt * 28);
      }

      g2d.translate(ox + sxOff * dpr, oy + syOff * dpr);
      g2d.scale(scale, scale);

      // Mặt sàn
      g2d.drawImage(floorCache.canvas, 0, 0);

      // Vết máu & vết cháy nổ mờ dần
      for (let i = decals.length - 1; i >= 0; i--) {
        const d = decals[i];
        d.life -= dt;
        if (d.life <= 0) { decals.splice(i, 1); continue; }
        const fade = d.life < 4.0 ? (d.life / 4.0) : 1.0;
        g2d.globalAlpha = d.alpha * fade;
        g2d.fillStyle = d.color;
        g2d.beginPath(); g2d.arc(d.x, d.y, d.r, 0, Math.PI * 2); g2d.fill();
      }
      g2d.globalAlpha = 1;

      // Vỏ đạn đồng văng xoay trên sàn
      g2d.fillStyle = '#fbbf24';
      for (let i = casings.length - 1; i >= 0; i--) {
        const cs = casings[i];
        cs.life -= dt;
        if (cs.life <= 0) { casings.splice(i, 1); continue; }
        cs.x += cs.vx * dt;
        cs.y += cs.vy * dt;
        cs.vx *= 0.9; cs.vy *= 0.9;
        cs.rot += cs.vrot * dt;
        g2d.save();
        g2d.globalAlpha = Math.min(1, cs.life * 2);
        g2d.translate(cs.x, cs.y);
        g2d.rotate(cs.rot);
        g2d.fillRect(-2.5, -1, 5, 2);
        g2d.restore();
      }

      // Vũng Axit độc & Vùng Bão Băng Cryo trên mặt đất
      for (const hz of (state.hazards || [])) {
        const isCryo = hz.kind === 'cryo';
        g2d.fillStyle = isCryo ? 'rgba(56,189,248,0.20)' : 'rgba(34,197,94,0.28)';
        g2d.beginPath(); g2d.arc(hz.x, hz.y, hz.r, 0, Math.PI * 2); g2d.fill();
        g2d.fillStyle = isCryo ? 'rgba(186,230,253,0.18)' : 'rgba(74,222,128,0.34)';
        g2d.beginPath(); g2d.arc(hz.x, hz.y, hz.r * (0.62 + 0.08 * Math.sin(tSec * 5 + hz.id)), 0, Math.PI * 2); g2d.fill();
        g2d.strokeStyle = isCryo ? 'rgba(125,211,252,0.7)' : 'rgba(74,222,128,0.5)';
        g2d.lineWidth = 2;
        g2d.beginPath(); g2d.arc(hz.x, hz.y, hz.r, 0, Math.PI * 2); g2d.stroke();
      }

      // Vòng Cảnh Báo Chiêu Boss / Mini-Boss (Telegraphs)
      for (const tg of (state.telegraphs || [])) {
        const prog = clamp(tg.prog || 0, 0.05, 1);
        const col = tg.kind === 'orbital' ? '244, 63, 94' : '251, 146, 60';
        g2d.save();
        g2d.fillStyle = `rgba(${col}, ${0.12 + prog * 0.22})`;
        g2d.beginPath(); g2d.arc(tg.x, tg.y, tg.r, 0, Math.PI * 2); g2d.fill();
        g2d.fillStyle = `rgba(${col}, ${0.22 + prog * 0.25})`;
        g2d.beginPath(); g2d.arc(tg.x, tg.y, tg.r * prog, 0, Math.PI * 2); g2d.fill();
        g2d.strokeStyle = `rgba(${col}, 0.92)`;
        g2d.lineWidth = 2.5;
        g2d.setLineDash([10, 6]);
        g2d.beginPath(); g2d.arc(tg.x, tg.y, tg.r, 0, Math.PI * 2); g2d.stroke();
        g2d.restore();
      }

      // Mìn Từ Trường (Proximity Laser Mines)
      for (const mn of (state.mines || [])) {
        const pulse = 0.4 + 0.45 * Math.abs(Math.sin(tSec * 6 + mn.id));
        g2d.strokeStyle = `rgba(244,63,94,${pulse * 0.45})`;
        g2d.lineWidth = 1.5;
        g2d.beginPath(); g2d.arc(mn.x, mn.y, mn.r, 0, Math.PI * 2); g2d.stroke();
        g2d.fillStyle = '#334155';
        g2d.beginPath(); g2d.arc(mn.x, mn.y, 9, 0, Math.PI * 2); g2d.fill();
        g2d.fillStyle = `rgba(239,68,68,${0.55 + pulse * 0.45})`;
        g2d.beginPath(); g2d.arc(mn.x, mn.y, 3.8, 0, Math.PI * 2); g2d.fill();
      }

      // Vật phẩm tiếp tế & Power-Up toàn đội
      for (const pk of (state.pickups || [])) {
        const bob = Math.sin(tSec * 6 + pk.id) * 3;
        const pkStyle = {
          med: ['#4ade80', '+'], ammo: ['#38bdf8', '⚡'], cash: ['#facc15', '$'],
          double_dmg: ['#fb923c', '🔥'], inf_ammo: ['#22d3ee', '∞'], nuke: ['#fde047', '☢'],
        }[pk.kind] || ['#facc15', '$'];
        g2d.save();
        g2d.translate(pk.x, pk.y + bob);
        g2d.fillStyle = 'rgba(255,255,255,0.14)';
        g2d.beginPath(); g2d.arc(0, 0, 16, 0, Math.PI * 2); g2d.fill();
        g2d.fillStyle = pkStyle[0];
        g2d.beginPath(); g2d.roundRect(-10, -10, 20, 20, 5); g2d.fill();
        g2d.fillStyle = '#0f172a';
        g2d.font = '800 12px system-ui, sans-serif';
        g2d.textAlign = 'center';
        g2d.textBaseline = 'middle';
        g2d.fillText(pkStyle[1], 0, 1);
        g2d.restore();
      }

      // Chướng ngại vật / Công trình 2.5D
      const obs = state.arena?.obstacles || [];
      for (const ob of obs) drawObstacle25D(g2d, ob, state.mode, tSec);

      // Thùng Phuy Nhiên Liệu Đỏ 2.5D (Explosive Barrels)
      for (const b of (state.barrels || [])) drawBarrel25D(g2d, b, tSec);

      // Trụ súng Sentry tự động (có thanh HP + thanh Đạn!)
      const activeTurrets = new Set();
      for (const tr of (state.turrets || [])) {
        activeTurrets.add(tr.id);
        let curAim = lerpTurret.get(tr.id);
        curAim = curAim === undefined ? tr.aim : lerpAngle(curAim, tr.aim, Math.min(1, dt * 16));
        lerpTurret.set(tr.id, curAim);

        g2d.save();
        g2d.translate(tr.x, tr.y);
        g2d.strokeStyle = 'rgba(52,211,153,0.12)';
        g2d.lineWidth = 1.5;
        g2d.beginPath(); g2d.arc(0, 0, 140, 0, Math.PI * 2); g2d.stroke();
        // Chân đế 3 càng
        g2d.strokeStyle = '#64748b';
        g2d.lineWidth = 3;
        for (let k = 0; k < 3; k++) {
          const a = (Math.PI * 2 / 3) * k + 0.5;
          g2d.beginPath(); g2d.moveTo(0, 0); g2d.lineTo(Math.cos(a) * 18, Math.sin(a) * 18); g2d.stroke();
        }
        g2d.fillStyle = '#1e293b';
        g2d.beginPath(); g2d.arc(0, 0, 14, 0, Math.PI * 2); g2d.fill();
        g2d.strokeStyle = '#34d399';
        g2d.lineWidth = 2;
        g2d.stroke();
        g2d.save();
        g2d.rotate(curAim);
        g2d.fillStyle = '#34d399';
        g2d.fillRect(0, -4, 21, 3);
        g2d.fillRect(0, 1, 21, 3);
        g2d.restore();

        // Thanh HP (Xanh lá / Cam) & Thanh Đạn (Xanh lam)
        const hpR = clamp((tr.hp ?? 180) / Math.max(1, tr.maxHp || 180), 0, 1);
        const amR = clamp((tr.ammo ?? 0) / Math.max(1, tr.maxAmmo || 90), 0, 1);
        g2d.fillStyle = 'rgba(0,0,0,0.72)';
        g2d.fillRect(-18, -24, 36, 4);
        g2d.fillStyle = hpR > 0.4 ? '#4ade80' : '#f97316';
        g2d.fillRect(-18, -24, 36 * hpR, 4);
        g2d.fillStyle = 'rgba(0,0,0,0.72)';
        g2d.fillRect(-18, -19, 36, 2.5);
        g2d.fillStyle = '#38bdf8';
        g2d.fillRect(-18, -19, 36 * amR, 2.5);
        g2d.restore();
      }
      for (const id of lerpTurret.keys()) if (!activeTurrets.has(id)) lerpTurret.delete(id);

      // Nội suy Dead-Reckoning 60 FPS & vẽ Zombie có cử động
      const activeZIds = new Set();
      const zBlend = 1 - Math.exp(-dt * 16);
      for (const z of (state.zombies || [])) {
        activeZIds.add(z.id);
        let cur = lerpZomb.get(z.id);
        const targetFacing = (Math.abs(z.vx || 0) > 1 || Math.abs(z.vy || 0) > 1)
          ? Math.atan2(z.vy || 0, z.vx || 0)
          : (cur ? cur.facing : 0);
        if (!cur) {
          cur = { x: z.x, y: z.y, facing: targetFacing };
          lerpZomb.set(z.id, cur);
        } else {
          cur.x += (z.vx || 0) * dt * 0.55;
          cur.y += (z.vy || 0) * dt * 0.55;
          cur.x += (z.x - cur.x) * zBlend;
          cur.y += (z.y - cur.y) * zBlend;
          cur.facing = lerpAngle(cur.facing, targetFacing, zBlend);
        }
        drawZombie(g2d, z, cur.x, cur.y, cur.facing, tSec);
      }
      for (const id of lerpZomb.keys()) if (!activeZIds.has(id)) lerpZomb.delete(id);

      // Nội suy + Local Movement Prediction 0ms cho bản thân & vẽ Chiến binh
      const activeMarks = new Set();
      const sBlend = 1 - Math.exp(-dt * 16);
      for (const sv of (state.survivors || [])) {
        if (!sv.alive) continue;
        activeMarks.add(sv.mark);
        const isMe = sv.mark === state.you?.mark;
        let cur = lerpSurv.get(sv.mark);
        if (!cur) {
          cur = { x: sv.x, y: sv.y, aim: sv.aim };
          lerpSurv.set(sv.mark, cur);
        } else {
          if (isMe && !sv.downed && !sv.dashing) {
            // Dự đoán di chuyển 0ms trực tiếp từ phím WASD rồi hòa trộn mượt về vị trí chuẩn server
            let lvx = touchMove.vx;
            let lvy = touchMove.vy;
            if (keys.has('KeyW') || keys.has('ArrowUp')) lvy -= 1;
            if (keys.has('KeyS') || keys.has('ArrowDown')) lvy += 1;
            if (keys.has('KeyA') || keys.has('ArrowLeft')) lvx -= 1;
            if (keys.has('KeyD') || keys.has('ArrowRight')) lvx += 1;
            const mag = Math.hypot(lvx, lvy);
            if (mag > 0.01) {
              const baseSpd = (state.catalog?.classes?.[sv.cls]?.speed || 235) * (1 + 0.12 * ((sv.perks || {}).speed || 0)) * (sv.stimLeft > 0 ? 1.25 : 1);
              const [px, py] = resolveCircleObsClient(cur.x + (lvx / mag) * baseSpd * dt, cur.y + (lvy / mag) * baseSpd * dt, 17, obs, aw, ah);
              cur.x = px;
              cur.y = py;
            }
            const recon = 1 - Math.exp(-dt * 11);
            cur.x += (sv.x - cur.x) * recon;
            cur.y += (sv.y - cur.y) * recon;
          } else {
            cur.x += (sv.vx || 0) * dt * 0.55;
            cur.y += (sv.vy || 0) * dt * 0.55;
            cur.x += (sv.x - cur.x) * sBlend;
            cur.y += (sv.y - cur.y) * sBlend;
          }
          cur.aim = lerpAngle(cur.aim, sv.aim, sBlend);
        }
        const renderAim = (isMe && hasMouseMoved && !sv.downed && !shopOpen)
          ? Math.atan2(mouseWorldY - cur.y, mouseWorldX - cur.x)
          : cur.aim;
        drawSurvivor(g2d, sv, cur.x, cur.y, renderAim, tSec, isMe, nowMs);
      }
      for (const m of lerpSurv.keys()) if (!activeMarks.has(m)) lerpSurv.delete(m);

      // Đạn bay (Lựu đạn nổ/Băng/EMP, Rocket M79, Axit & Plasma)
      for (const pr of (state.projectiles || [])) {
        if (pr.kind === 'grenade' || pr.kind === 'cryo' || pr.kind === 'emp') {
          const arcLift = Math.sin(Math.min(1, pr.t || 0) * Math.PI) * 36;
          g2d.fillStyle = 'rgba(0,0,0,0.4)';
          g2d.beginPath(); g2d.ellipse(pr.x, pr.y + 4, 7, 4, 0, 0, Math.PI * 2); g2d.fill();
          g2d.fillStyle = pr.kind === 'cryo' ? '#38bdf8' : pr.kind === 'emp' ? '#a78bfa' : '#f97316';
          g2d.beginPath(); g2d.arc(pr.x, pr.y - arcLift, 6.5, 0, Math.PI * 2); g2d.fill();
        } else {
          const col = pr.kind === 'rocket' ? '#fb7185' : pr.kind === 'plasma' ? '#f43f5e' : '#4ade80';
          g2d.fillStyle = 'rgba(255,255,255,0.22)';
          g2d.beginPath(); g2d.arc(pr.x, pr.y, 10, 0, Math.PI * 2); g2d.fill();
          g2d.fillStyle = col;
          g2d.beginPath(); g2d.arc(pr.x, pr.y, 6, 0, Math.PI * 2); g2d.fill();
        }
      }

      // Tia đạn (Tracers & Railgun Beams)
      for (let i = tracers.length - 1; i >= 0; i--) {
        const tr = tracers[i];
        tr.life -= dt;
        if (tr.life <= 0) { tracers.splice(i, 1); continue; }
        const alpha = Math.max(0, tr.life / tr.maxLife);
        g2d.save();
        g2d.globalAlpha = alpha;
        if (tr.weapon === 'railgun' || tr.lv >= 3) {
          g2d.strokeStyle = tr.color;
          g2d.lineWidth = tr.weapon === 'railgun' ? 11 * alpha : 6 * alpha;
          g2d.globalAlpha = alpha * 0.35;
          g2d.beginPath(); g2d.moveTo(tr.x1, tr.y1); g2d.lineTo(tr.x2, tr.y2); g2d.stroke();
          g2d.globalAlpha = alpha;
        }
        g2d.strokeStyle = tr.color;
        g2d.lineWidth = tr.weapon === 'railgun' ? 4.5 * alpha : tr.weapon === 'flamer' ? 9 * alpha : 2.4;
        g2d.beginPath(); g2d.moveTo(tr.x1, tr.y1); g2d.lineTo(tr.x2, tr.y2); g2d.stroke();
        g2d.restore();
      }

      // Tia sét giật chuyền (Tesla Chain Lightning Arcs)
      for (let i = chains.length - 1; i >= 0; i--) {
        const ch = chains[i];
        ch.life -= dt;
        if (ch.life <= 0) { chains.splice(i, 1); continue; }
        const alpha = Math.max(0, ch.life / ch.maxLife);
        if (ch.pts.length >= 2) {
          g2d.save();
          g2d.globalAlpha = alpha;
          g2d.strokeStyle = '#93c5fd';
          g2d.lineWidth = 3.2;
          g2d.beginPath();
          g2d.moveTo(ch.pts[0][0], ch.pts[0][1]);
          for (let k = 1; k < ch.pts.length; k++) {
            const p0 = ch.pts[k - 1];
            const p1 = ch.pts[k];
            const mx = (p0[0] + p1[0]) * 0.5 + (Math.random() - 0.5) * 22;
            const my = (p0[1] + p1[1]) * 0.5 + (Math.random() - 0.5) * 22;
            g2d.lineTo(mx, my);
            g2d.lineTo(p1[0], p1[1]);
          }
          g2d.stroke();
          g2d.restore();
        }
      }

      // Vết cào đỏ khi Zombie đánh trúng Chiến binh (Claw Slash VFX)
      for (let i = slashes.length - 1; i >= 0; i--) {
        const sl = slashes[i];
        sl.life -= dt;
        if (sl.life <= 0) { slashes.splice(i, 1); continue; }
        const alpha = Math.max(0, sl.life / sl.maxLife);
        g2d.save();
        g2d.translate(sl.x, sl.y);
        g2d.rotate(sl.ang);
        g2d.globalAlpha = alpha;
        g2d.strokeStyle = '#ef4444';
        g2d.lineWidth = 3;
        for (const off of [-8, 0, 8]) {
          g2d.beginPath();
          g2d.arc(0, off, 20, -0.75, 0.75);
          g2d.stroke();
        }
        g2d.restore();
      }

      // Quả cầu lửa nổ (Fireball Glow — Thùng phuy, Lựu đạn, Rocket M79)
      for (let i = fireballs.length - 1; i >= 0; i--) {
        const fb = fireballs[i];
        fb.life -= dt;
        if (fb.life <= 0) { fireballs.splice(i, 1); continue; }
        const prog = 1 - fb.life / fb.maxLife;
        const rad = fb.r + (fb.maxR - fb.r) * Math.pow(prog, 0.52);
        const alpha = Math.max(0, 1 - Math.pow(prog, 1.35));
        g2d.save();
        g2d.globalAlpha = alpha;
        const grad = g2d.createRadialGradient(fb.x, fb.y, rad * 0.08, fb.x, fb.y, rad);
        grad.addColorStop(0, '#ffffff');
        grad.addColorStop(0.28, '#fef08a');
        grad.addColorStop(0.62, 'rgba(249, 115, 22, 0.85)');
        grad.addColorStop(0.86, 'rgba(220, 38, 38, 0.42)');
        grad.addColorStop(1, 'rgba(15, 23, 42, 0)');
        g2d.fillStyle = grad;
        g2d.beginPath(); g2d.arc(fb.x, fb.y, rad, 0, Math.PI * 2); g2d.fill();
        g2d.restore();
      }

      // Sóng xung kích (Shockwaves) & Hạt nổ (Particles)
      for (let i = shockwaves.length - 1; i >= 0; i--) {
        const sw = shockwaves[i];
        sw.life -= dt;
        if (sw.life <= 0) { shockwaves.splice(i, 1); continue; }
        const prog = 1 - sw.life / sw.maxLife;
        const rad = sw.r + (sw.maxR - sw.r) * prog;
        g2d.save();
        g2d.globalAlpha = (1 - prog) * 0.8;
        g2d.strokeStyle = sw.color;
        g2d.lineWidth = 5 * (1 - prog);
        g2d.beginPath(); g2d.arc(sw.x, sw.y, rad, 0, Math.PI * 2); g2d.stroke();
        g2d.restore();
      }

      for (let i = particles.length - 1; i >= 0; i--) {
        const pt = particles[i];
        pt.life -= dt;
        if (pt.life <= 0) { particles.splice(i, 1); continue; }
        pt.x += pt.vx * dt;
        pt.y += pt.vy * dt;
        pt.vx *= 0.92; pt.vy *= 0.92;
        g2d.globalAlpha = Math.max(0, pt.life / pt.maxLife);
        g2d.fillStyle = pt.color;
        g2d.beginPath(); g2d.arc(pt.x, pt.y, pt.size, 0, Math.PI * 2); g2d.fill();
      }
      g2d.globalAlpha = 1;

      // Chữ sát thương bay lên
      for (let i = floatTexts.length - 1; i >= 0; i--) {
        const ft = floatTexts[i];
        ft.life -= dt;
        if (ft.life <= 0) { floatTexts.splice(i, 1); continue; }
        ft.y -= dt * 36;
        g2d.save();
        g2d.globalAlpha = Math.min(1, (ft.life / ft.maxLife) * 1.4);
        g2d.font = ft.big ? '800 15px system-ui, sans-serif' : '700 12px system-ui, sans-serif';
        g2d.textAlign = 'center';
        g2d.fillStyle = '#000000';
        g2d.fillText(ft.text, ft.x + 1, ft.y + 1);
        g2d.fillStyle = ft.color;
        g2d.fillText(ft.text, ft.x, ft.y);
        g2d.restore();
      }

      // Đèn cảnh báo đỏ 4 góc khi có Boss / Mini-Boss
      if ((state.bosses || []).length > 0 || state.boss) {
        const alarmAlpha = 0.12 + 0.10 * Math.abs(Math.sin(tSec * 4.5));
        g2d.fillStyle = `rgba(239, 68, 68, ${alarmAlpha})`;
        for (const [bx, by] of [[40, 40], [aw - 40, 40], [40, ah - 40], [aw - 40, ah - 40]]) {
          g2d.beginPath(); g2d.arc(bx, by, 90, 0, Math.PI * 2); g2d.fill();
        }
      }

      // Tâm ngắm chiến thuật
      if (!shopOpen && state.you?.mark && hasMouseMoved) {
        g2d.save();
        g2d.translate(mouseWorldX, mouseWorldY);
        g2d.strokeStyle = mouseDown ? '#fb923c' : '#38bdf8';
        g2d.lineWidth = 1.8;
        g2d.beginPath();
        g2d.arc(0, 0, mouseDown ? 12 : 9, 0, Math.PI * 2);
        g2d.moveTo(-16, 0); g2d.lineTo(-6, 0);
        g2d.moveTo(6, 0); g2d.lineTo(16, 0);
        g2d.moveTo(0, -16); g2d.lineTo(0, -6);
        g2d.moveTo(0, 6); g2d.lineTo(0, 16);
        g2d.stroke();
        g2d.restore();
      }

      g2d.restore();
    }

    rafId = requestAnimationFrame(renderFrame);

    /* ------------------------------------------- Input Loop (15 Hz) ------ */
    // Cho phép gửi WASD liên tục ở cả pha wave VÀ pha shop (khi đang đợi wave sau!)
    const inputTimer = setInterval(() => {
      if (!state || state.status !== 'playing' || !state.you?.mark) return;
      const me = (state.survivors || []).find((x) => x.mark === state.you.mark);
      if (!me || !me.alive || me.downed) return;
      let vx = touchMove.vx;
      let vy = touchMove.vy;
      if (keys.has('KeyW') || keys.has('ArrowUp')) vy -= 1;
      if (keys.has('KeyS') || keys.has('ArrowDown')) vy += 1;
      if (keys.has('KeyA') || keys.has('ArrowLeft')) vx -= 1;
      if (keys.has('KeyD') || keys.has('ArrowRight')) vx += 1;
      updateMouseWorld();
      const curPos = lerpSurv.get(me.mark) || me;
      const aim = hasMouseMoved ? Math.atan2(mouseWorldY - curPos.y, mouseWorldX - curPos.x) : (me.aim || 0);
      send('input', {
        vx: clamp(vx, -1, 1),
        vy: clamp(vy, -1, 1),
        aim: +aim.toFixed(3),
        firing: !shopOpen && state.phase === 'wave' && mouseDown,
      });
    }, 66);

    const onKeyDown = (e) => {
      const tag = (document.activeElement?.tagName || '').toLowerCase();
      if (tag === 'input' || tag === 'textarea' || tag === 'select') return;
      keys.add(e.code);
      if (!state || state.status !== 'playing' || !state.you?.mark) return;
      if (e.code === 'KeyB') {
        e.preventDefault();
        shopOpen = !shopOpen;
        if (shopOpen) mouseDown = false;
        renderShopModal(true);
        return;
      }
      if (shopOpen) {
        if (e.code === 'Escape') {
          shopOpen = false;
          shopOverlay.classList.add('hidden');
        }
        return;
      }
      if (e.code === 'Space' || e.code === 'ShiftLeft') {
        e.preventDefault();
        send('dash');
      } else if (e.code === 'KeyR') {
        send('reload');
      } else if (e.code === 'KeyG') {
        throwGadget('grenade');
      } else if (e.code === 'KeyF') {
        throwGadget('cryo');
      } else if (e.code === 'KeyQ') {
        throwGadget('emp');
      } else if (e.code === 'KeyC') {
        send('mine');
      } else if (e.code === 'KeyE') {
        send('turret');
      } else if (e.code.startsWith('Digit')) {
        const idx = Number(e.code.slice(5)) - 1;
        const me = (state.survivors || []).find((x) => x.mark === state.you.mark);
        if (me && me.weapons?.[idx]) send('switch', { weapon: me.weapons[idx] });
      }
    };
    const onKeyUp = (e) => { keys.delete(e.code); };
    const onMouseMove = (e) => {
      hasMouseMoved = true;
      mouseScreenX = e.clientX;
      mouseScreenY = e.clientY;
      updateMouseWorld();
    };
    const onMouseDown = (e) => {
      if (shopOpen) return;
      hasMouseMoved = true;
      mouseScreenX = e.clientX;
      mouseScreenY = e.clientY;
      updateMouseWorld();
      if (e.button === 2) {
        e.preventDefault();
        throwGadget('grenade');
        return;
      }
      if (e.button === 0) {
        mouseDown = true;
        const me = (state?.survivors || []).find((x) => x.mark === state?.you?.mark);
        if (me && state?.phase === 'wave') {
          const curPos = lerpSurv.get(me.mark) || me;
          send('shoot', { aim: +Math.atan2(mouseWorldY - curPos.y, mouseWorldX - curPos.x).toFixed(3) });
        }
      }
    };
    const onMouseUp = () => { mouseDown = false; };
    const onContext = (e) => { e.preventDefault(); };

    // Z6: Nhả toàn bộ phím/chuột/cảm ứng khi Alt-Tab hoặc chuyển tab để không bị kẹt di chuyển/bắn
    let moveTouchId = null;
    let moveOriginX = 0;
    let moveOriginY = 0;
    let aimTouchId = null;
    const releaseInputs = () => {
      keys.clear();
      mouseDown = false;
      touchMove.vx = 0;
      touchMove.vy = 0;
      moveTouchId = null;
      aimTouchId = null;
      if (state && state.status === 'playing' && state.you?.mark) {
        const me = (state.survivors || []).find((x) => x.mark === state.you.mark);
        if (me && me.alive && !me.downed) {
          send('input', { vx: 0, vy: 0, aim: +(me.aim || 0).toFixed(3), firing: false });
        }
      }
    };
    const onVisibilityChange = () => {
      if (document.hidden) releaseInputs();
    };

    // Z10: Twin-stick cảm ứng (nửa trái màn hình di chuyển, nửa phải ngắm & khai hỏa)
    const onTouchStart = (e) => {
      if (shopOpen) return;
      e.preventDefault();
      const rect = canvas.getBoundingClientRect();
      const midX = rect.left + rect.width * 0.5;
      for (const tc of Array.from(e.changedTouches)) {
        if (tc.clientX < midX && moveTouchId === null) {
          moveTouchId = tc.identifier;
          moveOriginX = tc.clientX;
          moveOriginY = tc.clientY;
          touchMove.vx = 0;
          touchMove.vy = 0;
        } else if (aimTouchId === null) {
          aimTouchId = tc.identifier;
          hasMouseMoved = true;
          mouseScreenX = tc.clientX;
          mouseScreenY = tc.clientY;
          updateMouseWorld();
          mouseDown = true;
        }
      }
    };
    const onTouchMove = (e) => {
      if (shopOpen) return;
      e.preventDefault();
      for (const tc of Array.from(e.changedTouches)) {
        if (tc.identifier === moveTouchId) {
          const dx = tc.clientX - moveOriginX;
          const dy = tc.clientY - moveOriginY;
          const dist = Math.hypot(dx, dy);
          if (dist > 8) {
            const scale = Math.min(1, dist / 48);
            touchMove.vx = (dx / dist) * scale;
            touchMove.vy = (dy / dist) * scale;
          } else {
            touchMove.vx = 0;
            touchMove.vy = 0;
          }
        } else if (tc.identifier === aimTouchId) {
          hasMouseMoved = true;
          mouseScreenX = tc.clientX;
          mouseScreenY = tc.clientY;
          updateMouseWorld();
        }
      }
    };
    const onTouchEnd = (e) => {
      for (const tc of Array.from(e.changedTouches)) {
        if (tc.identifier === moveTouchId) {
          moveTouchId = null;
          touchMove.vx = 0;
          touchMove.vy = 0;
        } else if (tc.identifier === aimTouchId) {
          aimTouchId = null;
          mouseDown = false;
        }
      }
    };

    window.addEventListener('keydown', onKeyDown);
    window.addEventListener('keyup', onKeyUp);
    window.addEventListener('blur', releaseInputs);
    document.addEventListener('visibilitychange', onVisibilityChange);
    canvas.addEventListener('mousemove', onMouseMove);
    canvas.addEventListener('mousedown', onMouseDown);
    window.addEventListener('mouseup', onMouseUp);
    canvas.addEventListener('contextmenu', onContext);
    canvas.addEventListener('touchstart', onTouchStart, { passive: false });
    canvas.addEventListener('touchmove', onTouchMove, { passive: false });
    canvas.addEventListener('touchend', onTouchEnd);
    canvas.addEventListener('touchcancel', onTouchEnd);

    /* ------------------------------------------- State Sync -------------- */
    function renderState() {
      if (!state) return;
      const tbKey = `${state.code || ''}|${t('zombie.title')}`;
      if (tbKey !== lastTopbarKey) {
        lastTopbarKey = tbKey;
        ctx.setTopbar(...roomTopbar(ctx, state, CHANNEL, t('zombie.title')));
      }

      if (typeof state.matchId === 'number' && state.matchId !== currentMatchId) {
        currentMatchId = state.matchId;
        resetMatchVisuals();
      }

      lobbyWrap.classList.toggle('hidden', state.status !== 'waiting');
      stageWrap.classList.toggle('hidden', state.status !== 'playing');
      finishWrap.classList.toggle('hidden', state.status !== 'finished');

      if (state.status === 'waiting') {
        shopOpen = false;
        const key = JSON.stringify([state.mode, state.config, state.seats, state.seatClasses, state.chat?.length]);
        if (key !== lastLobbyKey) {
          lastLobbyKey = key;
          renderLobbyUi();
        }
        return;
      }

      if (state.status === 'finished') {
        shopOpen = false;
        mouseDown = false;
        hurtOverlay.style.opacity = '0';
        renderFinish();
        return;
      }

      if (state.phase === 'shop' && autoShopWave !== state.wave) {
        autoShopWave = state.wave;
        shopOpen = true;
        mouseDown = false;
        renderShopModal(true);
      } else if (state.phase === 'wave' && autoShopWave === state.wave - 1 && shopOpen) {
        shopOpen = false;
        shopOverlay.classList.add('hidden');
      }

      ingestEvents(state.events);
      updateHud();
    }

    const stopNet = net.on(CHANNEL, (msg) => {
      if (msg.t === 'state') {
        // Giữ lại các trường tĩnh (catalog, arena, seats, chat...) khi server gửi delta frame 15 Hz
        if (state) {
          if (!msg.catalog && state.catalog) msg.catalog = state.catalog;
          if (!msg.arena && state.arena) msg.arena = state.arena;
          if (!msg.chat && state.chat) msg.chat = state.chat;
          if (!msg.seats && state.seats) msg.seats = state.seats;
          if (!msg.seatLabels && state.seatLabels) msg.seatLabels = state.seatLabels;
          if (!msg.seatOrder && state.seatOrder) msg.seatOrder = state.seatOrder;
        }
        state = msg;
        renderState();
      } else if (msg.t === 'error') {
        if (msg.message) toast(msg.message, 'danger');
      } else if (msg.t === 'closed') {
        toast(msg.message || t('shell.roomClosed'), 'danger');
        ctx.navigate(CHANNEL);
      }
    });

    const join = () => send('join', { room: roomCode });
    const stopRejoin = net.onRejoin(join);
    join();

    return () => {
      cancelAnimationFrame(rafId);
      clearInterval(inputTimer);
      window.removeEventListener('keydown', onKeyDown);
      window.removeEventListener('keyup', onKeyUp);
      window.removeEventListener('blur', releaseInputs);
      document.removeEventListener('visibilitychange', onVisibilityChange);
      canvas.removeEventListener('mousemove', onMouseMove);
      canvas.removeEventListener('mousedown', onMouseDown);
      window.removeEventListener('mouseup', onMouseUp);
      canvas.removeEventListener('contextmenu', onContext);
      canvas.removeEventListener('touchstart', onTouchStart);
      canvas.removeEventListener('touchmove', onTouchMove);
      canvas.removeEventListener('touchend', onTouchEnd);
      canvas.removeEventListener('touchcancel', onTouchEnd);
      stopNet();
      stopRejoin();
      send('leave');
    };
  },
};

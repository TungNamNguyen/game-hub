/* Đêm Tử Thần (Zombie Outbreak) — Game Bắn Súng Sinh Tồn Zombie Multiplayer 1–6 người Co-op & AI Bots.
 * Đồ họa 2.5D Tactical Canvas 60 FPS với Instant Local Aim, Velocity Dead-Reckoning, Dynamic Flashlight,
 * 7 loại vũ khí có thể nâng cấp Mk.I–Mk.III + SVG Icons, 4 lớp Chiến Binh, Mini-Boss & Boss Đột Biến.
 */

import { avatar, clear, h, mount } from '../dom.js';
import { modeLabel, t } from '../i18n.js';
import { soundEnabled, toast } from '../ui.js';
import { renderLobby, roomCard, roomChat, roomTopbar } from './gameroom.js';

const CHANNEL = 'zombie';
const CLASS_IDS = ['assault', 'medic', 'engineer', 'vanguard'];
const MAP_IDS = ['outpost', 'lab', 'endless'];
const DIFF_IDS = ['easy', 'normal', 'hard'];

const CLASS_META = {
  assault: { icon: '🔫', color: '#38bdf8', desc: '+20% Sát thương · Thay đạn nhanh · SMG' },
  medic: { icon: '⚕️', color: '#4ade80', desc: 'Hào quang hồi máu · Cứu đồng đội ×2 nhanh' },
  engineer: { icon: '🛠️', color: '#fbbf24', desc: 'Tặng 1 Trụ Súng Sentry · Trụ mạnh +35%' },
  vanguard: { icon: '🛡️', color: '#f87171', desc: '150 HP + 55 Giáp · Shotgun · Dash nhanh' },
};

const PERK_DESC = {
  damage: '+20% Sát thương đạn',
  reload: '+30% Băng đạn · -18% Thay đạn',
  speed: '+12% Tốc độ di chuyển',
  armor: '+30 HP tối đa · +45 Giáp',
  vamp: '+4 HP mỗi khi hạ Zombie',
};

const PERK_ICON = {
  damage: '💥',
  reload: '🔄',
  speed: '👟',
  armor: '🛡️',
  vamp: '🩸',
};

const ITEM_ICON = {
  medkit: '🩹',
  ammo: '📦',
  grenade: '💣',
  turret: '🛰️',
  shield: '🔰',
  stim: '💉',
};

const WEAPON_SHORT = {
  pistol: 'M1911',
  smg: 'VECTOR',
  shotgun: 'M870',
  rifle: 'AK-47',
  launcher: 'M79',
  flamer: 'FLAMER',
  railgun: 'RAILGUN',
};

/* ------------------------------------------- SVG Weapon Silhouette Icons -- */
const WEAPON_SVG_MARKUP = {
  pistol: `<svg viewBox="0 0 64 28" class="z-wsvg" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 8h34v7H27l-3 10h-8l3-10h-5z" fill="currentColor" fill-opacity="0.22"/><path d="M27 15h6l-1 4h-5"/><line x1="48" y1="10" x2="54" y2="10"/></svg>`,
  smg: `<svg viewBox="0 0 64 28" class="z-wsvg" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M8 9h38v8H34l-2 9h-6l1-9H16l-2 7H9l2-7H8z" fill="currentColor" fill-opacity="0.22"/><line x1="46" y1="12" x2="58" y2="12"/><line x1="22" y1="6" x2="34" y2="6"/></svg>`,
  shotgun: `<svg viewBox="0 0 64 28" class="z-wsvg" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 15l12-4h40v4H34l-3 4H22l-4 5H6z" fill="currentColor" fill-opacity="0.22"/><rect x="33" y="15" width="14" height="4" rx="1" fill="currentColor" fill-opacity="0.45"/><line x1="56" y1="12" x2="60" y2="12"/></svg>`,
  rifle: `<svg viewBox="0 0 64 28" class="z-wsvg" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 13l12-2h34v5H38l4 9h-6l-4-9h-6l-2 7h-5l1-7H14l-10 3z" fill="currentColor" fill-opacity="0.22"/><line x1="50" y1="12" x2="61" y2="12"/><line x1="26" y1="8" x2="36" y2="8"/></svg>`,
  launcher: `<svg viewBox="0 0 64 28" class="z-wsvg" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M6 15l12-4h32v9H28l-3 5h-6l2-5h-5L6 21z" fill="currentColor" fill-opacity="0.22"/><rect x="26" y="8" width="26" height="9" rx="2" fill="currentColor" fill-opacity="0.32"/><circle cx="55" cy="12.5" r="2.5" fill="currentColor"/></svg>`,
  flamer: `<svg viewBox="0 0 64 28" class="z-wsvg" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="10" y="9" width="32" height="10" rx="3" fill="currentColor" fill-opacity="0.22"/><rect x="16" y="19" width="16" height="6" rx="2" fill="currentColor" fill-opacity="0.4"/><line x1="42" y1="13" x2="54" y2="13"/><path d="M55 9c3 2 5 4 5 5s-2 3-5 5c1-2 1-4 0-5 1-1 1-3 0-5z" fill="#fb923c" stroke="#fb923c"/></svg>`,
  railgun: `<svg viewBox="0 0 64 28" class="z-wsvg" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 12h18l4-4h34v4H34v4h26v4H26l-4-4H16l-3 8H7l2-8H4z" fill="currentColor" fill-opacity="0.22"/><line x1="28" y1="14" x2="58" y2="14" stroke="#e0f2fe" stroke-width="2.5"/></svg>`,
};

function makeWeaponIcon(wid, color) {
  const wrap = h('span', { class: 'z-wicon-wrap', style: { color: color || '#e2e8f0' } });
  wrap.innerHTML = WEAPON_SVG_MARKUP[wid] || WEAPON_SVG_MARKUP.pistol;
  return wrap;
}

function lerpAngle(a, b, f) {
  let diff = ((b - a + Math.PI * 3) % (Math.PI * 2)) - Math.PI;
  return a + diff * f;
}

/* ------------------------------------------- WebAudio Procedural Combat SFX */
let audioCtx = null;
function getAudio() {
  if (!soundEnabled()) return null;
  if (!audioCtx && typeof window !== 'undefined') {
    const AC = window.AudioContext || window.webkitAudioContext;
    if (AC) audioCtx = new AC();
  }
  if (audioCtx && audioCtx.state === 'suspended') {
    audioCtx.resume().catch(() => {});
  }
  return audioCtx;
}

function playGunSfx(weapon) {
  const ctx = getAudio();
  if (!ctx) return;
  const now = ctx.currentTime;
  try {
    if (weapon === 'railgun') {
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.type = 'sawtooth';
      osc.frequency.setValueAtTime(920, now);
      osc.frequency.exponentialRampToValueAtTime(110, now + 0.24);
      gain.gain.setValueAtTime(0.14, now);
      gain.gain.exponentialRampToValueAtTime(0.001, now + 0.25);
      osc.connect(gain).connect(ctx.destination);
      osc.start(now);
      osc.stop(now + 0.26);
      return;
    }
    if (weapon === 'launcher') {
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.type = 'triangle';
      osc.frequency.setValueAtTime(220, now);
      osc.frequency.exponentialRampToValueAtTime(55, now + 0.18);
      gain.gain.setValueAtTime(0.18, now);
      gain.gain.exponentialRampToValueAtTime(0.001, now + 0.19);
      osc.connect(gain).connect(ctx.destination);
      osc.start(now);
      osc.stop(now + 0.2);
      return;
    }
    if (weapon === 'flamer') {
      const buf = ctx.createBuffer(1, Math.floor(ctx.sampleRate * 0.08), ctx.sampleRate);
      const data = buf.getChannelData(0);
      for (let i = 0; i < data.length; i++) data[i] = (Math.random() * 2 - 1) * 0.4;
      const src = ctx.createBufferSource();
      src.buffer = buf;
      const flt = ctx.createBiquadFilter();
      flt.type = 'bandpass';
      flt.frequency.value = 500;
      const gain = ctx.createGain();
      gain.gain.setValueAtTime(0.07, now);
      gain.gain.exponentialRampToValueAtTime(0.001, now + 0.08);
      src.connect(flt).connect(gain).connect(ctx.destination);
      src.start(now);
      return;
    }
    const dur = weapon === 'shotgun' ? 0.16 : weapon === 'rifle' ? 0.10 : 0.065;
    const buf = ctx.createBuffer(1, Math.floor(ctx.sampleRate * dur), ctx.sampleRate);
    const data = buf.getChannelData(0);
    for (let i = 0; i < data.length; i++) {
      data[i] = (Math.random() * 2 - 1) * Math.pow(1 - i / data.length, 1.6);
    }
    const src = ctx.createBufferSource();
    src.buffer = buf;
    const flt = ctx.createBiquadFilter();
    flt.type = 'lowpass';
    flt.frequency.value = weapon === 'shotgun' ? 900 : weapon === 'smg' ? 2200 : weapon === 'turret' ? 2600 : 1500;
    const gain = ctx.createGain();
    const vol = weapon === 'shotgun' ? 0.17 : weapon === 'turret' ? 0.05 : 0.10;
    gain.gain.setValueAtTime(vol, now);
    gain.gain.exponentialRampToValueAtTime(0.001, now + dur);
    src.connect(flt).connect(gain).connect(ctx.destination);
    src.start(now);
  } catch (_) {}
}

function playBoomSfx() {
  const ctx = getAudio();
  if (!ctx) return;
  const now = ctx.currentTime;
  try {
    const dur = 0.42;
    const buf = ctx.createBuffer(1, Math.floor(ctx.sampleRate * dur), ctx.sampleRate);
    const data = buf.getChannelData(0);
    for (let i = 0; i < data.length; i++) {
      data[i] = (Math.random() * 2 - 1) * Math.pow(1 - i / data.length, 1.4);
    }
    const src = ctx.createBufferSource();
    src.buffer = buf;
    const flt = ctx.createBiquadFilter();
    flt.type = 'lowpass';
    flt.frequency.setValueAtTime(420, now);
    flt.frequency.exponentialRampToValueAtTime(70, now + dur);
    const gain = ctx.createGain();
    gain.gain.setValueAtTime(0.24, now);
    gain.gain.exponentialRampToValueAtTime(0.001, now + dur);
    src.connect(flt).connect(gain).connect(ctx.destination);
    src.start(now);
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

  const bg = mode === 'lab' ? '#0a131b' : mode === 'endless' ? '#160a0e' : '#10151c';
  g.fillStyle = bg;
  g.fillRect(0, 0, w, h);

  // Lưới sàn chiến thuật
  const tile = 70;
  g.strokeStyle = mode === 'lab'
    ? 'rgba(34, 211, 238, 0.08)'
    : mode === 'endless'
      ? 'rgba(244, 63, 94, 0.07)'
      : 'rgba(148, 163, 184, 0.07)';
  g.lineWidth = 1;
  for (let x = 0; x <= w; x += tile) {
    g.beginPath(); g.moveTo(x, 0); g.lineTo(x, h); g.stroke();
  }
  for (let y = 0; y <= h; y += tile) {
    g.beginPath(); g.moveTo(0, y); g.lineTo(w, y); g.stroke();
  }

  // Vân nền ngẫu nhiên nhẹ
  let seed = mode === 'lab' ? 42 : mode === 'endless' ? 99 : 7;
  const rand = () => {
    seed = (seed * 1664525 + 1013904223) >>> 0;
    return seed / 4294967296;
  };
  for (let i = 0; i < 240; i++) {
    const px = rand() * w;
    const py = rand() * h;
    const r = 1 + rand() * 3;
    g.fillStyle = rand() > 0.5 ? 'rgba(255,255,255,0.025)' : 'rgba(0,0,0,0.22)';
    g.fillRect(px, py, r * 2, r);
  }

  // Vòng tròn sân đáp trung tâm
  const cx = w * 0.5;
  const cy = h * 0.5;
  g.save();
  g.strokeStyle = mode === 'lab'
    ? 'rgba(34, 211, 238, 0.16)'
    : mode === 'endless'
      ? 'rgba(239, 68, 68, 0.16)'
      : 'rgba(250, 204, 21, 0.14)';
  g.lineWidth = 4;
  g.setLineDash([18, 12]);
  g.beginPath();
  g.arc(cx, cy, 175, 0, Math.PI * 2);
  g.stroke();
  g.setLineDash([]);
  g.lineWidth = 2;
  g.beginPath();
  g.arc(cx, cy, 240, 0, Math.PI * 2);
  g.stroke();
  g.restore();

  // Viền cảnh báo quanh chu vi bản đồ
  g.strokeStyle = mode === 'lab' ? 'rgba(34,211,238,0.28)' : 'rgba(250,204,21,0.24)';
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
    let autoShopWave = -1;
    let currentMatchId = -1;
    let lastEventSeq = 0;
    let lastLobbyKey = '';
    let lastHudKey = '';
    let lastShopKey = '';
    let floorCache = { mode: '', canvas: null };

    // Live 60 FPS cooldown trackers (synced from server, ticked smoothly every frame)
    let localDashEndMs = 0;
    let localDashTotal = 3.4;
    let localReloadEndMs = 0;
    let localReloadTotal = 1.2;
    let dashFillEl = null;
    let dashTextEl = null;
    let shopTimerEl = null;

    // Entity interpolation & visual effects state
    const lerpSurv = new Map();
    const lerpZomb = new Map();
    const lerpTurret = new Map();
    const tracers = [];
    const particles = [];
    const decals = [];
    const floatTexts = [];
    const shockwaves = [];
    let shakePower = 0;

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
      tracers.length = 0;
      floatTexts.length = 0;
      shockwaves.length = 0;
      lerpSurv.clear();
      lerpZomb.clear();
      lerpTurret.clear();
      shakePower = 0;
      autoShopWave = -1;
      shopOpen = false;
      lastHudKey = '';
      lastShopKey = '';
      lastEventSeq = 0;
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
    const topHud = h('div', { class: 'zombie-top-hud' });
    const bossHud = h('div', { class: 'zombie-boss-hud hidden' });
    const bottomHud = h('div', { class: 'zombie-bottom-hud' });
    const shopOverlay = h('div', { class: 'zombie-shop-overlay hidden' });

    const touchControls = h('div', { class: 'zombie-touch-bar' },
      h('button', { type: 'button', class: 'z-tbtn', onclick: () => send('dash') }, '⚡ Dash'),
      h('button', { type: 'button', class: 'z-tbtn', onclick: () => send('grenade', { tx: mouseWorldX, ty: mouseWorldY }) }, '💣 Bom'),
      h('button', { type: 'button', class: 'z-tbtn', onclick: () => send('turret') }, '🛰️ Trụ'),
      h('button', { type: 'button', class: 'z-tbtn', onclick: () => send('reload') }, '🔄 Đạn'),
      h('button', { type: 'button', class: 'z-tbtn', onclick: () => { shopOpen = !shopOpen; lastShopKey = ''; renderShopModal(); } }, '🛒 Shop'),
    );

    stageWrap.append(canvas, topHud, bossHud, bottomHud, touchControls, shopOverlay);

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
      if (particles.length > 360) particles.splice(0, particles.length - 360);
    }

    function addDecal(x, y, r, color) {
      decals.push({ x, y, r, color, alpha: 0.52, life: 18.0, maxLife: 18.0 });
      if (decals.length > 75) decals.shift();
    }

    function ingestEvents(events) {
      if (!Array.isArray(events) || !events.length) return;
      // Phòng hờ nếu server restart và seq nhỏ hơn lastEventSeq
      if (events[events.length - 1].seq < lastEventSeq) {
        lastEventSeq = 0;
      }
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
          if (ev.weapon === 'flamer') {
            addParticles(ev.x, ev.y, 5, '#fb923c', 120, 260, 4, 8, 0.14, 0.28);
          } else {
            addParticles(ev.x, ev.y, ev.weapon === 'shotgun' ? 7 : 3, ev.color || '#fde047', 60, 180, 2, 4, 0.08, 0.18);
          }
          if (ev.mark === state?.you?.mark) {
            if (ev.weapon === 'shotgun' || ev.weapon === 'launcher') shakePower = Math.max(shakePower, 6.5);
            else if (ev.weapon === 'railgun') shakePower = Math.max(shakePower, 9.0);
            else if (ev.weapon === 'rifle') shakePower = Math.max(shakePower, 2.2);
            playGunSfx(ev.weapon);
          }
        } else if (ev.t === 'hit') {
          addParticles(ev.x, ev.y, ev.crit ? 8 : 4, ev.crit ? '#38bdf8' : '#22c55e', 45, 160, 2, 4.5, 0.15, 0.35);
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
          addDecal(ev.x, ev.y, isBig ? 44 : isMini ? 30 : ev.kind === 'brute' ? 24 : 14, blood);
          addParticles(ev.x, ev.y, isBig ? 38 : isMini ? 24 : 14, blood, 60, 250, 3, 6.5, 0.25, 0.65);
          if (isBig || isMini) {
            shockwaves.push({ x: ev.x, y: ev.y, r: 20, maxR: isBig ? 230 : 150, color: blood, life: 0.5, maxLife: 0.5 });
            shakePower = Math.max(shakePower, isBig ? 14 : 9);
            playBoomSfx();
          }
        } else if (ev.t === 'boom') {
          addDecal(ev.x, ev.y, 40, '#1e293b');
          addParticles(ev.x, ev.y, 32, '#fb923c', 80, 340, 3, 8, 0.22, 0.65);
          addParticles(ev.x, ev.y, 18, '#fef08a', 40, 210, 2, 5, 0.16, 0.45);
          shockwaves.push({ x: ev.x, y: ev.y, r: 16, maxR: ev.radius || 135, color: '#fb923c', life: 0.35, maxLife: 0.35 });
          shakePower = Math.max(shakePower, 12);
          playBoomSfx();
        } else if (ev.t === 'slam' || ev.t === 'orbital') {
          const col = ev.t === 'orbital' ? '#f43f5e' : '#fb923c';
          addDecal(ev.x, ev.y, 34, '#3f121e');
          addParticles(ev.x, ev.y, 26, col, 90, 300, 3, 7, 0.22, 0.55);
          shockwaves.push({ x: ev.x, y: ev.y, r: 14, maxR: ev.radius || 110, color: col, life: 0.38, maxLife: 0.38 });
          shakePower = Math.max(shakePower, 10);
          playBoomSfx();
        } else if (ev.t === 'acid') {
          shockwaves.push({ x: ev.x, y: ev.y, r: 12, maxR: ev.radius || 68, color: '#4ade80', life: 0.32, maxLife: 0.32 });
          addParticles(ev.x, ev.y, 16, '#86efac', 40, 150, 3, 6, 0.2, 0.5);
        } else if (ev.t === 'dash') {
          shockwaves.push({ x: ev.x, y: ev.y, r: 8, maxR: 48, color: '#38bdf8', life: 0.22, maxLife: 0.22 });
          addParticles(ev.x, ev.y, 10, '#7dd3fc', 30, 120, 2, 4.5, 0.15, 0.32);
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
          const lbl = ev.kind === 'med' ? '+32 HP' : ev.kind === 'ammo' ? '+ĐẠN' : '+$75';
          const col = ev.kind === 'med' ? '#4ade80' : ev.kind === 'ammo' ? '#38bdf8' : '#facc15';
          floatTexts.push({ x: ev.x, y: ev.y - 16, text: lbl, color: col, big: false, life: 0.85, maxLife: 0.85 });
        } else if (ev.t === 'wave') {
          if (ev.boss) {
            toast(`⚠️ ĐỢT ${ev.wave} — BOSS ${ev.bossTitle || 'CHÚA TỂ'} XUẤT HIỆN!`, 'danger');
          } else if (ev.miniBoss) {
            toast(`🔥 ĐỢT ${ev.wave} — MINI-BOSS ${ev.bossTitle || 'TINH ANH'} XUẤT HIỆN!`, 'danger');
          } else {
            toast(`☣️ Đợt ${ev.wave} bắt đầu!`, 'ok');
          }
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
          '⌨️ WASD di chuyển · Chuột ngắm & bắn · 1–7 đổi súng · R thay đạn · Space Lướt né · G Lựu đạn · E Trụ súng · B Cửa hàng'),
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

    /* ------------------------------------------- Armory Shop Modal 2.0 --- */
    function renderShopModal(force = false) {
      const s = state;
      if (!s || !shopOpen || s.status !== 'playing') {
        shopOverlay.classList.add('hidden');
        shopTimerEl = null;
        return;
      }
      const me = (s.survivors || []).find((x) => x.mark === s.you?.mark);
      if (!me) {
        shopOverlay.classList.add('hidden');
        return;
      }
      shopOverlay.classList.remove('hidden');

      // Chỉ cập nhật text đếm ngược mà không phá hủy nút bấm khi dữ liệu mua sắm không đổi
      const shopKey = JSON.stringify([
        s.phase, s.wave, me.money, me.weapons, me.weaponLv, me.perks,
        me.grenades, me.turrets, me.readyShop, Math.round(me.hp), Math.round(me.armor),
      ]);
      if (!force && shopKey === lastShopKey) {
        if (shopTimerEl && s.phase === 'shop') {
          shopTimerEl.textContent = me.readyShop ? 'Đã sẵn sàng…' : `Sẵn sàng ngay (${Math.ceil(s.shopLeft)}s)`;
        }
        return;
      }
      lastShopKey = shopKey;
      clear(shopOverlay);

      const cat = s.catalog || {};
      const maxLv = cat.maxWeaponLv || 3;
      const weaponOrder = cat.weaponOrder || ['pistol', 'smg', 'shotgun', 'rifle', 'launcher', 'flamer', 'railgun'];

      const mkStatBar = (label, pct, color) => h('div', { class: 'z-stat-row' },
        h('span', { class: 'z-stat-lbl' }, label),
        h('div', { class: 'z-stat-track' },
          h('div', { class: 'z-stat-fill', style: { width: `${Math.max(8, Math.min(100, pct))}%`, background: color } })));

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
          const canBuyNew = !owned && me.money >= w.cost;
          const canRefill = owned && wid !== 'pistol' && me.money >= refillCost;
          const canUpgrade = owned && curLv < maxLv && me.money >= upgCost;

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

      const itemGrid = h('div', { class: 'zombie-shop-grid' },
        Object.entries(cat.items || {}).map(([iid, it]) => {
          const canBuy = me.money >= it.cost;
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
        }));

      const perkGrid = h('div', { class: 'zombie-shop-grid' },
        Object.entries(cat.perks || {}).map(([pid, pk]) => {
          const cur = (me.perks || {})[pid] || 0;
          const maxed = cur >= pk.max;
          const cost = pk.cost + cur * 110;
          const canBuy = !maxed && me.money >= cost;
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
        }));

      shopTimerEl = s.phase === 'shop'
        ? h('button', {
            type: 'button',
            class: 'sm primary',
            disabled: me.readyShop,
            onclick: () => {
              send('ready_shop');
              shopOpen = false;
              renderShopModal();
            },
          }, me.readyShop ? 'Đã sẵn sàng…' : `Sẵn sàng ngay (${Math.ceil(s.shopLeft)}s)`)
        : null;

      const headRight = h('div', { class: 'row', style: { gap: '8px', alignItems: 'center', flexWrap: 'wrap' } },
        h('span', { class: 'chip warn', style: { fontSize: '14px', fontWeight: '800' } }, `💰 $${me.money}`),
        shopTimerEl,
        h('button', {
          type: 'button',
          class: 'sm ghost',
          onclick: () => { shopOpen = false; renderShopModal(); },
        }, 'Đóng (B)'));

      shopOverlay.append(
        h('div', { class: 'zombie-shop-modal card col', style: { gap: '12px' } },
          h('div', { class: 'spread', style: { gap: '8px', flexWrap: 'wrap' } },
            h('h2', {}, s.phase === 'shop' ? `🛒 Trạm Tiếp Tế — Đợt ${s.wave + 1} sắp tới` : '🛒 Kho Vũ Khí & Nâng Cấp'),
            headRight),
          h('div', { class: 'small muted', style: { fontWeight: '700' } }, '🔫 Vũ Khí & Nâng Cấp Mk.I – Mk.III'),
          wGrid,
          h('div', { class: 'small muted', style: { fontWeight: '700' } }, '🧰 Tiếp Tế & Chiến Thuật'),
          itemGrid,
          h('div', { class: 'small muted', style: { fontWeight: '700' } }, '⚡ Nâng Cấp Kỹ Năng (Perks)'),
          perkGrid));
    }

    /* ------------------------------------------- In-Game HUD ------------- */
    function renderHud() {
      const s = state;
      if (!s || s.status !== 'playing') return;
      const me = (s.survivors || []).find((x) => x.mark === s.you?.mark);

      // Đồng bộ đồng hồ hồi chiêu Dash & Reload cho vòng lặp 60 FPS
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

      const bosses = s.bosses || (s.boss ? [s.boss] : []);
      const hudKey = JSON.stringify([
        s.phase, s.wave, s.zombiesLeft, s.totalKills, Math.ceil(s.shopLeft),
        bosses.map((b) => [b.id, Math.ceil(b.hp), b.enraged, b.skill]),
        (s.survivors || []).map((x) => [
          x.mark, Math.round(x.hp), Math.round(x.armor), x.downed, x.alive,
          Math.ceil(x.bleedout || 0), x.weapon, (x.weaponLv || {})[x.weapon],
          x.mag?.[x.weapon], x.reserve?.[x.weapon], x.money, x.grenades, x.turrets,
          x.reloading, Math.ceil((x.dashReady || 0) * 10), x.stimLeft > 0,
        ]),
      ]);
      if (hudKey === lastHudKey) {
        if (shopOpen) renderShopModal();
        return;
      }
      lastHudKey = hudKey;

      // Top HUD (chỉ còn 1 nút thoát chính là nút Lobby trên topbar chung!)
      clear(topHud);
      const waveLabel = s.maxWaves > 0 ? `ĐỢT ${s.wave} / ${s.maxWaves}` : `ĐỢT ${s.wave}`;
      topHud.append(
        h('div', { class: 'z-hud-pill accent' }, `☣️ ${waveLabel}`),
        s.phase === 'shop'
          ? h('div', { class: 'z-hud-pill warn' }, `🛒 Tiếp tế: ${Math.ceil(s.shopLeft)}s`)
          : h('div', { class: 'z-hud-pill danger' }, `🧟 Còn lại: ${s.zombiesLeft}`),
        h('div', { class: 'z-hud-pill' }, `💀 Diệt: ${s.totalKills}`),
        h('button', {
          type: 'button',
          class: 'xs primary',
          onclick: () => { shopOpen = !shopOpen; lastShopKey = ''; renderShopModal(true); },
        }, '🛒 Shop (B)'),
      );

      // Boss & Mini-Boss Health Bars
      if (bosses.length > 0) {
        bossHud.classList.remove('hidden');
        clear(bossHud);
        for (const b of bosses) {
          const pct = Math.max(0, Math.min(100, (b.hp / Math.max(1, b.maxHp)) * 100));
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

      clear(bottomHud);
      dashFillEl = null;
      dashTextEl = null;
      if (me) {
        const wInfo = s.catalog?.weapons?.[me.weapon] || {};
        const curLv = (me.weaponLv || {})[me.weapon] || 1;
        const curMag = me.mag?.[me.weapon] ?? 0;
        const curRes = me.reserve?.[me.weapon];
        const ammoStr = me.reloading ? 'ĐANG THAY ĐẠN…' : `${curMag} / ${curRes === -1 ? '∞' : (curRes ?? 0)}`;
        const hpPct = Math.max(0, Math.min(100, (me.hp / Math.max(1, me.maxHp)) * 100));
        const arPct = Math.max(0, Math.min(100, (me.armor / Math.max(1, me.maxArmor)) * 100));

        const vitals = h('div', { class: 'z-hud-box z-vitals' },
          h('div', { class: 'spread tiny' },
            h('strong', {}, `❤️ ${Math.ceil(me.hp)}/${Math.ceil(me.maxHp)}`),
            h('span', { style: { color: '#38bdf8', fontWeight: '700' } }, `🛡️ ${Math.ceil(me.armor)}`),
            me.stimLeft > 0 ? h('span', { style: { color: '#22d3ee', fontWeight: '700' } }, `💉${Math.ceil(me.stimLeft)}s`) : null),
          h('div', { class: 'z-bar hp' }, h('div', { style: { width: `${hpPct}%` } })),
          h('div', { class: 'z-bar armor' }, h('div', { style: { width: `${arPct}%` } })));

        const weaponSlots = h('div', { class: 'z-hud-box z-weapons' },
          h('div', { class: 'spread tiny', style: { gap: '8px' } },
            h('div', { class: 'row', style: { gap: '6px', alignItems: 'center' } },
              makeWeaponIcon(me.weapon, curLv >= 3 ? '#e879f9' : (wInfo.color || '#fde047')),
              h('strong', { style: { color: wInfo.color || '#fde047' } }, `${wInfo.name || me.weapon}${curLv > 1 ? ` Mk.${curLv}` : ''}`)),
            h('strong', { style: { color: me.reloading ? '#fbbf24' : '#f8fafc' } }, ammoStr)),
          h('div', { class: 'row', style: { gap: '4px', marginTop: '5px', flexWrap: 'wrap' } },
            (me.weapons || []).map((wid, idx) => {
              const lv = (me.weaponLv || {})[wid] || 1;
              return h('button', {
                type: 'button',
                class: 'xs ' + (wid === me.weapon ? 'primary' : 'ghost'),
                onclick: () => send('switch', { weapon: wid }),
              }, `${idx + 1}:${WEAPON_SHORT[wid] || wid.toUpperCase()}${lv > 1 ? `★${lv}` : ''}`);
            })));

        const dashPct = me.dashReady > 0 ? Math.min(100, (me.dashReady / Math.max(0.5, me.dashTotal || 3.4)) * 100) : 0;
        dashFillEl = h('div', { class: 'z-cd-fill', style: { width: `${dashPct}%` } });
        dashTextEl = h('span', { class: 'z-cd-text' }, me.dashReady <= 0 ? '⚡ Dash [Space]' : `⚡ ${me.dashReady.toFixed(1)}s`);
        const dashBadge = h('button', {
          type: 'button',
          class: 'z-skill-btn' + (me.dashReady <= 0 ? ' ready' : ' cooling'),
          onclick: () => send('dash'),
        }, dashFillEl, dashTextEl);

        const tactical = h('div', { class: 'z-hud-box z-tactical' },
          h('span', { class: 'chip warn', style: { fontWeight: '800' } }, `💰 $${me.money}`),
          dashBadge,
          h('button', {
            type: 'button',
            class: 'z-skill-btn' + (me.grenades > 0 ? ' ready' : ''),
            onclick: () => send('grenade', { tx: mouseWorldX, ty: mouseWorldY }),
          }, h('span', { class: 'z-cd-text' }, `💣 ×${me.grenades} [G]`)),
          h('button', {
            type: 'button',
            class: 'z-skill-btn' + (me.turrets > 0 ? ' ready' : ''),
            onclick: () => send('turret'),
          }, h('span', { class: 'z-cd-text' }, `🛰️ ×${me.turrets} [E]`)));

        bottomHud.append(vitals, weaponSlots, tactical);
      }

      const squadBox = h('div', { class: 'z-hud-box z-squad' + ((s.survivors || []).length > 4 ? ' six-col' : '') },
        (s.survivors || []).map((sv) => h('div', { class: 'z-squad-row' + (sv.downed ? ' downed' : !sv.alive ? ' dead' : '') },
          h('span', { class: 'geo-dot', style: { background: sv.color } }),
          h('span', { class: 'nowrap', style: { fontSize: '11.5px', fontWeight: sv.mark === s.you?.mark ? '700' : '500', maxWidth: '88px', overflow: 'hidden', textOverflow: 'ellipsis' } }, sv.name),
          h('span', { class: 'tiny muted' }, sv.downed ? `🆘${Math.ceil(sv.bleedout)}s` : !sv.alive ? '💀' : `❤️${Math.ceil(sv.hp)}`),
          h('span', { class: 'tiny', style: { color: '#facc15', marginLeft: 'auto' } }, `💀${sv.kills}`))));
      bottomHud.append(squadBox);

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

    /* ------------------------------------------- 60 FPS Canvas Engine ---- */
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
      g.fillStyle = 'rgba(0,0,0,0.48)';
      g.fillRect(x + 8, y + 10, w, h);

      if (kind === 'biotank') {
        const grad = g.createLinearGradient(x, y, x + w, y + h);
        grad.addColorStop(0, '#0f3d4c');
        grad.addColorStop(0.5, '#0e7490');
        grad.addColorStop(1, '#164e63');
        g.fillStyle = grad;
        g.fillRect(x, y, w, h);
        g.fillStyle = `rgba(34, 211, 238, ${0.28 + 0.14 * Math.sin(tSec * 3.2 + x)})`;
        g.fillRect(x + 8, y + 8, w - 16, h - 16);
        g.strokeStyle = '#22d3ee';
        g.lineWidth = 2;
        g.strokeRect(x + 1, y + 1, w - 2, h - 2);
      } else if (kind === 'reactor') {
        g.fillStyle = '#2b151e';
        g.fillRect(x, y, w, h);
        const pulse = 0.55 + 0.35 * Math.sin(tSec * 4.5);
        const rg = g.createRadialGradient(x + w / 2, y + h / 2, 4, x + w / 2, y + h / 2, w * 0.45);
        rg.addColorStop(0, `rgba(244, 63, 94, ${pulse})`);
        rg.addColorStop(1, 'rgba(244, 63, 94, 0)');
        g.fillStyle = rg;
        g.fillRect(x, y, w, h);
        g.strokeStyle = '#fb7185';
        g.lineWidth = 2.5;
        g.strokeRect(x + 2, y + 2, w - 4, h - 4);
      } else if (kind === 'bunker') {
        g.fillStyle = '#1e293b';
        g.fillRect(x, y, w, h);
        g.fillStyle = '#334155';
        g.fillRect(x + 6, y + 6, w - 12, h - 18);
        g.strokeStyle = '#64748b';
        g.lineWidth = 2;
        g.strokeRect(x + 1, y + 1, w - 2, h - 2);
      } else {
        g.fillStyle = mode === 'lab' ? '#1e293b' : '#293241';
        g.fillRect(x, y, w, h);
        g.fillStyle = mode === 'lab' ? '#334155' : '#3b475a';
        g.fillRect(x + 4, y + 4, w - 8, h - 12);
        g.strokeStyle = mode === 'lab' ? '#38bdf8' : '#f59e0b';
        g.lineWidth = 1.5;
        g.strokeRect(x + 1, y + 1, w - 2, h - 2);
      }
    }

    function drawSurvivor(g, sv, sx, sy, aimAngle, tSec, isMe, nowMs) {
      g.save();
      g.translate(sx, sy);

      // Hào quang Quân Y (Medic)
      if (sv.cls === 'medic' && sv.alive && !sv.downed) {
        g.strokeStyle = `rgba(74, 222, 128, ${0.16 + 0.08 * Math.sin(tSec * 4)})`;
        g.lineWidth = 2;
        g.beginPath();
        g.arc(0, 0, 140, 0, Math.PI * 2);
        g.stroke();
      }

      // Hào quang Huyết Thanh Cuồng Phong (Stim)
      if (sv.stimLeft > 0 && sv.alive && !sv.downed) {
        g.strokeStyle = `rgba(34, 211, 238, ${0.45 + 0.25 * Math.sin(tSec * 10)})`;
        g.lineWidth = 2.5;
        g.beginPath();
        g.arc(0, 0, 23, 0, Math.PI * 2);
        g.stroke();
      }

      if (sv.downed) {
        g.fillStyle = 'rgba(239, 68, 68, 0.22)';
        g.beginPath();
        g.arc(0, 0, 32 + Math.sin(tSec * 7) * 5, 0, Math.PI * 2);
        g.fill();
        g.strokeStyle = '#ef4444';
        g.lineWidth = 2.5;
        g.beginPath();
        g.arc(0, 0, 26, 0, Math.PI * 2);
        g.stroke();
        if (sv.reviveProg > 0) {
          g.strokeStyle = '#4ade80';
          g.lineWidth = 5;
          g.beginPath();
          g.arc(0, 0, 32, -Math.PI / 2, -Math.PI / 2 + Math.PI * 2 * sv.reviveProg);
          g.stroke();
        }
      }

      // Đèn pin chiến thuật (Flashlight Cone — xoay 60 FPS tức thì cho bản thân)
      if (sv.alive && !sv.downed) {
        g.save();
        g.rotate(aimAngle);
        const fl = g.createRadialGradient(14, 0, 6, 14, 0, 290);
        fl.addColorStop(0, 'rgba(255, 250, 220, 0.22)');
        fl.addColorStop(0.55, 'rgba(255, 245, 200, 0.07)');
        fl.addColorStop(1, 'rgba(255, 245, 200, 0)');
        g.fillStyle = fl;
        g.beginPath();
        g.moveTo(10, 0);
        g.arc(10, 0, 290, -0.36, 0.36);
        g.closePath();
        g.fill();
        g.restore();
      }

      // Đổ bóng chân
      g.fillStyle = 'rgba(0,0,0,0.45)';
      g.beginPath();
      g.ellipse(3, 5, 17, 14, 0, 0, Math.PI * 2);
      g.fill();

      // Thân & vũ khí xoay theo góc ngắm
      g.save();
      g.rotate(aimAngle);
      if (sv.dashing) {
        g.shadowColor = '#38bdf8';
        g.shadowBlur = 16;
      }
      g.fillStyle = sv.downed ? '#64748b' : (sv.color || '#38bdf8');
      g.beginPath();
      g.roundRect(-12, -14, 22, 28, 8);
      g.fill();
      g.strokeStyle = isMe ? '#ffffff' : 'rgba(255,255,255,0.45)';
      g.lineWidth = isMe ? 2.2 : 1.3;
      g.stroke();

      const wid = sv.weapon || 'pistol';
      const wLv = (sv.weaponLv || {})[wid] || 1;
      g.fillStyle = wLv >= 3 ? '#e879f9' : wid === 'railgun' ? '#22d3ee' : wid === 'flamer' ? '#f97316' : wid === 'launcher' ? '#f43f5e' : '#cbd5e1';
      if (wid === 'shotgun' || wid === 'rifle' || wid === 'railgun') {
        g.fillRect(6, -3, 24, 6);
        g.fillStyle = '#0f172a';
        g.fillRect(10, -2, 8, 4);
      } else if (wid === 'flamer' || wid === 'launcher') {
        g.fillRect(6, -4.5, 23, 9);
        g.fillStyle = wid === 'launcher' ? '#fb7185' : '#fbbf24';
        g.fillRect(24, -3.5, 5, 7);
      } else {
        g.fillRect(8, -2.5, 16, 5);
      }

      // Mũ bảo hộ chiến thuật
      g.fillStyle = '#0f172a';
      g.beginPath();
      g.arc(0, 0, 10, 0, Math.PI * 2);
      g.fill();
      g.fillStyle = CLASS_META[sv.cls]?.color || '#38bdf8';
      g.fillRect(4, -5, 5, 10);
      g.restore();

      // Thanh tiến trình thay đạn (60 FPS) ngay trên đầu bản thân
      if (isMe && localReloadEndMs > nowMs) {
        const rem = Math.max(0, (localReloadEndMs - nowMs) / 1000);
        const prog = 1 - Math.min(1, rem / Math.max(0.2, localReloadTotal));
        g.fillStyle = 'rgba(0,0,0,0.7)';
        g.fillRect(-20, 22, 40, 4);
        g.fillStyle = '#fbbf24';
        g.fillRect(-20, 22, 40 * prog, 4);
      }

      // Thanh máu & tên trên đầu
      const barW = 36;
      const hpRatio = Math.max(0, Math.min(1, sv.hp / Math.max(1, sv.maxHp)));
      g.fillStyle = 'rgba(0,0,0,0.65)';
      g.fillRect(-barW / 2, -28, barW, 5);
      g.fillStyle = sv.downed ? '#ef4444' : hpRatio > 0.4 ? '#4ade80' : '#f97316';
      g.fillRect(-barW / 2, -28, barW * hpRatio, 5);

      g.font = '600 11px system-ui, sans-serif';
      g.textAlign = 'center';
      g.fillStyle = '#f8fafc';
      g.fillText(sv.name, 0, -33);
      g.restore();
    }

    function drawZombie(g, z, zx, zy, tSec) {
      g.save();
      g.translate(zx, zy);

      const r = z.r || 16;
      const isMajor = z.kind === 'boss' || z.kind === 'titan';
      const isMini = z.kind === 'butcher' || z.kind === 'queen';

      // Hào quang Boss / Mini-Boss / Enraged
      if (isMajor || isMini) {
        const auraCol = z.kind === 'queen'
          ? 'rgba(52, 211, 153, 0.36)'
          : z.kind === 'butcher'
            ? 'rgba(251, 146, 60, 0.36)'
            : z.enraged
              ? 'rgba(244, 63, 94, 0.58)'
              : 'rgba(244, 63, 94, 0.38)';
        const bg = g.createRadialGradient(0, 0, r * 0.4, 0, 0, r * (z.enraged ? 2.2 : 1.85));
        bg.addColorStop(0, auraCol);
        bg.addColorStop(1, 'rgba(0, 0, 0, 0)');
        g.fillStyle = bg;
        g.beginPath();
        g.arc(0, 0, r * (z.enraged ? 2.2 : 1.85), 0, Math.PI * 2);
        g.fill();
      } else if (z.charging) {
        g.strokeStyle = 'rgba(248, 113, 113, 0.85)';
        g.lineWidth = 3;
        g.beginPath();
        g.arc(0, 0, r + 6, 0, Math.PI * 2);
        g.stroke();
      }

      // Bóng
      g.fillStyle = 'rgba(0,0,0,0.45)';
      g.beginPath();
      g.ellipse(3, 5, r, r * 0.8, 0, 0, Math.PI * 2);
      g.fill();

      const palette = {
        walker: '#4d7c0f',
        runner: '#dc2626',
        bloater: '#65a30d',
        spitter: '#10b981',
        brute: '#7c2d12',
        butcher: '#c2410c',
        queen: '#0d9488',
        boss: '#9f1239',
        titan: '#7f1d1d',
      };
      g.fillStyle = z.flash ? '#ffffff' : (palette[z.kind] || '#4d7c0f');
      const wobble = Math.sin(tSec * (z.kind === 'runner' ? 14 : 7) + z.id) * 1.4;
      g.beginPath();
      g.arc(0, wobble, r, 0, Math.PI * 2);
      g.fill();
      g.strokeStyle = z.enraged ? '#fde047' : z.burn ? '#fb923c' : isMini ? '#fed7aa' : 'rgba(0,0,0,0.6)';
      g.lineWidth = (z.enraged || z.burn || isMajor) ? 3 : 2;
      g.stroke();

      // Chi tiết đặc trưng từng chủng
      if (z.kind === 'bloater' || z.kind === 'queen') {
        g.fillStyle = `rgba(163, 230, 53, ${0.65 + 0.3 * Math.sin(tSec * 8 + z.id)})`;
        g.beginPath();
        g.arc(-r * 0.3, -r * 0.2, r * 0.24, 0, Math.PI * 2);
        g.arc(r * 0.32, r * 0.18, r * 0.2, 0, Math.PI * 2);
        g.fill();
      } else if (z.kind === 'butcher') {
        // Lưỡi dao phay khổng lồ xoay cạnh Đao Đồ Tể
        g.save();
        g.rotate(tSec * 3.5 + z.id);
        g.fillStyle = '#e2e8f0';
        g.fillRect(r * 0.5, -5, 18, 10);
        g.fillStyle = '#ef4444';
        g.fillRect(r * 0.5 + 12, -5, 6, 10);
        g.restore();
      } else if (z.kind === 'titan') {
        // Lõi năng lượng hạt nhân ở trung tâm Bạo Chúa
        g.fillStyle = z.enraged ? '#fef08a' : '#fb7185';
        g.beginPath();
        g.arc(0, 0, r * 0.36 + Math.sin(tSec * 9) * 2.5, 0, Math.PI * 2);
        g.fill();
      }

      if (isMajor || isMini || z.kind === 'brute') {
        g.fillStyle = z.kind === 'queen' ? '#5eead4' : '#fde047';
        const er = isMajor ? 4.8 : 3.2;
        g.beginPath();
        g.arc(-r * 0.28, -r * 0.18, er, 0, Math.PI * 2);
        g.arc(r * 0.28, -r * 0.18, er, 0, Math.PI * 2);
        g.fill();
      } else {
        g.fillStyle = z.kind === 'runner' ? '#fef08a' : '#bef264';
        g.beginPath();
        g.arc(-4, -3, 2.2, 0, Math.PI * 2);
        g.arc(4, -3, 2.2, 0, Math.PI * 2);
        g.fill();
      }

      if (z.hp < z.maxHp || z.kind === 'brute' || isMini || isMajor) {
        const bw = Math.max(26, r * 1.7);
        const pct = Math.max(0, Math.min(1, z.hp / Math.max(1, z.maxHp)));
        g.fillStyle = 'rgba(0,0,0,0.72)';
        g.fillRect(-bw / 2, -r - 11, bw, 4.5);
        g.fillStyle = isMajor ? '#f43f5e' : isMini ? '#fb923c' : '#ef4444';
        g.fillRect(-bw / 2, -r - 11, bw * pct, 4.5);
      }

      g.restore();
    }

    function renderFrame(nowMs) {
      rafId = requestAnimationFrame(renderFrame);
      const dt = Math.min(0.05, Math.max(0.001, (nowMs - lastFrameAt) / 1000));
      lastFrameAt = nowMs;
      if (!state || state.status !== 'playing') return;

      // Cập nhật thanh hồi chiêu Dash 60 FPS trực tiếp (không cần chờ server tick)
      if (dashFillEl && dashTextEl) {
        if (localDashEndMs > nowMs) {
          const rem = (localDashEndMs - nowMs) / 1000;
          const pct = Math.min(100, (rem / Math.max(0.5, localDashTotal)) * 100);
          dashFillEl.style.width = `${pct.toFixed(1)}%`;
          dashTextEl.textContent = `⚡ ${rem.toFixed(1)}s`;
        } else if (dashFillEl.style.width !== '0%') {
          dashFillEl.style.width = '0%';
          dashTextEl.textContent = '⚡ Dash [Space]';
        }
      }

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

      // 1. Mặt sàn
      g2d.drawImage(floorCache.canvas, 0, 0);

      // 2. Vết máu & vết cháy nổ tự mờ dần theo thời gian
      for (let i = decals.length - 1; i >= 0; i--) {
        const d = decals[i];
        d.life -= dt;
        if (d.life <= 0) {
          decals.splice(i, 1);
          continue;
        }
        const fade = d.life < 4.0 ? (d.life / 4.0) : 1.0;
        g2d.globalAlpha = d.alpha * fade;
        g2d.fillStyle = d.color;
        g2d.beginPath();
        g2d.arc(d.x, d.y, d.r, 0, Math.PI * 2);
        g2d.fill();
      }
      g2d.globalAlpha = 1;

      // 3. Vũng axit độc phát sáng
      for (const hz of (state.hazards || [])) {
        const ag = g2d.createRadialGradient(hz.x, hz.y, 4, hz.x, hz.y, hz.r);
        ag.addColorStop(0, 'rgba(74, 222, 128, 0.65)');
        ag.addColorStop(0.7, 'rgba(34, 197, 94, 0.35)');
        ag.addColorStop(1, 'rgba(34, 197, 94, 0)');
        g2d.fillStyle = ag;
        g2d.beginPath();
        g2d.arc(hz.x, hz.y, hz.r, 0, Math.PI * 2);
        g2d.fill();
      }

      // 3b. Vòng Cảnh Báo Chiêu Boss / Mini-Boss (Telegraph Danger Zones)
      for (const tg of (state.telegraphs || [])) {
        const prog = Math.max(0.05, Math.min(1, tg.prog || 0));
        const col = tg.kind === 'orbital' ? '244, 63, 94' : '251, 146, 60';
        g2d.save();
        g2d.fillStyle = `rgba(${col}, ${0.12 + prog * 0.22})`;
        g2d.beginPath();
        g2d.arc(tg.x, tg.y, tg.r, 0, Math.PI * 2);
        g2d.fill();
        // Vòng nạp lực lan dần ra mép ngoài
        g2d.fillStyle = `rgba(${col}, ${0.22 + prog * 0.25})`;
        g2d.beginPath();
        g2d.arc(tg.x, tg.y, tg.r * prog, 0, Math.PI * 2);
        g2d.fill();
        g2d.strokeStyle = `rgba(${col}, 0.92)`;
        g2d.lineWidth = 2.5;
        g2d.setLineDash([10, 6]);
        g2d.beginPath();
        g2d.arc(tg.x, tg.y, tg.r, 0, Math.PI * 2);
        g2d.stroke();
        g2d.restore();
      }

      // 4. Vật phẩm tiếp tế rơi trên sàn
      for (const pk of (state.pickups || [])) {
        const bob = Math.sin(tSec * 6 + pk.id) * 3;
        const col = pk.kind === 'med' ? '#4ade80' : pk.kind === 'ammo' ? '#38bdf8' : '#facc15';
        g2d.save();
        g2d.translate(pk.x, pk.y + bob);
        g2d.fillStyle = col;
        g2d.shadowColor = col;
        g2d.shadowBlur = 12;
        g2d.beginPath();
        g2d.roundRect(-10, -10, 20, 20, 5);
        g2d.fill();
        g2d.shadowBlur = 0;
        g2d.fillStyle = '#0f172a';
        g2d.font = '800 12px system-ui, sans-serif';
        g2d.textAlign = 'center';
        g2d.textBaseline = 'middle';
        g2d.fillText(pk.kind === 'med' ? '+' : pk.kind === 'ammo' ? '⚡' : '$', 0, 1);
        g2d.restore();
      }

      // 5. Chướng ngại vật 2.5D
      for (const ob of (state.arena?.obstacles || [])) {
        drawObstacle25D(g2d, ob, state.mode, tSec);
      }

      // 6. Trụ súng Sentry tự động (nội suy góc mượt)
      const activeTurrets = new Set();
      for (const tr of (state.turrets || [])) {
        activeTurrets.add(tr.id);
        let curAim = lerpTurret.get(tr.id);
        if (curAim === undefined) curAim = tr.aim;
        else curAim = lerpAngle(curAim, tr.aim, Math.min(1, dt * 16));
        lerpTurret.set(tr.id, curAim);

        g2d.save();
        g2d.translate(tr.x, tr.y);
        g2d.strokeStyle = 'rgba(52, 211, 153, 0.14)';
        g2d.lineWidth = 1.5;
        g2d.beginPath();
        g2d.arc(0, 0, 140, 0, Math.PI * 2);
        g2d.stroke();
        g2d.fillStyle = '#1e293b';
        g2d.beginPath();
        g2d.arc(0, 0, 14, 0, Math.PI * 2);
        g2d.fill();
        g2d.strokeStyle = '#34d399';
        g2d.lineWidth = 2;
        g2d.stroke();
        g2d.rotate(curAim);
        g2d.fillStyle = '#34d399';
        g2d.fillRect(0, -3.5, 20, 7);
        g2d.restore();
      }
      for (const id of lerpTurret.keys()) {
        if (!activeTurrets.has(id)) lerpTurret.delete(id);
      }

      // 7. Nội suy Dead-Reckoning 60 FPS & vẽ Zombie
      const activeZIds = new Set();
      const zBlend = 1 - Math.exp(-dt * 16);
      for (const z of (state.zombies || [])) {
        activeZIds.add(z.id);
        let cur = lerpZomb.get(z.id);
        if (!cur) {
          cur = { x: z.x, y: z.y };
          lerpZomb.set(z.id, cur);
        } else {
          // Dự đoán vị trí theo vận tốc rồi hòa trộn mượt về vị trí chuẩn server
          cur.x += (z.vx || 0) * dt * 0.55;
          cur.y += (z.vy || 0) * dt * 0.55;
          cur.x += (z.x - cur.x) * zBlend;
          cur.y += (z.y - cur.y) * zBlend;
        }
        drawZombie(g2d, z, cur.x, cur.y, tSec);
      }
      for (const id of lerpZomb.keys()) {
        if (!activeZIds.has(id)) lerpZomb.delete(id);
      }

      // 8. Nội suy Dead-Reckoning + Instant Local Aim & vẽ Chiến binh
      const activeMarks = new Set();
      const sBlend = 1 - Math.exp(-dt * 18);
      for (const sv of (state.survivors || [])) {
        if (!sv.alive) continue;
        activeMarks.add(sv.mark);
        const isMe = sv.mark === state.you?.mark;
        let cur = lerpSurv.get(sv.mark);
        if (!cur) {
          cur = { x: sv.x, y: sv.y, aim: sv.aim };
          lerpSurv.set(sv.mark, cur);
        } else {
          cur.x += (sv.vx || 0) * dt * 0.55;
          cur.y += (sv.vy || 0) * dt * 0.55;
          cur.x += (sv.x - cur.x) * sBlend;
          cur.y += (sv.y - cur.y) * sBlend;
          cur.aim = lerpAngle(cur.aim, sv.aim, sBlend);
        }
        const renderAim = (isMe && hasMouseMoved && !sv.downed && !shopOpen)
          ? Math.atan2(mouseWorldY - cur.y, mouseWorldX - cur.x)
          : cur.aim;
        drawSurvivor(g2d, sv, cur.x, cur.y, renderAim, tSec, isMe, nowMs);
      }
      for (const m of lerpSurv.keys()) {
        if (!activeMarks.has(m)) lerpSurv.delete(m);
      }

      // 9. Đạn bay (Lựu đạn, Đạn M79 Rocket, Cầu Axit & Plasma Boss)
      for (const pr of (state.projectiles || [])) {
        if (pr.kind === 'grenade') {
          const arcLift = Math.sin(Math.min(1, pr.t || 0) * Math.PI) * 34;
          g2d.fillStyle = 'rgba(0,0,0,0.4)';
          g2d.beginPath();
          g2d.ellipse(pr.x, pr.y + 4, 7, 4, 0, 0, Math.PI * 2);
          g2d.fill();
          g2d.fillStyle = '#f97316';
          g2d.beginPath();
          g2d.arc(pr.x, pr.y - arcLift, 6.5, 0, Math.PI * 2);
          g2d.fill();
        } else if (pr.kind === 'rocket') {
          g2d.fillStyle = '#fb7185';
          g2d.shadowColor = '#f43f5e';
          g2d.shadowBlur = 12;
          g2d.beginPath();
          g2d.arc(pr.x, pr.y, 6, 0, Math.PI * 2);
          g2d.fill();
          g2d.shadowBlur = 0;
        } else if (pr.kind === 'plasma') {
          g2d.fillStyle = '#f43f5e';
          g2d.shadowColor = '#fb7185';
          g2d.shadowBlur = 12;
          g2d.beginPath();
          g2d.arc(pr.x, pr.y, 6.5, 0, Math.PI * 2);
          g2d.fill();
          g2d.shadowBlur = 0;
        } else {
          g2d.fillStyle = '#4ade80';
          g2d.shadowColor = '#4ade80';
          g2d.shadowBlur = 10;
          g2d.beginPath();
          g2d.arc(pr.x, pr.y, 6, 0, Math.PI * 2);
          g2d.fill();
          g2d.shadowBlur = 0;
        }
      }

      // 10. Đường đạn (Tracers / Railgun Beams)
      for (let i = tracers.length - 1; i >= 0; i--) {
        const tr = tracers[i];
        tr.life -= dt;
        if (tr.life <= 0) {
          tracers.splice(i, 1);
          continue;
        }
        const alpha = Math.max(0, tr.life / tr.maxLife);
        g2d.save();
        g2d.globalAlpha = alpha;
        g2d.strokeStyle = tr.color;
        g2d.lineWidth = tr.weapon === 'railgun' ? 6.5 * alpha : tr.weapon === 'flamer' ? 9 * alpha : (tr.lv >= 3 ? 3.2 : 2.4);
        if (tr.weapon === 'railgun' || tr.lv >= 3) {
          g2d.shadowColor = tr.color;
          g2d.shadowBlur = tr.weapon === 'railgun' ? 16 : 8;
        }
        g2d.beginPath();
        g2d.moveTo(tr.x1, tr.y1);
        g2d.lineTo(tr.x2, tr.y2);
        g2d.stroke();
        g2d.restore();
      }

      // 11. Sóng xung kích (Shockwaves) & Hạt nổ (Particles)
      for (let i = shockwaves.length - 1; i >= 0; i--) {
        const sw = shockwaves[i];
        sw.life -= dt;
        if (sw.life <= 0) {
          shockwaves.splice(i, 1);
          continue;
        }
        const prog = 1 - sw.life / sw.maxLife;
        const rad = sw.r + (sw.maxR - sw.r) * prog;
        g2d.save();
        g2d.globalAlpha = (1 - prog) * 0.8;
        g2d.strokeStyle = sw.color;
        g2d.lineWidth = 5 * (1 - prog);
        g2d.beginPath();
        g2d.arc(sw.x, sw.y, rad, 0, Math.PI * 2);
        g2d.stroke();
        g2d.restore();
      }

      for (let i = particles.length - 1; i >= 0; i--) {
        const pt = particles[i];
        pt.life -= dt;
        if (pt.life <= 0) {
          particles.splice(i, 1);
          continue;
        }
        pt.x += pt.vx * dt;
        pt.y += pt.vy * dt;
        pt.vx *= 0.92;
        pt.vy *= 0.92;
        g2d.globalAlpha = Math.max(0, pt.life / pt.maxLife);
        g2d.fillStyle = pt.color;
        g2d.beginPath();
        g2d.arc(pt.x, pt.y, pt.size, 0, Math.PI * 2);
        g2d.fill();
      }
      g2d.globalAlpha = 1;

      // 12. Chữ sát thương bay lên
      for (let i = floatTexts.length - 1; i >= 0; i--) {
        const ft = floatTexts[i];
        ft.life -= dt;
        if (ft.life <= 0) {
          floatTexts.splice(i, 1);
          continue;
        }
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

      // 13. Đèn cảnh báo đỏ nhấp nháy 4 góc khi có Boss hoặc Mini-Boss
      if ((state.bosses || []).length > 0 || state.boss) {
        const alarmAlpha = 0.12 + 0.10 * Math.abs(Math.sin(tSec * 4.5));
        for (const [bx, by] of [[30, 30], [aw - 30, 30], [30, ah - 30], [aw - 30, ah - 30]]) {
          const ag = g2d.createRadialGradient(bx, by, 5, bx, by, 140);
          ag.addColorStop(0, `rgba(239, 68, 68, ${alarmAlpha * 2})`);
          ag.addColorStop(1, 'rgba(239, 68, 68, 0)');
          g2d.fillStyle = ag;
          g2d.beginPath();
          g2d.arc(bx, by, 140, 0, Math.PI * 2);
          g2d.fill();
        }
      }

      // 14. Tâm ngắm chiến thuật
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
    const inputTimer = setInterval(() => {
      if (!state || state.status !== 'playing' || !state.you?.mark || shopOpen) return;
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
        vx: Math.max(-1, Math.min(1, vx)),
        vy: Math.max(-1, Math.min(1, vy)),
        aim: +aim.toFixed(3),
        firing: mouseDown,
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
        lastShopKey = '';
        renderShopModal(true);
        return;
      }
      if (shopOpen) {
        if (e.code === 'Escape') {
          shopOpen = false;
          renderShopModal();
        }
        return;
      }
      if (e.code === 'Space' || e.code === 'ShiftLeft') {
        e.preventDefault();
        send('dash');
      } else if (e.code === 'KeyR') {
        send('reload');
      } else if (e.code === 'KeyG') {
        updateMouseWorld();
        const me = (state.survivors || []).find((x) => x.mark === state.you.mark);
        const tx = hasMouseMoved ? mouseWorldX : (me ? me.x + Math.cos(me.aim || 0) * 200 : 700);
        const ty = hasMouseMoved ? mouseWorldY : (me ? me.y + Math.sin(me.aim || 0) * 200 : 450);
        send('grenade', { tx, ty });
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
        send('grenade', { tx: mouseWorldX, ty: mouseWorldY });
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

    window.addEventListener('keydown', onKeyDown);
    window.addEventListener('keyup', onKeyUp);
    canvas.addEventListener('mousemove', onMouseMove);
    canvas.addEventListener('mousedown', onMouseDown);
    window.addEventListener('mouseup', onMouseUp);
    canvas.addEventListener('contextmenu', onContext);

    /* ------------------------------------------- State Sync -------------- */
    function renderState() {
      if (!state) return;
      ctx.setTopbar(...roomTopbar(ctx, state, CHANNEL, t('zombie.title')));

      // Khi bắt đầu ván mới (matchId đổi), dọn sạch xác/vết máu & đồng bộ lại event seq!
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
        renderFinish();
        return;
      }

      if (state.phase === 'shop' && autoShopWave !== state.wave) {
        autoShopWave = state.wave;
        shopOpen = true;
        mouseDown = false;
        lastShopKey = '';
        renderShopModal(true);
      } else if (state.phase === 'wave' && autoShopWave === state.wave - 1 && shopOpen) {
        shopOpen = false;
        renderShopModal();
      }

      ingestEvents(state.events);
      renderHud();
    }

    const stopNet = net.on(CHANNEL, (msg) => {
      if (msg.t === 'state') {
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
      canvas.removeEventListener('mousemove', onMouseMove);
      canvas.removeEventListener('mousedown', onMouseDown);
      window.removeEventListener('mouseup', onMouseUp);
      canvas.removeEventListener('contextmenu', onContext);
      stopNet();
      stopRejoin();
      send('leave');
    };
  },
};

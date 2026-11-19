/* Đêm Tử Thần (Zombie Outbreak) — Game Bắn Súng Sinh Tồn Zombie Multiplayer 1–4 người Co-op & AI Bots.
 * Đồ họa 2.5D Tactical Canvas 60 FPS với Dynamic Flashlight, Particle VFX, Screen Shake,
 * 6 loại súng, 4 lớp Chiến Binh, 6 chủng Zombie + Boss, Cứu đồng đội & Cửa hàng tiếp tế.
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

/* ------------------------------------------- Offscreen Arena Floor Cache -- */
function buildFloorCanvas(mode, w, h) {
  const c = document.createElement('canvas');
  c.width = w;
  c.height = h;
  const g = c.getContext('2d');

  // Nền chính theo chủ đề bản đồ
  const bg = mode === 'lab' ? '#0b141c' : mode === 'endless' ? '#160b0f' : '#11161d';
  g.fillStyle = bg;
  g.fillRect(0, 0, w, h);

  // Lưới gạch bê tông / sàn thép chiến thuật
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

  // Vân nền ngẫu nhiên nhẹ (tạo cảm giác vật liệu thực tế)
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

  // Vòng tròn sân đáp trực thăng / trung tâm chiến thuật
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

  // Viền cảnh báo vàng-đen quanh chu vi bản đồ
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
    let lastEventSeq = 0;
    let lastLobbyKey = '';
    let lastHudKey = '';
    let floorCache = { mode: '', canvas: null };

    // Entity interpolation & visual effects state
    const lerpSurv = new Map();
    const lerpZomb = new Map();
    const tracers = [];
    const particles = [];
    const decals = [];
    const floatTexts = [];
    const shockwaves = [];
    let shakePower = 0;

    // Local input state
    const keys = new Set();
    let mouseScreenX = 0;
    let mouseScreenY = 0;
    let mouseWorldX = 700;
    let mouseWorldY = 450;
    let mouseDown = false;
    let touchMove = { vx: 0, vy: 0 };

    const send = (action, extra = {}) => net.send(CHANNEL, action, extra);

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

    // Mobile virtual action buttons (shown on touch devices via CSS)
    const touchControls = h('div', { class: 'zombie-touch-bar' },
      h('button', { type: 'button', class: 'z-tbtn', onclick: () => send('dash') }, '⚡ Dash'),
      h('button', { type: 'button', class: 'z-tbtn', onclick: () => send('grenade', { tx: mouseWorldX, ty: mouseWorldY }) }, '💣 Bom'),
      h('button', { type: 'button', class: 'z-tbtn', onclick: () => send('turret') }, '🔫 Trụ'),
      h('button', { type: 'button', class: 'z-tbtn', onclick: () => send('reload') }, '🔄 Đạn'),
      h('button', { type: 'button', class: 'z-tbtn', onclick: () => { shopOpen = !shopOpen; renderShopModal(); } }, '🛒 Shop'),
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
      decals.push({ x, y, r, color, alpha: 0.55 });
      if (decals.length > 85) decals.shift();
    }

    function ingestEvents(events) {
      if (!Array.isArray(events)) return;
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
              life: ev.weapon === 'railgun' ? 0.24 : ev.weapon === 'flamer' ? 0.14 : 0.08,
              maxLife: ev.weapon === 'railgun' ? 0.24 : 0.10,
            });
          }
          // Vỏ đạn văng ngang & tia lửa đầu nòng
          if (ev.weapon === 'flamer') {
            addParticles(ev.x, ev.y, 5, '#fb923c', 120, 260, 4, 8, 0.14, 0.28);
          } else {
            addParticles(ev.x, ev.y, ev.weapon === 'shotgun' ? 7 : 3, ev.color || '#fde047', 60, 180, 2, 4, 0.08, 0.18);
          }
          if (ev.mark === state?.you?.mark) {
            if (ev.weapon === 'shotgun') shakePower = Math.max(shakePower, 6.5);
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
          const blood = ev.kind === 'bloater' || ev.kind === 'spitter' ? '#4ade80' : ev.kind === 'boss' ? '#f43f5e' : '#16a34a';
          addDecal(ev.x, ev.y, ev.kind === 'boss' ? 42 : ev.kind === 'brute' ? 24 : 14, blood);
          addParticles(ev.x, ev.y, ev.kind === 'boss' ? 35 : 14, blood, 60, 240, 3, 6.5, 0.25, 0.65);
          if (ev.kind === 'boss') {
            shockwaves.push({ x: ev.x, y: ev.y, r: 20, maxR: 220, color: '#f43f5e', life: 0.5, maxLife: 0.5 });
            shakePower = Math.max(shakePower, 14);
            playBoomSfx();
          }
        } else if (ev.t === 'boom') {
          addDecal(ev.x, ev.y, 44, '#1e293b');
          addParticles(ev.x, ev.y, 32, '#fb923c', 80, 340, 3, 8, 0.22, 0.65);
          addParticles(ev.x, ev.y, 18, '#fef08a', 40, 210, 2, 5, 0.16, 0.45);
          shockwaves.push({ x: ev.x, y: ev.y, r: 16, maxR: ev.radius || 135, color: '#fb923c', life: 0.35, maxLife: 0.35 });
          shakePower = Math.max(shakePower, 13);
          playBoomSfx();
        } else if (ev.t === 'acid') {
          shockwaves.push({ x: ev.x, y: ev.y, r: 12, maxR: ev.radius || 68, color: '#4ade80', life: 0.32, maxLife: 0.32 });
          addParticles(ev.x, ev.y, 16, '#86efac', 40, 150, 3, 6, 0.2, 0.5);
        } else if (ev.t === 'dash') {
          shockwaves.push({ x: ev.x, y: ev.y, r: 8, maxR: 48, color: '#38bdf8', life: 0.22, maxLife: 0.22 });
          addParticles(ev.x, ev.y, 10, '#7dd3fc', 30, 120, 2, 4.5, 0.15, 0.32);
        } else if (ev.t === 'revive') {
          shockwaves.push({ x: ev.x, y: ev.y, r: 10, maxR: 85, color: '#4ade80', life: 0.45, maxLife: 0.45 });
          floatTexts.push({ x: ev.x, y: ev.y - 24, text: '💚 CỨU SỐNG!', color: '#4ade80', big: true, life: 1.1, maxLife: 1.1 });
        } else if (ev.t === 'pickup') {
          const lbl = ev.kind === 'med' ? '+32 HP' : ev.kind === 'ammo' ? '+ĐẠN' : '+$75';
          const col = ev.kind === 'med' ? '#4ade80' : ev.kind === 'ammo' ? '#38bdf8' : '#facc15';
          floatTexts.push({ x: ev.x, y: ev.y - 16, text: lbl, color: col, big: false, life: 0.85, maxLife: 0.85 });
        } else if (ev.t === 'wave') {
          toast(ev.boss ? `⚠️ ĐỢT ${ev.wave} — CHÚA TỂ ĐỘT BIẾN XUẤT HIỆN!` : `☣️ Đợt ${ev.wave} bắt đầu!`, ev.boss ? 'danger' : 'ok');
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
          '⌨️ WASD di chuyển · Chuột ngắm & bắn · 1–6 đổi súng · R thay đạn · Space Lướt né · G Lựu đạn · E Trụ súng · B Cửa hàng'),
        h('button', {
          type: 'button',
          class: 'primary',
          disabled: !seated,
          onclick: () => send('start'),
        }, `🚀 ${t('zombie.startBtn')} (${s.seatedCount || 0}/4)`),
      );

      // Squad seats + Bot management
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
          h('div', { class: 'card-title', style: { margin: '0' } }, `Đội hình (${s.seatedCount || 0}/4)`),
          botSelect),
      );

      for (const m of (s.seatOrder || ['1', '2', '3', '4'])) {
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

    /* ------------------------------------------- Armory Shop Modal ------- */
    function renderShopModal() {
      const s = state;
      if (!s || !shopOpen || !s.inProgress && s.status !== 'playing') {
        shopOverlay.classList.add('hidden');
        return;
      }
      const me = (s.survivors || []).find((x) => x.mark === s.you?.mark);
      if (!me) {
        shopOverlay.classList.add('hidden');
        return;
      }
      shopOverlay.classList.remove('hidden');
      clear(shopOverlay);

      const cat = s.catalog || {};
      const weaponOrder = cat.weaponOrder || ['pistol', 'smg', 'shotgun', 'rifle', 'flamer', 'railgun'];

      const wGrid = h('div', { class: 'zombie-shop-grid' },
        weaponOrder.filter((id) => id !== 'pistol').map((wid) => {
          const w = cat.weapons?.[wid];
          if (!w) return null;
          const owned = (me.weapons || []).includes(wid);
          const cost = owned ? Math.max(80, Math.floor(w.cost / 3)) : w.cost;
          const canBuy = me.money >= cost;
          return h('button', {
            type: 'button',
            class: 'zombie-shop-item' + (owned ? ' owned' : ''),
            disabled: !canBuy,
            onclick: () => send('buy', { item: wid }),
          },
            h('strong', { style: { color: w.color } }, w.name),
            h('span', { class: 'tiny muted' }, `DMG ${w.dmg} · Băng ${w.mag}`),
            h('span', { class: 'chip ' + (canBuy ? 'ok' : '') }, owned ? `Nạp đầy $${cost}` : `Mua $${cost}`));
        }));

      const itemGrid = h('div', { class: 'zombie-shop-grid' },
        Object.entries(cat.items || {}).map(([iid, it]) => {
          const canBuy = me.money >= it.cost;
          return h('button', {
            type: 'button',
            class: 'zombie-shop-item',
            disabled: !canBuy,
            onclick: () => send('buy', { item: iid }),
          },
            h('strong', {}, it.name),
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
            onclick: () => send('buy', { item: pid }),
          },
            h('strong', {}, `${pk.name} (Lv.${cur}/${pk.max})`),
            h('span', { class: 'tiny muted' }, PERK_DESC[pid] || ''),
            h('span', { class: 'chip ' + (canBuy ? 'ok' : '') }, maxed ? 'MAX' : `$${cost}`));
        }));

      const headRight = h('div', { class: 'row', style: { gap: '8px', alignItems: 'center' } },
        h('span', { class: 'chip warn', style: { fontSize: '14px', fontWeight: '700' } }, `💰 $${me.money}`),
        s.phase === 'shop'
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
          : null,
        h('button', {
          type: 'button',
          class: 'sm ghost',
          onclick: () => { shopOpen = false; renderShopModal(); },
        }, 'Đóng (B)'));

      shopOverlay.append(
        h('div', { class: 'zombie-shop-modal card col', style: { gap: '12px' } },
          h('div', { class: 'spread' },
            h('h2', {}, s.phase === 'shop' ? `🛒 Trạm Tiếp Tế — Đợt ${s.wave + 1} sắp bắt đầu` : '🛒 Kho Vũ Khí & Nâng Cấp'),
            headRight),
          h('div', { class: 'small muted', style: { fontWeight: '700' } }, '🔫 Vũ Khí'),
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
      const hudKey = JSON.stringify([
        s.phase, s.wave, s.zombiesLeft, s.totalKills, Math.ceil(s.shopLeft),
        s.boss?.hp,
        (s.survivors || []).map((x) => [x.mark, Math.round(x.hp), Math.round(x.armor), x.downed, x.alive, x.weapon, x.mag?.[x.weapon], x.reserve?.[x.weapon], x.money, x.grenades, x.turrets, x.reloading, x.dashReady > 0]),
      ]);
      if (hudKey === lastHudKey) return;
      lastHudKey = hudKey;

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
          onclick: () => { shopOpen = !shopOpen; renderShopModal(); },
        }, '🛒 Shop (B)'),
        h('button', {
          type: 'button',
          class: 'xs ghost',
          onclick: () => ctx.navigate(CHANNEL),
        }, 'Thoát'),
      );

      if (s.boss) {
        bossHud.classList.remove('hidden');
        const pct = Math.max(0, Math.min(100, (s.boss.hp / Math.max(1, s.boss.maxHp)) * 100));
        mount(bossHud,
          h('div', { class: 'z-boss-label' }, `☠️ CHÚA TỂ ĐỘT BIẾN — ${Math.ceil(s.boss.hp)} / ${Math.ceil(s.boss.maxHp)} HP`),
          h('div', { class: 'z-boss-bar' }, h('div', { class: 'z-boss-fill', style: { width: `${pct}%` } })));
      } else {
        bossHud.classList.add('hidden');
      }

      clear(bottomHud);
      if (me) {
        const wInfo = s.catalog?.weapons?.[me.weapon] || {};
        const curMag = me.mag?.[me.weapon] ?? 0;
        const curRes = me.reserve?.[me.weapon];
        const ammoStr = me.reloading ? 'ĐANG THAY ĐẠN…' : `${curMag} / ${curRes === -1 ? '∞' : (curRes ?? 0)}`;
        const hpPct = Math.max(0, Math.min(100, (me.hp / Math.max(1, me.maxHp)) * 100));
        const arPct = Math.max(0, Math.min(100, (me.armor / Math.max(1, me.maxArmor)) * 100));

        const vitals = h('div', { class: 'z-hud-box z-vitals' },
          h('div', { class: 'spread tiny' },
            h('strong', {}, `❤️ HP ${Math.ceil(me.hp)}/${Math.ceil(me.maxHp)}`),
            h('span', { style: { color: '#38bdf8' } }, `🛡️ ${Math.ceil(me.armor)}`)),
          h('div', { class: 'z-bar hp' }, h('div', { style: { width: `${hpPct}%` } })),
          h('div', { class: 'z-bar armor' }, h('div', { style: { width: `${arPct}%` } })));

        const weaponSlots = h('div', { class: 'z-hud-box z-weapons' },
          h('div', { class: 'spread tiny' },
            h('strong', { style: { color: wInfo.color || '#fde047' } }, wInfo.name || me.weapon),
            h('strong', {}, ammoStr)),
          h('div', { class: 'row', style: { gap: '4px', marginTop: '4px' } },
            (me.weapons || []).map((wid, idx) => h('button', {
              type: 'button',
              class: 'xs ' + (wid === me.weapon ? 'primary' : 'ghost'),
              onclick: () => send('switch', { weapon: wid }),
            }, `${idx + 1}:${wid.toUpperCase()}`))));

        const tactical = h('div', { class: 'z-hud-box z-tactical' },
          h('span', { class: 'chip warn' }, `💰 $${me.money}`),
          h('span', { class: 'chip ' + (me.dashReady <= 0 ? 'ok' : '') }, me.dashReady <= 0 ? '⚡ Dash [Space]' : `⚡ ${me.dashReady}s`),
          h('span', { class: 'chip' }, `💣 ×${me.grenades} [G]`),
          h('span', { class: 'chip' }, `🔫 Trụ ×${me.turrets} [E]`));

        bottomHud.append(vitals, weaponSlots, tactical);
      }

      const squadBox = h('div', { class: 'z-hud-box z-squad' },
        (s.survivors || []).map((sv) => h('div', { class: 'z-squad-row' + (sv.downed ? ' downed' : !sv.alive ? ' dead' : '') },
          h('span', { class: 'geo-dot', style: { background: sv.color } }),
          h('span', { class: 'nowrap', style: { fontSize: '12px', fontWeight: sv.mark === s.you?.mark ? '700' : '500' } }, sv.name),
          h('span', { class: 'tiny muted' }, sv.downed ? `🆘 ${sv.bleedout}s` : !sv.alive ? '💀' : `❤️${Math.ceil(sv.hp)}`),
          h('span', { class: 'tiny', style: { color: '#facc15' } }, `💀${sv.kills}`))));
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
      const rect = canvas.getBoundingClientRect();
      if (!rect.width || !rect.height) return;
      const dpr = window.devicePixelRatio || 1;
      const cx = (mouseScreenX - rect.left) * dpr;
      const cy = (mouseScreenY - rect.top) * dpr;
      const { scale, ox, oy } = getTransform();
      mouseWorldX = (cx - ox) / Math.max(0.01, scale);
      mouseWorldY = (cy - oy) / Math.max(0.01, scale);
    }

    function drawObstacle25D(g, ob, mode, tSec) {
      const { x, y, w, h, kind } = ob;
      // Đổ bóng 2.5D
      g.fillStyle = 'rgba(0,0,0,0.48)';
      g.fillRect(x + 8, y + 10, w, h);

      // Thân khối
      if (kind === 'biotank') {
        const grad = g.createLinearGradient(x, y, x + w, y + h);
        grad.addColorStop(0, '#0f3d4c');
        grad.addColorStop(0.5, '#0e7490');
        grad.addColorStop(1, '#164e63');
        g.fillStyle = grad;
        g.fillRect(x, y, w, h);
        // Bọt sinh học phát sáng bên trong
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

    function drawSurvivor(g, sv, sx, sy, tSec, isMe) {
      g.save();
      g.translate(sx, sy);

      // Hào quang Quân Y (Medic)
      if (sv.cls === 'medic' && sv.alive && !sv.downed) {
        g.strokeStyle = `rgba(74, 222, 128, ${0.18 + 0.08 * Math.sin(tSec * 4)})`;
        g.lineWidth = 2;
        g.beginPath();
        g.arc(0, 0, 140, 0, Math.PI * 2);
        g.stroke();
      }

      if (sv.downed) {
        // Vòng tròn SOS và tiến độ Cứu thương
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

      // Đèn pin chiến thuật (Flashlight Cone)
      if (sv.alive && !sv.downed) {
        g.save();
        g.rotate(sv.aim);
        const fl = g.createRadialGradient(14, 0, 6, 14, 0, 290);
        fl.addColorStop(0, 'rgba(255, 250, 220, 0.24)');
        fl.addColorStop(0.55, 'rgba(255, 245, 200, 0.08)');
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
      g.rotate(sv.aim);
      if (sv.dashing) {
        g.shadowColor = '#38bdf8';
        g.shadowBlur = 16;
      }
      // Vai áo giáp
      g.fillStyle = sv.downed ? '#64748b' : (sv.color || '#38bdf8');
      g.beginPath();
      g.roundRect(-12, -14, 22, 28, 8);
      g.fill();
      g.strokeStyle = isMe ? '#ffffff' : 'rgba(255,255,255,0.45)';
      g.lineWidth = isMe ? 2.2 : 1.3;
      g.stroke();

      // Hình dáng súng theo loại vũ khí đang cầm
      const wid = sv.weapon || 'pistol';
      g.fillStyle = wid === 'railgun' ? '#22d3ee' : wid === 'flamer' ? '#f97316' : '#cbd5e1';
      if (wid === 'shotgun' || wid === 'rifle' || wid === 'railgun') {
        g.fillRect(6, -3, 24, 6);
        g.fillStyle = '#0f172a';
        g.fillRect(10, -2, 8, 4);
      } else if (wid === 'flamer') {
        g.fillRect(6, -4, 22, 8);
        g.fillStyle = '#fbbf24';
        g.fillRect(24, -3, 5, 6);
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
      // Hào quang Boss hoặc Brute đang húc
      if (z.kind === 'boss') {
        const bg = g.createRadialGradient(0, 0, r * 0.4, 0, 0, r * 1.9);
        bg.addColorStop(0, 'rgba(244, 63, 94, 0.42)');
        bg.addColorStop(1, 'rgba(244, 63, 94, 0)');
        g.fillStyle = bg;
        g.beginPath();
        g.arc(0, 0, r * 1.9, 0, Math.PI * 2);
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

      // Màu thân theo chủng loại
      const palette = {
        walker: '#4d7c0f',
        runner: '#dc2626',
        bloater: '#65a30d',
        spitter: '#10b981',
        brute: '#7c2d12',
        boss: '#9f1239',
      };
      g.fillStyle = z.flash ? '#ffffff' : (palette[z.kind] || '#4d7c0f');
      const wobble = Math.sin(tSec * (z.kind === 'runner' ? 14 : 7) + z.id) * 1.4;
      g.beginPath();
      g.arc(0, wobble, r, 0, Math.PI * 2);
      g.fill();
      g.strokeStyle = z.burn ? '#fb923c' : 'rgba(0,0,0,0.6)';
      g.lineWidth = z.burn ? 3 : 2;
      g.stroke();

      // Chi tiết đặc trưng: mụn axit Bloater, gai giáp Brute/Boss, mắt phát sáng
      if (z.kind === 'bloater') {
        g.fillStyle = `rgba(163, 230, 53, ${0.65 + 0.3 * Math.sin(tSec * 8 + z.id)})`;
        g.beginPath();
        g.arc(-6, -4, 6, 0, Math.PI * 2);
        g.arc(7, 4, 5, 0, Math.PI * 2);
        g.fill();
      } else if (z.kind === 'boss' || z.kind === 'brute') {
        g.fillStyle = '#fde047';
        g.beginPath();
        g.arc(-r * 0.28, -r * 0.15, z.kind === 'boss' ? 4.5 : 3, 0, Math.PI * 2);
        g.arc(r * 0.28, -r * 0.15, z.kind === 'boss' ? 4.5 : 3, 0, Math.PI * 2);
        g.fill();
      } else {
        g.fillStyle = z.kind === 'runner' ? '#fef08a' : '#bef264';
        g.beginPath();
        g.arc(-4, -3, 2.2, 0, Math.PI * 2);
        g.arc(4, -3, 2.2, 0, Math.PI * 2);
        g.fill();
      }

      // Thanh máu (chỉ hiện khi đã bị thương hoặc là Brute/Boss)
      if (z.hp < z.maxHp || z.kind === 'brute' || z.kind === 'boss') {
        const bw = Math.max(26, r * 1.7);
        const pct = Math.max(0, Math.min(1, z.hp / Math.max(1, z.maxHp)));
        g.fillStyle = 'rgba(0,0,0,0.7)';
        g.fillRect(-bw / 2, -r - 10, bw, 4);
        g.fillStyle = z.kind === 'boss' ? '#f43f5e' : '#ef4444';
        g.fillRect(-bw / 2, -r - 10, bw * pct, 4);
      }

      g.restore();
    }

    function renderFrame(nowMs) {
      rafId = requestAnimationFrame(renderFrame);
      const dt = Math.min(0.05, Math.max(0.001, (nowMs - lastFrameAt) / 1000));
      lastFrameAt = nowMs;
      if (!state || state.status !== 'playing') return;

      // Đồng bộ kích thước canvas sắc nét theo DPR
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

      // Rung màn hình (Screen Shake)
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

      // 2. Vết máu & vết cháy nổ mờ dần
      for (const d of decals) {
        g2d.globalAlpha = d.alpha;
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

      // 6. Trụ súng Sentry tự động
      for (const tr of (state.turrets || [])) {
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
        g2d.rotate(tr.aim);
        g2d.fillStyle = '#34d399';
        g2d.fillRect(0, -3.5, 20, 7);
        g2d.restore();
      }

      // 7. Nội suy và vẽ Zombie
      const activeZIds = new Set();
      for (const z of (state.zombies || [])) {
        activeZIds.add(z.id);
        let cur = lerpZomb.get(z.id);
        if (!cur) {
          cur = { x: z.x, y: z.y };
          lerpZomb.set(z.id, cur);
        } else {
          const f = Math.min(1, dt * 16);
          cur.x += (z.x - cur.x) * f;
          cur.y += (z.y - cur.y) * f;
        }
        drawZombie(g2d, z, cur.x, cur.y, tSec);
      }
      for (const id of lerpZomb.keys()) {
        if (!activeZIds.has(id)) lerpZomb.delete(id);
      }

      // 8. Nội suy và vẽ Chiến binh
      const activeMarks = new Set();
      for (const sv of (state.survivors || [])) {
        if (!sv.alive) continue;
        activeMarks.add(sv.mark);
        let cur = lerpSurv.get(sv.mark);
        if (!cur) {
          cur = { x: sv.x, y: sv.y };
          lerpSurv.set(sv.mark, cur);
        } else {
          const f = Math.min(1, dt * 18);
          cur.x += (sv.x - cur.x) * f;
          cur.y += (sv.y - cur.y) * f;
        }
        drawSurvivor(g2d, sv, cur.x, cur.y, tSec, sv.mark === state.you?.mark);
      }
      for (const m of lerpSurv.keys()) {
        if (!activeMarks.has(m)) lerpSurv.delete(m);
      }

      // 9. Đạn bay (Lựu đạn & Cầu axit)
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
        g2d.lineWidth = tr.weapon === 'railgun' ? 6 * alpha : tr.weapon === 'flamer' ? 9 * alpha : 2.4;
        if (tr.weapon === 'railgun') {
          g2d.shadowColor = '#22d3ee';
          g2d.shadowBlur = 16;
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

      // 12. Chữ sát thương bay lên (Floating Damage Numbers)
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

      // 13. Đèn cảnh báo đỏ nhấp nháy 4 góc khi có Boss
      if (state.boss) {
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

      // 14. Tâm ngắm chiến thuật (Tactical Crosshair)
      if (!shopOpen && state.you?.mark) {
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
      const aim = Math.atan2(mouseWorldY - curPos.y, mouseWorldX - curPos.x);
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
        renderShopModal();
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
        send('grenade', { tx: mouseWorldX, ty: mouseWorldY });
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
      mouseScreenX = e.clientX;
      mouseScreenY = e.clientY;
      updateMouseWorld();
    };
    const onMouseDown = (e) => {
      if (shopOpen) return;
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
        renderFinish();
        return;
      }

      // Tự mở cửa hàng tiếp tế khi vừa sang pha shop giữa đợt
      if (state.phase === 'shop' && autoShopWave !== state.wave) {
        autoShopWave = state.wave;
        shopOpen = true;
        mouseDown = false;
        renderShopModal();
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

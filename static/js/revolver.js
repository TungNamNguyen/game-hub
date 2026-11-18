/* Khẩu súng lục ổ quay Colt Python .357 Magnum (Sòng Bịp) + Hiệu ứng máu bắn.
 *
 * Chia tách bộ phận rời để CSS tạo chuyển động cơ khí thật:
 *   .rv-body       thân súng (giật ngược khi nổ)
 *   .rv-hammer     búa đập có gai (ngật ra sau lúc xoay, đập mạnh khi bóp cò)
 *   .rv-trigger    cò súng (kéo lùi về sau khi bắn)
 *   .rv-cylinder   đồng hồ ổ đạn 6 ngăn ở góc dưới trái (xoay tròn quanh tâm)
 *   .rv-drum-flute rãnh khía trên ổ đạn thật trong khung súng
 *   .rv-flash      tia lửa đầu nòng 3 lớp + vòng sóng xung kích
 *   .rv-smoke      khói thuốc súng cuộn lên sau phát bắn
 */

import { t } from './i18n.js';

const NS = 'http://www.w3.org/2000/svg';
let COUNTER = 0;

function el(tag, attrs = {}, ...kids) {
  const node = document.createElementNS(NS, tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (value === null || value === undefined || value === false) continue;
    node.setAttribute(key, String(value));
  }
  for (const kid of kids.flat()) if (kid) node.appendChild(kid);
  return node;
}

/** Tâm đồng hồ ổ đạn 6 ngăn (khớp CSS .rv-cylinder { transform-origin: 48px 136px }). */
export const CYLINDER_CENTER = { x: 48, y: 136, radius: 26 };

function chamberSpots() {
  return Array.from({ length: 6 }, (_, i) => {
    const angle = (i * 60 - 90) * Math.PI / 180;
    return {
      index: i,
      x: CYLINDER_CENTER.x + Math.cos(angle) * 15.5,
      y: CYLINDER_CENTER.y + Math.sin(angle) * 15.5,
    };
  });
}

/**
 * Khẩu súng Colt Python .357 Magnum.
 * @param {number} used  số ổ đã bắn
 * @param {number} size  bề rộng hiển thị (px)
 */
export function revolver({ used = 0, size = 340 } = {}) {
  const uid = `rv${++COUNTER}`;
  const spots = chamberSpots();

  const chambers = spots.map((spot) => el('g', {
    class: 'rv-chamber' + (spot.index < used ? ' spent' : ''),
    'data-chamber': spot.index,
  },
    el('circle', {
      cx: spot.x, cy: spot.y, r: 5.8,
      fill: spot.index < used ? '#141210' : `url(#${uid}hole)`,
      stroke: '#09090b', 'stroke-width': 1.2,
    }),
    spot.index < used ? null : el('circle', {
      cx: spot.x, cy: spot.y, r: 2.6, fill: '#d4a145', opacity: 0.95,
    })));

  return el('svg', {
    viewBox: '0 0 320 180',
    width: size,
    height: Math.round(size * 180 / 320),
    class: 'revolver-svg',
    role: 'img',
    'aria-label': t('bluff.revolverAria'),
  },
    el('defs', {},
      el('linearGradient', { id: `${uid}gunmetal`, x1: '0', y1: '0', x2: '0', y2: '1' },
        el('stop', { offset: '0', 'stop-color': '#cbd5e1' }),
        el('stop', { offset: '0.18', 'stop-color': '#64748b' }),
        el('stop', { offset: '0.52', 'stop-color': '#334155' }),
        el('stop', { offset: '0.85', 'stop-color': '#1e293b' }),
        el('stop', { offset: '1', 'stop-color': '#0f172a' })),
      el('linearGradient', { id: `${uid}barrelTop`, x1: '0', y1: '0', x2: '0', y2: '1' },
        el('stop', { offset: '0', 'stop-color': '#e2e8f0' }),
        el('stop', { offset: '0.4', 'stop-color': '#94a3b8' }),
        el('stop', { offset: '1', 'stop-color': '#334155' })),
      el('linearGradient', { id: `${uid}drumSide`, x1: '0', y1: '0', x2: '0', y2: '1' },
        el('stop', { offset: '0', 'stop-color': '#94a3b8' }),
        el('stop', { offset: '0.28', 'stop-color': '#475569' }),
        el('stop', { offset: '0.68', 'stop-color': '#1e293b' }),
        el('stop', { offset: '1', 'stop-color': '#0f172a' })),
      el('linearGradient', { id: `${uid}walnut`, x1: '0', y1: '0', x2: '1', y2: '1' },
        el('stop', { offset: '0', 'stop-color': '#9a5b32' }),
        el('stop', { offset: '0.45', 'stop-color': '#6b3a1e' }),
        el('stop', { offset: '1', 'stop-color': '#3b1d0d' })),
      el('radialGradient', { id: `${uid}hole`, cx: '0.4', cy: '0.35', r: '0.75' },
        el('stop', { offset: '0', 'stop-color': '#475569' }),
        el('stop', { offset: '1', 'stop-color': '#09090b' })),
      el('radialGradient', { id: `${uid}fire`, cx: '0.15', cy: '0.5', r: '0.85' },
        el('stop', { offset: '0', 'stop-color': '#ffffff' }),
        el('stop', { offset: '0.25', 'stop-color': '#fef08a' }),
        el('stop', { offset: '0.6', 'stop-color': '#f97316' }),
        el('stop', { offset: '1', 'stop-color': 'rgba(239,68,68,0)' }))),

    el('g', { class: 'rv-body' },
      // ---- Búa đập có gai (Hammer) ---------------------------------------- //
      el('g', { class: 'rv-hammer' },
        el('path', {
          d: 'M86 58 L76 42 C74 38 78 34 83 36 L91 44 L98 42 L95 58 Z',
          fill: `url(#${uid}gunmetal)`, stroke: '#09090b', 'stroke-width': 1.4, 'stroke-linejoin': 'round',
        }),
        el('path', { d: 'M78 39 L84 36', stroke: '#e2e8f0', 'stroke-width': 1.4, 'stroke-linecap': 'round' })),

      // ---- Báng gỗ óc chó công thái học (Walnut Grip) -------------------- //
      el('path', {
        d: 'M105 84 C94 88 86 98 80 116 L68 150 C66 157 73 163 85 162 C97 161 104 156 106 146 '
         + 'L112 118 C115 106 119 96 122 88 Z',
        fill: `url(#${uid}walnut)`, stroke: '#231006', 'stroke-width': 2.2, 'stroke-linejoin': 'round',
      }),
      // Vân caro nhám + huy hiệu đồng
      el('path', {
        d: 'M88 108 L78 144 M96 108 L86 146 M103 112 L94 146 M82 118 L104 126 M78 130 L100 138 M74 142 L96 148',
        stroke: '#2c1408', 'stroke-width': 1.2, opacity: 0.65,
      }),
      el('circle', { cx: 92, cy: 112, r: 3.4, fill: '#d4a145', stroke: '#451a03', 'stroke-width': 1 }),

      // ---- Cò súng & Vành bảo vệ cò (Trigger & Guard) -------------------- //
      el('path', {
        d: 'M122 88 C119 107 125 119 140 118 C153 117 161 106 160 88',
        fill: 'none', stroke: '#1e293b', 'stroke-width': 5.2, 'stroke-linecap': 'round',
      }),
      el('path', {
        d: 'M122 88 C119 107 125 119 140 118 C153 117 161 106 160 88',
        fill: 'none', stroke: '#64748b', 'stroke-width': 1.6, 'stroke-linecap': 'round',
      }),
      el('g', { class: 'rv-trigger' },
        el('path', {
          d: 'M140 90 C138 99 135 105 131 109 C137 110 142 103 145 90 Z',
          fill: '#cbd5e1', stroke: '#0f172a', 'stroke-width': 1.2,
        })),

      // ---- Khung thép chính (Main Frame) --------------------------------- //
      el('path', {
        d: 'M88 54 C85 50 90 46 98 46 H174 V88 H115 L105 84 C96 82 91 74 91 66 L88 54 Z',
        fill: `url(#${uid}gunmetal)`, stroke: '#09090b', 'stroke-width': 1.8, 'stroke-linejoin': 'round',
      }),
      // Cửa sổ ổ đạn (Cylinder Window cut-out)
      el('rect', {
        x: 112, y: 51, width: 52, height: 32, rx: 3,
        fill: '#0b0f17', stroke: '#09090b', 'stroke-width': 1.4,
      }),

      // ---- Ổ đạn khía rãnh nằm gọn trong khung (Fluted Cylinder) -------- //
      el('g', { class: 'rv-drum' },
        el('rect', {
          x: 114, y: 52, width: 48, height: 30, rx: 4,
          fill: `url(#${uid}drumSide)`, stroke: '#09090b', 'stroke-width': 1.4,
        }),
        el('rect', { x: 117, y: 55, width: 32, height: 5.5, rx: 2.5, fill: '#0f172a', opacity: 0.72 }),
        el('rect', { x: 117, y: 64, width: 32, height: 6.5, rx: 2.5, fill: '#0f172a', opacity: 0.78 }),
        el('rect', { x: 117, y: 74, width: 32, height: 5.5, rx: 2.5, fill: '#0f172a', opacity: 0.72 }),
        el('line', { x1: 156, y1: 52, x2: 156, y2: 82, stroke: '#94a3b8', 'stroke-width': 1.2, opacity: 0.5 })),

      // ---- Nòng súng có thanh tản nhiệt & Underlug (Barrel) -------------- //
      // Thanh gân tản nhiệt trên nòng (Vented Rib)
      el('rect', {
        x: 170, y: 44, width: 112, height: 7, rx: 1.5,
        fill: `url(#${uid}barrelTop)`, stroke: '#09090b', 'stroke-width': 1.3,
      }),
      // Khe thoáng tản nhiệt
      ...[182, 202, 222, 242, 262].map((vx) => el('rect', {
        x: vx, y: 48.5, width: 11, height: 2.8, rx: 1, fill: '#0f172a',
      })),
      // Thân nòng chính + Underlug dài
      el('path', {
        d: 'M172 51 H284 L286 55 V73 L282 76 H172 Z',
        fill: `url(#${uid}gunmetal)`, stroke: '#09090b', 'stroke-width': 1.6, 'stroke-linejoin': 'round',
      }),
      // Rãnh ống đẩy vỏ đạn (Ejector shroud line)
      el('line', { x1: 176, y1: 65, x2: 280, y2: 65, stroke: '#0f172a', 'stroke-width': 1.6 }),
      el('line', { x1: 176, y1: 66.5, x2: 280, y2: 66.5, stroke: '#94a3b8', 'stroke-width': 0.9, opacity: 0.5 }),
      // Đầu ruồi ngắm có vạch cam phản quang
      el('path', { d: 'M268 44 L280 37 L283 44 Z', fill: '#334155', stroke: '#09090b', 'stroke-width': 1.2 }),
      el('path', { d: 'M271 43 L279 38.5', stroke: '#ef4444', 'stroke-width': 2, 'stroke-linecap': 'round' }),
      // Miệng nòng
      el('rect', { x: 284, y: 53, width: 3.5, height: 11, rx: 1, fill: '#09090b' }),

      // ---- Tia lửa đầu nòng 3 lớp & Khói thuốc --------------------------- //
      el('g', { class: 'rv-flash' },
        el('circle', { cx: 292, cy: 59, r: 22, fill: `url(#${uid}fire)` }),
        el('path', {
          d: 'M286 58 L319 30 L302 55 L324 58 L302 62 L319 86 L288 61 Z',
          fill: `url(#${uid}fire)`,
        })),
      el('g', { class: 'rv-smoke' },
        el('circle', { cx: 294, cy: 48, r: 9, fill: '#e2e8f0', opacity: 0.45 }),
        el('circle', { cx: 306, cy: 36, r: 11, fill: '#cbd5e1', opacity: 0.32 }),
        el('circle', { cx: 298, cy: 22, r: 7, fill: '#94a3b8', opacity: 0.24 }))),

    // ---- Đồng hồ ổ đạn 6 ngăn (HUD bên trái để đếm ổ rõ ràng) ---------- //
    el('g', { class: 'rv-dial' },
      el('circle', {
        cx: CYLINDER_CENTER.x, cy: CYLINDER_CENTER.y, r: CYLINDER_CENTER.radius + 3,
        fill: 'rgba(15,23,42,0.85)', stroke: 'rgba(148,163,184,0.35)', 'stroke-width': 1.4,
      }),
      el('g', { class: 'rv-cylinder' },
        el('circle', {
          cx: CYLINDER_CENTER.x, cy: CYLINDER_CENTER.y, r: CYLINDER_CENTER.radius,
          fill: `url(#${uid}drumSide)`, stroke: '#09090b', 'stroke-width': 1.8,
        }),
        ...chambers,
        el('circle', {
          cx: CYLINDER_CENTER.x, cy: CYLINDER_CENTER.y, r: 4,
          fill: '#cbd5e1', stroke: '#09090b', 'stroke-width': 1.2,
        }))));
}

/** Hiệu ứng máu bắn tung tóe (Blood Splatter VFX) khi súng nổ trúng đạn. */
export function bloodSplatter() {
  const uid = `bld${++COUNTER}`;
  return el('svg', {
    viewBox: '0 0 420 280',
    class: 'blood-splatter-svg',
    'aria-hidden': 'true',
  },
    el('defs', {},
      el('radialGradient', { id: `${uid}grad`, cx: '0.45', cy: '0.45', r: '0.6' },
        el('stop', { offset: '0', 'stop-color': '#dc2626' }),
        el('stop', { offset: '0.55', 'stop-color': '#991b1b' }),
        el('stop', { offset: '1', 'stop-color': '#450a0a' }))),
    // Mảng máu văng chính
    el('path', {
      class: 'blood-core',
      d: 'M210 120 C235 90 278 74 302 98 C320 116 296 146 270 156 C292 170 304 198 276 208 '
       + 'C250 218 228 190 214 176 C198 198 166 212 148 192 C132 174 154 146 172 134 '
       + 'C152 114 156 82 184 82 C202 82 204 106 210 120 Z',
      fill: `url(#${uid}grad)`,
    }),
    // Các tia máu văng tốc độ cao & giọt nhỏ
    ...[
      [318, 72, 9], [345, 58, 5], [336, 128, 7], [368, 140, 4], [295, 224, 8],
      [322, 240, 4], [134, 72, 8], [108, 52, 4], [116, 152, 7], [90, 168, 4.5],
      [158, 228, 6.5], [228, 56, 7], [248, 38, 4], [190, 244, 5],
    ].map(([cx, cy, r]) => el('circle', { cx, cy, r, fill: '#b91c1c', opacity: 0.92 })),
    // Giọt máu chảy rỉ xuống
    el('path', { class: 'blood-drip d1', d: 'M184 190 Q186 226 184 258', stroke: '#991b1b', 'stroke-width': 5.5, 'stroke-linecap': 'round', fill: 'none' }),
    el('path', { class: 'blood-drip d2', d: 'M244 184 Q246 224 244 264', stroke: '#b91c1c', 'stroke-width': 4.5, 'stroke-linecap': 'round', fill: 'none' }),
    el('path', { class: 'blood-drip d3', d: 'M278 164 Q280 202 278 238', stroke: '#7f1d1d', 'stroke-width': 4, 'stroke-linecap': 'round', fill: 'none' }));
}

export function chamberStrip(used = 0, total = 6, { dead = false } = {}) {
  const wrap = document.createElement('div');
  wrap.className = 'chambers' + (dead ? ' dead' : '');
  const left = Math.max(0, total - used);
  wrap.title = dead ? t('bluff.eliminated')
    : t('bluff.chamberTitle', {
        used,
        total,
        left,
        pct: left ? Math.round(100 / left) : 100,
      });
  for (let i = 0; i < total; i++) {
    const dot = document.createElement('span');
    dot.className = 'chamber-dot' + (i < used ? ' spent' : '');
    wrap.appendChild(dot);
  }
  return wrap;
}

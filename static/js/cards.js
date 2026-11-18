/* Bộ quân của Sòng Bịp: bốn linh vật vẽ bằng SVG, không ảnh, không font ngoài.
 *
 * Bốn quân — Rồng, Phượng, Hổ, Quỷ — vẽ theo lối HUY HIỆU (con dấu) chứ không
 * tả thực. Lý do rất thực dụng: trên bàn chơi quân chỉ rộng 56-96px, mà nét tả
 * thực ở cỡ đó biến thành một vệt mờ. Hình khối dứt khoát, ít chi tiết, nét dày
 * thì cỡ nào cũng đọc ra ngay là con gì.
 *
 * Mặt quân màu ngà trên bàn nỉ xanh sẫm: đó là tương phản mạnh nhất, và cũng
 * là cách bộ quân thật vẫn dùng. Mặt sau màu huyết đỏ + hoa văn vàng để úp
 * xuống bàn vẫn thấy rõ "đây là một quân đang úp".
 *
 * Mỗi SVG tự sinh id gradient riêng (COUNTER) vì trên bàn có thể có 20 quân
 * cùng lúc; trùng id thì mọi quân sẽ ăn chung một gradient của quân đầu tiên.
 */

import { rankNameI18n, t } from './i18n.js';

const NS = 'http://www.w3.org/2000/svg';
let COUNTER = 0;

function el(tag, attrs = {}, ...kids) {
  const node = document.createElementNS(NS, tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (value === null || value === undefined || value === false) continue;
    node.setAttribute(key, String(value));
  }
  for (const kid of kids.flat()) {
    if (kid) node.appendChild(kid);
  }
  return node;
}

/** Nhiều path cùng kiểu nét — viết gọn cho phần vẽ linh vật. */
function strokes(paths, attrs = {}) {
  return paths.map((d) => el('path', { d, fill: 'none', ...attrs }));
}

/* ======================================================= dữ liệu về quân === */

export const RANKS = ['DRAGON', 'PHOENIX', 'TIGER', 'DEMON', 'DEVIL'];

export const RANK_META = {
  DRAGON: {
    name: 'Rồng', short: 'R',
    ink: '#0f766e', ink2: '#115e59', glow: 'rgba(20,184,166,0.5)',
  },
  PHOENIX: {
    name: 'Phượng', short: 'P',
    ink: '#be123c', ink2: '#9f1239', glow: 'rgba(244,63,94,0.5)',
  },
  TIGER: {
    name: 'Hổ', short: 'H',
    ink: '#b45309', ink2: '#92400e', glow: 'rgba(245,158,11,0.5)',
  },
  DEMON: {
    name: 'Quỷ', short: 'Q',
    ink: '#6d28d9', ink2: '#5b21b6', glow: 'rgba(139,92,246,0.55)',
  },
  // Ma Vương: máu đọng gần như đen. Bốn quân kia đã chiếm lam / đỏ tươi / hổ
  // phách / tím, nên quân thứ năm phải là màu TỐI để không lẫn với Phượng ở cỡ
  // 56px — cùng họ đỏ nhưng khác hẳn độ sáng thì mắt phân biệt được ngay.
  // ``ink`` (mặt) phải SÁNG hơn ``ink2`` (sừng) rõ rệt, khác các quân kia chỉ
  // lệch nhau một chút: cả sừng cừu lẫn mặt đều là khối lớn nằm sát nhau, cùng
  // sắc thì ở cỡ 56px chúng dính thành một bóng đen không đọc ra hình gì.
  DEVIL: {
    name: 'Ma Vương', short: 'M',
    ink: '#6b1220', ink2: '#1c0409', glow: 'rgba(220,38,38,0.62)',
  },
};

export function rankName(rank) {
  return rankNameI18n(rank) || (RANK_META[rank] || {}).name || rank || '?';
}

/* ====================================================== hình bốn linh vật == */
/* Mọi hình vẽ trong hộp 0 0 100 100, gốc toạ độ ở góc trên bên trái, để hàm
 * emblem() đặt vào đâu cũng được bằng một phép translate + scale. */

function tigerArt(meta) {
  // Mặt hổ nhìn chính diện. Nhận ra bằng: hai tai tròn, vệt vằn trên trán, mũi
  // tam giác, râu. Đây là con dễ nhận nhất trong bốn con nên vẽ thẳng mặt.
  const w = { stroke: meta.ink2, 'stroke-width': 3.2, 'stroke-linecap': 'round',
              'stroke-linejoin': 'round' };
  return [
    // tai
    el('path', { d: 'M30 30 C20 24 16 12 26 10 C34 9 38 18 37 27 Z', fill: meta.ink }),
    el('path', { d: 'M70 30 C80 24 84 12 74 10 C66 9 62 18 63 27 Z', fill: meta.ink }),
    el('path', { d: 'M30 26 C25 22 24 16 28 15 C32 15 34 20 33 25 Z', fill: '#fdf6e3' }),
    el('path', { d: 'M70 26 C75 22 76 16 72 15 C68 15 66 20 67 25 Z', fill: '#fdf6e3' }),
    // đầu
    el('path', {
      d: 'M50 92 C30 92 19 76 20 56 C21 38 33 26 50 26 C67 26 79 38 80 56 '
       + 'C81 76 70 92 50 92 Z',
      fill: meta.ink,
    }),
    // vằn trán + má, vẽ bằng màu ngà để nổi trên nền lông
    ...strokes([
      'M50 28 V44', 'M40 31 L36 46', 'M60 31 L64 46',
      'M22 54 H33', 'M23 62 H32', 'M78 54 H67', 'M77 62 H68',
    ], { stroke: '#fdf6e3', 'stroke-width': 2.6, 'stroke-linecap': 'round' }),
    // mắt
    el('ellipse', { cx: 38, cy: 56, rx: 7, ry: 5.6, fill: '#fdf6e3' }),
    el('ellipse', { cx: 62, cy: 56, rx: 7, ry: 5.6, fill: '#fdf6e3' }),
    el('circle', { cx: 38.5, cy: 56, r: 2.7, fill: '#1c1917' }),
    el('circle', { cx: 61.5, cy: 56, r: 2.7, fill: '#1c1917' }),
    // mũi + miệng
    el('path', { d: 'M43 68 Q50 63 57 68 Q50 75 43 68 Z', fill: '#fdf6e3' }),
    ...strokes(['M50 75 V79', 'M50 79 Q42 85 35 78', 'M50 79 Q58 85 65 78'], w),
    // râu
    ...strokes(['M34 72 L16 69', 'M34 76 L16 80', 'M66 72 L84 69', 'M66 76 L84 80'],
      { stroke: meta.ink2, 'stroke-width': 2, 'stroke-linecap': 'round' }),
  ];
}

function dragonArt(meta) {
  // Rồng phương Đông, đầu nhìn ngang sang phải, thân cuộn một vòng bên dưới.
  // Dấu hiệu nhận dạng: sừng vắt ra sau, bờm gai, râu mép dài, thân uốn.
  const line = { stroke: meta.ink2, 'stroke-width': 2.6, 'stroke-linecap': 'round',
                 'stroke-linejoin': 'round' };
  return [
    // thân cuộn
    el('path', {
      d: 'M40 62 C22 64 14 80 26 90 C38 98 56 92 58 78',
      fill: 'none', stroke: meta.ink, 'stroke-width': 9, 'stroke-linecap': 'round',
    }),
    // vảy trên thân
    ...strokes(['M28 66 L26 60', 'M20 76 L14 74', 'M26 88 L22 94', 'M42 94 L44 100'],
      { stroke: meta.ink2, 'stroke-width': 2.4, 'stroke-linecap': 'round' }),
    // sừng
    el('path', {
      d: 'M56 22 C50 12 38 6 28 8 C38 12 46 18 52 27 Z', fill: meta.ink2,
    }),
    // bờm gai sau đầu
    el('path', {
      d: 'M50 30 L38 26 L46 36 L34 36 L44 44 L34 48 L46 52 Z', fill: meta.ink2,
    }),
    // đầu + hàm
    el('path', {
      d: 'M52 24 C68 24 80 34 82 46 C83 54 79 60 72 62 L58 64 C50 65 46 70 46 76 '
       + 'L38 70 C36 58 42 46 52 40 Z',
      fill: meta.ink,
    }),
    // mõm nhô ra trước
    el('path', { d: 'M78 52 L94 56 L78 62 Z', fill: meta.ink }),
    ...strokes(['M80 57 H90'], { stroke: '#fdf6e3', 'stroke-width': 2 }),
    // mắt
    el('ellipse', { cx: 66, cy: 40, rx: 6, ry: 5, fill: '#fdf6e3' }),
    el('circle', { cx: 67, cy: 40, r: 2.4, fill: '#1c1917' }),
    // lỗ mũi
    el('circle', { cx: 80, cy: 49, r: 1.7, fill: '#fdf6e3' }),
    // răng
    el('path', { d: 'M62 64 L64 70 L67 64 Z', fill: '#fdf6e3' }),
    el('path', { d: 'M70 63 L72 68 L75 62 Z', fill: '#fdf6e3' }),
    // râu mép
    ...strokes(['M84 62 C88 72 86 84 78 92', 'M58 66 C54 76 56 86 62 92'], line),
  ];
}

function phoenixArt(meta) {
  // Phượng, đầu nhìn ngang sang phải, ba chiếc mào vắt ra sau và đuôi xoè.
  const plume = { stroke: meta.ink, 'stroke-width': 3.4, 'stroke-linecap': 'round' };
  return [
    // đuôi xoè phía dưới bên trái
    ...strokes([
      'M46 62 C32 68 22 82 18 96', 'M48 66 C38 76 34 86 34 98',
      'M50 70 C46 80 48 90 54 98',
    ], { stroke: meta.ink, 'stroke-width': 4.2, 'stroke-linecap': 'round' }),
    // Mào: ba nét vắt về sau. Mọi điểm phải nằm trong hộp 0-100 — bản đầu cho
    // nét trên cùng chạy tới y = -2 nên khi đặt vào huy hiệu thì mào chọc ra
    // ngoài vành tròn.
    ...strokes([
      'M56 32 C46 20 32 14 20 18 C32 22 42 26 50 34',
      'M59 28 C53 16 44 8 32 6 C40 14 48 22 52 30',
      'M63 27 C63 16 58 8 51 3 C55 13 58 20 59 29',
    ], plume),
    // thân + cổ
    el('path', {
      d: 'M54 36 C60 28 72 26 78 32 C82 37 80 45 74 48 L62 54 C55 58 51 66 51 74 '
       + 'L42 68 C40 56 45 44 54 36 Z',
      fill: meta.ink,
    }),
    // cánh
    el('path', {
      d: 'M52 56 C64 58 74 66 78 78 C68 72 58 66 50 64 Z', fill: meta.ink2,
    }),
    ...strokes(['M56 60 L66 70', 'M60 58 L70 66'],
      { stroke: '#fdf6e3', 'stroke-width': 1.8, 'stroke-linecap': 'round' }),
    // mỏ
    el('path', { d: 'M78 34 L96 40 L78 46 Z', fill: '#f59e0b' }),
    ...strokes(['M80 40 H92'], { stroke: meta.ink2, 'stroke-width': 1.6 }),
    // mắt
    el('ellipse', { cx: 70, cy: 36, rx: 5, ry: 4.4, fill: '#fdf6e3' }),
    el('circle', { cx: 70.6, cy: 36, r: 2.1, fill: '#1c1917' }),
  ];
}

function demonArt(meta) {
  // Mặt nạ quỷ: hai sừng, mắt xếch, nanh. Đây là quân chủ bài (luôn tính là
  // thật) nên vẽ dữ nhất bàn, để bốc được lên là biết mình vừa gặp may.
  return [
    // sừng
    el('path', {
      d: 'M28 34 C16 24 14 10 24 4 C28 14 32 24 38 32 Z', fill: meta.ink2,
    }),
    el('path', {
      d: 'M72 34 C84 24 86 10 76 4 C72 14 68 24 62 32 Z', fill: meta.ink2,
    }),
    // mặt nạ
    el('path', {
      d: 'M50 95 C33 95 23 80 23 60 C23 42 34 30 50 30 C66 30 77 42 77 60 '
       + 'C77 80 67 95 50 95 Z',
      fill: meta.ink,
    }),
    // mắt xếch
    el('path', { d: 'M31 54 L47 58 L33 64 Z', fill: '#fde68a' }),
    el('path', { d: 'M69 54 L53 58 L67 64 Z', fill: '#fde68a' }),
    el('circle', { cx: 38, cy: 59, r: 2.4, fill: '#1c1917' }),
    el('circle', { cx: 62, cy: 59, r: 2.4, fill: '#1c1917' }),
    // chân mày
    ...strokes(['M28 48 L46 53', 'M72 48 L54 53'],
      { stroke: '#fde68a', 'stroke-width': 3, 'stroke-linecap': 'round' }),
    // mũi
    el('path', { d: 'M50 62 L45 74 H55 Z', fill: meta.ink2 }),
    // miệng nhăn + nanh
    el('path', {
      d: 'M33 77 Q50 90 67 77 Q50 82 33 77 Z', fill: '#fdf6e3',
    }),
    el('path', { d: 'M39 79 L42 87 L45 79 Z', fill: '#fdf6e3' }),
    el('path', { d: 'M55 79 L58 87 L61 79 Z', fill: '#fdf6e3' }),
    // vệt má
    ...strokes(['M27 68 L34 71', 'M73 68 L66 71'],
      { stroke: '#fde68a', 'stroke-width': 2.2, 'stroke-linecap': 'round' }),
  ];
}

function devilArt(meta) {
  // Ma Vương. Phải phân biệt được với Quỷ NGAY Ở CỠ NHỎ, vì hai quân này cùng
  // họ "mặt nạ có sừng" và người chơi phải quyết định trong 30 giây. Ba dấu
  // hiệu tách hẳn khỏi Quỷ:
  //   - sừng CỪU cuộn vòng ra hai bên, thay vì sừng nhọn chọc lên;
  //   - vương miện lửa giữa hai sừng (Quỷ không có gì ở đó);
  //   - con ngươi là khe DỌC, mặt dài hình tam giác ngược thay vì mặt bầu.
  const flame = (cx, cy, scale, fill) => el('path', {
    d: 'M0 -12 C5 -4 8 0 4 5 C1 8 -4 8 -5 3 C-6 -2 -2 -6 0 -12 Z',
    transform: `translate(${cx} ${cy}) scale(${scale})`,
    fill,
  });
  return [
    // sừng cừu, cuộn ra ngoài rồi vòng xuống
    el('path', {
      d: 'M35 31 C26 21 13 18 7 27 C1 37 8 48 18 47 '
       + 'C11 43 8 35 12 30 C18 23 28 25 34 33 Z',
      fill: meta.ink2,
    }),
    el('path', {
      d: 'M65 31 C74 21 87 18 93 27 C99 37 92 48 82 47 '
       + 'C89 43 92 35 88 30 C82 23 72 25 66 33 Z',
      fill: meta.ink2,
    }),
    // Vương miện lửa: ba ngọn, ngọn giữa cao nhất. Lõi hổ phách phải đủ to mới
    // thấy — ngọn lửa màu sừng nằm cạnh sừng thì coi như không có.
    flame(40, 31, 0.72, meta.ink2),
    flame(40, 31, 0.42, '#f59e0b'),
    flame(60, 31, 0.72, meta.ink2),
    flame(60, 31, 0.42, '#f59e0b'),
    flame(50, 26, 1.05, meta.ink2),
    flame(50, 26, 0.66, '#fbbf24'),
    // mặt: tam giác ngược, hàm nhọn
    el('path', {
      d: 'M50 96 C40 88 30 76 28 60 C27 48 36 38 50 38 '
       + 'C64 38 73 48 72 60 C70 76 60 88 50 96 Z',
      fill: meta.ink,
    }),
    // mắt hạnh nhân, con ngươi khe dọc như mắt dê
    el('path', { d: 'M32 60 Q39 54 47 60 Q39 66 32 60 Z', fill: '#fbbf24' }),
    el('path', { d: 'M68 60 Q61 54 53 60 Q61 66 68 60 Z', fill: '#fbbf24' }),
    el('ellipse', { cx: 39.5, cy: 60, rx: 1.5, ry: 3.4, fill: '#170406' }),
    el('ellipse', { cx: 60.5, cy: 60, rx: 1.5, ry: 3.4, fill: '#170406' }),
    // chân mày chữ V, đổ dốc vào giữa
    ...strokes(['M30 52 L45 57', 'M70 52 L55 57'],
      { stroke: '#fbbf24', 'stroke-width': 3, 'stroke-linecap': 'round' }),
    // mũi mảnh
    el('path', { d: 'M50 68 L47 77 H53 Z', fill: meta.ink2 }),
    // miệng nhăn + hai nanh dài hơn của Quỷ, chọc xuống gần hết hàm
    el('path', { d: 'M36 80 Q50 88 64 80 Q50 92 36 80 Z', fill: '#fdf6e3' }),
    el('path', { d: 'M41 82 L44 93 L47 82 Z', fill: '#fdf6e3' }),
    el('path', { d: 'M53 82 L56 93 L59 82 Z', fill: '#fdf6e3' }),
    // vết nứt rực trên má
    ...strokes(['M31 70 L37 73', 'M69 70 L63 73'],
      { stroke: '#f59e0b', 'stroke-width': 2.2, 'stroke-linecap': 'round' }),
  ];
}

const ART = {
  DRAGON: dragonArt, PHOENIX: phoenixArt, TIGER: tigerArt, DEMON: demonArt,
  DEVIL: devilArt,
};

/** Chỉ riêng hình linh vật, đặt gọn trong ô vuông ``size``. */
export function emblem(rank, size = 48) {
  const meta = RANK_META[rank] || RANK_META.DRAGON;
  const svg = el('svg', {
    viewBox: '0 0 100 100', width: size, height: size,
    class: 'emblem', 'aria-hidden': 'true',
  }, ...(ART[rank] || dragonArt)(meta));
  return svg;
}

/* ============================================================== mặt quân === */

/** Một mặt quân ngửa. ``size`` là bề rộng; chiều cao theo tỉ lệ 1:1.4. */
export function cardFace(rank, { size = 70, className = '' } = {}) {
  const meta = RANK_META[rank] || RANK_META.DRAGON;
  const uid = `cf${++COUNTER}`;
  const svg = el('svg', {
    viewBox: '0 0 140 196', width: size, height: Math.round(size * 1.4),
    // Lớp theo quân để CSS nhấn được một quân cụ thể mà không phải đọc SVG —
    // Ma Vương cần viền rực để trên tay không bao giờ bị nhặt nhầm.
    class: `card-svg card-r-${RANK_META[rank] ? rank : 'DRAGON'}`
      + (className ? ' ' + className : ''),
    role: 'img', 'aria-label': meta.name,
  },
    el('defs', {},
      el('linearGradient', { id: `${uid}p`, x1: '0', y1: '0', x2: '0.4', y2: '1' },
        el('stop', { offset: '0', 'stop-color': '#fffdf5' }),
        el('stop', { offset: '1', 'stop-color': '#f0e6cf' })),
      el('radialGradient', { id: `${uid}m`, cx: '0.5', cy: '0.42', r: '0.62' },
        el('stop', { offset: '0', 'stop-color': '#fffef8' }),
        el('stop', { offset: '1', 'stop-color': '#e8dcc0' }))),
    // giấy
    el('rect', { x: 1, y: 1, width: 138, height: 194, rx: 12,
                 fill: `url(#${uid}p)`, stroke: '#cbb894', 'stroke-width': 2 }),
    // khung kép
    el('rect', { x: 8.5, y: 8.5, width: 123, height: 179, rx: 8,
                 fill: 'none', stroke: meta.ink, 'stroke-width': 1.6,
                 opacity: 0.55 }),
    el('rect', { x: 12.5, y: 12.5, width: 115, height: 171, rx: 6,
                 fill: 'none', stroke: meta.ink, 'stroke-width': 0.8,
                 opacity: 0.3 }),
    // bốn hoa văn góc
    ...[[20, 20, 1, 1], [120, 20, -1, 1], [20, 176, 1, -1], [120, 176, -1, -1]]
      .map(([x, y, sx, sy]) => el('path', {
        d: 'M0 10 L0 3 Q0 0 3 0 L10 0',
        transform: `translate(${x} ${y}) scale(${sx} ${sy})`,
        fill: 'none', stroke: meta.ink, 'stroke-width': 2,
        'stroke-linecap': 'round', opacity: 0.75,
      })),
    // huy hiệu giữa
    el('circle', { cx: 70, cy: 88, r: 42, fill: `url(#${uid}m)`,
                   stroke: meta.ink, 'stroke-width': 1.4, opacity: 0.95 }),
    el('circle', { cx: 70, cy: 88, r: 37, fill: 'none', stroke: meta.ink,
                   'stroke-width': 0.7, opacity: 0.4 }),
    el('g', { transform: 'translate(32 50) scale(0.76)' },
      ...(ART[rank] || dragonArt)(meta)),
    // Tên quân dưới chân. Cỡ 14 chứ không phải 19: ở 19 thì "PHƯỢNG" rộng ~100
    // đơn vị trên lá 140 đơn vị, tức là tràn qua cả khung trong.
    el('text', {
      x: 70, y: 173, 'text-anchor': 'middle', fill: meta.ink2,
      'font-size': 14, 'font-weight': '700', 'letter-spacing': '0.6',
      'font-family': 'system-ui, sans-serif',
    }, document.createTextNode(meta.name.toUpperCase())),
    // Ký hiệu hai góc chéo nhau như quân thật. Góc dưới đặt ở y=141 (ngang hông
    // huy hiệu) chứ không phải y=152: ở 152 nó nằm đúng cạnh dòng tên và đọc ra
    // thành "HỔ H".
    cornerMark(rank, meta, 26, 33, false),
    cornerMark(rank, meta, 112, 141, true));
  return svg;
}

function cornerMark(rank, meta, x, y, flipped) {
  return el('g', {
    transform: `translate(${x} ${y})${flipped ? ' rotate(180)' : ''}`,
  },
    el('text', {
      x: 0, y: 0, 'text-anchor': 'middle', fill: meta.ink2,
      'font-size': 21, 'font-weight': '800',
      'font-family': 'system-ui, sans-serif',
    }, document.createTextNode(meta.short)),
    el('g', { transform: 'translate(-7 4) scale(0.14)' },
      ...(ART[rank] || dragonArt)(meta)));
}

/** Mặt sau quân. Dùng cho quân trên tay người khác và chồng quân giữa bàn. */
export function cardBack({ size = 70, className = '' } = {}) {
  const uid = `cb${++COUNTER}`;
  const lattice = [];
  // Hoa văn: hai chùm đường chéo cắt nhau, đủ dày để úp xuống trông "có ruột"
  // mà vẫn nhẹ (chỉ ~24 nét cho mỗi quân).
  for (let i = -3; i <= 9; i++) {
    lattice.push(el('path', {
      d: `M${i * 20 - 10} 0 L${i * 20 + 186} 196`,
      stroke: '#f5c451', 'stroke-width': 1, opacity: 0.22, fill: 'none',
    }));
    lattice.push(el('path', {
      d: `M${i * 20 - 10} 196 L${i * 20 + 186} 0`,
      stroke: '#f5c451', 'stroke-width': 1, opacity: 0.22, fill: 'none',
    }));
  }
  return el('svg', {
    viewBox: '0 0 140 196', width: size, height: Math.round(size * 1.4),
    class: 'card-svg card-back' + (className ? ' ' + className : ''),
    role: 'img', 'aria-label': t('bluff.cardBackAria'),
  },
    el('defs', {},
      el('linearGradient', { id: `${uid}b`, x1: '0', y1: '0', x2: '0.5', y2: '1' },
        el('stop', { offset: '0', 'stop-color': '#7f1d1d' }),
        el('stop', { offset: '1', 'stop-color': '#450a0a' })),
      el('clipPath', { id: `${uid}c` },
        el('rect', { x: 10, y: 10, width: 120, height: 176, rx: 7 }))),
    el('rect', { x: 1, y: 1, width: 138, height: 194, rx: 12,
                 fill: `url(#${uid}b)`, stroke: '#f5c451', 'stroke-width': 2 }),
    el('g', { 'clip-path': `url(#${uid}c)` }, ...lattice),
    el('rect', { x: 10, y: 10, width: 120, height: 176, rx: 7, fill: 'none',
                 stroke: '#f5c451', 'stroke-width': 1.5, opacity: 0.8 }),
    // huy hiệu giữa: hình thoi lồng chữ SB
    el('path', { d: 'M70 58 L104 98 L70 138 L36 98 Z', fill: '#450a0a',
                 stroke: '#f5c451', 'stroke-width': 2 }),
    el('path', { d: 'M70 70 L94 98 L70 126 L46 98 Z', fill: 'none',
                 stroke: '#f5c451', 'stroke-width': 1, opacity: 0.6 }),
    el('text', {
      x: 70, y: 106, 'text-anchor': 'middle', fill: '#f5c451',
      'font-size': 26, 'font-weight': '800', 'letter-spacing': '1',
      'font-family': 'system-ui, sans-serif',
    }, document.createTextNode('SB')));
}

/** Lá quân chủ: to, có vành như một tấm huy chương treo giữa bàn. */
export function tableCard(rank, { size = 104 } = {}) {
  const meta = RANK_META[rank] || RANK_META.DRAGON;
  const uid = `tc${++COUNTER}`;
  return el('svg', {
    viewBox: '0 0 120 120', width: size, height: size,
    class: 'table-card-svg', role: 'img',
    'aria-label': t('bluff.tableCardAria', { name: rankNameI18n(rank) }),
  },
    el('defs', {},
      el('radialGradient', { id: `${uid}g`, cx: '0.5', cy: '0.4', r: '0.65' },
        el('stop', { offset: '0', 'stop-color': '#fffdf3' }),
        el('stop', { offset: '1', 'stop-color': '#e6d8b6' }))),
    el('circle', { cx: 60, cy: 60, r: 57, fill: `url(#${uid}g)`,
                   stroke: meta.ink, 'stroke-width': 3 }),
    el('circle', { cx: 60, cy: 60, r: 50, fill: 'none', stroke: meta.ink,
                   'stroke-width': 1, opacity: 0.45 }),
    // 12 vạch quanh vành, như khía trên đồng xu
    ...Array.from({ length: 12 }, (_, i) => el('path', {
      d: 'M60 5 V11',
      transform: `rotate(${i * 30} 60 60)`,
      stroke: meta.ink, 'stroke-width': 2, opacity: 0.5,
      'stroke-linecap': 'round',
    })),
    el('g', { transform: 'translate(24 20) scale(0.72)' },
      ...(ART[rank] || dragonArt)(meta)));
}

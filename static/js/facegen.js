/* Sinh mặt người ngẫu nhiên, hoàn toàn offline.
 *
 * CÁCH HOẠT ĐỘNG: mỗi khuôn mặt là một "mô tả" (descriptor) gồm chỉ số của
 * từng đặc điểm — da số 3, tóc số 7, mắt số 2... Từ mô tả đó sinh ra một DANH
 * SÁCH HÌNH (display list) gồm các khối cơ bản, rồi có hai bộ xuất đọc cùng
 * danh sách đó: một dựng SVG để xem trước, một vẽ lên canvas để xuất PNG.
 *
 * VÌ SAO TÁCH RA DISPLAY LIST thay vì dựng SVG rồi vẽ SVG đó lên canvas: một
 * số trình duyệt coi canvas đã "nhiễm bẩn" sau khi vẽ ảnh SVG lên, làm
 * toBlob() ném lỗi bảo mật và không xuất được PNG. Vẽ trực tiếp bằng Path2D
 * thì không bao giờ gặp chuyện đó, mà vẫn không phải vẽ hình hai lần.
 *
 * VÌ SAO HÌNH ĐẮP TỪ KHỐI CƠ BẢN (circle/ellipse/cung tròn) chứ không phải
 * path nhiều điểm điều khiển: toàn bộ hình ở đây được viết mà không nhìn được
 * bản render, nên phải là thứ tính được bằng toán. Ví dụ mái tóc dùng đúng
 * cung của hộp sọ (A40 46) nên chắc chắn ôm khít đầu, không lệch.
 *
 * MÃ KHUÔN MẶT: mô tả được đóng gói thành một số theo hệ cơ số trộn rồi ghi ra
 * base36 (~9 ký tự). Đây là song ánh — cùng một mã luôn cho lại đúng một mặt,
 * và mọi tổ hợp đều có mã. Tích các chiều ~2·10^13, vẫn dưới 2^53 nên số
 * nguyên JavaScript biểu diễn chính xác, không sai số.
 */

/* ========================================================== hình học ===== */
// Khung thiết kế 200x200. Đầu là ellipse tâm (100,86) bán trục 40x46, nên
// đỉnh sọ y=40, đáy hàm y=132, mép trái x=60, mép phải x=140.
const HEAD = { cx: 100, cy: 86, rx: 40, ry: 46 };
const EYE_Y = 86;
const EYE_L = 84;
const EYE_R = 116;
// 74 chứ không phải 71: ở 71 thì mày chạm chân tóc, hai nét dính vào nhau
// trông như một vệt dày.
const BROW_Y = 74;
const NOSE_Y = 92;
const MOUTH_Y = 112;

// Cung nửa trên hộp sọ, từ mép trái sang mép phải. Mọi kiểu tóc "ốp đầu" đều
// bắt đầu bằng cung này nên không bao giờ lệch khỏi sọ.
const SKULL_TOP = `M60 86 A${HEAD.rx} ${HEAD.ry} 0 0 1 140 86`;

/** Đường path của hình chữ nhật bo góc. Có hàm này thì bộ xuất chỉ cần biết
 *  ba loại hình (path, circle, ellipse), khỏi phụ thuộc ctx.roundRect. */
function rrect(x, y, w, h, r) {
  const k = Math.min(r, w / 2, h / 2);
  return `M${x + k} ${y} h${w - 2 * k} a${k} ${k} 0 0 1 ${k} ${k}`
       + ` v${h - 2 * k} a${k} ${k} 0 0 1 ${-k} ${k}`
       + ` h${-(w - 2 * k)} a${k} ${k} 0 0 1 ${-k} ${-k}`
       + ` v${-(h - 2 * k)} a${k} ${k} 0 0 1 ${k} ${-k} Z`;
}

/** Độ sáng cảm nhận của màu, 0..255. Dùng để biết màu có quá nhạt hay không. */
function luminance(hex) {
  const n = parseInt(hex.slice(1), 16);
  return 0.299 * ((n >> 16) & 255) + 0.587 * ((n >> 8) & 255) + 0.114 * (n & 255);
}

/** Pha màu hex sáng/tối hơn. amount > 0 là sáng lên, < 0 là tối đi. */
function shade(hex, amount) {
  const n = parseInt(hex.slice(1), 16);
  const mix = (c) => {
    const v = amount >= 0 ? c + (255 - c) * amount : c * (1 + amount);
    return Math.max(0, Math.min(255, Math.round(v)));
  };
  const r = mix((n >> 16) & 255);
  const g = mix((n >> 8) & 255);
  const b = mix(n & 255);
  return '#' + ((1 << 24) | (r << 16) | (g << 8) | b).toString(16).slice(1);
}

/* ========================================================= bảng chọn ===== */
export const SKINS = [
  { name: 'rất sáng', base: '#fae3d2' },
  { name: 'sáng', base: '#f3d5c0' },
  { name: 'sáng ấm', base: '#e8b894' },
  { name: 'vừa', base: '#dda87a' },
  { name: 'rám nắng', base: '#c98c5e' },
  { name: 'nâu', base: '#b07a52' },
  { name: 'nâu đậm', base: '#8d5a3b' },
  { name: 'nâu sẫm', base: '#6b4230' },
];

export const AGES = [
  { id: 'young', name: 'trẻ' },
  { id: 'mid', name: 'trung niên' },
  { id: 'old', name: 'lớn tuổi' },
];

export const HAIR_COLORS = [
  { name: 'đen', hex: '#2a2320' },
  { name: 'nâu đậm', hex: '#4a3728' },
  { name: 'nâu', hex: '#7a5230' },
  { name: 'nâu sáng', hex: '#a97449' },
  { name: 'vàng', hex: '#d9a55c' },
  { name: 'vàng bạch kim', hex: '#ece0c8' },
  { name: 'đỏ gừng', hex: '#c0452a' },
  { name: 'muối tiêu', hex: '#9ca3af' },
  { name: 'bạc', hex: '#e5e7eb' },
  { name: 'tím', hex: '#6d28d9' },
  { name: 'xanh', hex: '#2563eb' },
  { name: 'hồng', hex: '#db2777' },
];

export const HAIR_STYLES = [
  'húi cua', 'ngắn', 'ngắn có mái', 'bob', 'dài xoã', 'dài gợn',
  'búi', 'đuôi ngựa', 'xù afro', 'xoăn', 'mohawk', 'tóc tết',
  'hói', 'khăn trùm',
];

export const EYE_STYLES = [
  'mở', 'mở to', 'cười híp', 'nháy', 'lim dim', 'nhíu', 'nhìn ngang', 'trợn',
];
export const BROW_STYLES = ['ngang', 'nhướn', 'vòng', 'nhíu', 'mảnh', 'rậm'];
export const NOSE_STYLES = ['nhỏ', 'hạt', 'bẹt', 'thẳng'];
export const MOUTH_STYLES = [
  'cười', 'cười hở', 'nghiêm', 'cười khẩy', 'tròn miệng', 'mếu', 'lè lưỡi', 'cười to',
];
export const BEARD_STYLES = ['không', 'lởm chởm', 'râu mép', 'râu dê', 'râu ngắn', 'râu rậm'];
export const GLASS_STYLES = ['không', 'tròn', 'vuông', 'râm', 'nửa vành', 'gọng mảnh'];
export const HAT_STYLES = ['không', 'mũ lưỡi trai', 'mũ len', 'băng đô'];

export const SHIRTS = [
  'cổ tròn', 'cổ tim', 'hoodie', 'blazer', 'cổ lọ', 'polo', 'ba lỗ', 'sơ mi',
];
export const SHIRT_COLORS = [
  '#6366f1', '#f59e0b', '#16a34a', '#dc2626', '#0ea5e9', '#8b5cf6', '#475569',
  '#d97706', '#0f766e', '#be185d', '#e2e8f0', '#65a30d', '#f43f5e', '#0891b2',
];
export const EYE_COLORS = ['#2a2320', '#4a3728', '#6b5330', '#2f6b46', '#2b5f8a'];
// Bảng màu nền studio sạch và có độ tương phản tốt cho avatar tròn.
export const BG_COLORS = [
  '#1e293b', '#312e81', '#134e4a', '#1e3a5f', '#3b0764', '#4c0519', '#0f172a',
  '#14532d', '#451a03', '#334155', '#1d4ed8', '#6d28d9', '#be185d', '#0f766e',
  '#b45309', '#374151', '#0369a1', '#7c3aed', '#047857', '#9f1239',
];

// Đặc điểm bổ sung mới 2.0 (thêm ở cuối để tương thích 100% với mã cũ)
export const EARRING_STYLES = ['không', 'khuyên tròn', 'khuyên nụ'];
export const ACCESSORY_STYLES = ['không', 'tai nghe', 'khẩu trang', 'dây chuyền'];
export const FRECKLES_STYLES = ['không', 'tàn nhang', 'nốt ruồi duyên'];
export const BG_STYLES = ['trơn', 'hào quang', 'chấm sao'];
export const GENDERS = ['Nam', 'Nữ'];

// 16 trục ban đầu
const OLD_AXES = [
  ['skin', SKINS.length],
  ['age', AGES.length],
  ['hair', HAIR_STYLES.length],
  ['hairColor', HAIR_COLORS.length],
  ['eyes', EYE_STYLES.length],
  ['brows', BROW_STYLES.length],
  ['nose', NOSE_STYLES.length],
  ['mouth', MOUTH_STYLES.length],
  ['beard', BEARD_STYLES.length],
  ['glasses', GLASS_STYLES.length],
  ['hat', HAT_STYLES.length],
  ['shirt', SHIRTS.length],
  ['shirtColor', SHIRT_COLORS.length],
  ['bg', BG_COLORS.length],
  ['blush', 2],
  ['eyeColor', EYE_COLORS.length],
];
const OLD_TOTAL = OLD_AXES.reduce((n, [, card]) => n * card, 1);

// Danh sách trục 2.0 đầy đủ
export const AXES = [
  ...OLD_AXES,
  ['earring', EARRING_STYLES.length],
  ['accessory', ACCESSORY_STYLES.length],
  ['freckles', FRECKLES_STYLES.length],
  ['bgStyle', BG_STYLES.length],
  ['gender', GENDERS.length],
];

/** Tổng số khuôn mặt khác nhau có thể sinh ra. */
export const TOTAL_FACES = AXES.reduce((n, [, card]) => n * card, 1);

const FEMALE_HAIRS = [3, 4, 5, 6, 7, 9, 11];
const MALE_HAIRS = [0, 1, 2, 8, 9, 10];
const FEMALE_BROWS = [0, 1, 2, 4];

/* ===================================================== mô tả và mã ======= */
export function randomFace(genderPref = 'all') {
  const desc = {};
  for (const [key, card] of AXES) desc[key] = Math.floor(Math.random() * card);
  const g = genderPref === 'female' ? 1 : genderPref === 'male' ? 0 : Math.floor(Math.random() * 2);
  desc.gender = g;
  if (g === 1) {
    desc.beard = 0;
    desc.hair = FEMALE_HAIRS[Math.floor(Math.random() * FEMALE_HAIRS.length)];
    desc.brows = FEMALE_BROWS[Math.floor(Math.random() * FEMALE_BROWS.length)];
    desc.blush = Math.random() < 0.7 ? 1 : 0;
    desc.earring = Math.random() < 0.6 ? (1 + Math.floor(Math.random() * 2)) : 0;
  } else {
    desc.hair = MALE_HAIRS[Math.floor(Math.random() * MALE_HAIRS.length)];
  }
  return desc;
}

/** Đóng gói mô tả thành mã base36 ngắn. Song ánh với mô tả. */
export function encodeFace(desc) {
  let n = 0;
  for (const [key, card] of AXES) {
    const idx = Math.min(card - 1, Math.max(0, desc[key] | 0));
    n = n * card + idx;
  }
  return n.toString(36);
}

/** Giải mã. Hỗ trợ cả mã cũ (16 trục) lẫn mã mới 2.0 (20 trục) mượt mà. */
export function decodeFace(code) {
  const clean = String(code || '').trim().toLowerCase().replace(/[^0-9a-z]/g, '');
  if (!clean) return null;
  let n = parseInt(clean, 36);
  if (!Number.isFinite(n) || n < 0 || n >= TOTAL_FACES) return null;

  const isOld = n < OLD_TOTAL;
  const axes = isOld ? OLD_AXES : AXES;

  const values = new Array(axes.length);
  for (let i = axes.length - 1; i >= 0; i--) {
    const card = axes[i][1];
    values[i] = n % card;
    n = Math.floor(n / card);
  }
  const desc = {};
  axes.forEach(([key], i) => { desc[key] = values[i]; });

  // Nếu là mã cũ, đặt mặc định cho các trục mới
  if (isOld) {
    desc.earring = 0;
    desc.accessory = 0;
    desc.freckles = 0;
    desc.bgStyle = 0;
    desc.gender = 0;
  }
  return desc;
}

/** Danh sách đặc điểm để hiện cho người dùng xem. */
export function describeFace(desc) {
  const hair = HAIR_STYLES[desc.hair];
  const out = [
    ['Giới tính', GENDERS[desc.gender || 0]],
    ['Da', SKINS[desc.skin].name],
    ['Tuổi', AGES[desc.age].name],
    ['Tóc', hair === 'hói' ? 'hói'
      : `${hair} · ${HAIR_COLORS[desc.hairColor].name}`],
    ['Mắt', EYE_STYLES[desc.eyes]],
    ['Mày', BROW_STYLES[desc.brows]],
    ['Mũi', NOSE_STYLES[desc.nose]],
    ['Miệng', MOUTH_STYLES[desc.mouth]],
    ['Áo', SHIRTS[desc.shirt]],
  ];
  if (desc.beard) out.push(['Râu', BEARD_STYLES[desc.beard]]);
  if (desc.glasses) out.push(['Kính', GLASS_STYLES[desc.glasses]]);
  if (desc.hat) out.push(['Mũ', HAT_STYLES[desc.hat]]);
  if (desc.earring) out.push(['Khuyên', EARRING_STYLES[desc.earring]]);
  if (desc.accessory) out.push(['Phụ kiện', ACCESSORY_STYLES[desc.accessory]]);
  if (desc.freckles) out.push(['Nét mặt', FRECKLES_STYLES[desc.freckles]]);
  if (desc.bgStyle) out.push(['Kiểu nền', BG_STYLES[desc.bgStyle]]);
  return out;
}

/* ====================================================== vẽ từng phần ==== */
function eyeShapes(style, cx, side, c) {
  const white = '#ffffff';
  const iris = c.eye;
  const look = side * 1.2;           // hai mắt nhìn hơi lệch nhau cho tự nhiên

  // Hàm tạo tròng mắt long lanh 2.0 (con ngươi + 2 đốm sáng phản chiếu + mí mắt)
  const sparkle = (r, pupilR, bigR) => [
    { k: 'circle', cx: cx + look, cy: EYE_Y + 1, r, fill: iris },
    { k: 'circle', cx: cx + look, cy: EYE_Y + 1, r: pupilR, fill: '#18181b' },
    { k: 'circle', cx: cx + look - 1.4, cy: EYE_Y - 0.9, r: bigR, fill: white },
    { k: 'circle', cx: cx + look + 1.2, cy: EYE_Y + 1.5, r: 0.75, fill: white, op: 0.85 },
    { k: 'path', d: `M${cx - 7} ${EYE_Y - 5} Q${cx} ${EYE_Y - 9} ${cx + 7} ${EYE_Y - 5}`,
      stroke: c.skinDark, sw: 1.4, op: 0.65 },
  ];

  switch (style) {
    case 0: return [                                   // mở
      { k: 'ellipse', cx, cy: EYE_Y, rx: 7, ry: 8, fill: white },
      ...sparkle(3.5, 2.1, 1.2),
    ];
    case 1: return [                                   // mở to
      { k: 'ellipse', cx, cy: EYE_Y, rx: 8.5, ry: 9.5, fill: white },
      ...sparkle(4.3, 2.5, 1.5),
    ];
    case 2: return [                                   // cười híp
      { k: 'path', d: `M${cx - 7} ${EYE_Y + 2} Q${cx} ${EYE_Y - 6} ${cx + 7} ${EYE_Y + 2}`,
        stroke: iris, sw: 3.2 },
      { k: 'path', d: `M${cx + (side < 0 ? -6 : 6)} ${EYE_Y + 1} l${side < 0 ? -2 : 2} 2`,
        stroke: iris, sw: 2.2 },
    ];
    case 3: return side < 0                            // nháy (mắt trái mở)
      ? [{ k: 'ellipse', cx, cy: EYE_Y, rx: 7, ry: 8, fill: white },
         ...sparkle(3.5, 2.1, 1.2)]
      : [{ k: 'path', d: `M${cx - 7} ${EYE_Y + 2} Q${cx} ${EYE_Y - 6} ${cx + 7} ${EYE_Y + 2}`,
           stroke: iris, sw: 3.2 }];
    case 4: return [                                   // lim dim
      { k: 'ellipse', cx, cy: EYE_Y + 1, rx: 7, ry: 5.5, fill: white },
      { k: 'circle', cx: cx + look, cy: EYE_Y + 2, r: 3.1, fill: iris },
      { k: 'circle', cx: cx + look - 1.2, cy: EYE_Y + 0.8, r: 1.0, fill: white },
      { k: 'path', d: `M${cx - 7.5} ${EYE_Y - 2} Q${cx} ${EYE_Y + 1} ${cx + 7.5} ${EYE_Y - 2}`,
        stroke: c.skinDark, sw: 2.4 },
    ];
    case 5: return [                                   // nhíu
      { k: 'path', d: `M${cx - 7} ${EYE_Y - 1} Q${cx} ${EYE_Y + 5} ${cx + 7} ${EYE_Y - 1}`,
        stroke: iris, sw: 3 },
    ];
    case 6: return [                                   // nhìn ngang
      { k: 'ellipse', cx, cy: EYE_Y, rx: 7, ry: 8, fill: white },
      { k: 'circle', cx: cx + 3, cy: EYE_Y + 1, r: 3.4, fill: iris },
      { k: 'circle', cx: cx + 3, cy: EYE_Y + 1, r: 2.0, fill: '#18181b' },
      { k: 'circle', cx: cx + 1.8, cy: EYE_Y - 0.8, r: 1.1, fill: white },
    ];
    default: return [                                  // trợn
      { k: 'ellipse', cx, cy: EYE_Y, rx: 8, ry: 9, fill: white },
      ...sparkle(2.8, 1.8, 1.0),
    ];
  }
}

function browShapes(style, cx, c, thick) {
  const y = BROW_Y;
  const col = c.brow;
  const d = {
    0: `M${cx - 9} ${y} Q${cx} ${y - 2} ${cx + 9} ${y}`,
    1: `M${cx - 9} ${y + 1} Q${cx} ${y - 7} ${cx + 9} ${y - 2}`,
    2: `M${cx - 9} ${y + 1} Q${cx} ${y - 8} ${cx + 9} ${y + 1}`,
    3: `M${cx - 9} ${y - 3} Q${cx} ${y + 1} ${cx + 9} ${y + 3}`,
    4: `M${cx - 8} ${y} Q${cx} ${y - 4} ${cx + 8} ${y}`,
    5: `M${cx - 10} ${y + 1} Q${cx} ${y - 5} ${cx + 10} ${y + 1}`,
  }[style];
  const widths = { 0: 3.4, 1: 3.4, 2: 3.2, 3: 3.6, 4: 2.4, 5: 5 };
  // Mắt trái và phải là ảnh gương, nên nhíu/nhướn phải lật theo bên.
  const flipped = (style === 1 || style === 3) && cx > 100
    ? d.replace(/^M(\S+) (\S+) Q(\S+) (\S+) (\S+) (\S+)$/,
        (_m, x1, y1, qx, qy, x2, y2) => `M${x2} ${y2} Q${qx} ${qy} ${x1} ${y1}`)
    : d;
  return [{ k: 'path', d: flipped, stroke: col, sw: widths[style] + thick }];
}

function noseShapes(style, c) {
  switch (style) {
    case 0: return [{ k: 'path', d: `M100 ${NOSE_Y} v10 q0 4 5 4`,
                      stroke: c.skinDark, sw: 3 }];
    case 1: return [{ k: 'ellipse', cx: 100, cy: NOSE_Y + 10, rx: 4.5, ry: 3,
                      fill: c.skinDark }];
    case 2: return [{ k: 'path', d: `M93 ${NOSE_Y + 9} q7 5 14 0`,
                      stroke: c.skinDark, sw: 3.2 }];
    default: return [{ k: 'path', d: `M100 ${NOSE_Y - 1} v12`,
                      stroke: c.skinDark, sw: 2.8 }];
  }
}

function mouthShapes(style, c) {
  const y = MOUTH_Y;
  const lip = c.lip;
  switch (style) {
    case 0: return [{ k: 'path', d: `M88 ${y} Q100 ${y + 9} 112 ${y}`,
                      stroke: lip, sw: 3.4 }];
    case 1: return [                                   // cười hở răng
      { k: 'path', d: `M87 ${y - 2} Q100 ${y + 14} 113 ${y - 2} Z`, fill: lip },
      { k: 'path', d: `M90 ${y - 1} Q100 ${y + 4} 110 ${y - 1} Z`, fill: '#ffffff' },
    ];
    case 2: return [{ k: 'path', d: `M90 ${y + 2} h20`, stroke: lip, sw: 3.2 }];
    case 3: return [{ k: 'path', d: `M89 ${y + 2} Q100 ${y + 7} 111 ${y - 1}`,
                      stroke: lip, sw: 3.2 }];
    case 4: return [                                   // tròn miệng
      { k: 'ellipse', cx: 100, cy: y + 2, rx: 6, ry: 7, fill: lip },
      { k: 'ellipse', cx: 100, cy: y + 3, rx: 3, ry: 3.5, fill: shade(lip, -0.35) },
    ];
    case 5: return [{ k: 'path', d: `M89 ${y + 5} Q100 ${y - 3} 111 ${y + 5}`,
                      stroke: lip, sw: 3.2 }];
    case 6: return [                                   // lè lưỡi
      { k: 'path', d: `M88 ${y} Q100 ${y + 10} 112 ${y}`, stroke: lip, sw: 3.4 },
      { k: 'path', d: rrect(95, y + 5, 11, 9, 4.5), fill: '#e8756b' },
    ];
    default: return [                                  // cười to
      { k: 'path', d: `M84 ${y - 3} Q100 ${y + 18} 116 ${y - 3} Z`, fill: lip },
      { k: 'path', d: `M88 ${y - 2} Q100 ${y + 4} 112 ${y - 2} Z`, fill: '#ffffff' },
      { k: 'path', d: `M96 ${y + 11} q4 3 8 0`, stroke: '#e8756b', sw: 3 },
    ];
  }
}

function beardShapes(style, hairHex) {
  // Viền ngoài ôm hàm, viền trong chừa má — râu vẽ TRƯỚC miệng nên miệng nằm
  // trên râu, giống thật.
  const jaw = 'M63 94 Q66 138 100 141 Q134 138 137 94 Q131 120 100 122 Q69 120 63 94 Z';
  switch (style) {
    case 0: return [];
    case 1: return [{ k: 'path', d: jaw, fill: hairHex, op: 0.32 }];
    case 2: return [{ k: 'path', d: 'M86 103 Q100 97 114 103 Q107 110 100 108 Q93 110 86 103 Z',
                      fill: hairHex }];
    case 3: return [                                   // râu dê
      { k: 'path', d: 'M86 103 Q100 97 114 103 Q107 110 100 108 Q93 110 86 103 Z',
        fill: hairHex },
      { k: 'path', d: rrect(93, 118, 14, 18, 7), fill: hairHex },
    ];
    case 4: return [{ k: 'path', d: jaw, fill: hairHex },
                    { k: 'path', d: 'M86 103 Q100 97 114 103 Q107 110 100 108 Q93 110 86 103 Z',
                      fill: hairHex }];
    default: return [                                  // râu rậm
      { k: 'path', d: 'M60 88 Q62 146 100 150 Q138 146 140 88 Q132 118 100 120 Q68 118 60 88 Z',
        fill: hairHex },
      { k: 'path', d: 'M85 102 Q100 95 115 102 Q107 110 100 108 Q93 110 85 102 Z',
        fill: hairHex },
    ];
  }
}

function hairShapes(style, hex) {
  /* cap = khối tóc ốp sọ, dùng chung cho nhiều kiểu.
   *
   * Vùng tóc nằm giữa CUNG NGOÀI (mép sọ) và ĐƯỜNG CHÂN TÓC bên trong. Điểm
   * dễ sai: nếu đường chân tóc chụm về đúng mép sọ ở hai bên thì vùng tóc bị
   * bóp thành lưỡi liềm mỏng trên đỉnh, và mặt nào cũng trông như hói. Nên
   * đường chân tóc phải hạ xuống tới y≈84 ở hai thái dương, chỉ nhô lên giữa
   * trán theo tham số ``hairline``.
   */
  const cap = (hairline, fill = hex) => ({
    k: 'path',
    d: `${SKULL_TOP} L140 84`
     + ` Q138 ${hairline + 14} 126 ${hairline + 8}`
     + ` Q114 ${hairline} 100 ${hairline}`
     + ` Q86 ${hairline} 74 ${hairline + 8}`
     + ` Q62 ${hairline + 14} 60 84 Z`,
    fill,
  });
  const dark = shade(hex, -0.3);
  switch (style) {
    case 0: return { back: [], front: [cap(72)] };                    // húi cua
    case 1: return { back: [], front: [cap(62)] };                    // ngắn
    case 2: return { back: [], front: [                               // ngắn có mái
      cap(56),
      { k: 'path', d: 'M60 84 Q64 50 100 48 Q76 58 70 86 Z', fill: dark },
    ] };
    case 3: return {                                                  // bob
      back: [{ k: 'path', d: 'M56 80 Q56 36 100 36 Q144 36 144 80 L146 130 Q120 121 100 121 Q80 121 54 130 Z', fill: hex }],
      front: [cap(60)],
    };
    case 4: return {                                                  // dài xoã
      back: [{ k: 'path', d: 'M54 80 Q54 34 100 34 Q146 34 146 80 L148 176 Q124 164 100 162 Q76 164 52 176 Z', fill: hex }],
      front: [cap(58)],
    };
    case 5: return {                                                  // dài gợn
      back: [{ k: 'path', d: 'M54 80 Q54 34 100 34 Q146 34 146 80 L147 168 Q136 177 126 168 Q113 159 100 159 Q87 159 74 168 Q64 177 53 168 Z', fill: hex }],
      front: [cap(58), { k: 'path', d: 'M60 84 Q64 52 88 46 Q70 60 68 86 Z', fill: dark }],
    };
    case 6: return {                                                  // búi
      back: [{ k: 'circle', cx: 100, cy: 30, r: 16, fill: hex }],
      front: [cap(58)],
    };
    case 7: return {                                                  // đuôi ngựa
      back: [{ k: 'ellipse', cx: 151, cy: 100, rx: 14, ry: 30, fill: hex }],
      front: [cap(58)],
    };
    case 8: return {                                                  // xù afro
      back: [{ k: 'circle', cx: 100, cy: 64, r: 53, fill: hex }],
      front: [cap(66)],
    };
    case 9: return {                                                  // xoăn
      back: [],
      front: [
        cap(62),
        { k: 'circle', cx: 64, cy: 68, r: 14, fill: hex },
        { k: 'circle', cx: 80, cy: 50, r: 16, fill: hex },
        { k: 'circle', cx: 102, cy: 44, r: 16, fill: hex },
        { k: 'circle', cx: 124, cy: 51, r: 15, fill: hex },
        { k: 'circle', cx: 138, cy: 70, r: 13, fill: hex },
      ],
    };
    case 10: return {                                                 // mohawk
      back: [],
      front: [
        cap(76, dark),
        { k: 'path', d: 'M80 68 Q88 16 100 14 Q112 16 120 68 Q100 60 80 68 Z', fill: hex },
      ],
    };
    case 11: return {                                                 // tóc tết
      back: [
        { k: 'path', d: rrect(53, 74, 10, 60, 5), fill: hex },
        { k: 'path', d: rrect(66, 86, 10, 50, 5), fill: hex },
        { k: 'path', d: rrect(124, 86, 10, 50, 5), fill: hex },
        { k: 'path', d: rrect(137, 74, 10, 60, 5), fill: hex },
      ],
      front: [cap(60)],
    };
    case 12: return { back: [], front: [] };                          // hói
    default: return {                                                 // khăn trùm
      back: [{ k: 'path', d: 'M50 84 Q50 32 100 32 Q150 32 150 84 L152 152 Q126 142 100 142 Q74 142 48 152 Z', fill: hex }],
      front: [
        { k: 'path', d: 'M58 88 A42 48 0 0 1 142 88 Q138 54 100 50 Q62 54 58 88 Z', fill: hex },
        { k: 'path', d: 'M58 88 Q60 60 78 50 Q64 68 62 90 Z', fill: shade(hex, 0.12) },
      ],
    };
  }
}

function glassShapes(style) {
  const frame = '#2a2320';
  const bridge = { k: 'path', d: 'M97 86 h6', stroke: frame, sw: 3 };
  const arms = { k: 'path', d: 'M71 82 l-10 -3 M129 82 l10 -3', stroke: frame, sw: 3 };
  const glint = (style === 3)
    ? [{ k: 'path', d: 'M74 79 l8 14 M108 79 l8 14', stroke: '#ffffff', sw: 2.2, op: 0.28 }]
    : [{ k: 'path', d: 'M76 80 l6 11 M108 80 l6 11', stroke: '#ffffff', sw: 1.6, op: 0.35 }];
  switch (style) {
    case 0: return [];
    case 1: return [
      { k: 'circle', cx: EYE_L, cy: EYE_Y, r: 13, fill: 'none', stroke: frame, sw: 3 },
      { k: 'circle', cx: EYE_R, cy: EYE_Y, r: 13, fill: 'none', stroke: frame, sw: 3 },
      ...glint, bridge, arms,
    ];
    case 2: return [
      { k: 'path', d: rrect(71, 77, 26, 19, 4), fill: 'none', stroke: frame, sw: 3 },
      { k: 'path', d: rrect(103, 77, 26, 19, 4), fill: 'none', stroke: frame, sw: 3 },
      ...glint, bridge, arms,
    ];
    case 3: return [                                   // kính râm
      { k: 'path', d: rrect(69, 76, 28, 20, 8), fill: '#1a1512' },
      { k: 'path', d: rrect(103, 76, 28, 20, 8), fill: '#1a1512' },
      ...glint,
      { k: 'path', d: 'M97 84 h6 M69 80 l-8 -3 M131 80 l8 -3', stroke: '#1a1512', sw: 3 },
    ];
    case 4: return [                                   // nửa vành
      { k: 'path', d: 'M71 80 h26 M103 80 h26', stroke: frame, sw: 3.4 },
      { k: 'path', d: 'M71 80 q0 14 13 14 q13 0 13 -14 M103 80 q0 14 13 14 q13 0 13 -14',
        fill: 'none', stroke: frame, sw: 2 },
      ...glint, bridge,
    ];
    default: return [                                  // gọng mảnh
      { k: 'circle', cx: EYE_L, cy: EYE_Y, r: 12, fill: 'none', stroke: '#6b5b4a', sw: 1.8 },
      { k: 'circle', cx: EYE_R, cy: EYE_Y, r: 12, fill: 'none', stroke: '#6b5b4a', sw: 1.8 },
      ...glint,
      { k: 'path', d: 'M96 86 h8', stroke: '#6b5b4a', sw: 1.8 },
      { k: 'path', d: 'M72 82 l-11 -3 M128 82 l11 -3', stroke: '#6b5b4a', sw: 1.8 },
    ];
  }
}

function hatShapes(style, shirtHex) {
  const hex = shade(shirtHex, -0.35);
  const dark = shade(shirtHex, -0.55);
  switch (style) {
    case 0: return [];
    case 1: return [                                   // mũ lưỡi trai
      { k: 'path', d: `M60 80 A${HEAD.rx} ${HEAD.ry} 0 0 1 140 80 L140 74 Q136 44 100 40 Q64 44 60 74 Z`, fill: hex },
      { k: 'path', d: 'M58 74 h84 q7 0 7 7 h-98 q0 -7 7 -7 z', fill: dark },
      { k: 'circle', cx: 100, cy: 46, r: 5, fill: shade(shirtHex, -0.15) },
    ];
    case 2: return [                                   // mũ len
      { k: 'path', d: `${SKULL_TOP} Q136 46 100 42 Q64 46 60 86 Z`, fill: hex },
      { k: 'path', d: rrect(58, 70, 84, 13, 6.5), fill: dark },
    ];
    default: return [                                  // băng đô
      { k: 'path', d: rrect(59, 62, 82, 11, 5.5), fill: hex },
    ];
  }
}

function shirtShapes(style, hex) {
  const body = 'M22 200 Q30 162 66 150 Q84 144 100 144 Q116 144 134 150 Q170 162 178 200 Z';
  const dark = shade(hex, -0.22);
  const base = { k: 'path', d: body, fill: hex };
  switch (style) {
    case 0: return [base, { k: 'path', d: 'M84 147 Q100 161 116 147', stroke: dark, sw: 4 }];
    case 1: return [base, { k: 'path', d: 'M82 146 L100 166 L118 146 Q108 155 100 155 Q92 155 82 146 Z', fill: dark }];
    case 2: return [                                   // hoodie
      { k: 'path', d: 'M22 200 Q30 160 64 148 Q84 142 100 142 Q116 142 136 148 Q170 160 178 200 Z', fill: hex },
      { k: 'path', d: 'M60 148 Q70 180 100 182 Q130 180 140 148 Q126 161 100 162 Q74 161 60 148 Z', fill: dark },
      { k: 'path', d: 'M96 160 v22 M104 160 v22', stroke: shade(hex, 0.3), sw: 2.6 },
    ];
    case 3: return [                                   // blazer + cà vạt
      base,
      // Ve áo phải tối HẲN so với thân áo, tối nhẹ thì hai mảng gần như trùng
      // màu và cái blazer biến thành áo phông trơn.
      { k: 'path', d: 'M78 146 L100 178 L122 146 L134 151 L118 200 L82 200 L66 151 Z',
        fill: shade(hex, -0.48) },
      { k: 'path', d: 'M96 157 h8 l-2 26 h-4 z', fill: '#dc2626' },
    ];
    case 4: return [base, { k: 'path', d: rrect(78, 138, 44, 15, 6), fill: dark }];
    case 5: return [                                   // polo
      base,
      { k: 'path', d: 'M86 146 L100 162 L114 146 L120 150 L100 170 L80 150 Z', fill: dark },
      { k: 'path', d: 'M99 156 v14', stroke: shade(hex, -0.35), sw: 2 },
    ];
    case 6: return [                                   // ba lỗ
      { k: 'path', d: 'M34 200 Q42 168 72 154 Q86 148 100 148 Q114 148 128 154 Q158 168 166 200 Z', fill: hex },
      { k: 'path', d: 'M84 150 Q100 166 116 150', stroke: dark, sw: 4 },
    ];
    default: return [                                  // sơ mi
      base,
      { k: 'path', d: 'M84 146 L100 168 L116 146 L124 150 L100 176 L76 150 Z', fill: '#f8fafc' },
      { k: 'path', d: 'M99 170 v26', stroke: dark, sw: 2.4 },
    ];
  }
}

function ageShapes(age, c) {
  if (age === 0) return [];
  const lines = [
    'M70 78 q6 -3 11 -1', 'M119 77 q6 -2 11 1',
    'M86 64 q14 -3 28 0',
  ];
  if (age === 2) lines.push('M88 58 q12 -3 24 0', 'M78 104 q4 6 3 12', 'M122 104 q-4 6 -3 12');
  return lines.map((d) => ({ k: 'path', d, stroke: c.skinDark, sw: 1.8, op: 0.85 }));
}

/* ================================================== dựng display list === */
/** Mô tả -> danh sách hình, thứ tự vẽ từ sau ra trước. */
export function faceShapes(desc) {
  const isFemale = desc.gender === 1;
  const skin = SKINS[desc.skin].base;
  const hairHex = HAIR_COLORS[desc.hairColor].hex;
  const shirtHex = SHIRT_COLORS[desc.shirtColor];
  const c = {
    skin,
    skinDark: shade(skin, -0.3),
    eye: EYE_COLORS[desc.eyeColor],
    brow: luminance(hairHex) > 150 ? shade(hairHex, -0.5) : shade(hairHex, -0.12),
    lip: isFemale ? '#d94862' : shade(skin, -0.42),
  };
  const hair = hairShapes(desc.hair, hairHex);
  const hijab = desc.hair === 13;
  const thickBrow = desc.age === 2 ? 0.6 : 0;

  const bgHex = BG_COLORS[desc.bg];
  const out = [
    { k: 'path', d: 'M0 0 h200 v200 h-200 Z', fill: bgHex },
  ];

  // Kiểu nền (bgStyle: 0 trơn, 1 hào quang, 2 chấm sao)
  if (desc.bgStyle === 1) {
    out.push({ k: 'circle', cx: 100, cy: 92, r: 76, fill: shade(bgHex, 0.28), op: 0.45 });
  } else if (desc.bgStyle === 2) {
    for (const [sx, sy, r] of [[28, 28, 3.5], [172, 32, 2.5], [36, 168, 3], [168, 165, 3.5], [92, 18, 2]]) {
      out.push({ k: 'circle', cx: sx, cy: sy, r, fill: '#ffffff', op: 0.35 });
    }
  }

  out.push(...hair.back);
  out.push(...shirtShapes(desc.shirt, shirtHex));

  // Cổ và bóng đổ mềm dưới cằm lên cổ
  out.push({ k: 'path', d: rrect(87, 112, 26, 28, 11), fill: c.skinDark });
  out.push({ k: 'path', d: 'M87 114 Q100 128 113 114 L113 124 Q100 134 87 124 Z', fill: shade(skin, -0.25), op: 0.65 });

  // Khối sọ mặt
  out.push({ k: 'ellipse', cx: HEAD.cx, cy: HEAD.cy, rx: isFemale ? HEAD.rx - 1.5 : HEAD.rx, ry: HEAD.ry, fill: skin });

  // Tai & Khuyên tai
  if (!hijab) {
    for (const ex of [62, 138]) {
      out.push({ k: 'ellipse', cx: ex, cy: 94, rx: 7, ry: 9.5, fill: skin });
      out.push({ k: 'path', d: `M${ex} 89 q${ex < 100 ? 3 : -3} 5 0 10`,
                 stroke: shade(skin, -0.22), sw: 1.8 });
    }
    if (desc.earring === 1) {
      // Khuyên tròn vàng
      out.push({ k: 'circle', cx: 62, cy: 102, r: 3.8, fill: 'none', stroke: '#f59e0b', sw: 2 });
      out.push({ k: 'circle', cx: 138, cy: 102, r: 3.8, fill: 'none', stroke: '#f59e0b', sw: 2 });
    } else if (desc.earring === 2) {
      // Khuyên nụ lấp lánh
      out.push({ k: 'circle', cx: 62, cy: 101, r: 2.2, fill: '#fbbf24' });
      out.push({ k: 'circle', cx: 138, cy: 101, r: 2.2, fill: '#fbbf24' });
    }
  }

  if (!isFemale) out.push(...beardShapes(desc.beard, hairHex));

  // Má hồng
  if (desc.blush) {
    out.push({ k: 'ellipse', cx: 74, cy: 101, rx: 8, ry: 4.5, fill: '#f43f5e', op: 0.35 });
    out.push({ k: 'ellipse', cx: 126, cy: 101, rx: 8, ry: 4.5, fill: '#f43f5e', op: 0.35 });
  }

  // Tàn nhang hoặc nốt ruồi duyên
  if (desc.freckles === 1) {
    for (const [fx, fy] of [[71, 98], [75, 100], [79, 97], [121, 97], [125, 100], [129, 98]]) {
      out.push({ k: 'circle', cx: fx, cy: fy, r: 1.1, fill: c.skinDark, op: 0.65 });
    }
  } else if (desc.freckles === 2) {
    out.push({ k: 'circle', cx: 123, cy: 96, r: 1.3, fill: '#2a2320' });
  }

  out.push(...eyeShapes(desc.eyes, EYE_L, -1, c));
  out.push(...eyeShapes(desc.eyes, EYE_R, 1, c));
  if (isFemale && desc.eyes !== 2) {
    out.push({ k: 'path', d: `M${EYE_L - 6} ${EYE_Y - 3} q-3 -3 -5 -2`, stroke: '#1e1b18', sw: 1.5 });
    out.push({ k: 'path', d: `M${EYE_R + 6} ${EYE_Y - 3} q3 -3 5 -2`, stroke: '#1e1b18', sw: 1.5 });
  }
  out.push(...browShapes(desc.brows, EYE_L, c, thickBrow));
  out.push(...browShapes(desc.brows, EYE_R, c, thickBrow));
  out.push(...noseShapes(desc.nose, c));
  out.push(...mouthShapes(desc.mouth, c));
  out.push(...ageShapes(desc.age, c));

  out.push(...hair.front);

  // Phụ kiện: Tai nghe, khẩu trang, dây chuyền
  if (desc.accessory === 1) {
    // Tai nghe DJ quàng cổ
    out.push({ k: 'path', d: 'M62 140 Q100 166 138 140', stroke: '#1e293b', sw: 9 });
    out.push({ k: 'ellipse', cx: 58, cy: 132, rx: 7, ry: 13, fill: '#0ea5e9' });
    out.push({ k: 'ellipse', cx: 142, cy: 132, rx: 7, ry: 13, fill: '#0ea5e9' });
    out.push({ k: 'ellipse', cx: 58, cy: 132, rx: 4, ry: 8, fill: '#0284c7' });
    out.push({ k: 'ellipse', cx: 142, cy: 132, rx: 4, ry: 8, fill: '#0284c7' });
  } else if (desc.accessory === 2) {
    // Khẩu trang đen
    out.push({ k: 'path', d: 'M68 106 Q100 97 132 106 L124 136 Q100 146 76 136 Z', fill: '#0f172a' });
    out.push({ k: 'path', d: 'M69 108 L62 98 M131 108 L138 98', stroke: '#0f172a', sw: 1.8 });
  } else if (desc.accessory === 3) {
    // Dây chuyền bạc
    out.push({ k: 'path', d: 'M78 146 Q100 178 122 146', stroke: '#cbd5e1', sw: 2.2 });
    out.push({ k: 'circle', cx: 100, cy: 164, r: 3.5, fill: '#38bdf8' });
  }

  out.push(...glassShapes(desc.glasses));

  const hat = hijab && desc.hat !== 3 ? 0 : desc.hat;
  out.push(...hatShapes(hat, shirtHex));

  return out;
}

/* ======================================================== bộ xuất ======== */
const SVG_NS = 'http://www.w3.org/2000/svg';

/** Dựng phần tử <svg> thật (không dùng innerHTML) để xem trước. */
export function toSvgElement(shapes, size = 200) {
  const svg = document.createElementNS(SVG_NS, 'svg');
  svg.setAttribute('viewBox', '0 0 200 200');
  svg.setAttribute('width', size);
  svg.setAttribute('height', size);
  svg.setAttribute('aria-hidden', 'true');
  for (const s of shapes) {
    const el = document.createElementNS(SVG_NS, s.k === 'path' ? 'path' : s.k);
    if (s.k === 'path') el.setAttribute('d', s.d);
    else if (s.k === 'circle') {
      el.setAttribute('cx', s.cx); el.setAttribute('cy', s.cy); el.setAttribute('r', s.r);
    } else {
      el.setAttribute('cx', s.cx); el.setAttribute('cy', s.cy);
      el.setAttribute('rx', s.rx); el.setAttribute('ry', s.ry);
    }
    el.setAttribute('fill', s.stroke ? (s.fill || 'none') : (s.fill || 'none'));
    if (s.stroke) {
      el.setAttribute('stroke', s.stroke);
      el.setAttribute('stroke-width', s.sw || 3);
      el.setAttribute('stroke-linecap', 'round');
      el.setAttribute('stroke-linejoin', 'round');
    }
    if (s.op !== undefined) el.setAttribute('opacity', s.op);
    svg.appendChild(el);
  }
  return svg;
}

/** Vẽ lên canvas 2D. Dùng Path2D nên không bao giờ làm canvas "nhiễm bẩn",
 *  toBlob() luôn chạy được. */
export function drawFace(ctx, shapes, size = 256) {
  const k = size / 200;
  ctx.save();
  ctx.clearRect(0, 0, size, size);
  ctx.scale(k, k);
  ctx.lineCap = 'round';
  ctx.lineJoin = 'round';
  for (const s of shapes) {
    ctx.globalAlpha = s.op === undefined ? 1 : s.op;
    let path;
    if (s.k === 'path') {
      path = new Path2D(s.d);
    } else {
      path = new Path2D();
      if (s.k === 'circle') path.arc(s.cx, s.cy, s.r, 0, Math.PI * 2);
      else path.ellipse(s.cx, s.cy, s.rx, s.ry, 0, 0, Math.PI * 2);
    }
    if (s.fill && s.fill !== 'none') { ctx.fillStyle = s.fill; ctx.fill(path); }
    else if (!s.stroke) { ctx.fillStyle = s.fill || '#000'; ctx.fill(path); }
    if (s.stroke) {
      ctx.strokeStyle = s.stroke;
      ctx.lineWidth = s.sw || 3;
      ctx.stroke(path);
    }
  }
  ctx.restore();
  ctx.globalAlpha = 1;
}

/** Xuất PNG. Trả về Blob. */
export function facePng(desc, size = 256) {
  const canvas = document.createElement('canvas');
  canvas.width = size;
  canvas.height = size;
  drawFace(canvas.getContext('2d'), faceShapes(desc), size);
  return new Promise((resolve, reject) => {
    canvas.toBlob((blob) => (blob ? resolve(blob) : reject(new Error('Không xuất được ảnh.'))),
      'image/png');
  });
}

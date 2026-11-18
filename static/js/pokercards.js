/* Bộ bài Tây 52 lá cho Xì Tố — SVG vẽ trực tiếp, không ảnh, không font ngoài.
 *
 * Thiết kế theo bài của các site poker online: chỉ số (rank + chất) thật to ở
 * góc trên-trái để đọc được ngay cả khi lá bài chỉ rộng 34-40px trên ghế
 * người khác, và một chất lớn ở giữa. Lá J/Q/K vẽ chữ to trong khung thay vì
 * hình người — ở cỡ nhỏ hình người chỉ là một vệt màu.
 *
 * Lá bài từ server: {v: 2-14, s: "S"|"H"|"D"|"C", label: "A♠"}.
 * Lớp phụ ``hl`` (thuộc tay thắng) và ``dim`` (không dùng tới) do CSS tô.
 */

import { suitNameI18n, t } from './i18n.js';

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

function text(x, y, content, attrs = {}) {
  return el('text', { x, y, 'font-family': 'system-ui, "Segoe UI", sans-serif', ...attrs },
    document.createTextNode(content));
}

const RANK_GLYPH = { 10: '10', 11: 'J', 12: 'Q', 13: 'K', 14: 'A' };
const SUIT_GLYPH = { S: '♠', H: '♥', D: '♦', C: '♣' };
const SUIT_NAME = { S: 'bích', H: 'cơ', D: 'rô', C: 'chuồn' };
const SUIT_COLOR = { S: '#111827', C: '#111827', H: '#c8102e', D: '#c8102e' };

export function rankGlyph(value) {
  return RANK_GLYPH[value] || String(value);
}

/** Lá bài ngửa. ``size`` là bề rộng (px); cao = 1.4 lần rộng. */
export function pokerCardFace(card, { size = 60, className = '' } = {}) {
  const value = card.v ?? card.value;
  const suit = card.s ?? card.suit;
  const color = SUIT_COLOR[suit] || '#111827';
  const glyph = rankGlyph(value);
  const pip = SUIT_GLYPH[suit] || '?';
  const uid = `pf${++COUNTER}`;
  const isFace = value >= 11 && value <= 13;
  const wide = glyph.length > 1;

  const center = isFace
    ? [
        el('rect', { x: 26, y: 46, width: 48, height: 62, rx: 6, fill: 'none',
                     stroke: color, 'stroke-width': 2, opacity: 0.55 }),
        text(50, 92, glyph, { 'font-size': 40, 'font-weight': '800', fill: color,
                              'text-anchor': 'middle' }),
        text(50, 104, pip, { 'font-size': 13, fill: color, 'text-anchor': 'middle' }),
      ]
    : [text(56, 104, pip, { 'font-size': value === 14 ? 64 : 50, fill: color,
                            'text-anchor': 'middle' })];

  return el('svg', {
    viewBox: '0 0 100 140', width: size, height: Math.round(size * 1.4),
    class: 'pcard' + (className ? ' ' + className.trim() : ''),
    role: 'img', 'aria-label': `${glyph} ${suitNameI18n(suit) || SUIT_NAME[suit] || ''}`,
  },
    el('defs', {},
      el('linearGradient', { id: `${uid}p`, x1: '0', y1: '0', x2: '0.2', y2: '1' },
        el('stop', { offset: '0', 'stop-color': '#ffffff' }),
        el('stop', { offset: '1', 'stop-color': '#eef0f3' }))),
    el('rect', { x: 1.5, y: 1.5, width: 97, height: 137, rx: 9,
                 fill: `url(#${uid}p)`, stroke: '#c9ced6', 'stroke-width': 1.5 }),
    // Chỉ số góc — phần quan trọng nhất, nên to và đậm.
    text(wide ? 5 : 9, 38, glyph, { 'font-size': wide ? 34 : 38, 'font-weight': '800',
                                   fill: color, 'letter-spacing': wide ? '-2' : '0' }),
    text(10, 64, pip, { 'font-size': 26, fill: color }),
    ...center);
}

/** Mặt sau. */
export function cardBack({ size = 60, className = '' } = {}) {
  const uid = `pb${++COUNTER}`;
  const lines = [];
  for (let i = -6; i <= 12; i++) {
    lines.push(el('path', { d: `M${i * 12} 0 L${i * 12 + 140} 140`, stroke: '#ffffff',
                            'stroke-width': 1, opacity: 0.12 }));
    lines.push(el('path', { d: `M${i * 12} 140 L${i * 12 + 140} 0`, stroke: '#ffffff',
                            'stroke-width': 1, opacity: 0.12 }));
  }
  return el('svg', {
    viewBox: '0 0 100 140', width: size, height: Math.round(size * 1.4),
    class: 'pcard back' + (className ? ' ' + className : ''),
    role: 'img', 'aria-label': t('poker.cardBackAria'),
  },
    el('defs', {},
      el('linearGradient', { id: `${uid}b`, x1: '0', y1: '0', x2: '0.6', y2: '1' },
        el('stop', { offset: '0', 'stop-color': '#b91c1c' }),
        el('stop', { offset: '1', 'stop-color': '#6b0f1a' })),
      el('clipPath', { id: `${uid}c` },
        el('rect', { x: 8, y: 8, width: 84, height: 124, rx: 6 }))),
    el('rect', { x: 1.5, y: 1.5, width: 97, height: 137, rx: 9, fill: '#fff',
                 stroke: '#c9ced6', 'stroke-width': 1.5 }),
    el('rect', { x: 8, y: 8, width: 84, height: 124, rx: 6, fill: `url(#${uid}b)` }),
    el('g', { 'clip-path': `url(#${uid}c)` }, ...lines),
    text(50, 82, '♠', { 'font-size': 36, fill: '#ffffff', opacity: 0.85,
                        'text-anchor': 'middle' }));
}

/** Ô bài chung chưa lật (khung mờ). */
export function cardSlot({ size = 60 } = {}) {
  return el('svg', {
    viewBox: '0 0 100 140', width: size, height: Math.round(size * 1.4),
    class: 'pcard slot', 'aria-hidden': 'true',
  },
    el('rect', { x: 2, y: 2, width: 96, height: 136, rx: 9, fill: 'rgba(0,0,0,0.18)',
                 stroke: 'rgba(255,255,255,0.18)', 'stroke-width': 2,
                 'stroke-dasharray': '6 5' }));
}

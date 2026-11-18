/* Cờ tướng. Bàn 9 cột x 10 hàng, quân vẽ bằng chữ Hán trên đĩa tròn.
 *
 * Giống chess.js: view này KHÔNG biết luật. Server gửi `state.legal` (nước đi
 * hợp lệ của riêng người tới lượt) và view chỉ tô sáng rồi gửi lại lựa chọn.
 * Mọi luật rắc rối của cờ tướng — chân mã, mắt tượng, ngòi pháo, lộ mặt tướng
 * — nằm gọn trong xiangqi.py.
 */

import { clear, h, mount } from '../dom.js';
import { seatLabelI18n, t } from '../i18n.js';
import { createSelect, sfx, toast } from '../ui.js';
import { actionRow, formatClockSec, renderLobby, roomCard, roomChat, roomTopbar, seatPanel } from './gameroom.js';

const CHANNEL = 'xiangqi';
const COLS = 9;
const ROWS = 10;
const FILES = 'abcdefghi';
const clockOptions = () => [
  { id: 'none', label: t('chess.clockNone') },
  { id: '180+2', label: t('chess.clock180') },
  { id: '600+0', label: t('chess.clock600') },
  { id: '900+5', label: t('chess.clock900') },
];

// Chữ Hán truyền thống: hai bên dùng chữ khác nhau cho cùng một loại quân, đó
// là quy ước của cờ tướng chứ không phải trang trí.
const GLYPH = {
  rK: '帥', rA: '仕', rE: '相', rH: '傌', rR: '俥', rC: '炮', rP: '兵',
  bK: '將', bA: '士', bE: '象', bH: '馬', bR: '車', bC: '砲', bP: '卒',
};
const pieceName = (kind) => t('xiangqi.piece.' + kind);

export default {
  async mount(root, ctx, param) {
    if (!param) {
      const clocks = clockOptions();
      let clockPreset = localStorage.getItem('hub.xiangqi.clock') || 'none';
      if (!clocks.some((c) => c.id === clockPreset)) clockPreset = 'none';
      const clockSelect = createSelect({
        options: clocks.map((c) => ({ value: c.id, label: c.label })),
        value: clockPreset,
        ariaLabel: t('chess.clockLabel'),
        onChange: (val) => {
          clockPreset = val;
          localStorage.setItem('hub.xiangqi.clock', clockPreset);
        },
      });
      return renderLobby(root, ctx, CHANNEL, {
        title: t('xiangqi.title'),
        blurb: t('xiangqi.blurb'),
        iconName: 'xiangqi',
        extraFields: () => h('div', { class: 'field' }, h('label', {}, t('chess.clockLabel')), clockSelect),
        extraBody: () => ({ config: { clock: clockPreset } }),
        onEnter: (code) => ctx.navigate(`${CHANNEL}/${code}`),
      });
    }
    return mountRoom(root, ctx, param.toUpperCase());
  },
};

function mountRoom(root, ctx, code) {
  const { net } = ctx;
  let state = null;
  let selected = -1;
  let flipped = localStorage.getItem('hub.xiangqi.flip') === '1';
  let autoFlipped = false;
  let prevMoves = -1;
  let prevStatus = '';
  let clockSkew = 0;
  let boardFlippedRendered = null;
  const cellsByIndex = new Map();

  const statusBar = h('div', { class: 'status-bar', role: 'status', 'aria-live': 'polite' },
    t('shell.connecting'));
  const board = h('div', { class: 'xq-board', role: 'grid', 'aria-label': t('xiangqi.boardAria') });
  const fileBar = h('div', { class: 'xq-files' });
  const rankBar = h('div', { class: 'xq-ranks' });
  const banner = h('div', {});
  const mobileSeats = h('div', { class: 'mobile-seats' });
  const actions = h('div', { class: 'row-wrap' });
  const side = h('div', { class: 'game-side' });

  mount(root,
    h('div', { class: 'game-layout' },
      h('div', { class: 'game-main' },
        statusBar, banner, mobileSeats,
        h('div', { class: 'xq-frame' }, rankBar, board, fileBar),
        actions),
      side));

  /* ---------------------------------------------------------- toạ độ ------ */
  function order() {
    const out = [];
    for (let r = 0; r < ROWS; r++) {
      for (let c = 0; c < COLS; c++) {
        out.push(flipped ? (ROWS - 1 - r) * COLS + (COLS - 1 - c) : r * COLS + c);
      }
    }
    return out;
  }

  const squareName = (index) => FILES[index % COLS] + (ROWS - Math.floor(index / COLS));

  function renderAxes() {
    const files = flipped ? [...FILES].reverse() : [...FILES];
    mount(fileBar, files.map((f) => h('span', {}, f)));
    const ranks = [];
    for (let r = 0; r < ROWS; r++) ranks.push(flipped ? r + 1 : ROWS - r);
    mount(rankBar, ranks.map((r) => h('span', {}, String(r))));
  }

  const fitGlyphs = () => {
    const width = board.clientWidth;
    if (width) board.style.fontSize = Math.round((width / COLS) * 0.56) + 'px';
  };
  const resizeObserver = new ResizeObserver(fitGlyphs);
  resizeObserver.observe(board);

  /* ---------------------------------------------------------- nước đi ----- */
  const movesFrom = (index) => (state?.legal || {})[String(index)] || [];
  const canPlay = () => Boolean(state) && state.status === 'playing'
    && state.you.mark && state.turn === state.you.mark;

  function onSquare(index) {
    if (!state) return;
    if (!canPlay()) {
      if (state.you.mark && state.status === 'playing') toast(t('chess.notYourTurn'));
      return;
    }
    if (selected >= 0) {
      if (movesFrom(selected).includes(index)) {
        const from = selected;
        selected = -1;
        net.send(CHANNEL, 'move', { from, to: index });
        return;
      }
      if (index === selected) { selected = -1; render(); return; }
    }
    if (movesFrom(index).length) {
      selected = index;
      render();
      return;
    }
    const piece = state.board[index];
    if (piece && piece[0] === state.colorOf[state.you.mark]) {
      toast(t('chess.noMovesPiece'));
    }
    selected = -1;
    render();
  }

  /* ---------------------------------------------------------- vẽ bàn ----- */
  function ensureBoardGrid() {
    if (boardFlippedRendered === flipped && cellsByIndex.size === COLS * ROWS) return;
    boardFlippedRendered = flipped;
    cellsByIndex.clear();
    clear(board);
    for (const index of order()) {
      const row = Math.floor(index / COLS);
      const col = index % COLS;
      const palace = col >= 3 && col <= 5 && (row <= 2 || row >= 7);
      const baseCls = 'xq-cell'
        + (palace ? ' palace' : '')
        + (row === 4 ? ' river-top' : '')
        + (row === 5 ? ' river-bottom' : '');
      const cell = h('button', {
        type: 'button',
        class: baseCls,
        dataset: { index: String(index), baseCls, piece: '', dot: '0' },
        role: 'gridcell',
        onclick: () => onSquare(index),
      });
      cellsByIndex.set(index, cell);
      board.appendChild(cell);
    }
    fitGlyphs();
  }

  function renderBoard() {
    ensureBoardGrid();
    const s = state;
    const targets = new Set(selected >= 0 ? movesFrom(selected) : []);
    const [lastFrom, lastTo] = s.lastMove || [-1, -1];
    const checkIndex = s.checkMark ? s.kingIndex[s.checkMark] : -1;
    const playable = canPlay();
    const myColor = s.you.mark ? s.colorOf[s.you.mark] : '';

    board.classList.toggle('playable', playable);
    for (const [index, cell] of cellsByIndex.entries()) {
      const piece = s.board[index];
      const mine = piece && piece[0] === myColor;
      const hit = targets.has(index);
      const cls = cell.dataset.baseCls
        + (index === selected ? ' selected' : '')
        + (index === lastFrom || index === lastTo ? ' last' : '')
        + (index === checkIndex ? ' check' : '')
        + (hit ? (piece ? ' capture' : ' move') : '')
        + (playable && mine && movesFrom(index).length ? ' grabbable' : '');
      if (cell.className !== cls) cell.className = cls;

      const sideWord = piece ? (piece[0] === 'r' ? t('xiangqi.red') : t('xiangqi.black')) : '';
      const pName = piece ? pieceName(piece[1]) : '';
      const label = squareName(index)
        + (piece ? ` — ${sideWord} ${pName}` : ` — ${t('chess.emptySq')}`);
      if (cell.getAttribute('aria-label') !== label) cell.setAttribute('aria-label', label);

      const needDot = hit && !piece ? '1' : '0';
      const pieceTitle = piece ? `${sideWord} ${pName}` : '';
      if (cell.dataset.piece !== piece || cell.dataset.dot !== needDot || cell.dataset.pt !== pieceTitle) {
        cell.dataset.piece = piece;
        cell.dataset.dot = needDot;
        cell.dataset.pt = pieceTitle;
        clear(cell);
        if (piece) {
          cell.appendChild(h('span', {
            class: 'xq-piece ' + piece[0],
            title: pieceTitle,
          }, GLYPH[piece] || '?'));
        } else if (needDot === '1') {
          cell.appendChild(h('span', { class: 'xq-dot' }));
        }
      }
    }
  }

  /* ------------------------------------------------------- panel phụ ----- */
  function moveList() {
    const s = state;
    const rows = h('div', { class: 'movelist' });
    for (let i = 0; i < s.moves.length; i += 2) {
      const red = s.moves[i];
      const black = s.moves[i + 1];
      rows.appendChild(h('div', { class: 'movelist-row' },
        h('span', { class: 'movelist-no' }, String(i / 2 + 1) + '.'),
        h('span', { class: 'movelist-san' }, red ? red.note : ''),
        h('span', { class: 'movelist-san' }, black ? black.note : '')));
    }
    if (!s.moves.length) {
      rows.appendChild(h('div', { class: 'tiny muted' }, t('chess.noMovesYet')));
    }
    const card = h('div', { class: 'card tight col' },
      h('div', { class: 'spread' },
        h('div', { class: 'card-title', style: { margin: '0' } }, t('chess.movesTitle')),
        h('span', { class: 'tiny muted' }, t('chess.moveCount', { n: s.moveCount }))),
      rows,
      h('div', { class: 'tiny muted' }, t('xiangqi.notationHint')));
    requestAnimationFrame(() => { rows.scrollTop = rows.scrollHeight; });
    return card;
  }

  function capturedPanel() {
    const s = state;
    const line = (mark) => {
      const taken = s.captured[mark] || [];
      return h('div', { class: 'captured-row' },
        h('span', { class: 'tiny muted nowrap' },
          t('chess.capturedBy', { seat: seatLabelI18n(s.seatLabels[mark]) })),
        taken.length
          ? h('span', { class: 'captured-line' },
              taken.map((piece) => h('span', {
                class: 'xq-piece sm ' + piece[0],
                title: pieceName(piece[1]),
              }, GLYPH[piece] || '?')))
          : h('span', { class: 'tiny muted' }, '—'));
    };
    return h('div', { class: 'card tight col' },
      h('div', { class: 'card-title', style: { marginBottom: '2px' } }, t('chess.capturedTitle')),
      line('X'), line('O'));
  }

  function renderBanner() {
    const s = state;
    const mine = s.you.mark;
    clear(banner);
    if (s.status === 'playing' && mine && s.undoOffer && s.undoOffer !== mine) {
      const who = s.seats[s.undoOffer];
      banner.appendChild(h('div', { class: 'banner warn row-wrap' },
        h('span', { class: 'grow' },
          t('chess.undoAsked', { name: who ? who.name : t('xiangqi.opponent') })),
        h('button', { class: 'sm primary', onclick: () => net.send(CHANNEL, 'undo-accept') },
          t('chess.accept')),
        h('button', { class: 'sm ghost', onclick: () => net.send(CHANNEL, 'undo-decline') },
          t('chess.decline'))));
      return;
    }
    if (s.status === 'playing' && mine && s.undoOffer === mine) {
      banner.appendChild(h('div', { class: 'banner row-wrap' },
        h('span', { class: 'grow' }, t('chess.undoSent')),
        h('button', { class: 'sm ghost', onclick: () => net.send(CHANNEL, 'undo') },
          t('chess.withdraw'))));
      return;
    }
    if (s.status === 'playing' && mine && s.drawOffer && s.drawOffer !== mine) {
      const who = s.seats[s.drawOffer];
      banner.appendChild(h('div', { class: 'banner warn row-wrap' },
        h('span', { class: 'grow' },
          t('chess.drawAsked', { name: who ? who.name : t('xiangqi.opponent') })),
        h('button', { class: 'sm primary', onclick: () => net.send(CHANNEL, 'draw-accept') },
          t('chess.acceptDraw')),
        h('button', { class: 'sm ghost', onclick: () => net.send(CHANNEL, 'draw-decline') },
          t('chess.decline'))));
      return;
    }
    if (s.status === 'playing' && mine && s.drawOffer === mine) {
      banner.appendChild(h('div', { class: 'banner row-wrap' },
        h('span', { class: 'grow' }, t('chess.drawSent')),
        h('button', { class: 'sm ghost', onclick: () => net.send(CHANNEL, 'draw') },
          t('chess.withdraw'))));
      return;
    }
    if (s.status === 'finished' && s.note) {
      banner.appendChild(h('div', { class: 'banner' }, s.note));
    }
  }

  function statusText(s) {
    const mine = s.you.mark;
    const foeMark = mine === 'X' ? 'O' : 'X';
    if (s.status === 'waiting') {
      if (!mine) return { text: t('caro.waitTwo'), cls: 'wait' };
      return { text: t('chess.waitSeat', { seat: seatLabelI18n(s.seatLabels[mine]) }), cls: 'wait' };
    }
    if (s.status === 'playing') {
      const seat = s.seats[s.turn];
      const checkNote = s.check ? t('chess.inCheck') : '';
      if (!mine) {
        return {
          text: t('chess.specTurn', {
            name: seat ? seat.name : '',
            seat: seatLabelI18n(s.seatLabels[s.turn]),
            check: checkNote,
          }),
          cls: '',
        };
      }
      if (s.turn === mine) {
        return {
          text: t('xiangqi.yourTurn', {
            seat: seatLabelI18n(s.seatLabels[mine]),
            check: checkNote,
          }),
          cls: 'turn',
        };
      }
      const foe = s.seats[foeMark];
      if (foe && !foe.connected) {
        return { text: t('caro.foeOffline', { name: foe.name }), cls: 'wait' };
      }
      return {
        text: t('chess.waitFoe', {
          name: foe ? foe.name : t('xiangqi.opponent'),
          seat: seatLabelI18n(s.seatLabels[foeMark]),
        }),
        cls: 'wait',
      };
    }
    if (s.winner === 'draw') return { text: t('chess.drawResult'), cls: '' };
    const champ = s.seats[s.winner];
    if (mine && s.winner === mine) return { text: t('caro.youWin'), cls: 'won' };
    if (mine) return { text: t('caro.youLose', { name: champ ? champ.name : '' }), cls: 'lost' };
    return {
      text: t('chess.otherWin', {
        name: champ ? champ.name : '',
        seat: seatLabelI18n(s.seatLabels[s.winner] || ''),
      }),
      cls: '',
    };
  }

  function toolbar() {
    const s = state;
    const row = h('div', { class: 'row-wrap' });
    row.appendChild(h('button', {
      class: 'sm ghost',
      onclick: () => {
        flipped = !flipped;
        localStorage.setItem('hub.xiangqi.flip', flipped ? '1' : '0');
        render();
      },
    }, t('chess.flipBoard')));
    if (s.status === 'playing' && s.you.mark && s.canUndo && s.undoOffer !== s.you.mark) {
      row.appendChild(h('button', {
        class: 'sm', onclick: () => net.send(CHANNEL, 'undo'),
      }, t('chess.askUndo')));
    }
    if (s.status === 'playing' && s.you.mark && s.drawOffer !== s.you.mark) {
      row.appendChild(h('button', {
        class: 'sm', onclick: () => net.send(CHANNEL, 'draw'),
      }, t('chess.askDraw')));
    }
    row.appendChild(h('span', { class: 'chip' },
      t('xiangqi.idle60', { n: Math.floor((s.idle || 0) / 2) })));
    return row;
  }

  function updateClockNodes() {
    if (!state || !state.clock || !state.clock.enabled) return;
    const clock = state.clock;
    const nowServer = Date.now() / 1000 + clockSkew;
    for (const el of root.querySelectorAll('[data-clock-seat]')) {
      const mark = el.dataset.clockSeat;
      let rem = Number((clock.remain && clock.remain[mark]) ?? clock.initial ?? 0);
      if (state.status === 'playing' && state.turn === mark && clock.turnStartedAt) {
        rem = Math.max(0, rem - Math.max(0, nowServer - clock.turnStartedAt));
      }
      el.textContent = '⏱ ' + formatClockSec(rem);
      el.classList.toggle('low', state.status === 'playing' && rem <= 20);
    }
  }

  /* --------------------------------------------------------------- render */
  function render() {
    const s = state;
    if (!s) return;

    // Quân Đỏ vẽ ở dưới theo lệ. Ai cầm Đen thì tự quay bàn một lần cho dễ
    // nhìn, sau đó tôn trọng lựa chọn thủ công.
    if (!autoFlipped && s.you.mark) {
      flipped = s.colorOf[s.you.mark] === 'b';
      autoFlipped = true;
    }

    renderAxes();
    renderBoard();
    renderBanner();

    const info = statusText(s);
    statusBar.textContent = info.text;
    statusBar.className = 'status-bar ' + info.cls;

    mount(mobileSeats, seatPanel(s, { markClass: false, clockSkew }));
    mount(actions, actionRow(s, net, CHANNEL), toolbar());
    mount(side, seatPanel(s, { markClass: false, clockSkew }), capturedPanel(), moveList(),
          roomCard(s, CHANNEL), roomChat(s, net, CHANNEL));
    ctx.setTopbar(...roomTopbar(ctx, s, CHANNEL, t('xiangqi.title')));

    if (prevMoves >= 0) {
      if (s.status === 'finished' && prevStatus !== 'finished') {
        if (s.you.mark && s.winner === s.you.mark) sfx.win();
        else if (s.you.mark && s.winner !== 'draw') sfx.lose();
        else sfx.move();
      } else if (s.moveCount > prevMoves) {
        const last = s.moves[s.moves.length - 1];
        if (last && last.mark !== s.you.mark) (s.check ? sfx.hit() : sfx.move());
      }
    }
    prevMoves = s.moveCount;
    prevStatus = s.status;
  }

  /* --------------------------------------------------------------- mạng -- */
  const stop = net.on(CHANNEL, (msg) => {
    if (msg.t === 'state') {
      if (msg.serverNow) clockSkew = msg.serverNow - Date.now() / 1000;
      if (!state || msg.moveCount < (state.moveCount || 0)) selected = -1;
      state = msg;
      if (selected >= 0 && !movesFrom(selected).length) selected = -1;
      render();
    } else if (msg.t === 'error') {
      selected = -1;
      toast(msg.message, 'danger');
      if (state) render();
    } else if (msg.t === 'closed') {
      toast(msg.message || t('shell.roomClosed'), 'danger');
      ctx.navigate(CHANNEL);
    }
  });

  const clockTimer = setInterval(updateClockNodes, 250);

  const onKey = (event) => {
    if (event.key === 'Escape' && selected >= 0) { selected = -1; render(); }
  };
  window.addEventListener('keydown', onKey);

  const join = () => net.send(CHANNEL, 'join', { room: code });
  const stopRejoin = net.onRejoin(join);
  join();

  return () => {
    stop();
    stopRejoin();
    clearInterval(clockTimer);
    resizeObserver.disconnect();
    window.removeEventListener('keydown', onKey);
    net.send(CHANNEL, 'leave');
  };
}

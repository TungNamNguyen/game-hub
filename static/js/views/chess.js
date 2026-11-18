/* Cờ vua. Bàn 8x8, quân vẽ bằng ký tự Unicode nên không cần ảnh.
 *
 * Client KHÔNG biết luật cờ vua. Server gửi kèm danh sách nước đi hợp lệ của
 * riêng người đang tới lượt (`state.legal`), việc của view này chỉ là tô sáng
 * các ô đó và gửi lại nước người dùng chọn. Nhờ vậy luật chỉ tồn tại ở một
 * chỗ (chessgame.py) và không có cách nào đi nước sai qua DevTools.
 */

import { clear, h, mount } from '../dom.js';
import { seatLabelI18n, t } from '../i18n.js';
import { chooseBox, createSelect, sfx, toast } from '../ui.js';
import { actionRow, formatClockSec, renderLobby, roomCard, roomChat, roomTopbar, seatPanel } from './gameroom.js';

const CHANNEL = 'chess';

// Dùng bộ ký tự đặc (♚) cho CẢ hai màu rồi phân biệt bằng màu chữ + viền ở CSS.
// Bộ rỗng (♔) mảnh hơn nhiều nên đặt cạnh bộ đặc sẽ lệch trọng lượng thị giác.
const GLYPH = { K: '♚', Q: '♛', R: '♜', B: '♝', N: '♞', P: '♟' };
const pieceName = (kind) => t('chess.piece.' + kind);
const PROMO_ORDER = ['Q', 'R', 'B', 'N'];
const FILES = 'abcdefgh';
const clockOptions = () => [
  { id: 'none', label: t('chess.clockNone') },
  { id: '180+2', label: t('chess.clock180') },
  { id: '600+0', label: t('chess.clock600') },
  { id: '900+5', label: t('chess.clock900') },
];

export default {
  async mount(root, ctx, param) {
    if (!param) {
      const clocks = clockOptions();
      let clockPreset = localStorage.getItem('hub.chess.clock') || 'none';
      if (!clocks.some((c) => c.id === clockPreset)) clockPreset = 'none';
      const clockSelect = createSelect({
        options: clocks.map((c) => ({ value: c.id, label: c.label })),
        value: clockPreset,
        ariaLabel: t('chess.clockLabel'),
        onChange: (val) => {
          clockPreset = val;
          localStorage.setItem('hub.chess.clock', clockPreset);
        },
      });
      return renderLobby(root, ctx, CHANNEL, {
        title: t('chess.title'),
        blurb: t('chess.blurb'),
        iconName: 'chess',
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
  let flipped = localStorage.getItem('hub.chess.flip') === '1';
  let autoFlipped = false;     // đã tự quay bàn theo màu quân của mình chưa
  let prevMoves = -1;
  let prevStatus = '';
  let promoting = false;       // đang mở hộp thoại phong cấp
  let clockSkew = 0;
  let boardFlippedRendered = null;
  const cellsByIndex = new Map();

  const statusBar = h('div', { class: 'status-bar', role: 'status', 'aria-live': 'polite' },
    t('shell.connecting'));
  const board = h('div', { class: 'chess-board', role: 'grid', 'aria-label': t('chess.boardAria') });
  const fileBar = h('div', { class: 'chess-files' });
  const rankBar = h('div', { class: 'chess-ranks' });
  const banner = h('div', {});
  const mobileSeats = h('div', { class: 'mobile-seats' });
  const actions = h('div', { class: 'row-wrap' });
  const side = h('div', { class: 'game-side' });

  // Grid 2 cột x 2 hàng: nhãn hàng bên trái CÙNG HÀNG với bàn, nhãn cột ở
  // dưới CÙNG CỘT với bàn. Nhờ vậy nhãn luôn thẳng với ô dù bàn co giãn.
  const frame = h('div', { class: 'chess-frame' }, rankBar, board, fileBar);

  mount(root,
    h('div', { class: 'game-layout' },
      h('div', { class: 'game-main' },
        statusBar, banner, mobileSeats, frame, actions),
      side));

  /* ---------------------------------------------------------- toạ độ ------ */
  /** Thứ tự index bàn theo cách vẽ hiện tại (có thể đã quay 180°). */
  function order() {
    const out = [];
    for (let r = 0; r < 8; r++) {
      for (let c = 0; c < 8; c++) {
        out.push(flipped ? (7 - r) * 8 + (7 - c) : r * 8 + c);
      }
    }
    return out;
  }

  const squareName = (index) => FILES[index % 8] + (8 - Math.floor(index / 8));

  function renderAxes() {
    const files = flipped ? [...FILES].reverse() : [...FILES];
    mount(fileBar, files.map((f) => h('span', {}, f)));
    const ranks = flipped ? [1, 2, 3, 4, 5, 6, 7, 8] : [8, 7, 6, 5, 4, 3, 2, 1];
    mount(rankBar, ranks.map((r) => h('span', {}, String(r))));
  }

  // Ký tự quân phải to theo ô. Cỡ ô do CSS quyết định (bàn co theo khung), nên
  // đo lại bằng ResizeObserver thay vì tính bằng công thức.
  const fitGlyphs = () => {
    const width = board.clientWidth;
    if (width) board.style.fontSize = Math.round((width / 8) * 0.76) + 'px';
  };
  const resizeObserver = new ResizeObserver(fitGlyphs);
  resizeObserver.observe(board);

  /* ---------------------------------------------------------- nước đi ----- */
  const movesFrom = (index) => (state?.legal || {})[String(index)] || [];
  const canPlay = () => Boolean(state) && state.status === 'playing'
    && state.you.mark && state.turn === state.you.mark;

  async function commit(frm, option) {
    let promo = '';
    if (option.promo) {
      promoting = true;
      const color = state.colorOf[state.you.mark];
      promo = await chooseBox({
        title: t('chess.promoTitle'),
        body: t('chess.promoBody', { sq: squareName(option.to) }),
        options: PROMO_ORDER.map((kind) => ({
          id: kind,
          label: pieceName(kind),
          glyph: h('span', { class: 'chess-piece ' + color }, GLYPH[kind]),
        })),
        fallback: 'Q',
      });
      promoting = false;
      if (!promo) promo = 'Q';
    }
    selected = -1;
    // Optimistic UI: di chuyển quân ngay lập tức trên bàn (0ms)
    if (state && state.board) {
      const myColor = state.colorOf[state.you.mark];
      state.board[option.to] = promo ? (myColor + promo) : state.board[frm];
      state.board[frm] = '';
      state.lastMove = [frm, option.to];
      state.turn = state.you.mark === 'X' ? 'O' : 'X';
      state.legal = {};
      sfx.move();
      renderBoard();
      const info = statusText(state);
      statusBar.textContent = info.text;
      statusBar.className = 'status-bar ' + info.cls;
    }
    net.send(CHANNEL, 'move', { from: frm, to: option.to, promo });
  }

  function onSquare(index) {
    if (!state || promoting) return;
    if (!canPlay()) {
      if (state.you.mark && state.status === 'playing') toast(t('chess.notYourTurn'));
      return;
    }
    if (selected >= 0) {
      const option = movesFrom(selected).find((m) => m.to === index);
      if (option) { commit(selected, option); return; }
      if (index === selected) { selected = -1; renderBoard(); return; }
    }
    if (movesFrom(index).length) {
      selected = index;
      renderBoard();
    } else if (state.board[index] && state.board[index][0] === state.colorOf[state.you.mark]) {
      selected = -1;
      toast(t('chess.noMovesPiece'));
      renderBoard();
    } else if (selected >= 0) {
      selected = -1;
      renderBoard();
    }
  }

  /* ---------------------------------------------------------- vẽ bàn ----- */
  function ensureBoardGrid() {
    if (boardFlippedRendered === flipped && cellsByIndex.size === 64) return;
    boardFlippedRendered = flipped;
    cellsByIndex.clear();
    clear(board);
    for (const index of order()) {
      const row = Math.floor(index / 8);
      const dark = (row + (index % 8)) % 2 === 1;
      const cell = h('button', {
        type: 'button',
        class: 'chess-cell' + (dark ? ' dark' : ' light'),
        dataset: { index: String(index), dark: dark ? '1' : '0', piece: '', dot: '0' },
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
    const targets = new Map();
    if (selected >= 0) for (const m of movesFrom(selected)) targets.set(m.to, m);
    const [lastFrom, lastTo] = s.lastMove || [-1, -1];
    const checkIndex = s.checkMark ? s.kingIndex[s.checkMark] : -1;
    const playable = canPlay();
    const myColor = s.you.mark ? s.colorOf[s.you.mark] : '';

    board.classList.toggle('playable', playable);
    for (const [index, cell] of cellsByIndex.entries()) {
      const piece = s.board[index];
      const target = targets.get(index);
      const mine = piece && piece[0] === myColor;
      const dark = cell.dataset.dark === '1';

      const cls = 'chess-cell' + (dark ? ' dark' : ' light')
        + (index === selected ? ' selected' : '')
        + (index === lastFrom || index === lastTo ? ' last' : '')
        + (index === checkIndex ? ' check' : '')
        + (target ? (piece ? ' capture' : ' move') : '')
        + (playable && mine && movesFrom(index).length ? ' grabbable' : '');
      if (cell.className !== cls) cell.className = cls;

      const label = squareName(index)
        + (piece
          ? ` — ${piece[0] === 'w' ? t('chess.white') : t('chess.black')} ${pieceName(piece[1])}`
          : ` — ${t('chess.emptySq')}`);
      if (cell.getAttribute('aria-label') !== label) cell.setAttribute('aria-label', label);

      const needDot = target && !piece ? '1' : '0';
      const pieceTitle = piece ? pieceName(piece[1]) : '';
      if (cell.dataset.piece !== piece || cell.dataset.dot !== needDot || cell.dataset.pt !== pieceTitle) {
        cell.dataset.piece = piece;
        cell.dataset.dot = needDot;
        cell.dataset.pt = pieceTitle;
        clear(cell);
        if (piece) {
          cell.appendChild(h('span', { class: 'chess-piece ' + piece[0], title: pieceTitle },
            GLYPH[piece[1]]));
        } else if (needDot === '1') {
          cell.appendChild(h('span', { class: 'chess-dot' }));
        }
      }
    }
  }

  /* ------------------------------------------------------- panel phụ ----- */
  function moveList() {
    const s = state;
    const rows = h('div', { class: 'movelist' });
    for (let i = 0; i < s.moves.length; i += 2) {
      const white = s.moves[i];
      const black = s.moves[i + 1];
      rows.appendChild(h('div', { class: 'movelist-row' },
        h('span', { class: 'movelist-no' }, String(i / 2 + 1) + '.'),
        h('span', { class: 'movelist-san' }, white ? white.san : ''),
        h('span', { class: 'movelist-san' }, black ? black.san : '')));
    }
    if (!s.moves.length) {
      rows.appendChild(h('div', { class: 'tiny muted' }, t('chess.noMovesYet')));
    }
    const card = h('div', { class: 'card tight col' },
      h('div', { class: 'spread' },
        h('div', { class: 'card-title', style: { margin: '0' } }, t('chess.movesTitle')),
        h('span', { class: 'tiny muted' }, t('chess.moveCount', { n: s.moveCount }))),
      rows);
    // Nước mới nhất luôn nằm trong tầm mắt.
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
              // Quân bị ăn đã mang sẵn màu của nó ("bQ"), dùng luôn thay vì
              // suy ra từ màu của người ăn.
              taken.map((piece) => h('span', {
                class: 'chess-piece sm ' + piece[0], title: pieceName(piece[1]),
              }, GLYPH[piece[1]])))
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
          text: t('chess.yourTurn', {
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
        localStorage.setItem('hub.chess.flip', flipped ? '1' : '0');
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
      t('chess.rule50', { n: Math.floor((s.halfmove || 0) / 2) })));
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

    // Lần đầu vào ghế thì tự quay bàn về phía quân của mình. Sau đó tôn trọng
    // lựa chọn thủ công của người dùng, không tự quay nữa.
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
    ctx.setTopbar(...roomTopbar(ctx, s, CHANNEL, t('chess.title')));

    // Âm thanh chỉ kêu khi có thay đổi thật, không kêu lúc mới vào phòng.
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
      // Ván mới / bàn đổi thì bỏ ô đang chọn để không giữ ô cũ không còn nghĩa.
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

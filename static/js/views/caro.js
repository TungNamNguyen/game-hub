/* Cờ caro / XO. Bàn từ 3x3 tới 50x50, cuộn và zoom được. */

import { clear, h, mount, numberOf } from '../dom.js';
import { t } from '../i18n.js';
import { sfx, toast } from '../ui.js';
import { actionRow, renderLobby, roomCard, roomChat, roomTopbar, seatPanel } from './gameroom.js';

const CHANNEL = 'caro';
const MIN_CELL = 20;    // nhỏ hơn mức này thì bấm chuột hay trượt
const MAX_CELL = 48;    // to hơn thì bàn nhỏ trông thưa thớt
const ZOOM_PX = 6;

export default {
  async mount(root, ctx, param) {
    if (!param) {
      return renderLobby(root, ctx, CHANNEL, {
        title: t('caro.title'),
        blurb: t('caro.blurb'),
        onEnter: (code) => ctx.navigate(`${CHANNEL}/${code}`),
      });
    }
    return mountRoom(root, ctx, param.toUpperCase());
  },
};

function mountRoom(root, ctx, code) {
  const { net } = ctx;
  let state = null;
  let builtSize = 0;
  let renderedClass = [];
  let appliedCell = 0;
  let zoomStep = Number(localStorage.getItem('hub.caro.zoom') || 0) || 0;
  let prevMoves = -1;
  let prevStatus = '';
  let prevLastMove = -1;

  const board = h('div', { class: 'caro-board', role: 'grid', 'aria-label': t('caro.boardAria') });
  const boardWrap = h('div', { class: 'board-wrap' }, board);
  const statusBar = h('div', { class: 'status-bar', role: 'status', 'aria-live': 'polite' },
    t('shell.connecting'));
  const mobileSeats = h('div', { class: 'mobile-seats' });
  const boardInfo = h('span', {});
  const actions = h('div', { class: 'row-wrap' });
  const side = h('div', { class: 'col game-side-col', style: { flex: '0 1 300px', minWidth: '260px' } });

  const zoomBar = h('div', { class: 'zoombar' },
    boardInfo,
    h('span', { class: 'grow' }),
    h('button', { class: 'xs', onclick: () => setZoom(zoomStep - 1) }, t('caro.zoomOut')),
    h('button', { class: 'xs', onclick: () => { setZoom(0); requestAnimationFrame(centerBoard); } },
      t('caro.zoomReset')),
    h('button', { class: 'xs', onclick: () => setZoom(zoomStep + 1) }, t('caro.zoomIn')),
    h('button', {
      class: 'xs',
      onclick: () => {
        if (state && state.lastMove >= 0) revealCell(state.lastMove, true);
        else centerBoard();
      },
    }, t('caro.lastMove')));

  mount(root,
    h('div', { class: 'row-wrap', style: { alignItems: 'flex-start', gap: '16px' } },
      h('div', { class: 'board-shell', style: { flex: '1 1 520px', minWidth: '0' } },
        statusBar, mobileSeats, boardWrap, zoomBar, actions),
      side));

  /* ---------------------------------------------------------- vẽ bàn cờ -- */
  function buildBoard(size) {
    board.style.setProperty('--n', size);
    clear(board);
    const frag = document.createDocumentFragment();
    for (let i = 0; i < size * size; i++) {
      const cell = document.createElement('button');
      cell.type = 'button';
      cell.className = 'caro-cell empty';
      cell.dataset.index = i;
      cell.setAttribute('role', 'gridcell');
      cell.setAttribute('aria-label',
        t('caro.cellAria', { r: Math.floor(i / size) + 1, c: (i % size) + 1 }));
      frag.appendChild(cell);
    }
    board.appendChild(frag);
    builtSize = size;
    renderedClass = new Array(size * size).fill('');
    appliedCell = 0;
    applyCellSize();
    requestAnimationFrame(centerBoard);
  }

  /** Cỡ ô vừa khung hiện tại, trước khi cộng zoom của người chơi. */
  function autoCell(size) {
    const availW = boardWrap.clientWidth - 12;
    const availH = Math.max(260, window.innerHeight * 0.68) - 12;
    const fit = Math.floor(Math.min(availW, availH) / size) - 1;
    return Math.max(MIN_CELL, Math.min(MAX_CELL, fit));
  }

  function applyCellSize() {
    if (!builtSize) return;
    const cell = Math.max(12, Math.min(96, autoCell(builtSize) + zoomStep * ZOOM_PX));
    if (cell === appliedCell) return;   // tránh ghi lại vô ích -> khỏi lặp resize
    appliedCell = cell;
    board.style.setProperty('--cell', cell + 'px');
    board.style.fontSize = Math.max(8, Math.round(cell * 0.66)) + 'px';
  }

  function setZoom(step) {
    zoomStep = Math.max(-4, Math.min(10, step));
    localStorage.setItem('hub.caro.zoom', String(zoomStep));
    applyCellSize();
  }

  function centerBoard() {
    boardWrap.scrollLeft = Math.max(0, (boardWrap.scrollWidth - boardWrap.clientWidth) / 2);
    boardWrap.scrollTop = Math.max(0, (boardWrap.scrollHeight - boardWrap.clientHeight) / 2);
  }

  /** Kéo khung về ô chỉ định nếu nó đang nằm ngoài vùng nhìn thấy. */
  function revealCell(index, force) {
    if (index < 0 || !builtSize) return;
    const cell = board.children[index];
    if (!cell) return;
    const scrollable = boardWrap.scrollWidth > boardWrap.clientWidth + 2
                    || boardWrap.scrollHeight > boardWrap.clientHeight + 2;
    if (!scrollable) return;
    const left = cell.offsetLeft, top = cell.offsetTop;
    const visible = left >= boardWrap.scrollLeft
      && left + cell.offsetWidth <= boardWrap.scrollLeft + boardWrap.clientWidth
      && top >= boardWrap.scrollTop
      && top + cell.offsetHeight <= boardWrap.scrollTop + boardWrap.clientHeight;
    if (visible && !force) return;
    boardWrap.scrollTo({
      left: left - boardWrap.clientWidth / 2 + cell.offsetWidth / 2,
      top: top - boardWrap.clientHeight / 2 + cell.offsetHeight / 2,
      behavior: 'smooth',
    });
  }

  board.onclick = (event) => {
    const cell = event.target.closest('.caro-cell');
    if (!cell || !state) return;
    const index = Number(cell.dataset.index);
    if (state.board[index]) return;
    if (state.status !== 'playing' || state.turn !== state.you.mark) return;
    net.send(CHANNEL, 'move', { index });
  };

  // Ctrl + lăn chuột để zoom, như mọi thứ khác trên máy tính.
  const onWheel = (event) => {
    if (!event.ctrlKey) return;
    event.preventDefault();
    setZoom(zoomStep + (event.deltaY < 0 ? 1 : -1));
  };
  boardWrap.addEventListener('wheel', onWheel, { passive: false });

  const resizeObserver = new ResizeObserver(applyCellSize);
  resizeObserver.observe(boardWrap);
  window.addEventListener('resize', applyCellSize);

  /* ------------------------------------------------------------- render -- */
  function statusText(s) {
    const mine = s.you.mark;
    const other = mine === 'X' ? 'O' : 'X';
    if (s.status === 'waiting') {
      if (!mine) return { text: t('caro.waitTwo'), cls: 'wait' };
      return { text: t('caro.waitOther', { mine, other }), cls: 'wait' };
    }
    if (s.status === 'playing') {
      const seat = s.seats[s.turn];
      if (!mine) return { text: t('caro.specTurn', { name: seat ? seat.name : s.turn, mark: s.turn }), cls: '' };
      if (s.turn === mine) return { text: t('caro.yourTurn', { mark: mine }), cls: 'turn' };
      const foe = s.seats[other];
      if (foe && !foe.connected) {
        return { text: t('caro.foeOffline', { name: foe.name }), cls: 'wait' };
      }
      return { text: t('caro.waitFoe', { name: foe ? foe.name : other, mark: other }), cls: 'wait' };
    }
    if (s.winner === 'draw') return { text: t('caro.draw'), cls: '' };
    const champ = s.seats[s.winner];
    if (mine && s.winner === mine) return { text: t('caro.youWin'), cls: 'won' };
    if (mine) return { text: t('caro.youLose', { name: champ ? champ.name : s.winner }), cls: 'lost' };
    return { text: t('caro.otherWin', { name: champ ? champ.name : s.winner, mark: s.winner }), cls: '' };
  }

  function render() {
    const s = state;
    if (!s) return;
    if (builtSize !== s.size) buildBoard(s.size);

    const mine = s.you.mark;
    const myTurn = s.status === 'playing' && s.turn === mine;
    board.classList.toggle('playable', myTurn);
    board.dataset.mark = mine || '';
    board.setAttribute('aria-disabled', String(!myTurn));

    // Chỉ ghi lại ô thật sự đổi và bỏ qua hoàn toàn vòng lặp 2.500 ô khi
    // gói state chỉ là tin nhắn chat hoặc thay đổi người xem.
    if (s.moveCount !== prevMoves || s.status !== prevStatus || s.lastMove !== prevLastMove) {
      const winSet = new Set(s.winLine);
      const cells = board.children;
      for (let i = 0; i < cells.length; i++) {
        const mark = s.board[i];
        const cls = 'caro-cell'
          + (mark ? ' ' + mark.toLowerCase() : ' empty')
          + (i === s.lastMove ? ' last' : '')
          + (winSet.has(i) ? ' win' : '');
        if (renderedClass[i] !== cls) {
          const cell = cells[i];
          cell.className = cls;
          if (cell.textContent !== mark) cell.textContent = mark;
          renderedClass[i] = cls;
        }
      }
    }

    const info = statusText(s);
    statusBar.textContent = info.text;
    statusBar.className = 'status-bar ' + info.cls;
    boardInfo.textContent =
      t('caro.boardInfo', { n: s.size, total: numberOf(s.size * s.size), win: s.winLen });

    mount(mobileSeats, seatPanel(s));
    mount(actions, actionRow(s, net, CHANNEL));
    mount(side, seatPanel(s), roomCard(s, CHANNEL), roomChat(s, net, CHANNEL));
    ctx.setTopbar(...roomTopbar(ctx, s, CHANNEL, t('caro.title')));

    // Bàn lớn thì nước của đối thủ có thể nằm ngoài vùng đang xem.
    if (s.lastMove !== prevLastMove) {
      if (s.lastMove >= 0) revealCell(s.lastMove, false);
      prevLastMove = s.lastMove;
    }
    if (s.winLine.length) revealCell(s.winLine[0], false);

    // Âm thanh chỉ kêu khi có thay đổi thật, không kêu lúc mới vào phòng.
    if (prevMoves >= 0) {
      if (s.status === 'finished' && prevStatus !== 'finished') {
        if (mine && s.winner === mine) sfx.win();
        else if (mine && s.winner !== 'draw') sfx.lose();
        else sfx.move();
      } else if (s.lastMove >= 0 && s.board[s.lastMove] !== mine && s.moveCount > prevMoves) {
        sfx.move();
      }
    }
    prevMoves = s.moveCount;
    prevStatus = s.status;
  }

  /* --------------------------------------------------------------- mạng -- */
  const stop = net.on(CHANNEL, (msg) => {
    if (msg.t === 'state') { state = msg; render(); }
    else if (msg.t === 'error') toast(msg.message, 'danger');
    else if (msg.t === 'closed') {
      toast(msg.message || t('shell.roomClosed'), 'danger');
      ctx.navigate(CHANNEL);
    }
  });

  const join = () => net.send(CHANNEL, 'join', { room: code });
  const stopRejoin = net.onRejoin(join);
  join();

  return () => {
    stop();
    stopRejoin();
    resizeObserver.disconnect();
    window.removeEventListener('resize', applyCellSize);
    boardWrap.removeEventListener('wheel', onWheel);
    net.send(CHANNEL, 'leave');
  };
}

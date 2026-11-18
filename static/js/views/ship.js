/* Bắn tàu. Pha xếp tàu (click chọn tàu rồi click lên bàn, R để quay) và pha bắn
 * với hai bàn cạnh nhau.
 *
 * Client không bao giờ biết tàu đối thủ ở đâu: server đã che trong match_view,
 * nên ở đây không có cách nào vẽ ra dù muốn.
 */

import { clear, h, icon, mount } from '../dom.js';
import { seatLabelI18n, shipNameI18n, t } from '../i18n.js';
import { sfx, toast } from '../ui.js';
import { actionRow, renderLobby, roomCard, roomChat, roomTopbar, seatPanel } from './gameroom.js';

const CHANNEL = 'ship';
const LETTERS = 'ABCDEFGHIJ';

export default {
  async mount(root, ctx, param) {
    if (!param) {
      return renderLobby(root, ctx, CHANNEL, {
        title: t('ship.title'),
        blurb: t('ship.blurb'),
        onEnter: (code) => ctx.navigate(`${CHANNEL}/${code}`),
      });
    }
    return mountRoom(root, ctx, param.toUpperCase());
  },
};

function mountRoom(root, ctx, code) {
  const { net } = ctx;
  let state = null;
  let selected = null;        // key tàu đang chọn để xếp
  let horizontal = true;
  let hover = -1;
  let prevStatus = '';
  let prevShots = -1;
  let prevEnemyHits = -1;
  let pendingShotIdx = -1;
  let ownCellNodes = [];

  const statusBar = h('div', { class: 'status-bar', role: 'status', 'aria-live': 'polite' },
    t('shell.connecting'));
  const ownBox = h('div', { class: 'ship-board-box' });
  const foeBox = h('div', { class: 'ship-board-box' });
  const mobileFleet = h('div', { class: 'mobile-fleet' });
  const actions = h('div', { class: 'row-wrap' });
  const side = h('div', { class: 'ship-side' });
  const placingBar = h('div', { class: 'row-wrap' });
  // Lớp "firing" cho CSS biết đang ở pha bắn: màn hẹp thì hai bàn xếp chồng,
  // lúc đó bàn đối thủ (nơi mình bấm bắn) phải lên trên.
  const boardsBox = h('div', { class: 'ship-boards' }, ownBox, foeBox);
  const layoutEl = h('div', { class: 'ship-layout' },
    h('div', { class: 'ship-main' },
      statusBar,
      placingBar,
      boardsBox,
      mobileFleet,
      actions),
    side);

  mount(root, layoutEl);

  /* ----------------------------------------------------- dựng lưới 10x10 -- */
  function grid({ size, cellClass, onCell, onHover, mode, outCells }) {
    const box = h('div', {
      class: 'ship-grid' + (mode ? ' ' + mode : ''),
      style: { '--n': size },
      onmouseleave: onHover ? () => onHover(-1) : null,
    });
    box.style.setProperty('--n', size);

    box.appendChild(h('div', { class: 'ship-axis' }, ''));
    for (let c = 0; c < size; c++) box.appendChild(h('div', { class: 'ship-axis' }, LETTERS[c]));

    for (let r = 0; r < size; r++) {
      box.appendChild(h('div', { class: 'ship-axis' }, String(r + 1)));
      for (let c = 0; c < size; c++) {
        const index = r * size + c;
        const btn = h('button', {
          type: 'button',
          class: 'ship-cell ' + cellClass(index),
          'aria-label': `${LETTERS[c]}${r + 1}`,
          onclick: onCell ? () => onCell(index) : null,
          onmouseenter: onHover ? () => onHover(index) : null,
          onfocus: onHover ? () => onHover(index) : null,
        }, cellText(index));
        if (outCells) outCells[index] = btn;
        box.appendChild(btn);
      }
    }
    return box;

    function cellText(index) {
      const cls = cellClass(index);
      if (cls.includes('miss')) return '•';
      if (cls.includes('pending')) return '◎';
      return '';
    }
  }

  /** Các ô con tàu đang chọn sẽ chiếm nếu đặt tại ô hover.
   *  Luôn trả về cùng một hình dạng {cells, bad} để bên gọi không phải đoán. */
  const NO_PREVIEW = { cells: [], bad: false };

  function previewCells() {
    if (selected === null || hover < 0 || !state) return NO_PREVIEW;
    const spec = state.shipTypes.find((s) => s.key === selected);
    if (!spec) return NO_PREVIEW;
    const size = state.boardSize;
    const row = Math.floor(hover / size);
    const col = hover % size;
    const cells = [];
    for (let step = 0; step < spec.size; step++) {
      const r = horizontal ? row : row + step;
      const c = horizontal ? col + step : col;
      if (r >= size || c >= size) return { cells, bad: true };
      cells.push(r * size + c);
    }
    return { cells, bad: false };
  }

  /** Số ô kề tàu đã xếp, để báo đỏ ngay mà không cần chờ server từ chối. */
  function blockedCells(own, size) {
    const blocked = new Set();
    for (const ship of own.ships || []) {
      for (const cell of ship.cells) {
        const r = Math.floor(cell / size), c = cell % size;
        for (let dr = -1; dr <= 1; dr++) {
          for (let dc = -1; dc <= 1; dc++) {
            const nr = r + dr, nc = c + dc;
            if (nr >= 0 && nr < size && nc >= 0 && nc < size) blocked.add(nr * size + nc);
          }
        }
      }
    }
    return blocked;
  }

  /* ------------------------------------------------------- bàn của mình -- */
  function renderOwnBoard() {
    const s = state;
    const size = s.boardSize;
    const own = s.own;
    const placing = s.status === 'placing' && Boolean(s.you.mark);

    const shipCell = new Map();
    for (const ship of own.ships || []) {
      for (const cell of ship.cells) shipCell.set(cell, ship);
    }
    const preview = placing ? previewCells() : NO_PREVIEW;
    const previewSet = new Set(preview.cells);
    const blocked = placing ? blockedCells(own, size) : new Set();
    const badPreview = preview.bad || preview.cells.some((cell) => blocked.has(cell));

    const cellClass = (index) => {
      const classes = [];
      if (previewSet.has(index)) classes.push(badPreview ? 'preview-bad' : 'preview-ok');
      const shot = own.shots ? own.shots[String(index)] : null;
      const ship = shipCell.get(index);
      if (shot === 'hit') classes.push('hit');
      else if (shot === 'miss') classes.push('miss');
      else if (ship) classes.push('ship', ship.sunk ? 'sunk' : '');
      if (index === s.lastShot && s.turn === s.you.mark && s.status === 'playing') {
        classes.push('lastshot');
      }
      return classes.filter(Boolean).join(' ');
    };

    const onCell = placing ? (index) => {
      const ship = shipCell.get(index);
      if (ship) { sfx.move(); net.send(CHANNEL, 'remove', { ship: keyOf(ship) }); return; }
      if (selected === null) { toast(t('ship.selectShipFirst')); return; }
      const row = Math.floor(index / size), col = index % size;
      sfx.move();
      net.send(CHANNEL, 'place', { ship: selected, row, col, horizontal });
    } : null;

    // Cập nhật class preview trực tiếp trên 100 ô thay vì dựng lại cả bảng 121 node mỗi lần rê chuột
    const updateHoverInPlace = () => {
      if (!ownCellNodes.length) return;
      const pv = placing ? previewCells() : NO_PREVIEW;
      const pvSet = new Set(pv.cells);
      const badPv = pv.bad || pv.cells.some((c) => blocked.has(c));
      for (let i = 0; i < ownCellNodes.length; i++) {
        const el = ownCellNodes[i];
        if (!el) continue;
        el.classList.toggle('preview-ok', pvSet.has(i) && !badPv);
        el.classList.toggle('preview-bad', pvSet.has(i) && badPv);
      }
    };

    const onHover = placing ? (index) => {
      if (hover === index) return;
      hover = index;
      updateHoverInPlace();
    } : null;

    const hitsTaken = (own.ships || []).reduce((sum, sh) => sum + (sh.hits || []).length, 0);
    const total = s.totalShipCells;
    ownCellNodes = new Array(size * size);

    mount(ownBox,
      h('div', { class: 'ship-board-title' },
        h('span', {}, s.you.mark ? t('ship.yourFleet') : t('ship.player1Board')),
        h('span', { class: 'grow' }),
        h('span', { class: 'tiny muted' }, t('ship.hitsTaken', { hits: hitsTaken, total }))),
      grid({ size, cellClass, onCell, onHover, mode: placing ? 'placing' : '', outCells: ownCellNodes }),
      h('div', { class: 'progress' },
        h('span', { style: { width: `${Math.round(hitsTaken / total * 100)}%` } })));
  }

  function keyOf(ship) {
    return ship.key || (state.shipTypes.find((t) => t.name === ship.name) || {}).key || '';
  }

  /* ------------------------------------------------------ bàn đối thủ ----- */
  function renderFoeBoard() {
    const s = state;
    const size = s.boardSize;
    const foe = s.enemy;
    const myTurn = s.status === 'playing' && s.turn === s.you.mark && Boolean(s.you.mark);

    const sunkCell = new Set();
    for (const ship of foe.sunkShips || []) for (const cell of ship.cells) sunkCell.add(cell);
    const revealed = new Set();
    for (const ship of foe.ships || []) for (const cell of ship.cells) revealed.add(cell);

    const cellClass = (index) => {
      const classes = [];
      const shot = foe.shots ? foe.shots[String(index)] : null;
      if (shot === 'hit') classes.push('hit');
      else if (shot === 'miss') classes.push('miss');
      else if (index === pendingShotIdx) classes.push('pending', 'lastshot');
      else if (revealed.has(index)) classes.push('reveal');   // chỉ khi ván đã xong
      else if (myTurn && pendingShotIdx < 0) classes.push('open');
      if (sunkCell.has(index)) classes.push('sunk');
      if (index === s.lastShot && s.lastResult && s.turn !== s.you.mark) classes.push('lastshot');
      return classes.filter(Boolean).join(' ');
    };

    const onCell = myTurn ? (index) => {
      if (pendingShotIdx >= 0) return;
      if (foe.shots && foe.shots[String(index)]) return;
      pendingShotIdx = index;
      sfx.move();
      renderFoeBoard();
      net.send(CHANNEL, 'fire', { index });
    } : null;

    const sunk = foe.sunkCount || 0;
    const shipCount = foe.shipCount || s.shipTypes.length;

    mount(foeBox,
      h('div', { class: 'ship-board-title' },
        h('span', {}, s.you.mark ? t('ship.enemyBoard') : t('ship.player2Board')),
        h('span', { class: 'grow' }),
        h('span', { class: 'tiny muted' }, t('ship.sunkCount', { sunk, total: shipCount }))),
      grid({ size, cellClass, onCell, mode: myTurn ? 'firing' : '' }),
      h('div', { class: 'progress' },
        h('span', { style: { width: `${Math.round(sunk / shipCount * 100)}%` } })));
  }

  /* -------------------------------------------------- danh sách hạm đội -- */
  function fleetPanel(extraClass = '') {
    const s = state;
    const own = s.own;
    const placing = s.status === 'placing' && Boolean(s.you.mark);
    const placedKeys = new Set((own.ships || []).map((sh) => keyOf(sh)));

    const list = h('div', { class: 'fleet-list' });
    for (const type of s.shipTypes) {
      const ship = (own.ships || []).find((sh) => keyOf(sh) === type.key);
      const hits = ship ? (ship.hits || []).length : 0;
      const pips = h('div', { class: 'fleet-pips' },
        Array.from({ length: type.size }, (_, i) =>
          h('span', { class: 'fleet-pip' + (i < hits ? ' hit' : '') })));

      list.appendChild(h('button', {
        class: 'fleet-item'
          + (selected === type.key && placing ? ' selected' : '')
          + (placedKeys.has(type.key) ? ' placed' : '')
          + (ship && ship.sunk ? ' sunk' : ''),
        disabled: !placing && !ship,
        onclick: () => {
          if (!placing) return;
          if (placedKeys.has(type.key)) {
            net.send(CHANNEL, 'remove', { ship: type.key });
            selected = type.key;
          } else {
            selected = selected === type.key ? null : type.key;
          }
          render();
        },
      }, h('span', { class: 'grow nowrap' }, shipNameI18n(type.name)),
         h('span', { class: 'tiny muted' }, t('ship.cellsSize', { n: type.size })), pips));
    }

    return h('div', { class: 'card tight col' + (extraClass ? ' ' + extraClass : '') },
      h('div', { class: 'card-title', style: { marginBottom: '2px' } }, t('ship.fleetTitle')),
      list,
      placing ? h('div', { class: 'tiny muted' }, t('ship.placeGuide')) : null);
  }

  /* ------------------------------------------------------- pha xếp tàu --- */
  function renderPlacingBar() {
    const s = state;
    if (s.status !== 'placing' || !s.you.mark) { clear(placingBar); return; }
    const own = s.own;
    const remaining = (own.remaining || []).length;

    mount(placingBar,
      h('span', { class: 'chip' + (horizontal ? '' : ' accent') },
        horizontal ? t('ship.horiz') : t('ship.vert')),
      h('button', { class: 'sm', onclick: () => { horizontal = !horizontal; render(); } },
        t('ship.rotateBtn')),
      h('button', { class: 'sm', onclick: () => net.send(CHANNEL, 'auto') },
        icon('dice', 14), ' ' + t('ship.autoPlace')),
      h('button', { class: 'sm ghost', onclick: () => net.send(CHANNEL, 'clear') }, t('ship.clearAll')),
      own.ready
        ? h('button', { class: 'sm', onclick: () => net.send(CHANNEL, 'unready') },
            t('ship.unready'))
        : h('button', {
            class: 'sm primary', disabled: remaining > 0,
            onclick: () => net.send(CHANNEL, 'ready'),
          }, remaining ? t('ship.remaining', { n: remaining }) : t('ship.ready')));
  }

  /* ------------------------------------------------------------- render -- */
  function statusText(s) {
    const mine = s.you.mark;
    const foeMark = mine === 'X' ? 'O' : 'X';
    if (s.status === 'waiting') {
      return {
        text: mine ? t('ship.waitFoeJoin') : t('caro.waitTwo'),
        cls: 'wait',
      };
    }
    if (s.status === 'placing') {
      if (!mine) return { text: t('ship.placingSpec'), cls: 'wait' };
      if (!s.own.ready) return { text: t('ship.placingYou'), cls: 'turn' };
      return { text: t('ship.placingWait'), cls: 'wait' };
    }
    if (s.status === 'playing') {
      const seat = s.seats[s.turn];
      if (!mine) return { text: t('ship.firingSpec', { name: seat ? seat.name : s.turn }), cls: '' };
      if (s.turn === mine) {
        const extra = s.lastResult === 'hit' ? t('ship.hitBonus') : '';
        return { text: t('ship.yourTurn') + extra, cls: 'turn' };
      }
      const foe = s.seats[foeMark];
      if (foe && !foe.connected) {
        return { text: t('caro.foeOffline', { name: foe.name }), cls: 'wait' };
      }
      return { text: t('ship.waitFoeFire', { name: foe ? foe.name : t('ship.enemyFallback') }), cls: 'wait' };
    }
    const champ = s.seats[s.winner];
    if (mine && s.winner === mine) return { text: t('ship.youWin'), cls: 'won' };
    if (mine) return { text: t('ship.youLose', { name: champ ? champ.name : '' }), cls: 'lost' };
    return { text: t('ship.otherWin', { name: champ ? champ.name : s.winner }), cls: '' };
  }

  function logPanel() {
    const log = h('div', { class: 'ship-log' });
    for (const entry of [...state.log].reverse()) {
      log.appendChild(h('div', { class: 'dim' }, entry.text));
    }
    if (!state.log.length) log.appendChild(h('div', { class: 'tiny muted' }, t('ship.noShotsYet')));
    return h('div', { class: 'card tight col' },
      h('div', { class: 'card-title', style: { marginBottom: '2px' } }, t('ship.logTitle')), log);
  }

  function render() {
    const s = state;
    if (!s) return;

    // Tự động chọn tàu đầu tiên chưa xếp để người chơi chạm bàn đặt ngay.
    if (s.status === 'placing' && s.you.mark && !s.own.ready && selected === null) {
      const placedKeys = new Set((s.own.ships || []).map((sh) => keyOf(sh)));
      const nextShip = (s.shipTypes || []).find((tp) => !placedKeys.has(tp.key));
      if (nextShip) selected = nextShip.key;
    }

    const info = statusText(s);
    statusBar.textContent = info.text;
    statusBar.className = 'status-bar ' + info.cls;

    renderPlacingBar();
    renderOwnBoard();
    renderFoeBoard();
    layoutEl.classList.toggle('ship-placing', s.status === 'placing');
    boardsBox.classList.toggle('firing', s.status !== 'placing');
    mount(actions, actionRow(s, net, CHANNEL));

    const readyChips = h('div', { class: 'row', style: { gap: '6px' } },
      ['X', 'O'].map((mark) => h('span', {
        class: 'chip' + (s.readyState[mark] ? ' ok' : ''),
      }, `${seatLabelI18n(s.seatLabels[mark])}: ${s.readyState[mark] ? t('ship.readyBadge') : t('ship.placingBadge')}`)));

    mount(mobileFleet, s.status === 'placing' ? fleetPanel() : null);
    mount(side,
      seatPanel(s, { markClass: false }),
      fleetPanel('desktop-fleet'),
      roomCard(s, CHANNEL, s.status === 'placing' ? readyChips : null),
      logPanel(),
      roomChat(s, net, CHANNEL));
    ctx.setTopbar(...roomTopbar(ctx, s, CHANNEL, t('ship.title')));

    // âm thanh
    const myShots = Object.keys(s.enemy.shots || {}).length;
    const hitsOnMe = s.own.shots
      ? Object.values(s.own.shots).filter((v) => v === 'hit').length
      : 0;
    if (prevShots >= 0 && s.status === 'playing') {
      if (myShots > prevShots) {
        s.lastResult === 'hit' ? sfx.hit() : sfx.miss();
      } else if (hitsOnMe > prevEnemyHits) {
        sfx.hit();
      }
    }
    if (s.status === 'finished' && prevStatus !== 'finished' && s.you.mark) {
      s.winner === s.you.mark ? sfx.win() : sfx.lose();
    }
    prevShots = myShots;
    prevEnemyHits = hitsOnMe;
    prevStatus = s.status;
  }

  /* --------------------------------------------------------- bàn phím ---- */
  const onKey = (event) => {
    if (event.key !== 'r' && event.key !== 'R') return;
    if (/^(INPUT|TEXTAREA)$/.test(document.activeElement?.tagName || '')) return;
    if (!state || state.status !== 'placing') return;
    horizontal = !horizontal;
    render();
  };
  window.addEventListener('keydown', onKey);

  /* --------------------------------------------------------------- mạng -- */
  const stop = net.on(CHANNEL, (msg) => {
    if (msg.t === 'state') {
      pendingShotIdx = -1;
      // Tàu vừa xếp xong thì bỏ chọn để không xếp trùng.
      if (state && msg.own && (msg.own.ships || []).length > (state.own?.ships || []).length) {
        selected = null;
      }
      state = msg;
      render();
    } else if (msg.t === 'error') {
      pendingShotIdx = -1;
      toast(msg.message, 'danger');
      if (state) renderFoeBoard();
    } else if (msg.t === 'closed') {
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
    window.removeEventListener('keydown', onKey);
    net.send(CHANNEL, 'leave');
  };
}

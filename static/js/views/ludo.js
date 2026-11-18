/* Cờ Cá Ngựa (4 người) — đủ luật xuất quân, cản đường, đá tiến, Đá Hậu, leo chuồng 1–6.
 * Cơ chế phòng: đủ 4 người tự động bắt đầu; chưa đủ thì Chủ phòng có thể bấm Bắt đầu bất cứ lúc nào.
 */

import { avatar, clear, h, icon, mount } from '../dom.js';
import { modeLabel, t } from '../i18n.js';
import { confirmBox, sfx, toast } from '../ui.js';
import { renderLobby, roomCard, roomChat, roomTopbar } from './gameroom.js';

const CHANNEL = 'ludo';
const COLORS = ['R', 'B', 'Y', 'G'];

// Tạo bảng ánh xạ 56 ô vòng ngoài trên lưới 15x15 (row 0..14, col 0..14)
const TRACK_COORDS = (() => {
  const coords = [];
  for (let c = 0; c <= 6; c++) coords.push([6, c]);       // 0..6
  for (let r = 5; r >= 0; r--) coords.push([r, 6]);       // 7..12
  coords.push([0, 7]);                                    // 13 (cửa chuồng B)
  for (let r = 0; r <= 6; r++) coords.push([r, 8]);       // 14..20
  for (let c = 9; c <= 14; c++) coords.push([6, c]);      // 21..26
  coords.push([7, 14]);                                   // 27 (cửa chuồng Y)
  for (let c = 14; c >= 8; c--) coords.push([8, c]);      // 28..34
  for (let r = 9; r <= 14; r++) coords.push([r, 8]);      // 35..40
  coords.push([14, 7]);                                   // 41 (cửa chuồng G)
  for (let r = 14; r >= 8; r--) coords.push([r, 6]);      // 42..48
  for (let c = 5; c >= 0; c--) coords.push([8, c]);       // 49..54
  coords.push([7, 0]);                                    // 55 (cửa chuồng R)
  return coords;
})();

const TRACK_KEY_TO_IDX = new Map(TRACK_COORDS.map(([r, c], idx) => [`${r},${c}`, idx]));

const START_GLOBAL = { R: 0, B: 14, Y: 28, G: 42 };
const DOOR_GLOBAL = { R: 55, B: 13, Y: 27, G: 41 };

// Chuồng đích 1..6 cho từng màu
const HOME_COORDS = {
  R: [[7, 1], [7, 2], [7, 3], [7, 4], [7, 5], [7, 6]],
  B: [[1, 7], [2, 7], [3, 7], [4, 7], [5, 7], [6, 7]],
  Y: [[7, 13], [7, 12], [7, 11], [7, 10], [7, 9], [7, 8]],
  G: [[13, 7], [12, 7], [11, 7], [10, 7], [9, 7], [8, 7]],
};
const HOME_KEY_MAP = new Map();
for (const c of COLORS) {
  HOME_COORDS[c].forEach(([r, col], i) => {
    HOME_KEY_MAP.set(`${r},${col}`, { color: c, rank: i + 1 });
  });
}

// Vị trí 4 chuồng xuất phát ở 4 góc
const YARD_META = {
  R: { r0: 0, c0: 0 },
  B: { r0: 0, c0: 9 },
  Y: { r0: 9, c0: 9 },
  G: { r0: 9, c0: 0 },
};

function horseSvg(color) {
  const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  svg.setAttribute('viewBox', '0 0 24 24');
  svg.setAttribute('class', 'ludo-horse-svg');
  svg.setAttribute('aria-hidden', 'true');
  svg.innerHTML =
    `<path d="M18 20H6v-2c0-1.2 1.2-2.2 2.5-2.8l1.2-3.2c-1.1.3-2.5.3-3.5-.4-.7-.5-.9-1.4-.4-2.2L8.5 5.5 7.8 3.2c1.4.2 2.6.8 3.5 1.8.8-.3 1.7-.4 2.6-.3 2.5.3 4.3 2.5 4.1 5.2-.1 1.8-.8 3.6-1.5 5.2l1.2 2.5c.3.7.3 1.4.3 2.4Z" fill="currentColor" stroke="rgba(0,0,0,0.45)" stroke-width="1.2" stroke-linejoin="round"/>`
    + `<circle cx="10.2" cy="8.2" r="0.9" fill="#0f172a"/>`;
  return svg;
}

function diceSvg(value) {
  const pips = {
    1: [[12, 12]],
    2: [[7, 7], [17, 17]],
    3: [[7, 7], [12, 12], [17, 17]],
    4: [[7, 7], [17, 7], [7, 17], [17, 17]],
    5: [[7, 7], [17, 7], [12, 12], [7, 17], [17, 17]],
    6: [[7, 6.5], [17, 6.5], [7, 12], [17, 12], [7, 17.5], [17, 17.5]],
  }[value] || [[12, 12]];

  const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  svg.setAttribute('viewBox', '0 0 24 24');
  svg.setAttribute('class', 'ludo-dice-svg');
  svg.setAttribute('aria-hidden', 'true');
  const dots = pips.map(([cx, cy]) => `<circle cx="${cx}" cy="${cy}" r="2.1" fill="currentColor"/>`).join('');
  svg.innerHTML = `<rect x="1.5" y="1.5" width="21" height="21" rx="5" fill="none" stroke="currentColor" stroke-width="1.8"/>${dots}`;
  return svg;
}

export default {
  async mount(root, ctx, param) {
    if (!param) {
      return renderLobby(root, ctx, CHANNEL, {
        title: t('ludo.title'),
        blurb: t('ludo.blurb'),
        iconName: 'horse',
        onEnter: (code) => ctx.navigate(`${CHANNEL}/${code}`),
      });
    }
    return mountRoom(root, ctx, param.toUpperCase());
  },
};

function mountRoom(root, ctx, code) {
  const { net } = ctx;
  let state = null;
  let selectedPiece = null;
  let prevRollSeq = 0;
  let prevEventSeq = 0;
  let prevStatus = '';
  let serverSkewMs = 0;
  let lastClockSec = -1;
  let optimisticRollPlayed = false;
  let botLevelPick = localStorage.getItem(`hub.level.${CHANNEL}`) || 'normal';

  const send = (action, extra = {}) => net.send(CHANNEL, action, extra);

  const banner = h('div', { class: 'status-bar', role: 'status', 'aria-live': 'polite' }, t('shell.connecting'));
  const boardBox = h('div', { class: 'ludo-board' });
  const diceStage = h('div', { class: 'ludo-controls card tight' });
  const hostPanel = h('div', {});
  const seatsCard = h('div', { class: 'card tight col' });
  const feedCard = h('div', { class: 'card tight col' });
  const roomCardSlot = h('div', {});
  const chatSlot = h('div', {});
  const clockBadge = h('span', { class: 'ludo-clock hidden' });

  const mainCol = h('div', { class: 'ludo-main col' }, banner, boardBox, diceStage);
  const sideCol = h('div', { class: 'ludo-side col' },
    hostPanel, seatsCard, feedCard, roomCardSlot, chatSlot);

  root.className = 'view';
  mount(root, h('div', { class: 'ludo-layout' }, mainCol, sideCol));

  function colorName(c) {
    return t(`ludo.color.${c}`);
  }

  function nameOf(s, c) {
    return s.seats?.[c]?.name || colorName(c);
  }

  function moveLabel(s, mv) {
    const num = `#${mv.piece + 1}`;
    if (mv.kind === 'kick_back') {
      return `⚔️ ${num} ${t('ludo.actBackKick', { target: nameOf(s, mv.kickedColor) })}`;
    }
    if (mv.kind === 'kick' || mv.kind === 'deploy_kick') {
      return `💥 ${num} ${t('ludo.actKick', { target: nameOf(s, mv.kickedColor) })}`;
    }
    if (mv.kind === 'deploy') return `🐎 ${num} ${t('ludo.actDeploy')}`;
    if (mv.kind === 'enter_home' || mv.kind === 'climb_home') {
      return `🏁 ${num} ${t('ludo.actHome', { rank: mv.toPos - 55 })}`;
    }
    return `${num} ${t('ludo.actMove', { steps: s.dice })}`;
  }

  function execMove(mv) {
    selectedPiece = null;
    sfx.move();
    if (state && state.you?.mark && state.pieces?.[state.you.mark]) {
      const myColor = state.you.mark;
      const myPieces = state.pieces[myColor];
      const p = myPieces.find((x) => x.id === mv.piece);
      if (p) {
        p.pos = mv.toPos;
        if (mv.toPos === -1) { p.zone = 'stable'; p.global = null; p.rank = 0; }
        else if (mv.toPos <= 55) { p.zone = 'track'; p.global = mv.toGlobal; p.rank = 0; }
        else { p.zone = 'home'; p.global = null; p.rank = mv.toPos - 55; }
      }
      state.legalMoves = [];
      renderBoard();
      renderControls();
    }
    send('move', { piece: mv.piece, kind: mv.kind });
  }

  function execRoll(btnEl) {
    if (!state || state.status !== 'playing' || state.phase !== 'roll' || state.turn !== state.you?.mark) return;
    if (btnEl) btnEl.disabled = true;
    optimisticRollPlayed = true;
    sfx.move();
    send('roll');
  }

  /* ---------------------------------------------------------- vẽ bàn cờ --- */
  function renderBoard() {
    const s = state;
    if (!s) return;
    clear(boardBox);

    const myColor = s.you?.mark || '';
    const isMyMove = s.status === 'playing' && s.phase === 'move' && s.turn === myColor;
    const moves = isMyMove ? (s.legalMoves || []) : [];

    const playablePieces = new Set(moves.map((m) => m.piece));
    // Nếu chỉ chọn 1 quân, hoặc lọc theo quân đang chọn
    const shownMoves = selectedPiece !== null
      ? moves.filter((m) => m.piece === selectedPiece)
      : moves;

    const targetGlobalMap = new Map();
    const targetHomeMap = new Map();
    for (const mv of shownMoves) {
      if (mv.toGlobal !== null && mv.toGlobal !== undefined) {
        targetGlobalMap.set(mv.toGlobal, mv);
      } else if (mv.toPos > 55) {
        targetHomeMap.set(`${myColor}:${mv.toPos - 55}`, mv);
      }
    }

    // Gom quân đang đứng trên track & home
    const trackPieceAt = new Map();
    const homePieceAt = new Map();
    for (const c of COLORS) {
      for (const p of (s.pieces?.[c] || [])) {
        if (p.zone === 'track' && p.global !== null) {
          trackPieceAt.set(p.global, { color: c, piece: p });
        } else if (p.zone === 'home' && p.rank >= 1) {
          homePieceAt.set(`${c}:${p.rank}`, { color: c, piece: p });
        }
      }
    }

    const makeHorseBtn = (color, pieceObj, clickableMoves) => {
      const canPlay = isMyMove && color === myColor && clickableMoves.length > 0;
      const isSelected = selectedPiece === pieceObj.id;
      const hasBackKick = clickableMoves.some((m) => m.kind === 'kick_back');
      const btn = h('button', {
        type: 'button',
        class: `ludo-piece c-${color}`
          + (canPlay ? ' playable' : '')
          + (isSelected ? ' selected' : '')
          + (hasBackKick ? ' can-backkick' : ''),
        disabled: !canPlay,
        title: `${colorName(color)} #${pieceObj.id + 1}`,
        onclick: (ev) => {
          ev.stopPropagation();
          if (!canPlay) return;
          if (clickableMoves.length === 1) {
            execMove(clickableMoves[0]);
          } else {
            selectedPiece = isSelected ? null : pieceObj.id;
            renderBoard();
            renderControls();
          }
        },
      },
        horseSvg(color),
        h('span', { class: 'ludo-piece-num' }, String(pieceObj.id + 1)));
      return btn;
    };

    // 1. Vẽ 4 chuồng góc (6x6 mỗi góc)
    for (const c of COLORS) {
      const { r0, c0 } = YARD_META[c];
      const seat = s.seats?.[c];
      const isTurn = s.status === 'playing' && s.turn === c;
      const isHostSeat = s.hostMark === c;
      const isMe = myColor === c;
      const eliminated = (s.eliminated || []).includes(c);
      const stablePieces = (s.pieces?.[c] || []).filter((p) => p.zone === 'stable');

      const yard = h('div', {
        class: `ludo-yard c-${c}`
          + (isTurn ? ' active-turn' : '')
          + (isMe ? ' me' : '')
          + (eliminated ? ' eliminated' : ''),
        style: {
          gridRow: `${r0 + 1} / span 6`,
          gridColumn: `${c0 + 1} / span 6`,
        },
      });

      const header = h('div', { class: 'ludo-yard-head' },
        seat
          ? h('div', { class: 'row', style: { gap: '5px', minWidth: '0' } },
              avatar(seat, 'sm'),
              h('span', { class: 'nowrap ludo-yard-name' },
                (isHostSeat ? '👑 ' : '') + seat.name))
          : h('span', { class: 'tiny muted' }, t('ludo.seatOpen', { color: colorName(c) })));

      const slots = h('div', { class: 'ludo-stable-slots' });
      for (let i = 0; i < 4; i++) {
        const pieceObj = stablePieces[i];
        const slot = h('div', { class: `ludo-stable-slot c-${c}` });
        if (pieceObj) {
          const pMoves = moves.filter((m) => m.piece === pieceObj.id);
          slot.appendChild(makeHorseBtn(c, pieceObj, pMoves));
        }
        slots.appendChild(slot);
      }

      yard.append(header, slots);
      boardBox.appendChild(yard);
    }

    // 2. Vẽ các ô đường chạy + ô chuồng đích + trung tâm
    for (let r = 0; r < 15; r++) {
      for (let col = 0; col < 15; col++) {
        // Bỏ qua 4 vùng chuồng góc 6x6
        if ((r < 6 && col < 6) || (r < 6 && col > 8) || (r > 8 && col < 6) || (r > 8 && col > 8)) {
          continue;
        }
        const key = `${r},${col}`;

        // Ô trung tâm (7,7)
        if (r === 7 && col === 7) {
          const turnColor = s.status === 'playing' ? s.turn : '';
          const center = h('div', {
            class: `ludo-center` + (turnColor ? ` c-${turnColor}` : ''),
            style: { gridRow: '8', gridColumn: '8' },
          },
            s.status === 'playing' && s.dice
              ? h('div', { class: 'ludo-center-dice' }, diceSvg(s.dice))
              : h('span', { class: 'ludo-center-star' }, '★'));
          boardBox.appendChild(center);
          continue;
        }

        // Ô chuồng đích 1..6
        const homeInfo = HOME_KEY_MAP.get(key);
        if (homeInfo) {
          const { color, rank } = homeInfo;
          const cell = h('div', {
            class: `ludo-cell ludo-home-cell c-${color}`,
            style: { gridRow: String(r + 1), gridColumn: String(col + 1) },
          }, h('span', { class: 'ludo-rank-num' }, String(rank)));

          const occ = homePieceAt.get(`${color}:${rank}`);
          if (occ) {
            const pMoves = moves.filter((m) => m.piece === occ.piece.id);
            cell.appendChild(makeHorseBtn(occ.color, occ.piece, pMoves));
          }
          const targetMv = targetHomeMap.get(`${color}:${rank}`);
          if (targetMv) {
            cell.classList.add('target-move');
            cell.onclick = () => execMove(targetMv);
          }
          boardBox.appendChild(cell);
          continue;
        }

        // Ô vòng ngoài 0..55
        const gIdx = TRACK_KEY_TO_IDX.get(key);
        if (gIdx !== undefined) {
          let startColor = '';
          let doorColor = '';
          for (const c of COLORS) {
            if (START_GLOBAL[c] === gIdx) startColor = c;
            if (DOOR_GLOBAL[c] === gIdx) doorColor = c;
          }
          const targetMv = targetGlobalMap.get(gIdx);
          const isBackKickTarget = targetMv && targetMv.kind === 'kick_back';
          const isKickTarget = targetMv && (targetMv.kind === 'kick' || targetMv.kind === 'deploy_kick');

          const cell = h('div', {
            class: 'ludo-cell ludo-track-cell'
              + (startColor ? ` start-${startColor}` : '')
              + (doorColor ? ` door-${doorColor}` : '')
              + (targetMv ? ' target-move' : '')
              + (isBackKickTarget ? ' target-backkick' : isKickTarget ? ' target-kick' : ''),
            style: { gridRow: String(r + 1), gridColumn: String(col + 1) },
          });

          if (startColor) {
            cell.appendChild(h('span', { class: 'ludo-cell-tag' }, '★'));
          } else if (doorColor) {
            cell.appendChild(h('span', { class: 'ludo-cell-tag door' }, '▲'));
          }

          const occ = trackPieceAt.get(gIdx);
          if (occ) {
            const pMoves = moves.filter((m) => m.piece === occ.piece.id);
            cell.appendChild(makeHorseBtn(occ.color, occ.piece, pMoves));
          }

          if (targetMv) {
            cell.title = moveLabel(s, targetMv);
            cell.onclick = () => execMove(targetMv);
            if (isBackKickTarget) {
              cell.appendChild(h('span', { class: 'ludo-target-badge backkick' }, '⚔️'));
            } else if (isKickTarget) {
              cell.appendChild(h('span', { class: 'ludo-target-badge kick' }, '💥'));
            }
          }
          boardBox.appendChild(cell);
        }
      }
    }
  }

  /* --------------------------------------------------- bảng điều khiển --- */
  function renderControls() {
    const s = state;
    if (!s) return;
    clear(diceStage);

    const myColor = s.you?.mark || '';
    const isMyTurn = s.status === 'playing' && s.turn === myColor;

    if (s.status === 'waiting') {
      const seatedCount = COLORS.filter((c) => s.seats?.[c]).length;
      const cfg = s.config || {};
      const canCfg = s.isHost;

      diceStage.append(
        h('div', { class: 'spread' },
          h('strong', {}, t('ludo.waitingHead', { n: seatedCount })),
          h('span', { class: 'chip accent' }, modeLabel(CHANNEL, s.mode, s.label))),
        h('p', { class: 'small dim' }, t('ludo.autoStartHint')),
        h('div', { class: 'ludo-cfg-grid' },
          h('div', { class: 'row', style: { gap: '6px', flexWrap: 'wrap' } },
            h('span', { class: 'tiny muted' }, t('ludo.cfgDeploy') + ':'),
            h('button', {
              type: 'button',
              class: 'xs ' + (cfg.deployRule === '1and6' ? 'primary' : 'ghost'),
              disabled: !canCfg,
              onclick: () => send('config', { deployRule: '1and6' }),
            }, t('ludo.deploy16')),
            h('button', {
              type: 'button',
              class: 'xs ' + (cfg.deployRule === '6only' ? 'primary' : 'ghost'),
              disabled: !canCfg,
              onclick: () => send('config', { deployRule: '6only' }),
            }, t('ludo.deploy6'))),
          h('div', { class: 'row', style: { gap: '6px', flexWrap: 'wrap' } },
            h('span', { class: 'tiny muted' }, t('ludo.cfgBackKick') + ':'),
            h('button', {
              type: 'button',
              class: 'xs ' + (cfg.backKick ? 'primary' : 'ghost'),
              disabled: !canCfg,
              onclick: () => send('config', { backKick: true }),
            }, t('ludo.on')),
            h('button', {
              type: 'button',
              class: 'xs ' + (!cfg.backKick ? 'primary' : 'ghost'),
              disabled: !canCfg,
              onclick: () => send('config', { backKick: false }),
            }, t('ludo.off')))),
        s.isHost
          ? h('button', {
              type: 'button',
              class: 'primary ludo-start-btn',
              onclick: () => send('start'),
            }, seatedCount < 2 ? t('ludo.startWithBotBtn') : t('ludo.startNowBtn', { n: seatedCount }))
          : h('div', { class: 'tiny muted' },
              t('ludo.waitHostStart', { host: s.seats?.[s.hostMark]?.name || '' })));
      return;
    }

    if (s.status === 'finished') {
      const winner = s.winner;
      const myVoted = (s.rematch || []).includes(myColor);
      const isWin = myColor && winner === myColor;
      diceStage.append(
        h('div', { class: 'banner ' + (isWin ? 'ok' : 'accent') },
          winner === 'draw' ? t('ludo.draw') : t('ludo.winBanner', { name: nameOf(s, winner), color: colorName(winner) })),
        h('div', { class: 'row-wrap' },
          myColor
            ? h('button', {
                type: 'button',
                class: 'primary grow',
                disabled: myVoted,
                onclick: () => send('rematch'),
              }, myVoted ? t('room.rematchWait') : t('room.rematch'))
            : null,
          s.isHost
            ? h('button', {
                type: 'button',
                class: 'ghost',
                onclick: () => send('start'),
              }, t('ludo.hostRestart'))
            : null));
      return;
    }

    // Đang chơi
    const turnName = nameOf(s, s.turn);
    const rollInfo = s.dice
      ? h('div', { class: 'ludo-dice-box' }, diceSvg(s.dice), h('span', { class: 'ludo-dice-val' }, String(s.dice)))
      : h('div', { class: 'ludo-dice-box empty' }, '?');

    const rollBtn = h('button', {
      type: 'button',
      class: 'primary ludo-roll-btn' + (isMyTurn && s.phase === 'roll' ? ' pulse' : ''),
      disabled: !(isMyTurn && s.phase === 'roll'),
      onclick: (ev) => execRoll(ev.currentTarget),
    }, icon('dice', 18), ' ', isMyTurn && s.phase === 'roll'
      ? t('ludo.rollBtn')
      : t('ludo.turnOf', { name: turnName }));

    diceStage.append(
      h('div', { class: 'spread' },
        h('div', { class: 'row', style: { gap: '10px' } },
          rollInfo,
          h('div', { class: 'col', style: { gap: '2px' } },
            h('strong', { class: `ludo-turn-name c-${s.turn}` },
              isMyTurn ? t('ludo.yourTurn') : t('ludo.playerTurn', { name: turnName, color: colorName(s.turn) })),
            h('span', { class: 'tiny muted' },
              s.phase === 'roll' ? t('ludo.hintRoll') : t('ludo.hintMove')))),
        clockBadge),
      rollBtn);

    if (isMyTurn && s.phase === 'move' && (s.legalMoves || []).length) {
      const moveRow = h('div', { class: 'ludo-moves-bar' },
        (s.legalMoves || []).map((mv) => {
          const isBack = mv.kind === 'kick_back';
          const isKick = mv.kind === 'kick' || mv.kind === 'deploy_kick';
          return h('button', {
            type: 'button',
            class: 'sm ludo-move-pill'
              + (isBack ? ' backkick' : isKick ? ' kick' : '')
              + (selectedPiece === mv.piece ? ' selected' : ''),
            onclick: () => execMove(mv),
          }, moveLabel(s, mv));
        }));
      diceStage.appendChild(moveRow);
    }
  }

  /* ----------------------------------------------------------- cột phụ --- */
  function renderSide() {
    const s = state;
    if (!s) return;

    // 1. Bảng ghế 4 người + thêm/bỏ máy cho Chủ phòng
    clear(seatsCard);
    seatsCard.appendChild(h('div', { class: 'spread' },
      h('div', { class: 'card-title', style: { margin: '0' } }, t('ludo.seatsTitle')),
      s.status === 'waiting' && s.isHost
        ? h('select', {
            class: 'ludo-bot-lvl',
            'aria-label': t('room.botLevelLabel'),
            value: botLevelPick,
            onchange: (e) => {
              botLevelPick = e.target.value;
              localStorage.setItem(`hub.level.${CHANNEL}`, botLevelPick);
            },
          },
            h('option', { value: 'easy', selected: botLevelPick === 'easy' }, t('ludo.botEasy')),
            h('option', { value: 'normal', selected: botLevelPick === 'normal' }, t('ludo.botNormal')),
            h('option', { value: 'hard', selected: botLevelPick === 'hard' }, t('ludo.botHard')))
        : null));

    for (const c of COLORS) {
      const seat = s.seats?.[c];
      const isMe = s.you?.mark === c;
      const isTurn = s.status === 'playing' && s.turn === c;
      const isHostSeat = s.hostMark === c;
      const homeCount = (s.pieces?.[c] || []).filter((p) => p.zone === 'home').length;

      if (!seat) {
        seatsCard.appendChild(h('div', { class: `ludo-seat-row empty c-${c}` },
          h('span', { class: `ludo-dot c-${c}` }),
          h('span', { class: 'small muted grow' }, colorName(c)),
          !s.you?.mark && s.status === 'waiting'
            ? h('button', { type: 'button', class: 'xs ghost', onclick: () => send('sit') }, t('flags.sit'))
            : null,
          s.isHost && s.status === 'waiting'
            ? h('button', {
                type: 'button',
                class: 'xs',
                onclick: () => send('add_bot', { mark: c, level: botLevelPick }),
              }, '+ 🤖')
            : null));
        continue;
      }

      seatsCard.appendChild(h('div', {
        class: `ludo-seat-row c-${c}` + (isMe ? ' me' : '') + (isTurn ? ' turn' : ''),
      },
        h('span', { class: `ludo-dot c-${c}` }),
        avatar(seat, 'sm'),
        h('div', { class: 'col grow', style: { gap: '0', minWidth: '0' } },
          h('span', { class: 'nowrap', style: { fontSize: '13px', fontWeight: isMe ? '700' : '500' } },
            (isHostSeat ? '👑 ' : '') + seat.name + (isMe ? t('shell.youSuffix') : '')),
          h('span', { class: 'tiny muted' },
            `${colorName(c)} · 🏁 ${homeCount}/4 · 🏆 ${s.scores?.[c] || 0}`)),
        s.isHost && s.status === 'waiting' && seat.bot
          ? h('button', {
              type: 'button',
              class: 'xs ghost',
              title: t('ludo.removeBot'),
              onclick: () => send('remove_bot', { mark: c }),
            }, '✕')
          : null));
    }

    // Thao tác ghế cá nhân
    const actRow = h('div', { class: 'row-wrap', style: { marginTop: '4px' } });
    if (s.you?.mark) {
      if (s.status === 'playing') {
        actRow.appendChild(h('button', {
          type: 'button',
          class: 'sm danger ghost',
          onclick: async () => {
            if (await confirmBox({ title: t('room.resignConfirmTitle'), okText: t('room.resignBtn'), danger: true })) {
              send('resign');
            }
          },
        }, icon('flag', 14), ' ', t('room.resignBtn')));
      }
      actRow.appendChild(h('button', {
        type: 'button',
        class: 'sm ghost',
        onclick: () => send('stand'),
      }, t('room.standUp')));
    }
    if (actRow.childNodes.length) seatsCard.appendChild(actRow);

    // 2. Nhật ký nước đi
    clear(feedCard);
    feedCard.appendChild(h('div', { class: 'card-title', style: { margin: '0' } }, t('ludo.feedTitle')));
    const feedList = h('div', { class: 'ludo-feed-list' },
      ...(s.feed || []).slice(-10).reverse().map((item) =>
        h('div', { class: `ludo-feed-item tone-${item.tone || 'move'}` }, item.text)));
    if (!(s.feed || []).length) {
      feedList.appendChild(h('div', { class: 'tiny muted' }, t('ludo.feedEmpty')));
    }
    feedCard.appendChild(feedList);

    mount(roomCardSlot, roomCard(s, CHANNEL));
    mount(chatSlot, roomChat(s, net, CHANNEL));
  }

  function updateBanner() {
    const s = state;
    if (!s) return;
    if (s.status === 'waiting') {
      const n = COLORS.filter((c) => s.seats?.[c]).length;
      banner.className = 'status-bar wait';
      banner.textContent = t('ludo.bannerWaiting', { n });
      return;
    }
    if (s.status === 'finished') {
      banner.className = 'status-bar ' + (s.winner === s.you?.mark ? 'won' : 'lost');
      banner.textContent = s.winner === 'draw'
        ? t('ludo.draw')
        : t('ludo.winBanner', { name: nameOf(s, s.winner), color: colorName(s.winner) });
      return;
    }
    const mine = s.you?.mark === s.turn;
    const ev = s.lastEvent;
    if (ev && ev.type === 'kick_back') {
      banner.className = 'status-bar turn';
      banner.textContent = `⚔️ ${nameOf(s, ev.color)} ĐÁ HẬU ${nameOf(s, ev.kickedColor)}! · ${mine ? t('ludo.yourTurn') : t('ludo.playerTurn', { name: nameOf(s, s.turn), color: colorName(s.turn) })}`;
      return;
    }
    banner.className = 'status-bar ' + (mine ? 'turn' : 'wait');
    banner.textContent = mine
      ? (s.phase === 'roll' ? t('ludo.bannerRoll') : t('ludo.bannerPick', { dice: s.dice }))
      : t('ludo.bannerOther', { name: nameOf(s, s.turn), color: colorName(s.turn) });
  }

  function updateClock() {
    if (!state || !state.deadline || state.status !== 'playing') {
      clockBadge.classList.add('hidden');
      lastClockSec = -1;
      return;
    }
    const nowServer = Date.now() + serverSkewMs;
    const sec = Math.max(0, Math.ceil((state.deadline * 1000 - nowServer) / 1000));
    if (sec === lastClockSec) return;
    lastClockSec = sec;
    clockBadge.classList.remove('hidden');
    clockBadge.classList.toggle('low', sec <= 7);
    clockBadge.textContent = `⏱ ${sec}s`;
  }

  function renderAll() {
    if (!state) return;
    ctx.setTopbar(...roomTopbar(ctx, state, CHANNEL, t('ludo.title')));
    updateBanner();
    renderBoard();
    renderControls();
    renderSide();
    updateClock();
  }

  const onKeyDown = (event) => {
    if (!state || state.status !== 'playing' || state.turn !== state.you?.mark) return;
    const tag = (event.target?.tagName || '').toLowerCase();
    if (tag === 'input' || tag === 'textarea' || tag === 'select') return;
    if (event.code === 'Space' && state.phase === 'roll') {
      event.preventDefault();
      execRoll(diceStage.querySelector('.ludo-roll-btn'));
    }
  };
  document.addEventListener('keydown', onKeyDown);

  const stopNet = net.on(CHANNEL, (msg) => {
    if (msg.t === 'state') {
      state = msg;
      selectedPiece = null;
      if (typeof msg.now === 'number') {
        serverSkewMs = msg.now * 1000 - Date.now();
      }
      const rSeq = msg.lastRoll?.seq || 0;
      const eSeq = msg.lastEvent?.seq || 0;
      if (rSeq > prevRollSeq) {
        prevRollSeq = rSeq;
        if (!optimisticRollPlayed) sfx.move();
        optimisticRollPlayed = false;
      }
      if (eSeq > prevEventSeq) {
        prevEventSeq = eSeq;
        const evType = msg.lastEvent?.type;
        if (evType === 'kick' || evType === 'kick_back' || evType === 'deploy_kick') {
          sfx.hit();
        }
      }
      if (prevStatus === 'playing' && msg.status === 'finished') {
        if (msg.you?.mark && msg.winner === msg.you.mark) sfx.win();
        else if (msg.you?.mark) sfx.lose();
      }
      prevStatus = msg.status;
      renderAll();
    } else if (msg.t === 'error') {
      toast(msg.message, 'danger');
    } else if (msg.t === 'closed') {
      toast(msg.message || t('shell.roomClosed'), 'danger');
      ctx.navigate(CHANNEL);
    }
  });

  const timer = setInterval(updateClock, 250);
  const join = () => send('join', { room: code });
  const stopRejoin = net.onRejoin(join);
  join();

  return () => {
    stopNet();
    stopRejoin();
    clearInterval(timer);
    document.removeEventListener('keydown', onKeyDown);
    send('leave');
  };
}

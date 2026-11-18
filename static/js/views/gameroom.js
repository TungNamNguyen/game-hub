/* Phần vỏ dùng chung của Caro và Bắn tàu.
 *
 * Hai game khác nhau ở bàn chơi, nhưng giống hệt nhau ở: sảnh chờ, tạo phòng,
 * link mời, bảng ghế, tỉ số, nút đánh lại / xin thua / rời ghế, chat trong
 * phòng. Gom hết vào đây để hai view chỉ còn việc vẽ bàn.
 */

import { api, avatar, clear, copyText, h, icon, mount, postJSON } from '../dom.js';
import { botLevelDesc, botLevelLabel, modeLabel, onLangChange, seatLabelI18n, statusLabel, t } from '../i18n.js';
import { openRulesModal } from '../rules.js';
import { confirmBox, createSelect, emptyState, toast } from '../ui.js';

/* ============================================================ sảnh chờ === */
/** Nhãn cho từng trạng thái phòng (giữ STATUS_LABEL để tương thích ngược). */
export const STATUS_LABEL = {
  waiting: 'đang chờ người',
  placing: 'đang xếp tàu',
  playing: 'đang chơi',
  finished: 'vừa xong',
};

export async function renderLobby(root, ctx, channel,
                                  { title, blurb, iconName = 'caro', onEnter,
                                    botHint = '', humanHint = '', extraBody = null,
                                    extraFields = null }) {
  const listBox = h('div', { class: 'col' });
  let modes = [];
  let def = '';

  try {
    const info = await api(`/api/modes/${channel}`);
    modes = info.modes;
    def = info.default;
  } catch {
    modes = [];
  }

  const stored = localStorage.getItem(`hub.mode.${channel}`);
  const initialMode = (modes.some((m) => m.id === stored) && stored) || def;
  const modeSelect = modes.length > 1
    ? createSelect({
        options: modes.map((m) => ({ value: m.id, label: modeLabel(channel, m.id, m.label) })),
        value: initialMode,
        ariaLabel: t('room.boardMode'),
        onChange: (val) => localStorage.setItem(`hub.mode.${channel}`, val),
      })
    : null;

  const codeInput = h('input', {
    maxlength: 4,
    placeholder: t('room.codePlaceholder'),
    style: { textTransform: 'uppercase', letterSpacing: '3px', fontWeight: '700' },
    onkeydown: (event) => { if (event.key === 'Enter') joinByCode(); },
  });

  const currentMode = () => (modeSelect ? modeSelect.value : def);

  /* --- máy có chơi được game này không -------------------------------- */
  let botInfo = null;
  try {
    const info = await api('/api/bots');
    if (info.channels.includes(channel)) botInfo = info;
  } catch {
    botInfo = null;          // không có máy thì chỉ còn chế độ chơi với người
  }

  /* --- trạng thái của bảng chọn --------------------------------------- */
  const sideKey = `hub.opponent.${channel}`;
  const levelKey = `hub.level.${channel}`;
  // 'human' | 'bot'. Chỉ cho phép 'bot' khi server thật sự có máy cho game này.
  let side = botInfo && localStorage.getItem(sideKey) === 'bot' ? 'bot' : 'human';
  let level = localStorage.getItem(levelKey) || (botInfo ? botInfo.default : 'normal');
  if (botInfo && !botInfo.levels.some((l) => l.id === level)) level = botInfo.default;

  let busy = false;

  /** Gọi API tạo phòng rồi vào. `kind`: 'quick' | 'room' | 'bot'. */
  async function start(kind) {
    if (busy) return;
    busy = true;
    try {
      const path = kind === 'quick' ? '/api/rooms/quick'
        : kind === 'bot' ? '/api/rooms/solo' : '/api/rooms';
      const body = { channel, mode: currentMode() };
      if (kind === 'bot') body.level = level;
      if (typeof extraBody === 'function') {
        const extra = extraBody();
        if (extra && typeof extra === 'object') Object.assign(body, extra);
      }
      const { code } = await postJSON(path, body);
      onEnter(code);
    } catch (err) {
      toast(err.message, 'danger');
    } finally {
      busy = false;
    }
  }

  function joinByCode() {
    const code = codeInput.value.trim().toUpperCase();
    if (code.length !== 4) { toast(t('room.codeInvalid'), 'danger'); return; }
    onEnter(code);
  }

  /* --- thẻ "Vào chơi" ------------------------------------------------- */
  const playBox = h('div', { class: 'col' });

  function renderPlay() {
    const switcher = botInfo
      ? h('div', { class: 'segmented', role: 'group', 'aria-label': t('room.opponentAria') },
          h('button', {
            class: side === 'human' ? 'active' : '',
            'aria-pressed': String(side === 'human'),
            onclick: () => {
              side = 'human';
              localStorage.setItem(sideKey, side);
              renderPlay();
            },
          }, icon('users', 15), ' ' + t('room.vsHuman')),
          h('button', {
            class: side === 'bot' ? 'active' : '',
            'aria-pressed': String(side === 'bot'),
            onclick: () => {
              side = 'bot';
              localStorage.setItem(sideKey, side);
              renderPlay();
            },
          }, t('room.vsBot')))
      : null;

    const levelField = side === 'bot' && botInfo
      ? h('div', { class: 'field' },
          h('label', {}, t('room.botLevelLabel')),
          h('div', { class: 'level-grid', role: 'group', 'aria-label': t('room.levelAria') },
            botInfo.levels.map((item) => h('button', {
              class: 'level-btn' + (item.id === level ? ' active' : ''),
              'aria-pressed': String(item.id === level),
              onclick: () => {
                level = item.id;
                localStorage.setItem(levelKey, level);
                renderPlay();          // chỉ đổi lựa chọn, chưa vào phòng
              },
            },
              h('span', { class: 'level-name' }, botLevelLabel(item.id, item.label)),
              h('span', { class: 'level-desc' }, botLevelDesc(item.id, item.desc))))))
      : null;

    const actions = side === 'bot'
      ? h('div', { class: 'row' },
          h('button', {
            class: 'primary grow', onclick: () => start('bot'),
          }, t('room.startBot')))
      : h('div', { class: 'row' },
          h('button', { class: 'primary grow', onclick: () => start('quick') },
            t('room.quickPlay')),
          h('button', { class: 'grow', onclick: () => start('room') },
            t('room.createPrivate')));

    mount(playBox,
      switcher,
      modeSelect ? h('div', { class: 'field' }, h('label', {}, t('room.boardMode')), modeSelect) : null,
      typeof extraFields === 'function' ? extraFields(side) : extraFields,
      levelField,
      actions,
      h('div', { class: 'row' }, codeInput,
        h('button', { onclick: joinByCode }, t('room.joinByCode'))));
  }

  mount(root,
    h('div', { class: 'col', style: { maxWidth: '620px', margin: '0 auto', gap: '16px' } },
      h('div', { class: 'hero' },
        h('div', { class: 'spread', style: { alignItems: 'center', gap: '12px' } },
          h('h1', {}, title),
          h('button', {
            class: 'sm ghost',
            type: 'button',
            onclick: () => openRulesModal(channel),
          }, icon('book', 15), ' ' + t('shell.rulesBtn'))),
        blurb ? h('p', { class: 'dim', style: { marginTop: '6px' } }, blurb) : null),
      h('div', { class: 'card' },
        h('div', { class: 'card-title' }, t('room.playCardTitle')),
        playBox),
      h('div', { class: 'card' },
        h('div', { class: 'spread', style: { marginBottom: '12px' } },
          h('div', { class: 'card-title', style: { margin: '0' } }, t('room.openRoomsTitle')),
          h('button', { class: 'xs ghost', onclick: () => refresh() }, t('room.refresh'))),
        listBox)));

  renderPlay();

  async function refresh() {
    try {
      const data = await api('/api/rooms');
      const rooms = (data.rooms || {})[channel] || [];
      clear(listBox);
      if (!rooms.length) {
        listBox.appendChild(emptyState(t('room.empty'),
          iconName));
        return;
      }
      // Phòng còn ghế trống lên trước: đó là phòng vào được ngay.
      const sorted = [...rooms].sort((a, b) => b.openSeats - a.openSeats);
      for (const room of sorted) {
        const label = statusLabel(room.status);
        const modeText = modeLabel(channel, room.mode, room.label);
        listBox.appendChild(h('div', { class: 'room-row' },
          h('div', { class: 'grow', style: { minWidth: '0' } },
            h('div', { class: 'row', style: { gap: '8px' } },
              h('div', { class: 'room-code' }, room.code),
              room.solo ? h('span', { class: 'chip bot-chip' }, t('room.soloChip')) : null,
              room.tournament
                ? h('span', { class: 'chip accent' }, room.stage === 'lobby'
                    ? t('room.tourReg')
                    : room.stage === 'done' ? t('room.tourDone')
                      : t('room.tourAlive', { alive: room.alive }))
                : null),
            h('div', { class: 'tiny muted nowrap' },
              `${modeText} · ${label}`
              + (room.players.length
                ? ' · ' + room.players.join((room.seatCount || 2) > 2 ? ', ' : ' vs ')
                : ''))),
          h('button', {
            class: 'sm' + (room.openSeats ? ' primary' : ''),
            onclick: () => onEnter(room.code),
          }, room.openSeats ? t('room.enterPlay') : t('room.enterWatch'))));
      }
    } catch (err) {
      mount(listBox, h('div', { class: 'banner danger' }, err.message));
    }
  }

  await refresh();
  const timer = setInterval(refresh, 4000);
  return () => clearInterval(timer);
}

/* ======================================================= linh kiện phòng = */

export function formatClockSec(sec) {
  const s = Math.max(0, Math.ceil(Number(sec || 0)));
  const m = Math.floor(s / 60);
  const r = s % 60;
  return `${String(m).padStart(2, '0')}:${String(r).padStart(2, '0')}`;
}

/** Bảng hai ghế kèm tỉ số (và đồng hồ thi đấu nếu có). */
export function seatPanel(state, { markClass = true, clockSkew = 0 } = {}) {
  const box = h('div', { class: 'seats' });
  const clock = state.clock && state.clock.enabled ? state.clock : null;
  const nowServer = Date.now() / 1000 + clockSkew;

  for (const mark of ['X', 'O']) {
    const seat = state.seats[mark];
    const isMe = mark === state.you.mark;
    const active = state.turn === mark && (state.status === 'playing' || state.status === 'placing');
    let clockNode = null;
    if (clock) {
      let rem = Number((clock.remain && clock.remain[mark]) ?? clock.initial ?? 0);
      if (state.status === 'playing' && state.turn === mark && clock.turnStartedAt) {
        rem = Math.max(0, rem - Math.max(0, nowServer - clock.turnStartedAt));
      }
      const low = state.status === 'playing' && rem <= 20;
      clockNode = h('div', {
        class: 'seat-clock' + (active ? ' running' : '') + (low ? ' low' : ''),
        dataset: { clockSeat: mark },
        title: clock.increment ? t('room.clockTitleInc', { inc: clock.increment }) : t('room.clockTitle'),
      }, '⏱ ', formatClockSec(rem));
    }
    box.appendChild(h('div', {
      class: 'seat' + (active ? ' active' : '') + (isMe ? ' me' : '')
             + (seat && seat.bot ? ' bot' : ''),
    },
      h('div', { class: 'spread', style: { gap: '6px' } },
        h('div', { class: 'row', style: { gap: '7px' } },
          h('span', {
            class: 'seat-mark' + (markClass ? ' ' + mark.toLowerCase() : ''),
          }, state.seatLabels ? seatLabelI18n(state.seatLabels[mark]) : mark),
          seat
            ? (seat.bot
                ? h('span', { class: 'seat-bot', title: t('room.botTitle') }, '🤖')
                : h('span', { class: 'dot' + (seat.connected ? '' : ' off') }))
            : null),
        clockNode),
      h('div', { class: 'small nowrap', style: { marginTop: '3px' } },
        seat ? (seat.name + (isMe ? t('shell.youSuffix') : '')) : h('span', { class: 'muted' }, t('room.emptySeat'))),
      h('div', { class: 'tiny muted' }, t('room.winsCount', { n: state.scores[mark] || 0 }))));
  }
  return box;
}

/** Nút đánh lại / xin thua / ngồi / rời ghế. */
export function actionRow(state, net, channel) {
  const seated = Boolean(state.you.mark);
  const finished = state.status === 'finished';
  const playing = state.status === 'playing' || state.status === 'placing';
  const voted = state.rematch.includes(state.you.mark);
  const hasFreeSeat = !state.seats.X || !state.seats.O;
  const row = h('div', { class: 'row-wrap' });

  if (finished && seated) {
    row.appendChild(h('button', {
      class: 'primary', disabled: voted,
      onclick: () => net.send(channel, 'rematch'),
    }, voted ? t('room.rematchWait') : t('room.rematch')));
  }
  if (playing && seated) {
    row.appendChild(h('button', {
      onclick: async () => {
        if (await confirmBox({ title: t('room.resignConfirmTitle'), okText: t('room.resignBtn'), danger: true })) {
          net.send(channel, 'resign');
        }
      },
    }, icon('flag', 15), ' ' + t('room.resignBtn')));
  }
  if (!seated && hasFreeSeat) {
    row.appendChild(h('button', { class: 'primary', onclick: () => net.send(channel, 'sit') },
      t('room.sitFree')));
  }
  if (seated) {
    row.appendChild(h('button', { class: 'ghost', onclick: () => net.send(channel, 'stand') },
      t('room.standUp')));
  }
  return row;
}

/** Thẻ thông tin phòng + link mời. */
export function roomCard(state, channel, extra = null) {
  const link = `${location.origin}/#/${channel}/${state.code}`;
  const linkInput = h('input', {
    readOnly: true, value: link, class: 'tiny',
    onclick: (event) => event.target.select(),
  });
  return h('div', { class: 'card tight col' },
    h('div', { class: 'spread' },
      h('div', {},
        h('div', { class: 'card-title', style: { margin: '0' } }, t('room.cardTitle')),
        h('div', { class: 'room-code' }, state.code)),
      h('span', { class: 'chip accent' }, modeLabel(channel, state.mode, state.label))),
    extra,
    h('div', { class: 'field' },
      h('label', {}, t('room.inviteLabel')),
      linkInput,
      h('div', { class: 'row' },
        h('button', {
          class: 'sm grow',
          onclick: async () => {
            const ok = await copyText(link);
            toast(ok ? t('room.linkCopied') : t('room.copyFailed'), ok ? 'ok' : 'danger');
          },
        }, icon('copy', 14), ' ' + t('room.copyLink')),
        h('button', {
          class: 'sm grow',
          onclick: async () => {
            const ok = await copyText(state.code);
            toast(ok ? t('room.codeCopied', { code: state.code }) : t('room.copyCodeFailed'), ok ? 'ok' : 'danger');
          },
        }, t('room.copyCode')))),
    state.spectators.length
      ? h('div', { class: 'tiny muted' }, t('room.spectators', { names: state.spectators.map((s) => s.name).join(', ') }))
      : null);
}

const _chatCache = new Map();
onLangChange(() => _chatCache.clear());

/** Chat trong phòng. Tái sử dụng thẻ <input> theo mã phòng để không bao giờ
 *  làm mất chữ hoặc mất focus khi đối thủ vừa đi nước cờ mới. */
export function roomChat(state, net, channel) {
  const key = `${channel}:${state.code || ''}`;
  let entry = _chatCache.get(key);
  if (!entry) {
    const log = h('div', { class: 'room-chat-log' });
    const input = h('input', { placeholder: t('room.chatPlaceholder'), maxlength: 300 });
    const form = h('form', {
      class: 'row', style: { gap: '6px' },
      onsubmit: (event) => {
        event.preventDefault();
        const text = input.value.trim();
        if (!text) return;
        entry.net.send(channel, 'say', { text });
        input.value = '';
      },
    }, input, h('button', { class: 'sm', type: 'submit' }, t('room.chatSend')));

    const card = h('div', { class: 'card tight room-chat' },
      h('div', { class: 'card-title', style: { marginBottom: '6px' } }, t('room.chatTitle')), log, form);
    entry = { card, log, input, net, sig: '' };
    if (_chatCache.size > 24) {
      const oldest = _chatCache.keys().next().value;
      _chatCache.delete(oldest);
    }
    _chatCache.set(key, entry);
  }
  entry.net = net;

  const chatList = state.chat || [];
  const last = chatList[chatList.length - 1];
  const sig = `${chatList.length}:${last ? (last.ts || '') + ':' + (last.text || '') : ''}`;
  if (entry.sig !== sig) {
    entry.sig = sig;
    const { log } = entry;
    const wasNearBottom = log.scrollHeight - log.scrollTop - log.clientHeight < 48;
    clear(log);
    for (const item of chatList) {
      if (item.kind === 'system') {
        log.appendChild(h('div', { class: 'sys' }, item.text));
      } else {
        log.appendChild(h('div', {},
          h('span', { style: { color: item.color || 'var(--accent-soft)', fontWeight: '650' } },
            item.name + ': '),
          item.text));
      }
    }
    if (wasNearBottom) {
      requestAnimationFrame(() => { log.scrollTop = log.scrollHeight; });
    }
  }
  return entry.card;
}

/** Thanh tiêu đề trên topbar khi đang ở trong phòng. */
export function roomTopbar(ctx, state, channel, label) {
  return [
    h('div', { class: 'row grow room-topbar', style: { minWidth: '0', gap: '6px' } },
      h('button', {
        class: 'sm ghost',
        onclick: () => { ctx.net.send(channel, 'leave'); ctx.navigate(channel); },
      }, t('shell.backLobby')),
      h('span', { class: 'chip room-topbar-label' }, label),
      h('span', { class: 'room-code', style: { fontSize: '14px' } }, state.code),
      h('span', { class: 'grow' }),
      h('button', {
        class: 'xs ghost room-rules-btn',
        type: 'button',
        title: t('shell.rulesTitle'),
        onclick: () => openRulesModal(channel),
      }, icon('book', 14), h('span', { class: 'room-rules-label' }, ' ' + t('shell.rulesBtn')))),
  ];
}

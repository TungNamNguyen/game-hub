/* Xì Tố (No-Limit Texas Hold'em) — bàn chơi.
 *
 * Bố cục theo các site poker online (PokerStars, GGPoker...):
 *   - Bàn nỉ hình bầu dục, tối đa 6 ghế. Ghế của MÌNH luôn ở giữa cạnh dưới.
 *   - Chip đã cược hiện trước mặt từng người, pot + 5 ô bài chung ở giữa.
 *   - Khu "hero" dưới bàn: 2 lá tẩy cỡ lớn + tên tay bài hiện tại.
 *   - Bảng hành động: Bỏ bài / Qua / Theo / Cược / Tố với ô nhập số, thanh
 *     trượt, các nút nhanh Min · ½ Pot · ¾ Pot · Pot · Tất tay, và phím tắt.
 *   - Hành động đặt trước (Qua/Bỏ, Theo bất kỳ, Qua) khi chưa tới lượt.
 *
 * Khu chat và bảng xếp hạng được dựng MỘT LẦN rồi chỉ cập nhật phần ruột —
 * nếu dựng lại mỗi gói state thì ô đang gõ chat sẽ bị xoá mỗi khi ai đó cược.
 * Bảng hành động cũng chỉ dựng lại khi tình huống cược đổi, để không giật mất
 * thanh trượt đang kéo.
 */

import { avatar, clear, copyText, h, icon, mount } from '../dom.js';
import { EMOJI_GROUPS } from '../emoji.js';
import { emojiGroupName, locale, modeLabel, pokerReasonLabel, seatLabelI18n, t, tauntLabel } from '../i18n.js';
import { confirmBox, sfx, toast } from '../ui.js';
import { cardBack, cardSlot, pokerCardFace } from '../pokercards.js';
import { renderLobby, roomTopbar } from './gameroom.js';

const CHANNEL = 'poker';

/** Chỗ ghế (% khung bàn), theo chiều kim đồng hồ từ ghế mình.
 *
 * Phần tử thứ ba là MỐC NEO: 'top' = toạ độ là mép TRÊN của ghế, 'bottom' =
 * mép DƯỚI, bỏ trống = tâm. Ghế sát mép trên/dưới phải neo theo mép, vì bàn
 * co theo chiều cao màn hình còn ghế cao cố định — neo theo tâm thì màn thấp
 * sẽ cắt mất nửa ghế (đúng lỗi trên laptop màn rộng nhưng thấp).
 */
// Ghế hai bên neo theo mép 'left' / 'right' vì cùng lý do: bàn hẹp (điện
// thoại, cửa sổ chia đôi) thì ghế neo theo tâm sẽ thò ra ngoài bàn.
const SPOTS = {
  2: [[50, 98, 'bottom'], [50, 3, 'top']],
  3: [[50, 98, 'bottom'], [2, 30, 'left'], [98, 30, 'right']],
  4: [[50, 98, 'bottom'], [1.5, 50, 'left'], [50, 3, 'top'], [98.5, 50, 'right']],
  5: [[50, 98, 'bottom'], [1.5, 64, 'left'], [24, 3, 'top'], [76, 3, 'top'],
      [98.5, 64, 'right']],
  6: [[50, 98, 'bottom'], [1.5, 70, 'left'], [3, 26, 'left'], [50, 3, 'top'],
      [97, 26, 'right'], [98.5, 70, 'right']],
};
const CENTER = [50, 47];

// Thuật ngữ đánh bài giữ nguyên tiếng Anh như mọi site poker online — người
// chơi quen "Check / Call / Raise" hơn "Qua / Theo / Tố".
const ACTION_TEXT = {
  sb: 'Small blind', bb: 'Big blind', check: 'Check', call: 'Call', bet: 'Bet',
  raise: 'Raise', allin: 'All-in', fold: 'Fold',
};

const fmt = (n) => Number(n || 0).toLocaleString(locale());

export default {
  async mount(root, ctx, param) {
    if (!param) {
      return renderLobby(root, ctx, CHANNEL, {
        title: t('poker.title'),
        blurb: t('poker.blurb'),
        iconName: 'cards',
        onEnter: (code) => ctx.navigate(`${CHANNEL}/${code}`),
      });
    }
    return mountRoom(root, ctx, param.toUpperCase());
  },
};

function mountRoom(root, ctx, code) {
  const { net } = ctx;
  let state = null;
  let clockSkew = 0;
  let pre = '';                 // hành động đặt trước: '' | checkfold | callany | check
  let preKey = '';              // tình huống mà hành động đặt trước được chọn
  let autoSentKey = '';
  let actionKey = '';
  let raiseTo = 0;
  let prevActor = '';
  let prevPhase = '';
  let prevHand = 0;
  let prevStage = '';           // giai đoạn giải đấu lần vẽ trước
  let lastChatCount = 0;
  // Bong bóng chat đã hiện (khoá = ts|ghế). Bong bóng nằm ở lớp RIÊNG, tạo
  // đúng một lần cho mỗi tin rồi tự gỡ — nếu vẽ chung với ghế thì mỗi lần bàn
  // vẽ lại, bong bóng bị tạo lại và chạy lại hiệu ứng "bật lên", nhìn y như
  // tin nhắn bị gửi lặp 4-5 lần.
  const bubbles = new Set();
  let prevBets = {};           // ghế -> số chip cược lần vẽ trước (để chỉ diễn khi đổi)
  let resultAnimated = -1;     // ván đã chạy hiệu ứng hiện kết quả

  /* ------------------------------------------------------------ khung ---- */
  const banner = h('div', { class: 'pk-banner', role: 'status', 'aria-live': 'polite' },
    t('shell.connecting'));
  const felt = h('div', { class: 'pk-felt' });
  const oval = h('div', { class: 'pk-oval' });
  const seatLayer = h('div', { class: 'pk-layer' });
  const betLayer = h('div', { class: 'pk-layer' });
  const centerBox = h('div', { class: 'pk-center' });
  felt.append(oval, betLayer, centerBox, seatLayer);

  const heroCards = h('div', { class: 'pk-hero-cards' });
  const heroLabel = h('div', { class: 'pk-hero-label' });
  const heroInfo = h('div', { class: 'pk-hero-info' });
  const actionBox = h('div', { class: 'pk-actions' });
  const hero = h('div', { class: 'pk-hero' },
    h('div', { class: 'pk-hero-left' }, heroCards, heroLabel, heroInfo),
    actionBox);

  const roomBox = h('div', { class: 'card tight col' });
  const tourCard = h('div', { class: 'card tight col pk-tour-card hidden' });
  const boardCard = h('div', { class: 'card tight col pk-leader' });
  const feedBox = h('div', { class: 'feed-list' });
  const feedCard = h('div', { class: 'card tight' },
    h('div', { class: 'card-title', style: { margin: '0 0 6px' } }, t('poker.feedTitle')), feedBox);
  const chatCard = buildChat();

  mount(root, h('div', { class: 'pk-layout' },
    h('div', { class: 'pk-main' }, banner, felt, hero),
    h('div', { class: 'col pk-rail' }, roomBox, tourCard, boardCard, chatCard.card,
      feedCard)));

  /* ---------------------------------------------------------- tra cứu ---- */
  const nowServer = () => Date.now() / 1000 + clockSkew;
  const mySeat = (s) => (s.me && s.me.seat) || '';
  const nameOf = (s, seat) => (s.seats[seat] && s.seats[seat].name) || seatLabelI18n(s.seatLabels[seat]) || seat;

  /** Ghế theo chiều kim đồng hồ, bắt đầu từ ghế mình (hoặc ghế 1 nếu đang xem). */
  function ring(s) {
    const order = s.seatOrder;
    const start = Math.max(0, order.indexOf(mySeat(s)));
    return order.map((_, i) => order[(start + i) % order.length]);
  }

  function sameCard(a, b) { return a.v === b.v && a.s === b.s; }

  /** 5 lá thắng của pot chính ở lần chia ``run`` (1 hoặc 2), để làm sáng.
   * Khi chia 2 lần thì mỗi dãy bài chung có người thắng riêng. */
  function winningCards(s, run = 1) {
    const r = s.result;
    if (!r || !r.showdown || !r.pots.length) return [];
    const pot = r.pots.find((p) => (p.run || 1) === run) || r.pots[0];
    const hand = r.hands[pot.winners[0]];
    if (!hand) return [];
    return run === 2 && hand.best2 ? hand.best2 : hand.best;
  }

  /* --------------------------------------------------------- một ghế ---- */
  function seatNode(s, seat, [x, y, at]) {
    const info = s.seats[seat];
    const mine = seat === mySeat(s);
    const node = h('div', {
      class: 'pk-seat' + (at ? ' at-' + at : ''),
      style: { left: x + '%', top: y + '%' },
      dataset: { seat },
    });

    const tour = s.tournament;
    // Giải đã chốt danh sách: ghế trống là ghế KHÔNG tham gia, không mở lại.
    const locked = Boolean(tour) && tour.stage !== 'lobby';

    if (!info) {
      node.classList.add('empty');
      const seated = Boolean(mySeat(s));
      node.appendChild(h('div', { class: 'pk-empty-ring' }, icon('users', 18)));
      node.appendChild(locked
        ? h('div', { class: 'tiny muted' }, t('poker.notPlaying'))
        : seated
          ? h('div', { class: 'tiny muted' }, tour ? t('poker.waitReg') : t('poker.emptySeat'))
          : h('button', {
              class: 'xs primary', onclick: () => net.send(CHANNEL, 'requestSeat', { seat }),
            }, tour ? t('poker.regSeat') : t('poker.sitHere')));
      return node;
    }

    const acting = s.actor === seat && s.phase === 'betting';
    const r = s.result;
    const won = r && r.winners.includes(seat);
    node.classList.toggle('me', mine);
    node.classList.toggle('acting', acting);
    node.classList.toggle('folded', info.folded);
    node.classList.toggle('out', !info.dealt && s.status === 'playing');
    node.classList.toggle('winner', Boolean(won));
    node.classList.toggle('offline', !info.connected);
    node.classList.toggle('eliminated', Boolean(info.eliminated));
    node.classList.toggle('champion', Boolean(tour && tour.champion === seat));

    // Bong bóng chat / cà khịa gần nhất (4 giây). Hiệu ứng "bật lên" chỉ chạy
    // LẦN ĐẦU một tin xuất hiện (``bubbles`` nhớ các tin đã diễn). Bàn vẽ lại
    // liên tục, nếu lần nào cũng diễn thì nhìn như tin bị gửi lặp 4-5 lần.
    const last = [...s.chat].reverse().find((m) => m.mark === seat && m.kind !== 'system');
    const age = last ? nowServer() - last.ts : 99;
    if (last && age < 4) {
      const key = `${last.ts}|${seat}`;
      const fresh = !bubbles.has(key);
      bubbles.add(key);
      node.appendChild(h('div', {
        class: 'pk-bubble' + (last.kind === 'taunt' ? ' taunt' : '') + (fresh ? ' fresh' : ''),
        dataset: { until: String(Date.now() + (4 - age) * 1000) },
      }, last.kind === 'taunt' ? tauntLabel(last.text) : last.text));
    }

    // Bài: người khác thì mặt sau, trừ khi đã lật (showdown / all-in / khoe).
    // Người đã bỏ bài vẫn hiện bài nếu họ bấm "Khoe bài" lúc hết ván.
    const shown = s.shown[seat];
    if ((info.live || shown) && !mine) {
      const best = winningCards(s);
      node.appendChild(h('div', { class: 'pk-seat-cards' + (shown ? ' shown' : '') },
        shown
          ? shown.map((c) => pokerCardFace(c, {
              size: 40, className: best.some((b) => sameCard(b, c)) ? 'hl' : '' }))
          : [cardBack({ size: 34 }), cardBack({ size: 34 })]));
    }

    const face = h('div', { class: 'pk-face' },
      avatar(info, 'lg'),
      acting ? h('div', { class: 'pk-timer' }) : null);
    node.appendChild(face);

    const plate = h('div', { class: 'pk-plate' },
      h('div', { class: 'pk-name nowrap' }, info.name + (mine ? t('shell.youSuffix') : '')),
      h('div', { class: 'pk-stack' }, info.allIn ? 'ALL-IN' : fmt(info.chips)));
    node.appendChild(plate);

    // Huy hiệu giải đấu: chủ phòng lúc đăng ký, cúp cho nhà vô địch.
    if (tour && tour.stage === 'lobby' && info.host) {
      node.appendChild(h('span', { class: 'pk-host', title: t('poker.hostBadge') }, '★'));
    }
    if (tour && tour.champion === seat) {
      node.appendChild(h('span', { class: 'pk-crown', title: t('poker.champBadge') }, '👑'));
    }

    // Huy hiệu vị trí.
    if (s.button === seat) node.appendChild(h('span', { class: 'pk-dealer', title: t('poker.dealerBtnTitle') }, 'D'));
    const pos = s.sbSeat === seat ? 'SB' : s.bbSeat === seat ? 'BB' : '';
    if (pos && s.street === 'preflop' && s.phase !== 'showdown') {
      node.appendChild(h('span', { class: 'pk-pos' }, pos));
    }

    // Dòng trạng thái dưới tên: hành động gần nhất, hoặc lý do không chơi.
    let tag = '';
    let tone = '';
    if (info.eliminated) {
      tag = tour && tour.champion === seat ? t('poker.champTag') : t('poker.elimPlace', { place: info.place });
      tone = tour && tour.champion === seat ? 'win' : 'fold';
    } else if (info.outAt) {
      const left = Math.max(0, Math.ceil(info.outAt - nowServer()));
      tag = t('poker.dcLeft', { s: left });
      tone = 'fold';
    } else if (won && r) {
      tag = `+${fmt(r.payouts[seat] || 0)}`;
      tone = 'win';
    } else if (s.phase === 'showdown' && r && r.hands[seat]) {
      const hand = r.hands[seat];
      tag = hand.label2 ? `${hand.label} | ${hand.label2}` : hand.label;
    } else if (s.phase === 'ritvote' && s.rit.votes[seat] !== undefined) {
      const vote = s.rit.votes[seat];
      tag = vote === null ? t('poker.deciding') : vote ? t('poker.runTwiceOk') : t('poker.runOnce');
      tone = vote ? 'call' : 'none';
    } else if (info.action && info.action !== 'sb' && info.action !== 'bb') {
      tag = ACTION_TEXT[info.action] || info.action;
      tone = info.action;
    } else if (!info.connected) {
      tag = t('poker.dcStatus');
    } else if (info.leaving) {
      tag = t('poker.leavingStatus');
    } else if (info.sittingOut) {
      tag = t('poker.sittingOutStatus');
    } else if (info.chips <= 0 && !info.live) {
      tag = t('poker.bustedStatus');
      tone = 'fold';
    } else if (!info.dealt && s.status === 'playing') {
      tag = t('poker.nextHandStatus');
    }
    if (tag) {
      node.appendChild(h('div', {
        class: 'pk-tag tone-' + (tone || 'none'),
        // Đếm lùi hạn quay lại được đồng hồ 150ms cập nhật, không phải chờ gói
        // state mới (server chỉ phát khi có người hành động).
        dataset: info.eliminated || !info.outAt ? {} : { out: String(info.outAt) },
      }, tag));
    }

    // Giải đấu không có hàng chờ: ghế đã chốt từ lúc khởi tranh.
    if (tour) return node;

    // Hàng chờ của ghế này.
    const queue = info.queue || [];
    const queued = (s.me.queuedFor || []).includes(seat);
    if (!mySeat(s)) {
      node.appendChild(h('button', {
        class: 'xs ' + (queued ? 'ghost' : ''),
        onclick: () => net.send(CHANNEL, queued ? 'leaveQueue' : 'requestSeat', { seat }),
      }, queued
        ? t('poker.leaveQueue', { n: queue.length })
        : t('poker.queueJoined', { extra: queue.length ? ' · ' + queue.length : '' })));
    } else if (queue.length) {
      node.appendChild(h('div', { class: 'tiny muted' }, t('poker.queueWaiting', { n: queue.length })));
    }
    return node;
  }

  /** Chồng chip cược trước mặt một ghế, nằm giữa ghế và tâm bàn. */
  function betNode(s, seat, [x, y, at]) {
    const info = s.seats[seat];
    if (!info || !info.bet) return null;
    // Ghế neo theo mép: tâm thật của ghế lệch vào trong bàn ~20%, chip cược
    // đặt giữa tâm đó và tâm bàn để không đè lên ghế.
    const cy = at === 'top' ? y + 30 : at === 'bottom' ? y - 22 : y;
    const cx = at === 'left' ? x + 12 : at === 'right' ? x - 12 : x;
    const k = 0.4;
    let bx = cx + (CENTER[0] - cx) * k;
    let by = cy + (CENTER[1] - cy) * k;
    // Ghế trên cùng: đặt chip lệch sang phải ghế, ngang hàng nhãn hành động,
    // để không đè lên dòng "Hand #… · Preflop" giữa bàn.
    if (at === 'top') { bx = x + 12; by = y + 25; }
    // Chỉ diễn hiệu ứng trượt chip khi số cược vừa đổi, không phải mỗi lần vẽ.
    const fresh = prevBets[seat] !== info.bet;
    return h('div', { class: 'pk-bet' + (fresh ? ' fresh' : ''),
                      style: { left: bx + '%', top: by + '%' } },
      h('span', { class: 'pk-chip' }), fmt(info.bet));
  }

  /** Gỡ bong bóng đã hết 4 giây mà không phải vẽ lại cả bàn. */
  const bubbleSweep = setInterval(() => {
    const now = Date.now();
    for (const node of seatLayer.querySelectorAll('.pk-bubble')) {
      if (Number(node.dataset.until) < now) node.remove();
    }
  }, 500);

  /* ---------------------------------------------------------- giữa bàn --- */
  function boardRow(cards, best, size, label) {
    const slots = [];
    for (let i = 0; i < 5; i++) {
      const card = cards[i];
      slots.push(card
        ? pokerCardFace(card, {
            size,
            className: best.length ? (best.some((b) => sameCard(b, card)) ? 'hl' : 'dim') : '',
          })
        : cardSlot({ size }));
    }
    return h('div', { class: 'pk-board-row' },
      label ? h('span', { class: 'pk-run-tag' }, label) : null,
      h('div', { class: 'pk-board' }, slots));
  }

  function centerNode(s) {
    const rit = s.rit || {};
    const twoBoards = rit.twice && (s.board1.length || rit.run === 2);
    const size = twoBoards ? 48 : 62;
    const potShown = s.result
      ? s.result.pots.reduce((sum, p) => sum + p.amount, 0)
      : s.pot;
    const street = rit.twice ? t('poker.ritRun', { run: rit.run }) : s.streetName;
    return h('div', { class: 'pk-center-inner' },
      h('div', { class: 'pk-street' },
        s.status === 'playing'
          ? t('poker.handStreet', { no: s.handNo, street })
          : t('poker.waitDeal')),
      twoBoards ? boardRow(s.board1, winningCards(s, 1), size, t('poker.runTag', { run: 1 })) : null,
      boardRow(s.board, winningCards(s, twoBoards ? 2 : 1), size, twoBoards ? t('poker.runTag', { run: 2 }) : ''),
      potShown
        ? h('div', { class: 'pk-pot' }, h('span', { class: 'pk-chip' }), `Pot ${fmt(potShown)}`)
        : null,
      s.sidePots && s.sidePots.length
        ? h('div', { class: 'pk-sidepots' },
            s.sidePots.map((p, i) => h('span', {},
              i ? t('poker.sidePot', { n: i, amount: fmt(p.amount) })
                : t('poker.mainPot', { amount: fmt(p.amount) }))))
        : null,
      resultNode(s));
  }

  function resultNode(s) {
    const r = s.result;
    if (!r) return null;
    // Hiệu ứng bật lên chỉ chạy lần đầu của mỗi ván, không chạy lại mỗi lần vẽ.
    const fresh = resultAnimated !== s.handNo;
    resultAnimated = s.handNo;
    return h('div', { class: 'pk-result' + (fresh ? ' fresh' : '') },
      r.pots.map((pot) => h('div', { class: 'pk-result-row' },
        h('strong', {}, pot.winners.map((seat) => nameOf(s, seat)).join(' & ')),
        t('poker.winsPot', {
          pot: r.pots.length > 1 ? pot.name + ' ' : '',
          amount: fmt(pot.amount),
        }),
        pot.label ? h('span', { class: 'pk-result-hand' }, ` · ${pot.label}`) : null)));
  }

  /* ------------------------------------------------------------- hero ---- */
  function renderHero(s) {
    const me = s.me || {};
    const seat = mySeat(s);
    clear(heroCards);
    clear(heroInfo);
    const tour = s.tournament;
    if (!seat) {
      heroLabel.textContent = '';
      heroCards.appendChild(h('div', { class: 'pk-hero-empty' },
        tour && tour.locked
          ? t('poker.specTourLocked')
          : tour
            ? t('poker.specTourOpen')
            : t('poker.specCash')));
      return;
    }
    const best = winningCards(s);
    if (me.hole && me.hole.length) {
      me.hole.forEach((card, i) => {
        const face = pokerCardFace(card, {
          size: 86,
          className: (me.folded ? 'dim' : '') + (best.some((b) => sameCard(b, card)) ? ' hl' : ''),
        });
        face.style.setProperty('--tilt', (i ? 5 : -5) + 'deg');
        heroCards.appendChild(face);
      });
      heroLabel.textContent = me.folded ? t('poker.folded') : me.handLabel || '';
    } else {
      heroCards.appendChild(cardSlot({ size: 86 }));
      heroCards.appendChild(cardSlot({ size: 86 }));
      heroLabel.textContent = me.eliminated ? t('poker.elimPlace', { place: me.place })
        : tour && tour.stage === 'lobby' ? t('poker.registeredWait')
          : s.status === 'playing' ? t('poker.dealtNext') : t('poker.waitDeal');
    }
    heroInfo.appendChild(h('span', { class: 'pk-hero-chips' },
      h('span', { class: 'pk-chip' }), t('poker.chipsSuffix', { amount: fmt(me.chips) })));
    if (me.hole && me.hole.length && s.shown[seat]) {
      heroInfo.appendChild(h('span', { class: 'chip' }, t('poker.shownBadge')));
    }
  }

  /* ----------------------------------------------------- bảng hành động -- */
  function situationKey(s) {
    const a = s.act;
    const me = s.me || {};
    const t = s.tournament;
    return JSON.stringify([s.handNo, s.street, s.phase, s.actor, s.currentBet, me.seat,
      me.chips, me.live, me.sittingOut, me.leaving, a && a.canRaise, a && a.minTo,
      me.canShow, me.canVoteRit, s.rit && s.rit.votes,
      t && [t.stage, t.registered, t.ready, t.alive, t.canStart, t.isHost, t.locked,
        me.eliminated, me.place]]);
  }

  function renderActions(s) {
    const key = situationKey(s) + '|' + pre;
    if (key === actionKey) return;
    actionKey = key;
    clear(actionBox);
    const me = s.me || {};
    const seat = mySeat(s);
    const tour = s.tournament;

    if (!seat) {
      const free = s.seatOrder.filter((x) => !s.seats[x]);
      if (tour) {
        actionBox.appendChild(tour.locked
          ? h('div', { class: 'pk-wait' }, tour.stage === 'done'
              ? t('poker.tourLockedDone')
              : t('poker.tourLockedRunning'))
          : h('button', { class: 'primary', onclick: () => net.send(CHANNEL, 'sit') },
              free.length ? t('poker.regJoin') : t('poker.regFull')));
        return;
      }
      actionBox.appendChild(free.length
        ? h('button', { class: 'primary', onclick: () => net.send(CHANNEL, 'sit') },
            t('poker.sitDown'))
        : h('div', { class: 'tiny muted' }, t('poker.tableFullQueue')));
      return;
    }

    // Giải đấu: chưa khởi tranh / đã xong / đã bị loại thì không có gì để cược.
    if (tour && (tour.stage !== 'running' || me.eliminated)) {
      actionBox.appendChild(tourneyPanel(s, tour, me));
      return;
    }

    const util = tour
      ? h('div', { class: 'pk-util' },
          h('button', {
            class: 'xs ghost danger',
            onclick: async () => {
              const ok = await confirmBox({
                title: t('poker.leaveTourConfirmTitle'),
                body: t('poker.leaveTourConfirmBody'),
                okText: t('poker.leaveTourOk'),
                danger: true,
              });
              if (ok) net.send(CHANNEL, 'stand');
            },
          }, t('poker.leaveTourBtn')))
      : h('div', { class: 'pk-util' },
          me.chips <= 0 && !(me.live && ['betting', 'ritvote', 'runout'].includes(s.phase))
            ? h('button', { class: 'primary', onclick: () => net.send(CHANNEL, 'rebuy') },
                t('poker.rebuyBtn', { amount: fmt(s.chipStart) }))
            : null,
          h('button', { class: 'xs ghost', onclick: () => net.send(CHANNEL, 'sitout') },
            me.sittingOut ? t('poker.imBack') : t('poker.sitOut')),
          h('button', {
            class: 'xs ghost', onclick: () => net.send(CHANNEL, me.leaving ? 'sit' : 'stand'),
          }, me.leaving ? t('poker.stay') : t('poker.leaveTable')));

    const a = s.act;
    if (s.phase === 'ritvote' && me.live) {
      actionBox.appendChild(ritPanel(s));
    } else if (s.phase === 'showdown' && me.canShow) {
      actionBox.appendChild(h('div', { class: 'pk-show' },
        h('button', { class: 'pk-btn call', onclick: () => net.send(CHANNEL, 'show') },
          t('poker.showCards')),
        h('span', { class: 'tiny muted' },
          me.folded ? t('poker.showFoldHint') : t('poker.muckHint'))));
    } else if (a) {
      actionBox.appendChild(turnPanel(s, a));
    } else if (me.live && !me.allIn && s.phase === 'betting') {
      actionBox.appendChild(prePanel(s));
    } else {
      let text = '';
      if (s.phase === 'starting') text = t('poker.dealingSoon');
      else if (s.phase === 'showdown') text = t('poker.handOverNext');
      else if (me.allIn && me.live) text = t('poker.youAllin');
      else if (me.folded) text = t('poker.youFoldedWait');
      else if (s.status !== 'playing') {
        text = tour ? t('poker.waitReconnect')
          : t('poker.waitPlayersChips');
      } else if (!me.dealt) text = t('poker.dealtNext');
      if (text) actionBox.appendChild(h('div', { class: 'pk-wait' }, text));
    }
    actionBox.appendChild(util);
  }

  /** Bảng điều khiển giải đấu: đăng ký, bấm bắt đầu, và màn hình sau khi bị
   *  loại / sau khi đã có vô địch. */
  function tourneyPanel(s, tour, me) {
    const box = h('div', { class: 'pk-tourney' });
    const startBtn = (label) => h('button', {
      class: 'pk-btn raise', disabled: !tour.canStart,
      onclick: () => net.send(CHANNEL, 'start'),
    }, label);

    if (tour.stage === 'lobby') {
      box.appendChild(h('div', { class: 'pk-tourney-head' },
        t('poker.tourRegSummary', {
          reg: tour.registered,
          total: tour.seatsTotal,
          chips: fmt(s.chipStart),
        })));
      box.appendChild(h('div', { class: 'tiny muted' },
        t('poker.tourRegDesc', {
          total: tour.seatsTotal,
          min: tour.minPlayers,
        })));
      box.appendChild(h('div', { class: 'pk-main-btns' },
        tour.isHost
          ? startBtn(tour.canStart
              ? t('poker.tourStart', { n: tour.ready })
              : t('poker.tourNeedMin', { min: tour.minPlayers }))
          : h('div', { class: 'pk-wait grow' },
              t('poker.tourWaitHost', { name: tour.hostName || '' })),
        h('button', { class: 'xs ghost', onclick: () => net.send(CHANNEL, 'stand') },
          t('poker.withdrawReg'))));
      return box;
    }

    if (tour.stage === 'done') {
      const champ = tour.champion;
      box.appendChild(h('div', { class: 'pk-tourney-head' + (champ === mySeat(s) ? ' win' : '') },
        champ === mySeat(s) ? t('poker.youChamp')
          : t('poker.otherChamp', { name: nameOf(s, champ) })));
      box.appendChild(h('div', { class: 'tiny muted' },
        me.place ? t('poker.yourPlace', { place: me.place, total: tour.placements.length }) : ''));
      box.appendChild(h('div', { class: 'pk-main-btns' },
        tour.isHost
          ? startBtn(t('poker.newTour'))
          : h('div', { class: 'pk-wait grow' },
              t('poker.waitHostNewTour', { name: tour.hostName || '' }))));
      return box;
    }

    // đang chạy mà mình đã bị loại
    box.appendChild(h('div', { class: 'pk-tourney-head out' },
      t('poker.elimHeader', { place: me.place, total: tour.seatsTotal })));
    box.appendChild(h('div', { class: 'tiny muted' },
      t('poker.elimDesc', { alive: tour.alive })));
    return box;
  }

  /** Bỏ phiếu chia 2 lần — chỉ người còn trong ván lúc tất tay. */
  function ritPanel(s) {
    const me = s.me;
    const votes = s.rit.votes || {};
    const left = Object.entries(votes).filter(([, v]) => v === null).map(([seat]) => nameOf(s, seat));
    const box = h('div', { class: 'pk-rit' },
      h('div', { class: 'pk-rit-title' }, t('poker.ritTitle')),
      h('div', { class: 'tiny muted' }, t('poker.ritDesc')));
    if (me.canVoteRit) {
      box.appendChild(h('div', { class: 'pk-main-btns' },
        h('button', { class: 'pk-btn fold', onclick: () => net.send(CHANNEL, 'rit', { yes: false }) },
          t('poker.ritNo')),
        h('button', { class: 'pk-btn raise', onclick: () => net.send(CHANNEL, 'rit', { yes: true }) },
          t('poker.ritYes'))));
    } else {
      box.appendChild(h('div', { class: 'pk-wait' },
        t('poker.ritWait', { names: left.join(', ') || t('poker.ritOthers') })));
    }
    return box;
  }

  /** Mức "tố lên tới" ứng với một phần pot, theo cách tính pot-size raise. */
  function potTo(a, frac) {
    const potAfterCall = a.pot + a.toCall;
    const target = a.currentBet + Math.round(frac * potAfterCall);
    return Math.max(a.minTo, Math.min(a.maxTo, target));
  }

  function turnPanel(s, a) {
    const box = h('div', { class: 'pk-turn' });
    if (!raiseTo || raiseTo < a.minTo || raiseTo > a.maxTo) raiseTo = a.minTo;

    const send = (tKind, extra) => { net.send(CHANNEL, tKind, extra); pre = ''; };
    const verb = a.isBet ? t('poker.betVerb') : t('poker.raiseVerb');

    if (a.canRaise) {
      const input = h('input', {
        type: 'number', class: 'pk-amount', min: String(a.minTo), max: String(a.maxTo),
        step: String(s.blinds.sb), value: String(raiseTo), 'aria-label': t('poker.raiseInputAria'),
      });
      const slider = h('input', {
        type: 'range', class: 'pk-slider', min: String(a.minTo), max: String(a.maxTo),
        step: String(s.blinds.sb), value: String(raiseTo), 'aria-label': t('poker.betSliderAria'),
      });
      const raiseBtn = h('button', { class: 'pk-btn raise' });
      const sync = (v, from) => {
        raiseTo = Math.max(a.minTo, Math.min(a.maxTo, Math.round(Number(v) || a.minTo)));
        if (from !== 'input') input.value = String(raiseTo);
        if (from !== 'slider') slider.value = String(raiseTo);
        raiseBtn.textContent = raiseTo >= a.maxTo
          ? `All-in ${fmt(raiseTo)}` : `${verb} ${fmt(raiseTo)}`;
        raiseBtn.classList.toggle('allin', raiseTo >= a.maxTo);
      };
      input.addEventListener('input', () => sync(input.value, 'input'));
      input.addEventListener('change', () => sync(input.value));
      input.addEventListener('keydown', (e) => { if (e.key === 'Enter') raiseBtn.click(); });
      slider.addEventListener('input', () => sync(slider.value, 'slider'));
      raiseBtn.addEventListener('click', () => send('raise', { amount: raiseTo }));

      const presets = s.street === 'preflop' && a.isBet === false && a.currentBet <= s.blinds.bb
        ? [['2.5BB', Math.round(2.5 * s.blinds.bb)], ['3BB', 3 * s.blinds.bb],
           ['4BB', 4 * s.blinds.bb], ['Pot', potTo(a, 1)]]
        : [['Min', a.minTo], ['½ Pot', potTo(a, 0.5)], ['¾ Pot', potTo(a, 0.75)],
           ['Pot', potTo(a, 1)]];
      box.appendChild(h('div', { class: 'pk-presets' },
        presets.map(([label, v]) => h('button', {
          class: 'xs', onclick: () => sync(Math.max(a.minTo, Math.min(a.maxTo, v))),
        }, label)),
        h('button', { class: 'xs danger', onclick: () => sync(a.maxTo) }, 'All-in')));
      box.appendChild(h('div', { class: 'pk-sizer' }, slider, input));
      sync(raiseTo);

      box.appendChild(h('div', { class: 'pk-main-btns' },
        h('button', { class: 'pk-btn fold', onclick: () => send('fold') },
          'Fold', h('kbd', {}, 'F')),
        a.canCheck
          ? h('button', { class: 'pk-btn call', onclick: () => send('check') },
              'Check', h('kbd', {}, 'C'))
          : h('button', { class: 'pk-btn call', onclick: () => send('call') },
              `Call ${fmt(a.callAmount)}`, h('kbd', {}, 'C')),
        raiseBtn));
    } else {
      box.appendChild(h('div', { class: 'tiny muted' },
        a.toCall > 0 && a.myBet + a.toCall >= a.currentBet && a.callIsAllIn
          ? t('poker.callAllinNote')
          : t('poker.cannotRaiseNote')));
      box.appendChild(h('div', { class: 'pk-main-btns' },
        h('button', { class: 'pk-btn fold', onclick: () => send('fold') },
          'Fold', h('kbd', {}, 'F')),
        a.canCheck
          ? h('button', { class: 'pk-btn call', onclick: () => send('check') },
              'Check', h('kbd', {}, 'C'))
          : h('button', { class: 'pk-btn call', onclick: () => send('call') },
              a.callIsAllIn ? `Call all-in ${fmt(a.callAmount)}` : `Call ${fmt(a.callAmount)}`,
              h('kbd', {}, 'C'))));
    }
    return box;
  }

  function prePanel(s) {
    const info = s.seats[mySeat(s)] || {};
    const facing = s.currentBet > (info.bet || 0);
    const opts = facing
      ? [['checkfold', 'Fold'], ['callany', t('poker.preCallAny')]]
      : [['checkfold', t('poker.preCheckFold')], ['check', 'Check'], ['callany', t('poker.preCallAny')]];
    return h('div', { class: 'pk-pre' },
      h('span', { class: 'tiny muted' }, t('poker.preActionWait', { name: nameOf(s, s.actor) })),
      opts.map(([id, label]) => h('label', { class: 'pk-pre-opt' + (pre === id ? ' on' : '') },
        h('input', {
          type: 'checkbox', checked: pre === id,
          onchange: (e) => {
            pre = e.target.checked ? id : '';
            preKey = `${s.handNo}|${s.street}`;
            actionKey = '';
            renderActions(state);
          },
        }), label)));
  }

  /** Tới lượt mình mà đã đặt trước hành động thì tự gửi. */
  function runPreAction(s) {
    const a = s.act;
    if (!a || !pre) return;
    if (preKey !== `${s.handNo}|${s.street}`) { pre = ''; return; }
    const key = `${s.handNo}|${s.street}|${s.currentBet}`;
    if (autoSentKey === key) return;
    let actType = '';
    if (pre === 'checkfold') actType = a.canCheck ? 'check' : 'fold';
    else if (pre === 'callany') actType = a.canCheck ? 'check' : 'call';
    else if (pre === 'check' && a.canCheck) actType = 'check';
    pre = '';
    if (!actType) return;
    autoSentKey = key;
    setTimeout(() => net.send(CHANNEL, actType), 300);
  }

  /* ----------------------------------------------------------- phím tắt -- */
  function onKey(e) {
    if (!state || !state.act) return;
    const tag = (e.target && e.target.tagName) || '';
    if (tag === 'INPUT' && e.target.type !== 'range') return;
    if (tag === 'TEXTAREA') return;
    const a = state.act;
    const k = e.key.toLowerCase();
    if (k === 'f') net.send(CHANNEL, 'fold');
    else if (k === 'c') net.send(CHANNEL, a.canCheck ? 'check' : 'call');
    else if (k === 'r' && a.canRaise) net.send(CHANNEL, 'raise', { amount: raiseTo || a.minTo });
    else return;
    e.preventDefault();
  }
  document.addEventListener('keydown', onKey);

  /* -------------------------------------------------------------- đồng hồ */
  function tickTimer() {
    if (!state) return;
    const node = seatLayer.querySelector('.pk-seat.acting .pk-timer');
    if (state.phase === 'starting' || state.phase === 'ritvote') {
      const left = Math.max(0, Math.ceil(state.deadline - nowServer()));
      const el = banner.querySelector('.pk-count');
      if (el) el.textContent = String(left);
    }
    for (const tag of seatLayer.querySelectorAll('.pk-tag[data-out]')) {
      const left = Math.max(0, Math.ceil(Number(tag.dataset.out) - nowServer()));
      tag.textContent = t('poker.dcLeft', { s: left });
    }
    if (!node || state.phase !== 'betting') return;
    const left = Math.max(0, state.deadline - nowServer());
    const p = Math.min(1, left / (state.actionSeconds || 25));
    node.style.setProperty('--p', String(p));
    node.classList.toggle('low', left <= 7);
    const num = banner.querySelector('.pk-count');
    if (num) num.textContent = String(Math.ceil(left));
  }
  const timer = setInterval(tickTimer, 150);

  /* -------------------------------------------------------------- banner - */
  function renderBanner(s) {
    const seat = mySeat(s);
    const tour = s.tournament;
    let text = '';
    let cls = '';
    let count = false;
    if (tour && tour.stage === 'lobby') {
      text = t('poker.tourLobbyBanner', { reg: tour.registered, total: tour.seatsTotal });
      cls = 'wait';
    } else if (tour && tour.stage === 'done') {
      text = tour.champion === seat
        ? t('poker.tourChampBanner')
        : t('poker.tourOtherChampBanner', { name: nameOf(s, tour.champion) });
      cls = tour.champion === seat ? 'won' : '';
    } else if (s.phase === 'starting') {
      text = t('poker.dealingIn');
      count = true;
      cls = 'wait';
    } else if (s.status !== 'playing') {
      text = tour ? t('poker.waitReconnect') : t('poker.waitMinPlayers');
      cls = 'wait';
    } else if (s.phase === 'showdown') {
      const r = s.result;
      const mineWon = r && r.winners.includes(seat);
      text = mineWon
        ? t('poker.youWinChips', { chips: fmt(r.payouts[seat]) })
        : r
          ? t('poker.othersWinHand', { names: r.winners.map((x) => nameOf(s, x)).join(' & ') })
          : t('poker.handOver');
      cls = mineWon ? 'won' : '';
    } else if (s.phase === 'ritvote') {
      text = t('poker.ritVoteBanner');
      count = true;
      cls = 'hot';
    } else if (s.phase === 'runout') {
      text = s.rit.twice
        ? t('poker.ritRunBanner', { run: s.rit.run })
        : t('poker.allinRunout');
      cls = 'hot';
    } else if (s.actor === seat) {
      text = t('poker.yourTurnBanner');
      count = true;
      cls = 'turn';
    } else {
      text = t('poker.waitActorBanner', { name: nameOf(s, s.actor) });
      count = true;
    }
    mount(banner,
      h('span', { class: 'grow' }, text,
        count ? h('strong', { class: 'pk-count' }, '') : null, count ? 's' : ''),
      tour && tour.stage === 'running'
        ? h('span', { class: 'chip accent' }, t('poker.aliveChip', { alive: tour.alive }))
        : null,
      h('span', { class: 'chip' }, `Blinds ${fmt(s.blinds.sb)}/${fmt(s.blinds.bb)}`
        + (tour && tour.stage === 'running' ? t('poker.levelChip', { level: tour.level }) : '')));
    banner.className = 'pk-banner ' + cls;
  }

  /* ------------------------------------------------------ thông tin phòng */
  function renderRoom(s) {
    const link = `${location.origin}/#/${CHANNEL}/${s.code}`;
    mount(roomBox,
      h('div', { class: 'spread' },
        h('div', {},
          h('div', { class: 'card-title', style: { margin: '0' } }, t('room.cardTitle')),
          h('div', { class: 'room-code' }, s.code)),
        h('span', { class: 'chip accent' }, modeLabel(CHANNEL, s.mode, s.label))),
      h('button', {
        class: 'sm', onclick: async () => {
          const ok = await copyText(link);
          toast(ok ? t('room.linkCopied') : t('room.copyCodeFailed'), ok ? 'ok' : 'danger');
        },
      }, icon('copy', 14), ' ', t('poker.copyInvite')),
      s.spectators.length
        ? h('div', { class: 'tiny muted' },
            t('room.spectators', { names: s.spectators.map((p) => p.name).join(', ') }))
        : null);
  }

  /* --------------------------------------------------- bảng hạng giải đấu */
  function renderTourney(s) {
    const tour = s.tournament;
    tourCard.classList.toggle('hidden', !tour);
    if (!tour) return;
    // Người còn trong giải: xếp theo chip, nhiều nhất lên đầu.
    const alive = s.seatOrder
      .filter((seat) => s.seats[seat] && !s.seats[seat].eliminated)
      .sort((a, b) => s.seats[b].chips - s.seats[a].chips);
    // Hạng 1 là nhà vô địch — vẫn còn ghế, không nằm trong danh sách bị loại.
    const outRows = tour.placements.filter((row) => row.place !== 1)
      .sort((a, b) => a.place - b.place);
    const stage = tour.stage === 'lobby' ? t('poker.tourStageLobby')
      : tour.stage === 'done' ? t('poker.tourStageDone')
        : t('poker.tourStageAlive', { alive: tour.alive, total: outRows.length + tour.alive });
    mount(tourCard,
      h('div', { class: 'spread' },
        h('div', { class: 'card-title', style: { margin: '0' } }, t('poker.tourTitle')),
        h('span', { class: 'chip accent' }, stage)),
      tour.stage === 'running'
        ? h('div', { class: 'tiny muted' },
            t('poker.tourLevelInfo', {
              level: tour.level,
              count: tour.levelCount,
              sb: fmt(s.blinds.sb),
              bb: fmt(s.blinds.bb),
              next: tour.nextLevelIn,
            }))
        : null,
      alive.map((seat, i) => h('div', { class: 'pk-tour-row' + (i === 0 ? ' top' : '') },
        h('span', { class: 'pk-rank' }, `#${i + 1}`),
        avatar(s.seats[seat], 'sm'),
        h('span', { class: 'grow nowrap' }, s.seats[seat].name
          + (seat === mySeat(s) ? t('shell.youSuffix') : '')),
        h('strong', {}, fmt(s.seats[seat].chips)))),
      outRows.length
        ? h('div', { class: 'col', style: { gap: '2px', marginTop: '6px' } },
            h('div', { class: 'tiny muted' }, t('poker.eliminatedListTitle')),
            outRows.map((row) => h('div', { class: 'pk-tour-row out' },
              h('span', { class: 'pk-rank' }, `#${row.place}`),
              h('span', { class: 'grow nowrap' }, row.name),
              h('span', { class: 'tiny muted' }, pokerReasonLabel(row.reason)))))
        : null,
      tour.stage === 'lobby'
        ? h('div', { class: 'tiny muted' },
            t('poker.tourGraceNote', { sec: Math.round(tour.graceSeconds) }))
        : null);
  }

  /* ------------------------------------------------------------ xếp hạng */
  async function loadLeaderboard() {
    try {
      const res = await fetch('/api/poker/leaderboard');
      const data = await res.json();
      renderLeaderboard(data.board || []);
    } catch { /* không có bảng thì thôi, không ảnh hưởng ván */ }
  }
  function renderLeaderboard(rows) {
    mount(boardCard,
      h('div', { class: 'card-title', style: { margin: '0' } }, t('poker.leaderTitle')),
      rows.length
        ? rows.map((row, i) => h('div', { class: 'pk-leader-row' + (i === 0 ? ' top' : '') },
            h('span', { class: 'pk-rank' }, i === 0 ? '👑' : `#${i + 1}`),
            avatar(row, 'sm'),
            h('span', { class: 'grow nowrap' }, row.name),
            h('span', { class: 'tiny muted' }, t('poker.leaderHands', { n: row.hands })),
            h('strong', { class: row.net >= 0 ? 'pk-plus' : 'pk-minus' },
              (row.net >= 0 ? '+' : '') + fmt(row.net))))
        : h('div', { class: 'tiny muted' }, t('poker.leaderEmpty')),
      h('div', { class: 'tiny muted' }, t('poker.leaderNote')));
  }
  renderLeaderboard([]);
  loadLeaderboard();
  const boardTimer = setInterval(loadLeaderboard, 12000);

  /* ------------------------------------------------------- chat + cà khịa */
  function buildChat() {
    const log = h('div', { class: 'room-chat-log' });
    const input = h('input', { placeholder: t('poker.chatPlaceholder'), maxlength: 300 });
    const emojiPop = h('div', { class: 'emoji-pop hidden' });
    const tauntPop = h('div', { class: 'emoji-pop hidden pk-taunts' });
    const emojiWrap = h('div', { style: { position: 'relative' } },
      h('button', {
        class: 'icon ghost', type: 'button', title: 'Emoji', 'aria-label': t('chat.emojiAria'),
        onclick: (e) => {
          e.stopPropagation();
          tauntPop.classList.add('hidden');
          emojiPop.classList.toggle('hidden');
          if (!emojiPop.childElementCount) {
            for (const group of EMOJI_GROUPS) {
              emojiPop.appendChild(h('div', { class: 'emoji-group-title' }, emojiGroupName(group.name)));
              emojiPop.appendChild(h('div', { class: 'emoji-grid' },
                group.list.map((emoji) => h('button', {
                  class: 'emoji-btn', type: 'button',
                  onclick: () => { input.value += emoji; input.focus(); },
                }, emoji))));
            }
          }
        },
      }, icon('smile')),
      emojiPop);
    const tauntWrap = h('div', { style: { position: 'relative' } },
      h('button', {
        class: 'icon ghost', type: 'button', title: t('poker.quickTauntTip'), 'aria-label': t('poker.quickTauntTip'),
        onclick: (e) => {
          e.stopPropagation();
          emojiPop.classList.add('hidden');
          tauntPop.classList.toggle('hidden');
        },
      }, '😏'),
      tauntPop);
    const form = h('form', {
      class: 'row', style: { gap: '4px' },
      onsubmit: (e) => {
        e.preventDefault();
        const text = input.value.trim();
        if (!text) return;
        net.send(CHANNEL, 'say', { text });
        input.value = '';
        emojiPop.classList.add('hidden');
      },
    }, input, emojiWrap, tauntWrap,
      h('button', { class: 'icon', type: 'submit', title: t('chat.send'), 'aria-label': t('chat.send') },
        icon('send', 16)));
    const quick = h('div', { class: 'pk-quick-emoji' },
      ['😂', '🔥', '😏', '🤡', '😱', '👏', '🙏', '💸'].map((emoji) => h('button', {
        class: 'emoji-btn', type: 'button', title: t('poker.sendEmojiTip', { emoji }),
        onclick: () => net.send(CHANNEL, 'say', { text: emoji }),
      }, emoji)));
    const card = h('div', { class: 'card tight room-chat' },
      h('div', { class: 'card-title', style: { marginBottom: '6px' } }, t('poker.chatTitle')),
      log, quick, form);
    const away = (e) => {
      if (!emojiWrap.contains(e.target)) emojiPop.classList.add('hidden');
      if (!tauntWrap.contains(e.target)) tauntPop.classList.add('hidden');
    };
    document.addEventListener('click', away);

    function update(s) {
      if (!tauntPop.childElementCount) {
        s.taunts.forEach((text, id) => tauntPop.appendChild(h('button', {
          class: 'pk-taunt', type: 'button',
          onclick: () => { net.send(CHANNEL, 'taunt', { id }); tauntPop.classList.add('hidden'); },
        }, tauntLabel(text))));
      }
      const stick = log.scrollHeight - log.scrollTop - log.clientHeight < 30;
      clear(log);
      for (const entry of s.chat) {
        if (entry.kind === 'system') {
          log.appendChild(h('div', { class: 'sys' }, entry.text));
          continue;
        }
        log.appendChild(h('div', { class: entry.kind === 'taunt' ? 'pk-chat-taunt' : '' },
          h('span', { style: { color: entry.color || 'var(--accent-soft)', fontWeight: '650' } },
            entry.name + ': '),
          entry.kind === 'taunt' ? tauntLabel(entry.text) : entry.text));
      }
      if (stick) log.scrollTop = log.scrollHeight;
    }
    return { card, update, dispose: () => document.removeEventListener('click', away) };
  }

  /* ------------------------------------------------------------- vẽ lại -- */
  function renderAll() {
    const s = state;
    if (!s) return;
    const seats = ring(s);
    const spots = SPOTS[seats.length] || SPOTS[6];
    clear(seatLayer);
    clear(betLayer);
    const bets = {};
    seats.forEach((seat, i) => {
      seatLayer.appendChild(seatNode(s, seat, spots[i]));
      const bet = betNode(s, seat, spots[i]);
      if (bet) betLayer.appendChild(bet);
      bets[seat] = (s.seats[seat] || {}).bet || 0;
    });
    prevBets = bets;
    mount(centerBox, centerNode(s));
    renderBanner(s);
    renderHero(s);
    renderActions(s);
    renderRoom(s);
    renderTourney(s);
    chatCard.update(s);
    mount(feedBox, [...s.feed].reverse().map((entry) => h('div', {
      class: 'feed-row' + (entry.tone ? ' tone-' + entry.tone : ''),
    }, entry.text)));
    ctx.setTopbar(...roomTopbar(ctx, s, CHANNEL, t('poker.shortTitle')));
    tickTimer();
  }

  function react(s) {
    const seat = mySeat(s);
    if (s.actor === seat && seat && s.phase === 'betting' && prevActor !== seat) {
      sfx.move();
      raiseTo = 0;
    }
    if (s.phase === 'showdown' && prevPhase !== 'showdown') {
      if (s.result && s.result.winners.includes(seat)) sfx.win();
      else sfx.hit();
      setTimeout(loadLeaderboard, 400);
    }
    if (s.phase === 'runout' && prevPhase !== 'runout') sfx.hit();
    const stage = (s.tournament && s.tournament.stage) || '';
    if (stage !== prevStage) {
      if (stage === 'running') sfx.message();
      if (stage === 'done') {
        if (s.tournament.champion === seat) sfx.win();
        else sfx.hit();
      }
      prevStage = stage;
      actionKey = '';           // đổi giai đoạn giải: vẽ lại bảng điều khiển
    }
    if (s.handNo !== prevHand) { pre = ''; raiseTo = 0; }
    if (s.chat.length > lastChatCount && lastChatCount) {
      const last = s.chat[s.chat.length - 1];
      if (last.kind === 'taunt') sfx.message();
    }
    lastChatCount = s.chat.length;
    prevActor = s.actor;
    prevPhase = s.phase;
    prevHand = s.handNo;
  }

  /* --------------------------------------------------------------- mạng -- */
  const stop = net.on(CHANNEL, (msg) => {
    if (msg.t === 'state') {
      if (msg.now) clockSkew = msg.now - Date.now() / 1000;
      state = msg;
      react(msg);
      renderAll();
      runPreAction(msg);
    } else if (msg.t === 'error') {
      toast(msg.message, 'danger');
      actionKey = '';
      if (state) renderActions(state);
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
    clearInterval(timer);
    clearInterval(boardTimer);
    clearInterval(bubbleSweep);
    chatCard.dispose();
    document.removeEventListener('keydown', onKey);
    net.send(CHANNEL, 'leave');
  };
}

/* Sòng Bịp — bàn chơi.
 *
 * Bố cục: bàn nỉ hình bầu dục, tối đa bốn chỗ quanh rìa, quân chủ và chồng quân
 * úp ở giữa, tay quân của mình xoè ở đáy màn hình. Chỗ của CHÍNH MÌNH luôn được
 * kéo xuống cạnh dưới, bất kể server gán ghế nào — ngồi ở bàn thật thì mình
 * luôn là người ngồi gần nhất.
 *
 * Server đẩy pha theo mốc thời gian (turn -> reveal -> aim -> shot), nên view
 * này KHÔNG tự bấm giờ cho diễn biến. Nó chỉ:
 *   - đếm lùi đồng hồ lượt (hiệu deadline - now của server, để lệch giờ máy
 *     khách không làm sai đồng hồ);
 *   - chạy animation cho đúng pha đang nhận được;
 *   - nhớ pha trước để biết lúc nào là "vừa mới chuyển", vì gói state được phát
 *     lại nhiều lần trong cùng một pha (ai nhắn tin trong phòng cũng phát lại).
 */

import { avatar, clear, h, icon, mount } from '../dom.js';
import { getLang, rankNameI18n, seatLabelI18n, t, tauntLabel } from '../i18n.js';
import { confirmBox, sfx, toast } from '../ui.js';
import { cardBack, cardFace, rankName, tableCard } from '../cards.js';
import { bloodSplatter, chamberStrip, revolver } from '../revolver.js';
import { renderLobby, roomCard, roomChat, roomTopbar } from './gameroom.js';

const CHANNEL = 'bluff';

/** Quân Ma Vương. Trùng hằng DEVIL ở bluff.py — đổi một bên phải đổi cả hai. */
const DEVIL = 'DEVIL';

/** Bốn chỗ quanh bàn, tính theo phần trăm khung bàn. Chỗ 0 là của mình.
 *
 * ``at`` cho biết toạ độ neo theo CẠNH nào của chỗ ngồi thay vì theo tâm (mặc
 * định là tâm). Cần thiết vì bàn co giãn theo bề ngang còn chỗ ngồi cao cố định
 * (~160px): neo theo tâm thì trên màn hình hẹp, chỗ ngồi rìa bị ``overflow:
 * hidden`` của mặt nỉ cắt mất đầu. Neo theo cạnh thì không bao giờ bị cắt, bất
 * kể bàn to nhỏ ra sao.
 */
const SPOTS = {
  2: [{ x: 50, y: 99, self: true, at: 'bottom' },
      { x: 50, y: 2, at: 'top' }],
  3: [{ x: 50, y: 99, self: true, at: 'bottom' },
      { x: 3, y: 34, at: 'left' }, { x: 97, y: 34, at: 'right' }],
  4: [{ x: 50, y: 99, self: true, at: 'bottom' },
      { x: 2, y: 46, at: 'left' }, { x: 50, y: 2, at: 'top' },
      { x: 98, y: 46, at: 'right' }],
};

export default {
  async mount(root, ctx, param) {
    if (!param) {
      return renderLobby(root, ctx, CHANNEL, {
        title: t('bluff.title'),
        blurb: t('bluff.blurb'),
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
  let picked = new Set();          // id quân đang chọn trên tay
  let clockSkew = 0;               // giờ server − giờ máy này
  let prevPhase = '';
  let prevRound = -1;
  let tauntOpen = false;
  let revealTimers = [];

  const tableBox = h('div', { class: 'bluff-table' });
  const centerBox = h('div', { class: 'bluff-center' });
  const banner = h('div', { class: 'bluff-banner', role: 'status', 'aria-live': 'polite' },
    t('shell.connecting'));
  const handBox = h('div', { class: 'bluff-hand' });
  const handBar = h('div', { class: 'bluff-handbar' });
  const feedBox = h('div', { class: 'bluff-feed' });
  const side = h('div', { class: 'col bluff-side' });
  const stage = h('div', { class: 'bluff-stage' });

  tableBox.appendChild(centerBox);

  mount(root,
    h('div', { class: 'bluff-layout' },
      h('div', { class: 'bluff-main' },
        banner,
        h('div', { class: 'bluff-felt' }, tableBox, stage),
        // Tay quân + nút hành động gom một khối để CSS giữ nó dính đáy màn
        // hình: màn thấp phải cuộn xem bàn thì vẫn luôn thấy quân của mình.
        h('div', { class: 'bluff-dock' }, handBox, handBar)),
      h('div', { class: 'col bluff-rail' }, feedBox, side)));

  /* --------------------------------------------------------- tra cứu nhỏ -- */
  /** Tên hiển thị của một ghế, lùi về nhãn ghế nếu chỗ đó đã trống. */
  function nameOf(s, seat) {
    return (s.seats[seat] && s.seats[seat].name) || seatLabelI18n(s.seatLabels[seat]) || seat;
  }

  /** Mọi người phải bắn ở lượt đối chất này, theo thứ tự bắn.
   *
   * ``losers`` là khoá mới; lùi về ``loser`` để phòng đang chạy lúc server vừa
   * nâng cấp không vỡ giao diện.
   */
  function shooters(s) {
    const ch = s.challenge;
    if (!ch) return [];
    if (ch.losers && ch.losers.length) return ch.losers;
    return ch.loser ? [ch.loser] : [];
  }

  /* ------------------------------------------------- thứ tự chỗ trên bàn -- */
  /** Xoay danh sách ghế để ghế của mình xuống chỗ dưới cùng. */
  function seatRing(s) {
    const order = s.seatOrder || [];
    const mine = s.you.mark;
    const start = mine ? order.indexOf(mine) : 0;
    const from = start < 0 ? 0 : start;
    return order.map((_, i) => order[(from + i) % order.length]);
  }

  function seatUser(info) {
    if (!info) return null;
    if (info.bot || info.avatar) return info;
    const fallback = info.uid === ctx.me.uid
      ? ctx.me.avatar
      : ctx.directory?.[info.uid]?.avatar;
    return fallback ? { ...info, avatar: fallback } : info;
  }

  /* --------------------------------------------------------- một chỗ ngồi -- */
  function seatNode(s, seat, spot) {
    const info = s.seats[seat];
    const mine = seat === (s.you.mark);
    const turn = s.phase === 'turn' && s.turn === seat;
    const dead = info ? !info.alive : false;
    // Cú Ma Vương đẩy nhiều người vào tầm súng một lúc, nên phải soi cả danh
    // sách chứ không chỉ người đầu tiên.
    const target = shooters(s).includes(seat)
      && ['reveal', 'aim', 'shot'].includes(s.phase);
    const accused = s.challenge && s.challenge.accused === seat && s.phase !== 'turn';
    const caller = s.challenge && s.challenge.caller === seat && s.phase !== 'turn';

    const node = h('div', {
      class: 'bluff-seat'
        + (mine ? ' me' : '') + (turn ? ' turn' : '') + (dead ? ' dead' : '')
        + (target ? ' target' : '') + (accused ? ' accused' : '')
        + (caller ? ' caller' : '')
        + (spot.at ? ' at-' + spot.at : '')
        + (spot.self ? ' bottom' : ''),
      style: { left: spot.x + '%', top: spot.y + '%' },
      dataset: { seat },
    });

    if (!info) {
      node.appendChild(h('div', { class: 'seat-empty' }, icon('users', 18)));
      node.appendChild(h('div', { class: 'seat-name muted' }, t('room.emptySeat')));
      node.appendChild(h('div', { class: 'tiny muted' }, seatLabelI18n(s.seatLabels[seat])));
      return node;
    }

    // Quân trên tay người khác: chỉ hiện số, vẽ tối đa 5 mặt sau xếp chồng.
    const fan = h('div', { class: 'seat-fan' });
    if (!spot.self) {
      const count = Math.min(info.cards, 5);
      for (let i = 0; i < count; i++) {
        const back = cardBack({ size: 26 });
        back.style.setProperty('--i', String(i));
        fan.appendChild(back);
      }
      if (!info.cards) fan.appendChild(h('span', { class: 'tiny muted' }, t('bluff.outOfCards')));
    }

    node.appendChild(h('div', { class: 'seat-face' },
      avatar(seatUser(info), 'lg'),
      turn ? h('span', { class: 'seat-ring' }) : null,
      dead ? h('span', { class: 'seat-skull', title: info.cause || t('bluff.eliminated') }, '💀') : null,
      info.bot ? h('span', { class: 'seat-bot', title: t('bluff.botTitle') }, '🤖') : null));

    node.appendChild(h('div', { class: 'seat-name nowrap' },
      info.name + (mine ? t('shell.youSuffix') : '')));
    node.appendChild(chamberStrip(info.shots, info.chambers, { dead }));
    node.appendChild(h('div', { class: 'seat-meta' },
      dead
        ? h('span', { class: 'tiny danger-text' }, info.cause || t('bluff.eliminated'))
        : h('span', { class: 'tiny muted' },
            t('bluff.cardsAndLeft', { cards: info.cards, left: info.left }))));
    const taunt = (s.taunts || {})[seat];
    if (taunt && taunt.text) {
      node.appendChild(h('div', {
        class: 'bluff-taunt-bubble',
        dataset: { tid: String(taunt.id || '') },
      }, tauntLabel(taunt.text)));
    }
    if (!spot.self) node.appendChild(fan);
    return node;
  }

  /* ------------------------------------------------------- giữa bàn ------- */
  function centerNode(s) {
    const box = h('div', { class: 'bluff-center-inner' });
    const devilName = s.devilName ? rankNameI18n(DEVIL) : rankNameI18n(DEVIL);

    box.appendChild(h('div', { class: 'table-card' },
      tableCard(s.tableRank, { size: 96 }),
      h('div', { class: 'table-card-label' },
        h('span', { class: 'tiny muted' }, t('bluff.tableRankLabel')),
        h('strong', {}, rankName(s.tableRank)),
        // Vòng này có Ma Vương hay không là thông tin công khai, và là thứ đổi
        // hẳn cách chơi, nên nó phải nằm ngay cạnh quân chủ chứ không nhét vào
        // mục luật. Kèm luôn "5 con" để người chơi đếm quân không lệch.
        s.devilRank
          ? h('span', { class: 'devil-badge', title: t('bluff.devilBadgeTitle') },
              '☠ ', h('strong', {}, devilName),
              h('span', { class: 'tiny' },
                t('bluff.devilLeftRank', {
                  n: (s.deckCount || {})[s.tableRank],
                  rank: rankName(s.tableRank),
                })))
          : s.devilMode
            ? h('span', { class: 'tiny muted' }, t('bluff.noDevilThisRound'))
            : null)));

    // Chồng quân úp giữa bàn: mỗi lượt một cọc nhỏ, lệch nhau cho thấy có mấy lượt.
    const pileTotal = s.pile.reduce((sum, p) => sum + p.count, 0);
    const pile = h('div', { class: 'bluff-pile' });
    s.pile.slice(-6).forEach((play, index) => {
      const stack = h('div', { class: 'pile-stack', style: { '--k': String(index) } });
      for (let i = 0; i < play.count; i++) {
        const back = cardBack({ size: 30 });
        back.style.setProperty('--i', String(i));
        stack.appendChild(back);
      }
      pile.appendChild(stack);
    });
    if (pileTotal) {
      box.appendChild(pile);
      box.appendChild(h('div', { class: 'tiny muted' }, t('bluff.pileTotal', { n: pileTotal })));
    } else {
      box.appendChild(h('div', { class: 'tiny muted' }, t('bluff.pileEmpty')));
    }

    if (s.lastPlay) {
      const who = s.seats[s.lastPlay.seat];
      box.appendChild(h('div', { class: 'bluff-claim' },
        h('strong', {}, who ? who.name : seatLabelI18n(s.seatLabels[s.lastPlay.seat])),
        t('bluff.claimPrefix'),
        h('span', { class: 'claim-count' }, String(s.lastPlay.count)),
        t('bluff.claimUnit'),
        h('span', { class: 'claim-rank' }, rankName(s.tableRank))));
    }
    return box;
  }

  /* --------------------------------------------- lật quân khi có người hô -- */
  function revealNode(s) {
    const ch = s.challenge;
    if (!ch) return null;
    const list = shooters(s);
    const devilName = rankNameI18n(DEVIL);
    // Ma Vương là kết cục thứ BA, không phải một kiểu "bịp": người bị hô thắng.
    // Nên nó có lớp riêng, không dùng lại was-lie.
    const kind = ch.devil ? ' was-devil' : (ch.truthful ? ' was-truth' : ' was-lie');

    const verdict = ch.devil
      ? t('bluff.devilVerdict', {
          devil: devilName,
          accused: nameOf(s, ch.accused),
          targets: list.length > 1 ? t('bluff.allNTargets', { n: list.length }) : nameOf(s, list[0] || ''),
        })
      : ch.truthful
        ? t('bluff.truthVerdict', { caller: nameOf(s, ch.caller) })
        : t('bluff.lieVerdict', { accused: nameOf(s, ch.accused) });

    const verdictDelay = (ch.cards.length * 0.6).toFixed(2) + 's';
    return h('div', { class: 'reveal-box' + kind, style: { '--vd': verdictDelay } },
      h('div', { class: 'reveal-head' },
        h('strong', {}, nameOf(s, ch.caller)),
        t('bluff.callHeader'),
        h('strong', {}, nameOf(s, ch.accused))),
      h('div', { class: 'reveal-cards' },
        ch.cards.map((card, index) => {
          const tone = card.devil ? ' devil' : (card.truth ? ' truth' : ' lie');
          return h('div', {
            class: 'reveal-card' + tone,
            style: { '--d': (index * 0.6).toFixed(2) + 's' },
          }, cardFace(card.rank, { size: 84 }),
            h('span', { class: 'reveal-tag' },
              card.devil ? '☠ ' + devilName : card.truth ? t('bluff.tagTruth') : t('bluff.tagLie')));
        })),
      h('div', { class: 'reveal-verdict delayed' }, verdict),
      // Hàng người phải bắn. Hiện đủ cả hàng ngay từ pha lật quân: biết trước
      // mình đứng thứ mấy trong hàng chính là chỗ nghẹt thở của cú Ma Vương.
      h('div', { class: 'reveal-loser delayed' },
        list.length
          ? list.map((seat, index) => h('span', { class: 'shoot-chip' },
              s.seats[seat] ? avatar(seatUser(s.seats[seat]), 'sm') : null,
              h('span', {}, nameOf(s, seat)),
              list.length > 1
                ? h('span', { class: 'shoot-order' }, `#${index + 1}`)
                : null))
          : h('span', {}, t('bluff.noShooters'))));
  }

  /* ----------------------------------------- sân khấu: ổ đạn và phát súng -- */
  function stageNode(s) {
    const phase = s.phase;
    if (phase === 'turn' || phase === 'over') return null;

    const ch = s.challenge;
    // ``firing`` là người đang bị kề súng NGAY BÂY GIỜ. Với cú Ma Vương thì
    // hàng có nhiều người và server bắn lần lượt, nên không được dùng
    // challenge.loser (người đầu hàng) cho pha aim/shot.
    const loserSeat = s.firing || (s.shot && s.shot.seat) || (ch && ch.loser) || '';
    const loser = s.seats[loserSeat];
    const info = loser || {};
    const waiting = (s.pending || []).filter((seat) => s.seats[seat] && s.seats[seat].alive);

    if (phase === 'reveal') {
      return h('div', { class: 'bluff-stage-inner reveal' }, revealNode(s));
    }

    const used = s.shot ? s.shot.chamber : (info.shots || 0);
    const gun = revolver({ used, size: 340 });
    const queueNote = waiting.length
      ? h('div', { class: 'stage-queue' },
          t('bluff.queueNote', {
            n: waiting.length,
            names: waiting.map((seat) => nameOf(s, seat)).join(', '),
          }))
      : null;

    if (phase === 'aim') {
      const left = Math.max(1, (info.chambers || 6) - used);
      return h('div', { class: 'bluff-stage-inner aim' },
        h('div', { class: 'stage-who' },
          loser ? avatar(seatUser(loser), 'lg') : null,
          h('div', {},
            h('strong', {}, loser ? loser.name : loserSeat),
            h('div', { class: 'tiny muted' },
              t('bluff.aimMeta', {
                chamber: used + 1,
                left,
                pct: Math.round(100 / left),
              })))),
        h('div', { class: 'gun-wrap spinning' }, gun),
        h('div', { class: 'stage-caption' }, t('bluff.spinning')),
        queueNote);
    }

    // phase === 'shot'
    const died = s.shot && s.shot.result === 'death';
    return h('div', {
      class: 'bluff-stage-inner shot ' + (died ? 'death' : 'blank'),
    },
      died ? bloodSplatter() : null,
      h('div', { class: 'stage-who' + (died ? ' gone' : '') },
        loser ? avatar(seatUser(loser), 'lg') : null,
        h('div', {},
          h('strong', {}, loser ? loser.name : loserSeat),
          h('div', { class: 'tiny muted' }, died ? t('bluff.shotHit') : t('bluff.shotBlank')))),
      h('div', { class: 'gun-wrap ' + (died ? 'fired' : 'clicked') }, gun),
      h('div', { class: 'stage-verdict' }, died ? t('bluff.bang') : t('bluff.clickBlank')),
      h('div', { class: 'stage-caption' }, died
        ? t('bluff.diedCaption', { name: loser ? loser.name : '' })
        : t('bluff.livedCaption', {
            left: s.shot ? s.shot.left : '?',
            pct: s.shot ? Math.round(s.shot.odds * 100) : '?',
          })),
      queueNote);
  }

  /* -------------------------------------------------------- tay quân ------ */
  function renderHand(s) {
    clear(handBox);
    const myTurn = s.phase === 'turn' && s.turn === (s.you.mark);
    if (!s.you.mark) {
      handBox.appendChild(h('div', { class: 'tiny muted' },
        t('bluff.spectatingHand')));
      return;
    }
    if (!s.hand.length) {
      handBox.appendChild(h('div', { class: 'hand-empty' },
        t('bluff.handEmptySkip')));
      return;
    }
    const devilName = rankNameI18n(DEVIL);
    const byId = new Map(s.hand.map((card) => [card.id, card]));
    const devilPicked = [...picked].some((id) => (byId.get(id) || {}).rank === DEVIL);

    s.hand.forEach((card, index) => {
      const on = picked.has(card.id);
      const isDevil = card.rank === DEVIL;
      // Phần cong của nan quạt cần |offset|, mà CSS abs() mới chỉ có ở Chrome
      // rất gần đây — tính sẵn ở đây rồi đưa xuống CSS bằng biến.
      const offset = index - (s.hand.length - 1) / 2;
      const btn = h('button', {
        class: 'hand-card' + (on ? ' picked' : '')
          + (isDevil ? ' is-devil' : '')
          // Ma Vương đi một mình, nên khi nó đang được chọn thì mọi quân khác
          // hết cửa, và ngược lại. Làm mờ thay vì khoá hẳn: bấm vào vẫn ĐỔI
          // được sang quân đó, khoá lại thì người chơi phải bỏ chọn hai lần.
          + ((devilPicked && !isDevil) || (isDevil && picked.size && !on)
            ? ' blocked' : ''),
        style: {
          '--tilt': (offset * 3.2).toFixed(2) + 'deg',
          '--lift': (Math.abs(offset) * 3).toFixed(1) + 'px',
        },
        disabled: !myTurn || s.forcedLiar,
        'aria-pressed': String(on),
        title: isDevil ? t('bluff.devilSoloTitle', { devil: devilName }) : rankName(card.rank),
        onclick: () => {
          if (on) {
            picked.delete(card.id);
          } else if (isDevil) {
            // Chọn Ma Vương thì gạt sạch phần đang chọn, không báo lỗi: người
            // chơi vừa nói rõ họ muốn đánh quân này.
            if (picked.size) toast(t('bluff.devilAutoToast', { devil: devilName }), 'ok');
            picked = new Set([card.id]);
          } else if (devilPicked) {
            toast(t('bluff.devilDropToast', { devil: devilName }), 'ok');
            picked = new Set([card.id]);
          } else {
            if (picked.size >= s.maxPlay) {
              toast(t('bluff.maxPlayErr', { max: s.maxPlay }), 'danger');
              return;
            }
            picked.add(card.id);
          }
          sfx.move();
          renderHand(s);
          renderHandBar(s);
        },
      }, cardFace(card.rank, { size: 84 }));
      handBox.appendChild(btn);
    });
  }

  function renderHandBar(s) {
    clear(handBar);
    const mySeat = s.you.mark;
    const myTurn = s.phase === 'turn' && s.turn === mySeat;
    const alive = s.seats[mySeat] ? s.seats[mySeat].alive : false;

    if (!s.you.mark) {
      handBar.appendChild(h('button', {
        class: 'primary', onclick: () => net.send(CHANNEL, 'sit'),
      }, t('bluff.sitBtn')));
      return;
    }
    if (!alive && s.status === 'playing') {
      handBar.appendChild(h('span', { class: 'chip danger' }, t('bluff.deadChip')));
      handBar.appendChild(h('span', { class: 'tiny muted' },
        t('bluff.deadWait')));
      return;
    }

    const canCall = myTurn && s.lastPlay && s.lastPlay.seat !== mySeat;
    const count = picked.size;
    const devilName = rankNameI18n(DEVIL);
    const byId = new Map(s.hand.map((card) => [card.id, card]));
    const devilPicked = [...picked].some((id) => (byId.get(id) || {}).rank === DEVIL);

    if (myTurn && !s.forcedLiar) {
      handBar.appendChild(h('button', {
        class: 'primary bluff-place' + (devilPicked ? ' devil' : ''), disabled: !count,
        onclick: () => {
          net.send(CHANNEL, 'play', { cards: [...picked] });
          picked = new Set();
        },
      }, count
        // Lời khai KHÔNG đổi khi đặt Ma Vương: vẫn úp xuống và khai là quân chủ,
        // nếu không thì bàn biết ngay và cú phản đòn mất hết ý nghĩa. Chỉ ghi
        // thêm cho CHÍNH người đặt biết họ đang cầm gì trong tay.
        ? t('bluff.placeCount', { count, rank: rankName(s.tableRank) })
          + (devilPicked ? t('bluff.devilPlaceHint', { devil: devilName }) : '')
        : t('bluff.pickCards')));
    }
    if (devilPicked) {
      handBar.appendChild(h('span', { class: 'tiny devil-hint' },
        t('bluff.devilPlayTip', { rank: rankName(s.tableRank) })));
    }
    if (canCall) {
      handBar.appendChild(h('button', {
        class: 'danger bluff-call' + (s.forcedLiar ? ' pulse' : ''),
        onclick: () => {
          picked = new Set();
          net.send(CHANNEL, 'liar');
        },
      }, t('bluff.callLiarBtn')));
    }
    if (s.forcedLiar && myTurn) {
      handBar.appendChild(h('span', { class: 'tiny warn-text' },
        t('bluff.forcedLiarTip')));
    }
    if (count) {
      handBar.appendChild(h('button', {
        class: 'ghost sm', onclick: () => { picked = new Set(); renderAll(); },
      }, t('bluff.clearPick')));
    }

    if (s.status === 'finished') {
      const voted = s.rematch.includes(mySeat);
      handBar.appendChild(h('button', {
        class: 'primary', disabled: voted,
        onclick: () => net.send(CHANNEL, 'rematch'),
      }, voted
        ? t('bluff.rematchWait', { n: s.rematch.length, total: s.seatOrder.length })
        : t('bluff.playAgain')));
    }
    if (s.status === 'playing' && alive) {
      const choices = s.tauntChoices || [];
      if (choices.length) {
        handBar.appendChild(h('button', {
          class: 'sm ghost' + (tauntOpen ? ' active' : ''),
          onclick: () => { tauntOpen = !tauntOpen; renderHandBar(s); },
        }, t('bluff.tauntBtn')));
      }
      handBar.appendChild(h('button', {
        class: 'ghost sm',
        onclick: async () => {
          if (await confirmBox({
            title: t('bluff.resignTitle'),
            body: t('bluff.resignBody'),
            okText: t('bluff.resignOk'), danger: true,
          })) net.send(CHANNEL, 'resign');
        },
      }, icon('flag', 14), ' ', t('bluff.resignOk')));
      if (tauntOpen && choices.length) {
        handBar.appendChild(h('div', { class: 'bluff-taunt-tray' },
          choices.map((txt) => h('button', {
            class: 'xs ghost',
            onclick: () => {
              net.send(CHANNEL, 'taunt', { text: txt });
              tauntOpen = false;
              renderHandBar(s);
            },
          }, tauntLabel(txt)))));
      }
    }
  }

  /* ---------------------------------------------------------- đồng hồ ----- */
  const clockLabel = h('span', { class: 'bluff-clock-num' }, '');
  const clockRing = h('span', { class: 'bluff-clock-ring' });
  const clock = h('div', { class: 'bluff-clock hidden' }, clockRing, clockLabel);

  function tickClock() {
    if (!state || state.phase !== 'turn' || !state.deadline) {
      clock.classList.add('hidden');
      return;
    }
    const left = Math.max(0, state.deadline - (Date.now() / 1000 + clockSkew));
    clock.classList.remove('hidden');
    clock.classList.toggle('low', left <= 6);
    clockLabel.textContent = String(Math.ceil(left));
    clockRing.style.setProperty('--p', String(Math.min(1, left / 30)));
  }
  const clockTimer = setInterval(tickClock, 200);

  /* ------------------------------------------------------------ vẽ lại ---- */
  function bannerText(s) {
    const mySeat = s.you.mark;
    const seatName = (seat) => (s.seats[seat] ? s.seats[seat].name : seatLabelI18n(s.seatLabels[seat]));

    if (s.status === 'waiting') {
      const need = s.seatOrder.filter((seat) => !s.seats[seat]).length;
      return { text: t('bluff.waitNeed', { need }), cls: 'wait' };
    }
    if (s.status === 'finished') {
      if (s.winner === mySeat) return { text: t('bluff.youSurvived'), cls: 'won' };
      if (!s.winner || s.winner === 'draw') return { text: t('bluff.emptyTable'), cls: '' };
      return { text: t('bluff.winnerName', { name: seatName(s.winner) }), cls: 'lost' };
    }
    const queued = (s.pending || []).length;
    const tail = queued ? t('bluff.stillMoreShooters', { n: queued }) : '';
    if (s.phase === 'reveal') {
      const ch = s.challenge;
      return ch && ch.devil
        ? {
            text: t('bluff.devilRevealBanner', {
              devil: rankNameI18n(DEVIL),
              n: shooters(s).length,
            }),
            cls: 'hot',
          }
        : { text: t('bluff.revealingBanner'), cls: 'hot' };
    }
    if (s.phase === 'aim') {
      return { text: t('bluff.aimBanner', { name: seatName(s.firing) }) + tail, cls: 'hot' };
    }
    if (s.phase === 'shot') {
      return s.shot && s.shot.result === 'death'
        ? { text: t('bluff.deathBanner', { name: seatName(s.shot.seat) }) + tail, cls: 'lost' }
        : { text: t('bluff.blankBanner') + tail, cls: 'won' };
    }
    if (s.turn === mySeat) {
      return {
        text: s.forcedLiar
          ? t('bluff.forcedLiarBanner')
          : t('bluff.yourTurnBanner', { rank: rankName(s.tableRank) }),
        cls: 'turn',
      };
    }
    return { text: t('bluff.waitTurnBanner', { name: seatName(s.turn) }), cls: 'wait' };
  }

  function renderAll() {
    const s = state;
    if (!s) return;
    const ring = seatRing(s);
    const spots = SPOTS[ring.length] || SPOTS[4];

    // Chỗ ngồi: vẽ lại toàn bộ, tối đa 4 chỗ nên không cần tối ưu từng ô.
    for (const old of [...tableBox.querySelectorAll('.bluff-seat')]) old.remove();
    ring.forEach((seat, index) => {
      tableBox.appendChild(seatNode(s, seat, spots[index] || spots[0]));
    });
    mount(centerBox, centerNode(s));

    const stageInner = stageNode(s);
    if (stageInner) {
      mount(stage, stageInner);
      stage.classList.add('on');
    } else {
      clear(stage);
      stage.classList.remove('on');
    }

    const info = bannerText(s);
    mount(banner,
      h('span', { class: 'bluff-round' }, s.round ? t('bluff.roundNum', { round: s.round }) : ''),
      h('span', { class: 'grow' }, info.text),
      clock);
    banner.className = 'bluff-banner ' + info.cls;
    tickClock();

    renderHand(s);
    renderHandBar(s);

    // Diễn biến. Mới nhất lên đầu để không phải cuộn.
    mount(feedBox,
      h('div', { class: 'card-title', style: { margin: '0 0 6px' } }, t('bluff.feedTitle')),
      h('div', { class: 'feed-list' },
        [...s.feed].reverse().map((entry) => h('div', {
          class: 'feed-row' + (entry.tone ? ' tone-' + entry.tone : ''),
        }, entry.text))));

    mount(side, roomCard(s, CHANNEL, rulesCard(s)), roomChat(s, net, CHANNEL));
    ctx.setTopbar(...roomTopbar(ctx, s, CHANNEL, t('bluff.title')));
  }

  function rulesCard(s) {
    const devilName = rankNameI18n(DEVIL);
    const counts = s.deckCount || {};
    // Thành phần bộ quân của ĐÚNG vòng này. Ở chế độ Ma Vương nó đổi theo quân
    // chủ, mà đếm quân là phần lõi của game nên không được để người chơi tự đoán.
    const deckLine = ['DRAGON', 'PHOENIX', 'TIGER', 'DEMON', DEVIL]
      .filter((rank) => counts[rank])
      .map((rank) => `${counts[rank]} ${rankName(rank)}`)
      .join(' · ');

    return h('details', { class: 'bluff-rules' },
      h('summary', {}, t('bluff.rulesSummary')),
      h('ul', {},
        h('li', {}, t('bluff.rule1a'),
          h('strong', {}, t('bluff.rule1b')), t('bluff.rule1c')),
        h('li', {}, t('bluff.rule2', { rank: rankName(s.tableRank) })),
        h('li', {}, h('strong', {}, t('bluff.rule3a')), t('bluff.rule3b')),
        h('li', {}, t('bluff.rule4')),
        s.devilMode
          ? h('li', { class: 'rule-devil' },
              h('strong', {}, devilName), t('bluff.rule5_devil_a'),
              h('strong', {}, t('bluff.rule5_devil_b')), t('bluff.rule5_devil_c'),
              h('strong', {}, t('bluff.rule5_devil_d')), t('bluff.rule5_devil_e'),
              h('strong', {}, t('bluff.rule5_devil_f')), t('bluff.rule5_devil_g'),
              h('strong', {}, t('bluff.rule5_devil_h')), t('bluff.rule5_devil_i'))
          : null,
        s.devilMode
          ? h('li', { class: 'tiny muted' },
              t('bluff.rule5_2p', { devil: devilName }))
          : null,
        h('li', {}, t('bluff.rule6a'),
          h('strong', {}, t('bluff.rule6b')), t('bluff.rule6c')),
        h('li', {}, t('bluff.rule7')),
        deckLine
          ? h('li', { class: 'tiny muted' }, t('bluff.deckLine', { line: deckLine }))
          : null));
  }

  /* ----------------------------------------------------- âm thanh & rung -- */
  function clearRevealTimers() {
    for (const id of revealTimers) clearTimeout(id);
    revealTimers = [];
  }

  function reactToPhase(s) {
    if (s.phase === prevPhase && s.round === prevRound) return;

    if (s.phase === 'reveal' && prevPhase === 'turn') {
      clearRevealTimers();
      sfx.hit();
      const cards = (s.challenge && s.challenge.cards) || [];
      cards.forEach((card, idx) => {
        revealTimers.push(setTimeout(() => {
          if (card.devil || !card.truth) sfx.hit();
          else sfx.move();
        }, idx * 600));
      });
      // Ma Vương lộ diện là khoảnh khắc to nhất của chế độ này — cho nó cùng
      // độ rung với một phát đạn, dù chưa ai bắn.
      if (s.challenge && s.challenge.devil) {
        revealTimers.push(setTimeout(() => {
          root.classList.add('shake');
          setTimeout(() => root.classList.remove('shake'), 700);
        }, Math.max(0, (cards.length - 1) * 600)));
      }
    } else if (s.phase === 'aim' && prevPhase !== 'aim') {
      clearRevealTimers();
      sfx.miss();
    } else if (s.phase === 'shot' && prevPhase !== 'shot') {
      if (s.shot && s.shot.result === 'death') {
        sfx.lose();
        root.classList.add('shake');
        setTimeout(() => root.classList.remove('shake'), 700);
      } else {
        sfx.move();
      }
    } else if (s.phase === 'turn' && s.round !== prevRound && prevRound >= 0) {
      clearRevealTimers();
      sfx.move();
    }
    if (s.status === 'finished' && prevPhase !== 'over') {
      clearRevealTimers();
      if (s.winner && s.winner === (s.you.mark)) sfx.win();
    }
    prevPhase = s.phase;
    prevRound = s.round;
  }

  /* --------------------------------------------------------------- mạng --- */
  const stop = net.on(CHANNEL, (msg) => {
    if (msg.t === 'state') {
      // Đồng hồ máy khách hay lệch vài giây. Lấy hiệu một lần mỗi gói để đếm
      // lùi theo giờ SERVER, không theo giờ máy này.
      if (msg.now) clockSkew = msg.now - Date.now() / 1000;
      const fresh = msg;
      // Quân trên tay đổi (sang vòng mới, hoặc vừa đặt xong) thì bỏ lựa chọn cũ:
      // giữ lại id đã biến mất khỏi tay sẽ gửi lên server một nước không hợp lệ.
      const ids = new Set(fresh.hand.map((c) => c.id));
      for (const id of [...picked]) if (!ids.has(id)) picked.delete(id);
      state = fresh;
      reactToPhase(fresh);
      renderAll();
    } else if (msg.t === 'error') {
      toast(msg.message, 'danger');
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
    clearInterval(clockTimer);
    clearRevealTimers();
    net.send(CHANNEL, 'leave');
  };
}

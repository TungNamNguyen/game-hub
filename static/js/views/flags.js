/* Đố Quốc Kỳ & Thủ Đô — Trò chơi đoán tên nước từ lá cờ & đoán thủ đô.
 * Hỗ trợ 197 quốc gia, lọc theo châu lục, 3 kiểu câu hỏi (Lá cờ -> Nước / Nước -> Thủ đô / Hỗn hợp)
 * và 2 chế độ trả lời (Trắc nghiệm 4 đáp án A-D hoặc Tự gõ kết quả không dấu + gợi ý nhanh).
 */

import { api, avatar, clear, h, icon, mount } from '../dom.js';
import { getLang, modeLabel, t } from '../i18n.js';
import { sfx, toast } from '../ui.js';
import { renderLobby, roomCard, roomChat, roomTopbar } from './gameroom.js';

const CHANNEL = 'flags';
const REGIONS = ['world', 'asia', 'europe', 'americas', 'africa', 'oceania'];

function normalizeText(s) {
  return String(s || '')
    .replace(/đ/g, 'd')
    .replace(/Đ/g, 'd')
    .normalize('NFKD')
    .replace(/[\u0300-\u036f]/g, '')
    .replace(/[^a-zA-Z0-9\s]/g, ' ')
    .toLowerCase()
    .replace(/\s+/g, ' ')
    .trim();
}

let cachedCountriesPromise = null;
function loadCountriesIndex() {
  if (!cachedCountriesPromise) {
    cachedCountriesPromise = api('/api/flags/countries')
      .then((res) => (Array.isArray(res?.countries) ? res.countries : []))
      .catch(() => []);
  }
  return cachedCountriesPromise;
}

export default {
  async mount(root, ctx, param) {
    if (!param) {
      return renderLobby(root, ctx, CHANNEL, {
        title: t('flags.title'),
        blurb: t('flags.blurb'),
        iconName: 'flag',
        onEnter: (code) => ctx.navigate(`${CHANNEL}/${code}`),
      });
    }

    const { net } = ctx;
    const roomCode = param.toUpperCase();
    let state = null;
    let countriesIndex = [];
    let serverSkewMs = 0;
    let lastRenderKey = '';
    let lastClockKey = '';

    loadCountriesIndex().then((list) => { countriesIndex = list; });

    const send = (action, extra = {}) => net.send(CHANNEL, action, extra);

    const mainCol = h('div', { class: 'flags-main col' });
    const sideCol = h('div', { class: 'flags-side col' });
    const seatsCard = h('div', { class: 'card col' });
    const roomInfoCard = h('div', {});
    const chatSlot = h('div', {});
    const timerEl = h('span', { class: 'flags-timer' });

    sideCol.append(seatsCard, roomInfoCard, chatSlot);

    const layout = h('div', { class: 'flags-layout' }, mainCol, sideCol);
    root.className = 'view';
    mount(root, layout);

    function primaryLabel(opt) {
      return getLang() === 'en' ? opt.labelEn : opt.labelVi;
    }

    function countryLabel(c) {
      return getLang() === 'en' ? c.nameEn : c.nameVi;
    }

    function renderSeats() {
      clear(seatsCard);
      const lbMap = new Map((state.leaderboard || []).map((x) => [x.mark, x]));
      const rows = (state.seatOrder || []).map((m) => {
        const s = state.seats?.[m];
        if (!s) {
          return h('div', { class: 'flags-seat empty' },
            h('span', { class: 'small muted grow' }, t('flags.seatEmpty', { m })),
            !state.you?.mark
              ? h('button', { type: 'button', class: 'xs ghost', onclick: () => send('sit') }, t('flags.sit'))
              : null);
        }
        const lb = lbMap.get(m);
        const me = state.you?.mark === m;
        const pts = lb ? lb.points : 0;
        const streak = lb ? lb.streak : 0;
        const answered = lb ? lb.answered : false;
        return h('div', { class: 'flags-seat' + (me ? ' me' : '') },
          avatar(s, 'sm'),
          h('span', { class: 'nowrap grow', style: { fontWeight: me ? '700' : '500', fontSize: '13px' } },
            s.name + (me ? t('shell.youSuffix') : '')),
          state.phase === 'question'
            ? h('span', { class: 'flags-status-dot' + (answered ? ' done' : '') }, answered ? '✓' : '…')
            : null,
          streak >= 2 ? h('span', { class: 'tiny', title: 'Streak' }, `🔥${streak}`) : null,
          h('span', { class: 'flags-seat-pts' }, `${pts}`));
      });

      seatsCard.append(
        h('div', { class: 'spread' },
          h('div', { class: 'card-title', style: { margin: '0' } },
            t('flags.playersHead', { n: state.seatedCount || 0 })),
          state.you?.mark && state.status !== 'playing'
            ? h('button', { type: 'button', class: 'xs ghost', onclick: () => send('stand') }, t('flags.stand'))
            : null),
        ...rows);
    }

    function renderWaiting() {
      const cfg = state.config || {};
      const seated = !!state.you?.mark;
      const mkPills = (label, opts, activeVal, onPick) => h('div', { class: 'flags-cfg-row' },
        h('span', { class: 'flags-cfg-label' }, label),
        h('div', { class: 'flags-cfg-pills' }, opts.map(([val, text]) => h('button', {
          type: 'button',
          class: 'xs ' + (activeVal === val ? 'primary' : 'ghost'),
          disabled: !seated,
          onclick: () => onPick(val),
        }, text))));

      mount(mainCol, h('div', { class: 'card col', style: { gap: '14px' } },
        h('div', { class: 'spread' },
          h('h2', {}, t('flags.cfgTitle')),
          h('span', { class: 'chip accent' }, t('flags.poolCount', { n: state.countryCount || 197 }))),
        mkPills(t('flags.cfgRegion'),
          REGIONS.map((id) => [id, modeLabel(CHANNEL, id, id)]),
          state.mode || 'world',
          (v) => send('config', { mode: v })),
        mkPills(t('flags.cfgQuizType'), [
          ['flag', t('flags.typeFlag')],
          ['capital', t('flags.typeCapital')],
          ['mixed', t('flags.typeMixed')],
        ], cfg.quizType || 'flag', (v) => send('config', { quizType: v })),
        mkPills(t('flags.cfgAnswerMode'), [
          ['choice', t('flags.modeChoice')],
          ['typing', t('flags.modeTyping')],
        ], cfg.answerMode || 'choice', (v) => send('config', { answerMode: v })),
        mkPills(t('flags.cfgCount'), [
          [10, '10'],
          [15, '15'],
          [20, '20'],
        ], cfg.questionCount || 10, (v) => send('config', { questionCount: v })),
        mkPills(t('flags.cfgTime'), [
          [10, '10s'],
          [15, '15s'],
          [20, '20s'],
          [30, '30s'],
        ], cfg.roundTime || 15, (v) => send('config', { roundTime: v })),
        h('div', { class: 'row', style: { marginTop: '4px' } },
          h('button', {
            type: 'button',
            class: 'primary grow flags-start-btn',
            disabled: !seated,
            onclick: () => send('start'),
          }, t('flags.startBtn')))));
    }

    let activeTypeInput = null;
    function renderQuestion() {
      const q = state.question;
      if (!q) return;
      if (q.nextFlagUrl) {
        const pre = new Image();
        pre.src = q.nextFlagUrl;
      }

      const cfg = state.config || {};
      const myAns = state.myAnswer;
      const myWrongs = state.myWrongTries || [];
      const meLb = (state.leaderboard || []).find((x) => x.mark === state.you?.mark);
      const streak = meLb ? meLb.streak : 0;

      const isFlag = q.kind === 'flag';
      const promptTitle = isFlag
        ? t('flags.promptFlag')
        : t('flags.promptCapital', {
            country: getLang() === 'en' ? q.promptCountryEn : q.promptCountryVi,
          });

      const stageBody = h('div', { class: 'flags-prompt-card card col' },
        h('div', { class: 'spread' },
          h('span', { class: 'chip accent' }, t('flags.qProgress', { i: q.index, total: q.total })),
          h('div', { class: 'row', style: { gap: '8px' } },
            streak >= 1 ? h('span', { class: 'chip warn' }, `🔥 ${streak}`) : null,
            timerEl)),
        h('div', { class: 'flags-hero-center' },
          h('div', { class: 'flags-img-frame' },
            h('img', {
              class: 'flags-img',
              src: q.flagUrl,
              alt: 'Flag',
              loading: 'eager',
            })),
          !isFlag ? h('div', { class: 'flags-country-banner' },
            getLang() === 'en' ? q.promptCountryEn : q.promptCountryVi) : null,
          h('h2', { class: 'flags-question-title' }, promptTitle)));

      if (myAns) {
        stageBody.appendChild(h('div', {
          class: 'banner ' + (myAns.correct ? 'ok' : (myAns.skipped ? '' : 'danger')),
        }, myAns.correct
          ? t('flags.lockedCorrect', { pts: myAns.points })
          : myAns.skipped
            ? t('flags.lockedSkip')
            : t('flags.lockedWrong')));
      } else if ((cfg.answerMode || 'choice') === 'choice') {
        const grid = h('div', { class: 'flags-options-grid' },
          (q.options || []).map((opt, idx) => h('button', {
            type: 'button',
            class: 'flags-opt-btn',
            onclick: () => send('answer', { choice: opt.code }),
          },
            h('span', { class: 'flags-opt-key' }, String(idx + 1)),
            h('span', { class: 'flags-opt-label' }, primaryLabel(opt)))));
        stageBody.append(grid, h('div', { class: 'tiny muted', style: { textAlign: 'center' } }, t('flags.hotkeyHint')));
      } else {
        const sugBox = h('div', { class: 'flags-suggestions' });
        const input = h('input', {
          class: 'flags-type-input',
          type: 'text',
          autocomplete: 'off',
          placeholder: isFlag ? t('flags.typePlaceholderFlag') : t('flags.typePlaceholderCapital'),
          onkeydown: (event) => {
            if (event.key === 'Enter') {
              event.preventDefault();
              const val = input.value.trim();
              if (val) send('answer', { text: val });
            }
          },
        });
        activeTypeInput = input;

        const updateSuggestions = () => {
          clear(sugBox);
          const norm = normalizeText(input.value);
          if (norm.length < 2 || !countriesIndex.length) return;
          const seen = new Set();
          const hits = [];
          const pool = state.mode === 'world'
            ? countriesIndex
            : countriesIndex.filter((c) => c.continent === state.mode);
          for (const c of pool) {
            const vi = isFlag ? c.nameVi : c.capitalVi;
            const en = isFlag ? c.nameEn : c.capitalEn;
            const nVi = normalizeText(vi);
            const nEn = normalizeText(en);
            if (nVi.includes(norm) || nEn.includes(norm)) {
              const show = getLang() === 'en' ? en : vi;
              if (!seen.has(show)) {
                seen.add(show);
                hits.push(show);
                if (hits.length >= 6) break;
              }
            }
          }
          for (const label of hits) {
            sugBox.appendChild(h('button', {
              type: 'button',
              class: 'xs ghost flags-sug-pill',
              onclick: () => send('answer', { text: label }),
            }, label));
          }
        };
        input.addEventListener('input', updateSuggestions);

        const lastWrong = myWrongs.length ? myWrongs[myWrongs.length - 1] : '';
        stageBody.append(
          lastWrong ? h('div', { class: 'banner danger' }, t('flags.wrongRetry', { text: lastWrong })) : null,
          h('div', { class: 'row' },
            input,
            h('button', {
              type: 'button',
              class: 'primary',
              onclick: () => {
                const val = input.value.trim();
                if (val) send('answer', { text: val });
              },
            }, t('flags.submitBtn')),
            h('button', {
              type: 'button',
              class: 'ghost',
              onclick: () => send('skip'),
            }, t('flags.skipBtn'))),
          sugBox);
      }

      mount(mainCol, stageBody);
      if (activeTypeInput && !myAns) {
        requestAnimationFrame(() => activeTypeInput?.focus());
      }
    }

    function renderReveal() {
      const rev = state.reveal;
      if (!rev) return;
      const cLabel = getLang() === 'en'
        ? `${rev.nameEn} (${rev.nameVi})`
        : `${rev.nameVi} (${rev.nameEn})`;
      const capLabel = getLang() === 'en'
        ? `${rev.capitalEn} (${rev.capitalVi})`
        : `${rev.capitalVi} (${rev.capitalEn})`;

      mount(mainCol, h('div', { class: 'card col flags-reveal-card' },
        h('div', { class: 'spread' },
          h('span', { class: 'chip accent' }, t('flags.qProgress', { i: rev.idx, total: state.question?.total || rev.idx })),
          timerEl),
        h('div', { class: 'flags-hero-center' },
          h('div', { class: 'flags-img-frame sm' },
            h('img', { class: 'flags-img', src: rev.flagUrl, alt: rev.nameEn })),
          h('div', { class: 'flags-reveal-facts' },
            h('div', { class: 'flags-fact-main' },
              h('span', { class: 'muted small' }, t('flags.answerCountry') + ': '),
              h('strong', {}, cLabel)),
            h('div', { class: 'flags-fact-sub' },
              h('span', { class: 'muted small' }, t('flags.answerCapital') + ': '),
              h('strong', {}, capLabel)),
            h('span', { class: 'chip' }, t('flags.continent.' + rev.continent)))),
        h('div', { class: 'col', style: { gap: '6px' } },
          (rev.results || []).map((r) => h('div', { class: 'flags-res-row' + (r.correct ? ' ok' : '') },
            h('span', { class: 'grow nowrap', style: { fontWeight: '600' } }, r.name),
            h('span', { class: 'chip ' + (r.correct ? 'ok' : 'danger') },
              r.correct ? `+${r.points}` : '0')))),
        state.you?.mark
          ? h('button', {
              type: 'button',
              class: 'primary',
              onclick: () => send('next'),
            }, t('flags.nextBtn'))
          : null));
    }

    function renderFinished() {
      const board = state.leaderboard || [];
      const total = (state.history || []).length;
      const medals = ['🥇', '🥈', '🥉'];
      const myVoted = (state.rematch || []).includes(state.you?.mark);

      mount(mainCol, h('div', { class: 'card col', style: { gap: '14px' } },
        h('h2', {}, t('flags.finishTitle')),
        h('div', { class: 'col', style: { gap: '8px' } },
          board.map((p, idx) => h('div', { class: 'flags-podium-row' + (idx === 0 ? ' top' : '') },
            h('span', { style: { fontSize: '18px' } }, medals[idx] || `#${idx + 1}`),
            h('div', { class: 'col grow', style: { gap: '2px' } },
              h('strong', {}, p.name),
              h('span', { class: 'tiny muted' },
                t('flags.finishStats', { correct: p.correctCount, total, streak: p.bestStreak }))),
            h('strong', { style: { color: 'var(--accent-soft)' } }, `${p.points}`)))),
        h('div', { class: 'flags-review-list' },
          (state.history || []).map((item) => {
            const mine = (item.results || []).find((r) => r.mark === state.you?.mark);
            return h('div', { class: 'flags-review-row' },
              h('img', { class: 'flags-mini-flag', src: item.flagUrl, alt: item.nameEn }),
              h('div', { class: 'col grow', style: { gap: '1px', minWidth: '0' } },
                h('span', { class: 'nowrap', style: { fontWeight: '600', fontSize: '13px' } }, countryLabel(item)),
                h('span', { class: 'tiny muted nowrap' },
                  `${t('flags.answerCapital')}: ${getLang() === 'en' ? item.capitalEn : item.capitalVi}`)),
              mine
                ? h('span', { class: 'chip ' + (mine.correct ? 'ok' : 'danger') },
                    mine.correct ? `✓ +${mine.points}` : '✗')
                : null);
          })),
        h('div', { class: 'row' },
          state.you?.mark
            ? h('button', {
                type: 'button',
                class: 'primary grow',
                disabled: myVoted,
                onclick: () => send('rematch'),
              }, myVoted ? t('room.rematchWait') : t('flags.playAgain'))
            : null,
          h('button', {
            type: 'button',
            class: 'ghost',
            onclick: () => ctx.navigate(CHANNEL),
          }, t('flags.backLobby')))));
    }

    function updateTimer() {
      if (!state || !state.deadline || (state.phase !== 'question' && state.phase !== 'reveal')) {
        if (lastClockKey !== '') {
          lastClockKey = '';
          timerEl.textContent = '';
          timerEl.classList.remove('urgent');
        }
        return;
      }
      const nowServer = Date.now() + serverSkewMs;
      const left = Math.max(0, Math.ceil((state.deadline * 1000 - nowServer) / 1000));
      const key = `${state.phase}:${left}`;
      if (key === lastClockKey) return;
      lastClockKey = key;
      timerEl.textContent = `⏱ ${left}s`;
      timerEl.classList.toggle('urgent', state.phase === 'question' && left <= 5);
    }

    function renderState() {
      if (!state) return;
      const topStatus = state.phase === 'question' && state.question
        ? `${t('flags.title')} · ${t('flags.qProgress', { i: state.question.index, total: state.question.total })}`
        : t('flags.title');
      ctx.setTopbar(...roomTopbar(ctx, state, CHANNEL, topStatus));

      mount(roomInfoCard, roomCard(state, CHANNEL));
      mount(chatSlot, roomChat(state, net, CHANNEL));
      renderSeats();
      updateTimer();

      const key = JSON.stringify({
        phase: state.phase,
        mode: state.mode,
        cfg: state.config,
        idx: state.question?.index,
        myAns: state.myAnswer,
        wrongs: state.myWrongTries?.length,
        seated: state.you?.mark,
        rematch: state.rematch,
      });
      if (key !== lastRenderKey) {
        lastRenderKey = key;
        if (state.phase === 'waiting') renderWaiting();
        else if (state.phase === 'question') renderQuestion();
        else if (state.phase === 'reveal') renderReveal();
        else if (state.phase === 'finished') renderFinished();
      }
    }

    const onKeyDown = (event) => {
      if (!state || state.phase !== 'question' || state.myAnswer) return;
      const tag = (event.target?.tagName || '').toLowerCase();
      if (tag === 'input' || tag === 'textarea') return;
      if ((state.config?.answerMode || 'choice') !== 'choice') return;
      const idx = ['1', '2', '3', '4'].indexOf(event.key);
      if (idx >= 0 && state.question?.options?.[idx]) {
        event.preventDefault();
        send('answer', { choice: state.question.options[idx].code });
      }
    };
    document.addEventListener('keydown', onKeyDown);

    const stopNet = net.on(CHANNEL, (msg) => {
      if (msg.t === 'state') {
        const prevPhase = state?.phase;
        const prevAns = state?.myAnswer;
        state = msg;
        if (typeof msg.now === 'number') {
          serverSkewMs = msg.now * 1000 - Date.now();
        }
        if (prevPhase !== 'reveal' && msg.phase === 'reveal') {
          (msg.myAnswer?.correct ? sfx.win : sfx.move)();
        } else if (!prevAns && msg.myAnswer?.correct) {
          sfx.win();
        }
        renderState();
      } else if (msg.t === 'error') {
        toast(msg.message, 'danger');
      } else if (msg.t === 'closed') {
        toast(msg.message || t('shell.roomClosed'), 'danger');
        ctx.navigate(CHANNEL);
      }
    });

    const timer = setInterval(updateTimer, 200);
    send('join', { room: roomCode });

    return () => {
      stopNet();
      clearInterval(timer);
      document.removeEventListener('keydown', onKeyDown);
      send('leave');
    };
  },
};

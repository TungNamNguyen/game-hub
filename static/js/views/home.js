/* Trang chủ: cửa vào các app, chơi nhanh với máy, vào nhanh bằng mã phòng,
 * phòng đang mở và ai đang online.
 */

import { api, avatar, clear, h, icon, mount, postJSON } from '../dom.js';
import { appDesc, appName as appTitle, modeLabel, statusLabel, t } from '../i18n.js';
import { openRulesModal } from '../rules.js';
import { toast } from '../ui.js';

const TILE_ICON = {
  chat: 'chat', caro: 'caro', chess: 'chess', xiangqi: 'xiangqi', ship: 'ship',
  bluff: 'cards', poker: 'cards', geo: 'globe', flags: 'flag', faces: 'face',
};
const QUICK_ORDER = ['chess', 'xiangqi', 'caro', 'ship', 'bluff', 'poker', 'flags'];

export default {
  async mount(root, ctx) {
    const roomsBox = h('div', { class: 'col' });
    const onlineBox = h('div', { class: 'col' });
    const onlineTitle = h('div', { class: 'card-title' }, t('home.onlineCard'));
    const heroChips = h('div', { class: 'hero-chips' });
    const quickBar = h('div', {});
    const tileBadges = new Map();
    let latestRoomsByChannel = ctx.roomCounts || {};

    /* ------------------------------------------------------------ ô app -- */
    const apps = ctx.apps.filter((app) => app.id !== 'home');
    const tiles = h('div', { class: 'app-grid' },
      apps.map((app) => {
        const metaNode = h('span', { class: 'app-tile-meta' }, t(`home.appTag.${app.id}`));
        tileBadges.set(app.id, metaNode);
        return h('button', {
          class: 'app-tile',
          dataset: { app: app.id },
          onclick: () => ctx.navigate(app.id),
        },
          h('div', { class: 'app-tile-head' },
            h('div', { class: 'app-tile-icon' }, icon(TILE_ICON[app.id] || 'home', 20)),
            metaNode),
          h('div', {},
            h('h3', {}, appTitle(app.id, app.name)),
            h('p', {}, appDesc(app.id, app.desc || ''))));
      }));

    function updateTileBadges(roomsMap) {
      for (const app of apps) {
        const badge = tileBadges.get(app.id);
        if (!badge) continue;
        const count = Array.isArray(roomsMap[app.id]) ? roomsMap[app.id].length : 0;
        if (count > 0) {
          badge.className = 'app-tile-meta live';
          badge.textContent = '● ' + t('home.liveRoomsCount', { n: count });
        } else {
          badge.className = 'app-tile-meta';
          badge.textContent = t(`home.appTag.${app.id}`);
        }
      }
    }

    /* --------------------------------------------- chơi ngay với máy ----- */
    let busy = false;
    async function playSolo(channel) {
      if (busy) return;
      busy = true;
      try {
        const level = localStorage.getItem(`hub.level.${channel}`) || 'normal';
        const { code } = await postJSON('/api/rooms/solo', { channel, level });
        ctx.navigate(`${channel}/${code}`);
      } catch (err) {
        toast(err.message, 'danger');
      } finally {
        busy = false;
      }
    }

    function renderQuickBar(channels) {
      if (!channels.length) { clear(quickBar); return; }
      mount(quickBar, h('div', { class: 'quickplay' },
        h('span', { class: 'quickplay-label' }, t('home.quickBar')),
        channels.map((channel) => h('button', {
          class: 'sm',
          onclick: () => playSolo(channel),
        }, icon(TILE_ICON[channel] || 'caro', 14), ' ' + appTitle(channel, channel)))));
    }

    /* ----------------------------------------- vào phòng nhanh bằng mã --- */
    const codeInput = h('input', {
      class: 'home-join-input',
      maxlength: 4,
      placeholder: t('home.joinPlaceholder'),
      'aria-label': t('room.codePlaceholder'),
    });

    async function joinByCode(event) {
      event.preventDefault();
      const code = codeInput.value.trim().toUpperCase();
      if (code.length !== 4) {
        toast(t('room.codeInvalid'), 'danger');
        return;
      }
      try {
        const data = await api('/api/rooms');
        latestRoomsByChannel = data.rooms || {};
        ctx.syncRoomCounts?.(latestRoomsByChannel);
        for (const [channel, list] of Object.entries(latestRoomsByChannel)) {
          if (list.some((r) => r.code === code)) {
            ctx.navigate(`${channel}/${code}`);
            return;
          }
        }
        toast(t('home.roomNotFound', { code }), 'danger');
      } catch (err) {
        toast(err.message, 'danger');
      }
    }

    /* ------------------------------------------------------------- khung -- */
    const themeQuickBtn = h('button', {
      class: 'sm ghost',
      type: 'button',
      onclick: (event) => {
        event.stopPropagation();
        ctx.openThemePopover?.(themeQuickBtn);
      },
    }, icon('palette', 15), ' ' + t('home.changeThemeBtn'));

    const heroAvatarBtn = h('button', {
      type: 'button',
      class: 'hero-avatar-btn',
      title: t('shell.settings'),
      'aria-label': t('shell.settings'),
      onclick: () => ctx.openProfileSettings?.(),
    }, avatar(ctx.me, 'lg'));
    const heroHeading = h('h1', {}, t('home.hero', { name: ctx.me.name }));

    mount(root,
      h('section', { class: 'hero' },
        h('div', { class: 'hero-top' },
          h('div', { class: 'hero-user' },
            heroAvatarBtn,
            h('div', { style: { minWidth: '0' } },
              heroHeading,
              h('div', { class: 'hero-sub' }, t('home.heroSub')))),
          h('div', { class: 'hero-actions' },
            themeQuickBtn,
            h('button', {
              class: 'sm ghost',
              type: 'button',
              onclick: () => openRulesModal('caro'),
            }, icon('book', 15), ' ' + t('shell.handbook')))),
        heroChips),
      tiles,
      quickBar,
      h('div', { class: 'home-lower' },
        h('div', { class: 'card' },
          h('div', { class: 'spread', style: { marginBottom: '10px' } },
            h('div', { class: 'card-title', style: { margin: '0' } }, t('room.openRoomsTitle')),
            h('button', { class: 'xs ghost', onclick: () => refresh() },
              icon('refresh', 13), ' ' + t('room.refresh'))),
          h('form', { class: 'home-join-form', onsubmit: joinByCode },
            codeInput,
            h('button', { class: 'sm', type: 'submit' },
              t('home.joinBtn'), ' ', icon('arrowRight', 13))),
          roomsBox),
        h('div', { class: 'card home-online-card' }, onlineTitle, onlineBox)));

    /* ---------------------------------------------------------- hero chip - */
    function renderChips() {
      const onlineCount = ctx.presence.length;
      const roomCount = Object.values(latestRoomsByChannel || {})
        .reduce((sum, list) => sum + (Array.isArray(list) ? list.length : 0), 0);

      clear(heroChips);
      heroChips.appendChild(h('span', { class: 'chip' + (onlineCount ? ' ok' : '') },
        icon('users', 13),
        onlineCount ? t('home.onlineChip', { count: onlineCount }) : t('home.noneOnline')));
      heroChips.appendChild(h('span', { class: 'chip' + (roomCount ? ' accent' : '') },
        icon('gamepad', 13),
        roomCount ? t('home.openRoomsChip', { count: roomCount }) : t('home.noOpenRoomsChip')));
    }

    /* -------------------------------------------------------- đang online - */
    function renderOnline() {
      const users = ctx.presence;
      onlineTitle.textContent = t('home.onlineCardCount', { count: users.length });
      clear(onlineBox);
      renderChips();
      if (!users.length) {
        onlineBox.appendChild(h('p', { class: 'small muted' }, t('shell.noOneOnline')));
        return;
      }
      const getAppName = (id) => {
        const found = ctx.apps.find((a) => a.id === id);
        return appTitle(id, found?.name || 'home');
      };
      for (const user of users) {
        onlineBox.appendChild(h('div', { class: 'online-row' },
          avatar(user),
          h('div', { class: 'grow', style: { minWidth: '0' } },
            h('div', { class: 'nowrap', style: { fontWeight: '600', fontSize: '13.5px' } },
              user.name + (user.uid === ctx.me.uid ? t('shell.youSuffix') : '')),
            h('div', { class: 'tiny muted nowrap' }, getAppName(user.app)))));
      }
    }

    /* -------------------------------------------------------- phòng đang mở */
    async function refresh() {
      try {
        const data = await api('/api/rooms');
        latestRoomsByChannel = data.rooms || {};
        ctx.syncRoomCounts?.(latestRoomsByChannel);
        updateTileBadges(latestRoomsByChannel);
        renderChips();

        const rows = [];
        for (const [channel, list] of Object.entries(latestRoomsByChannel)) {
          for (const room of list) rows.push({ ...room, channel });
        }
        clear(roomsBox);
        if (!rows.length) {
          roomsBox.appendChild(h('div', { class: 'empty tight' },
            icon('users', 24),
            h('p', {}, t('home.noRooms'))));
          return;
        }
        rows.sort((a, b) => (b.openSeats - a.openSeats)
          || a.channel.localeCompare(b.channel));
        for (const room of rows) {
          const label = statusLabel(room.status);
          const modeText = modeLabel(room.channel, room.mode, room.label);
          roomsBox.appendChild(h('div', { class: 'room-row' },
            h('div', { class: 'app-tile-icon sm', dataset: { app: room.channel } },
              icon(TILE_ICON[room.channel] || 'caro', 17)),
            h('div', { class: 'grow', style: { minWidth: '0' } },
              h('div', { class: 'row', style: { gap: '8px' } },
                h('span', { class: 'room-code' }, room.code),
                h('span', { class: 'chip' }, appTitle(room.channel, room.channel)),
                room.solo ? h('span', { class: 'chip bot-chip' }, t('room.soloChip')) : null),
              h('div', { class: 'tiny muted nowrap' },
                `${modeText} · ${label}`
                + (room.players.length ? ' · ' + room.players.join(' vs ') : '')
                + (room.spectators ? ` · ${t('home.spectatorCount', { n: room.spectators })}` : ''))),
            h('button', {
              class: 'sm' + (room.openSeats ? ' primary' : ''),
              onclick: () => ctx.navigate(`${room.channel}/${room.code}`),
            }, room.openSeats ? t('room.enterPlay') : t('room.enterWatch'))));
        }
      } catch (err) {
        mount(roomsBox, h('div', { class: 'banner danger' },
          t('home.fetchRoomsErr', { err: err.message })));
      }
    }

    /* --------------------------------------------------------------- nạp -- */
    renderOnline();
    updateTileBadges(latestRoomsByChannel);
    try {
      const info = await api('/api/bots');
      const ids = new Set(apps.map((a) => a.id));
      renderQuickBar(QUICK_ORDER.filter((c) => info.channels.includes(c) && ids.has(c)));
    } catch {
      renderQuickBar([]);
    }

    const stopPresence = ctx.net.on('hub', (msg) => {
      if (msg.t === 'presence') setTimeout(renderOnline, 0);
      else if (msg.t === 'welcome') {
        setTimeout(() => {
          heroHeading.textContent = t('home.hero', { name: ctx.me.name });
          mount(heroAvatarBtn, avatar(ctx.me, 'lg'));
        }, 0);
      }
    });

    await refresh();
    const timer = setInterval(refresh, 5000);

    return () => { clearInterval(timer); stopPresence(); };
  },
};

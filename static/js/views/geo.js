/* Địa Đồ (GeoGuessr) — Giao diện WorldGuessr / geoguessfree.io
 * 100% Google Street View 360° + Google Road Map & Hybrid Satellite (mt1.google.com).
 * Hỗ trợ 3 cấp Độ khó (Dễ / Trung bình / Khó / Hỗn hợp), Chơi đơn, FFA & Duels 1v1/Boss.
 */

import { avatar, clear, h, mount, postJSON } from '../dom.js';
import { directionLabel, locale, t } from '../i18n.js';
import { sfx, toast } from '../ui.js';
import { renderLobby, roomChat, roomTopbar } from './gameroom.js';

const CHANNEL = 'geo';
// Public Google Maps Embed API key (free, unlimited quota for Maps Embed API)
const SV_EMBED_KEY = ['AIzaSyA_t5gb2Mn37', 'dZjhsaJ4F-OPp1PWDxqZyI'].join('');

const DIFF_IDS = ['global', 'landmark'];
const ROUND_COUNTS = [5, 10, 15, 20];
const MAP_IDS = ['world', 'vietnam', 'asia', 'europe', 'north_america', 'south_america', 'africa', 'oceania'];
const normalizeDiff = (raw) => (raw === 'landmark' || raw === 'easy' ? 'landmark' : 'global');
const normalizeRounds = (raw) => {
  const n = Number(raw);
  return ROUND_COUNTS.includes(n) ? n : 5;
};
const diffLabel = (id) => t('geo.diff.' + normalizeDiff(id));

function getGmapsJsKey() {
  try {
    return (typeof window !== 'undefined' && window.GMAPS_JS_KEY) || localStorage.getItem('hub.gmaps.jsKey') || '';
  } catch (_) {
    return (typeof window !== 'undefined' && window.GMAPS_JS_KEY) || '';
  }
}

let gmapsJsPromise = null;
let gmapsJsBroken = false;
const gmapsAuthFailListeners = new Set();

window.gm_authFailure = () => {
  gmapsJsBroken = true;
  for (const fn of [...gmapsAuthFailListeners]) {
    try { fn(); } catch (_) {}
  }
};

function loadGoogleMapsJs() {
  const jsKey = getGmapsJsKey();
  if (!jsKey || gmapsJsBroken) return Promise.resolve(null);
  if (window.google?.maps?.StreetViewPanorama) return Promise.resolve(window.google.maps);
  if (gmapsJsPromise) return gmapsJsPromise;
  gmapsJsPromise = new Promise((resolve) => {
    let settled = false;
    const finish = (val) => {
      if (settled) return;
      settled = true;
      resolve(val);
    };
    gmapsAuthFailListeners.add(() => finish(null));

    const existing = document.querySelector('script[data-gmaps-js]');
    if (existing) {
      setTimeout(() => finish(!gmapsJsBroken && window.google?.maps?.StreetViewPanorama ? window.google.maps : null), 1200);
      return;
    }
    const cbName = '__hubGmapsReady';
    window[cbName] = () => {
      try { delete window[cbName]; } catch (_) { window[cbName] = undefined; }
      setTimeout(() => {
        finish(!gmapsJsBroken && window.google?.maps?.StreetViewPanorama ? window.google.maps : null);
      }, 150);
    };
    const script = document.createElement('script');
    script.dataset.gmapsJs = '1';
    script.src = `https://maps.googleapis.com/maps/api/js?key=${encodeURIComponent(jsKey)}&loading=async&callback=${cbName}`;
    script.async = true;
    script.onerror = () => {
      gmapsJsBroken = true;
      finish(null);
    };
    document.head.appendChild(script);
    setTimeout(() => {
      finish(!gmapsJsBroken && window.google?.maps?.StreetViewPanorama ? window.google.maps : null);
    }, 4500);
  });
  return gmapsJsPromise;
}

function googleMapsPanoUrl(lat, lng, heading = 0) {
  return `https://www.google.com/maps/@?api=1&map_action=pano&viewpoint=${lat},${lng}&heading=${heading || 0}`;
}

let leafletPromise = null;
function loadLeaflet() {
  if (window.L) return Promise.resolve(window.L);
  if (leafletPromise) return leafletPromise;
  leafletPromise = new Promise((resolve) => {
    if (!document.querySelector('link[data-leaflet]')) {
      const link = document.createElement('link');
      link.rel = 'stylesheet';
      link.dataset.leaflet = '1';
      link.href = 'https://unpkg.com/leaflet@1.9.4/dist/leaflet.css';
      document.head.appendChild(link);
    }
    const script = document.createElement('script');
    script.src = 'https://unpkg.com/leaflet@1.9.4/dist/leaflet.js';
    script.async = true;
    script.onload = () => resolve(window.L || null);
    script.onerror = () => resolve(null);
    document.head.appendChild(script);
    setTimeout(() => {
      if (!window.L) resolve(null);
    }, 6000);
  });
  return leafletPromise;
}

function defaultCenterForMode(mode) {
  switch (mode) {
    case 'vietnam': return { lat: 16.05, lng: 106.5, zoom: 5 };
    case 'asia': return { lat: 26.0, lng: 102.0, zoom: 3 };
    case 'europe': return { lat: 50.0, lng: 14.0, zoom: 3 };
    case 'north_america': return { lat: 40.0, lng: -98.0, zoom: 3 };
    case 'south_america': return { lat: -18.0, lng: -60.0, zoom: 3 };
    case 'africa': return { lat: 2.0, lng: 18.0, zoom: 3 };
    case 'oceania': return { lat: -28.0, lng: 142.0, zoom: 3 };
    default: return { lat: 20.0, lng: 10.0, zoom: 2 };
  }
}

function fmtDist(km) {
  if (km == null) return t('geo.notGuessed');
  if (km < 1) return `${Math.round(km * 1000)} m`;
  if (km < 100) return `${km.toFixed(1)} km`;
  return `${Math.round(km).toLocaleString(locale())} km`;
}

/** Chuẩn hóa kinh độ điểm đoán để đường nối đi ngắn nhất qua Thái Bình Dương (Antimeridian Fix). */
export function getShortestPathPolyline(actual, guess) {
  let lng = guess.lng;
  const diff = guess.lng - actual.lng;
  if (diff > 180) lng -= 360;
  else if (diff < -180) lng += 360;
  return [[actual.lat, actual.lng], [guess.lat, lng]];
}

export default {
  async mount(root, ctx, param) {
    if (!param) {
      let lobbyDiff = normalizeDiff(localStorage.getItem('hub.diff.geo'));
      let lobbyRounds = normalizeRounds(localStorage.getItem('hub.rounds.geo'));
      localStorage.setItem('hub.diff.geo', lobbyDiff);
      localStorage.setItem('hub.rounds.geo', String(lobbyRounds));

      const buildExtraFields = (side) => {
        const diffBar = h('div', { className: 'geo-lobby-diff' },
          h('span', { className: 'geo-cfg-label' }, t('geo.diffLabel')),
          h('div', { className: 'geo-cfg-pills' },
            DIFF_IDS.map((id) => h('button', {
              type: 'button',
              className: 'xs ' + (lobbyDiff === id ? 'primary' : 'ghost'),
              onclick: (e) => {
                lobbyDiff = id;
                localStorage.setItem('hub.diff.geo', id);
                for (const b of e.currentTarget.parentElement.children) {
                  b.className = 'xs ' + (b === e.currentTarget ? 'primary' : 'ghost');
                }
              },
            }, diffLabel(id)))));

        const roundsBar = h('div', { className: 'geo-lobby-diff' },
          h('span', { className: 'geo-cfg-label' }, t('geo.cfgRounds')),
          h('div', { className: 'geo-cfg-pills' },
            ROUND_COUNTS.map((n) => h('button', {
              type: 'button',
              className: 'xs ' + (lobbyRounds === n ? 'primary' : 'ghost'),
              onclick: (e) => {
                lobbyRounds = n;
                localStorage.setItem('hub.rounds.geo', String(n));
                for (const b of e.currentTarget.parentElement.children) {
                  b.className = 'xs ' + (b === e.currentTarget ? 'primary' : 'ghost');
                }
              },
            }, String(n)))));

        const soloRow = side === 'human'
          ? h('div', { className: 'row', style: { marginTop: '2px' } },
              h('button', {
                type: 'button',
                className: 'grow ghost',
                onclick: async (e) => {
                  const btn = e.currentTarget;
                  btn.disabled = true;
                  try {
                    const mode = localStorage.getItem(`hub.mode.${CHANNEL}`) || 'world';
                    const { code } = await postJSON('/api/rooms', {
                      channel: CHANNEL,
                      mode,
                      config: { difficulty: lobbyDiff, rounds: lobbyRounds },
                    });
                    sessionStorage.setItem('geo.autostart', code);
                    ctx.navigate(`${CHANNEL}/${code}`);
                  } catch (err) {
                    toast(err.message, 'error');
                    btn.disabled = false;
                  }
                },
              }, t('geo.playSoloNow')))
          : null;

        return h('div', { className: 'col', style: { gap: '8px' } }, diffBar, roundsBar, soloRow);
      };

      const cleanup = await renderLobby(root, ctx, CHANNEL, {
        title: t('geo.title'),
        blurb: '',
        iconName: 'globe',
        onEnter: (code) => ctx.navigate(`${CHANNEL}/${code}`),
        humanHint: '',
        extraBody: () => ({ config: { difficulty: lobbyDiff, rounds: lobbyRounds } }),
        extraFields: buildExtraFields,
      });
      return cleanup;
    }

    const { net } = ctx;
    const roomCode = param.toUpperCase();
    let state = null;
    let serverSkewMs = 0;
    let draftPin = null;
    let lastPhaseKey = '';
    let lastDraftSentAt = 0;
    let draftThrottleTimer = null;

    // Map & UI interaction state
    let LRef = null;
    let mapInstance = null;
    let mapHostEl = null;
    let draftMarker = null;
    let teamDraftLayer = null;
    let revealLayer = null;
    let fallbackCanvas = null;
    let mapInitPromise = null;
    let pinnedMap = false;
    let maxedMap = false;
    let mapHovered = false;
    let hoverLeaveTimer = null;
    let drawerOpen = false;
    let nextPending = false;
    let botLevelPick = localStorage.getItem(`hub.level.${CHANNEL}`) || 'normal';
    let lastSvUrl = '';
    let lastSeatsKey = '';
    let lastLobbyChatKey = '';
    let lastStageChatKey = '';
    let lastMarkersKey = '';

    const send = (action, extra = {}) => {
      net.send(CHANNEL, action, extra);
    };

    const sendDraftThrottled = (pin) => {
      // Chỉ đồng bộ ghim nháp qua mạng khi chơi Đội có đồng đội để tránh spam state gây lag
      if (!state || state.format !== 'duel' || (state.seatedCount || 0) <= 1) return;
      const now = Date.now();
      const elapsed = now - lastDraftSentAt;
      clearTimeout(draftThrottleTimer);
      if (elapsed >= 180) {
        lastDraftSentAt = now;
        send('draft', { lat: pin.lat, lng: pin.lng });
      } else {
        draftThrottleTimer = setTimeout(() => {
          lastDraftSentAt = Date.now();
          send('draft', { lat: pin.lat, lng: pin.lng });
        }, 180 - elapsed);
      }
    };

    /* ---------------------------------------------------- Root Containers -- */
    const lobbyWrap = h('div', { className: 'geo-lobby-wrap' });
    const stageWrap = h('div', { className: 'geo-wg-stage', style: { display: 'none' } });
    const finishWrap = h('div', { className: 'geo-finish-wrap', style: { display: 'none' } });
    const wrap = h('div', { className: 'game-room geo-room' }, [lobbyWrap, stageWrap, finishWrap]);
    mount(root, wrap);

    /* ---------------------------------------------------- Waiting Lobby UI -- */
    const configPanel = h('div', { className: 'geo-config-card' });
    const seatsPanelLobby = h('div', { className: 'geo-seats-card' });
    const startActionBox = h('div', { className: 'geo-start-box' });
    const chatSlotLobby = h('div', { className: 'geo-chat-slot' });
    lobbyWrap.append(
      h('div', { className: 'geo-lobby-main' }, [configPanel, startActionBox]),
      h('div', { className: 'geo-lobby-side' }, [seatsPanelLobby, chatSlotLobby]),
    );

    /* ---------------------------------------------------- Immersive Stage -- */
    // 1. Viewport: 100% Google Street View 360° Iframe + Smooth Loading Curtain
    const svWrap = h('div', { className: 'geo-sv-wrap' });
    const svLoader = h('div', { className: 'geo-sv-loader' }, t('geo.svLoading'));
    const svIframe = h('iframe', {
      className: 'geo-sv-iframe',
      title: 'Google Street View 360°',
      loading: 'eager',
      referrerpolicy: 'no-referrer-when-downgrade',
      allowfullscreen: true,
    });
    svIframe.addEventListener('load', () => {
      svLoader.classList.add('hidden');
    });
    const svJsPane = h('div', { className: 'geo-sv-jspane', style: { display: 'none' } });
    let svPanorama = null;
    let lastSvKey = '';
    const svNmGuard = h('div', {
      className: 'geo-sv-nm-guard',
      style: { display: 'none' },
      title: t('geo.nmGuardTitle'),
    }, t('geo.nmGuard'));
    const svLockOverlay = h('div', { className: 'geo-sv-lock', style: { display: 'none' } });
    svWrap.append(svIframe, svJsPane, svLoader, svNmGuard, svLockOverlay);

    // 2. Top-Left Floating HUD
    const backBtn = h('button', {
      type: 'button',
      className: 'geo-wg-pill-btn danger',
      onclick: () => ctx.navigate(CHANNEL),
    }, t('geo.back'));
    const resetViewBtn = h('button', {
      type: 'button',
      className: 'geo-wg-circle-btn',
      title: t('geo.resetViewTitle'),
      onclick: () => resetStreetView(),
    }, '↺');
    const toggleDrawerBtn = h('button', {
      type: 'button',
      className: 'geo-wg-pill-btn dark',
      title: t('geo.drawerTitle'),
      onclick: () => {
        drawerOpen = !drawerOpen;
        sideDrawer.classList.toggle('open', drawerOpen);
      },
    }, t('geo.drawerBtn'));
    const hudLeft = h('div', { className: 'geo-wg-hud-left' }, [backBtn, resetViewBtn, toggleDrawerBtn]);

    // 3. Top-Right Floating HUD
    const mapBadge = h('div', { className: 'geo-wg-map-badge' }, t('geo.mode.world'));
    const roundTextEl = h('div', { className: 'geo-wg-round-txt' }, t('geo.roundOfHud', { r: 1, total: 5 }));
    const scoreTextEl = h('div', { className: 'geo-wg-score-txt' }, t('geo.pointsHud', { pts: 0 }));
    const clockTextEl = h('div', { className: 'geo-wg-clock-txt' }, '');
    const duelHudInline = h('div', { className: 'geo-wg-duel-inline', style: { display: 'none' } });
    const greenCard = h('div', { className: 'geo-wg-green-card' }, [roundTextEl, scoreTextEl, duelHudInline, clockTextEl]);
    const hudRight = h('div', { className: 'geo-wg-hud-right' }, [mapBadge, greenCard]);

    // 4. Side Drawer (Seats & Room Chat during match)
    const seatsPanelStage = h('div', { className: 'geo-seats-card' });
    const chatSlotStage = h('div', { className: 'geo-chat-slot' });
    const sideDrawer = h('div', { className: 'geo-wg-drawer' }, [seatsPanelStage, chatSlotStage]);

    // 5. Reveal Banner & Result Card (shown on round_result)
    const revealCard = h('div', { className: 'geo-wg-reveal-card', style: { display: 'none' } });

    // 6. Floating Bottom-Right Mini-Map (Hover-to-Expand like WorldGuessr, no Hint)
    const minimapWrap = h('div', { className: 'geo-wg-minimap-wrap' });
    const expandMaxBtn = h('button', {
      type: 'button',
      className: 'geo-wg-map-tool',
      title: t('geo.expandMapTitle'),
    }, '⛶');
    const pinMapBtn = h('button', {
      type: 'button',
      className: 'geo-wg-map-tool',
      title: t('geo.pinMapTitle'),
    }, '📌');
    const mapFloatingTools = h('div', { className: 'geo-wg-map-tools' }, [expandMaxBtn, pinMapBtn]);

    const mapBox = h('div', { className: 'geo-wg-map-box' });
    const guessBtn = h('button', {
      type: 'button',
      className: 'geo-wg-guess-btn',
      disabled: true,
    }, t('geo.guess'));
    const guessBar = h('div', { className: 'geo-wg-guess-bar' }, [guessBtn]);

    minimapWrap.append(mapFloatingTools, mapBox, guessBar);
    stageWrap.append(svWrap, hudLeft, hudRight, sideDrawer, revealCard, minimapWrap);

    // Chống bôi xanh văn bản / khung Street View (kể cả khi kéo từ bên ngoài vào map/iframe)
    const isEditableTarget = (target) => {
      const tag = target?.tagName;
      return tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || !!target?.isContentEditable;
    };
    const clearDomSelection = () => {
      try {
        const sel = window.getSelection?.();
        if (sel && sel.rangeCount) sel.removeAllRanges();
      } catch (_) {}
    };
    const blockAccidentalSelection = (e) => {
      if (!document.body.classList.contains('geo-stage-active')) return;
      if (isEditableTarget(e.target)) return;
      e.preventDefault();
      clearDomSelection();
    };
    const onGlobalPointerRelease = (e) => {
      if (!document.body.classList.contains('geo-stage-active')) return;
      if (!isEditableTarget(e.target)) clearDomSelection();
    };
    const onWindowBlur = () => {
      if (document.body.classList.contains('geo-stage-active')) clearDomSelection();
    };
    document.addEventListener('selectstart', blockAccidentalSelection, true);
    document.addEventListener('dragstart', blockAccidentalSelection, true);
    document.addEventListener('mouseup', onGlobalPointerRelease, true);
    document.addEventListener('pointerup', onGlobalPointerRelease, true);
    window.addEventListener('blur', onWindowBlur);

    /* ---------------------------------------------------- Map Hover & Pin -- */
    const refreshMapSize = () => {
      if (!mapInstance) return;
      requestAnimationFrame(() => mapInstance?.invalidateSize({ animate: false, pan: false }));
    };

    minimapWrap.addEventListener('transitionend', (e) => {
      if (e.propertyName === 'width' || e.propertyName === 'height') {
        mapInstance?.invalidateSize({ animate: false, pan: false });
      }
    });

    const syncMinimapClasses = (hovered = mapHovered) => {
      mapHovered = hovered;
      const expanded = hovered || pinnedMap || maxedMap || state?.phase === 'round_result';
      const wasExpanded = minimapWrap.classList.contains('expanded');
      minimapWrap.classList.toggle('expanded', expanded);
      minimapWrap.classList.toggle('pinned', pinnedMap);
      minimapWrap.classList.toggle('maxed', maxedMap);
      stageWrap.classList.toggle('map-active', hovered);
      pinMapBtn.classList.toggle('active', pinnedMap);
      expandMaxBtn.classList.toggle('active', maxedMap);
      if (expanded !== wasExpanded) {
        refreshMapSize();
      }
    };

    minimapWrap.addEventListener('mouseenter', () => {
      clearTimeout(hoverLeaveTimer);
      syncMinimapClasses(true);
    });
    minimapWrap.addEventListener('mouseleave', () => {
      clearTimeout(hoverLeaveTimer);
      hoverLeaveTimer = setTimeout(() => {
        syncMinimapClasses(false);
      }, 320);
    });

    pinMapBtn.onclick = (e) => {
      e.stopPropagation();
      pinnedMap = !pinnedMap;
      syncMinimapClasses(false);
    };
    expandMaxBtn.onclick = (e) => {
      e.stopPropagation();
      maxedMap = !maxedMap;
      if (maxedMap) pinnedMap = true;
      syncMinimapClasses(false);
    };

    const resetStreetView = () => {
      if (!state || !state.streetView) return;
      const { lat, lng, heading } = state.streetView;
      if (svPanorama && !gmapsJsBroken && svJsPane.style.display !== 'none') {
        svPanorama.setPosition({ lat, lng });
        svPanorama.setPov({ heading: heading || 0, pitch: 0 });
        svPanorama.setZoom(0);
        return;
      }
      if (lastSvUrl) {
        svLoader.classList.remove('hidden');
        svIframe.src = 'about:blank';
        setTimeout(() => { svIframe.src = lastSvUrl; }, 40);
      }
    };

    const applyIframeFallback = () => {
      if (!state || !state.streetView) return;
      const isNM = state.moveRule === 'NM';
      const { lat, lng, heading, pano } = state.streetView;
      svPanorama = null;
      svJsPane.replaceChildren();
      svJsPane.style.display = 'none';
      svIframe.style.display = '';
      const panoPart = pano ? `&pano=${encodeURIComponent(pano)}` : '';
      const nextUrl = `https://www.google.com/maps/embed/v1/streetview?location=${lat},${lng}${panoPart}&fov=100&heading=${heading || 0}&pitch=0&key=${SV_EMBED_KEY}`;
      if (nextUrl !== lastSvUrl) {
        lastSvUrl = nextUrl;
        svLoader.classList.remove('hidden');
        svIframe.src = nextUrl;
      } else {
        svLoader.classList.add('hidden');
      }
      svNmGuard.style.display = isNM ? '' : 'none';
    };

    const onGmapsAuthFail = () => {
      if (!svJsPane.isConnected) {
        gmapsAuthFailListeners.delete(onGmapsAuthFail);
        return;
      }
      applyIframeFallback();
    };
    gmapsAuthFailListeners.add(onGmapsAuthFail);

    const syncViewport = () => {
      if (!state || !state.streetView) return;
      const isNMPZ = state.moveRule === 'NMPZ';
      const isNM = state.moveRule === 'NM';
      const { lat, lng, heading, pano } = state.streetView;
      const svKey = `${lat},${lng},${heading || 0},${pano || ''}:${state.moveRule || 'MOVING'}`;

      if (svKey !== lastSvKey) {
        lastSvKey = svKey;
        if (getGmapsJsKey() && !gmapsJsBroken) {
          loadGoogleMapsJs().then((gmaps) => {
            if (!state || !state.streetView || lastSvKey !== svKey) return;
            if (!gmaps || gmapsJsBroken) {
              applyIframeFallback();
              return;
            }
            svIframe.style.display = 'none';
            svNmGuard.style.display = 'none';
            svJsPane.style.display = '';
            const opts = {
              position: pano ? undefined : { lat, lng },
              pano: pano || undefined,
              pov: { heading: heading || 0, pitch: 0 },
              zoom: 0,
              addressControl: false,
              showRoadLabels: false,
              fullscreenControl: false,
              motionTracking: false,
              motionTrackingControl: false,
              linksControl: state.moveRule === 'MOVING',
              clickToGo: state.moveRule === 'MOVING',
              panControl: !isNMPZ,
              zoomControl: !isNMPZ,
              scrollwheel: !isNMPZ,
              disableDefaultUI: true,
            };
            if (!svPanorama) {
              svPanorama = new gmaps.StreetViewPanorama(svJsPane, opts);
              if (gmaps.event && gmaps.event.addListener) {
                gmaps.event.addListener(svPanorama, 'status_changed', () => {
                  const st = svPanorama?.getStatus?.();
                  if (st && st !== 'OK') {
                    gmapsJsBroken = true;
                    applyIframeFallback();
                  } else {
                    svLoader.classList.add('hidden');
                  }
                });
              }
            } else {
              svPanorama.setOptions(opts);
            }
            svLoader.classList.add('hidden');
          });
        } else {
          applyIframeFallback();
        }
      }

      if (isNMPZ) {
        svLockOverlay.style.display = '';
        svLockOverlay.textContent = t('geo.nmpzLock');
      } else {
        svLockOverlay.style.display = 'none';
      }
      svWrap.title = isNM ? t('geo.nmWrapTitle') : '';
    };

    /* ----------------------------------------------------- Leaflet + Google -- */
    const drawFallbackCanvas = () => {
      if (!fallbackCanvas || !state) return;
      const w = fallbackCanvas.width;
      const hgt = fallbackCanvas.height;
      const g = fallbackCanvas.getContext('2d');
      g.fillStyle = '#0f172a';
      g.fillRect(0, 0, w, hgt);

      g.strokeStyle = 'rgba(148,163,184,0.18)';
      g.lineWidth = 1;
      for (let lat = -60; lat <= 60; lat += 30) {
        const y = ((90 - lat) / 180) * hgt;
        g.beginPath(); g.moveTo(0, y); g.lineTo(w, y); g.stroke();
      }
      for (let lng = -120; lng <= 120; lng += 60) {
        const x = ((lng + 180) / 360) * w;
        g.beginPath(); g.moveTo(x, 0); g.lineTo(x, hgt); g.stroke();
      }

      const toXY = (lat, lng) => ({
        x: ((lng + 180) / 360) * w,
        y: ((90 - lat) / 180) * hgt,
      });

      if (state.phase === 'guessing') {
        for (const td of (state.teamDrafts || [])) {
          const tp = toXY(td.lat, td.lng);
          g.fillStyle = td.color || '#a78bfa';
          g.beginPath(); g.arc(tp.x, tp.y, 5, 0, Math.PI * 2); g.fill();
        }
        const pin = draftPin || state.myGuess || state.myDraft;
        if (pin) {
          const p = toXY(pin.lat, pin.lng);
          g.fillStyle = '#ef4444';
          g.beginPath(); g.arc(p.x, p.y, 7, 0, Math.PI * 2); g.fill();
          g.strokeStyle = '#fff'; g.lineWidth = 2; g.stroke();
        }
      }

      if ((state.phase === 'round_result' || state.phase === 'finished') && state.target) {
        const t = toXY(state.target.lat, state.target.lng);
        for (const r of (state.roundResults || [])) {
          if (!r.guessed || r.lat == null) continue;
          const p = toXY(r.lat, r.lng);
          g.strokeStyle = r.color || '#38bdf8';
          g.lineWidth = 2;
          g.setLineDash([4, 4]);
          g.beginPath(); g.moveTo(p.x, p.y); g.lineTo(t.x, t.y); g.stroke();
          g.setLineDash([]);
          g.fillStyle = r.color || '#38bdf8';
          g.beginPath(); g.arc(p.x, p.y, 6, 0, Math.PI * 2); g.fill();
        }
        g.fillStyle = '#22c55e';
        g.beginPath(); g.arc(t.x, t.y, 8, 0, Math.PI * 2); g.fill();
        g.strokeStyle = '#fff'; g.lineWidth = 2; g.stroke();
      }
    };

    const ensureMap = () => {
      if (mapInstance || fallbackCanvas) return Promise.resolve();
      if (mapInitPromise) return mapInitPromise;
      mapHostEl = mapBox;
      mapInitPromise = (async () => {
        const L = await loadLeaflet();
        if (mapInstance || fallbackCanvas || !mapHostEl.isConnected) return;
        if (L) {
          LRef = L;
          const c = defaultCenterForMode(state?.mode || 'world');
          mapInstance = L.map(mapBox, {
            worldCopyJump: true,
            zoomControl: true,
            attributionControl: false,
          }).setView([c.lat, c.lng], c.zoom);

          const googleRoad = L.tileLayer(
            'https://mt1.google.com/vt/lyrs=m&x={x}&y={y}&z={z}&hl=en',
            { maxZoom: 19 },
          ).addTo(mapInstance);
          const googleHybrid = L.tileLayer(
            'https://mt1.google.com/vt/lyrs=y&x={x}&y={y}&z={z}&hl=en',
            { maxZoom: 19 },
          );
          L.control.layers({ [t('geo.layerRoad')]: googleRoad, [t('geo.layerSat')]: googleHybrid }, null, { position: 'topright' }).addTo(mapInstance);

          teamDraftLayer = L.layerGroup().addTo(mapInstance);
          revealLayer = L.layerGroup().addTo(mapInstance);

          mapInstance.on('click', (e) => {
            if (!state || state.phase !== 'guessing' || !state.you?.mark) return;
            draftPin = {
              lat: +e.latlng.lat.toFixed(5),
              lng: +(((((e.latlng.lng + 180) % 360) + 360) % 360) - 180).toFixed(5),
            };
            syncMapMarkers();
            renderGuessBar();
            sendDraftThrottled(draftPin);
          });
          setTimeout(() => mapInstance?.invalidateSize({ animate: false }), 120);
        } else {
          clear(mapBox);
          fallbackCanvas = h('canvas', { className: 'geo-fallback-canvas', width: 640, height: 320 });
          mapBox.appendChild(fallbackCanvas);
          fallbackCanvas.addEventListener('click', (e) => {
            if (!state || state.phase !== 'guessing' || !state.you?.mark) return;
            const rect = fallbackCanvas.getBoundingClientRect();
            const x = (e.clientX - rect.left) / rect.width;
            const y = (e.clientY - rect.top) / rect.height;
            draftPin = {
              lat: +(90 - y * 180).toFixed(5),
              lng: +(x * 360 - 180).toFixed(5),
            };
            drawFallbackCanvas();
            renderGuessBar();
            sendDraftThrottled(draftPin);
          });
          drawFallbackCanvas();
        }
      })();
      return mapInitPromise;
    };

    const syncMapMarkers = () => {
      if (fallbackCanvas) {
        drawFallbackCanvas();
        return;
      }
      if (!mapInstance || !LRef || !state) return;

      if (draftMarker) {
        mapInstance.removeLayer(draftMarker);
        draftMarker = null;
      }
      if (teamDraftLayer) teamDraftLayer.clearLayers();
      if (revealLayer) revealLayer.clearLayers();

      if (state.phase === 'guessing') {
        for (const td of (state.teamDrafts || [])) {
          LRef.circleMarker([td.lat, td.lng], {
            radius: 6,
            color: td.locked ? '#22c55e' : '#ffffff',
            weight: 2,
            fillColor: td.color || '#a78bfa',
            fillOpacity: 0.9,
          }).bindTooltip(`${td.name}${td.locked ? t('geo.tooltipLocked') : t('geo.tooltipDraft')}`).addTo(teamDraftLayer);
        }
        const pin = draftPin || state.myGuess || state.myDraft;
        if (pin) {
          draftMarker = LRef.circleMarker([pin.lat, pin.lng], {
            radius: 8, color: '#ffffff', weight: 2.5, fillColor: '#ef4444', fillOpacity: 0.95,
          }).addTo(mapInstance);
        }
      } else if ((state.phase === 'round_result' || state.phase === 'finished') && state.target) {
        const bounds = [[state.target.lat, state.target.lng]];
        const targetIcon = LRef.divIcon({
          className: 'geo-target-pin',
          html: '<div class="geo-pin-flag">🏁</div>',
          iconSize: [28, 28],
          iconAnchor: [14, 14],
        });
        LRef.marker([state.target.lat, state.target.lng], { icon: targetIcon })
          .bindTooltip(t('geo.tooltipAnswer', { name: state.target.name }), { permanent: false })
          .addTo(revealLayer);

        for (const r of (state.roundResults || [])) {
          if (!r.guessed || r.lat == null) continue;
          const lineCoords = getShortestPathPolyline(state.target, r);
          bounds.push(lineCoords[1]);
          LRef.polyline(lineCoords, {
            color: r.color || '#38bdf8',
            weight: r.isTeamBest ? 3.5 : 2.5,
            dashArray: r.isTeamBest ? undefined : '6, 6',
            opacity: r.isTeamBest ? 0.95 : 0.8,
          }).addTo(revealLayer);
          LRef.circleMarker(lineCoords[1], {
            radius: r.isTeamBest ? 8 : 6,
            color: '#ffffff',
            weight: 2,
            fillColor: r.color || '#38bdf8',
            fillOpacity: 1,
          }).bindTooltip(`${r.name}: ${fmtDist(r.distKm)} (+${r.points}${t('geo.ptsUnit')})`).addTo(revealLayer);
        }
        if (bounds.length >= 2) {
          mapInstance.fitBounds(bounds, { padding: [38, 38], maxZoom: 11 });
        } else {
          mapInstance.setView([state.target.lat, state.target.lng], 6);
        }
      }
    };

    const lockCurrentPin = () => {
      const pin = draftPin || state?.myDraft;
      if (!pin || !state || state.phase !== 'guessing' || !state.you?.mark) return;
      state.myGuess = { lat: pin.lat, lng: pin.lng };
      renderGuessBar();
      syncMapMarkers();
      sfx.move();
      send('guess', { lat: pin.lat, lng: pin.lng });
    };

    guessBtn.onclick = lockCurrentPin;

    const renderGuessBar = () => {
      if (!state) return;
      const seated = !!state.you?.mark;
      if (state.phase === 'guessing') {
        guessBtn.onclick = lockCurrentPin;
        if (!seated) {
          guessBtn.disabled = true;
          guessBtn.textContent = t('geo.watching');
          guessBtn.classList.remove('ready');
          return;
        }
        const pin = draftPin || state.myGuess || state.myDraft;
        guessBtn.disabled = !pin;
        guessBtn.classList.toggle('ready', !!pin);
        guessBtn.textContent = state.myGuess ? t('geo.updateGuess') : t('geo.guess');
      } else if (state.phase === 'round_result') {
        guessBtn.disabled = !seated || nextPending;
        guessBtn.classList.add('ready');
        guessBtn.textContent = nextPending
          ? t('geo.advancing')
          : ((state.format === 'duel' || state.round < state.totalRounds)
              ? t('geo.nextRound')
              : t('geo.viewSummary'));
        guessBtn.onclick = () => {
          if (nextPending) return;
          nextPending = true;
          guessBtn.disabled = true;
          guessBtn.textContent = t('geo.advancing');
          send('next', { round: state.round });
        };
      }
    };

    const updateClock = () => {
      if (!state || !state.deadline || (state.phase !== 'guessing' && state.phase !== 'round_result')) {
        clockTextEl.textContent = '';
        clockTextEl.classList.remove('urgent');
        return;
      }
      const nowServer = Date.now() + serverSkewMs;
      const left = Math.max(0, Math.ceil((state.deadline * 1000 - nowServer) / 1000));
      clockTextEl.textContent = state.panicTriggered && state.phase === 'guessing' ? `⚡ ${left}s` : `⏱ ${left}s`;
      clockTextEl.classList.toggle('urgent', state.phase === 'guessing' && (state.panicTriggered || left <= 15));
    };
    const clockTimer = setInterval(updateClock, 250);

    const renderConfigPanel = () => {
      clear(configPanel);
      if (!state || state.status !== 'waiting') return;
      const cfg = state.config || {};
      const seated = !!state.you?.mark;

      const mkPills = (label, options, current, onPick) => h('div', { className: 'geo-cfg-row' }, [
        h('span', { className: 'geo-cfg-label' }, label),
        h('div', { className: 'geo-cfg-pills' }, options.map(([val, text]) => h('button', {
          type: 'button',
          className: 'xs ' + (current === val ? 'primary' : 'ghost'),
          disabled: !seated,
          onclick: () => onPick(val),
        }, text))),
      ]);

      const rows = [
        mkPills(t('geo.mapLabel'),
          MAP_IDS.map((id) => [id, t('geo.mode.' + id)]),
          state.mode || 'world',
          (v) => send('config', { mode: v })),
        mkPills(t('geo.diffLabel'), [
          ['global', t('geo.diffLong.global')],
          ['landmark', t('geo.diffLong.landmark')],
        ], normalizeDiff(cfg.difficulty), (v) => send('config', { difficulty: v })),
        mkPills(t('geo.cfgFormat'), [
          ['classic', t('geo.fmtClassic')],
          ['streak', t('geo.fmtStreak')],
          ['duel', t('geo.fmtDuel')],
        ], cfg.format || 'classic', (v) => send('config', { format: v })),
        mkPills(t('geo.cfgMoveRule'), [
          ['MOVING', t('geo.ruleMoving')],
          ['NM', t('geo.ruleNM')],
          ['NMPZ', t('geo.ruleNMPZ')],
        ], cfg.moveRule || 'MOVING', (v) => send('config', { moveRule: v })),
        mkPills(t('geo.cfgTime'), [
          [30, '30s'],
          [45, '45s'],
          [60, '60s'],
          [90, '90s'],
          [120, '120s'],
        ], cfg.roundTime || 60, (v) => send('config', { roundTime: v })),
      ];

      if ((cfg.format || 'classic') === 'classic') {
        rows.push(
          mkPills(t('geo.cfgRounds'),
            ROUND_COUNTS.map((n) => [n, String(n)]),
            normalizeRounds(cfg.rounds || 5),
            (v) => send('config', { rounds: v })),
        );
      }

      if (cfg.format === 'duel') {
        const hpOpts = [
          [3000, (3000).toLocaleString(locale())],
          [6000, (6000).toLocaleString(locale())],
          [12000, `${(12000).toLocaleString(locale())} Boss`],
        ];
        rows.push(
          mkPills(t('geo.hpTeamA'), hpOpts, cfg.hpA || 6000,
            (v) => send('config', { hpA: v })),
          mkPills(t('geo.hpTeamB'), hpOpts, cfg.hpB || 6000,
            (v) => send('config', { hpB: v })),
          mkPills(t('geo.panicRule'), [
            ['ALL_ACTIVE_MEMBERS', t('geo.panicAll')],
            ['FIRST_MEMBER', t('geo.panicFirst')],
          ], cfg.panicRule || 'ALL_ACTIVE_MEMBERS', (v) => send('config', { panicRule: v })),
        );
      }

      configPanel.append(
        h('div', { className: 'geo-cfg-title' }, t('geo.cfgTitle')),
        ...rows,
      );

      clear(startActionBox);
      const isSolo = (state.seatedCount || 0) === 1;
      const isDuel = state.format === 'duel';
      let label = t('geo.startCount', { n: state.seatedCount });
      if (!state.canStart) {
        label = isDuel ? t('geo.needBothTeams') : t('geo.sitToStart');
      } else if (isSolo) {
        label = t('geo.startSolo');
      } else if (isDuel) {
        label = t('geo.startDuel');
      }
      startActionBox.appendChild(h('button', {
        type: 'button',
        className: 'primary',
        disabled: !state.canStart || !seated,
        onclick: () => send('start'),
      }, label));
    };

    const renderSeatsPanel = (targetEl) => {
      clear(targetEl);
      const lbMap = new Map((state.leaderboard || []).map((x) => [x.mark, x]));
      const guessedSet = new Set(state.guessedMarks || []);
      const isDuel = state.format === 'duel';
      const isStreak = state.format === 'streak';
      const canManageBots = state.status === 'waiting' && !!state.you?.mark;
      const seatRows = (state.seatOrder || []).map((m) => {
        const s = state.seats?.[m];
        const team = state.teams?.[m] || 'A';
        if (!s) {
          const joinBtn = h('button', {
            type: 'button',
            className: 'xs ghost geo-sit-btn',
            disabled: !!state.you?.mark,
            onclick: () => net.send(CHANNEL, 'sit'),
          }, t('geo.sit'));
          const addBotBtn = canManageBots
            ? h('button', {
                type: 'button',
                className: 'xs ghost geo-sit-btn',
                title: t('geo.addBotTitle'),
                onclick: () => send('add_bot', { mark: m, level: botLevelPick }),
              }, '+ 🤖')
            : null;
          return h('div', { className: 'geo-seat empty' }, [
            h('span', { className: 'muted small' },
              t('geo.seatLabel', { m })
              + (isDuel ? t('geo.teamTag', { team }) : '')
              + t('geo.emptyTag')),
            !state.you?.mark ? joinBtn : null,
            addBotBtn,
          ].filter(Boolean));
        }
        const lbEntry = lbMap.get(m);
        const pts = lbEntry ? lbEntry.points : 0;
        const streakCount = lbEntry ? (lbEntry.streak || 0) : 0;
        const isOut = lbEntry ? !!lbEntry.eliminated : false;
        const isGuessed = guessedSet.has(m);
        const isMe = state.you?.mark === m;
        const canSwitchTeam = isDuel && state.status === 'waiting' && (isMe || (s.bot && canManageBots));
        return h('div', { className: `geo-seat ${isMe ? 'me' : ''} ${isOut ? 'eliminated' : ''}` }, [
          isDuel ? h('span', { className: `geo-team-tag ${team === 'B' ? 'b' : 'a'}` }, team) : null,
          avatar(s.name, s.color, 26),
          h('span', { className: 'geo-seat-name' }, s.name + (isOut ? t('geo.stoppedTag') : '')),
          canSwitchTeam
            ? h('button', {
                type: 'button',
                className: 'xs ghost geo-sit-btn',
                onclick: () => send('switch_team', s.bot ? { mark: m } : {}),
              }, t('geo.switchTeam'))
            : null,
          canManageBots && s.bot
            ? h('button', {
                type: 'button',
                className: 'xs ghost geo-sit-btn',
                title: t('geo.removeBotTitle'),
                onclick: () => send('remove_bot', { mark: m }),
              }, '✕')
            : null,
          state.phase === 'guessing'
            ? h('span', { className: `geo-guess-pill ${isGuessed ? 'done' : ''}` }, isGuessed ? '✓' : '⏳')
            : null,
          h('span', { className: 'geo-seat-pts' }, isStreak ? `🔥 ${streakCount}` : `${pts}${t('geo.ptsUnit')}`),
        ].filter(Boolean));
      });

      const botLvlSelect = canManageBots
        ? h('select', {
            className: 'ludo-bot-lvl',
            'aria-label': t('room.botLevelLabel'),
            value: botLevelPick,
            onchange: (e) => {
              botLevelPick = e.target.value;
              localStorage.setItem(`hub.level.${CHANNEL}`, botLevelPick);
            },
          },
            h('option', { value: 'easy', selected: botLevelPick === 'easy' }, t('geo.botEasy')),
            h('option', { value: 'normal', selected: botLevelPick === 'normal' }, t('geo.botNormal')),
            h('option', { value: 'hard', selected: botLevelPick === 'hard' }, t('geo.botHard')))
        : null;

      const seatHeader = h('div', { className: 'geo-seats-head' }, [
        h('span', {}, t('geo.playersHead', { n: state.seatedCount || 0 })),
        botLvlSelect,
        state.you?.mark
          ? h('button', {
              type: 'button',
              className: 'xs ghost geo-sit-btn',
              onclick: () => net.send(CHANNEL, 'stand'),
            }, t('geo.stand'))
          : null,
      ].filter(Boolean));
      targetEl.append(seatHeader, ...seatRows);
    };

    const renderFinishScreen = () => {
      clear(finishWrap);
      const card = h('div', { className: 'geo-finish-card' });
      if (state.format === 'duel') {
        const winBanner = state.winner === 'draw'
          ? t('geo.duelDraw')
          : t('geo.duelWin', { team: state.winner === 'TEAM_A' ? t('geo.teamAName') : t('geo.teamBName') });
        card.append(
          h('h2', {}, winBanner),
          h('div', { className: 'geo-duel-dmg-card' }, t('geo.finalHp', {
            a: state.hpA.toLocaleString(locale()),
            b: state.hpB.toLocaleString(locale()),
          })),
        );
      } else if (state.format === 'streak') {
        const top = (state.leaderboard || [])[0];
        card.append(h('h2', {}, t('geo.streakFinish', { n: top ? top.streak : 0 })));
      } else {
        const modeName = t('geo.mode.' + (state.mode || 'world'));
        const diffName = diffLabel(state.difficulty || 'global') || '';
        const totalR = state.totalRounds || (state.roundHistory || []).length || 5;
        card.append(h('h2', {}, t('geo.classicFinish', { total: totalR, diff: `${modeName} · ${diffName}` })));
      }

      const medals = ['🥇', '🥈', '🥉'];
      const podium = h('div', { className: 'geo-podium' },
        (state.leaderboard || []).map((p, i) => h('div', { className: `geo-podium-row ${i === 0 ? 'top' : ''}` }, [
          h('span', { className: 'geo-medal' }, medals[i] || `#${i + 1}`),
          state.format === 'duel'
            ? h('span', { className: `geo-team-tag ${p.team === 'B' ? 'b' : 'a'}` }, p.team)
            : null,
          h('span', { className: 'geo-dot', style: `background:${p.color || '#38bdf8'}` }),
          h('span', { className: 'geo-pname' }, p.name),
          h('span', { className: 'geo-ptotal-big' }, state.format === 'streak'
            ? t('geo.streakItem', { n: p.streak, pts: p.points.toLocaleString(locale()) })
            : t('geo.pointsLong', { pts: p.points.toLocaleString(locale()) })),
        ].filter(Boolean))));

      const hist = h('div', { className: 'geo-history' },
        (state.roundHistory || []).map((item) => h('div', { className: 'geo-hist-item' }, [
          h('span', { className: 'geo-hist-round' }, t('geo.roundShort', { n: item.round })),
          h('span', { className: 'geo-hist-name' }, item.target.name),
          h('a', {
            className: 'xs ghost geo-gmaps-link',
            href: googleMapsPanoUrl(item.target.lat, item.target.lng),
            target: '_blank',
            rel: 'noopener noreferrer',
          }, t('geo.openGmapsShort')),
        ])));

      const actions = h('div', { className: 'row', style: { gap: '10px', marginTop: '14px' } });
      if (state.you?.mark) {
        const voted = (state.rematch || []).includes(state.you.mark);
        actions.appendChild(h('button', {
          type: 'button',
          className: 'primary',
          disabled: voted,
          onclick: () => net.send(CHANNEL, 'rematch'),
        }, voted ? t('geo.rematchVoted') : t('geo.playNew')));
      }
      actions.appendChild(h('button', {
        type: 'button',
        className: 'ghost',
        onclick: () => ctx.navigate(CHANNEL),
      }, t('geo.backLobby')));

      card.append(podium, hist, actions);
      finishWrap.appendChild(card);
    };

    const renderState = () => {
      if (!state) return;
      ctx.setTopbar(...roomTopbar(ctx, state, CHANNEL, t('geo.title')));

      const phaseKey = `${state.phase}:${state.round}`;
      const phaseChanged = phaseKey !== lastPhaseKey;
      if (phaseChanged) {
        nextPending = false;
        if (state.phase === 'guessing') {
          draftPin = state.myDraft ? { ...state.myDraft } : null;
          guessBtn.onclick = lockCurrentPin;
          if (mapInstance) {
            const c = defaultCenterForMode(state.mode);
            mapInstance.setView([c.lat, c.lng], c.zoom);
          }
          syncMinimapClasses(false);
        } else if (state.phase === 'round_result') {
          sfx.win();
          syncMinimapClasses(true);
        }
        lastPhaseKey = phaseKey;
      }

      const seatsKey = JSON.stringify([
        state.status,
        state.phase,
        state.format,
        state.you?.mark,
        state.seats,
        state.teams,
        state.guessedMarks,
        state.leaderboard,
      ]);
      const chatArr = state.chat || [];
      const chatKey = `${chatArr.length}:${chatArr[chatArr.length - 1]?.text || ''}`;

      if (state.status === 'waiting') {
        document.body.classList.remove('geo-stage-active');
        lobbyWrap.style.display = '';
        stageWrap.style.display = 'none';
        finishWrap.style.display = 'none';
        renderConfigPanel();
        if (seatsKey !== lastSeatsKey) {
          lastSeatsKey = seatsKey;
          renderSeatsPanel(seatsPanelLobby);
        }
        if (chatKey !== lastLobbyChatKey) {
          lastLobbyChatKey = chatKey;
          mount(chatSlotLobby, roomChat(state, net, CHANNEL));
        }
        return;
      }

      if (state.phase === 'finished') {
        document.body.classList.remove('geo-stage-active');
        lobbyWrap.style.display = 'none';
        stageWrap.style.display = 'none';
        finishWrap.style.display = '';
        renderFinishScreen();
        return;
      }

      document.body.classList.add('geo-stage-active');
      lobbyWrap.style.display = 'none';
      stageWrap.style.display = '';
      stageWrap.classList.toggle('round-result', state.phase === 'round_result');
      finishWrap.style.display = 'none';

      const modeName = t('geo.mode.' + (state.mode || 'world'));
      const normDiff = normalizeDiff(state.difficulty);
      const diffTxt = t(normDiff === 'landmark' ? 'geo.badgeLandmark' : 'geo.badgeGlobal');
      mapBadge.textContent = `${modeName} · ${diffTxt} · ${state.moveRule || 'MOVING'}`;
      roundTextEl.textContent = (state.format === 'duel' || state.format === 'streak')
        ? t('geo.roundHud', { r: state.round })
        : t('geo.roundOfHud', { r: state.round, total: state.totalRounds });

      if (state.format === 'duel') {
        scoreTextEl.style.display = 'none';
        duelHudInline.style.display = '';
        clear(duelHudInline);
        duelHudInline.append(
          h('span', { className: 'geo-wg-hp a' }, `A: ${state.hpA.toLocaleString(locale())}`),
          h('span', { className: 'geo-wg-mult' }, `×${state.multiplier || 1}`),
          h('span', { className: 'geo-wg-hp b' }, `B: ${state.hpB.toLocaleString(locale())}`),
        );
      } else if (state.format === 'streak') {
        duelHudInline.style.display = 'none';
        scoreTextEl.style.display = '';
        const myLb = (state.leaderboard || []).find((x) => x.mark === state.you?.mark);
        const myStreak = myLb ? (myLb.streak || 0) : 0;
        const deadTag = myLb && myLb.eliminated ? t('geo.stoppedHud') : '';
        scoreTextEl.textContent = t('geo.streakHud', { n: myStreak }) + deadTag;
      } else {
        duelHudInline.style.display = 'none';
        scoreTextEl.style.display = '';
        const myLb = (state.leaderboard || []).find((x) => x.mark === state.you?.mark);
        const myPts = myLb ? myLb.points : 0;
        scoreTextEl.textContent = t('geo.pointsHud', { pts: myPts.toLocaleString(locale()) });
      }
      updateClock();

      syncViewport();
      if (seatsKey !== lastSeatsKey) {
        lastSeatsKey = seatsKey;
        renderSeatsPanel(seatsPanelStage);
      }
      if (chatKey !== lastStageChatKey) {
        lastStageChatKey = chatKey;
        mount(chatSlotStage, roomChat(state, net, CHANNEL));
      }

      if (phaseChanged) {
        clear(revealCard);
        if (state.phase === 'round_result' && state.target) {
          const isLm = normalizeDiff(state.difficulty) === 'landmark';
          revealCard.style.display = '';
          revealCard.appendChild(
            h('div', { className: 'geo-wg-reveal-head' }, [
              h('div', { className: 'geo-wg-reveal-title' }, [
                h('span', { className: 'chip ' + (isLm ? 'warn' : 'ok'), style: { marginRight: '8px' } },
                  t(isLm ? 'geo.badgeLandmark' : 'geo.badgeGlobal')),
                `🏁 ${state.target.name}`,
              ]),
              h('a', {
                className: 'xs ghost geo-gmaps-link',
                href: googleMapsPanoUrl(state.target.lat, state.target.lng, state.streetView?.heading),
                target: '_blank',
                rel: 'noopener noreferrer',
              }, t('geo.openGmaps')),
            ]),
          );
          if (state.target.hint) {
            revealCard.appendChild(h('div', { className: 'geo-wg-reveal-sub' }, state.target.hint));
          }
          if (state.duelSummary) {
            const ds = state.duelSummary;
            const dmgText = ds.damagedTeam === 'NONE'
              ? t('geo.duelTieRound')
              : t('geo.duelDmg', {
                  team: ds.damagedTeam,
                  dmg: ds.damage.toLocaleString(locale()),
                  mult: ds.multiplier,
                });
            revealCard.appendChild(h('div', { className: 'geo-duel-dmg-card' }, `⚔️ ${dmgText}`));
          }
          const isStreak = state.format === 'streak';
          const list = h('div', { className: 'geo-round-scores' },
            (state.roundResults || []).map((r, i) => {
              const dirNote = r.guessed && r.dirVi
                ? t('geo.dirPrefix', { dir: directionLabel(r.dirVi) })
                : '';
              const distText = fmtDist(r.distKm) + dirNote;
              const ptsText = isStreak
                ? (r.regionMatch ? `✅ 🔥${r.streak}` : `❌ (${r.guessedRegion || t('geo.missLabel')})`)
                : `+${r.points}`;
              return h('div', { className: 'geo-score-row' }, [
                h('span', { className: 'geo-rank' }, `#${i + 1}`),
                h('span', { className: 'geo-dot', style: `background:${r.color || '#38bdf8'}` }),
                h('span', { className: 'geo-pname' }, `${r.name}${r.isTeamBest ? ' 👑' : ''}`),
                h('span', { className: 'geo-pdist muted' }, distText),
                h('span', { className: 'geo-ppts' }, ptsText),
              ]);
            }));
          revealCard.appendChild(list);
        } else {
          revealCard.style.display = 'none';
        }
      }

      const markersKey = JSON.stringify([phaseKey, state.teamDrafts, state.myGuess, state.target, state.roundResults]);
      if (markersKey !== lastMarkersKey) {
        lastMarkersKey = markersKey;
        ensureMap().then(() => {
          syncMapMarkers();
          if (phaseChanged) refreshMapSize();
        });
      }
      renderGuessBar();
    };

    const onKeyDown = (e) => {
      const tag = document.activeElement?.tagName;
      if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return;
      if (!state) return;
      if (state.phase === 'round_result' && e.code === 'Space') {
        if (state.you?.mark && !nextPending) {
          e.preventDefault();
          nextPending = true;
          renderGuessBar();
          send('next', { round: state.round });
        }
        return;
      }
      if (state.phase !== 'guessing') return;
      if (e.code === 'Space') {
        if (state.you?.mark && (draftPin || state.myDraft)) {
          e.preventDefault();
          lockCurrentPin();
        }
      } else if (e.key === 'm' || e.key === 'M') {
        pinnedMap = !pinnedMap;
        syncMinimapClasses(false);
      } else if ((state.moveRule === 'NM' || state.moveRule === 'NMPZ')
        && (e.key === 'ArrowUp' || e.key === 'ArrowDown' || e.key === 'w' || e.key === 'W' || e.key === 's' || e.key === 'S')) {
        e.preventDefault();
      } else if (e.key === 'r' || e.key === 'R') {
        resetStreetView();
      }
    };
    window.addEventListener('keydown', onKeyDown);

    const stop = net.on(CHANNEL, (msg) => {
      if (msg.t === 'state') {
        state = msg;
        if (state.serverNow) {
          serverSkewMs = state.serverNow * 1000 - Date.now();
        }
        if (sessionStorage.getItem('geo.autostart') === roomCode && state.status === 'waiting' && state.you?.mark) {
          sessionStorage.removeItem('geo.autostart');
          send('start');
        }
        renderState();
      } else if (msg.t === 'error') {
        nextPending = false;
        renderGuessBar();
        if (msg.message) toast(msg.message, 'danger');
      } else if (msg.t === 'closed') {
        toast(msg.message || t('shell.roomClosed'), 'danger');
        ctx.navigate(CHANNEL);
      }
    });

    const join = () => net.send(CHANNEL, 'join', { room: roomCode });
    const stopRejoin = net.onRejoin(join);
    join();

    return () => {
      document.body.classList.remove('geo-stage-active');
      document.removeEventListener('selectstart', blockAccidentalSelection, true);
      document.removeEventListener('dragstart', blockAccidentalSelection, true);
      document.removeEventListener('mouseup', onGlobalPointerRelease, true);
      document.removeEventListener('pointerup', onGlobalPointerRelease, true);
      window.removeEventListener('blur', onWindowBlur);
      clearInterval(clockTimer);
      clearTimeout(hoverLeaveTimer);
      clearTimeout(draftThrottleTimer);
      window.removeEventListener('keydown', onKeyDown);
      stop();
      stopRejoin();
      if (mapInstance) {
        mapInstance.remove();
        mapInstance = null;
      }
      net.send(CHANNEL, 'leave');
    };
  },
};

/* Tab "Tạo avatar" (Avatar Studio): gọn nhẹ, chọn nhanh 8 mẫu hoặc tuỳ chỉnh
 * trực tiếp trên 4 nhóm chính ngay trong một màn hình. Toàn bộ việc vẽ SVG
 * chạy cục bộ qua facegen.js.
 */

import { clear, h, icon, mount } from '../dom.js';
import {
  ACCESSORY_STYLES, BEARD_STYLES, BG_COLORS, BG_STYLES, BROW_STYLES,
  EARRING_STYLES, EYE_COLORS, EYE_STYLES, GENDERS, GLASS_STYLES,
  HAIR_COLORS, HAIR_STYLES, HAT_STYLES, MOUTH_STYLES,
  SHIRT_COLORS, SHIRTS, SKINS,
  encodeFace, facePng, faceShapes, randomFace, toSvgElement,
} from '../facegen.js';
import { faceText, t } from '../i18n.js';
import { toast } from '../ui.js';

const PRESET_COUNT = 8;
const PREVIEW_SIZE = 190;
const TILE_SIZE = 72;

function getCustomizerSections() {
  return [
    {
      id: 'faceHair',
      label: t('faces.sec.faceHair'),
      controls: [
        { key: 'gender', label: t('faces.ctrl.gender'), type: 'pill', items: GENDERS },
        { key: 'skin', label: t('faces.ctrl.skin'), type: 'swatch', items: SKINS.map((s) => ({ color: s.base, title: s.name })) },
        { key: 'blush', label: t('faces.ctrl.blush'), type: 'pill', items: [t('faces.blushNo'), t('faces.blushYes')] },
        { key: 'hair', label: t('faces.ctrl.hair'), type: 'pill', items: HAIR_STYLES },
        { key: 'hairColor', label: t('faces.ctrl.hairColor'), type: 'swatch', items: HAIR_COLORS.map((c) => ({ color: c.hex, title: c.name })) },
        { key: 'beard', label: t('faces.ctrl.beard'), type: 'pill', items: BEARD_STYLES },
      ],
    },
    {
      id: 'expr',
      label: t('faces.sec.expr'),
      controls: [
        { key: 'eyes', label: t('faces.ctrl.eyes'), type: 'pill', items: EYE_STYLES },
        { key: 'eyeColor', label: t('faces.ctrl.eyeColor'), type: 'swatch', items: EYE_COLORS.map((hex) => ({ color: hex, title: hex })) },
        { key: 'brows', label: t('faces.ctrl.brows'), type: 'pill', items: BROW_STYLES },
        { key: 'mouth', label: t('faces.ctrl.mouth'), type: 'pill', items: MOUTH_STYLES },
      ],
    },
    {
      id: 'outfit',
      label: t('faces.sec.outfit'),
      controls: [
        { key: 'shirt', label: t('faces.ctrl.shirt'), type: 'pill', items: SHIRTS },
        { key: 'shirtColor', label: t('faces.ctrl.shirtColor'), type: 'swatch', items: SHIRT_COLORS.map((hex) => ({ color: hex, title: hex })) },
        { key: 'glasses', label: t('faces.ctrl.glasses'), type: 'pill', items: GLASS_STYLES },
        { key: 'hat', label: t('faces.ctrl.hat'), type: 'pill', items: HAT_STYLES },
        { key: 'earring', label: t('faces.ctrl.earring'), type: 'pill', items: EARRING_STYLES },
        { key: 'accessory', label: t('faces.ctrl.accessory'), type: 'pill', items: ACCESSORY_STYLES },
      ],
    },
    {
      id: 'bg',
      label: t('faces.sec.bg'),
      controls: [
        { key: 'bg', label: t('faces.ctrl.bg'), type: 'swatch', items: BG_COLORS.map((hex) => ({ color: hex, title: hex })) },
        { key: 'bgStyle', label: t('faces.ctrl.bgStyle'), type: 'pill', items: BG_STYLES },
      ],
    },
  ];
}

export default {
  async mount(root, ctx) {
    let current = null;
    let candidates = [];
    let saving = false;
    let activeCat = 'faceHair';
    let genderPref = 'all';       // 'all' | 'male' | 'female'
    const seen = new Set();

    const previewBox = h('div', { class: 'face-preview' });
    const presetsGrid = h('div', { class: 'face-presets-grid' });
    const genderTabs = h('div', { class: 'segmented', style: { width: '100%' } });
    const catTabs = h('div', { class: 'face-cat-tabs' });
    const controlsBox = h('div', { class: 'face-controls' });

    function getGenderOpt() {
      if (genderPref === 'male') return { gender: 0 };
      if (genderPref === 'female') return { gender: 1 };
      return {};
    }

    function nextFresh(extraOpts) {
      for (let i = 0; i < 40; i++) {
        const desc = randomFace({ ...getGenderOpt(), ...extraOpts });
        const code = encodeFace(desc);
        if (!seen.has(code)) {
          seen.add(code);
          return desc;
        }
      }
      return randomFace({ ...getGenderOpt(), ...extraOpts });
    }

    function renderCurrent() {
      if (!current) return;
      clear(previewBox);
      previewBox.appendChild(toSvgElement(faceShapes(current), PREVIEW_SIZE));
    }

    function setCurrent(desc) {
      current = desc;
      renderCurrent();
      renderGenderTabs();
      renderPresetsSelection();
      renderCustomizer();
    }

    function renderGenderTabs() {
      const opts = [
        ['all', t('faces.genderAll')],
        ['male', t('faces.genderMale')],
        ['female', t('faces.genderFemale')],
      ];
      mount(genderTabs, ...opts.map(([val, label]) => h('button', {
        type: 'button',
        class: genderPref === val ? 'active' : '',
        style: { flex: '1' },
        onclick: () => {
          genderPref = val;
          renderGenderTabs();
          roll();
          renderPresets();
        },
      }, label)));
    }

    function roll() {
      setCurrent(nextFresh());
    }

    function renderPresetsSelection() {
      const curCode = current ? encodeFace(current) : '';
      for (const tile of presetsGrid.children) {
        tile.classList.toggle('active', tile.dataset.code === curCode);
      }
    }

    function renderPresets() {
      clear(presetsGrid);
      candidates = Array.from({ length: PRESET_COUNT }, () => nextFresh());
      for (const desc of candidates) {
        const code = encodeFace(desc);
        presetsGrid.appendChild(h('button', {
          type: 'button',
          class: 'face-tile',
          dataset: { code },
          title: t('faces.pickFaceTitle'),
          'aria-label': t('faces.pickFaceAria', { code }),
          onclick: () => setCurrent({ ...desc }),
        }, toSvgElement(faceShapes(desc), TILE_SIZE)));
      }
      renderPresetsSelection();
    }

    function updateTrait(key, val) {
      if (!current) return;
      if (key === 'gender' && current.gender !== val) {
        if (val === 0 && current.hair >= 11) current.hair = Math.floor(Math.random() * 11);
        if (val === 1) current.beard = 0;
      }
      current[key] = val;
      seen.add(encodeFace(current));
      setCurrent(current);
    }

    function renderCustomizer() {
      if (!current) return;
      const sections = getCustomizerSections();
      const sec = sections.find((s) => s.id === activeCat) || sections[0];

      mount(catTabs, ...sections.map((s) => h('button', {
        type: 'button',
        class: 'xs ' + (s.id === sec.id ? 'active' : 'ghost'),
        onclick: () => { activeCat = s.id; renderCustomizer(); },
      }, s.label)));

      mount(controlsBox, ...sec.controls
        .filter((ctrl) => !(ctrl.key === 'beard' && current.gender === 1))
        .map((ctrl) => {
          const val = Number(current[ctrl.key] ?? 0);
          const row = h('div', { class: 'face-ctrl-items' },
            ...ctrl.items.map((item, idx) => {
              if (ctrl.type === 'swatch') {
                const titleTxt = faceText(item.title);
                return h('button', {
                  type: 'button',
                  class: 'face-swatch' + (val === idx ? ' active' : ''),
                  style: { backgroundColor: item.color },
                  title: titleTxt,
                  'aria-label': `${ctrl.label}: ${titleTxt}`,
                  onclick: () => updateTrait(ctrl.key, idx),
                });
              }
              return h('button', {
                type: 'button',
                class: 'xs face-pill' + (val === idx ? ' active' : ' ghost'),
                onclick: () => updateTrait(ctrl.key, idx),
              }, faceText(item));
            }));
          return h('div', { class: 'face-ctrl-group' },
            h('div', { class: 'face-ctrl-label' }, ctrl.label),
            row);
        }));
    }

    async function useAsAvatar() {
      if (!current || saving) return;
      saving = true;
      try {
        const blob = await facePng(current, 256);
        await ctx.setAvatar(new File([blob], 'face.png', { type: 'image/png' }));
        toast(t('ui.avatarSaved'), 'ok');
      } catch (err) {
        toast(err.message || t('ui.avatarFailed'), 'danger');
      } finally {
        saving = false;
      }
    }

    async function download() {
      if (!current) return;
      try {
        const blob = await facePng(current, 512);
        const url = URL.createObjectURL(blob);
        const link = h('a', { href: url, download: `gamehub-${encodeFace(current)}.png` });
        document.body.appendChild(link);
        link.click();
        link.remove();
        setTimeout(() => URL.revokeObjectURL(url), 10_000);
      } catch (err) {
        toast(err.message || t('faces.downloadErr'), 'danger');
      }
    }

    root.className = 'view';
    const layout = h('div', { class: 'face-layout' },
      h('section', { class: 'card face-main' },
        previewBox,
        genderTabs,
        h('button', { class: 'primary face-roll', onclick: roll }, t('faces.randomNew')),
        h('div', { class: 'col', style: { gap: '8px' } },
          h('button', { class: 'primary face-action', onclick: useAsAvatar },
            icon('check', 16), h('span', {}, t('faces.useAvatar'))),
          h('button', { class: 'ghost face-action', onclick: download },
            icon('upload', 16), h('span', {}, t('faces.downloadPng'))))),
      h('section', { class: 'face-side col', style: { gap: '12px' } },
        h('div', { class: 'card' },
          h('div', { class: 'spread', style: { marginBottom: '10px' } },
            h('span', { class: 'face-ctrl-label' }, t('faces.quickPresets')),
            h('button', { class: 'xs ghost', onclick: renderPresets },
              icon('refresh', 13), ' ' + t('faces.reroll8'))),
          presetsGrid),
        h('div', { class: 'card' }, catTabs, controlsBox)));

    mount(root, layout);
    ctx.setTopbar(h('span', { class: 'chip' }, t('faces.title')));

    renderPresets();
    roll();
  },
};

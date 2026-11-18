/* Chat nhóm kiểu Messenger: nhiều kênh, emoji, gửi ảnh, biểu cảm, trả lời,
 * đang gõ, chưa đọc.
 *
 * Mọi nội dung do người dùng gõ đều đi qua textContent (xem dom.js), không có
 * chỗ nào ghép chuỗi vào innerHTML, nên không chèn được HTML qua tin nhắn.
 */

import { agoOf, avatar, clear, dayOf, h, icon, initials, mount, timeOf } from '../dom.js';
import { EMOJI_GROUPS, KAOMOJI_LIST, getRecentEmojis, recordRecentEmoji } from '../emoji.js';
import { emojiGroupName, t } from '../i18n.js';
import { isMuted, toggleMuted } from '../notify.js';
import { prompt, resizeImageFile, toast } from '../ui.js';

const CHANNEL = 'chat';
const GROUP_WINDOW = 5 * 60;   // giây: trong khoảng này thì gộp tin cùng người
const MAX_FILE_BYTES = 15 * 1024 * 1024;
const INLINE_IMAGE_TYPES = new Set(['image/png', 'image/jpeg', 'image/gif', 'image/webp']);

function formatBytes(bytes) {
  const n = Number(bytes) || 0;
  if (n < 1024) return `${n} B`;
  if (n < 1048576) return `${Math.max(1, Math.round(n / 1024))} KB`;
  return `${(n / 1048576).toFixed(1)} MB`;
}

export default {
  async mount(root, ctx, param) {
    const { net } = ctx;
    root.className = 'view flush';

    let channels = ctx.chatChannels || [];
    let active = param || localStorage.getItem('hub.chat.room') || 'chung';
    let messages = [];
    let replyTo = null;
    let attachment = null;      // {id, w, h, preview}
    let typingUntil = new Map();
    let sending = false;

    /* ------------------------------------------------------------ khung -- */
    const channelList = h('div', { class: 'channel-list' });
    const log = h('div', { class: 'chat-log' });
    const typingBar = h('div', { class: 'typing' });
    const headBox = h('div', { class: 'chat-head' });
    const replyBar = h('div', {});
    const attachBar = h('div', {});

    const input = h('textarea', {
      class: 'composer-input',
      rows: 1,
      placeholder: t('chat.composerPlaceholder'),
      maxlength: 4000,
      oninput: () => { autoGrow(); notifyTyping(); },
      onkeydown: (event) => {
        if (event.key === 'Enter' && !event.shiftKey) {
          event.preventDefault();
          submit();
        } else if (event.key === 'Escape') {
          setReply(null);
        }
      },
      onpaste: (event) => {
        const file = [...(event.clipboardData?.files || [])][0];
        if (file) {
          event.preventDefault();
          handleUpload(file);
        }
      },
    });

    const fileInput = h('input', {
      type: 'file', accept: 'image/png,image/jpeg,image/gif,image/webp',
      class: 'hidden',
      onchange: (event) => {
        const file = event.target.files?.[0];
        if (file) uploadImage(file);
        event.target.value = '';
      },
    });

    const fileInputAny = h('input', {
      type: 'file',
      class: 'hidden',
      onchange: (event) => {
        const file = event.target.files?.[0];
        if (file) handleUpload(file);
        event.target.value = '';
      },
    });

    const emojiPop = h('div', { class: 'emoji-pop hidden' });
    const emojiWrap = h('div', { style: { position: 'relative' } },
      h('button', {
        class: 'icon ghost', title: 'Emoji', 'aria-label': t('chat.emojiAria'),
        onclick: (event) => { event.stopPropagation(); toggleEmoji(); },
      }, icon('smile')),
      emojiPop);

    const sendBtn = h('button', {
      class: 'icon primary', title: t('chat.send'), 'aria-label': t('chat.sendAria'),
      onclick: submit,
    }, icon('send'));

    const composer = h('div', { class: 'composer' },
      replyBar, attachBar,
      h('div', { class: 'composer-box' },
        h('button', {
          class: 'icon ghost', title: t('chat.sendImage'), 'aria-label': t('chat.sendImage'),
          onclick: () => fileInput.click(),
        }, icon('image')),
        h('button', {
          class: 'icon ghost', title: t('chat.sendFile'), 'aria-label': t('chat.sendFile'),
          onclick: () => fileInputAny.click(),
        }, icon('paperclip')),
        input, emojiWrap, sendBtn),
      fileInput, fileInputAny);

    let dragDepth = 0;
    const dropOverlay = h('div', { class: 'chat-drop-overlay' },
      icon('paperclip', 28),
      h('span', {}, t('chat.dropHint')));

    const chatMain = h('div', {
      class: 'chat-main',
      ondragenter: (event) => {
        if (![...(event.dataTransfer?.types || [])].includes('Files')) return;
        event.preventDefault();
        dragDepth += 1;
        chatMain.classList.add('chat-drop-active');
      },
      ondragover: (event) => {
        if (![...(event.dataTransfer?.types || [])].includes('Files')) return;
        event.preventDefault();
      },
      ondragleave: () => {
        dragDepth = Math.max(0, dragDepth - 1);
        if (!dragDepth) chatMain.classList.remove('chat-drop-active');
      },
      ondrop: (event) => {
        dragDepth = 0;
        chatMain.classList.remove('chat-drop-active');
        const file = event.dataTransfer?.files?.[0];
        if (!file) return;
        event.preventDefault();
        handleUpload(file);
      },
    }, headBox, log, typingBar, composer, dropOverlay);

    const layout = h('div', { class: 'chat-layout' },
      h('aside', { class: 'chat-rail' },
        h('div', { class: 'chat-rail-head' },
          h('div', { class: 'card-title grow', style: { margin: '0' } }, t('chat.channelsHeader')),
          h('button', {
            class: 'icon ghost', title: t('chat.newChannelTitle'), 'aria-label': t('chat.newChannelTitle'),
            onclick: createChannel,
          }, icon('plus'))),
        channelList),
      chatMain);

    mount(root, layout);
    ctx.setTopbar(h('div', { class: 'row grow' },
      h('span', { class: 'chip' }, t('chat.title')),
      h('span', { class: 'tiny muted' }, t('chat.topbarSub'))));

    /* -------------------------------------------------------- danh sách -- */
    function renderChannels() {
      clear(channelList);
      for (const channel of channels) {
        const unread = channel.unread && channel.name !== active ? channel.unread : 0;
        const muted = isMuted(channel.name);
        channelList.appendChild(h('button', {
          class: 'channel-item' + (channel.name === active ? ' active' : '')
                 + (unread ? ' unread' : '') + (muted ? ' muted' : ''),
          title: muted ? `${channel.title}${t('chat.mutedSuffix')}` : channel.title,
          onclick: () => openChannel(channel.name),
        },
          h('span', { class: 'hash' }, '#'),
          h('div', { class: 'grow', style: { minWidth: '0' } },
            h('div', { class: 'channel-name nowrap' }, channel.title),
            h('div', { class: 'channel-preview nowrap' },
              channel.preview
                ? `${channel.lastName ? channel.lastName + ': ' : ''}${channel.preview}`
                : t('chat.noMsgYet'))),
          muted ? icon('bellOff', 13) : null,
          unread
            ? h('span', { class: 'nav-badge' + (muted ? ' quiet' : '') },
                unread > 99 ? '99+' : String(unread))
            : null));
      }
      if (!channels.length) {
        channelList.appendChild(h('div', { class: 'tiny muted', style: { padding: '8px' } },
          t('chat.loadingChannels')));
      }
    }

    function renderHead() {
      const info = channels.find((c) => c.name === active);
      const muted = isMuted(active);
      const count = messages.filter((m) => !m.deleted).length;
      mount(headBox,
        h('button', {
          class: 'icon ghost chat-back-btn',
          type: 'button',
          title: t('chat.channelsHeader'),
          'aria-label': t('chat.channelsHeader'),
          onclick: () => layout.classList.remove('on-channel'),
        }, icon('arrowLeft', 18)),
        h('span', { class: 'hash muted', style: { fontSize: '18px', fontWeight: '700' } }, '#'),
        h('div', { class: 'grow' },
          h('h2', {}, info ? info.title : active),
          h('div', { class: 'tiny muted' },
            muted ? t('chat.msgCountMuted', { count }) : t('chat.msgCount', { count }))),
        h('button', {
          class: 'icon ghost' + (muted ? ' muted-on' : ''),
          title: muted ? t('chat.unmuteTip') : t('chat.muteTip'),
          'aria-label': muted ? t('chat.unmuteAria') : t('chat.muteTip'),
          'aria-pressed': String(muted),
          onclick: () => {
            const now = toggleMuted(active);
            renderHead();
            renderChannels();
            ctx.refreshBadges();
            toast(now ? t('chat.mutedToast') : t('chat.unmutedToast'),
                  now ? '' : 'ok');
          },
        }, icon(muted ? 'bellOff' : 'bell')));
    }

    /* -------------------------------------------------------- tin nhắn --- */
    function renderMessages() {
      const nearBottom = log.scrollHeight - log.scrollTop - log.clientHeight < 120;
      clear(log);
      let lastDay = '';
      let prev = null;

      for (const message of messages) {
        const day = dayOf(message.ts);
        if (day !== lastDay) {
          log.appendChild(h('div', { class: 'day-sep' }, day));
          lastDay = day;
          prev = null;
        }
        const grouped = prev
          && prev.uid === message.uid
          && message.ts - prev.ts < GROUP_WINDOW
          && !message.replyTo;
        log.appendChild(messageNode(message, grouped));
        prev = message;
      }

      if (!messages.length) {
        log.appendChild(h('div', { class: 'empty' },
          icon('chat', 34), h('p', {}, t('chat.noMsgEmpty'))));
      }
      if (nearBottom) requestAnimationFrame(() => { log.scrollTop = log.scrollHeight; });
    }

    /* Tên/màu/avatar hiển thị luôn theo bản MỚI NHẤT của người gửi (tra qua
     * ctx.directory theo uid), không đóng băng theo lúc gửi tin. message.name
     * /message.color chỉ còn dùng làm fallback cho uid không có trong
     * directory (ví dụ dữ liệu cũ từ trước khi có directory). */
    function authorOf(message) {
      const profile = ctx.directory[message.uid];
      return {
        uid: message.uid,
        name: profile?.name || message.name,
        color: profile?.color || message.color,
        avatar: profile?.avatar || null,
      };
    }

    // replyTo của tin nhắn cũ (trước khi directory tồn tại) không có uid —
    // fallback về tên đã lưu tĩnh lúc đó.
    function replyAuthorName(replyTo) {
      if (replyTo.uid && ctx.directory[replyTo.uid]) return ctx.directory[replyTo.uid].name;
      return replyTo.name;
    }

    function messageNode(message, grouped) {
      const mine = message.uid === ctx.me.uid;
      const author = authorOf(message);

      if (message.deleted) {
        return h('div', { class: 'msg' + (grouped ? ' grouped' : '') },
          h('div', { class: 'msg-gutter' },
            grouped ? null : avatar(author)),
          h('div', { class: 'msg-body' },
            grouped ? null : h('div', { class: 'msg-head' },
              h('span', { class: 'msg-author', style: { color: author.color } }, author.name),
              h('span', { class: 'msg-time' }, timeOf(message.ts))),
            h('div', { class: 'msg-text deleted' }, t('chat.deletedMsg'))));
      }

      const actions = h('div', { class: 'msg-actions' },
        ...ctx.reactions.slice(0, 4).map((emoji) => h('button', {
          title: t('chat.reactTip', { emoji }),
          onclick: () => net.send(CHANNEL, 'react', { id: message.id, emoji }),
        }, emoji)),
        h('button', {
          title: t('chat.moreReactTip'), 'aria-label': t('chat.moreReactAria'),
          onclick: (event) => openReactionPicker(event.currentTarget, message),
        }, icon('smile', 15)),
        h('button', {
          title: t('chat.replyTip'), 'aria-label': t('chat.replyTip'),
          onclick: () => setReply(message),
        }, icon('reply', 15)),
        mine ? h('button', {
          title: t('chat.deleteTip'), 'aria-label': t('chat.deleteAria'),
          onclick: () => net.send(CHANNEL, 'delete', { id: message.id }),
        }, icon('trash', 15)) : null);

      const reactions = Object.entries(message.reactions || {});
      const body = h('div', { class: 'msg-body' },
        grouped ? null : h('div', { class: 'msg-head' },
          h('span', { class: 'msg-author', style: { color: author.color } }, author.name),
          h('span', { class: 'msg-time' }, timeOf(message.ts))),
        message.replyTo ? h('div', { class: 'msg-reply' },
          icon('reply', 13),
          h('span', { class: 'nowrap' },
            `${replyAuthorName(message.replyTo)}: ${message.replyTo.text}`)) : null,
        message.text ? h('div', { class: 'msg-text' }, message.text) : null,
        message.image ? imageNode(message.image) : null,
        message.file ? fileCardNode(message.file) : null,
        reactions.length ? h('div', { class: 'reactions' },
          reactions.map(([emoji, users]) => h('button', {
            class: 'reaction' + (users.includes(ctx.me.uid) ? ' mine' : ''),
            title: t('chat.reactUsers', { n: users.length }),
            onclick: () => net.send(CHANNEL, 'react', { id: message.id, emoji }),
          }, emoji, h('span', {}, String(users.length))))) : null);

      const msgEl = h('div', {
        class: 'msg' + (grouped ? ' grouped' : ''),
        onclick: (event) => {
          if (event.target.closest('button, a, img')) return;
          const was = msgEl.classList.contains('selected');
          for (const other of log.querySelectorAll('.msg.selected')) other.classList.remove('selected');
          if (!was) msgEl.classList.add('selected');
        },
      },
        h('div', { class: 'msg-gutter' },
          grouped
            ? h('span', { class: 'msg-hover-time' }, timeOf(message.ts))
            : avatar(author)),
        body, actions);
      return msgEl;
    }

    function imageNode(image) {
      const src = `/uploads/${encodeURIComponent(image.id)}`;
      return h('img', {
        class: 'msg-image', src, alt: t('chat.imgAlt'), loading: 'lazy',
        width: image.w || null, height: image.h || null,
        onclick: () => openLightbox(src),
        onload: () => { log.scrollTop = log.scrollHeight; },
      });
    }

    function fileCardNode(file) {
      const name = file.name || 'file';
      const href = `/uploads/file/${encodeURIComponent(file.id)}?name=${encodeURIComponent(name)}`;
      const badge = (file.ext || 'FILE').toUpperCase().slice(0, 6);
      return h('a', {
        class: 'msg-file',
        href,
        download: name,
        title: t('chat.downloadFile'),
      },
        h('span', { class: 'msg-file-ext' }, badge),
        h('span', { class: 'msg-file-meta grow' },
          h('span', { class: 'msg-file-name nowrap' }, name),
          h('span', { class: 'msg-file-size' }, formatBytes(file.size))),
        h('span', { class: 'msg-file-dl' }, icon('download', 16)));
    }

    function openLightbox(src) {
      const box = h('div', { class: 'lightbox', onclick: () => box.remove() },
        h('img', { src, alt: t('chat.imgZoomAlt') }));
      document.body.appendChild(box);
    }

    function openReactionPicker(anchor, message) {
      const pop = h('div', { class: 'emoji-pop', style: { bottom: 'auto', top: '100%' } },
        h('div', { class: 'emoji-grid' },
          ctx.reactions.map((emoji) => h('button', {
            class: 'emoji-btn',
            onclick: () => {
              net.send(CHANNEL, 'react', { id: message.id, emoji });
              pop.remove();
            },
          }, emoji))));
      anchor.parentElement.appendChild(pop);
      const away = (event) => {
        if (!pop.contains(event.target)) { pop.remove(); document.removeEventListener('click', away); }
      };
      setTimeout(() => document.addEventListener('click', away), 0);
    }

    /* ------------------------------------------------------- soạn tin ---- */
    function autoGrow() {
      input.style.height = 'auto';
      input.style.height = Math.min(input.scrollHeight, 160) + 'px';
    }

    function setReply(message) {
      replyTo = message;
      clear(replyBar);
      if (!message) return;
      const preview = message.text
        || (message.file ? t('chat.fileTag', { name: message.file.name }) : t('chat.photoTag'));
      replyBar.appendChild(h('div', { class: 'reply-bar' },
        icon('reply', 14),
        h('span', { class: 'grow nowrap' },
          t('chat.replyingTo', { name: message.name, text: preview })),
        h('button', { class: 'icon ghost xs', onclick: () => setReply(null) }, icon('close', 14))));
      input.focus();
    }

    function setAttachment(info) {
      attachment = info;
      clear(attachBar);
      if (!info) return;
      if (info.kind === 'file') {
        attachBar.appendChild(h('div', { class: 'attach-bar' },
          icon('file', 18),
          h('span', { class: 'grow nowrap' }, `${info.name} (${formatBytes(info.size)})`),
          h('button', { class: 'icon ghost xs', onclick: () => setAttachment(null) },
            icon('close', 14))));
        return;
      }
      attachBar.appendChild(h('div', { class: 'attach-bar' },
        h('img', { class: 'attach-thumb', src: info.preview, alt: t('chat.imgPreviewAlt') }),
        h('span', { class: 'grow' }, t('chat.imgSize', { w: info.w, h: info.h })),
        h('button', { class: 'icon ghost xs', onclick: () => setAttachment(null) },
          icon('close', 14))));
    }

    function handleUpload(file) {
      if (!file) return;
      if (INLINE_IMAGE_TYPES.has(file.type)) {
        uploadImage(file);
      } else {
        uploadFile(file);
      }
    }

    async function uploadImage(file) {
      if (!file.type.startsWith('image/')) { toast(t('chat.imgUploadOnly'), 'danger'); return; }
      const busy = h('div', { class: 'attach-bar' }, h('span', { class: 'spinner' }),
        h('span', {}, t('chat.imgUploading')));
      mount(attachBar, busy);
      try {
        const prepared = await resizeImageFile(file, 2000, 0.85);
        const form = new FormData();
        form.append('file', prepared);
        const res = await fetch('/api/chat/upload', { method: 'POST', body: form });
        if (!res.ok) {
          let detail = t('shell.uploadFailed');
          try { detail = (await res.json()).detail || detail; } catch { /* trống */ }
          throw new Error(detail);
        }
        const info = await res.json();
        setAttachment({ ...info, kind: 'image', preview: `/uploads/${info.id}` });
        input.focus();
      } catch (err) {
        clear(attachBar);
        toast(err.message, 'danger');
      }
    }

    async function uploadFile(file) {
      if (file.size > MAX_FILE_BYTES) {
        toast(t('chat.fileTooBig'), 'danger');
        return;
      }
      const busy = h('div', { class: 'attach-bar' }, h('span', { class: 'spinner' }),
        h('span', { class: 'grow nowrap' }, `${t('chat.fileUploading')} ${file.name}`));
      mount(attachBar, busy);
      try {
        const form = new FormData();
        form.append('file', file);
        const res = await fetch('/api/chat/upload-file', { method: 'POST', body: form });
        if (!res.ok) {
          let detail = t('chat.fileUploadErr');
          try { detail = (await res.json()).detail || detail; } catch { /* trống */ }
          throw new Error(detail);
        }
        const info = await res.json();
        setAttachment({ ...info, kind: 'file' });
        input.focus();
      } catch (err) {
        clear(attachBar);
        toast(err.message, 'danger');
      }
    }

    function submit() {
      if (sending) return;
      const text = input.value.trim();
      if (!text && !attachment) return;
      sending = true;
      net.send(CHANNEL, 'say', {
        text,
        image: attachment?.kind === 'image' ? attachment.id : '',
        file: attachment?.kind === 'file' ? { id: attachment.id, name: attachment.name } : null,
        replyTo: replyTo ? replyTo.id : '',
      });
      input.value = '';
      autoGrow();
      setReply(null);
      setAttachment(null);
      emojiPop.classList.add('hidden');
      setTimeout(() => { sending = false; }, 120);
    }

    let lastTyping = 0;
    function notifyTyping() {
      const now = Date.now();
      if (now - lastTyping < 1800) return;
      lastTyping = now;
      net.send(CHANNEL, 'typing');
    }

    /* ---------------------------------------------------------- emoji ---- */
    let recentGridEl = null;

    function insertTextAtCursor(item) {
      const at = input.selectionStart ?? input.value.length;
      input.value = input.value.slice(0, at) + item + input.value.slice(at);
      input.focus();
      input.setSelectionRange(at + item.length, at + item.length);
      autoGrow();
      recordRecentEmoji(item);
      renderRecentSection();
    }

    function renderRecentSection() {
      if (!recentGridEl) return;
      clear(recentGridEl);
      const recents = getRecentEmojis();
      if (!recents.length) {
        recentGridEl.appendChild(h('div', { class: 'emoji-empty' }, t('emoji.recentEmpty')));
        return;
      }
      recentGridEl.appendChild(h('div', { class: 'emoji-grid' },
        recents.map((item) => h('button', {
          class: 'emoji-btn' + (item.length > 3 ? ' is-kaomoji' : ''),
          type: 'button',
          onclick: () => insertTextAtCursor(item),
        }, item))));
    }

    function buildEmoji() {
      clear(emojiPop);
      const body = h('div', { class: 'emoji-body' });
      const tabs = h('div', { class: 'emoji-tabs' });
      const sections = new Map();

      const tabSpecs = [
        { id: 'recent', icon: '🕒', label: emojiGroupName('Gần đây') },
        ...EMOJI_GROUPS.map((g) => ({ id: g.id, icon: g.icon, label: emojiGroupName(g.name) })),
        { id: 'kaomoji', icon: '✿', label: t('emoji.kaomojiTitle') },
      ];

      const tabButtons = tabSpecs.map((spec, idx) => h('button', {
        type: 'button',
        class: 'emoji-tab-btn' + (idx === 1 ? ' active' : ''),
        title: spec.label,
        'aria-label': spec.label,
        onclick: () => {
          tabButtons.forEach((b, i) => b.classList.toggle('active', i === idx));
          const target = sections.get(spec.id);
          if (target) body.scrollTop = Math.max(0, target.offsetTop - body.offsetTop);
        },
      }, spec.icon));
      tabs.append(...tabButtons);

      // Mục Gần đây
      recentGridEl = h('div', {});
      renderRecentSection();
      const recentSec = h('div', { class: 'emoji-sec' },
        h('div', { class: 'emoji-group-title' }, emojiGroupName('Gần đây')),
        recentGridEl);
      sections.set('recent', recentSec);
      body.appendChild(recentSec);

      // Các nhóm emoji chuẩn
      for (const group of EMOJI_GROUPS) {
        const sec = h('div', { class: 'emoji-sec' },
          h('div', { class: 'emoji-group-title' }, emojiGroupName(group.name)),
          h('div', { class: 'emoji-grid' },
            group.list.map((emoji) => h('button', {
              class: 'emoji-btn', type: 'button',
              onclick: () => insertTextAtCursor(emoji),
            }, emoji))));
        sections.set(group.id, sec);
        body.appendChild(sec);
      }

      // Kaomoji
      const kaoSec = h('div', { class: 'emoji-sec' },
        h('div', { class: 'emoji-group-title' }, t('emoji.kaomojiTitle')),
        h('div', { class: 'kaomoji-grid' },
          KAOMOJI_LIST.map((kao) => h('button', {
            class: 'kaomoji-btn', type: 'button',
            onclick: () => insertTextAtCursor(kao),
          }, kao))));
      sections.set('kaomoji', kaoSec);
      body.appendChild(kaoSec);

      emojiPop.append(tabs, body);
    }

    function toggleEmoji() {
      emojiPop.classList.toggle('hidden');
      if (!emojiPop.classList.contains('hidden')) {
        if (!emojiPop.childElementCount) buildEmoji();
        else renderRecentSection();
      }
    }

    const closeEmoji = (event) => {
      if (!emojiWrap.contains(event.target)) emojiPop.classList.add('hidden');
    };
    document.addEventListener('click', closeEmoji);

    /* ------------------------------------------------------- đang gõ ----- */
    function renderTyping() {
      const now = Date.now();
      const names = [...typingUntil.entries()]
        .filter(([, until]) => until > now)
        .map(([name]) => name);
      typingBar.textContent = names.length
        ? (names.length === 1 ? t('chat.typingOne', { name: names[0] }) : t('chat.typingMany', { n: names.length }))
        : '';
    }
    const typingTimer = setInterval(renderTyping, 1000);

    /* ---------------------------------------------------------- kênh ----- */
    function openChannel(name) {
      active = name;
      ctx.chatActive = name;      // vỏ dùng để bỏ qua thông báo của kênh đang mở
      localStorage.setItem('hub.chat.room', name);
      layout.classList.add('on-channel');
      messages = [];
      renderChannels();
      renderHead();
      mount(log, h('div', { class: 'empty' }, h('span', { class: 'spinner' })));
      net.send(CHANNEL, 'join', { room: name });
      if (location.hash !== `#/chat/${name}`) {
        history.replaceState(null, '', `#/chat/${name}`);
      }
    }

    async function createChannel() {
      const title = await prompt({
        title: t('chat.newChannelTitle'),
        label: t('chat.newChannelPromptLabel'),
        okText: t('chat.newChannelPromptOk'), maxlength: 40,
      });
      if (title) net.send(CHANNEL, 'create', { title });
    }

    /* ----------------------------------------------------------- mạng ---- */
    const stop = net.on(CHANNEL, (msg) => {
      if (msg.t === 'channels') {
        channels = msg.channels;
        ctx.chatChannels = msg.channels;
        renderChannels();
        renderHead();
      } else if (msg.t === 'history') {
        if (msg.room !== active) return;
        messages = msg.messages;
        renderMessages();
        renderHead();
        requestAnimationFrame(() => { log.scrollTop = log.scrollHeight; });
      } else if (msg.t === 'message') {
        messages.push(msg.message);
        renderMessages();
        renderHead();
        if (msg.message.uid !== ctx.me.uid) {
          // Âm thanh do main.js phát (gói 'notify' của channel hub), vì nó đến
          // được cả khi người dùng đang ở app khác. Ở đây chỉ dọn "đang gõ".
          typingUntil.delete(msg.message.name);
          renderTyping();
        }
        net.send(CHANNEL, 'read');
      } else if (msg.t === 'update') {
        const at = messages.findIndex((m) => m.id === msg.message.id);
        if (at >= 0) { messages[at] = msg.message; renderMessages(); }
      } else if (msg.t === 'typing') {
        if (msg.uid === ctx.me.uid) return;
        typingUntil.set(msg.name, Date.now() + 3200);
        renderTyping();
      } else if (msg.t === 'created') {
        openChannel(msg.room);
        toast(t('chat.channelCreated'), 'ok');
      } else if (msg.t === 'error') {
        toast(msg.message, 'danger');
      }
    });

    // Tên/màu/avatar của bất kỳ ai đổi thì vẽ lại lịch sử đang mở — main.js
    // đã cập nhật ctx.directory trước khi các listener 'hub' khác chạy.
    const stopDirectory = net.on('hub', (msg) => {
      if (msg.t === 'directory' || msg.t === 'avatar-changed') renderMessages();
    });

    const rejoin = () => net.send(CHANNEL, 'join', { room: active });
    const stopRejoin = net.onRejoin(rejoin);

    renderChannels();
    renderHead();
    openChannel(active);
    net.send(CHANNEL, 'channels');
    autoGrow();
    input.focus();

    return () => {
      stop();
      stopDirectory();
      stopRejoin();
      clearInterval(typingTimer);
      document.removeEventListener('click', closeEmoji);
      ctx.chatActive = '';
      net.send(CHANNEL, 'leave');
    };
  },
};

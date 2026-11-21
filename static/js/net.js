/* Client realtime đa tầng của Game Hub.
 *
 * Luôn ưu tiên kết nối WebSocket (/ws) trước. Nếu mạng công ty / tường lửa
 * chặn WebSocket handshake, tự động chuyển sang HTTP Realtime Fallback:
 *   - Tầng 2: SSE Stream (/api/rt/stream) + Batch POST (/api/rt/send)
 *   - Tầng 3: HTTP Long-Polling (/api/rt/poll) + Piggybacked POST (/api/rt/send)
 *
 * Mọi view chỉ gọi send(), on(), onStatus(), onRejoin() — hoàn toàn trong suốt.
 */

export class Net {
  constructor() {
    this.sock = null;
    this.es = null;
    this.pollAbort = null;
    this.uid = '';
    this.name = '';
    this.token = '';
    this.sid = '';
    this.lastSeq = 0;
    this.mode = 'ws';               // 'ws' | 'sse' | 'poll'
    this.handlers = new Map();      // channel -> Set<fn>
    this.rejoiners = new Set();     // fn gọi lại sau khi nối lại
    this.statusFns = new Set();
    this.pingFns = new Set();
    this.pingMs = null;
    this.avgPingMs = null;
    this.jitterMs = null;
    this._lastPingAt = 0;
    this.delay = 400;
    this.pingTimer = null;
    this.retryTimer = null;
    this.wsHandshakeTimer = null;
    this.sseProbeTimer = null;
    this.closing = false;
    this.ready = false;
    this.flushing = false;
    this.queue = [];                // mảng object gói tin chờ gửi

    if (typeof window !== 'undefined') {
      window.addEventListener('pagehide', () => this._beaconClose());
      if (typeof document !== 'undefined') {
        document.addEventListener('visibilitychange', () => {
          if (!document.hidden && this.ready) {
            this.measurePing();
          }
        });
      }
    }
  }

  identify(uid, name, token = '') {
    this.uid = uid;
    this.name = name;
    if (token) this.token = token;
  }

  transportMode() {
    return this.mode;
  }

  /* --- đăng ký nghe ------------------------------------------------------- */
  on(channel, fn) {
    if (!this.handlers.has(channel)) this.handlers.set(channel, new Set());
    this.handlers.get(channel).add(fn);
    return () => this.handlers.get(channel)?.delete(fn);
  }

  onStatus(fn) {
    this.statusFns.add(fn);
    fn(this.ready, this.mode);
    return () => this.statusFns.delete(fn);
  }

  onPing(fn) {
    this.pingFns.add(fn);
    fn({ ms: this.pingMs, avg: this.avgPingMs, jitter: this.jitterMs, mode: this.mode, ready: this.ready });
    return () => this.pingFns.delete(fn);
  }

  /** View gọi hàm này để tự vào lại phòng sau khi mất kết nối. */
  onRejoin(fn) {
    this.rejoiners.add(fn);
    return () => this.rejoiners.delete(fn);
  }

  _emitStatus() {
    for (const fn of this.statusFns) {
      try { fn(this.ready, this.mode); } catch { /* bỏ qua */ }
    }
    this._emitPing();
  }

  _emitPing() {
    const info = { ms: this.pingMs, avg: this.avgPingMs, jitter: this.jitterMs, mode: this.mode, ready: this.ready };
    for (const fn of this.pingFns) {
      try { fn(info); } catch { /* bỏ qua */ }
    }
  }

  _recordPing(rawMs) {
    if (!Number.isFinite(rawMs)) return;
    const ms = Math.max(1, Math.round(rawMs));
    if (this.pingMs !== null) {
      const diff = Math.abs(ms - this.pingMs);
      this.jitterMs = this.jitterMs === null ? diff : Math.round(this.jitterMs * 0.7 + diff * 0.3);
    } else {
      this.jitterMs = 0;
    }
    this.pingMs = ms;
    this.avgPingMs = this.avgPingMs === null ? ms : Math.round(this.avgPingMs * 0.7 + ms * 0.3);
    this._emitPing();
  }

  measurePing() {
    if (!this.ready || this.closing) return;
    const now = typeof performance !== 'undefined' ? performance.now() : Date.now();
    this._lastPingAt = now;
    this.send('hub', 'ping', { ts: now });
  }

  _startPingLoop() {
    clearInterval(this.pingTimer);
    this.measurePing();
    this.pingTimer = setInterval(() => {
      if (!this.ready || this.closing) return;
      if (typeof document !== 'undefined' && document.hidden) {
        const now = typeof performance !== 'undefined' ? performance.now() : Date.now();
        if (now - this._lastPingAt < 18000) return;
      }
      this.measurePing();
    }, 5000);
  }

  _dispatchMsg(msg) {
    if (!msg || typeof msg !== 'object') return;
    const listeners = this.handlers.get(msg.ch);
    if (!listeners) return;
    for (const fn of listeners) {
      try { fn(msg); } catch (err) { console.error('handler lỗi', msg.ch, msg.t, err); }
    }
  }

  _runRejoiners() {
    for (const fn of this.rejoiners) {
      try { fn(); } catch { /* một view lỗi không được chặn các view khác */ }
    }
  }

  /* --- gửi / nhận -------------------------------------------------------- */
  send(channel, type, data = {}) {
    const msg = { ch: channel, t: type, ...data };
    if (this.mode === 'ws' && this.sock && this.sock.readyState === WebSocket.OPEN) {
      this.sock.send(JSON.stringify(msg));
      return;
    }
    if (this.queue.length < 40) this.queue.push(msg);
    if (this.mode !== 'ws' && this.ready && this.sid) {
      this._flushHttpQueue();
    }
  }

  /* --- kết nối & điều phối đa tầng --------------------------------------- */
  _clearTransports() {
    clearTimeout(this.retryTimer);
    clearTimeout(this.wsHandshakeTimer);
    clearTimeout(this.sseProbeTimer);
    clearInterval(this.pingTimer);
    this.retryTimer = null;
    this.wsHandshakeTimer = null;
    this.sseProbeTimer = null;
    this.pingTimer = null;

    if (this.sock) {
      const s = this.sock;
      this.sock = null;
      s.onopen = s.onmessage = s.onclose = s.onerror = null;
      try { s.close(); } catch { /* bỏ qua */ }
    }
    if (this.es) {
      const es = this.es;
      this.es = null;
      try { es.close(); } catch { /* bỏ qua */ }
    }
    if (this.pollAbort) {
      this.pollAbort.abort();
      this.pollAbort = null;
    }
  }

  connect() {
    this.closing = false;
    this._clearTransports();
    this._connectWs();
  }

  _scheduleReconnect() {
    if (this.closing) return;
    this._clearTransports();
    this.ready = false;
    this._emitStatus();
    this.retryTimer = setTimeout(() => this.connect(), this.delay);
    this.delay = Math.min(this.delay * 2, 5000);
  }

  /* --- Tầng 1: WebSocket -------------------------------------------------- */
  _connectWs() {
    this.mode = 'ws';
    const scheme = location.protocol === 'https:' ? 'wss' : 'ws';
    const query = `uid=${encodeURIComponent(this.uid)}&name=${encodeURIComponent(this.name)}&token=${encodeURIComponent(this.token || '')}`;
    let sock;
    try {
      sock = new WebSocket(`${scheme}://${location.host}/ws?${query}`);
    } catch {
      this._connectHttpFallback();
      return;
    }
    this.sock = sock;
    let opened = false;
    let fellBack = false;

    const triggerFallback = () => {
      if (opened || fellBack || this.closing) return;
      fellBack = true;
      clearTimeout(this.wsHandshakeTimer);
      if (this.sock === sock) {
        this.sock = null;
        sock.onopen = sock.onmessage = sock.onclose = sock.onerror = null;
        try { sock.close(); } catch { /* bỏ qua */ }
      }
      this._connectHttpFallback();
    };

    // Nếu proxy công ty treo handshake > 3.2s thì chuyển ngay sang HTTP Fallback.
    this.wsHandshakeTimer = setTimeout(triggerFallback, 3200);

    sock.onopen = () => {
      if (fellBack || this.closing) {
        try { sock.close(); } catch { /* bỏ qua */ }
        return;
      }
      opened = true;
      clearTimeout(this.wsHandshakeTimer);
      this.mode = 'ws';
      this.delay = 400;
      this.ready = true;
      this._emitStatus();
      while (this.queue.length) {
        sock.send(JSON.stringify(this.queue.shift()));
      }
      this._runRejoiners();
      this._startPingLoop();
    };

    sock.onmessage = (event) => {
      let msg;
      try { msg = JSON.parse(event.data); } catch { return; }
      if (msg && msg.ch === 'hub' && msg.t === 'pong' && typeof msg.ts === 'number') {
        const now = typeof performance !== 'undefined' ? performance.now() : Date.now();
        this._recordPing(now - msg.ts);
      }
      this._dispatchMsg(msg);
    };

    sock.onclose = () => {
      if (this.closing || fellBack) return;
      if (!opened) {
        // Bị từ chối ngay lúc handshake 101 -> chuyển sang SSE / Long-Polling.
        triggerFallback();
        return;
      }
      clearInterval(this.pingTimer);
      this.ready = false;
      this._emitStatus();
      this.retryTimer = setTimeout(() => this.connect(), this.delay);
      this.delay = Math.min(this.delay * 2, 5000);
    };

    sock.onerror = () => { /* onclose hoặc timer sẽ kích hoạt fallback */ };
  }

  /* --- Tầng 2 & 3: HTTP Realtime Fallback (SSE -> Long-Polling) ----------- */
  async _connectHttpFallback() {
    if (this.closing) return;
    this.mode = 'poll';
    this.sid = '';
    this.lastSeq = 0;

    try {
      const res = await fetch('/api/rt/open', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ uid: this.uid, name: this.name, token: this.token || '' }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      if (this.closing) return;

      if (data.fatal) {
        this._dispatchMsg(data.fatal);
        if (data.fatal.code === 'uid_conflict') {
          this.retryTimer = setTimeout(() => this.connect(), 400);
        }
        return;
      }

      this.sid = data.sid;
      this.delay = 400;
      this.ready = true;
      this._emitStatus();
      this._deliverBatch(data.seq, data.messages);
      this._runRejoiners();
      this._flushHttpQueue();

      if (typeof EventSource !== 'undefined') {
        this._startSse();
      } else {
        this._startPoll();
      }
    } catch {
      this._scheduleReconnect();
    }
  }

  _deliverBatch(seq, messages) {
    if (!Array.isArray(messages) || !messages.length) {
      if (typeof seq === 'number' && seq > this.lastSeq) this.lastSeq = seq;
      return;
    }
    const hasPerMsgSeq = messages.some((m) => m && typeof m._seq === 'number');
    if (!hasPerMsgSeq) {
      if (typeof seq === 'number' && seq > 0) {
        if (seq <= this.lastSeq) return;
        this.lastSeq = seq;
      }
    }
    for (const msg of messages) {
      if (!msg || typeof msg !== 'object') continue;
      if (typeof msg._seq === 'number') {
        if (msg._seq <= this.lastSeq) continue;
        this.lastSeq = msg._seq;
      }
      if (msg.ch === 'hub' && msg.t === 'pong' && typeof msg.ts === 'number') {
        const now = typeof performance !== 'undefined' ? performance.now() : Date.now();
        this._recordPing(now - msg.ts);
      }
      this._dispatchMsg(msg);
    }
    if (typeof seq === 'number' && seq > this.lastSeq) {
      this.lastSeq = seq;
    }
  }

  _startSse() {
    if (this.closing || !this.sid) return;
    const url = `/api/rt/stream?sid=${encodeURIComponent(this.sid)}&ack=${this.lastSeq}`;
    const es = new EventSource(url);
    this.es = es;
    let sseReady = false;

    const fallbackToPoll = () => {
      if (this.closing || this.es !== es) return;
      clearTimeout(this.sseProbeTimer);
      clearInterval(this.pingTimer);
      this.es = null;
      try { es.close(); } catch { /* bỏ qua */ }
      this._startPoll();
    };

    // Nếu tường lửa công ty giữ buffer stream > 2.5s không nhả event 'ready' -> sang Long-Polling.
    this.sseProbeTimer = setTimeout(() => {
      if (!sseReady) fallbackToPoll();
    }, 2500);

    es.addEventListener('ready', () => {
      if (this.es !== es || this.closing) return;
      sseReady = true;
      clearTimeout(this.sseProbeTimer);
      this.mode = 'sse';
      this._emitStatus();
      this._startPingLoop();
    });

    es.onmessage = (event) => {
      if (this.es !== es || this.closing) return;
      try {
        const data = JSON.parse(event.data);
        this._deliverBatch(data.seq, data.messages);
      } catch { /* bỏ qua frame lỗi */ }
    };

    es.onerror = () => {
      if (this.es !== es || this.closing) return;
      if (!sseReady) {
        fallbackToPoll();
      } else {
        // Mất kết nối khi đang chạy SSE -> thử mở lại từ đầu (ưu tiên WS lại).
        this._beaconClose();
        this._scheduleReconnect();
      }
    };
  }

  async _startPoll() {
    if (this.closing || !this.sid) return;
    this.mode = 'poll';
    this._emitStatus();
    this._startPingLoop();

    const ctrl = new AbortController();
    this.pollAbort = ctrl;
    let errors = 0;

    while (!this.closing && this.sid && this.pollAbort === ctrl) {
      try {
        const url = `/api/rt/poll?sid=${encodeURIComponent(this.sid)}&ack=${this.lastSeq}`;
        const res = await fetch(url, { signal: ctrl.signal, cache: 'no-store' });
        if (res.status === 404 || res.status === 410) {
          this.sid = '';
          this._scheduleReconnect();
          return;
        }
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();
        errors = 0;
        this._deliverBatch(data.seq, data.messages);
      } catch (err) {
        if (ctrl.signal.aborted || this.closing) return;
        errors += 1;
        if (errors >= 3) {
          this._beaconClose();
          this._scheduleReconnect();
          return;
        }
        await new Promise((r) => setTimeout(r, 400 * errors));
      }
    }
  }

  async _flushHttpQueue() {
    if (this.flushing || !this.ready || !this.sid || this.mode === 'ws') return;
    this.flushing = true;
    try {
      while (this.queue.length && this.ready && this.sid && !this.closing && this.mode !== 'ws') {
        const batch = this.queue.splice(0, 20);
        try {
          const res = await fetch('/api/rt/send', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ sid: this.sid, ack: this.lastSeq, messages: batch }),
          });
          if (res.status === 404 || res.status === 410) {
            this.queue.unshift(...batch);
            this.sid = '';
            this._scheduleReconnect();
            return;
          }
          if (!res.ok) throw new Error(`HTTP ${res.status}`);
          const data = await res.json();
          this._deliverBatch(data.seq, data.messages);
        } catch {
          this.queue.unshift(...batch);
          await new Promise((r) => setTimeout(r, 450));
          if (!this.sid || this.closing) return;
        }
      }
    } finally {
      this.flushing = false;
    }
  }

  _beaconClose() {
    const sid = this.sid;
    if (!sid) return;
    this.sid = '';
    try {
      if (typeof navigator !== 'undefined' && navigator.sendBeacon) {
        const blob = new Blob([JSON.stringify({ sid })], { type: 'application/json' });
        navigator.sendBeacon('/api/rt/close', blob);
      } else {
        fetch('/api/rt/close', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ sid }),
          keepalive: true,
        }).catch(() => {});
      }
    } catch { /* bỏ qua */ }
  }

  close() {
    this.closing = true;
    this._clearTransports();
    this._beaconClose();
  }
}

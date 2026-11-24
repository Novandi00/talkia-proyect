// frontend/tts_provider.js — Prioridad: 1) Piper WASM Local Neural (Offline) -> 2) Web Speech API Fallback
export class TTSProvider {
  constructor({ store, piperWorkerUrl = "/piper-worker.js", cooldownMs = 350, speechRate = 0.95 }) {
    this.store = store;
    this.cooldownMs = cooldownMs;
    this.speechRate = speechRate;
    this.lastSpokenAt = 0;
    this.audioCtx = null;
    this.piperReady = false;
    this.worker = null;
    this._initPiperWorker(piperWorkerUrl);
  }

  _initPiperWorker(workerUrl) {
    if (typeof Worker === "undefined") return;
    try {
      this.worker = new Worker(workerUrl, { type: "module" });
      this.worker.onmessage = (ev) => {
        if (ev.data?.type === "READY") this.piperReady = true;
      };
      this.worker.onerror = () => {
        this.piperReady = false;
      };
      this.worker.postMessage({ type: "INIT", model: "es_AR-daniela-high.onnx" });
    } catch {
      this.piperReady = false;
    }
  }

  async speak(sentence) {
    const clean = String(sentence || "").trim();
    if (!clean) return { engine: "none" };

    const now = performance.now();
    if (now - this.lastSpokenAt < this.cooldownMs) {
      return { engine: "debounced" };
    }
    this.lastSpokenAt = now;

    try {
      const cachedWav = await this.store?.getAudioBuffer(clean);
      if (cachedWav) {
        await this._playWavBuffer(cachedWav);
        return { engine: "piper-cache" };
      }
      if (this.piperReady && this.worker) {
        const wavBuffer = await this._synthesizeWithPiper(clean, 450);
        await this.store?.putAudioBuffer(clean, wavBuffer);
        await this._playWavBuffer(wavBuffer);
        return { engine: "piper-wasm" };
      }
    } catch {
      // Fallback a Web Speech
    }

    return this._speakWithBrowser(clean);
  }

  _synthesizeWithPiper(text, timeoutMs) {
    return new Promise((resolve, reject) => {
      const reqId = crypto.randomUUID();
      const timer = setTimeout(() => reject(new Error("Piper timeout")), timeoutMs);
      const handler = (ev) => {
        if (ev.data?.reqId !== reqId) return;
        clearTimeout(timer);
        this.worker.removeEventListener("message", handler);
        ev.data.wavBuffer ? resolve(ev.data.wavBuffer) : reject(new Error("Empty WAV"));
      };
      this.worker.addEventListener("message", handler);
      this.worker.postMessage({ type: "SYNTHESIZE", reqId, text });
    });
  }

  async _playWavBuffer(arrayBuffer) {
    if (!this.audioCtx) {
      const Ctx = window.AudioContext || window.webkitAudioContext;
      this.audioCtx = new Ctx();
    }
    if (this.audioCtx.state === "suspended") await this.audioCtx.resume();
    const decoded = await this.audioCtx.decodeAudioData(arrayBuffer.slice(0));
    const source = this.audioCtx.createBufferSource();
    source.buffer = decoded;
    source.playbackRate.value = this.speechRate;
    source.connect(this.audioCtx.destination);
    source.start(0);
  }

  _speakWithBrowser(text) {
    if (!("speechSynthesis" in window)) return { engine: "unavailable" };
    window.speechSynthesis.cancel();
    const utter = new SpeechSynthesisUtterance(text);
    const voices = window.speechSynthesis.getVoices();
    const preferred =
      voices.find((v) => v.lang === "es-AR" && v.localService) ||
      voices.find((v) => v.lang === "es-AR") ||
      voices.find((v) => v.lang.startsWith("es-"));
    if (preferred) utter.voice = preferred;
    utter.lang = preferred?.lang || "es-AR";
    utter.rate = this.speechRate;
    window.speechSynthesis.speak(utter);
    return { engine: "web-speech-fallback" };
  }
}

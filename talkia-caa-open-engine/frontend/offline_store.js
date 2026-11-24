// frontend/offline_store.js — Persistencia Local IndexedDB (< 15ms)
export class TalkiaOfflineStore {
  constructor(dbName = "talkia_caa_v2") {
    this.dbName = dbName;
    this.dbPromise = this._open();
  }

  _open() {
    return new Promise((resolve, reject) => {
      const req = indexedDB.open(this.dbName, 1);
      req.onupgradeneeded = () => {
        const db = req.result;
        if (!db.objectStoreNames.contains("pictograms")) db.createObjectStore("pictograms", { keyPath: "word" });
        if (!db.objectStoreNames.contains("boards")) db.createObjectStore("boards", { keyPath: "cacheKey" });
        if (!db.objectStoreNames.contains("tts_audio")) db.createObjectStore("tts_audio");
        if (!db.objectStoreNames.contains("pending_commits")) {
          db.createObjectStore("pending_commits", { keyPath: "idempotency_key" });
        }
      };
      req.onsuccess = () => resolve(req.result);
      req.onerror = () => reject(req.error);
    });
  }

  async putBoard(cacheKey, payload) {
    const db = await this.dbPromise;
    const tx = db.transaction(["boards", "pictograms"], "readwrite");
    tx.objectStore("boards").put({ cacheKey, payload, ts: Date.now() });
    for (const item of payload.fringe_items || []) {
      tx.objectStore("pictograms").put(item);
    }
  }

  async getBoard(cacheKey) {
    const db = await this.dbPromise;
    return new Promise((resolve) => {
      const req = db.transaction("boards", "readonly").objectStore("boards").get(cacheKey);
      req.onsuccess = () => resolve(req.result?.payload || null);
      req.onerror = () => resolve(null);
    });
  }

  async getAudioBuffer(sentence) {
    const db = await this.dbPromise;
    return new Promise((resolve) => {
      const req = db.transaction("tts_audio", "readonly").objectStore("tts_audio").get(sentence);
      req.onsuccess = () => resolve(req.result || null);
      req.onerror = () => resolve(null);
    });
  }

  async putAudioBuffer(sentence, wavBuffer) {
    const db = await this.dbPromise;
    db.transaction("tts_audio", "readwrite").objectStore("tts_audio").put(wavBuffer, sentence);
  }

  async enqueueOfflineCommit(commitEvent) {
    const db = await this.dbPromise;
    db.transaction("pending_commits", "readwrite").objectStore("pending_commits").put(commitEvent);
  }
}

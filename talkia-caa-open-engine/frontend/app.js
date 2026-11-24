// frontend/app.js — Controlador Principal CAA v2.0 (Core LAMP + Fringe + ARASAAC + TTS Resiliente)
import { assertValidStepPayload } from "./contracts.js";
import { TalkiaOfflineStore } from "./offline_store.js";
import { TTSProvider } from "./tts_provider.js";

const API_BASE = "http://localhost:8000";
const store = new TalkiaOfflineStore();
const tts = new TTSProvider({ store });

// Vocabulario Core Fijo LAMP 2x6 (Principio LAMP: posiciones fijas para memoria motora)
const LOCAL_CORE_SLOTS = [
  { word: "yo", label: "Yo", fitzgerald_category: "pronoun", arasaac_id: 31807 },
  { word: "vos", label: "Vos", fitzgerald_category: "pronoun", arasaac_id: 12264 },
  { word: "quiero", label: "Quiero", fitzgerald_category: "verb", arasaac_id: 5441 },
  { word: "necesito", label: "Necesito", fitzgerald_category: "verb", arasaac_id: 37160 },
  { word: "ir", label: "Ir", fitzgerald_category: "verb", arasaac_id: 2432 },
  { word: "ayuda", label: "Ayuda", fitzgerald_category: "social", arasaac_id: 32648 },
  { word: "sí", label: "Sí", fitzgerald_category: "social", arasaac_id: 5584 },
  { word: "no", label: "No", fitzgerald_category: "negation", arasaac_id: 5526 },
  { word: "más", label: "Más", fitzgerald_category: "adjective", arasaac_id: 5508 },
  { word: "parar", label: "Parar", fitzgerald_category: "negation", arasaac_id: 7196 },
  { word: "me_gusta", label: "Me gusta", fitzgerald_category: "verb", arasaac_id: 37815 },
  { word: "ahora", label: "Ahora", fitzgerald_category: "adjective", arasaac_id: 32747 }
];

const state = {
  sessionId: null,
  trigger: "conversacion",
  intent: "pregunta",
  scenario: "general",
  contextPath: [],
  coreSlots: LOCAL_CORE_SLOTS,
  fringeItems: [],
  candidateWords: [],
  constructedSentence: "¡Hola! ¿Cómo estás?",
  confidenceScore: 0.92,
  isOnline: true,
  stepStartTime: Date.now()
};

function renderPicto(item) {
  if (item.arasaac_id) {
    return `<img class="caa-picto" src="https://static.arasaac.org/pictograms/${item.arasaac_id}/${item.arasaac_id}_500.png" alt="" loading="lazy" onerror="this.style.display='none'" />`;
  }
  if (item.inline_svg) {
    return `<div class="caa-svg-icon">${item.inline_svg}</div>`;
  }
  return `<span class="caa-picto-fallback">💬</span>`;
}

async function apiRequest(endpoint, payload) {
  try {
    const res = await fetch(`${API_BASE}${endpoint}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
      signal: AbortSignal.timeout(1200)
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    state.isOnline = true;
    updateSyncStatus("⚡ Modo Online");
    return data;
  } catch (err) {
    state.isOnline = false;
    updateSyncStatus("🌙 Modo Local (Offline)");
    return null;
  }
}

function updateSyncStatus(text) {
  const pill = document.getElementById("sync-pill");
  if (pill) pill.textContent = text;
}

async function startNewSession() {
  const data = await apiRequest("/session/start", {
    trigger_type: state.trigger,
    conversation_intent: state.intent,
    scenario: state.scenario,
    timestamp: new Date().toISOString()
  });

  if (data && data.payload) {
    assertValidStepPayload(data.payload);
    state.sessionId = data.session_id;
    state.candidateWords = data.payload.candidate_words;
    state.fringeItems = data.payload.fringe_items || [];
    state.constructedSentence = data.payload.constructed_sentence;
    state.confidenceScore = data.payload.confidence_score;
    if (data.core_board) state.coreSlots = data.core_board;
  } else {
    // Respaldo determinista offline
    state.candidateWords = ["agua", "comer", "descansar", "baño", "mamá", "papá", "amigo", "feliz", "triste", "música"];
    state.fringeItems = state.candidateWords.map(w => ({
      word: w,
      label: w.replace("_", " "),
      fitzgerald_category: "noun"
    }));
  }
  renderUI();
}

async function handleWordSelection(word, source) {
  const latency = Math.round(Date.now() - state.stepStartTime);
  state.contextPath.push(word);
  state.stepStartTime = Date.now();

  if (state.sessionId && state.isOnline) {
    const data = await apiRequest("/session/step", {
      session_id: state.sessionId,
      selected_word: word,
      word_source: source,
      latency_ms: latency,
      conversation_intent: state.intent,
      scenario: state.scenario
    });

    if (data && data.payload) {
      assertValidStepPayload(data.payload);
      state.candidateWords = data.payload.candidate_words;
      state.fringeItems = data.payload.fringe_items || [];
      state.constructedSentence = data.payload.constructed_sentence;
      state.confidenceScore = data.payload.confidence_score;
      renderUI();
      return;
    }
  }

  // Fallback offline de construcción de frase
  const clean = state.contextPath.map(w => w.replace(/_/g, " ")).join(" ");
  state.constructedSentence = clean.charAt(0).toUpperCase() + clean.slice(1) + ".";
  renderUI();
}

async function handleCommit() {
  await tts.speak(state.constructedSentence);

  if (state.sessionId && state.isOnline) {
    await apiRequest("/session/commit", {
      session_id: state.sessionId,
      final_phrase: state.constructedSentence,
      idempotency_key: crypto.randomUUID()
    });
  } else {
    await store.enqueueOfflineCommit({
      idempotency_key: crypto.randomUUID(),
      trigger: state.trigger,
      phrase: state.constructedSentence,
      timestamp: Date.now()
    });
  }
}

function renderUI() {
  document.getElementById("constructed-sentence").textContent = state.constructedSentence;
  document.getElementById("fringe-confidence").textContent = `Confianza: ${Math.round(state.confidenceScore * 100)}%`;

  // Chips
  const chipsEl = document.getElementById("word-chips");
  chipsEl.innerHTML = "";
  state.contextPath.forEach(w => {
    const span = document.createElement("span");
    span.className = "word-chip";
    span.textContent = w.replace(/_/g, " ");
    chipsEl.appendChild(span);
  });

  // Render Core Grid (LAMP Fijo)
  const coreEl = document.getElementById("core-grid");
  coreEl.innerHTML = "";
  state.coreSlots.forEach(slot => {
    const btn = document.createElement("button");
    btn.className = "caa-btn";
    btn.dataset.fk = slot.fitzgerald_category || "misc";
    btn.innerHTML = `${renderPicto(slot.pictogram || slot)}<span class="caa-label">${slot.label || slot.word}</span>`;
    btn.addEventListener("click", () => handleWordSelection(slot.word, "core"));
    coreEl.appendChild(btn);
  });

  // Render Fringe Grid (10 palabras dinámicas)
  const fringeEl = document.getElementById("fringe-grid");
  fringeEl.innerHTML = "";
  state.candidateWords.forEach((word, idx) => {
    const meta = state.fringeItems[idx] || { word, label: word.replace(/_/g, " "), fitzgerald_category: "noun" };
    const btn = document.createElement("button");
    btn.className = "caa-btn";
    btn.dataset.fk = meta.fitzgerald_category || "misc";
    btn.innerHTML = `${renderPicto(meta)}<span class="caa-label">${meta.label || word}</span>`;
    btn.addEventListener("click", () => handleWordSelection(word, "fringe"));
    fringeEl.appendChild(btn);
  });

  // Modos de conversación
  const convModesEl = document.getElementById("conversation-modes");
  convModesEl.style.display = state.trigger === "conversacion" ? "flex" : "none";
}

// Event Listeners
document.querySelectorAll(".trigger-card").forEach(card => {
  card.addEventListener("click", () => {
    document.querySelectorAll(".trigger-card").forEach(c => c.classList.remove("active"));
    card.classList.add("active");
    state.trigger = card.dataset.trigger;
    state.contextPath = [];
    startNewSession();
  });
});

document.querySelectorAll(".mode-btn").forEach(btn => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".mode-btn").forEach(b => b.classList.remove("active"));
    btn.classList.add("active");
    state.intent = btn.dataset.intent;
    state.contextPath = [];
    startNewSession();
  });
});

document.getElementById("scenario-select").addEventListener("change", (e) => {
  state.scenario = e.target.value;
  startNewSession();
});

document.getElementById("toggle-fitzgerald").addEventListener("click", function() {
  const current = document.body.getAttribute("data-fitzgerald");
  const next = current === "on" ? "off" : "on";
  document.body.setAttribute("data-fitzgerald", next);
  this.classList.toggle("active", next === "on");
});

document.getElementById("toggle-sensory").addEventListener("click", function() {
  const current = document.body.getAttribute("data-sensory");
  const next = current === "calm" ? "normal" : "calm";
  document.body.setAttribute("data-sensory", next);
  this.classList.toggle("active", next === "calm");
});

document.getElementById("btn-undo").addEventListener("click", () => {
  state.contextPath.pop();
  const clean = state.contextPath.map(w => w.replace(/_/g, " ")).join(" ");
  state.constructedSentence = clean ? clean.charAt(0).toUpperCase() + clean.slice(1) + "." : "¡Hola! ¿Cómo estás?";
  renderUI();
});

document.getElementById("btn-clear").addEventListener("click", () => {
  state.contextPath = [];
  startNewSession();
});

document.getElementById("btn-speak").addEventListener("click", handleCommit);

// Registro de Service Worker
if ("serviceWorker" in navigator) {
  navigator.serviceWorker.register("./sw.js").catch(() => {});
}

// Arranque
startNewSession();

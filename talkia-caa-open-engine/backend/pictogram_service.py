"""backend/pictogram_service.py — Resolución ARASAAC + Lematizador Rioplatense + Caché SVG (< 50ms)."""
from __future__ import annotations

import html
import json
import urllib.parse
import urllib.request
from typing import Dict, List, Optional, Tuple

from backend.repository import TalkiaRepository
from backend.schemas import PictogramMetadata

ARASAAC_SEARCH_URL = "https://api.arasaac.org/v1/pictograms/es/search/{query}"
ARASAAC_PNG_TEMPLATE = "https://static.arasaac.org/pictograms/{picto_id}/{picto_id}_500.png"

# Catálogo semilla offline de alta frecuencia en español rioplatense -> ID oficial ARASAAC + Fitzgerald Key
OFFLINE_ARASAAC_CATALOG: Dict[str, Tuple[int, str]] = {
    "hola": (6009, "social"),
    "chau": (6009, "social"),
    "gracias": (6628, "social"),
    "por_favor": (34194, "social"),
    "agua": (2248, "noun"),
    "comer": (2349, "verb"),
    "dormir": (2369, "verb"),
    "descansar": (2369, "verb"),
    "ir_al_baño": (2275, "noun"),
    "baño": (2275, "noun"),
    "mi_medicación": (2465, "noun"),
    "dolor": (2368, "adjective"),
    "duele": (2368, "verb"),
    "feliz": (32123, "adjective"),
    "triste": (35545, "adjective"),
    "cansado": (35537, "adjective"),
    "enojado": (35539, "adjective"),
    "tranquilo": (32127, "adjective"),
    "mamá": (2458, "pronoun"),
    "papá": (2497, "pronoun"),
    "doctor": (2466, "pronoun"),
    "familia": (2392, "pronoun"),
    "música": (2479, "noun"),
    "escuela": (3082, "noun"),
    "casa": (2317, "noun"),
    "yo": (31807, "pronoun"),
    "vos": (12264, "pronoun"),
    "quiero": (5441, "verb"),
    "necesito": (37160, "verb"),
    "ir": (2432, "verb"),
    "ayuda": (32648, "social"),
    "sí": (5584, "social"),
    "no": (5526, "negation"),
    "más": (5508, "adjective"),
    "parar": (7196, "negation"),
    "me_gusta": (37815, "verb"),
    "ahora": (32747, "adjective"),
}

RIOPLATENSE_LEMMA_MAP: Dict[str, str] = {
    "podés": "poder",
    "querés": "querer",
    "hacés": "hacer",
    "sentís": "sentir",
    "te_sentís": "sentir",
    "acercame": "acercar",
    "acomodame": "acomodar",
    "traeme": "traer",
    "llamá": "llamar",
    "prendé": "encender",
    "apagá": "apagar",
    "contame": "contar",
    "hablemos": "hablar",
}

FITZGERALD_HEX: Dict[str, str] = {
    "pronoun": "#eab308",   # Amarillo: Personas / Pronombres
    "verb": "#22c55e",      # Verde: Acciones / Verbos
    "noun": "#f97316",      # Naranja: Sustantivos / Objetos / Lugares
    "adjective": "#3b82f6", # Azul: Descriptores / Emociones / Tiempo
    "social": "#ec4899",    # Rosa: Expresiones sociales / Cortesía
    "question": "#a855f7",  # Violeta: Interrogativos
    "negation": "#ef4444",  # Rojo suave: Negación / Emergencia / Parar
    "misc": "#94a3b8",      # Gris neutro: Conectores
}


def classify_fitzgerald(word: str) -> str:
    clean = word.lower().strip()
    if clean in OFFLINE_ARASAAC_CATALOG:
        return OFFLINE_ARASAAC_CATALOG[clean][1]
    if clean.startswith("¿") or clean in {"qué", "cómo", "cuándo", "dónde", "quién", "cuál", "por_qué"}:
        return "question"
    if clean in {"yo", "vos", "me", "te", "nosotros", "mamá", "papá", "amigo", "doctor", "familia"}:
        return "pronoun"
    if clean in {"no", "parar", "basta", "nunca", "tampoco"}:
        return "negation"
    if clean in {"hola", "chau", "gracias", "por_favor", "perdón", "buen", "buenas", "adiós", "ayuda"}:
        return "social"
    if clean.endswith(("ar", "er", "ir")) or clean in RIOPLATENSE_LEMMA_MAP or clean in {"quiero", "tengo", "estoy", "siento", "pienso", "creo", "vamos", "puedo"}:
        return "verb"
    if clean in {"bien", "mal", "mucho", "poco", "más", "ahora", "después", "hoy", "ayer", "mañana", "frío", "calor"}:
        return "adjective"
    return "noun"


def build_accessible_fallback_svg(label: str, category: str) -> str:
    """Genera un pictograma SVG determinista, minimalista y de baja carga sensorial cuando no hay red."""
    stroke = FITZGERALD_HEX.get(category, "#94a3b8")
    glyph = html.escape(label.replace("¿", "").strip()[:2].upper() or "•")
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" role="img" aria-hidden="true">'
        f'<rect x="4" y="4" width="56" height="56" rx="14" fill="#1e293b" stroke="{stroke}" stroke-width="4"/>'
        f'<text x="32" y="39" text-anchor="middle" fill="#f8fafc" font-family="sans-serif" '
        f'font-size="22" font-weight="700">{glyph}</text></svg>'
    )


class PictogramService:
    """Resuelve pictogramas en < 5ms desde SQLite/Catálogo Local y consulta ARASAAC opcionalmente."""

    def __init__(self, repo: TalkiaRepository, allow_remote_lookup: bool = False, timeout_sec: float = 0.25) -> None:
        self.repo = repo
        self.allow_remote_lookup = allow_remote_lookup
        self.timeout_sec = timeout_sec

    @staticmethod
    def normalize_key(word: str) -> Tuple[str, str]:
        key = word.strip().lower().replace("¿", "").replace("?", "")
        lemma = RIOPLATENSE_LEMMA_MAP.get(key, key.replace("_", " "))
        return key, lemma

    def resolve_batch(self, words: List[str]) -> List[PictogramMetadata]:
        key_map = {w: self.normalize_key(w) for w in words}
        cached = self.repo.get_cached_pictograms(k for k, _ in key_map.values())
        resolved: List[PictogramMetadata] = []

        for word in words:
            norm_key, lemma = key_map[word]
            if norm_key in cached:
                item = cached[norm_key]
                resolved.append(
                    PictogramMetadata(
                        word=word,
                        label=word.replace("_", " "),
                        fitzgerald_category=item.fitzgerald_category,
                        source=item.source,
                        arasaac_id=item.arasaac_id,
                        image_url=item.image_url,
                        inline_svg=item.inline_svg,
                    )
                )
                continue

            meta = self._resolve_single_uncached(word, norm_key, lemma)
            self.repo.upsert_pictogram(norm_key, lemma, meta)
            resolved.append(meta)

        return resolved

    def _resolve_single_uncached(self, surface_word: str, norm_key: str, lemma: str) -> PictogramMetadata:
        category = classify_fitzgerald(surface_word)
        label = surface_word.replace("_", " ")

        if norm_key in OFFLINE_ARASAAC_CATALOG:
            picto_id, cat = OFFLINE_ARASAAC_CATALOG[norm_key]
            return PictogramMetadata(
                word=surface_word,
                label=label,
                fitzgerald_category=cat,
                source="arasaac",
                arasaac_id=picto_id,
                image_url=ARASAAC_PNG_TEMPLATE.format(picto_id=picto_id),
                inline_svg=build_accessible_fallback_svg(label, cat),
            )

        if self.allow_remote_lookup:
            remote_id = self._query_arasaac_remote(lemma)
            if remote_id is not None:
                return PictogramMetadata(
                    word=surface_word,
                    label=label,
                    fitzgerald_category=category,
                    source="arasaac",
                    arasaac_id=remote_id,
                    image_url=ARASAAC_PNG_TEMPLATE.format(picto_id=remote_id),
                    inline_svg=build_accessible_fallback_svg(label, category),
                )

        return PictogramMetadata(
            word=surface_word,
            label=label,
            fitzgerald_category=category,
            source="local_svg",
            arasaac_id=None,
            image_url=None,
            inline_svg=build_accessible_fallback_svg(label, category),
        )

    def _query_arasaac_remote(self, lemma: str) -> Optional[int]:
        url = ARASAAC_SEARCH_URL.format(query=urllib.parse.quote(lemma))
        req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "TalKIA-CAA/2.0"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_sec) as resp:
                if resp.status != 200:
                    return None
                payload = json.loads(resp.read().decode("utf-8"))
                if isinstance(payload, list) and payload and "_id" in payload[0]:
                    return int(payload[0]["_id"])
        except Exception:
            return None
        return None

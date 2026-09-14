"""Adaptateur Corum L'Épargne (SCPI Origin, XL, Eurion, USA).

Stratégie (validée étape 0) :
  1. Ouvrir la page /documents de la SCPI.
  2. Repérer le dernier « Fil d'Actualités » (= bulletin trimestriel). Les noms
     de fichiers PDF sont imprévisibles -> on SCRAPE les liens, on ne devine pas.
  3. Télécharger le PDF, extraire le texte (pdfplumber).
  4. Extraire un jeu ciblé de métriques par REGEX sur des phrases auto-portantes.

Choix d'extraction (fiabilité > exhaustivité) :
  Le « Fil d'Actualités » Corum est une plaquette en colonnes. pdfplumber
  entrelace les colonnes : un matching « libellé -> nombre sur la même ligne »
  donnerait des valeurs fausses. On ne retient donc QUE des motifs
  auto-portants et sans ambiguïté (ex. la phrase de calcul de la
  capitalisation). Tout le reste part en A_VERIFIER avec le lien du PDF —
  jamais de valeur devinée.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from datetime import date
from urllib.parse import unquote, urljoin

from bs4 import BeautifulSoup

from ..models import Confidence, Metric, MetricKey
from ..parsing import parse_number_fr, parse_period_quarter, quarter_end_date
from ..pdf import PdfContent, Word, extract_pdf
from ..registry import ScpiEntry
from .base import SourceAdapter, norm

# add(key, value, unit, confidence, raw, note=None, override_period=None)
AddFn = Callable[..., None]

BASE = "https://www.corum.fr"
_BULLETIN_HINT = norm("Fil d'Actualités")  # "fil d'actualites"

# Métriques qu'on CHERCHE dans un bulletin Corum. Celles non extraites de façon
# certaine sont émises en A_VERIFIER (une ligne chacune) pour peupler l'onglet.
TARGET_KEYS: tuple[str, ...] = (
    MetricKey.PRIX_SOUSCRIPTION,
    MetricKey.PRIX_RETRAIT,
    MetricKey.VALEUR_RECONSTITUTION,
    MetricKey.VALEUR_REALISATION,
    MetricKey.CAPITALISATION,
    MetricKey.NOMBRE_ASSOCIES,
    MetricKey.NOMBRE_IMMEUBLES,
    MetricKey.TOF,
    MetricKey.TAUX_DISTRIBUTION,
    MetricKey.ACOMPTE,
    MetricKey.REPORT_A_NOUVEAU,
)

_NUM = r"\d[\d\s  ]*(?:,\d+)?"

# --- Motifs sur le TEXTE À PLAT (phrases auto-portantes) ---------------------
# "7 135 382 parts * 215 € = 1,534 milliard d'euros"  (phrase de bas de page)
RE_CAP = re.compile(
    rf"(?P<parts>{_NUM})\s*parts?\s*[*x×]\s*(?P<prix>{_NUM})\s*€\s*=\s*"
    rf"(?P<cap>{_NUM})\s*(?P<mult>milliard|million)",
    re.IGNORECASE,
)
# "Valeur de reconstitution6 (par part) 222,12 €"
RE_RECONST = re.compile(rf"reconstitution\S*\s*\(par part\)\s*(?P<v>{_NUM})\s*€", re.IGNORECASE)
# "Valeur de réalisation5 (par part) 177,10 €"
RE_REAL = re.compile(rf"r[eé]alisation\S*\s*\(par part\)\s*(?P<v>{_NUM})\s*€", re.IGNORECASE)

# --- Motifs sur les CELLULES DE TABLEAUX (auto-portantes) --------------------
# "5,73 % Rendement 20252 (taux de distribution)"  -> TD de l'année
RE_TD_CELL = re.compile(rf"(?P<v>{_NUM})\s*%\s*Rendement\s*(?P<y>20\d{{2}})", re.IGNORECASE)
# "2,75 € par part Dividende brut trimestriel"      -> acompte brut du trimestre
RE_ACOMPTE_CELL = re.compile(
    rf"(?P<v>{_NUM})\s*€\s*par part\s*Dividende brut trimestriel", re.IGNORECASE
)

_MULT = {"milliard": 1_000_000_000.0, "million": 1_000_000.0}
_NOTE_COLONNES = "Non extractible de façon certaine du bulletin (mise en page en colonnes)"

# Libellés positionnels : (metric_key, mots consécutifs du libellé).
POSITIONAL = (
    (MetricKey.NOMBRE_IMMEUBLES, ("nombre", "d’immeubles")),
    (MetricKey.NOMBRE_ASSOCIES, ("associés", "au")),
)


class CorumAdapter(SourceAdapter):
    sdg_key = "corum_lepargne"

    def fetch_metrics(self, entry: ScpiEntry) -> list[Metric]:
        if not entry.documents_url:
            return self._averifier_all(entry, "documents_url absente du registry", None, None)

        html = self.client.get_text(entry.documents_url)
        found = self._find_latest_bulletin(html)
        if found is None:
            return self._averifier_all(
                entry, "Aucun « Fil d'Actualités » trouvé sur la page documents",
                entry.documents_url, None,
            )

        pdf_url, year, quarter = found
        published = quarter_end_date(year, quarter)
        period = f"{year}-T{quarter}"

        content = extract_pdf(self.client.get_bytes(pdf_url))
        if content.is_probably_scanned:
            # Origin & XL au T2-2026 : plaquette 100 % image, pas de couche texte.
            return self._averifier_all(
                entry, "Bulletin en image (pas de couche texte) — OCR non tenté", pdf_url, period
            )

        return self._extract(entry, content, pdf_url, period, published)

    # -- Repérage du bulletin -------------------------------------------------
    def _find_latest_bulletin(self, html: str) -> tuple[str, int, int] | None:
        soup = BeautifulSoup(html, "html.parser")
        candidates: list[tuple[int, int, str]] = []
        for a in soup.find_all("a", href=True):
            href = a.get("href")
            if not isinstance(href, str):
                continue
            if not href.lower().split("?")[0].endswith(".pdf"):
                continue
            # href URL-encodés (Fil%20d%27Actualit%C3%A9s) : décoder avant match.
            label = norm(f"{a.get_text(' ', strip=True)} {unquote(href)}")
            if _BULLETIN_HINT not in label:
                continue
            pq = parse_period_quarter(label)
            if pq is None:
                continue
            candidates.append((pq[0], pq[1], urljoin(BASE, href)))
        if not candidates:
            return None
        year, quarter, url = max(candidates, key=lambda c: (c[0], c[1]))
        return url, year, quarter

    # -- Extraction -----------------------------------------------------------
    def _extract(
        self, entry: ScpiEntry, content: PdfContent, pdf_url: str, period: str, published: date
    ) -> list[Metric]:
        found: dict[str, Metric] = {}

        def add(key: str, value: float, unit: str | None, conf: Confidence, raw: str,
                note: str | None = None, override_period: str | None = None) -> None:
            found[key] = Metric.ok_num(
                scpi_id=entry.scpi_id, metric_key=key, value=value, unit=unit,
                period=override_period or period, source_url=pdf_url, published_at=published,
                collected_at=self.collected_at, confidence=conf, raw=raw, note=note,
            )

        self._from_text(content.text, add)
        self._from_tables(content.table_cells(), add)
        self._from_words(content.words, add)

        # Complète avec A_VERIFIER pour chaque cible non trouvée.
        out = list(found.values())
        for key in TARGET_KEYS:
            if key not in found:
                out.append(
                    Metric.a_verifier(
                        scpi_id=entry.scpi_id, metric_key=key, source_url=pdf_url,
                        collected_at=self.collected_at, period=period,
                        note=_NOTE_COLONNES,
                    )
                )
        return out

    # -- Source 1 : texte à plat (phrases auto-portantes) --------------------
    def _from_text(self, text: str, add: AddFn) -> None:
        flat = re.sub(r"\s+", " ", text)

        m = RE_CAP.search(flat)
        if m:
            cap = parse_number_fr(m.group("cap"))
            prix = parse_number_fr(m.group("prix"))
            parts = parse_number_fr(m.group("parts"))
            if cap is not None:
                add(MetricKey.CAPITALISATION, cap * _MULT[m.group("mult").lower()],
                    "EUR", Confidence.HAUTE, m.group(0))
            if prix is not None:
                add(MetricKey.PRIX_SOUSCRIPTION, prix, "EUR", Confidence.MOYENNE, m.group(0),
                    note="Déduit du « prix de part » de la formule de capitalisation")
            if parts is not None:
                add(MetricKey.NOMBRE_PARTS, parts, "parts", Confidence.HAUTE, m.group(0))

        for key, rgx in ((MetricKey.VALEUR_RECONSTITUTION, RE_RECONST),
                         (MetricKey.VALEUR_REALISATION, RE_REAL)):
            m = rgx.search(flat)
            if m:
                v = parse_number_fr(m.group("v"))
                if v is not None:
                    add(key, v, "EUR", Confidence.HAUTE, m.group(0))

    # -- Source 2 : cellules de tableaux (auto-portantes) --------------------
    def _from_tables(self, cells: list[str], add: AddFn) -> None:
        for cell in cells:
            m = RE_TD_CELL.search(cell)
            if m:
                v = parse_number_fr(m.group("v"))
                if v is not None:
                    add(MetricKey.TAUX_DISTRIBUTION, v, "%", Confidence.HAUTE, cell,
                        override_period=m.group("y"))
            m = RE_ACOMPTE_CELL.search(cell)
            if m:
                v = parse_number_fr(m.group("v"))
                if v is not None:
                    add(MetricKey.ACOMPTE, v, "EUR", Confidence.HAUTE, cell)

    # -- Source 3 : positionnel (gros chiffre au-dessus d'un libellé) --------
    def _from_words(self, words: list[Word], add: AddFn) -> None:
        for key, label in POSITIONAL:
            hit = _number_above_label(words, label)
            if hit is not None:
                value, raw = hit
                add(key, value, None, Confidence.MOYENNE, raw,
                    note="Chiffre du bloc « en un coup d'œil » (association positionnelle)")

    # -- Helpers A_VERIFIER ---------------------------------------------------
    def _averifier_all(
        self, entry: ScpiEntry, note: str, source_url: str | None, period: str | None
    ) -> list[Metric]:
        url = source_url or entry.documents_url or entry.fiche_url or f"https://{entry.domaine}"
        return [
            Metric.a_verifier(
                scpi_id=entry.scpi_id, metric_key=key, source_url=url,
                collected_at=self.collected_at, note=note, period=period,
            )
            for key in TARGET_KEYS
        ]


def _find_label_box(
    words: list[Word], label: tuple[str, ...]
) -> tuple[int, float, float, float] | None:
    """Trouve la 1re occurrence du libellé (mots consécutifs, même ligne).

    Renvoie (page, x0_min, x1_max, top) ou None.
    """
    n = len(label)
    want = [norm(w) for w in label]
    for i in range(len(words) - n + 1):
        seq = words[i : i + n]
        if seq[0]["page"] != seq[-1]["page"]:
            continue
        if any(abs(w["top"] - seq[0]["top"]) > 4 for w in seq):
            continue
        if [norm(w["text"]) for w in seq] != want:
            continue
        return (seq[0]["page"], min(w["x0"] for w in seq),
                max(w["x1"] for w in seq), seq[0]["top"])
    return None


def _number_above_label(words: list[Word], label: tuple[str, ...]) -> tuple[float, str] | None:
    """Nombre situé juste au-dessus d'un libellé, aligné horizontalement.

    Défensif : n'associe que les jetons numériques qui recouvrent la plage x du
    libellé, sur la ligne la plus proche au-dessus. Renvoie None si rien de sûr.
    """
    box = _find_label_box(words, label)
    if box is None:
        return None
    page, lx0, lx1, ltop = box
    above = [
        w for w in words
        if w["page"] == page and 6 < (ltop - w["top"]) < 60 and re.match(r"^\d", w["text"])
    ]
    overlap = [w for w in above if w["x1"] >= lx0 and w["x0"] <= lx1]
    if not overlap:
        return None
    # Ligne la plus proche au-dessus, prise ENTIÈRE (pour ne pas tronquer un nombre).
    top_line = max(w["top"] for w in overlap)
    line = sorted((w for w in above if abs(w["top"] - top_line) <= 4), key=lambda w: w["x0"])

    # Groupes contigus (espace <= 18pt). On ne garde QUE si le groupe qui
    # recouvre le libellé tient entièrement dans sa plage x (+/-10) : sinon le
    # nombre déborde sur un callout voisin -> extraction non sûre -> None.
    runs: list[list[Word]] = [[line[0]]]
    for w in line[1:]:
        if w["x0"] - runs[-1][-1]["x1"] <= 18:
            runs[-1].append(w)
        else:
            runs.append([w])
    target: list[Word] | None = None
    for run in runs:
        if any(w in overlap for w in run):
            if target is not None:
                return None  # deux groupes recouvrent le libellé -> ambigu
            target = run
    if target is None:
        return None
    if min(w["x0"] for w in target) < lx0 - 10 or max(w["x1"] for w in target) > lx1 + 10:
        return None
    raw = " ".join(w["text"] for w in target)
    value = parse_number_fr(raw)
    return (value, raw) if value is not None else None

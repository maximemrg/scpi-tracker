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
from datetime import date
from urllib.parse import unquote, urljoin

from bs4 import BeautifulSoup

from ..models import Confidence, Metric, MetricKey
from ..parsing import parse_number_fr, parse_period_quarter, quarter_end_date
from ..pdf import extract_pdf
from ..registry import ScpiEntry
from .base import SourceAdapter, norm

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

# "7 135 382 parts * 215 € = 1,534 milliard d'euros"  (phrase de bas de page)
RE_CAP = re.compile(
    rf"(?P<parts>{_NUM})\s*parts?\s*[*x×]\s*(?P<prix>{_NUM})\s*€\s*=\s*"
    rf"(?P<cap>{_NUM})\s*(?P<mult>milliard|million)",
    re.IGNORECASE,
)
# "Valeur de reconstitution6 (par part) 222,12 €"
RE_RECONST = re.compile(
    rf"reconstitution\S*\s*\(par part\)\s*(?P<v>{_NUM})\s*€",
    re.IGNORECASE,
)
# "Dividende par part1 au 2ème trimestre 2026 2,31 €"
RE_ACOMPTE = re.compile(
    rf"dividende par part\S*\s*au\s*(?P<q>\d)\S*\s*trimestre\s*(?P<y>20\d{{2}})\s*"
    rf"(?P<v>{_NUM})\s*€",
    re.IGNORECASE,
)

_MULT = {"milliard": 1_000_000_000.0, "million": 1_000_000.0}
_NOTE_COLONNES = "Non extractible de façon certaine du bulletin (mise en page en colonnes)"


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

        return self._extract(entry, content.text, pdf_url, period, published)

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
        self, entry: ScpiEntry, text: str, pdf_url: str, period: str, published: date
    ) -> list[Metric]:
        flat = re.sub(r"\s+", " ", text)
        found: dict[str, Metric] = {}

        def add(key: str, value: float, unit: str | None, conf: Confidence, raw: str,
                note: str | None = None) -> None:
            found[key] = Metric.ok_num(
                scpi_id=entry.scpi_id, metric_key=key, value=value, unit=unit,
                period=period, source_url=pdf_url, published_at=published,
                collected_at=self.collected_at, confidence=conf, raw=raw, note=note,
            )

        m = RE_CAP.search(flat)
        if m:
            parts = parse_number_fr(m.group("parts"))
            prix = parse_number_fr(m.group("prix"))
            cap_base = parse_number_fr(m.group("cap"))
            mult = _MULT[m.group("mult").lower()]
            if cap_base is not None:
                add(MetricKey.CAPITALISATION, cap_base * mult, "EUR",
                    Confidence.HAUTE, m.group(0))
            if prix is not None:
                add(MetricKey.PRIX_SOUSCRIPTION, prix, "EUR", Confidence.MOYENNE,
                    m.group(0), note="Déduit du « prix de part » de la formule de capitalisation")
            if parts is not None:
                add(MetricKey.NOMBRE_PARTS, parts, "parts", Confidence.HAUTE, m.group(0))

        m = RE_RECONST.search(flat)
        if m:
            v = parse_number_fr(m.group("v"))
            if v is not None:
                add(MetricKey.VALEUR_RECONSTITUTION, v, "EUR", Confidence.HAUTE, m.group(0))

        m = RE_ACOMPTE.search(flat)
        if m and int(m.group("q")) == int(period.split("-T")[1]):
            v = parse_number_fr(m.group("v"))
            if v is not None:
                add(MetricKey.ACOMPTE, v, "EUR", Confidence.MOYENNE, m.group(0))

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

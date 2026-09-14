"""Adaptateur Sofidy (Immorente, Sofidy Europe Invest).

Constat (vérifié sur Immorente T2-2026) : le bulletin Sofidy est une plaquette
dont la PLUPART des KPI (TOF, prix, capitalisation, nb d'associés...) sont
dessinés dans une POLICE VECTORISÉE -> pdfplumber ne rend que des glyphes
« (cid:NN) » = non extractibles. On NE devine pas.

Approche hybride (validée) :
  - on AUTOMATISE ce qui est fiable : la découverte datée du dernier bulletin
    (alimente l'onglet Sources) ;
  - tout KPI dont la valeur est en police vectorisée ou non isolable de façon
    sûre -> A_VERIFIER (valeur nulle + lien du PDF), destiné à la saisie
    manuelle (voir scpi.manual).

Listing par SCPI : sofidy.com/documentation/{slug} (Immorente = /documentation/).
"""

from __future__ import annotations

import re
from urllib.parse import unquote, urljoin

from bs4 import BeautifulSoup

from ..models import Metric, MetricKey
from ..parsing import parse_period_quarter
from ..pdf import extract_pdf
from ..registry import ScpiEntry
from .base import SourceAdapter, norm

BASE = "https://www.sofidy.com"

TARGET_KEYS: tuple[str, ...] = (
    MetricKey.PRIX_SOUSCRIPTION, MetricKey.PRIX_RETRAIT,
    MetricKey.VALEUR_RECONSTITUTION, MetricKey.VALEUR_REALISATION,
    MetricKey.CAPITALISATION, MetricKey.NOMBRE_ASSOCIES, MetricKey.NOMBRE_IMMEUBLES,
    MetricKey.TOF, MetricKey.TAUX_DISTRIBUTION, MetricKey.ACOMPTE,
    MetricKey.REPORT_A_NOUVEAU, MetricKey.DELAI_JOUISSANCE,
)


def sofidy_period(text: str) -> tuple[int, int] | None:
    """Repère (année, trimestre) dans les formes Sofidy variées.

    Gère 'T2 2026', '2026-T2' (parse_period_quarter), plus '2026_2T', '2T2026',
    '2t24' (année sur 2 chiffres).
    """
    pq = parse_period_quarter(text)  # "T2 2026" / "2026-T2" -> (année, trimestre)
    if pq is not None:
        return pq
    m = re.search(r"(20\d{2})[\s\-_]*([1-4])\s*t(?![a-z])", text, re.IGNORECASE)  # 2026_2T
    if m:
        return int(m.group(1)), int(m.group(2))
    m = re.search(r"\b([1-4])\s*t[\s\-_]*(20\d{2})\b", text, re.IGNORECASE)  # 1T-2026 / 2T2026
    if m:
        return int(m.group(2)), int(m.group(1))
    m = re.search(r"\b([1-4])\s*t\s*(\d{2})(?!\d)", text, re.IGNORECASE)  # 2t24
    if m:
        return 2000 + int(m.group(2)), int(m.group(1))
    return None


class SofidyAdapter(SourceAdapter):
    sdg_key = "sofidy"

    def fetch_metrics(self, entry: ScpiEntry) -> list[Metric]:
        if not entry.documents_url:
            return self._averifier_all(entry, "documents_url absente du registry", None, None)

        html = self.client.get_text(entry.documents_url)
        found = self._find_latest_bulletin(html)
        if found is None:
            return self._averifier_all(
                entry, "Aucun bulletin trimestriel trouvé sur la page documents",
                entry.documents_url, None,
            )

        pdf_url, year, quarter = found
        period = f"{year}-T{quarter}"
        content = extract_pdf(self.client.get_bytes(pdf_url))
        if content.is_probably_scanned:
            return self._averifier_all(
                entry, "Bulletin en image (pas de couche texte) — OCR non tenté", pdf_url, period
            )

        # KPI en police vectorisée / non isolables -> A_VERIFIER, mais SOURCÉS
        # avec le lien exact du bulletin daté (utile pour la saisie manuelle).
        cid = "(cid:" in content.text
        note = (
            "Valeurs du bulletin en police vectorisée (non extractibles) — saisie manuelle"
            if cid else
            "Non isolable de façon certaine du bulletin — saisie manuelle"
        )
        return [
            Metric.a_verifier(
                scpi_id=entry.scpi_id, metric_key=key, source_url=pdf_url,
                collected_at=self.collected_at, note=note, period=period,
            )
            for key in TARGET_KEYS
        ]

    def _find_latest_bulletin(self, html: str) -> tuple[str, int, int] | None:
        soup = BeautifulSoup(html, "html.parser")
        candidates: list[tuple[int, int, str]] = []
        for a in soup.find_all("a", href=True):
            href = a.get("href")
            if not isinstance(href, str) or not href.lower().split("?")[0].endswith(".pdf"):
                continue
            decoded = unquote(href)
            label = norm(f"{a.get_text(' ', strip=True)} {decoded}")
            filename = decoded.lower()
            is_bulletin = "bulletin" in label and (
                "trimestriel" in label or "-bt-" in filename or "_bt_" in filename
            )
            if not is_bulletin:
                continue
            pq = sofidy_period(f"{a.get_text(' ', strip=True)} {decoded}")
            if pq is None:
                continue
            candidates.append((pq[0], pq[1], urljoin(BASE, href)))
        if not candidates:
            return None
        year, quarter, url = max(candidates, key=lambda c: (c[0], c[1]))
        return url, year, quarter

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

"""Adaptateur Inter Gestion REIM (Cristal Rente, Cristal Life).

Source = fiches HTML. Particularité : le bloc « chiffres clés » place la
VALEUR AVANT le libellé (« 255,68 € Prix de souscription », « 684 M€
Capitalisation »). On n'extrait que ces motifs sûrs ; le reste -> A_VERIFIER.
Attention : les 214,28/212,47 € sont des « Valeur IFI » (à ne PAS confondre
avec reconstitution/réalisation).
"""

from __future__ import annotations

import re
from datetime import datetime

from bs4 import BeautifulSoup

from ..models import Confidence, Metric, MetricKey
from ..parsing import parse_date_fr, parse_number_fr
from ..registry import ScpiEntry
from .base import SourceAdapter

_N = r"[\d\s  ]"

TARGET_KEYS: tuple[str, ...] = (
    MetricKey.PRIX_SOUSCRIPTION, MetricKey.PRIX_RETRAIT,
    MetricKey.VALEUR_RECONSTITUTION, MetricKey.VALEUR_REALISATION,
    MetricKey.CAPITALISATION, MetricKey.NOMBRE_ASSOCIES, MetricKey.NOMBRE_IMMEUBLES,
    MetricKey.TOF, MetricKey.TAUX_DISTRIBUTION, MetricKey.TRI_10ANS,
    MetricKey.ACOMPTE, MetricKey.REPORT_A_NOUVEAU,
)

_PRIX = re.compile(rf"({_N}*\d,\d+)\s*€\s*Prix de souscription")
_CAP = re.compile(rf"({_N}*\d(?:,\d+)?)\s*M€\s*Capitalisation")
_TRI10 = re.compile(r"TRI 10 ans de\s*(\d+,\d+)\s*%")
_TD = re.compile(r"(\d+,\d+)\s*%\s*Taux de distribution")
_DATE = re.compile(r"Donn[ée]es au\s*(\d{1,2}/\d{1,2}/\d{4})")


class InterGestionAdapter(SourceAdapter):
    sdg_key = "inter_gestion_reim"

    def fetch_metrics(self, entry: ScpiEntry) -> list[Metric]:
        url = entry.fiche_url or entry.documents_url
        if not url:
            return _av_all(
                entry, "fiche_url absente", f"https://{entry.domaine}", self.collected_at
            )
        return self._extract(entry, _flatten(self.client.get_text(url)), url)

    def _extract(self, entry: ScpiEntry, text: str, url: str) -> list[Metric]:
        mdate = _DATE.search(text)
        published = parse_date_fr(mdate.group(1)) if mdate else None
        found: dict[str, Metric] = {}

        def add(key: str, value: float, unit: str | None, conf: Confidence, raw: str,
                period: str | None = None) -> None:
            found[key] = Metric.ok_num(
                scpi_id=entry.scpi_id, metric_key=key, value=value, unit=unit,
                period=period, source_url=url, published_at=published,
                collected_at=self.collected_at, confidence=conf, raw=raw,
            )

        specs = [
            (MetricKey.PRIX_SOUSCRIPTION, _PRIX, "EUR", 1.0, Confidence.HAUTE, None),
            (MetricKey.CAPITALISATION, _CAP, "EUR", 1_000_000.0, Confidence.HAUTE, None),
            (MetricKey.TRI_10ANS, _TRI10, "%", 1.0, Confidence.HAUTE, None),
            (MetricKey.TAUX_DISTRIBUTION, _TD, "%", 1.0, Confidence.MOYENNE, "2025"),
        ]
        for key, rgx, unit, mult, conf, period in specs:
            m = rgx.search(text)
            if m:
                v = parse_number_fr(m.group(1))
                if v is not None:
                    add(key, v * mult, unit, conf, m.group(0).strip(), period)

        out = list(found.values())
        out += [
            Metric.a_verifier(
                scpi_id=entry.scpi_id, metric_key=key, source_url=url,
                collected_at=self.collected_at,
                note="Non affiché en clair sur la fiche — bulletin ou saisie manuelle",
            )
            for key in TARGET_KEYS if key not in found
        ]
        return out


def _av_all(entry: ScpiEntry, note: str, url: str, collected: datetime) -> list[Metric]:
    return [
        Metric.a_verifier(scpi_id=entry.scpi_id, metric_key=key, source_url=url,
                          collected_at=collected, note=note)
        for key in TARGET_KEYS
    ]


def _flatten(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style"]):
        tag.extract()
    return re.sub(r"\s+", " ", soup.get_text(" "))

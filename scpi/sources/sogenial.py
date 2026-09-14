"""Adaptateur Sogenial Immobilier (Cœur d'Avenir, Cœur d'Europe, Cœur de Régions).

Source = fiches HTML (KPI structurés). Motifs communs aux 3 fiches.
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
    MetricKey.TOF, MetricKey.TAUX_DISTRIBUTION, MetricKey.TRI_5ANS,
    MetricKey.ACOMPTE, MetricKey.REPORT_A_NOUVEAU, MetricKey.DELAI_JOUISSANCE,
)

_TD = re.compile(r"Taux de distribution 2025[^%]*?(\d+,\d+)\s*%")
_TRI5 = re.compile(r"TRI 5 ans\s*:?\s*(\d+,\d+)\s*%")
_RET = re.compile(rf"Valeur de retrait\s*:\s*({_N}+(?:,\d+)?)\s*€")
_SOUS = re.compile(rf"Prix de (?:souscription|la part)\s*:\s*({_N}+(?:,\d+)?)\s*€")
_CAP = re.compile(rf"({_N}+,\d+)\s*M\s*€\s*Capitalisation")
_DELAI = re.compile(r"[Dd]élai de jouissance[^.]*?du\s*(\d+)\s*(?:er|e|ème|eme)?\s*mois")
_DATE = re.compile(r"au\s*(\d{1,2}\s+\w+\s+\d{4})")


class SogenialAdapter(SourceAdapter):
    sdg_key = "sogenial_immobilier"

    def fetch_metrics(self, entry: ScpiEntry) -> list[Metric]:
        url = entry.fiche_url or entry.documents_url
        if not url:
            return _averifier_all(entry, "fiche_url absente", f"https://{entry.domaine}",
                                  self.collected_at)
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
            (MetricKey.TAUX_DISTRIBUTION, _TD, "%", 1.0, Confidence.HAUTE, "2025"),
            (MetricKey.TRI_5ANS, _TRI5, "%", 1.0, Confidence.HAUTE, None),
            (MetricKey.PRIX_RETRAIT, _RET, "EUR", 1.0, Confidence.HAUTE, None),
            (MetricKey.PRIX_SOUSCRIPTION, _SOUS, "EUR", 1.0, Confidence.HAUTE, None),
            (MetricKey.CAPITALISATION, _CAP, "EUR", 1_000_000.0, Confidence.MOYENNE, None),
            (MetricKey.DELAI_JOUISSANCE, _DELAI, "mois", 1.0, Confidence.HAUTE, None),
        ]
        for key, rgx, unit, mult, conf, period in specs:
            m = rgx.search(text)
            if m:
                v = parse_number_fr(m.group(1))
                if v is not None:
                    add(key, v * mult, unit, conf, m.group(0).strip(), period)

        out = list(found.values())
        out += _averifier_missing(entry, found, url, self.collected_at)
        return out


def _averifier_missing(
    entry: ScpiEntry, found: dict[str, Metric], url: str, collected: datetime
) -> list[Metric]:
    return [
        Metric.a_verifier(
            scpi_id=entry.scpi_id, metric_key=key, source_url=url,
            collected_at=collected,
            note="Non affiché en clair sur la fiche — bulletin ou saisie manuelle",
        )
        for key in TARGET_KEYS if key not in found
    ]


def _averifier_all(entry: ScpiEntry, note: str, url: str, collected: datetime) -> list[Metric]:
    return [
        Metric.a_verifier(
            scpi_id=entry.scpi_id, metric_key=key, source_url=url,
            collected_at=collected, note=note,
        )
        for key in TARGET_KEYS
    ]


def _flatten(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style"]):
        tag.extract()
    return re.sub(r"\s+", " ", soup.get_text(" "))

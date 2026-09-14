"""Adaptateur Kyaneos AM (Kyaneos Pierre ; Kyaneos Denormandie 5).

Source = fiche HTML de Kyaneos Pierre (prix, capitalisation, associés, délai
de jouissance). Kyaneos Denormandie 5 est une SCPI FISCALE (Denormandie) : la
plupart des métriques de rendement n'ont pas de sens et son URL n'a pas été
confirmée (série visible jusqu'à Denormandie 4) -> A_VERIFIER complet.
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
    MetricKey.TOF, MetricKey.TAUX_DISTRIBUTION, MetricKey.ACOMPTE,
    MetricKey.REPORT_A_NOUVEAU, MetricKey.DELAI_JOUISSANCE,
)

_PRIX = re.compile(r"Prix de souscription\s*(\d+(?:,\d+)?)\s*€")
_CAP = re.compile(r"(\d+(?:,\d+)?)\s*M€\s*de\s*Capitalisation")
_ASSOC = re.compile(rf"(\d{_N}*\d|\d)\s*Associés")
_DELAI = re.compile(r"[Dd]élai de jouissance[^.]*?du\s*(\d+)\s*(?:er|e|ème|eme)?\s*mois")
_DATE = re.compile(r"(\d{1,2}/\d{1,2}/\d{4})")


class KyaneosAdapter(SourceAdapter):
    sdg_key = "kyaneos_am"

    def fetch_metrics(self, entry: ScpiEntry) -> list[Metric]:
        url = entry.fiche_url or entry.documents_url
        if not url:
            return _av_all(
                entry,
                "Fiche non confirmée (SCPI fiscale Denormandie) — saisie manuelle",
                f"https://{entry.domaine}", self.collected_at,
            )
        return self._extract(entry, _flatten(self.client.get_text(url)), url)

    def _extract(self, entry: ScpiEntry, text: str, url: str) -> list[Metric]:
        mdate = _DATE.search(text)
        published = parse_date_fr(mdate.group(1)) if mdate else None
        found: dict[str, Metric] = {}

        def add(key: str, value: float, unit: str | None, conf: Confidence, raw: str) -> None:
            found[key] = Metric.ok_num(
                scpi_id=entry.scpi_id, metric_key=key, value=value, unit=unit,
                period=None, source_url=url, published_at=published,
                collected_at=self.collected_at, confidence=conf, raw=raw,
            )

        specs = [
            (MetricKey.PRIX_SOUSCRIPTION, _PRIX, "EUR", 1.0, Confidence.HAUTE),
            (MetricKey.CAPITALISATION, _CAP, "EUR", 1_000_000.0, Confidence.HAUTE),
            (MetricKey.NOMBRE_ASSOCIES, _ASSOC, None, 1.0, Confidence.MOYENNE),
            (MetricKey.DELAI_JOUISSANCE, _DELAI, "mois", 1.0, Confidence.HAUTE),
        ]
        for key, rgx, unit, mult, conf in specs:
            m = rgx.search(text)
            if m:
                v = parse_number_fr(m.group(1))
                if v is not None:
                    add(key, v * mult, unit, conf, m.group(0).strip())

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

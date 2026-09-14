"""Adaptateur Arkéa REIM (Transitions Europe, MomenTime).

Source = fiches HTML (label immédiatement suivi de la valeur).
ATTENTION : certaines tuiles (TOF, nombre d'immeubles/locataires) affichent « 0 »
tant que le JS n'a pas chargé -> on NE les extrait PAS (valeurs placeholder).
On extrait ce qui est réel et stable : capitalisation, valeur de retrait,
commission de gestion, délai de jouissance.
"""

from __future__ import annotations

import re

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
    MetricKey.REPORT_A_NOUVEAU, MetricKey.DELAI_JOUISSANCE, MetricKey.FRAIS_GESTION,
)

_CAP = re.compile(rf"Capitalisation au \d{{1,2}}/\d{{1,2}}/\d{{4}}\s*({_N}+)\s*€")
_RET = re.compile(rf"Valeur de retrait\s*({_N}*\d,\d+)\s*€")
_DELAI = re.compile(r"[Dd]élai de jouissance[^.]*?du\s*(\d+)\s*(?:er|e|ème|eme|ième|ieme)?\s*mois")
_FRAIS = re.compile(r"Commission de gestion HT\s*([\d.,]+)\s*%")
_DATE = re.compile(r"au\s*(\d{1,2}/\d{1,2}/\d{4})")


class ArkeaAdapter(SourceAdapter):
    sdg_key = "arkea_reim"

    def fetch_metrics(self, entry: ScpiEntry) -> list[Metric]:
        url = entry.fiche_url or entry.documents_url
        if not url:
            return self._av_all(entry, "fiche_url absente", f"https://{entry.domaine}")
        text = _flatten(self.client.get_text(url))
        mdate = _DATE.search(text)
        published = parse_date_fr(mdate.group(1)) if mdate else None
        found: dict[str, Metric] = {}

        def add(key: str, value: float, unit: str | None, conf: Confidence, raw: str) -> None:
            found[key] = Metric.ok_num(
                scpi_id=entry.scpi_id, metric_key=key, value=value, unit=unit,
                period=None, source_url=url, published_at=published,
                collected_at=self.collected_at, confidence=conf, raw=raw,
            )

        for key, rgx, unit in (
            (MetricKey.CAPITALISATION, _CAP, "EUR"),
            (MetricKey.PRIX_RETRAIT, _RET, "EUR"),
            (MetricKey.FRAIS_GESTION, _FRAIS, "%"),
            (MetricKey.DELAI_JOUISSANCE, _DELAI, "mois"),
        ):
            m = rgx.search(text)
            if m:
                v = parse_number_fr(m.group(1))
                if v is not None and v != 0:  # 0 = tuile placeholder non chargée
                    add(key, v, unit, Confidence.HAUTE, m.group(0).strip())

        out = list(found.values())
        out += [
            Metric.a_verifier(
                scpi_id=entry.scpi_id, metric_key=key, source_url=url,
                collected_at=self.collected_at,
                note="Non affiché en clair / tuile à 0 (JS) — bulletin ou saisie manuelle",
            )
            for key in TARGET_KEYS if key not in found
        ]
        return out

    def _av_all(self, entry: ScpiEntry, note: str, url: str) -> list[Metric]:
        return [
            Metric.a_verifier(scpi_id=entry.scpi_id, metric_key=key, source_url=url,
                              collected_at=self.collected_at, note=note)
            for key in TARGET_KEYS
        ]


def _flatten(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style"]):
        tag.extract()
    return re.sub(r"\s+", " ", soup.get_text(" "))

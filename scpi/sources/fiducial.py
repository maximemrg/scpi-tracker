"""Adaptateur Fiducial Gérance (Sélectipierre 2 Paris).

La fiche HTML est une grille de tuiles : l'aplatissement mélange libellés et
valeurs (preuve : « reconstitution 773 € » < « réalisation 785 € », impossible
si correctement apparié). On n'extrait donc QUE les valeurs explicitement
délimitées et non ambiguës ; le reste -> A_VERIFIER (jamais de valeur douteuse).
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
    MetricKey.REPORT_A_NOUVEAU, MetricKey.DELAI_JOUISSANCE,
)

_RET = re.compile(rf"Valeur de retrait\s*:\s*({_N}+(?:,\d+)?)\s*€")
_TOF = re.compile(r"Occupation Financier de\s*(\d+[.,]\d+)\s*%")
_DELAI = re.compile(r"[Dd]élai de jouissance[^.]*?du\s*(\d+)\s*(?:er|e|ème|eme)?\s*mois")
_DATE = re.compile(r"au\s*(\d{1,2}/\d{1,2}/\d{4})")


class FiducialAdapter(SourceAdapter):
    sdg_key = "fiducial_gerance"

    def fetch_metrics(self, entry: ScpiEntry) -> list[Metric]:
        url = entry.fiche_url or entry.documents_url or f"https://{entry.domaine}"
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
            (MetricKey.PRIX_RETRAIT, _RET, "EUR"),
            (MetricKey.TOF, _TOF, "%"),
            (MetricKey.DELAI_JOUISSANCE, _DELAI, "mois"),
        ):
            m = rgx.search(text)
            if m:
                v = parse_number_fr(m.group(1))
                if v is not None:
                    add(key, v, unit, Confidence.HAUTE, m.group(0).strip())

        out = list(found.values())
        out += [
            Metric.a_verifier(
                scpi_id=entry.scpi_id, metric_key=key, source_url=url,
                collected_at=self.collected_at,
                note="Grille HTML ambiguë (appariement libellé/valeur) — saisie manuelle",
            )
            for key in TARGET_KEYS if key not in found
        ]
        return out


def _flatten(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style"]):
        tag.extract()
    return re.sub(r"\s+", " ", soup.get_text(" "))

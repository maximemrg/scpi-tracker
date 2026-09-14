"""Adaptateur Perial AM (PFO, PFO2, PF Grand Paris, PF Hospitalité Europe).

Les fiches sont un site Webflow dont l'aplatissement APPARIE MAL la plupart des
tuiles libellé/valeur (ex. « PGA 2025 84,6 % » = aberrant). Seule la tuile
« Taux de distribution 2025 » donne une valeur systématiquement plausible et
cohérente sur les 4 SCPI (6,10 / 4,65 / 4,80 / 4,11 %) -> on n'extrait QUE le TD
(confiance MOYENNE) ; tout le reste -> A_VERIFIER (saisie ou parsing DOM ciblé).

Note : Perial a rebrandé (slugs perial-o2, perial-grand-paris,
perial-hospitalite-europe) et a lancé 2 SCPI supplémentaires
(perial-opportunites-europe / -territoires) hors périmètre.
"""

from __future__ import annotations

import re

from bs4 import BeautifulSoup

from ..models import Confidence, Metric, MetricKey
from ..parsing import parse_number_fr
from ..registry import ScpiEntry
from .base import SourceAdapter

TARGET_KEYS: tuple[str, ...] = (
    MetricKey.PRIX_SOUSCRIPTION, MetricKey.PRIX_RETRAIT,
    MetricKey.VALEUR_RECONSTITUTION, MetricKey.VALEUR_REALISATION,
    MetricKey.CAPITALISATION, MetricKey.NOMBRE_ASSOCIES, MetricKey.NOMBRE_IMMEUBLES,
    MetricKey.TOF, MetricKey.TAUX_DISTRIBUTION, MetricKey.ACOMPTE,
    MetricKey.REPORT_A_NOUVEAU, MetricKey.DELAI_JOUISSANCE,
)

_TD = re.compile(r"Taux de distribution\*?\s*2025\s*(\d+,\d+)\s*%")


class PerialAdapter(SourceAdapter):
    sdg_key = "perial_am"

    def fetch_metrics(self, entry: ScpiEntry) -> list[Metric]:
        url = entry.fiche_url or entry.documents_url or f"https://{entry.domaine}"
        text = _flatten(self.client.get_text(url))
        found: dict[str, Metric] = {}

        m = _TD.search(text)
        if m:
            v = parse_number_fr(m.group(1))
            if v is not None:
                found[MetricKey.TAUX_DISTRIBUTION] = Metric.ok_num(
                    scpi_id=entry.scpi_id, metric_key=MetricKey.TAUX_DISTRIBUTION,
                    value=v, unit="%", period="2025", source_url=url, published_at=None,
                    collected_at=self.collected_at, confidence=Confidence.MOYENNE,
                    raw=m.group(0).strip(),
                    note="Grille Webflow : seul le TD est apparié de façon fiable",
                )

        out = list(found.values())
        out += [
            Metric.a_verifier(
                scpi_id=entry.scpi_id, metric_key=key, source_url=url,
                collected_at=self.collected_at,
                note="Grille Webflow ambiguë (appariement libellé/valeur) — saisie manuelle",
            )
            for key in TARGET_KEYS if key not in found
        ]
        return out


def _flatten(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style"]):
        tag.extract()
    return re.sub(r"\s+", " ", soup.get_text(" "))

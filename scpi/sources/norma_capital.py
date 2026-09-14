"""Adaptateur Norma Capital (NCap Régions, NCap Education Santé, NCap Continent).

Particularité : ici la meilleure SOURCE PRIMAIRE n'est pas le bulletin PDF
(portail documents en JavaScript + PDF souvent non lisibles) mais le SITE HTML
officiel, server-rendered, qui expose des KPI structurés par SCPI :
  TAUX DE DISTRIBUTION (année 2025, cf. note de bas de page), TRI 5 ans
  (2020-2025), CAPITALISATION, prix de souscription (via le ticket d'entrée).

On extrait ces 4 métriques de façon fiable depuis la page d'accueil ; le reste
(TOF, prix de retrait, associés/immeubles par SCPI, acompte, report...) part en
A_VERIFIER, sourcé sur la page SCPI, pour saisie manuelle.

Correspondances de noms : NCap Régions = ex-Vendôme Régions ;
NCap Education Santé = ex-Fair Invest (scpi_id `fair_invest`).
"""

from __future__ import annotations

import re

from bs4 import BeautifulSoup

from ..models import Confidence, Metric, MetricKey
from ..parsing import parse_date_fr, parse_number_fr
from ..registry import ScpiEntry
from .base import SourceAdapter

HOME_URL = "https://www.normacapital.fr/"

TARGET_KEYS: tuple[str, ...] = (
    MetricKey.PRIX_SOUSCRIPTION, MetricKey.PRIX_RETRAIT,
    MetricKey.VALEUR_RECONSTITUTION, MetricKey.VALEUR_REALISATION,
    MetricKey.CAPITALISATION, MetricKey.NOMBRE_ASSOCIES, MetricKey.NOMBRE_IMMEUBLES,
    MetricKey.TOF, MetricKey.TAUX_DISTRIBUTION, MetricKey.TRI_5ANS,
    MetricKey.ACOMPTE, MetricKey.REPORT_A_NOUVEAU, MetricKey.DELAI_JOUISSANCE,
)

# Marqueur de carte (dans l'ordre d'apparition sur la page d'accueil).
CARD_MARKERS: tuple[tuple[str, str], ...] = (
    ("ncap_regions", "NCap Régions"),
    ("fair_invest", "NCap Education Santé"),
    ("ncap_continent", "NCap Continent"),
)

_TD = re.compile(r"TAUX DE DISTRIBUTION[^%]*?(\d+,\d+)\s*%")
_TRI5 = re.compile(r"TRI 5 ANS[^%]*?(\d+,\d+)\s*%")
_CAP = re.compile(r"CAPITALISATION[^\d]*?([\d\s]+,\d+)\s*M€")
_PRIX = re.compile(r"parts?\s*de\s*([\d\s]+)\s*€")


class NormaCapitalAdapter(SourceAdapter):
    sdg_key = "norma_capital"

    def fetch_metrics(self, entry: ScpiEntry) -> list[Metric]:
        text = _flatten(self.client.get_text(HOME_URL))
        card = self._card_for(text, entry.scpi_id)
        av_source = entry.documents_url or entry.fiche_url or HOME_URL
        if card is None:
            return self._averifier_all(
                entry, "Carte SCPI introuvable sur la page d'accueil", av_source
            )

        # Date de la donnée : "Données propres Norma Capital au 30/06/2026".
        mdate = re.search(r"Donn[ée]es propres[^.]*?au\s*(\d{1,2}/\d{1,2}/\d{4})", text)
        published = parse_date_fr(mdate.group(1)) if mdate else None
        found: dict[str, Metric] = {}

        def add(key: str, value: float, unit: str | None, period: str | None,
                conf: Confidence, raw: str) -> None:
            found[key] = Metric.ok_num(
                scpi_id=entry.scpi_id, metric_key=key, value=value, unit=unit,
                period=period, source_url=HOME_URL, published_at=published,
                collected_at=self.collected_at, confidence=conf, raw=raw,
            )

        m = _TD.search(card)
        if m:
            v = parse_number_fr(m.group(1))
            if v is not None:
                # Note de bas de page : TD = dividende 2025 / prix au 01/01/2025.
                add(MetricKey.TAUX_DISTRIBUTION, v, "%", "2025", Confidence.HAUTE, m.group(0))
        m = _TRI5.search(card)
        if m:
            v = parse_number_fr(m.group(1))
            if v is not None:
                add(MetricKey.TRI_5ANS, v, "%", "2020-2025", Confidence.HAUTE, m.group(0))
        m = _CAP.search(card)
        if m:
            v = parse_number_fr(m.group(1))
            if v is not None:
                add(MetricKey.CAPITALISATION, v * 1_000_000.0, "EUR", None,
                    Confidence.HAUTE, m.group(0))
        m = _PRIX.search(card)
        if m:
            v = parse_number_fr(m.group(1))
            if v is not None:
                add(MetricKey.PRIX_SOUSCRIPTION, v, "EUR", None, Confidence.HAUTE, m.group(0))

        out = list(found.values())
        for key in TARGET_KEYS:
            if key not in found:
                out.append(Metric.a_verifier(
                    scpi_id=entry.scpi_id, metric_key=key, source_url=av_source,
                    collected_at=self.collected_at,
                    note="Non affiché sur le site — bulletin PDF/portail JS ou saisie manuelle",
                ))
        return out

    @staticmethod
    def _card_for(text: str, scpi_id: str) -> str | None:
        i = text.find("Nos 3 SCPI")
        section = text[i:] if i >= 0 else text
        end = section.find("Investir en SCPI comporte")
        if end > 0:
            section = section[:end]
        positions = [(sid, section.find(mark)) for sid, mark in CARD_MARKERS]
        positions = [(sid, p) for sid, p in positions if p >= 0]
        positions.sort(key=lambda x: x[1])
        for idx, (sid, pos) in enumerate(positions):
            if sid != scpi_id:
                continue
            nxt = positions[idx + 1][1] if idx + 1 < len(positions) else len(section)
            return section[pos:nxt]
        return None

    def _averifier_all(self, entry: ScpiEntry, note: str, source_url: str) -> list[Metric]:
        return [
            Metric.a_verifier(
                scpi_id=entry.scpi_id, metric_key=key, source_url=source_url,
                collected_at=self.collected_at, note=note,
            )
            for key in TARGET_KEYS
        ]


def _flatten(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style"]):
        tag.extract()
    return re.sub(r"\s+", " ", soup.get_text(" "))

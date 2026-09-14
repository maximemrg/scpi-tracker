"""Adaptateur Alderan (ActivImmo, Comète).

Comme Norma Capital, la source fiable est le SITE HTML : les fiches SCPI
exposent des KPI auto-portants (« Libellé : valeur »), identiques d'une SCPI
à l'autre — un seul jeu de motifs suffit.

Spécificité Alderan : dividendes versés MENSUELLEMENT (depuis 2025). Le montant
mensuel n'est pas isolable de façon sûre du HTML -> ACOMPTE en A_VERIFIER, avec
une note explicite ; la saisie manuelle utilise une période mensuelle
(ex. « 2026-M07 »), que le schéma append-only accepte déjà (period = texte libre).
"""

from __future__ import annotations

import re
from datetime import date

from bs4 import BeautifulSoup

from ..models import Confidence, Metric, MetricKey
from ..parsing import parse_number_fr
from ..registry import ScpiEntry
from .base import SourceAdapter

TARGET_KEYS: tuple[str, ...] = (
    MetricKey.PRIX_SOUSCRIPTION, MetricKey.PRIX_RETRAIT,
    MetricKey.VALEUR_RECONSTITUTION, MetricKey.VALEUR_REALISATION,
    MetricKey.CAPITALISATION, MetricKey.NOMBRE_ASSOCIES, MetricKey.NOMBRE_IMMEUBLES,
    MetricKey.TOF, MetricKey.TAUX_DISTRIBUTION, MetricKey.TRI_5ANS,
    MetricKey.ACOMPTE, MetricKey.REPORT_A_NOUVEAU, MetricKey.DELAI_JOUISSANCE,
)

_N = r"[\d\s  ]"  # chiffres + séparateurs de milliers

# Motifs stricts (valeur adjacente au libellé) validés sur Comète ET ActivImmo.
_TD = re.compile(r"Taux de distribution(?:\s*\(\d\))?\s*:?\s*(\d+,\d+)\s*%")
_PRIX_SOUS = re.compile(rf"Prix de souscription\s*:?\s*({_N}+,?\d*)\s*€")
_PRIX_RET = re.compile(rf"\bretrait\s*:\s*({_N}+,?\d*)\s*€")
_REAL = re.compile(
    rf"r[eé]alisation[^:€]*?au\s*(\d{{2}})\.(\d{{2}})\.(\d{{4}})[^:€]*?:\s*({_N}+,\d+)\s*€"
)
_TOF = re.compile(r"occupation financier\s*:\s*(\d+,\d+)\s*%")
_IMM = re.compile(r"[Nn]ombre d[’']immeubles\s*:\s*(\d+)")
_ASSOC = re.compile(rf"(\d{_N}*\d|\d)\s*associés\b")
_DELAI = re.compile(r"d[eé]lai de jouissance[^.]*?(\d+)\s*mois")


class AlderanAdapter(SourceAdapter):
    sdg_key = "alderan"

    def fetch_metrics(self, entry: ScpiEntry) -> list[Metric]:
        url = entry.fiche_url or entry.documents_url
        if not url:
            return self._averifier_all(entry, "fiche_url absente du registry",
                                       entry.documents_url or f"https://{entry.domaine}")
        text = _flatten(self.client.get_text(url))
        return self._extract(entry, text, url)

    def _extract(self, entry: ScpiEntry, text: str, url: str) -> list[Metric]:
        found: dict[str, Metric] = {}

        # Date de réalisation (au JJ.MM.AAAA) sert de date de la donnée.
        published: date | None = None
        mr = _REAL.search(text)
        if mr:
            published = date(int(mr.group(3)), int(mr.group(2)), int(mr.group(1)))

        def add(key: str, value: float, unit: str | None, conf: Confidence, raw: str,
                period: str | None = None) -> None:
            found[key] = Metric.ok_num(
                scpi_id=entry.scpi_id, metric_key=key, value=value, unit=unit,
                period=period, source_url=url, published_at=published,
                collected_at=self.collected_at, confidence=conf, raw=raw,
            )

        simple = [
            (MetricKey.TAUX_DISTRIBUTION, _TD, "%", Confidence.HAUTE, "2025"),
            (MetricKey.PRIX_SOUSCRIPTION, _PRIX_SOUS, "EUR", Confidence.HAUTE, None),
            (MetricKey.PRIX_RETRAIT, _PRIX_RET, "EUR", Confidence.HAUTE, None),
            (MetricKey.TOF, _TOF, "%", Confidence.HAUTE, None),
            (MetricKey.NOMBRE_IMMEUBLES, _IMM, None, Confidence.HAUTE, None),
            (MetricKey.DELAI_JOUISSANCE, _DELAI, "mois", Confidence.HAUTE, None),
            (MetricKey.NOMBRE_ASSOCIES, _ASSOC, None, Confidence.MOYENNE, None),
        ]
        for key, rgx, unit, conf, period in simple:
            m = rgx.search(text)
            if m:
                v = parse_number_fr(m.group(1))
                if v is not None:
                    add(key, v, unit, conf, m.group(0).strip(), period)

        if mr:
            v = parse_number_fr(mr.group(4))
            if v is not None:
                add(MetricKey.VALEUR_REALISATION, v, "EUR", Confidence.HAUTE, mr.group(0).strip())

        out = list(found.values())
        for target in TARGET_KEYS:
            if target not in found:
                note = (
                    "Dividende versé MENSUELLEMENT — à saisir par mois (period AAAA-Mmm)"
                    if target == MetricKey.ACOMPTE else
                    "Non affiché en clair sur la fiche — bulletin ou saisie manuelle"
                )
                out.append(Metric.a_verifier(
                    scpi_id=entry.scpi_id, metric_key=target, source_url=url,
                    collected_at=self.collected_at, note=note,
                ))
        return out

    def _averifier_all(self, entry: ScpiEntry, note: str, url: str) -> list[Metric]:
        return [
            Metric.a_verifier(
                scpi_id=entry.scpi_id, metric_key=key, source_url=url,
                collected_at=self.collected_at, note=note,
            )
            for key in TARGET_KEYS
        ]


def _flatten(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style"]):
        tag.extract()
    return re.sub(r"\s+", " ", soup.get_text(" "))

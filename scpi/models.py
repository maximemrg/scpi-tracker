"""Modèles de données partagés : Metric, Confidence, Status, clés de métriques.

Règle d'or (contrainte n°1) : aucune valeur n'est inventée. Une métrique qui
n'a pas pu être extraite de façon certaine est représentée par un Metric de
statut A_VERIFIER, valeur nulle, mais AVEC sa source_url — jamais omise
silencieusement, jamais remplie d'une valeur par défaut.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from enum import StrEnum


class Confidence(StrEnum):
    HAUTE = "HAUTE"        # parsé d'un bulletin / page officielle de la SdG
    MOYENNE = "MOYENNE"    # page officielle mais structure ambiguë
    FAIBLE = "FAIBLE"      # extraction incertaine
    MANUELLE = "MANUELLE"  # saisie manuelle (portefeuille / overrides)


class Status(StrEnum):
    OK = "OK"
    A_VERIFIER = "A_VERIFIER"


class MetricKey(StrEnum):
    """Vocabulaire contrôlé des métriques. Étendu au fil des adaptateurs."""

    # Valorisation
    PRIX_SOUSCRIPTION = "prix_souscription"
    PRIX_RETRAIT = "prix_retrait"
    VALEUR_RECONSTITUTION = "valeur_reconstitution"
    VALEUR_REALISATION = "valeur_realisation"
    ECART_PRIX_RECONSTITUTION = "ecart_prix_reconstitution"  # en %
    DATE_DERNIER_PRIX = "date_dernier_prix"

    # Rendement
    TAUX_DISTRIBUTION = "taux_distribution"            # % annuel, period = année
    ACOMPTE = "acompte"                                # € / part, period = trimestre ou mois
    TRI_5ANS = "tri_5ans"
    TRI_10ANS = "tri_10ans"
    PART_REVENUS_ETRANGERS = "part_revenus_etrangers"  # %
    REPORT_A_NOUVEAU = "report_a_nouveau"              # en jours de distribution

    # Risque / qualité
    TOF = "tof"                                        # taux d'occupation financier %
    LTV = "ltv"                                        # taux d'endettement %
    CAPITALISATION = "capitalisation"                  # €
    NOMBRE_PARTS = "nombre_parts"                      # nb total de parts
    COLLECTE_NETTE = "collecte_nette"                  # € sur le trimestre
    NOMBRE_ASSOCIES = "nombre_associes"
    PARTS_EN_ATTENTE_RETRAIT = "parts_en_attente_retrait"  # nb de parts (liquidité)
    NOMBRE_IMMEUBLES = "nombre_immeubles"

    # Frais
    COMMISSION_SOUSCRIPTION = "commission_souscription"  # %
    FRAIS_GESTION = "frais_gestion"                      # %
    COMMISSION_RETRAIT = "commission_retrait"            # %
    DELAI_JOUISSANCE = "delai_jouissance"                # mois
    MINIMUM_SOUSCRIPTION = "minimum_souscription"        # nb de parts


@dataclass(frozen=True, slots=True)
class Metric:
    """Une observation datée et sourcée d'une métrique pour une SCPI.

    `value_num` porte la valeur numérique (le cas usuel) ; `value_text` porte
    les valeurs non numériques (ex. SFDR "Article 8", catégorie). Exactement
    l'un des deux est renseigné pour un statut OK ; les deux sont None pour
    A_VERIFIER.
    """

    scpi_id: str
    metric_key: str
    value_num: float | None
    value_text: str | None
    unit: str | None
    period: str | None          # "2026-T2", "2025", "2026-06-30"...
    source_url: str
    published_at: date | None   # date de la DONNÉE (pas de la collecte)
    collected_at: datetime
    confidence: Confidence
    status: Status = Status.OK
    raw: str | None = None      # extrait brut ayant produit la valeur (traçabilité)
    note: str | None = None

    @classmethod
    def ok_num(
        cls,
        *,
        scpi_id: str,
        metric_key: str,
        value: float,
        unit: str | None,
        period: str | None,
        source_url: str,
        published_at: date | None,
        collected_at: datetime,
        confidence: Confidence = Confidence.HAUTE,
        raw: str | None = None,
        note: str | None = None,
    ) -> Metric:
        return cls(
            scpi_id=scpi_id,
            metric_key=metric_key,
            value_num=value,
            value_text=None,
            unit=unit,
            period=period,
            source_url=source_url,
            published_at=published_at,
            collected_at=collected_at,
            confidence=confidence,
            status=Status.OK,
            raw=raw,
            note=note,
        )

    @classmethod
    def a_verifier(
        cls,
        *,
        scpi_id: str,
        metric_key: str,
        source_url: str,
        collected_at: datetime,
        note: str,
        period: str | None = None,
    ) -> Metric:
        """Échec d'extraction : valeur nulle mais on garde la trace + le lien."""
        return cls(
            scpi_id=scpi_id,
            metric_key=metric_key,
            value_num=None,
            value_text=None,
            unit=None,
            period=period,
            source_url=source_url,
            published_at=None,
            collected_at=collected_at,
            confidence=Confidence.FAIBLE,
            status=Status.A_VERIFIER,
            note=note,
        )


def now_utc() -> datetime:
    return datetime.now(UTC)

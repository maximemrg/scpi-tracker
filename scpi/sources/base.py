"""Classe de base des adaptateurs de source."""

from __future__ import annotations

import unicodedata
from abc import ABC, abstractmethod
from datetime import datetime

from ..http import PoliteClient
from ..models import Metric, now_utc
from ..registry import ScpiEntry


def strip_accents(s: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn"
    )


def norm(s: str) -> str:
    """Minuscule sans accents, espaces insécables normalisés — pour matcher des labels."""
    s = s.replace(" ", " ").replace(" ", " ").replace(" ", " ")
    return strip_accents(s).lower()


class SourceAdapter(ABC):
    """Interface commune. `fetch_metrics(entry)` renvoie une liste de Metric.

    Un adaptateur ne lève pas d'exception pour une donnée manquante : il émet
    un Metric A_VERIFIER (valeur nulle + source_url). Il ne lève que pour un
    échec dur (page inaccessible, PDF introuvable) — géré par l'orchestrateur.
    """

    sdg_key: str = ""

    def __init__(self, client: PoliteClient, collected_at: datetime | None = None) -> None:
        self.client = client
        self.collected_at = collected_at or now_utc()

    @abstractmethod
    def fetch_metrics(self, entry: ScpiEntry) -> list[Metric]:
        ...

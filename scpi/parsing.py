"""Outils de parsing des formats FR (nombres, %, €, dates, trimestres).

Isolés ici pour être testés indépendamment des adaptateurs : c'est le premier
endroit qui casse quand une source change de format.
"""

from __future__ import annotations

import re
from datetime import date

# Espaces fines / insécables utilisées comme séparateurs de milliers en FR.
_SPACES = "    "
_NUM_RE = re.compile(rf"-?\d[\d{_SPACES}]*(?:[.,]\d+)?")

_QUARTER_END = {1: (3, 31), 2: (6, 30), 3: (9, 30), 4: (12, 31)}

_MONTHS_FR = {
    "janvier": 1, "février": 2, "fevrier": 2, "mars": 3, "avril": 4,
    "mai": 5, "juin": 6, "juillet": 7, "août": 8, "aout": 8,
    "septembre": 9, "octobre": 10, "novembre": 11, "décembre": 12, "decembre": 12,
}


def parse_number_fr(text: str) -> float | None:
    """Extrait le premier nombre FR d'une chaîne. '1 234,56 €' -> 1234.56.

    Retourne None si aucun nombre plausible n'est trouvé (jamais 0 par défaut).
    """
    m = _NUM_RE.search(text)
    if not m:
        return None
    raw = m.group(0)
    for sp in _SPACES:
        raw = raw.replace(sp, "")
    raw = raw.replace(",", ".")
    try:
        return float(raw)
    except ValueError:
        return None


def quarter_end_date(year: int, quarter: int) -> date:
    """Date de fin de trimestre (= date de la donnée d'un bulletin trimestriel)."""
    if quarter not in _QUARTER_END:
        raise ValueError(f"trimestre invalide: {quarter}")
    month, day = _QUARTER_END[quarter]
    return date(year, month, day)


_PERIOD_RE = re.compile(r"(?P<y>20\d{2})\s*[-_ ]?\s*T(?P<q>[1-4])", re.IGNORECASE)
_PERIOD_RE_ALT = re.compile(r"T(?P<q>[1-4])\s*[-_ ]?\s*(?P<y>20\d{2})", re.IGNORECASE)


def parse_period_quarter(text: str) -> tuple[int, int] | None:
    """Repère un (année, trimestre) dans une chaîne. Gère '2026-T2' et 'T2 2026'."""
    m = _PERIOD_RE.search(text) or _PERIOD_RE_ALT.search(text)
    if not m:
        return None
    return int(m.group("y")), int(m.group("q"))


def parse_date_fr(text: str) -> date | None:
    """Parse '15 avril 2025' ou '15/04/2025'. Retourne None si incertain."""
    m = re.search(r"(\d{1,2})[/.](\d{1,2})[/.](\d{4})", text)
    if m:
        d, mo, y = (int(g) for g in m.groups())
        try:
            return date(y, mo, d)
        except ValueError:
            return None
    m = re.search(r"(\d{1,2})\s+([a-zA-Zéûôàèç]+)\s+(\d{4})", text)
    if m:
        day = int(m.group(1))
        month = _MONTHS_FR.get(m.group(2).lower())
        year = int(m.group(3))
        if month is not None:
            try:
                return date(year, month, day)
            except ValueError:
                return None
    return None

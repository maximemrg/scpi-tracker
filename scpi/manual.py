"""Saisie manuelle (volet « saisie » de la stratégie hybride).

- `generate_template` : produit un gabarit YAML pré-rempli à partir des
  métriques A_VERIFIER en base (scpi, métrique, période, lien du PDF source).
  Vous n'avez qu'à compléter `value` (et éventuellement `published_at`).
- `import_template` : réinjecte les lignes complétées dans `manual_overrides`
  (confiance MANUELLE, prioritaires sur le scraping et conservées).

Cela ferme la boucle : ce que le scraping ne peut pas lire de façon sûre est
listé, sourcé, puis saisi une fois — sans jamais inventer de valeur.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from .storage import Store

_HEADER = (
    "# Gabarit de saisie manuelle SCPI — complétez le champ `value` de chaque\n"
    "# entrée à partir du `source_url` indiqué, puis :\n"
    "#   python -m scpi.cli import-overrides saisie_manuelle.yaml\n"
    "# Laissez `value: null` pour les lignes que vous ne renseignez pas encore.\n"
    "# `value` numérique -> stocké en valeur numérique ; texte -> valeur texte.\n"
)


def generate_template(store: Store, path: Path | str) -> int:
    """Écrit un gabarit YAML des A_VERIFIER sans override existant. Renvoie le nombre d'entrées."""
    rows = store.conn.execute(
        """SELECT scpi_id, metric_key, period, source_url, note,
                  MAX(collected_at) AS c
           FROM metrics WHERE status='A_VERIFIER'
           GROUP BY scpi_id, metric_key, period
           ORDER BY scpi_id, metric_key, period"""
    ).fetchall()

    items: list[dict[str, Any]] = []
    for r in rows:
        exists = store.conn.execute(
            """SELECT 1 FROM manual_overrides
               WHERE scpi_id=? AND metric_key=? AND (period IS ? OR period=?) LIMIT 1""",
            (r["scpi_id"], r["metric_key"], r["period"], r["period"]),
        ).fetchone()
        if exists:
            continue
        items.append({
            "scpi_id": r["scpi_id"],
            "metric_key": r["metric_key"],
            "period": r["period"],
            "value": None,          # <- À COMPLÉTER
            "unit": None,
            "published_at": None,   # optionnel : date de la donnée (AAAA-MM-JJ)
            "source_url": r["source_url"],
            "_note": r["note"],
        })

    path = Path(path)
    with path.open("w", encoding="utf-8") as fh:
        fh.write(_HEADER)
        yaml.safe_dump({"overrides": items}, fh, allow_unicode=True, sort_keys=False)
    return len(items)


def import_template(store: Store, path: Path | str) -> int:
    """Injecte les entrées complétées (value non nulle) dans manual_overrides. Renvoie le compte."""
    with Path(path).open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    n = 0
    for item in data.get("overrides", []):
        value = item.get("value")
        if value is None:
            continue
        value_num: float | None = None
        value_text: str | None = None
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            value_num = float(value)
        else:
            value_text = str(value)
        store.add_override(
            scpi_id=item["scpi_id"],
            metric_key=item["metric_key"],
            period=item.get("period"),
            value_num=value_num,
            value_text=value_text,
            unit=item.get("unit"),
            source_url=item.get("source_url"),
            published_at=item.get("published_at"),
            note="saisie manuelle (gabarit)",
        )
        n += 1
    return n

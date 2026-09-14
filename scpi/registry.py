"""Chargement du registre des sources (sources/registry.yaml)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import yaml

DEFAULT_REGISTRY_PATH = Path(__file__).resolve().parent.parent / "sources" / "registry.yaml"


@dataclass(frozen=True)
class ScpiEntry:
    scpi_id: str
    nom: str
    sdg_key: str
    sdg_nom: str
    domaine: str
    fiche_url: str | None
    documents_url: str | None
    strategie_bulletin: str
    conf: dict[str, Any]  # bloc YAML brut de la SCPI (patterns, notes, alias...)


@dataclass(frozen=True)
class Registry:
    raw: dict[str, Any]
    entries: dict[str, ScpiEntry]

    @property
    def blocked_domains(self) -> list[str]:
        return list(self.raw.get("meta", {}).get("sources_interdites", []))

    @property
    def collecte(self) -> dict[str, Any]:
        return dict(self.raw.get("meta", {}).get("politique_collecte", {}))

    def by_sdg(self, sdg_key: str) -> list[ScpiEntry]:
        return [e for e in self.entries.values() if e.sdg_key == sdg_key]


def load_registry(path: Path | None = None) -> Registry:
    path = path or DEFAULT_REGISTRY_PATH
    with path.open(encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)

    entries: dict[str, ScpiEntry] = {}
    for sdg_key, sdg in raw.get("societes_gestion", {}).items():
        for scpi_id, scpi in sdg.get("scpi", {}).items():
            entries[scpi_id] = ScpiEntry(
                scpi_id=scpi_id,
                nom=scpi.get("nom", scpi_id),
                sdg_key=sdg_key,
                sdg_nom=sdg.get("nom", sdg_key),
                domaine=sdg.get("domaine", ""),
                fiche_url=scpi.get("fiche_url"),
                documents_url=scpi.get("documents_url"),
                strategie_bulletin=sdg.get("strategie_bulletin", "scrape_listing"),
                conf=scpi,
            )
    return Registry(raw=raw, entries=entries)


def domain_of(url: str) -> str:
    return urlparse(url).netloc.lower().removeprefix("www.")

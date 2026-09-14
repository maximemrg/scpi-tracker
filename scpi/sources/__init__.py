"""Adaptateurs de sources : un par société de gestion.

Pas de parser universel : chaque SdG publie ses bulletins dans un format qui
lui est propre. On enregistre les adaptateurs dans ADAPTERS (clé = sdg_key).
"""

from __future__ import annotations

from .alderan import AlderanAdapter
from .base import SourceAdapter
from .corum import CorumAdapter
from .norma_capital import NormaCapitalAdapter
from .sofidy import SofidyAdapter
from .sogenial import SogenialAdapter

ADAPTERS: dict[str, type[SourceAdapter]] = {
    "corum_lepargne": CorumAdapter,
    "sofidy": SofidyAdapter,
    "norma_capital": NormaCapitalAdapter,
    "alderan": AlderanAdapter,
    "sogenial_immobilier": SogenialAdapter,
}

__all__ = [
    "ADAPTERS", "SourceAdapter", "CorumAdapter", "SofidyAdapter",
    "NormaCapitalAdapter", "AlderanAdapter", "SogenialAdapter",
]

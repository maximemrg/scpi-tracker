"""Adaptateurs de sources : un par société de gestion.

Pas de parser universel : chaque SdG publie ses bulletins dans un format qui
lui est propre. On enregistre les adaptateurs dans ADAPTERS (clé = sdg_key).
"""

from __future__ import annotations

from .base import SourceAdapter
from .corum import CorumAdapter

ADAPTERS: dict[str, type[SourceAdapter]] = {
    "corum_lepargne": CorumAdapter,
}

__all__ = ["ADAPTERS", "SourceAdapter", "CorumAdapter"]

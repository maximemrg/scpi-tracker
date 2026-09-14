"""Adaptateurs de sources : un par société de gestion.

Pas de parser universel : chaque SdG publie ses bulletins dans un format qui
lui est propre. On enregistre les adaptateurs dans ADAPTERS (clé = sdg_key).
"""

from __future__ import annotations

from .alderan import AlderanAdapter
from .arkea import ArkeaAdapter
from .base import SourceAdapter
from .corum import CorumAdapter
from .fiducial import FiducialAdapter
from .inter_gestion import InterGestionAdapter
from .kyaneos import KyaneosAdapter
from .norma_capital import NormaCapitalAdapter
from .perial import PerialAdapter
from .sofidy import SofidyAdapter
from .sogenial import SogenialAdapter

ADAPTERS: dict[str, type[SourceAdapter]] = {
    "corum_lepargne": CorumAdapter,
    "sofidy": SofidyAdapter,
    "norma_capital": NormaCapitalAdapter,
    "alderan": AlderanAdapter,
    "sogenial_immobilier": SogenialAdapter,
    "inter_gestion_reim": InterGestionAdapter,
    "kyaneos_am": KyaneosAdapter,
    "fiducial_gerance": FiducialAdapter,
    "perial_am": PerialAdapter,
    "arkea_reim": ArkeaAdapter,
}

__all__ = [
    "ADAPTERS", "SourceAdapter", "CorumAdapter", "SofidyAdapter",
    "NormaCapitalAdapter", "AlderanAdapter", "SogenialAdapter", "InterGestionAdapter",
    "KyaneosAdapter", "FiducialAdapter", "PerialAdapter", "ArkeaAdapter",
]

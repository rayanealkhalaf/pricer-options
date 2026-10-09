"""Pricer d'options : formules fermées, arbre binomial et Monte-Carlo.

Reconstruction en Python du classeur Excel/VBA ``Pricer_Options_Rayane_ALKHALAF.xlsm``.

Exemple ::

    >>> from pricer import prix_bsm
    >>> round(prix_bsm(100, 100, 0.05, 0.02, 0.20, 1.0, "call"), 6)
    9.227006
"""

from pricer.asian import asiatique_geometrique, mc_asiatique
from pricer.barrier import (
    NOMS_BARRIERE,
    TYPES_BARRIERE,
    mc_barriere,
    parites_barriere,
    prix_barriere,
    prix_barrieres,
)
from pricer.bsm import d1_d2, parite_call_put, prix_bsm, volatilite_implicite
from pricer.greeks import Grecques, grecques_bsm
from pricer.lsm import prix_lsm
from pricer.monte_carlo import ResultatMC, ResultatsMC, mc_europeenne
from pricer.rng import MRG32k3a, creer_generateur
from pricer.strategies import (
    STRATEGIES,
    Jambe,
    analyser_position,
    jambes_strategie,
    scenario_pnl,
    tableau_comparatif,
)
from pricer.trees import americaine_crr_controle, arbre_crr

__version__ = "1.0.0"

__all__ = [
    "NOMS_BARRIERE",
    "STRATEGIES",
    "TYPES_BARRIERE",
    "Grecques",
    "Jambe",
    "MRG32k3a",
    "ResultatMC",
    "ResultatsMC",
    "americaine_crr_controle",
    "analyser_position",
    "arbre_crr",
    "asiatique_geometrique",
    "creer_generateur",
    "d1_d2",
    "grecques_bsm",
    "jambes_strategie",
    "mc_asiatique",
    "mc_barriere",
    "mc_europeenne",
    "parite_call_put",
    "parites_barriere",
    "prix_barriere",
    "prix_barrieres",
    "prix_bsm",
    "prix_lsm",
    "scenario_pnl",
    "tableau_comparatif",
    "volatilite_implicite",
]

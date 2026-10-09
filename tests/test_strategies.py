"""Tests de l'onglet « Stratégies & Grecques » (valeurs de référence de l'Excel)."""

import math

import numpy as np
import pytest

from pricer.bsm import prix_bsm
from pricer.greeks import grecques_bsm
from pricer.strategies import (
    STRATEGIES,
    Jambe,
    analyser_position,
    bsm_vectorise,
    jambes_strategie,
    lecture_grecques,
    pnl_echeance,
    profils,
    scenario_pnl,
    tableau_comparatif,
)

#: Paramètres par défaut de l'onglet : S = 100, r = 5 %, q = 0, σ = 20 %, 100 jours.
MARCHE = {"S": 100.0, "r": 0.05, "q": 0.0, "vol": 0.20, "jours": 100}
STRADDLE = jambes_strategie("Achat stellage (straddle)", 100, 10)
#: Exemple pré-rempli des jambes personnalisées : iron condor.
IRON_CONDOR = [
    Jambe("put", 1, 1, 90),
    Jambe("put", -1, 1, 95),
    Jambe("call", -1, 1, 105),
    Jambe("call", 1, 1, 110),
]

#: Tableau comparatif de l'Excel (coût net, delta, gamma, vega, theta), arrondi à 1e-8.
COMPARATIF_EXCEL = {
    "Achat call": (4.86169017, 0.57267881, 0.03747474, 0.20534107, -0.02771304),
    "Achat put": (3.50116708, -0.42732119, 0.03747474, 0.20534107, -0.01420078),
    "Achat spread (bull call spread)": (
        3.50417562,
        0.33914266,
        0.00822119,
        0.04504761,
        -0.00867053,
    ),
    "Achat tunnel": (1.04860983, 0.63905601, 0.00623193, 0.03414758, -0.0120253),
    "Achat stellage (straddle)": (8.36285725, 0.14535763, 0.07494949, 0.41068213, -0.04191382),
    "Achat strangle": (4.35037918, 0.13822124, 0.06699679, 0.36710572, -0.03800807),
    "Achat papillon (butterfly)": (3.48641062, -0.02891282, -0.02691559, -0.1474827, 0.01562193),
    "Achat condor": (6.31548697, -0.0548473, -0.03891696, -0.21324359, 0.02294083),
}


def test_straddle_valeurs_excel():
    pos = analyser_position(STRADDLE, **MARCHE)
    assert pos.lignes[0].prime == pytest.approx(4.861690167464673, abs=1e-12)
    assert pos.lignes[1].prime == pytest.approx(3.501167080440041, abs=1e-12)
    attendu = {
        "delta": 0.145357629,
        "gamma": 0.0749494896,
        "vega": 0.4106821348,
        "theta": -0.041913817,
        "rho": 0.0169120703,
    }
    assert pos.cout_net == pytest.approx(8.3628572479, abs=1e-9)
    for nom, valeur in attendu.items():
        assert pos.grecques()[nom] == pytest.approx(valeur, abs=1e-9), nom


def test_straddle_profil_echeance():
    pos = analyser_position(STRADDLE, **MARCHE)
    assert pos.points_morts == pytest.approx([91.6371427521, 108.3628572479], abs=1e-9)
    assert pos.gain_max == math.inf
    assert pos.perte_max == pytest.approx(-8.3628572479, abs=1e-9)


def test_iron_condor_profil_exact():
    """Crédit encaissé, gain et perte bornés, points morts aux strikes ∓ crédit."""
    pos = analyser_position(IRON_CONDOR, **MARCHE)
    credit = -pos.cout_net
    assert credit > 0
    assert pos.points_morts == pytest.approx([95 - credit, 105 + credit], abs=1e-12)
    assert pos.gain_max == pytest.approx(credit, abs=1e-12)
    assert pos.perte_max == pytest.approx(credit - 5, abs=1e-12)


def test_scenario_valeurs_excel():
    """J+30, σ et spot inchangés : seul le theta contribue ; P&L réel −1,3685."""
    sc = scenario_pnl(STRADDLE, **MARCHE, jours_ecoules=30, vol_scenario=0.20, spot_scenario=100)
    assert sc.contribution_theta == pytest.approx(-1.25741451, abs=1e-8)
    assert sc.contribution_delta == sc.contribution_gamma == sc.contribution_vega == 0
    assert sc.pnl_reel == pytest.approx(-1.3685070859, abs=1e-9)
    assert sc.ecart == pytest.approx(-0.1110925759, abs=1e-8)


def test_scenario_petit_choc_bien_explique():
    """Pour un petit choc, le développement de Taylor explique presque tout le P&L."""
    sc = scenario_pnl(STRADDLE, **MARCHE, jours_ecoules=0, vol_scenario=0.201, spot_scenario=100.5)
    assert abs(sc.ecart) < 0.01 * abs(sc.pnl_reel) + 1e-4


def test_tableau_comparatif_excel():
    lignes = {li["stratégie"]: li for li in tableau_comparatif(**MARCHE, K0=100, delta_k=10)}
    assert len(lignes) == 16
    for nom, valeurs in COMPARATIF_EXCEL.items():
        li = lignes[nom]
        obtenu = (li["coût net"], li["delta"], li["gamma"], li["vega"], li["theta"])
        assert obtenu == pytest.approx(valeurs, abs=1e-8), nom
        # La vente est l'opposé exact de l'achat.
        vente = lignes[nom.replace("Achat", "Vente").replace("bull call", "bear call")]
        assert vente["coût net"] == pytest.approx(-li["coût net"], abs=1e-12)


def test_graphiques_valeurs_excel():
    """Premier point de la grille (S = 70) du graphique de l'onglet, grecque = Gamma."""
    pr = profils(STRADDLE, **MARCHE, jours_ecoules=30, vol_scenario=0.20, grecque="gamma")
    assert pr["spots"][0] == 70 and pr["spots"][-1] == 130 and pr["spots"].size == 121
    assert pr["pnl_echeance"][0] == pytest.approx(21.6371427521, abs=1e-9)
    assert pr["pnl_j0"][0] == pytest.approx(20.27903909799576, abs=1e-10)
    assert pr["pnl_scenario"][0] == pytest.approx(20.682944173619287, abs=1e-10)
    assert pr["grecque_j0"][0] == pytest.approx(0.0006025372271091117, abs=1e-14)
    assert pr["grecque_scenario"][0] == pytest.approx(6.015798394999131e-05, abs=1e-14)


def test_lecture_des_grecques_excel():
    pos = analyser_position(STRADDLE, **MARCHE)
    assert lecture_grecques(pos, **MARCHE) == [
        "Delta 0,15 : gagne ≈ 0,15 € si le sous-jacent monte de 1 € — biais haussier faible.",
        "Gamma 0,0749 > 0 : acheteur de convexité — les grands mouvements jouent en faveur "
        "de la position.",
        "Vega 0,411 : gagne ≈ 0,41 € si la volatilité implicite monte d'1 point "
        "(acheteur de volatilité).",
        "Theta -0,042 : perd ≈ 0,042 € par jour si rien ne bouge (le temps joue contre la "
        "position).",
        "Synthèse : acheteur de volatilité — paie le temps (Theta) pour profiter des "
        "mouvements (Gamma, Vega).",
    ]


@pytest.mark.parametrize("option", ["call", "put"])
def test_bsm_vectorise_coherent_avec_bsm_et_greeks(option):
    phi = 1 if option == "call" else -1
    g = bsm_vectorise(np.array([105.0]), 100, 0.03, 0.01, 0.25, 0.5, phi)
    ref = grecques_bsm(105, 100, 0.03, 0.01, 0.25, 0.5, option).en_dict()
    assert g["valeur"][0] == pytest.approx(prix_bsm(105, 100, 0.03, 0.01, 0.25, 0.5, option))
    for nom, valeur in ref.items():
        assert g[nom][0] == pytest.approx(valeur, abs=1e-12), nom


@pytest.mark.parametrize("nom", list(STRATEGIES))
def test_toutes_les_strategies(nom):
    """Cohérence : le P&L à l'échéance est nul aux points morts et borné comme annoncé."""
    pos = analyser_position(jambes_strategie(nom, 100, 10), **MARCHE)
    jambes = jambes_strategie(nom, 100, 10)
    for x in pos.points_morts:
        assert pnl_echeance(jambes, x, pos.cout_net) == pytest.approx(0, abs=1e-9)
    grille = pnl_echeance(jambes, np.linspace(1, 300, 3000), pos.cout_net)
    assert grille.max() <= pos.gain_max + 1e-9
    assert grille.min() >= pos.perte_max - 1e-9


def test_validations():
    with pytest.raises(ValueError, match="Stratégie inconnue"):
        jambes_strategie("Iron butterfly")
    with pytest.raises(ValueError, match="sens"):
        Jambe("call", 2, 1, 100)
    with pytest.raises(ValueError, match="strike"):
        Jambe("put", 1, 1, 0)
    with pytest.raises(ValueError, match="1 jour"):
        analyser_position(STRADDLE, 100, 0.05, 0, 0.2, 0)
    with pytest.raises(ValueError, match="1 à 4 jambes"):
        analyser_position(STRADDLE * 3, **MARCHE)
    with pytest.raises(ValueError, match="négatif ou nul"):
        jambes_strategie("Achat condor", 100, 80)

"""Tests de la formule de Black-Scholes-Merton (valeurs de référence de l'Excel)."""

import math

import pytest

from pricer.bsm import d1_d2, parite_call_put, prix_bsm
from tests.references import EURO


def test_valeurs_excel():
    assert prix_bsm(**EURO, option="call") == pytest.approx(9.227006, abs=1e-6)
    assert prix_bsm(**EURO, option="put") == pytest.approx(6.330081, abs=1e-6)


def test_parite_call_put():
    assert abs(parite_call_put(**EURO)) < 1e-10


@pytest.mark.parametrize("S", [50.0, 80.0, 100.0, 125.0, 300.0])
@pytest.mark.parametrize("vol", [0.05, 0.2, 0.8])
def test_parite_sur_une_grille(S, vol):
    assert abs(parite_call_put(S, 100.0, 0.03, 0.01, vol, 2.0)) < 1e-10


def test_onglet_europeen_tel_que_sauvegarde():
    """Entrées affichées dans l'onglet européen : r = 20 %, σ = 52 %, q = 0."""
    assert prix_bsm(100, 100, 0.20, 0.0, 0.52, 1.0, "call") == pytest.approx(29.044883, abs=1e-6)
    assert prix_bsm(100, 100, 0.20, 0.0, 0.52, 1.0, "put") == pytest.approx(10.917958, abs=1e-6)


def test_d1_d2():
    d1, d2 = d1_d2(**EURO)
    assert d1 == pytest.approx(0.25, abs=1e-12)  # (0 + (0.05 − 0.02 + 0.02)) / 0.2
    assert d2 == pytest.approx(0.05, abs=1e-12)


def test_volatilite_nulle():
    """σ = 0 : valeur intrinsèque forward actualisée."""
    forward = 100 * math.exp(-0.02) - 100 * math.exp(-0.05)
    assert prix_bsm(100, 100, 0.05, 0.02, 0.0, 1.0, "call") == pytest.approx(forward)
    assert prix_bsm(100, 100, 0.05, 0.02, 0.0, 1.0, "put") == 0.0


def test_bornes_d_arbitrage():
    c = prix_bsm(**EURO, option="call")
    assert max(100 * math.exp(-0.02) - 100 * math.exp(-0.05), 0) <= c <= 100 * math.exp(-0.02)


def test_entrees_invalides():
    with pytest.raises(ValueError, match="S doit être strictement positif"):
        prix_bsm(-1, 100, 0.05, 0.02, 0.2, 1)
    with pytest.raises(ValueError, match="'call' ou 'put'"):
        prix_bsm(100, 100, 0.05, 0.02, 0.2, 1, "digitale")

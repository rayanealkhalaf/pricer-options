"""Tests de la volatilité implicite (inversion de la formule BSM)."""

import math

import pytest

from pricer.bsm import prix_bsm, volatilite_implicite
from tests.references import EURO

MARCHE = {k: v for k, v in EURO.items() if k != "vol"}


def test_valeur_excel():
    """Le prix BSM de l'Excel (9,227006) redonne σ = 20 %."""
    assert volatilite_implicite(9.227006, **MARCHE, option="call") == pytest.approx(0.2, abs=1e-6)
    assert volatilite_implicite(6.330081, **MARCHE, option="put") == pytest.approx(0.2, abs=1e-6)


@pytest.mark.parametrize("option", ["call", "put"])
@pytest.mark.parametrize("K", [60.0, 90.0, 100.0, 115.0, 160.0])
@pytest.mark.parametrize("vol", [0.05, 0.2, 0.6, 1.5])
def test_aller_retour(option, K, vol):
    """σ → prix → σ, y compris loin de la monnaie (là où Newton peut diverger)."""
    prix = prix_bsm(100.0, K, 0.03, 0.01, vol, 1.5, option)
    s_actu, k_actu = 100.0 * math.exp(-0.01 * 1.5), K * math.exp(-0.03 * 1.5)
    valeur_temps = prix - max(s_actu - k_actu if option == "call" else k_actu - s_actu, 0.0)
    if valeur_temps < 1e-4:
        # Valeur temps quasi nulle : le prix ne contient plus d'information sur σ.
        pytest.skip("valeur temps trop faible pour identifier σ")
    sigma = volatilite_implicite(prix, 100.0, K, 0.03, 0.01, 1.5, option)
    assert prix_bsm(100.0, K, 0.03, 0.01, sigma, 1.5, option) == pytest.approx(prix, abs=1e-9)
    assert sigma == pytest.approx(vol, rel=1e-5)


def test_meme_volatilite_pour_call_et_put():
    """Par la parité call-put, le call et le put de même strike ont le même σ implicite."""
    c = prix_bsm(100, 110, 0.04, 0.0, 0.3, 2.0, "call")
    p = prix_bsm(100, 110, 0.04, 0.0, 0.3, 2.0, "put")
    assert volatilite_implicite(c, 100, 110, 0.04, 0.0, 2.0, "call") == pytest.approx(
        volatilite_implicite(p, 100, 110, 0.04, 0.0, 2.0, "put"), abs=1e-9
    )


def test_prix_sous_la_valeur_intrinseque():
    intrinseque = 100 * math.exp(-0.02) - 80 * math.exp(-0.05)
    with pytest.raises(ValueError, match="non-arbitrage"):
        volatilite_implicite(intrinseque - 0.01, 100, 80, 0.05, 0.02, 1.0, "call")


def test_prix_au_dessus_du_spot():
    with pytest.raises(ValueError, match="non-arbitrage"):
        volatilite_implicite(99.0, **MARCHE, option="call")


def test_volatilite_hors_recherche():
    prix = prix_bsm(100, 100, 0.0, 0.0, 3.0, 1.0, "call")
    with pytest.raises(ValueError, match="dépasse"):
        volatilite_implicite(prix, 100, 100, 0.0, 0.0, 1.0, "call", vol_max=2.0)


def test_prix_invalide():
    with pytest.raises(ValueError):
        volatilite_implicite(float("nan"), **MARCHE)

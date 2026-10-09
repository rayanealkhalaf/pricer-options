"""Grecques analytiques comparées aux différences finies centrées."""

import pytest

from pricer.bsm import prix_bsm
from pricer.greeks import grecques_bsm
from tests.references import EURO

CAS = [
    EURO,
    {"S": 80.0, "K": 100.0, "r": 0.03, "q": 0.0, "vol": 0.35, "T": 0.5},
    {"S": 120.0, "K": 100.0, "r": 0.01, "q": 0.04, "vol": 0.15, "T": 2.0},
]


def differences_finies(p: dict, option: str) -> dict[str, float]:
    """Dérivées numériques centrées, dans les conventions de l'Excel."""

    def v(**choc):
        decale = {k: p[k] + choc.get(k, 0.0) for k in p}
        return prix_bsm(**decale, option=option)

    h_s, h = 1e-2, 1e-5
    return {
        "delta": (v(S=h_s) - v(S=-h_s)) / (2 * h_s),
        "gamma": (v(S=h_s) - 2 * v() + v(S=-h_s)) / h_s**2,
        "vega": (v(vol=h) - v(vol=-h)) / (2 * h) / 100,  # pour +1 point de vol
        "theta": -(v(T=h) - v(T=-h)) / (2 * h) / 365,  # par jour, temps qui passe
        "rho": (v(r=h) - v(r=-h)) / (2 * h) / 100,  # pour +1 point de taux
    }


@pytest.mark.parametrize("p", CAS)
@pytest.mark.parametrize("option", ["call", "put"])
def test_grecques_egales_aux_differences_finies(p, option):
    analytiques = grecques_bsm(**p, option=option).en_dict()
    numeriques = differences_finies(p, option)
    for nom, valeur in analytiques.items():
        assert valeur == pytest.approx(numeriques[nom], abs=1e-4), nom


def test_valeurs_excel_onglet_europeen():
    """Grecques affichées dans l'onglet européen (r = 20 %, σ = 52 %, q = 0)."""
    gc = grecques_bsm(100, 100, 0.20, 0.0, 0.52, 1.0, "call")
    gp = grecques_bsm(100, 100, 0.20, 0.0, 0.52, 1.0, "put")
    assert gc.delta == pytest.approx(0.7404117687, abs=1e-9)
    assert gp.delta == pytest.approx(-0.2595882313, abs=1e-9)
    assert gc.gamma == pytest.approx(0.0062326932, abs=1e-9)
    assert gc.vega == pytest.approx(0.3241000449, abs=1e-9)
    assert gc.theta == pytest.approx(-0.0477420821, abs=1e-9)
    assert gp.theta == pytest.approx(-0.0028801230, abs=1e-9)
    assert gc.rho == pytest.approx(0.4499629399, abs=1e-9)
    assert gp.rho == pytest.approx(-0.3687678131, abs=1e-9)


def test_relations_call_put():
    gc, gp = grecques_bsm(**EURO, option="call"), grecques_bsm(**EURO, option="put")
    assert gc.gamma == pytest.approx(gp.gamma)
    assert gc.vega == pytest.approx(gp.vega)
    # Δ_C − Δ_P = e^{−qT}
    assert gc.delta - gp.delta == pytest.approx(0.98019867330675525)


def test_volatilite_nulle_refusee():
    with pytest.raises(ValueError, match="strictement positive"):
        grecques_bsm(100, 100, 0.05, 0.02, 0.0, 1.0)

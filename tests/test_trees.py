"""Tests de l'arbre de Cox-Ross-Rubinstein et de la correction par variable de contrôle."""

import pytest

from pricer.bsm import prix_bsm
from pricer.trees import americaine_crr_controle, arbre_crr
from tests.references import AMER, EURO


def test_put_americain_valeur_excel():
    """CRR 1 000 pas + variable de contrôle ≈ 2,3201 (Excel : 2,320083)."""
    res = americaine_crr_controle(**AMER, n_pas=1_000)
    assert res.cv_put == pytest.approx(2.3201, abs=0.002)
    assert res.cv_put == pytest.approx(2.320083, abs=1e-6)
    assert res.arbre.euro_put == pytest.approx(2.065596, abs=1e-6)
    assert res.arbre.amer_put == pytest.approx(2.319278, abs=1e-6)
    assert res.prime_put > 0.25  # prime d'exercice anticipé du put


def test_call_americain_egal_europeen_sans_dividende():
    """q = 0 : exercer un call avant l'échéance n'est jamais optimal (Merton, 1973)."""
    res = americaine_crr_controle(**AMER, n_pas=1_000)
    assert res.arbre.amer_call == pytest.approx(res.arbre.euro_call, abs=1e-10)
    assert res.cv_call == pytest.approx(res.bsm_call, abs=1e-10)
    assert res.prime_call == pytest.approx(0.0, abs=1e-10)


def test_call_americain_avec_dividende_vaut_plus():
    res = americaine_crr_controle(100, 100, 0.03, 0.08, 0.2, 1.0, n_pas=500)
    assert res.arbre.amer_call > res.arbre.euro_call + 0.05


@pytest.mark.parametrize("option", ["call", "put"])
def test_convergence_vers_bsm(option):
    """L'erreur de l'arbre européen décroît en O(1/n)."""
    bsm = prix_bsm(**EURO, option=option)
    erreurs = []
    for n in (50, 200, 800, 3_200):
        a = arbre_crr(**EURO, n_pas=n)
        erreurs.append(abs((a.euro_call if option == "call" else a.euro_put) - bsm))
    assert all(e2 < e1 for e1, e2 in zip(erreurs, erreurs[1:], strict=False))
    assert erreurs[-1] < 2e-3
    assert erreurs[-1] * 3_200 < 2 * erreurs[0] * 50  # ordre 1 : n·erreur reste borné


def test_parite_dans_l_arbre():
    """La parité call-put tient aussi sur l'arbre européen (même probabilité p)."""
    a = arbre_crr(**EURO, n_pas=500)
    import math

    forward = 100 * math.exp(-0.02) - 100 * math.exp(-0.05)
    assert a.euro_call - a.euro_put == pytest.approx(forward, abs=1e-10)


def test_bornes_de_l_americaine():
    a = arbre_crr(**AMER, n_pas=500)
    assert a.amer_put >= max(AMER["K"] - AMER["S"], 0)
    assert a.amer_put >= a.euro_put


def test_validations():
    with pytest.raises(ValueError, match="entre 50 et 5 000"):
        arbre_crr(**AMER, n_pas=10)
    with pytest.raises(ValueError, match="strictement positive"):
        arbre_crr(40, 40, 0.06, 0, 0.0, 1, 100)

"""Tests des options asiatiques."""

import math

import pytest

from pricer.asian import asiatique_geometrique, mc_asiatique
from pricer.bsm import prix_bsm
from tests.references import EURO, GRAINE

#: Valeur de l'Excel pour le call arithmétique avec contrôle (N = 50 000).
EXCEL_CV_CALL, EXCEL_SE_CALL = 5.519595, 0.00098


def test_geometrique_valeurs_excel():
    assert asiatique_geometrique(**EURO, n_fixings=12, option="call") == pytest.approx(
        5.3277, abs=1e-4
    )
    assert asiatique_geometrique(**EURO, n_fixings=12, option="put") == pytest.approx(
        4.0888, abs=1e-4
    )
    assert asiatique_geometrique(**EURO, n_fixings=12) == pytest.approx(5.327706, abs=1e-6)


def test_geometrique_un_fixing_egal_bsm():
    for option in ("call", "put"):
        assert asiatique_geometrique(**EURO, n_fixings=1, option=option) == pytest.approx(
            prix_bsm(**EURO, option=option), abs=1e-12
        )


@pytest.fixture(scope="module")
def resultats():
    return mc_asiatique(**EURO, n_fixings=12, n_sim=50_000, graine=GRAINE)


def test_call_arithmetique_avec_controle(resultats):
    cv = resultats.estimations["call"]["controle"]
    assert cv.prix == pytest.approx(5.52, abs=0.005)
    ecart = abs(cv.prix - EXCEL_CV_CALL) / math.hypot(cv.se, EXCEL_SE_CALL)
    assert ecart < 3


def test_moteur_valide_par_la_geometrique(generateur):
    """z géométrique : la MC de la moyenne géométrique retrouve la formule exacte."""
    res = mc_asiatique(**EURO, n_fixings=12, n_sim=50_000, graine=GRAINE, generateur=generateur)
    assert abs(res.diagnostics["z_geo_call"]) < 3
    assert abs(res.diagnostics["z_geo_put"]) < 3
    # Les trois estimateurs arithmétiques sont cohérents avec l'estimateur contrôlé.
    for option in ("call", "put"):
        cv = res.estimations[option]["controle"]
        for methode in ("standard", "antithetique"):
            est = res.estimations[option][methode]
            assert abs(est.prix - cv.prix) < 3 * math.hypot(est.se, cv.se)


def test_controle_reduit_fortement_la_variance(resultats):
    for option in ("call", "put"):
        m = resultats.estimations[option]
        assert m["controle"].se < m["antithetique"].se < m["standard"].se
        assert resultats.diagnostics[f"gain_cv_{option}"] > 100
        assert resultats.diagnostics[f"corr_{option}"] > 0.999


def test_ordre_des_prix(resultats):
    """Moyenne géométrique ≤ arithmétique (AM-GM) ; la moyenne lisse la volatilité."""
    call = resultats.estimations["call"]["controle"].prix
    assert asiatique_geometrique(**EURO, n_fixings=12) < call < prix_bsm(**EURO)


def test_validations():
    with pytest.raises(ValueError, match="dates de fixing"):
        asiatique_geometrique(**EURO, n_fixings=0)
    with pytest.raises(ValueError, match="50 000 000"):
        mc_asiatique(**EURO, n_fixings=1_000, n_sim=100_000)

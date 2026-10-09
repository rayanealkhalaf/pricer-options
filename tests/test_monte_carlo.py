"""Tests du Monte-Carlo européen et des estimateurs génériques."""

import numpy as np
import pytest

from pricer.monte_carlo import (
    ResultatMC,
    convergence_europeenne,
    estimer,
    estimer_avec_controle,
    grille_journaliere,
    mc_europeenne,
    simuler_trajectoires,
)
from tests.references import EURO, GRAINE


@pytest.fixture(scope="module")
def resultats_pcg():
    return mc_europeenne(**EURO, n_sim=100_000, graine=GRAINE)


def test_z_scores_contre_bsm(generateur):
    """Les trois méthodes, call et put : |z| < 3 face à la formule fermée."""
    res = mc_europeenne(**EURO, n_sim=100_000, graine=GRAINE, generateur=generateur)
    for option, scores in res.z_scores().items():
        for methode, z in scores.items():
            assert abs(z) < 3, (option, methode, z)


def test_reduction_de_variance(resultats_pcg):
    for option in ("call", "put"):
        m = resultats_pcg.estimations[option]
        assert m["controle"].se < m["standard"].se
        assert m["antithetique"].se < m["standard"].se
    assert resultats_pcg.diagnostics["gain_cv_call"] > 3
    # À coût égal (deux payoffs par tirage), l'antithétique reste rentable.
    assert resultats_pcg.diagnostics["efficacite_av_call"] > 1


def test_ic_et_diagnostics(resultats_pcg):
    est = resultats_pcg.estimations["call"]["standard"]
    assert est.ic_haut - est.ic_bas == pytest.approx(2 * 1.96 * est.se)
    d = resultats_pcg.diagnostics
    # Avec X = e^{−rT} S_T : Call − Put = X − K e^{−rT}, donc β_C − β_P = 1.
    assert d["beta_call"] - d["beta_put"] == pytest.approx(1.0, abs=1e-10)
    assert 0 < d["corr_call"] < 1 and -1 < d["corr_put"] < 0


def test_reproductible_avec_graine():
    a = mc_europeenne(**EURO, n_sim=5_000, graine=7)
    b = mc_europeenne(**EURO, n_sim=5_000, graine=7)
    assert a.estimations["call"]["standard"] == b.estimations["call"]["standard"]
    assert a.graine == 7


def test_volatilite_nulle():
    """σ = 0 : payoff déterministe, SE nulle, β* = 0 (garde-fou du VBA)."""
    res = mc_europeenne(100, 100, 0.05, 0.02, 0.0, 1.0, n_sim=1_000, graine=1)
    for m in res.estimations["call"].values():
        assert m.prix == pytest.approx(res.references["call"], abs=1e-12)
        assert m.se == pytest.approx(0.0, abs=1e-12)
    assert res.diagnostics["beta_call"] == 0.0


def test_estimateurs_generiques():
    y = np.array([1.0, 2.0, 3.0, 4.0])
    r = estimer(y)
    assert r.prix == 2.5 and r.se == pytest.approx(np.std(y, ddof=1) / 2)
    # Contrôle parfait : Y = 2X + 1, E[X] connu → prix exact, variance nulle.
    rng = np.random.default_rng(0)
    x = rng.normal(size=1_000)
    cv = estimer_avec_controle(2 * x + 1, x, 0.0)
    assert cv.beta == pytest.approx(2.0)
    assert cv.estimation.prix == pytest.approx(1.0)
    assert cv.estimation.se == pytest.approx(0.0, abs=1e-12)
    assert ResultatMC(1.0, 0.0, 10).z_score(2.0) == 0.0  # IFERROR → 0


def test_convergence_en_racine_de_n():
    tailles = [1_000, 4_000, 16_000, 64_000]
    conv = convergence_europeenne(**EURO, tailles=tailles, graine=GRAINE)
    se = conv["se_standard"]
    # SE ∝ 1/√N : multiplier N par 4 divise la SE par environ 2.
    assert np.all(np.diff(se) < 0)
    np.testing.assert_allclose(se[:-1] / se[1:], 2.0, rtol=0.15)


def test_trajectoires():
    temps = grille_journaliere(1.0)
    assert temps.size == 253 and temps[-1] == pytest.approx(1.0)
    assert grille_journaliere(0.5)[-1] == pytest.approx(0.5)
    assert grille_journaliere(0.1)[-1] == pytest.approx(0.1)  # pas résiduel
    chemins = simuler_trajectoires(100, 0.05, 0.02, 0.2, temps, n_chemins=20_000, graine=3)
    assert chemins.shape == (20_000, 253)
    assert np.all(chemins[:, 0] == 100)
    # E[S_T] = S e^{(r−q)T} (à 4 erreurs standards près)
    st = chemins[:, -1]
    assert abs(st.mean() - 100 * np.exp(0.03)) < 4 * st.std() / np.sqrt(st.size)
    with pytest.raises(ValueError, match="commencer à 0"):
        simuler_trajectoires(100, 0.05, 0.02, 0.2, np.array([0.5, 1.0]))


def test_entrees_invalides():
    with pytest.raises(ValueError, match="entier entre 1 000 et 10 000 000"):
        mc_europeenne(**EURO, n_sim=10)

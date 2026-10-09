"""Tests de Longstaff-Schwartz."""

import numpy as np
import pytest

from pricer.lsm import lsm_sur_chemins, prix_lsm, simuler_chemins_antithetiques
from pricer.trees import americaine_crr_controle
from tests.references import AMER, GRAINE


@pytest.fixture(scope="module")
def reference():
    return americaine_crr_controle(**AMER, n_pas=1_000)


def test_put_americain_proche_de_l_arbre(generateur, reference):
    """LSM ≈ 2,31, à moins de 3 erreurs standards de CRR + variable de contrôle."""
    res = prix_lsm(
        **AMER, option="put", n_sim=20_000, n_dates=50, graine=GRAINE, generateur=generateur
    )
    assert abs(res.prix - 2.31) < 3 * res.se
    assert abs(res.z_score(reference.cv_put)) < 3
    assert not res.exercice_immediat
    assert res.n == 10_000  # paires antithétiques


def test_call_sans_dividende(reference):
    res = prix_lsm(**AMER, option="call", n_sim=20_000, n_dates=50, graine=GRAINE)
    assert abs(res.z_score(reference.cv_call)) < 3


def test_exercice_immediat():
    """Put très dans la monnaie avec taux élevé : exercer tout de suite est optimal."""
    res = prix_lsm(10, 40, 0.10, 0, 0.2, 1, option="put", n_sim=2_000, n_dates=10, graine=1)
    assert res.exercice_immediat and res.prix == 30.0 and res.se == 0.0


def test_frontiere_d_exercice_sous_le_strike():
    res = prix_lsm(**AMER, option="put", n_sim=20_000, n_dates=50, graine=GRAINE)
    f = res.frontiere[~np.isnan(res.frontiere)]
    assert np.all(f <= AMER["K"]) and f.size > 40
    assert f[-1] >= f[0]  # la frontière remonte vers K à l'approche de l'échéance


def test_chemins_antithetiques():
    chemins, _ = simuler_chemins_antithetiques(40, 0.06, 0, 0.2, 1, 1_000, 20, graine=5)
    ln = np.log(chemins / 40)
    # Les deux chemins d'une paire sont symétriques autour de la dérive.
    derive = (0.06 - 0.02) * np.arange(1, 21) / 20
    np.testing.assert_allclose(
        ln[0::2] + ln[1::2], np.broadcast_to(2 * derive, (500, 20)), atol=1e-12
    )


def test_meme_graine_memes_chemins():
    """Comme dans le VBA, call et put partagent les chemins si la graine est la même."""
    chemins, _ = simuler_chemins_antithetiques(
        **{k: AMER[k] for k in ("S", "r", "q", "vol", "T")}, n_sim=2_000, n_dates=10, graine=3
    )
    direct = prix_lsm(**AMER, option="put", n_sim=2_000, n_dates=10, graine=3)
    via_chemins = lsm_sur_chemins(chemins, AMER["S"], AMER["K"], AMER["r"], AMER["T"], "put")
    assert direct.prix == via_chemins.prix


def test_validations():
    with pytest.raises(ValueError, match="dates d'exercice"):
        prix_lsm(**AMER, n_dates=5)
    with pytest.raises(ValueError, match="5 000 000"):
        prix_lsm(**AMER, n_sim=200_000, n_dates=500)

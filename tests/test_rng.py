"""Tests des générateurs PCG64 et MRG32k3a."""

import numpy as np
import pytest
from scipy import stats

from pricer.rng import GenerateurPCG64, MRG32k3a, creer_generateur


def test_mrg32k3a_valeur_de_reference():
    """Premier tirage de MRG32k3a avec les six graines à 12345 (L'Ecuyer, 1999)."""
    g = MRG32k3a(1)
    g.definir_etat((12345, 12345, 12345), (12345, 12345, 12345))
    assert g.uniforme() == pytest.approx(0.127011122046577, abs=1e-14)


@pytest.mark.parametrize("n", [1, 255, 256, 1_000, 4_097])
def test_mrg32k3a_vectorise_identique_au_sequentiel(n):
    """Le saut en avant redonne exactement la suite de la boucle VBA."""
    a, b = MRG32k3a(2024), MRG32k3a(2024)
    vecteur = a.uniformes(n)
    sequence = np.array([b.uniforme() for _ in range(n)])
    np.testing.assert_array_equal(vecteur, sequence)
    assert a.etat == b.etat  # l'état final est lui aussi identique


def test_box_muller_vectorise_identique_au_sequentiel():
    a, b = MRG32k3a(7), MRG32k3a(7)
    z1 = a.normales(3)  # nombre impair : une normale reste en réserve
    z2 = a.normales((2, 500))
    seq = np.array([b.normale() for _ in range(1003)])
    np.testing.assert_allclose(np.concatenate([z1, z2.ravel()]), seq, rtol=0, atol=1e-15)


def test_uniformes_dans_l_intervalle_ouvert():
    u = MRG32k3a(5).uniformes(100_000)
    assert u.min() > 0.0 and u.max() < 1.0


@pytest.mark.parametrize("methode", ["pcg64", "mrg32k3a"])
def test_normales_statistiquement_correctes(methode):
    z = creer_generateur(123, methode).normales(200_000)
    assert abs(z.mean()) < 4 / np.sqrt(z.size)
    assert abs(z.var() - 1) < 0.02
    assert stats.kstest(z, "norm").pvalue > 0.01


def test_reproductibilite_et_graine_aleatoire():
    np.testing.assert_array_equal(GenerateurPCG64(9).normales(10), GenerateurPCG64(9).normales(10))
    g = creer_generateur(0)  # 0 = graine aléatoire, comme dans l'Excel
    assert g.graine_utilisee > 0
    with pytest.raises(ValueError, match="Générateur inconnu"):
        creer_generateur(1, "mersenne")

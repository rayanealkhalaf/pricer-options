"""Tests des contrôles de validation (repris du VBA)."""

import math

import pytest

from pricer.validation import (
    probabilite_crr,
    valider_arbre,
    valider_barriere,
    valider_entier,
    valider_marche,
    valider_nombre,
    valider_option,
    valider_produit,
)


def test_parametres_valides_acceptes():
    valider_marche(100, 100, 0.05, 0.02, 0.2, 1.0)
    valider_marche(100, 100, 0.05, 0.02, 0.0, 1.0, vol_nulle_permise=True)


@pytest.mark.parametrize(
    ("params", "message"),
    [
        ((0, 100, 0.05, 0, 0.2, 1), "S doit être strictement positif"),
        ((-5, 100, 0.05, 0, 0.2, 1), "S doit être strictement positif"),
        ((100, 0, 0.05, 0, 0.2, 1), "K doit être strictement positif"),
        ((100, 100, 0.05, 0, -0.1, 1), "strictement positive"),
        ((100, 100, 0.05, 0, 0.0, 1), "strictement positive"),
        ((100, 100, 0.05, 0, 0.2, 0), "maturité doit être strictement positive"),
        ((100, 100, 0.05, 0, 0.2, 51), "T doit être <= 50"),
        ((100, 100, 20.0, 0, 0.2, 50), "hors domaine numérique"),
    ],
)
def test_parametres_invalides(params, message):
    with pytest.raises(ValueError, match=message):
        valider_marche(*params)


def test_volatilite_negative_refusee_meme_si_nulle_permise():
    with pytest.raises(ValueError, match="ne peut pas être négative"):
        valider_marche(100, 100, 0.05, 0, -0.01, 1, vol_nulle_permise=True)


@pytest.mark.parametrize("valeur", ["100", None, True, math.nan, math.inf, [1]])
def test_nombre_invalide(valeur):
    with pytest.raises(ValueError, match="doit être un nombre"):
        valider_nombre(valeur, "Le spot S")


def test_entier():
    assert valider_entier(1000, 1000, 2000, "N") == 1000
    assert valider_entier(1500.0, 1000, 2000, "N") == 1500
    for mauvais in (999, 2001, 1500.5, "1500", True):
        with pytest.raises(ValueError, match="N doit être un entier entre 1 000 et 2 000"):
            valider_entier(mauvais, 1000, 2000, "N")


def test_option():
    assert valider_option("call") is True
    assert valider_option("PUT") is False
    with pytest.raises(ValueError, match="'call' ou 'put'"):
        valider_option("straddle")


def test_barriere_et_produit():
    assert valider_barriere(90) == 90.0
    with pytest.raises(ValueError, match="H > 0"):
        valider_barriere(0)
    with pytest.raises(ValueError, match="trop gros"):
        valider_produit(10_000, 10_000, 5e7, "trop gros")


def test_probabilite_crr_et_arbre():
    p = probabilite_crr(0.06, 0.0, 0.2, 1 / 1000)
    assert 0.5 < p < 0.51
    # Taux très élevé, volatilité faible, peu de pas : p > 1, arbre refusé.
    with pytest.raises(ValueError, match=r"hors de \]0,1\["):
        valider_arbre(100, 0.5, 0.0, 0.01, 1.0, 50)

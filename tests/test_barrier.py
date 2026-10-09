"""Tests des options barrières."""

import pytest

from pricer.barrier import (
    TYPES_BARRIERE,
    analyser_type,
    barriere_ajustee_bgk,
    mc_barriere,
    parites_barriere,
    prix_barriere,
    prix_barrieres,
)
from pricer.bsm import prix_bsm
from tests.references import BARR, GRAINE

#: Valeurs de l'onglet « Options Barrières » (formules de cellule).
EXCEL = {
    "DOC": 8.138811, "DIC": 2.984951, "UOC": 0.0, "UIC": 11.123762,
    "DOP": 0.086816, "DIP": 8.140021, "UOP": 0.0, "UIP": 8.226837,
}  # fmt: skip


def test_valeurs_excel():
    assert prix_barriere(**BARR, type_barriere="DOC") == pytest.approx(8.1388, abs=1e-4)
    assert prix_barriere(**BARR, type_barriere="DIC") == pytest.approx(2.9850, abs=1e-4)
    prix = prix_barrieres(**BARR)
    for code, attendu in EXCEL.items():
        assert prix[code] == pytest.approx(attendu, abs=1e-6), code


PARAMS_PARITE = [
    BARR,
    {**BARR, "H": 115.0},  # barrière haute, K < H
    {**BARR, "K": 80.0},  # barrière basse, K = 80 < H = 90
    {**BARR, "K": 120.0, "H": 110.0},  # barrière haute, K > H
    {**BARR, "q": 0.0, "r": 0.01, "vol": 0.4, "T": 3.0},
]


@pytest.mark.parametrize("p", PARAMS_PARITE)
def test_parite_in_out_vanille(p):
    for nom, ecart in parites_barriere(prix_barrieres(**p)).items():
        assert abs(ecart) < 1e-10, nom


@pytest.mark.parametrize("p", PARAMS_PARITE)
def test_prix_positifs_et_bornes(p):
    prix = prix_barrieres(**p)
    for code in TYPES_BARRIERE:
        vanille = prix["call"] if code.endswith("C") else prix["put"]
        assert -1e-12 <= prix[code] <= vanille + 1e-12, code


@pytest.mark.parametrize("H", [100.0, 110.0])
def test_spot_au_dela_d_une_barriere_basse(H):
    """S ≤ H pour une barrière Down : déjà touchée, Out = 0 et In = vanille."""
    p = {**BARR, "H": H}
    for opt, out, inn in (("call", "DOC", "DIC"), ("put", "DOP", "DIP")):
        assert prix_barriere(**p, type_barriere=out) == 0.0
        vanille = prix_bsm(**{k: v for k, v in p.items() if k != "H"}, option=opt)
        assert prix_barriere(**p, type_barriere=inn) == pytest.approx(vanille, abs=1e-12)


@pytest.mark.parametrize("H", [100.0, 80.0])
def test_spot_au_dela_d_une_barriere_haute(H):
    p = {**BARR, "H": H}
    for opt, out, inn in (("call", "UOC", "UIC"), ("put", "UOP", "UIP")):
        assert prix_barriere(**p, type_barriere=out) == 0.0
        vanille = prix_bsm(**{k: v for k, v in p.items() if k != "H"}, option=opt)
        assert prix_barriere(**p, type_barriere=inn) == pytest.approx(vanille, abs=1e-12)


def test_barriere_lointaine_tend_vers_la_vanille():
    p = {**BARR, "H": 1.0}
    assert prix_barriere(**p, type_barriere="DOC") == pytest.approx(
        prix_bsm(100, 100, 0.05, 0.02, 0.25, 1.0), abs=1e-10
    )


def test_mc_pont_brownien_z_scores(generateur):
    """Surveillance continue (pont brownien) : |z| < 3 pour les 8 types."""
    res = mc_barriere(
        **BARR,
        n_pas=252,
        surveillance="continue",
        n_sim=50_000,
        graine=GRAINE,
        generateur=generateur,
    )
    for code, scores in res.z_scores().items():
        assert abs(scores["continue"]) < 3, code
    for nom, ecart in res.diagnostics.items():
        if nom.startswith("parite_mc"):
            assert abs(ecart) < 1e-10, nom


def test_mc_pont_brownien_sans_biais_meme_avec_peu_de_pas():
    """La correction est exacte : 4 pas suffisent pour retrouver la formule continue."""
    res = mc_barriere(**BARR, n_pas=4, surveillance="continue", n_sim=200_000, graine=GRAINE)
    for code in ("DOC", "DIC", "DOP", "DIP"):
        assert abs(res.z_scores()[code]["continue"]) < 3, code


def test_mc_surveillance_discrete():
    """En discret, la barrière est moins souvent touchée : Out > formule continue.

    La correction de Broadie-Glasserman-Kou (barrière décalée) explique l'écart.
    """
    res = mc_barriere(**BARR, n_pas=12, surveillance=1, n_sim=100_000, graine=GRAINE)
    doc = res.estimations["DOC"]["discrete"]
    assert doc.prix > res.references["DOC"] + 3 * doc.se
    assert abs(doc.z_score(res.diagnostics["bgk_DOC"])) < 3


def test_mc_spot_au_dela_de_la_barriere():
    res = mc_barriere(**{**BARR, "H": 105.0}, n_pas=50, n_sim=5_000, graine=GRAINE)
    assert res.estimations["DOC"]["continue"].prix == 0.0
    assert res.estimations["DIC"]["continue"] == res.estimations["call"]["continue"]


def test_bgk_et_types():
    assert barriere_ajustee_bgk(90, 100, 0.25, 1, 252) < 90
    assert barriere_ajustee_bgk(110, 100, 0.25, 1, 252) > 110
    assert analyser_type("down-and-out call").code == "DOC"
    assert analyser_type("Up and In Put").code == "UIP"
    with pytest.raises(ValueError, match="Type de barrière inconnu"):
        analyser_type("XYZ")


def test_validations():
    with pytest.raises(ValueError, match="H > 0"):
        prix_barriere(100, 100, 0, 0.05, 0.02, 0.25, 1)
    with pytest.raises(ValueError, match="0 \\(continue\\) ou 1"):
        mc_barriere(**BARR, surveillance=2)

"""Test de fumée de l'interface Streamlit : l'app se charge sans erreur."""

from pathlib import Path

import pytest

AppTest = pytest.importorskip("streamlit.testing.v1").AppTest
APP = str(Path(__file__).resolve().parents[1] / "app.py")


def lancer():
    app = AppTest.from_file(APP, default_timeout=180)
    app.run()
    return app


def test_valeurs_par_defaut():
    app = lancer()
    assert not app.exception
    assert len(app.tabs) == 5


def test_option_tres_en_dehors_de_la_monnaie():
    """K = 200 et σ = 5 % : prix BSM ≈ 0, le champ « prix de marché » ne doit pas planter."""
    app = lancer()
    app.number_input(key="eu_K").set_value(200.0)
    app.number_input(key="eu_v").set_value(5.0)
    app.run()
    assert not app.exception


def test_reinitialisation_des_parametres():
    app = lancer()
    app.number_input(key="eu_K").set_value(130.0)
    app.run()
    app.button[0].click()
    app.run()
    assert app.number_input(key="eu_K").value == 100.0
    assert not app.exception

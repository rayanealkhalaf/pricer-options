"""Paramètres de référence partagés par les tests (valeurs de l'Excel)."""

#: Onglets européen et asiatique : S = K = 100, r = 5 %, q = 2 %, σ = 20 %, T = 1.
EURO = {"S": 100.0, "K": 100.0, "r": 0.05, "q": 0.02, "vol": 0.20, "T": 1.0}
#: Onglet américain : S = K = 40, r = 6 %, q = 0, σ = 20 %, T = 1.
AMER = {"S": 40.0, "K": 40.0, "r": 0.06, "q": 0.0, "vol": 0.20, "T": 1.0}
#: Onglet barrières : S = K = 100, H = 90, r = 5 %, q = 2 %, σ = 25 %, T = 1.
BARR = {"S": 100.0, "K": 100.0, "H": 90.0, "r": 0.05, "q": 0.02, "vol": 0.25, "T": 1.0}

#: Graine fixée : les tests Monte-Carlo sont déterministes.
GRAINE = 42

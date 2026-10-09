"""Arbre binomial de Cox-Ross-Rubinstein (1979) : options européennes et américaines.

Reprise de la procédure VBA ``ArbreCRR`` : une **seule** induction arrière
calcule les quatre prix (européen et américain, call et put) sur le même arbre,
puis ``CalculerAmericaine`` applique la correction par variable de contrôle.

Paramétrage CRR, avec ``Δt = T/n`` :

.. math::

    u = e^{σ\\sqrt{Δt}}, \\qquad d = 1/u, \\qquad
    p = \\frac{e^{(r-q)Δt} - d}{u - d}

Le nœud ``j`` (nombre de hausses) de l'étape ``i`` vaut ``S·u^{2j−i}``. Comme
``u·d = 1``, l'arbre se recombine : il n'y a que ``i + 1`` nœuds à l'étape ``i``.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from pricer.bsm import prix_bsm
from pricer.validation import probabilite_crr, valider_arbre, valider_entier, valider_marche

#: Bornes du nombre de pas, comme dans l'onglet « Options Américaines ».
PAS_MIN, PAS_MAX = 50, 5_000


@dataclass(frozen=True)
class PrixArbre:
    """Les quatre prix issus d'une même induction arrière."""

    euro_call: float
    euro_put: float
    amer_call: float
    amer_put: float


def arbre_crr(
    S: float, K: float, r: float, q: float, vol: float, T: float, n_pas: int = 1_000
) -> PrixArbre:
    """Prix européens et américains par l'arbre CRR.

    Induction arrière, de ``i = n − 1`` jusqu'à 0 :

    .. math::

        V^{eu}_{i,j} = e^{-rΔt}\\,[p\\,V_{i+1,j+1} + (1-p)\\,V_{i+1,j}]

        V^{am}_{i,j} = \\max\\big(e^{-rΔt}[p\\,V^{am}_{i+1,j+1} + (1-p)\\,V^{am}_{i+1,j}],\\;
        \\text{payoff}(S_{i,j})\\big)

    Le ``max`` entre valeur de continuation et valeur d'exercice immédiat est
    la seule différence entre européen et américain. Chaque étape est
    vectorisée sur les nœuds (une boucle sur le temps, aucune sur les nœuds).
    L'erreur de l'arbre européen face à BSM décroît en ``O(1/n)``, avec une
    oscillation selon la position du strike entre les nœuds.

    Args:
        n_pas: nombre de pas de temps (50 à 5 000).
    """
    valider_marche(S, K, r, q, vol, T)
    n = valider_entier(n_pas, PAS_MIN, PAS_MAX, "Le nombre de pas de l'arbre")
    valider_arbre(S, r, q, vol, T, n)

    dt = T / n
    lu = vol * math.sqrt(dt)
    p = probabilite_crr(r, q, vol, dt)
    actu = math.exp(-r * dt)
    pu, pd = actu * p, actu * (1.0 - p)

    # Puissances S·u^k pour k = −n..n (indice k + n), calculées une seule fois.
    s_pow = S * np.exp(np.arange(-n, n + 1) * lu)
    s_final = s_pow[0 : 2 * n + 1 : 2]  # S·u^{2j−n}, j = 0..n
    v_ec = np.maximum(s_final - K, 0.0)
    v_ep = np.maximum(K - s_final, 0.0)
    v_ac = v_ec.copy()
    v_ap = v_ep.copy()

    for i in range(n - 1, -1, -1):
        s_i = s_pow[n - i : n + i + 1 : 2]  # S·u^{2j−i}, j = 0..i
        v_ec = pu * v_ec[1:] + pd * v_ec[:-1]
        v_ep = pu * v_ep[1:] + pd * v_ep[:-1]
        v_ac = np.maximum(pu * v_ac[1:] + pd * v_ac[:-1], s_i - K)
        v_ap = np.maximum(pu * v_ap[1:] + pd * v_ap[:-1], K - s_i)

    return PrixArbre(float(v_ec[0]), float(v_ep[0]), float(v_ac[0]), float(v_ap[0]))


@dataclass(frozen=True)
class ResultatAmericaine:
    """Résultats de l'onglet « Options Américaines » (partie arbre)."""

    arbre: PrixArbre
    bsm_call: float
    bsm_put: float
    cv_call: float
    cv_put: float

    @property
    def prime_call(self) -> float:
        """Prime d'exercice anticipé du call : ``Am_CV − BSM``."""
        return self.cv_call - self.bsm_call

    @property
    def prime_put(self) -> float:
        """Prime d'exercice anticipé du put : ``Am_CV − BSM``."""
        return self.cv_put - self.bsm_put


def americaine_crr_controle(
    S: float, K: float, r: float, q: float, vol: float, T: float, n_pas: int = 1_000
) -> ResultatAmericaine:
    """Prix américain corrigé par variable de contrôle (« valeur de référence »).

    .. math:: V^{am}_{CV} = V^{am}_{arbre} + \\big(V^{eu}_{BSM} - V^{eu}_{arbre}\\big)

    Idée : l'arbre commet presque la même erreur de discrétisation sur
    l'américaine et sur l'européenne (même grille, même payoff). Pour
    l'européenne, l'erreur est connue exactement grâce à BSM : on la retranche
    du prix américain. La convergence est nettement plus rapide et moins
    oscillante qu'avec l'arbre seul (Hull & White, 1988).
    """
    arbre = arbre_crr(S, K, r, q, vol, T, n_pas)
    bsm_call = prix_bsm(S, K, r, q, vol, T, "call")
    bsm_put = prix_bsm(S, K, r, q, vol, T, "put")
    return ResultatAmericaine(
        arbre=arbre,
        bsm_call=bsm_call,
        bsm_put=bsm_put,
        cv_call=arbre.amer_call + (bsm_call - arbre.euro_call),
        cv_put=arbre.amer_put + (bsm_put - arbre.euro_put),
    )

"""Formule fermée de Black-Scholes-Merton avec dividende continu.

Modèle : sous la probabilité risque-neutre, le sous-jacent suit un mouvement
brownien géométrique

.. math:: dS_t = (r - q)\\,S_t\\,dt + σ\\,S_t\\,dW_t

et une option européenne de maturité ``T`` vaut ``e^{-rT}·E[payoff(S_T)]``.
"""

from __future__ import annotations

import math

from scipy.optimize import brentq
from scipy.special import ndtr

from pricer.validation import valider_marche, valider_nombre, valider_option


def d1_d2(S: float, K: float, r: float, q: float, vol: float, T: float) -> tuple[float, float]:
    """Calcule d₁ et d₂.

    .. math::

        d_1 = \\frac{\\ln(S/K) + (r - q + σ^2/2)\\,T}{σ\\sqrt{T}}, \\qquad
        d_2 = d_1 - σ\\sqrt{T}

    Requiert ``σ > 0`` (d₁ n'est pas défini pour σ = 0, comme ``#N/A`` dans l'Excel).
    """
    valider_marche(S, K, r, q, vol, T)
    racine = vol * math.sqrt(T)
    d1 = (math.log(S / K) + (r - q + 0.5 * vol * vol) * T) / racine
    return d1, d1 - racine


def prix_bsm(
    S: float, K: float, r: float, q: float, vol: float, T: float, option: str = "call"
) -> float:
    """Prix Black-Scholes-Merton d'un call ou d'un put européen.

    .. math::

        C = S e^{-qT} N(d_1) - K e^{-rT} N(d_2)

        P = K e^{-rT} N(-d_2) - S e^{-qT} N(-d_1)

    Cas σ = 0 (autorisé, comme dans l'onglet européen) : le sous-jacent est
    déterministe et le prix vaut la valeur intrinsèque forward actualisée,
    ``max(S e^{-qT} − K e^{-rT}, 0)`` pour le call.

    Args:
        S: spot (> 0).
        K: strike (> 0).
        r: taux sans risque continu.
        q: taux de dividende continu.
        vol: volatilité (≥ 0).
        T: maturité en années (0 < T ≤ 50).
        option: ``"call"`` ou ``"put"``.

    Returns:
        Le prix de l'option.
    """
    valider_marche(S, K, r, q, vol, T, vol_nulle_permise=True)
    est_call = valider_option(option)
    s_actu = S * math.exp(-q * T)
    k_actu = K * math.exp(-r * T)
    if vol == 0.0:
        return max(s_actu - k_actu, 0.0) if est_call else max(k_actu - s_actu, 0.0)
    d1, d2 = d1_d2(S, K, r, q, vol, T)
    if est_call:
        return float(s_actu * ndtr(d1) - k_actu * ndtr(d2))
    return float(k_actu * ndtr(-d2) - s_actu * ndtr(-d1))


def parite_call_put(S: float, K: float, r: float, q: float, vol: float, T: float) -> float:
    """Écart à la parité call-put, nul en théorie.

    .. math:: C - P - (S e^{-qT} - K e^{-rT}) = 0

    La parité découle d'un argument de non-arbitrage (``C − P`` réplique un
    forward). Elle ne dépend pas du modèle : un écart non nul signale une erreur
    de formule.
    """
    c = prix_bsm(S, K, r, q, vol, T, "call")
    p = prix_bsm(S, K, r, q, vol, T, "put")
    return c - p - (S * math.exp(-q * T) - K * math.exp(-r * T))


def volatilite_implicite(
    prix: float,
    S: float,
    K: float,
    r: float,
    q: float,
    T: float,
    option: str = "call",
    vol_max: float = 5.0,
) -> float:
    """Volatilité implicite : le σ pour lequel le prix BSM égale le prix observé.

    Le prix BSM est strictement croissant en σ (vega > 0), donc la solution est
    unique quand elle existe. Elle existe si et seulement si le prix respecte
    les bornes de non-arbitrage :

    .. math::

        \\max(S e^{-qT} - K e^{-rT}, 0) < C < S e^{-qT}, \\qquad
        \\max(K e^{-rT} - S e^{-qT}, 0) < P < K e^{-rT}

    La racine est cherchée par la méthode de Brent sur ``]0, vol_max]`` :
    elle converge toujours (encadrement garanti), contrairement à Newton-Raphson
    qui peut diverger loin de la monnaie, là où le vega est quasi nul.

    Args:
        prix: prix de marché observé de l'option.
        S, K, r, q, T: paramètres de marché (voir :func:`prix_bsm`).
        option: ``"call"`` ou ``"put"``.
        vol_max: borne haute de la recherche (5 = 500 %).

    Returns:
        La volatilité implicite (en décimal, 0,2 = 20 %).

    Raises:
        ValueError: si le prix sort des bornes de non-arbitrage ou si la
            volatilité implicite dépasse ``vol_max``.
    """
    prix = valider_nombre(prix, "Le prix de marché")
    valider_marche(S, K, r, q, 0.0, T, vol_nulle_permise=True)
    est_call = valider_option(option)
    s_actu = S * math.exp(-q * T)
    k_actu = K * math.exp(-r * T)
    plancher = max(s_actu - k_actu, 0.0) if est_call else max(k_actu - s_actu, 0.0)
    plafond = s_actu if est_call else k_actu
    if not plancher < prix < plafond:
        raise ValueError(
            f"Le prix {prix:g} sort des bornes de non-arbitrage "
            f"]{plancher:.6g} ; {plafond:.6g}[ : aucune volatilité ne le reproduit."
        )

    def ecart(vol: float) -> float:
        return prix_bsm(S, K, r, q, vol, T, option) - prix

    vol_min = 1e-9
    if ecart(vol_max) < 0:
        raise ValueError(f"La volatilité implicite dépasse {vol_max:.0%}.")
    if ecart(vol_min) >= 0:
        return vol_min
    return float(brentq(ecart, vol_min, vol_max, xtol=1e-14, rtol=1e-12, maxiter=200))

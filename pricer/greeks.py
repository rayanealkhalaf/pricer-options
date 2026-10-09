"""Grecques analytiques de Black-Scholes-Merton (avec dividende continu q).

Conventions reprises de l'Excel :

- **Vega** pour une hausse de volatilité de **+1 point** (σ + 0,01) : ∂V/∂σ / 100 ;
- **Rho** pour une hausse de taux de **+1 point** (r + 0,01) : ∂V/∂r / 100 ;
- **Theta** **par jour calendaire** : ∂V/∂t / 365, où t est le temps écoulé
  (soit −∂V/∂T / 365).

Notation : φ est la densité de la loi normale, N sa fonction de répartition.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass

from scipy.special import ndtr

from pricer.bsm import d1_d2
from pricer.validation import valider_option

_INV_RACINE_2PI = 1.0 / math.sqrt(2.0 * math.pi)


@dataclass(frozen=True)
class Grecques:
    """Les cinq grecques d'une option européenne."""

    delta: float
    gamma: float
    vega: float
    theta: float
    rho: float

    def en_dict(self) -> dict[str, float]:
        """Renvoie les grecques sous forme de dictionnaire (affichage, tableaux)."""
        return asdict(self)


def grecques_bsm(
    S: float, K: float, r: float, q: float, vol: float, T: float, option: str = "call"
) -> Grecques:
    """Grecques analytiques d'un call ou d'un put européen.

    .. math::

        Δ_C = e^{-qT} N(d_1), \\qquad Δ_P = e^{-qT}\\,(N(d_1) - 1)

        Γ = \\frac{e^{-qT} φ(d_1)}{S σ \\sqrt{T}} \\quad (\\text{identique call/put})

        \\mathcal{V} = S e^{-qT} φ(d_1) \\sqrt{T} \\;/\\; 100

        Θ_C = \\Big[-\\frac{S e^{-qT} φ(d_1) σ}{2\\sqrt{T}} - rK e^{-rT} N(d_2)
              + qS e^{-qT} N(d_1)\\Big] / 365

        Θ_P = \\Big[-\\frac{S e^{-qT} φ(d_1) σ}{2\\sqrt{T}} + rK e^{-rT} N(-d_2)
              - qS e^{-qT} N(-d_1)\\Big] / 365

        ρ_C = K T e^{-rT} N(d_2) / 100, \\qquad ρ_P = -K T e^{-rT} N(-d_2) / 100

    Requiert σ > 0 (les grecques sont dégénérées pour σ = 0).
    """
    est_call = valider_option(option)
    d1, d2 = d1_d2(S, K, r, q, vol, T)
    eq = math.exp(-q * T)
    er = math.exp(-r * T)
    phi_d1 = _INV_RACINE_2PI * math.exp(-0.5 * d1 * d1)
    racine_t = math.sqrt(T)

    gamma = eq * phi_d1 / (S * vol * racine_t)
    vega = S * eq * phi_d1 * racine_t / 100.0
    terme_vol = -S * eq * phi_d1 * vol / (2.0 * racine_t)

    if est_call:
        delta = eq * ndtr(d1)
        theta = (terme_vol - r * K * er * ndtr(d2) + q * S * eq * ndtr(d1)) / 365.0
        rho = K * T * er * ndtr(d2) / 100.0
    else:
        delta = eq * (ndtr(d1) - 1.0)
        theta = (terme_vol + r * K * er * ndtr(-d2) - q * S * eq * ndtr(-d1)) / 365.0
        rho = -K * T * er * ndtr(-d2) / 100.0

    return Grecques(
        delta=float(delta),
        gamma=float(gamma),
        vega=float(vega),
        theta=float(theta),
        rho=float(rho),
    )

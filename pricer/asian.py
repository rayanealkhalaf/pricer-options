"""Options asiatiques à moyenne arithmétique discrète et strike fixe.

Reprise de la macro VBA ``CalculerAsiatique`` et de la fonction ``AsiatGeo``.

Produit : ``M`` fixings équirépartis ``t_i = i·T/M`` (i = 1..M) et

.. math::

    A = \\frac{1}{M}\\sum_{i=1}^{M} S_{t_i}, \\qquad
    \\text{Call} = e^{-rT}\\,E[\\max(A - K, 0)], \\qquad
    \\text{Put} = e^{-rT}\\,E[\\max(K - A, 0)]

Une somme de log-normales n'est pas log-normale : il n'existe pas de formule
fermée pour la moyenne arithmétique. En revanche, la moyenne **géométrique**
``G = (∏ S_{t_i})^{1/M}`` est exactement log-normale. Son prix exact sert donc de
variable de contrôle, très efficace puisque ``A`` et ``G`` sont presque
parfaitement corrélées.
"""

from __future__ import annotations

import math

import numpy as np
from scipy.special import ndtr

from pricer.bsm import prix_bsm
from pricer.monte_carlo import (
    ResultatsMC,
    estimer,
    estimer_avec_controle,
    gains_variance,
    lots_normales,
)
from pricer.rng import Methode, creer_generateur
from pricer.validation import valider_entier, valider_marche, valider_option, valider_produit


def parametres_geometriques(
    S: float, r: float, q: float, vol: float, T: float, n_fixings: int
) -> tuple[float, float]:
    """Moyenne et écart-type de ``ln G`` pour M fixings équirépartis.

    .. math::

        μ_G = \\ln S + (r - q - σ^2/2)\\,T\\,\\frac{M+1}{2M}, \\qquad
        σ_G = σ\\sqrt{T\\,\\frac{(M+1)(2M+1)}{6M^2}}

    Démonstration : ``ln G = ln S + (1/M) Σ_i X_{t_i}``, où ``X`` est un brownien
    avec dérive. Sa moyenne fait intervenir ``Σ t_i = T(M+1)/2`` et sa variance
    ``Σ_{i,k} min(t_i, t_k) = T·(M+1)(2M+1)/(6M)``.
    """
    m = n_fixings
    mu_g = math.log(S) + (r - q - 0.5 * vol * vol) * T * (m + 1) / (2.0 * m)
    sigma_g = vol * math.sqrt(T * (m + 1) * (2.0 * m + 1) / (6.0 * m * m))
    return mu_g, sigma_g


def asiatique_geometrique(
    S: float,
    K: float,
    r: float,
    q: float,
    vol: float,
    T: float,
    n_fixings: int = 12,
    option: str = "call",
) -> float:
    """Prix exact de l'asiatique à moyenne **géométrique** discrète.

    ``ln G ~ N(μ_G, σ_G²)`` (voir :func:`parametres_geometriques`), d'où une
    formule de type Black :

    .. math::

        F_G = E[G] = e^{μ_G + σ_G^2/2}, \\qquad
        d_1 = \\frac{μ_G - \\ln K + σ_G^2}{σ_G}, \\qquad d_2 = d_1 - σ_G

        \\text{Call} = e^{-rT}\\,[F_G\\,N(d_1) - K\\,N(d_2)], \\qquad
        \\text{Put} = e^{-rT}\\,[K\\,N(-d_2) - F_G\\,N(-d_1)]

    Pour M = 1, on retrouve exactement BSM (un seul fixing en T).
    """
    valider_marche(S, K, r, q, vol, T)
    est_call = valider_option(option)
    m = valider_entier(n_fixings, 1, 1_000, "Le nombre de dates de fixing")
    mu_g, sigma_g = parametres_geometriques(S, r, q, vol, T, m)
    forward = math.exp(mu_g + 0.5 * sigma_g * sigma_g)
    d1 = (mu_g - math.log(K) + sigma_g * sigma_g) / sigma_g
    d2 = d1 - sigma_g
    actu = math.exp(-r * T)
    if est_call:
        return float(actu * (forward * ndtr(d1) - K * ndtr(d2)))
    return float(actu * (K * ndtr(-d2) - forward * ndtr(-d1)))


def mc_asiatique(
    S: float,
    K: float,
    r: float,
    q: float,
    vol: float,
    T: float,
    n_fixings: int = 12,
    n_sim: int = 50_000,
    graine: int | None = None,
    generateur: Methode = "pcg64",
) -> ResultatsMC:
    """Asiatique arithmétique par Monte-Carlo : standard, antithétique, contrôle.

    Pour chaque simulation, on construit le log-chemin aux dates de fixing
    (schéma exact) ``x_i = x_{i−1} + (r − q − σ²/2)Δt + σ√Δt·Z_i`` et son
    antithétique (``−Z``) :

    1. **Standard** : payoff arithmétique actualisé sur le chemin ``Z`` ;
    2. **Antithétique** : moyenne des payoffs des chemins ``Z`` et ``−Z`` ;
    3. **Contrôle** : ``Ȳ − β*(Ḡ − G_exact)``, où ``G`` est le payoff
       géométrique du chemin ``Z`` et ``G_exact`` son prix exact
       (:func:`asiatique_geometrique`). La corrélation dépasse 0,999, d'où un
       gain de variance de plusieurs centaines.

    Diagnostic du moteur (``z_geo_call`` / ``z_geo_put``) :
    ``z = (Ḡ_MC − G_exact)/SE(G)``. Si le simulateur est correct, cette
    statistique est une N(0, 1) : c'est un test du générateur et du schéma.

    Args:
        n_fixings: nombre de dates de fixing M (1 à 1 000).
        n_sim: nombre de simulations (1 000 à 1 000 000), avec
            ``n_sim × M ≤ 50 000 000``.

    Returns:
        Un :class:`ResultatsMC`. Les références sont les prix géométriques exacts
        (``"geo_call"`` / ``"geo_put"``), et le prix BSM européen est donné
        dans les diagnostics pour comparaison.
    """
    valider_marche(S, K, r, q, vol, T)
    m = valider_entier(n_fixings, 1, 1_000, "Le nombre de dates de fixing")
    n = valider_entier(n_sim, 1_000, 1_000_000, "Le nombre de simulations")
    valider_produit(
        n, m, 50_000_000, "Simulations x fixings doit rester <= 50 000 000 (temps de calcul)."
    )
    gen = creer_generateur(graine, generateur)

    dt = T / m
    mu = (r - q - 0.5 * vol * vol) * dt
    sv = vol * math.sqrt(dt)
    actu = math.exp(-r * T)
    ln_s0 = math.log(S)
    geo_call = asiatique_geometrique(S, K, r, q, vol, T, m, "call")
    geo_put = asiatique_geometrique(S, K, r, q, vol, T, m, "put")

    c1, p1 = np.empty(n), np.empty(n)
    c_av, p_av = np.empty(n), np.empty(n)
    g_c, g_p = np.empty(n), np.empty(n)
    for debut, fin, z in lots_normales(gen, n, m):
        x1 = ln_s0 + np.cumsum(mu + sv * z, axis=1)
        x2 = ln_s0 + np.cumsum(mu - sv * z, axis=1)
        a1 = np.exp(x1).mean(axis=1)  # moyenne arithmétique, chemin Z
        a2 = np.exp(x2).mean(axis=1)  # moyenne arithmétique, chemin −Z
        g1 = np.exp(x1.mean(axis=1))  # moyenne géométrique, chemin Z
        cc1, pp1 = np.maximum(a1 - K, 0.0) * actu, np.maximum(K - a1, 0.0) * actu
        cc2, pp2 = np.maximum(a2 - K, 0.0) * actu, np.maximum(K - a2, 0.0) * actu
        c1[debut:fin], p1[debut:fin] = cc1, pp1
        c_av[debut:fin], p_av[debut:fin] = 0.5 * (cc1 + cc2), 0.5 * (pp1 + pp2)
        g_c[debut:fin] = np.maximum(g1 - K, 0.0) * actu
        g_p[debut:fin] = np.maximum(K - g1, 0.0) * actu

    cv_call = estimer_avec_controle(c1, g_c, geo_call)
    cv_put = estimer_avec_controle(p1, g_p, geo_put)
    geo_mc_call, geo_mc_put = estimer(g_c), estimer(g_p)
    estimations = {
        "call": {
            "standard": estimer(c1),
            "antithetique": estimer(c_av),
            "controle": cv_call.estimation,
        },
        "put": {
            "standard": estimer(p1),
            "antithetique": estimer(p_av),
            "controle": cv_put.estimation,
        },
        "geo_call": {"standard": geo_mc_call},
        "geo_put": {"standard": geo_mc_put},
    }
    diagnostics = {
        "beta_call": cv_call.beta,
        "beta_put": cv_put.beta,
        "corr_call": cv_call.correlation,
        "corr_put": cv_put.correlation,
        "z_geo_call": geo_mc_call.z_score(geo_call),
        "z_geo_put": geo_mc_put.z_score(geo_put),
        "bsm_call": prix_bsm(S, K, r, q, vol, T, "call"),
        "bsm_put": prix_bsm(S, K, r, q, vol, T, "put"),
        **gains_variance({k: estimations[k] for k in ("call", "put")}),
    }
    references = {"geo_call": geo_call, "geo_put": geo_put}
    return ResultatsMC(estimations, references, diagnostics, gen.graine_utilisee)

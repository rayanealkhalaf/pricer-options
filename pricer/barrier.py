"""Options barrières : formules de Reiner-Rubinstein (1991) et Monte-Carlo.

Les huit barrières standard (sans rebate) sont désignées par un code à trois
lettres :

========  ===========================  =========================================
Code      Nom                          Payoff à maturité
========  ===========================  =========================================
``DOC``   Down-and-Out Call            (S_T − K)⁺ si S n'a jamais touché H (H < S₀)
``DIC``   Down-and-In Call             (S_T − K)⁺ si S a touché H
``UOC``   Up-and-Out Call              (S_T − K)⁺ si S n'a jamais touché H (H > S₀)
``UIC``   Up-and-In Call               (S_T − K)⁺ si S a touché H
``DOP``   Down-and-Out Put             (K − S_T)⁺ si S n'a jamais touché H
``DIP``   Down-and-In Put              (K − S_T)⁺ si S a touché H
``UOP``   Up-and-Out Put               (K − S_T)⁺ si S n'a jamais touché H
``UIP``   Up-and-In Put                (K − S_T)⁺ si S a touché H
========  ===========================  =========================================

Relation fondamentale (vraie chemin par chemin) : **In + Out = vanille**, car
un chemin touche la barrière ou ne la touche pas.

Les formules fermées supposent une surveillance **continue**. Le Monte-Carlo
propose la surveillance continue (correction de pont brownien, sans biais) et la
surveillance **discrète** (franchissement observé aux seules dates de la grille).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

import numpy as np
from scipy.special import ndtr

from pricer.bsm import prix_bsm
from pricer.monte_carlo import ResultatMC, ResultatsMC, estimer, lots_normales
from pricer.rng import Methode, creer_generateur
from pricer.validation import (
    valider_barriere,
    valider_entier,
    valider_marche,
    valider_produit,
)

#: Les huit codes, dans l'ordre des lignes de l'onglet Excel.
TYPES_BARRIERE: tuple[str, ...] = ("DOC", "DIC", "UOC", "UIC", "DOP", "DIP", "UOP", "UIP")

NOMS_BARRIERE: dict[str, str] = {
    "DOC": "Down-and-Out Call",
    "DIC": "Down-and-In Call",
    "UOC": "Up-and-Out Call",
    "UIC": "Up-and-In Call",
    "DOP": "Down-and-Out Put",
    "DIP": "Down-and-In Put",
    "UOP": "Up-and-Out Put",
    "UIP": "Up-and-In Put",
}

Surveillance = Literal["continue", "discrete"]

#: β = −ζ(1/2)/√(2π) ≈ 0,5826 : constante de Broadie-Glasserman-Kou (1997).
BETA_BGK = 0.5825971579390106


@dataclass(frozen=True)
class TypeBarriere:
    """Caractéristiques d'une barrière décodées depuis son code."""

    code: str
    basse: bool  # Down (True) ou Up (False)
    sortante: bool  # Out (True) ou In (False)
    call: bool  # Call (True) ou Put (False)


def analyser_type(type_barriere: str) -> TypeBarriere:
    """Décode ``"DOC"``, ``"down-and-out call"``, ``"Down and Out Call"``…"""
    if not isinstance(type_barriere, str):
        raise ValueError(f"Type de barrière invalide : {type_barriere!r}.")
    lettres = "".join(c for c in type_barriere.upper() if c.isalpha())
    alias = {
        nom.upper().replace("-", "").replace(" ", ""): code for code, nom in NOMS_BARRIERE.items()
    }
    code = alias.get(lettres, lettres)
    if code not in TYPES_BARRIERE:
        raise ValueError(
            f"Type de barrière inconnu : {type_barriere!r}. "
            f"Choix possibles : {', '.join(TYPES_BARRIERE)}."
        )
    return TypeBarriere(code, code[0] == "D", code[1] == "O", code[2] == "C")


# ---------------------------------------------------------------------------
# Formules fermées
# ---------------------------------------------------------------------------


def prix_barriere(
    S: float,
    K: float,
    H: float,
    r: float,
    q: float,
    vol: float,
    T: float,
    type_barriere: str = "DOC",
) -> float:
    """Prix exact d'une barrière à surveillance continue, sans rebate.

    Notation de Haug (2007), avec ``σ√T`` noté ``v`` :

    .. math::

        μ = \\frac{r - q - σ^2/2}{σ^2}, \\qquad
        x_1 = \\frac{\\ln(S/K)}{v} + (1+μ)v, \\qquad
        x_2 = \\frac{\\ln(S/H)}{v} + (1+μ)v

        y_1 = \\frac{\\ln(H^2/(SK))}{v} + (1+μ)v, \\qquad
        y_2 = \\frac{\\ln(H/S)}{v} + (1+μ)v

    Quatre blocs, avec ``φ = +1`` (call) ou ``−1`` (put) et ``η = +1``
    (barrière basse) ou ``−1`` (barrière haute) :

    .. math::

        A = φ S e^{-qT} N(φ x_1) - φ K e^{-rT} N(φ x_1 - φ v)

        B = φ S e^{-qT} N(φ x_2) - φ K e^{-rT} N(φ x_2 - φ v)

        C = φ S e^{-qT} (H/S)^{2(μ+1)} N(η y_1) - φ K e^{-rT} (H/S)^{2μ} N(η y_1 - η v)

        D = φ S e^{-qT} (H/S)^{2(μ+1)} N(η y_2) - φ K e^{-rT} (H/S)^{2μ} N(η y_2 - η v)

    ``A`` est la vanille BSM. Les termes en ``(H/S)^{…}`` viennent du principe
    de réflexion : ils comptent les chemins qui touchent la barrière.

    ============  =================  =================
    Type          K ≥ H              K < H
    ============  =================  =================
    DOC           A − C              B − D
    DIC           C                  A − B + D
    UOC           0                  A − B + C − D
    UIC           A                  B − C + D
    DOP           A − B + C − D      0
    DIP           B − C + D          A
    UOP           B − D              A − C
    UIP           A − B + D          C
    ============  =================  =================

    Spot déjà au-delà de la barrière (``S ≤ H`` pour Down, ``S ≥ H`` pour Up) :
    la barrière est touchée dès l'origine, donc Out = 0 et In = vanille.
    """
    valider_marche(S, K, r, q, vol, T)
    H = valider_barriere(H)
    t = analyser_type(type_barriere)
    option = "call" if t.call else "put"

    deja_touchee = S <= H if t.basse else S >= H
    if deja_touchee:
        return 0.0 if t.sortante else prix_bsm(S, K, r, q, vol, T, option)

    phi = 1.0 if t.call else -1.0
    eta = 1.0 if t.basse else -1.0
    v = vol * math.sqrt(T)
    mu = (r - q - 0.5 * vol * vol) / (vol * vol)
    x1 = math.log(S / K) / v + (1.0 + mu) * v
    x2 = math.log(S / H) / v + (1.0 + mu) * v
    y1 = math.log(H * H / (S * K)) / v + (1.0 + mu) * v
    y2 = math.log(H / S) / v + (1.0 + mu) * v
    fs = S * math.exp(-q * T)
    fk = K * math.exp(-r * T)
    hs_1 = (H / S) ** (2.0 * (mu + 1.0))
    hs_0 = (H / S) ** (2.0 * mu)

    a = phi * fs * ndtr(phi * x1) - phi * fk * ndtr(phi * x1 - phi * v)
    b = phi * fs * ndtr(phi * x2) - phi * fk * ndtr(phi * x2 - phi * v)
    c = phi * fs * hs_1 * ndtr(eta * y1) - phi * fk * hs_0 * ndtr(eta * y1 - eta * v)
    d = phi * fs * hs_1 * ndtr(eta * y2) - phi * fk * hs_0 * ndtr(eta * y2 - eta * v)

    strike_haut = K >= H
    combinaisons = {
        "DOC": (a - c) if strike_haut else (b - d),
        "DIC": c if strike_haut else (a - b + d),
        "UOC": 0.0 if strike_haut else (a - b + c - d),
        "UIC": a if strike_haut else (b - c + d),
        "DOP": (a - b + c - d) if strike_haut else 0.0,
        "DIP": (b - c + d) if strike_haut else a,
        "UOP": (b - d) if strike_haut else (a - c),
        "UIP": (a - b + d) if strike_haut else c,
    }
    return float(combinaisons[t.code])


def prix_barrieres(
    S: float, K: float, H: float, r: float, q: float, vol: float, T: float
) -> dict[str, float]:
    """Les huit prix fermés d'un coup, plus les vanilles ``"call"`` et ``"put"``."""
    prix = {code: prix_barriere(S, K, H, r, q, vol, T, code) for code in TYPES_BARRIERE}
    prix["call"] = prix_bsm(S, K, r, q, vol, T, "call")
    prix["put"] = prix_bsm(S, K, r, q, vol, T, "put")
    return prix


def parites_barriere(prix: dict[str, float]) -> dict[str, float]:
    """Écarts à la parité ``Out + In − vanille`` (nuls en théorie), pour les 4 familles."""
    return {
        "Down Call": prix["DOC"] + prix["DIC"] - prix["call"],
        "Up Call": prix["UOC"] + prix["UIC"] - prix["call"],
        "Down Put": prix["DOP"] + prix["DIP"] - prix["put"],
        "Up Put": prix["UOP"] + prix["UIP"] - prix["put"],
    }


def barriere_ajustee_bgk(H: float, S: float, vol: float, T: float, n_pas: int) -> float:
    """Correction de continuité de Broadie-Glasserman-Kou (1997).

    Une barrière surveillée à ``m`` dates équivaut approximativement à une
    barrière continue **décalée vers l'extérieur** :

    .. math:: H_{adj} = H\\,e^{\\pm β σ \\sqrt{T/m}}, \\qquad β ≈ 0{,}5826

    avec ``−`` pour une barrière basse (``H < S``) et ``+`` pour une barrière
    haute. Intuition : entre deux dates, le chemin peut franchir la barrière
    sans que ce soit observé, donc la barrière « effective » est plus loin.
    """
    decalage = BETA_BGK * vol * math.sqrt(T / n_pas)
    return H * math.exp(-decalage) if H < S else H * math.exp(decalage)


# ---------------------------------------------------------------------------
# Monte-Carlo (macro CalculerBarriere)
# ---------------------------------------------------------------------------


def _normaliser_surveillance(surveillance: str | int) -> Surveillance:
    """Accepte ``"continue"``/``"discrete"`` ou le code Excel 0/1 (cellule C11)."""
    if surveillance in (0, "0", "continue", "continu"):
        return "continue"
    if surveillance in (1, "1", "discrete", "discrète", "discret"):
        return "discrete"
    raise ValueError("La surveillance doit valoir 0 (continue) ou 1 (discrète).")


def mc_barriere(
    S: float,
    K: float,
    H: float,
    r: float,
    q: float,
    vol: float,
    T: float,
    n_pas: int = 252,
    surveillance: Surveillance | int = "continue",
    n_sim: int = 50_000,
    graine: int | None = None,
    generateur: Methode = "pcg64",
) -> ResultatsMC:
    """Les huit barrières par Monte-Carlo, avec paires antithétiques.

    On simule ``n_sim`` **paires** de log-chemins (``Z`` et ``−Z``) sur
    ``n_pas`` pas de ``Δt = T/n_pas``. Pour chaque chemin, on calcule une
    probabilité de survie ``s`` (probabilité de ne pas avoir touché H) :

    - **discrète** : ``s = 1`` si aucun point de la grille n'a franchi H, sinon 0 ;
    - **continue** (pont brownien) : en plus, entre deux points ``x_k`` et
      ``x_{k+1}`` situés du bon côté de ``h = ln H``, le brownien conditionné
      (pont) touche la barrière avec une probabilité connue exactement :

      .. math::

          P(\\text{franchissement} \\mid x_k, x_{k+1})
          = \\exp\\Big(-\\frac{2\\,(x_k - h)(x_{k+1} - h)}{σ^2 Δt}\\Big)

      d'où ``s = ∏_k (1 − P_k)``. Cette correction est exacte pour un GBM à
      paramètres constants : l'estimateur n'a pas de biais de surveillance, quel
      que soit ``n_pas`` (seule sa variance en dépend).

    Le prix Out est ``E[e^{−rT}·payoff·s]``, et le prix In est calculé chemin
    par chemin comme ``vanille − Out``, ce qui garantit exactement la parité.
    Chaque échantillon est la moyenne d'une paire antithétique, d'où ``n = n_sim``.

    Si ``S < H``, la barrière est haute : les options Down ont déjà touché
    (Down-Out = 0, Down-In = vanille). Symétriquement si ``S > H``. Si ``S = H``,
    toutes les Out valent 0.

    Args:
        n_pas: nombre de pas de surveillance (1 à 10 000).
        surveillance: ``"continue"`` (0) ou ``"discrete"`` (1).
        n_sim: nombre de paires antithétiques (1 000 à 1 000 000), avec
            ``n_sim × n_pas ≤ 50 000 000``.

    Returns:
        Un :class:`ResultatsMC` indexé par code (``"DOC"``…) et par ``"call"``
        / ``"put"`` (vanilles), avec la méthode ``"continue"`` ou ``"discrete"``.
        Les références sont les formules fermées (surveillance continue).
    """
    valider_marche(S, K, r, q, vol, T)
    H = valider_barriere(H)
    m = valider_entier(n_pas, 1, 10_000, "Le nombre de pas de surveillance")
    mode = _normaliser_surveillance(surveillance)
    n = valider_entier(n_sim, 1_000, 1_000_000, "Le nombre de simulations")
    valider_produit(
        n,
        m,
        50_000_000,
        "Simulations x pas de surveillance doit rester <= 50 000 000 (temps de calcul).",
    )
    gen = creer_generateur(graine, generateur)

    basse, haute = S > H, S < H
    dt = T / m
    mu = (r - q - 0.5 * vol * vol) * dt
    sv = vol * math.sqrt(dt)
    actu = math.exp(-r * T)
    ln_h = math.log(H)
    ln_s0 = math.log(S)
    k2 = 2.0 / (vol * vol * dt)

    def survie(y: np.ndarray) -> np.ndarray:
        """Probabilité de survie de chaque chemin (log-prix aux dates 1..m)."""
        if not (basse or haute):
            return np.zeros(y.shape[0])  # S = H : barrière touchée dès l'origine
        x = np.concatenate([np.full((y.shape[0], 1), ln_s0), y[:, :-1]], axis=1)
        # Distances signées à la barrière, positives du côté « vivant ».
        dx, dy = (x - ln_h, y - ln_h) if basse else (ln_h - x, ln_h - y)
        franchi = np.any(dy <= 0.0, axis=1)
        if mode == "discrete":
            return np.where(franchi, 0.0, 1.0)
        # max(·, 0) : le produit est négatif au pas du franchissement ; le chemin
        # est alors mort de toute façon (franchi = True).
        proba_pont = np.exp(-k2 * np.maximum(dx * dy, 0.0))
        return np.where(franchi, 0.0, np.prod(1.0 - proba_pont, axis=1))

    van_c, van_p = np.empty(n), np.empty(n)
    out_c, out_p = np.empty(n), np.empty(n)
    for debut, fin, z in lots_normales(gen, n, m):
        y1 = ln_s0 + np.cumsum(mu + sv * z, axis=1)
        y2 = ln_s0 + np.cumsum(mu - sv * z, axis=1)
        s1, s2 = survie(y1), survie(y2)
        st1, st2 = np.exp(y1[:, -1]), np.exp(y2[:, -1])
        c1, p1 = np.maximum(st1 - K, 0.0) * actu, np.maximum(K - st1, 0.0) * actu
        c2, p2 = np.maximum(st2 - K, 0.0) * actu, np.maximum(K - st2, 0.0) * actu
        van_c[debut:fin], van_p[debut:fin] = 0.5 * (c1 + c2), 0.5 * (p1 + p2)
        out_c[debut:fin] = 0.5 * (c1 * s1 + c2 * s2)
        out_p[debut:fin] = 0.5 * (p1 * s1 + p2 * s2)

    vanille_c, vanille_p = estimer(van_c), estimer(van_p)
    sortie_c, sortie_p = estimer(out_c), estimer(out_p)
    entree_c, entree_p = estimer(van_c - out_c), estimer(van_p - out_p)
    zero = ResultatMC(0.0, 0.0, n)

    if basse:
        lignes = {
            "DOC": sortie_c,
            "DIC": entree_c,
            "UOC": zero,
            "UIC": vanille_c,
            "DOP": sortie_p,
            "DIP": entree_p,
            "UOP": zero,
            "UIP": vanille_p,
        }
    elif haute:
        lignes = {
            "DOC": zero,
            "DIC": vanille_c,
            "UOC": sortie_c,
            "UIC": entree_c,
            "DOP": zero,
            "DIP": vanille_p,
            "UOP": sortie_p,
            "UIP": entree_p,
        }
    else:
        lignes = {
            "DOC": zero,
            "DIC": vanille_c,
            "UOC": zero,
            "UIC": vanille_c,
            "DOP": zero,
            "DIP": vanille_p,
            "UOP": zero,
            "UIP": vanille_p,
        }
    lignes["call"], lignes["put"] = vanille_c, vanille_p

    estimations = {code: {mode: res} for code, res in lignes.items()}
    references = prix_barrieres(S, K, H, r, q, vol, T)
    diagnostics = {
        f"parite_mc_{nom}": val
        for nom, val in parites_barriere({c: r_.prix for c, r_ in lignes.items()}).items()
    }
    if mode == "discrete" and (basse or haute):
        h_bgk = barriere_ajustee_bgk(H, S, vol, T, m)
        for code in TYPES_BARRIERE:
            diagnostics[f"bgk_{code}"] = prix_barriere(S, K, h_bgk, r, q, vol, T, code)
    return ResultatsMC(estimations, references, diagnostics, gen.graine_utilisee)

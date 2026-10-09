"""Longstaff-Schwartz (2001) : options américaines par Monte-Carlo et régression.

Reprise des procédures VBA ``SimulerCheminsAV`` et ``PrixLSM``.

Principe : à chaque date d'exercice, le détenteur compare la valeur d'exercice
immédiat à la **valeur de continuation**, c'est-à-dire l'espérance
conditionnelle des flux futurs actualisés. Cette espérance est inconnue : on
l'approche par une régression des flux futurs réalisés sur des fonctions du
spot (ici un polynôme en ``x = S/K − 1``), en n'utilisant que les chemins dans
la monnaie (les seuls pour lesquels la décision se pose).

L'exercice n'est possible qu'aux ``n_dates`` dates ``t_j = j·T/n_dates`` : c'est
une option bermudéenne, dont le prix théorique est légèrement **inférieur** à celui
de l'américaine continue. Deux biais de signes opposés s'ajoutent au bruit
statistique : la règle d'exercice estimée est sous-optimale (biais bas), mais la
régression est estimée sur les mêmes chemins que ceux qui servent au prix, ce qui
lui donne un peu de « prescience » (biais haut). Le résultat peut donc tomber de
part et d'autre de la valeur de l'arbre.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace

import numpy as np

from pricer.monte_carlo import ResultatMC, lots_normales
from pricer.rng import Methode, creer_generateur
from pricer.validation import valider_entier, valider_marche, valider_option, valider_produit

#: Nombre minimal de chemins dans la monnaie pour lancer une régression (VBA).
MIN_CHEMINS_ITM = 8


@dataclass(frozen=True)
class ResultatLSM(ResultatMC):
    """Prix Longstaff-Schwartz avec erreur standard.

    ``n`` est le nombre de **paires** antithétiques (échantillons indépendants).

    Attributes:
        exercice_immediat: ``True`` si l'exercice à t = 0 vaut plus que la
            continuation (le prix est alors la valeur intrinsèque et SE = 0).
        frontiere: pour chaque date d'exercice ``t_j``, le spot le plus éloigné
            du strike pour lequel au moins un chemin a été exercé (le plus haut
            pour un put, le plus bas pour un call) ; ``NaN`` si aucun exercice.
            C'est une estimation empirique de la frontière d'exercice.
        temps: dates d'exercice ``t_j``.
        graine: graine utilisée pour simuler les chemins.
    """

    exercice_immediat: bool = False
    frontiere: np.ndarray | None = None
    temps: np.ndarray | None = None
    graine: int = 0


def simuler_chemins_antithetiques(
    S: float,
    r: float,
    q: float,
    vol: float,
    T: float,
    n_sim: int,
    n_dates: int,
    graine: int | None = None,
    generateur: Methode = "pcg64",
) -> tuple[np.ndarray, int]:
    """Chemins de GBM aux dates ``t_j = j·T/n_dates`` (j = 1..n_dates), par paires.

    Les lignes paires (0, 2, …) utilisent ``Z`` et les lignes impaires ``−Z``
    (lignes impaires/paires du VBA, qui numérote à partir de 1). Pour la paire
    ``i``, la normale ``Z_{i,j}`` est tirée dans l'ordre chemin puis date, comme
    dans ``SimulerCheminsAV``.

    Returns:
        Les chemins ``(n_sim, n_dates)`` et la graine utilisée.
    """
    gen = creer_generateur(graine, generateur)
    dt = T / n_dates
    mu = (r - q - 0.5 * vol * vol) * dt
    sv = vol * math.sqrt(dt)
    chemins = np.empty((n_sim, n_dates))
    ln_s0 = math.log(S)
    for debut, fin, z in lots_normales(gen, n_sim // 2, n_dates):
        chemins[2 * debut : 2 * fin : 2] = np.exp(ln_s0 + np.cumsum(mu + sv * z, axis=1))
        chemins[2 * debut + 1 : 2 * fin : 2] = np.exp(ln_s0 + np.cumsum(mu - sv * z, axis=1))
    return chemins, gen.graine_utilisee


def lsm_sur_chemins(
    chemins: np.ndarray,
    S: float,
    K: float,
    r: float,
    T: float,
    option: str = "put",
    degre: int = 3,
) -> ResultatLSM:
    """Algorithme de Longstaff-Schwartz appliqué à des chemins déjà simulés.

    Récurrence arrière, de la date ``n − 1`` à la date 1 :

    1. ``CF_i`` = flux du chemin ``i`` (initialement le payoff à maturité) et
       ``τ_i`` sa date ;
    2. sur les chemins dans la monnaie, on régresse
       ``Y_i = CF_i·e^{−r(τ_i − t_j)}`` sur la base ``1, x, x², …, x^degré``
       avec ``x = S_{i,j}/K − 1`` (moindres carrés) ;
    3. on exerce si ``payoff(S_{i,j}) > Ĉ(S_{i,j})`` : ``CF_i ← payoff`` et ``τ_i ← t_j``.

    Prix : ``V₀ = max(payoff(S₀), moyenne des CF_i·e^{−rτ_i})``.

    La normalisation ``x = S/K − 1`` garde la matrice de régression bien
    conditionnée (les puissances de ``S`` brut atteindraient 10⁶ pour S = 100).
    La régression est ignorée s'il y a moins de 8 chemins dans la monnaie ou si
    la matrice est de rang insuffisant (``Resoudre4`` renvoie Faux dans le VBA).

    L'erreur standard est calculée sur les **moyennes de paires** antithétiques,
    qui sont indépendantes entre elles (deux chemins d'une même paire ne le sont pas).
    """
    est_call = valider_option(option)
    degre = valider_entier(degre, 1, 6, "Le degré de la régression")
    n_sim, n_dates = chemins.shape
    dt = T / n_dates
    actu = np.exp(-r * dt * np.arange(n_dates + 1))  # e^{−r·t_j}, j = 0..n

    def payoff(s: np.ndarray) -> np.ndarray:
        return np.maximum(s - K, 0.0) if est_call else np.maximum(K - s, 0.0)

    cf = payoff(chemins[:, -1])
    tau = np.full(n_sim, n_dates)
    frontiere = np.full(n_dates, np.nan)
    if np.any(cf > 0):
        frontiere[-1] = K  # à maturité, on exerce dès que l'option est dans la monnaie

    for j in range(n_dates - 1, 0, -1):
        s_j = chemins[:, j - 1]
        exercice = payoff(s_j)
        itm = exercice > 0.0
        if np.count_nonzero(itm) < MIN_CHEMINS_ITM:
            continue
        x = s_j[itm] / K - 1.0
        base = np.vander(x, degre + 1, increasing=True)  # colonnes 1, x, x², …
        y = cf[itm] * actu[tau[itm] - j]
        coef, _, rang, _ = np.linalg.lstsq(base, y, rcond=None)
        if rang < degre + 1:
            continue
        continuation = base @ coef
        exerce = exercice[itm] > continuation
        idx = np.flatnonzero(itm)[exerce]
        cf[idx] = exercice[idx]
        tau[idx] = j
        if idx.size:
            frontiere[j - 1] = s_j[idx].min() if est_call else s_j[idx].max()

    valeurs = cf * actu[tau]
    paires = 0.5 * (valeurs[0::2] + valeurs[1::2])
    n_paires = paires.size
    moyenne = float(paires.mean())
    se = float(np.std(paires, ddof=1)) / math.sqrt(n_paires)
    temps = dt * np.arange(1, n_dates + 1)
    exercice_0 = max(S - K, 0.0) if est_call else max(K - S, 0.0)
    if exercice_0 > moyenne:
        return ResultatLSM(exercice_0, 0.0, n_paires, True, frontiere, temps)
    return ResultatLSM(moyenne, se, n_paires, False, frontiere, temps)


def prix_lsm(
    S: float,
    K: float,
    r: float,
    q: float,
    vol: float,
    T: float,
    option: str = "put",
    n_sim: int = 20_000,
    n_dates: int = 50,
    graine: int | None = None,
    generateur: Methode = "pcg64",
    degre: int = 3,
) -> ResultatLSM:
    """Prix d'une option américaine (bermudéenne) par Longstaff-Schwartz.

    Args:
        S, K, r, q, vol, T: paramètres de marché (σ > 0).
        option: ``"call"`` ou ``"put"``.
        n_sim: nombre de chemins (1 000 à 200 000), arrondi au nombre pair
            supérieur pour former des paires antithétiques.
        n_dates: nombre de dates d'exercice équiréparties (10 à 500).
        graine: graine du générateur (``None`` ou 0 = aléatoire). Avec la même
            graine, le call et le put sont évalués sur les mêmes chemins, comme
            dans le VBA.
        generateur: ``"pcg64"`` ou ``"mrg32k3a"``.
        degre: degré du polynôme de régression (3 dans l'Excel : base cubique).
    """
    valider_marche(S, K, r, q, vol, T)
    valider_option(option)
    n_sim = valider_entier(n_sim, 1_000, 200_000, "Le nombre de simulations LSM")
    n_dates = valider_entier(n_dates, 10, 500, "Le nombre de dates d'exercice LSM")
    n_sim += n_sim % 2
    valider_produit(
        n_sim,
        n_dates,
        5_000_000,
        "Simulations LSM x dates d'exercice doit rester <= 5 000 000 (limite mémoire).",
    )
    chemins, graine_utilisee = simuler_chemins_antithetiques(
        S, r, q, vol, T, n_sim, n_dates, graine, generateur
    )
    resultat = lsm_sur_chemins(chemins, S, K, r, T, option, degre)
    return replace(resultat, graine=graine_utilisee)

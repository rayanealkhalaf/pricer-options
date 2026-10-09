"""Monte-Carlo : outils statistiques communs et options européennes.

Ce module contient :

- les estimateurs génériques (moyenne + erreur standard, variable de contrôle),
  partagés par les moteurs asiatique et barrière ;
- la génération des normales **par lots** (mémoire bornée, ordre des tirages
  conservé) ;
- le moteur européen ``mc_europeenne`` (macro VBA ``CalculerMC``) : Monte-Carlo
  standard, antithétique et variable de contrôle ``S_T`` actualisé ;
- la simulation de trajectoires illustratives (``GenererTrajectoire``).

Tous les calculs sont vectorisés avec NumPy : aucune boucle Python ne parcourt
les simulations (les seules boucles portent sur les lots de mémoire).
"""

from __future__ import annotations

import math
from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field

import numpy as np

from pricer.bsm import prix_bsm
from pricer.rng import GenerateurNormal, Methode, creer_generateur
from pricer.validation import valider_entier, valider_marche, valider_nombre, valider_option

#: Quantile à 97,5 % de la loi normale arrondi, comme la constante ``Z95`` du VBA.
Z95 = 1.96
#: Nombre de jours de bourse par an pour les trajectoires illustratives.
JOURS_PAR_AN = 252.0
#: Taille maximale d'un lot de normales (en nombre de tirages, ≈ 16 Mo).
TAILLE_LOT = 2_000_000


# ---------------------------------------------------------------------------
# Résultats et estimateurs
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ResultatMC:
    """Une estimation Monte-Carlo : prix, erreur standard et taille d'échantillon.

    L'erreur standard vaut ``SE = s / √n``, où ``s`` est l'écart-type empirique
    (divisé par ``n − 1``). L'intervalle de confiance à 95 % vaut
    ``prix ± 1,96·SE``.
    """

    prix: float
    se: float
    n: int

    @property
    def ic_bas(self) -> float:
        """Borne basse de l'IC à 95 % : ``prix − 1,96·SE``."""
        return self.prix - Z95 * self.se

    @property
    def ic_haut(self) -> float:
        """Borne haute de l'IC à 95 % : ``prix + 1,96·SE``."""
        return self.prix + Z95 * self.se

    def z_score(self, reference: float) -> float:
        """Écart à une valeur de référence en nombre d'erreurs standards.

        .. math:: z = \\frac{\\hat{V}_{MC} - V_{\\text{fermée}}}{SE}

        Sous l'hypothèse d'un moteur sans biais, ``z`` suit approximativement une
        N(0, 1) : ``|z| < 2`` dans 95 % des cas et ``|z| < 3`` dans 99,7 % des cas.
        Si ``SE = 0`` (estimateur dégénéré), on renvoie 0, comme le ``IFERROR`` de
        la feuille Excel.
        """
        return (self.prix - reference) / self.se if self.se > 0 else 0.0


def estimer(echantillon: np.ndarray) -> ResultatMC:
    """Estimateur Monte-Carlo standard d'une espérance.

    .. math::

        \\hat{V} = \\frac{1}{n}\\sum_i Y_i, \\qquad
        SE = \\sqrt{\\frac{1}{n(n-1)}\\sum_i (Y_i - \\hat{V})^2}

    NumPy calcule la variance en deux passes (moyenne, puis moments centrés),
    comme le VBA, ce qui est plus stable que ``E[Y²] − E[Y]²``.
    """
    y = np.asarray(echantillon, dtype=float)
    n = y.size
    variance = float(np.var(y, ddof=1)) if n > 1 else 0.0
    return ResultatMC(float(np.mean(y)), math.sqrt(max(variance, 0.0) / n), n)


@dataclass(frozen=True)
class ResultatControle:
    """Estimation par variable de contrôle et diagnostics associés."""

    estimation: ResultatMC
    beta: float
    correlation: float


def estimer_avec_controle(y: np.ndarray, x: np.ndarray, esperance_x: float) -> ResultatControle:
    """Estimateur par variable de contrôle avec β* empirique.

    On dispose d'une variable ``X`` corrélée au payoff ``Y`` et dont l'espérance
    ``E[X]`` est connue exactement. L'estimateur

    .. math::

        \\hat{V}_{CV} = \\bar{Y} - β^*(\\bar{X} - E[X]), \\qquad
        β^* = \\frac{\\widehat{\\mathrm{Cov}}(Y, X)}{\\widehat{\\mathrm{Var}}(X)}

    reste sans biais (à l'estimation de β* près) et sa variance vaut

    .. math:: \\mathrm{Var}(Y) - β^*\\,\\mathrm{Cov}(Y, X) = \\mathrm{Var}(Y)\\,(1 - ρ^2_{XY})

    La réduction de variance est d'autant plus forte que ``|ρ|`` est proche de 1.
    Garde-fou repris du VBA : si ``Var(X) ≤ (10⁻¹²·X̄)²`` (par exemple σ = 0),
    alors β* = 0 et on retombe sur l'estimateur standard.
    """
    y = np.asarray(y, dtype=float)
    x = np.asarray(x, dtype=float)
    n = y.size
    my, mx = float(y.mean()), float(x.mean())
    dy, dx = y - my, x - mx
    var_y = float(dy @ dy) / (n - 1)
    var_x = float(dx @ dx) / (n - 1)
    cov = float(dy @ dx) / (n - 1)
    if var_x > 0.0 and var_x > (1e-12 * mx) ** 2:
        beta = cov / var_x
        correlation = cov / math.sqrt(var_y * var_x) if var_y > 0 else 0.0
    else:
        beta = correlation = 0.0
    prix = my - beta * (mx - esperance_x)
    variance = max(var_y - beta * cov, 0.0)
    return ResultatControle(ResultatMC(prix, math.sqrt(variance / n), n), beta, correlation)


@dataclass
class ResultatsMC:
    """Ensemble de résultats Monte-Carlo pour un produit.

    Attributes:
        estimations: ``{option: {méthode: ResultatMC}}``, par exemple
            ``estimations["call"]["controle"]``.
        references: ``{option: prix}`` donné par la formule fermée (s'il en existe une).
        diagnostics: indicateurs annexes (β*, corrélations, gains de variance...).
        graine: graine effectivement utilisée (pour reproduire le calcul).
    """

    estimations: dict[str, dict[str, ResultatMC]]
    references: dict[str, float] = field(default_factory=dict)
    diagnostics: dict[str, float] = field(default_factory=dict)
    graine: int = 0

    def z_scores(self) -> dict[str, dict[str, float]]:
        """z-scores de chaque estimation face à la formule fermée de son option."""
        return {
            option: {m: res.z_score(self.references[option]) for m, res in methodes.items()}
            for option, methodes in self.estimations.items()
            if option in self.references
        }

    def lignes(self) -> list[dict[str, float | str]]:
        """Tableau à plat (une ligne par option et méthode), prêt pour l'affichage."""
        lignes: list[dict[str, float | str]] = []
        for option, methodes in self.estimations.items():
            ref = self.references.get(option)
            for methode, res in methodes.items():
                lignes.append(
                    {
                        "option": option,
                        "méthode": methode,
                        "prix": res.prix,
                        "SE": res.se,
                        "IC95 bas": res.ic_bas,
                        "IC95 haut": res.ic_haut,
                        "formule fermée": ref if ref is not None else float("nan"),
                        "z": res.z_score(ref) if ref is not None else float("nan"),
                    }
                )
        return lignes


# ---------------------------------------------------------------------------
# Génération des normales par lots
# ---------------------------------------------------------------------------


def lots_normales(
    generateur: GenerateurNormal, n_lignes: int, n_colonnes: int, taille_lot: int = TAILLE_LOT
) -> Iterator[tuple[int, int, np.ndarray]]:
    """Produit la matrice ``(n_lignes, n_colonnes)`` de N(0, 1) par blocs de lignes.

    Chaque bloc ``Z[debut:fin]`` est rendu avec ses indices. Les tirages sont
    consommés ligne par ligne (un chemin après l'autre), dans le même ordre que
    les doubles boucles du VBA : le résultat ne dépend donc pas de la taille des
    lots. Cela borne la mémoire, même pour 50 millions de tirages.
    """
    lignes_par_lot = max(1, taille_lot // max(1, n_colonnes))
    for debut in range(0, n_lignes, lignes_par_lot):
        fin = min(n_lignes, debut + lignes_par_lot)
        yield debut, fin, generateur.normales((fin - debut, n_colonnes))


# ---------------------------------------------------------------------------
# Options européennes (macro CalculerMC)
# ---------------------------------------------------------------------------


def mc_europeenne(
    S: float,
    K: float,
    r: float,
    q: float,
    vol: float,
    T: float,
    n_sim: int = 100_000,
    graine: int | None = None,
    generateur: Methode = "pcg64",
) -> ResultatsMC:
    """Call et put européens par Monte-Carlo : trois estimateurs.

    Diffusion log-normale **exacte** en un seul pas (aucun biais de
    discrétisation) :

    .. math:: S_T = S \\exp\\big((r - q - σ^2/2)T + σ\\sqrt{T}\\,Z\\big), \\quad Z \\sim N(0, 1)

    1. **Standard** : ``Y = e^{-rT}·max(S_T − K, 0)``, moyenne et SE.
    2. **Antithétique** : avec les **mêmes** N tirages, ``½[Y(Z) + Y(−Z)]``.
       Comme le payoff est monotone en Z, les deux termes sont négativement
       corrélés et la variance baisse. Coût : deux évaluations de payoff par
       tirage (d'où le facteur ½ de l'« efficacité AV »).
    3. **Variable de contrôle** : ``X = e^{-rT}·S_T``, d'espérance exacte
       ``E[X] = S e^{-qT}`` (martingale actualisée) ; β* est estimé sur
       l'échantillon (voir :func:`estimer_avec_controle`).

    Args:
        S, K, r, q, vol, T: paramètres de marché (σ ≥ 0 accepté, comme dans l'Excel).
        n_sim: nombre de tirages N (1 000 à 10 000 000).
        graine: graine du générateur (``None`` ou 0 = aléatoire).
        generateur: ``"pcg64"`` (défaut) ou ``"mrg32k3a"`` (identique au VBA).

    Returns:
        Un :class:`ResultatsMC` avec les méthodes ``standard``, ``antithetique``
        et ``controle`` pour le call et le put, les prix BSM de référence et les
        diagnostics (β*, corrélations, gains de variance).
    """
    valider_marche(S, K, r, q, vol, T, vol_nulle_permise=True)
    n = valider_entier(n_sim, 1_000, 10_000_000, "Le nombre de simulations N")
    gen = creer_generateur(graine, generateur)

    drift = (r - q - 0.5 * vol * vol) * T
    vol_t = vol * math.sqrt(T)
    actu = math.exp(-r * T)
    esperance_x = S * math.exp(-q * T)  # E[e^{-rT} S_T] = S e^{-qT}

    call = np.empty(n)
    put = np.empty(n)
    call_av = np.empty(n)
    put_av = np.empty(n)
    x = np.empty(n)
    for debut, fin, z in lots_normales(gen, n, 1):
        z = z[:, 0]
        s_haut = S * np.exp(drift + vol_t * z)
        s_bas = S * np.exp(drift - vol_t * z)
        c_h = np.maximum(s_haut - K, 0.0) * actu
        p_h = np.maximum(K - s_haut, 0.0) * actu
        c_b = np.maximum(s_bas - K, 0.0) * actu
        p_b = np.maximum(K - s_bas, 0.0) * actu
        call[debut:fin] = c_h
        put[debut:fin] = p_h
        call_av[debut:fin] = 0.5 * (c_h + c_b)
        put_av[debut:fin] = 0.5 * (p_h + p_b)
        x[debut:fin] = s_haut * actu

    cv_call = estimer_avec_controle(call, x, esperance_x)
    cv_put = estimer_avec_controle(put, x, esperance_x)
    estimations = {
        "call": {
            "standard": estimer(call),
            "antithetique": estimer(call_av),
            "controle": cv_call.estimation,
        },
        "put": {
            "standard": estimer(put),
            "antithetique": estimer(put_av),
            "controle": cv_put.estimation,
        },
    }
    diagnostics = {
        "beta_call": cv_call.beta,
        "beta_put": cv_put.beta,
        "corr_call": cv_call.correlation,
        "corr_put": cv_put.correlation,
        **gains_variance(estimations),
    }
    references = {
        "call": prix_bsm(S, K, r, q, vol, T, "call"),
        "put": prix_bsm(S, K, r, q, vol, T, "put"),
    }
    return ResultatsMC(estimations, references, diagnostics, gen.graine_utilisee)


def _ratio_variance(se_ref: float, se: float, cout: float = 1.0) -> float:
    """``(SE_ref / SE)² / coût`` : facteur de réduction de variance à coût égal."""
    return (se_ref / se) ** 2 / cout if se > 0 else float("nan")


def gains_variance(estimations: dict[str, dict[str, ResultatMC]]) -> dict[str, float]:
    """Gains de variance CV et efficacité AV, comme les cellules F12:F15 de l'Excel.

    - gain CV = ``(SE_standard / SE_controle)²`` ;
    - efficacité AV = ``(SE_standard / SE_antithetique)² / 2`` (l'antithétique
      évalue deux payoffs par tirage : on divise par ce double coût).
    """
    gains: dict[str, float] = {}
    for option, m in estimations.items():
        se_std = m["standard"].se
        if "controle" in m:
            gains[f"gain_cv_{option}"] = _ratio_variance(se_std, m["controle"].se)
        if "antithetique" in m:
            gains[f"efficacite_av_{option}"] = _ratio_variance(se_std, m["antithetique"].se, 2.0)
    return gains


def convergence_europeenne(
    S: float,
    K: float,
    r: float,
    q: float,
    vol: float,
    T: float,
    tailles: Sequence[int],
    option: str = "call",
    graine: int | None = 42,
    generateur: Methode = "pcg64",
) -> dict[str, np.ndarray]:
    """Étude de convergence : prix et SE des trois méthodes pour chaque taille N.

    Illustre la vitesse ``SE ∝ 1/√N`` du Monte-Carlo : diviser l'erreur par 10
    demande 100 fois plus de simulations, d'où l'intérêt de la réduction de
    variance.

    Returns:
        Un dictionnaire avec ``n`` et, pour chaque méthode, ``prix_<méthode>``
        et ``se_<méthode>`` (tableaux NumPy alignés sur ``tailles``).
    """
    valider_option(option)
    sortie: dict[str, list[float]] = {"n": []}
    for n in tailles:
        res = mc_europeenne(S, K, r, q, vol, T, int(n), graine, generateur)
        sortie["n"].append(int(n))
        for methode, est in res.estimations[option.lower()].items():
            sortie.setdefault(f"prix_{methode}", []).append(est.prix)
            sortie.setdefault(f"se_{methode}", []).append(est.se)
    return {cle: np.asarray(val) for cle, val in sortie.items()}


# ---------------------------------------------------------------------------
# Trajectoires illustratives (GenererTrajectoire)
# ---------------------------------------------------------------------------


def grille_journaliere(T: float) -> np.ndarray:
    """Grille de temps ``0, 1/252, 2/252, …, T`` (convention du VBA).

    On prend ``⌊252·T⌋`` pas de ``1/252`` an, puis un pas résiduel s'il en
    reste un, pour finir exactement en ``T``.
    """
    T = valider_nombre(T, "La maturité T")
    if T <= 0:
        raise ValueError("La maturité doit être strictement positive (T > 0).")
    dt = 1.0 / JOURS_PAR_AN
    n_pas = int(T * JOURS_PAR_AN + 1e-9)
    temps = np.arange(n_pas + 1) * dt
    if T - n_pas * dt >= 1e-9:
        temps = np.append(temps, T)
    return temps


def simuler_trajectoires(
    S: float,
    r: float,
    q: float,
    vol: float,
    temps: np.ndarray,
    n_chemins: int = 1,
    graine: int | None = None,
    generateur: Methode = "pcg64",
) -> np.ndarray:
    """Trajectoires de mouvement brownien géométrique sur une grille quelconque.

    Schéma log-exact, sans biais de discrétisation quel que soit le pas :

    .. math::

        S_{t_{k+1}} = S_{t_k} \\exp\\big((r - q - σ^2/2)Δt_k + σ\\sqrt{Δt_k}\\,Z_k\\big)

    Args:
        temps: grille croissante qui commence à 0 (par exemple :func:`grille_journaliere`).
        n_chemins: nombre de trajectoires.

    Returns:
        Un tableau ``(n_chemins, len(temps))`` dont la première colonne vaut ``S``.
    """
    temps = np.asarray(temps, dtype=float)
    if temps.ndim != 1 or temps.size < 2 or temps[0] != 0.0 or np.any(np.diff(temps) <= 0):
        raise ValueError("La grille de temps doit commencer à 0 et être strictement croissante.")
    # K n'intervient pas ici : on contrôle S, r, q, σ et T = dernière date de la grille.
    valider_marche(S, S, r, q, vol, float(temps[-1]), vol_nulle_permise=True)
    n_chemins = valider_entier(n_chemins, 1, 100_000, "Le nombre de trajectoires")
    dt = np.diff(temps)
    gen = creer_generateur(graine, generateur)
    z = gen.normales((n_chemins, dt.size))
    increments = (r - q - 0.5 * vol * vol) * dt + vol * np.sqrt(dt) * z
    log_chemins = np.concatenate([np.zeros((n_chemins, 1)), np.cumsum(increments, axis=1)], axis=1)
    return S * np.exp(log_chemins)

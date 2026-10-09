"""Stratégies optionnelles et grecques de position (onglet « Stratégies & Grecques »).

Reprise de l'onglet Excel, entièrement en formules de cellule :

- 16 stratégies prédéfinies (call, put, spread, tunnel, stellage, strangle,
  papillon, condor, à l'achat et à la vente) et une stratégie personnalisée de
  1 à 4 jambes ;
- prime et grecques Black-Scholes-Merton de chaque jambe et de la position ;
- profil à l'échéance : points morts, gain et perte maximum **exacts** ;
- scénario (jours écoulés, nouvelle volatilité, nouveau spot) : P&L réel et
  décomposition par les grecques ;
- tableau comparatif de toutes les stratégies et profils pour les graphiques.

Conventions de l'Excel : maturité ``T = jours / 365`` ; vega et rho pour +1
point ; theta par jour calendaire ; montants en € pour une option sur un
sous-jacent (pas de multiplicateur de contrat).

Une stratégie prédéfinie place ses strikes en ``K0 + multiple × ΔK``.
Par exemple, un condor acheté est composé de calls de strikes
``K0 − 1,5ΔK``, ``K0 − 0,5ΔK``, ``K0 + 0,5ΔK`` et ``K0 + 1,5ΔK``,
pondérés ``+1, −1, −1, +1``.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

import numpy as np
from scipy.special import ndtr

from pricer.validation import valider_marche, valider_nombre, valider_option

_INV_RACINE_2PI = 1.0 / math.sqrt(2.0 * math.pi)
JOURS_PAR_AN = 365.0

Grecque = Literal["delta", "gamma", "vega", "theta"]
GRECQUES: tuple[str, ...] = ("delta", "gamma", "vega", "theta")

# ---------------------------------------------------------------------------
# Catalogue des stratégies (table P7:AG23 de l'onglet)
# ---------------------------------------------------------------------------

#: Une jambe prédéfinie : (φ = +1 call / −1 put, sens +1 achat / −1 vente,
#: quantité, multiple de ΔK).
JambeType = tuple[int, int, float, float]

STRATEGIES: dict[str, tuple[str, tuple[JambeType, ...]]] = {
    "Achat call": (
        "Hausse du sous-jacent ; perte limitée à la prime payée.",
        ((1, 1, 1, 0),),
    ),
    "Vente call": (
        "Stabilité ou baisse ; prime encaissée, perte illimitée à la hausse.",
        ((1, -1, 1, 0),),
    ),
    "Achat put": (
        "Baisse du sous-jacent ou couverture ; perte limitée à la prime.",
        ((-1, 1, 1, 0),),
    ),
    "Vente put": (
        "Stabilité ou hausse ; prime encaissée, perte forte en cas de baisse.",
        ((-1, -1, 1, 0),),
    ),
    "Achat spread (bull call spread)": (
        "Hausse modérée ; prime réduite, gain plafonné.",
        ((1, 1, 1, 0), (1, -1, 1, 1)),
    ),
    "Vente spread (bear call spread)": (
        "Stabilité ou baisse modérée ; crédit encaissé, perte plafonnée.",
        ((1, -1, 1, 0), (1, 1, 1, 1)),
    ),
    "Achat tunnel": (
        "Hausse ; achat du call financé par la vente du put.",
        ((1, 1, 1, 0.5), (-1, -1, 1, -0.5)),
    ),
    "Vente tunnel": (
        "Baisse ou protection ; achat du put financé par la vente du call.",
        ((1, -1, 1, 0.5), (-1, 1, 1, -0.5)),
    ),
    "Achat stellage (straddle)": (
        "Fort mouvement dans un sens ou l'autre, ou hausse de la volatilité.",
        ((1, 1, 1, 0), (-1, 1, 1, 0)),
    ),
    "Vente stellage (straddle)": (
        "Marché calme et baisse de la volatilité ; perte illimitée.",
        ((1, -1, 1, 0), (-1, -1, 1, 0)),
    ),
    "Achat strangle": (
        "Très fort mouvement ; moins cher que le stellage.",
        ((1, 1, 1, 0.5), (-1, 1, 1, -0.5)),
    ),
    "Vente strangle": (
        "Marché dans un couloir ; perte illimitée hors des bornes.",
        ((1, -1, 1, 0.5), (-1, -1, 1, -0.5)),
    ),
    "Achat papillon (butterfly)": (
        "Stabilité autour du strike central ; gain et perte limités.",
        ((1, 1, 1, -1), (1, -1, 2, 0), (1, 1, 1, 1)),
    ),
    "Vente papillon (butterfly)": (
        "Sortie de la zone centrale ; gain et perte limités.",
        ((1, -1, 1, -1), (1, 1, 2, 0), (1, -1, 1, 1)),
    ),
    "Achat condor": (
        "Stabilité dans une zone plus large que le papillon ; risque limité.",
        ((1, 1, 1, -1.5), (1, -1, 1, -0.5), (1, -1, 1, 0.5), (1, 1, 1, 1.5)),
    ),
    "Vente condor": (
        "Sortie d'une zone large ; gain et perte limités.",
        ((1, -1, 1, -1.5), (1, 1, 1, -0.5), (1, 1, 1, 0.5), (1, -1, 1, 1.5)),
    ),
}

PERSONNALISEE = "Personnalisée"
VUE_PERSONNALISEE = "Combinaison libre de 1 à 4 options."


@dataclass(frozen=True)
class Jambe:
    """Une option de la position.

    Attributes:
        option: ``"call"`` ou ``"put"``.
        sens: +1 pour un achat, −1 pour une vente.
        quantite: nombre d'options (≥ 0 ; 0 = jambe inactive).
        strike: prix d'exercice (> 0).
    """

    option: str
    sens: int
    quantite: float
    strike: float

    def __post_init__(self) -> None:
        valider_option(self.option)
        if self.sens not in (1, -1):
            raise ValueError("Le sens d'une jambe doit valoir +1 (achat) ou −1 (vente).")
        if valider_nombre(self.quantite, "La quantité") < 0:
            raise ValueError("La quantité d'une jambe doit être positive ou nulle.")
        if valider_nombre(self.strike, "Le strike") <= 0:
            raise ValueError("Le strike d'une jambe doit être strictement positif.")

    @property
    def phi(self) -> int:
        """+1 pour un call, −1 pour un put (convention φ des formules)."""
        return 1 if self.option.lower() == "call" else -1

    @property
    def poids(self) -> float:
        """Poids signé ``w = sens × quantité`` utilisé dans toutes les sommes."""
        return self.sens * self.quantite


def jambes_strategie(nom: str, K0: float = 100.0, delta_k: float = 10.0) -> list[Jambe]:
    """Jambes d'une stratégie prédéfinie, strikes ``K0 + multiple × ΔK``."""
    if nom not in STRATEGIES:
        raise ValueError(f"Stratégie inconnue : {nom!r}. Choix : {', '.join(STRATEGIES)}.")
    K0 = valider_nombre(K0, "Le strike central K0")
    delta_k = valider_nombre(delta_k, "L'écart entre strikes ΔK")
    if K0 <= 0 or delta_k < 0:
        raise ValueError("Il faut K0 > 0 et ΔK ≥ 0.")
    definition = STRATEGIES[nom][1]
    if any(K0 + mult * delta_k <= 0 for *_, mult in definition):
        raise ValueError("ΔK trop grand : un strike devient négatif ou nul.")
    return [
        Jambe("call" if phi == 1 else "put", sens, qte, K0 + mult * delta_k)
        for phi, sens, qte, mult in definition
    ]


# ---------------------------------------------------------------------------
# Black-Scholes-Merton vectorisé (une jambe, plusieurs spots)
# ---------------------------------------------------------------------------


def bsm_vectorise(
    S: np.ndarray | float, K: float, r: float, q: float, vol: float, T: float, phi: int
) -> dict[str, np.ndarray]:
    """Prix et grecques BSM d'**une** option pour un ou plusieurs spots.

    Mêmes formules que :mod:`pricer.bsm` et :mod:`pricer.greeks`, écrites avec
    ``φ`` pour traiter call et put en une fois :

    .. math::

        V = φ\\,[S e^{-qT} N(φ d_1) - K e^{-rT} N(φ d_2)], \\qquad
        Δ = φ\\,e^{-qT} N(φ d_1)

        Θ = \\big[-\\tfrac{S e^{-qT} φ(d_1) σ}{2\\sqrt{T}}
            - φ\\,r K e^{-rT} N(φ d_2) + φ\\,q S e^{-qT} N(φ d_1)\\big] / 365,
        \\qquad ρ = φ\\,K T e^{-rT} N(φ d_2) / 100

    À l'échéance (``T ≤ 0``), la valeur est le payoff, le delta vaut 1 ou 0
    selon que l'option est dans la monnaie, et les autres grecques sont nulles
    (convention de l'Excel).
    """
    S = np.asarray(S, dtype=float)
    if T <= 0:
        intrinseque = np.maximum(phi * (S - K), 0.0)
        zero = np.zeros_like(S)
        return {
            "valeur": intrinseque,
            "delta": np.where(phi * (S - K) > 0, float(phi), 0.0),
            "gamma": zero,
            "vega": zero,
            "theta": zero,
            "rho": zero,
        }
    racine_t = math.sqrt(T)
    sq = vol * racine_t
    d1 = (np.log(S / K) + (r - q + 0.5 * vol * vol) * T) / sq
    d2 = d1 - sq
    eq, er = math.exp(-q * T), math.exp(-r * T)
    n_d1, n_d2 = ndtr(phi * d1), ndtr(phi * d2)
    densite = _INV_RACINE_2PI * np.exp(-0.5 * d1 * d1)
    return {
        "valeur": phi * (S * eq * n_d1 - K * er * n_d2),
        "delta": phi * eq * n_d1,
        "gamma": eq * densite / (S * sq),
        "vega": S * eq * densite * racine_t / 100.0,
        "theta": (
            -S * eq * densite * vol / (2.0 * racine_t)
            - phi * r * K * er * n_d2
            + phi * q * S * eq * n_d1
        )
        / JOURS_PAR_AN,
        "rho": phi * K * T * er * n_d2 / 100.0,
    }


# ---------------------------------------------------------------------------
# Analyse de la position
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LigneJambe:
    """Prime et grecques d'une jambe, pondérées par ``w = sens × quantité``."""

    jambe: Jambe
    prime: float  # prime unitaire
    montant: float  # w × prime (> 0 payé, < 0 encaissé)
    delta: float
    gamma: float
    vega: float
    theta: float
    rho: float


@dataclass(frozen=True)
class AnalysePosition:
    """Résultat de :func:`analyser_position`.

    ``gain_max`` vaut ``+inf`` si le gain est illimité et ``perte_max`` vaut
    ``−inf`` si la perte est illimitée (« Illimité » dans l'Excel).
    """

    lignes: list[LigneJambe]
    cout_net: float
    delta: float
    gamma: float
    vega: float
    theta: float
    rho: float
    points_morts: list[float]
    gain_max: float
    perte_max: float

    def grecques(self) -> dict[str, float]:
        """Grecques de la position."""
        return {
            "delta": self.delta,
            "gamma": self.gamma,
            "vega": self.vega,
            "theta": self.theta,
            "rho": self.rho,
        }


def _valider_position(
    jambes: list[Jambe], S: float, r: float, q: float, vol: float, jours: float
) -> list[Jambe]:
    """Contrôles communs ; renvoie les jambes actives (quantité > 0)."""
    if not 1 <= len(jambes) <= 4:
        raise ValueError("Une stratégie comporte de 1 à 4 jambes.")
    jours = valider_nombre(jours, "La maturité en jours")
    if jours < 1:
        raise ValueError("La maturité doit être d'au moins 1 jour.")
    actives = [j for j in jambes if j.quantite > 0]
    for j in actives or jambes:
        valider_marche(S, j.strike, r, q, vol, jours / JOURS_PAR_AN)
    return actives


def pnl_echeance(jambes: list[Jambe], spots: np.ndarray | float, cout_net: float) -> np.ndarray:
    """P&L à l'échéance : ``Σ w_i · max(φ_i (x − K_i), 0) − coût net``."""
    x = np.asarray(spots, dtype=float)
    payoff = sum(
        (j.poids * np.maximum(j.phi * (x - j.strike), 0.0) for j in jambes), np.zeros_like(x)
    )
    return payoff - cout_net


def profil_echeance(jambes: list[Jambe], cout_net: float) -> tuple[list[float], float, float]:
    """Points morts, gain maximum et perte maximum **exacts** à l'échéance.

    Le P&L à l'échéance est linéaire par morceaux, avec des cassures aux
    strikes. On l'évalue en ``x = 0`` et à chaque strike, puis :

    - chaque changement de signe entre deux points consécutifs donne un point
      mort par interpolation linéaire (exacte, puisque le profil est linéaire) ;
    - au-delà du plus haut strike, la pente vaut ``Σ w_i`` sur les calls : si
      elle est non nulle, il peut y avoir un dernier point mort, et le gain
      (pente > 0) ou la perte (pente < 0) est illimité ;
    - sinon, le gain et la perte extrêmes sont atteints en l'un des points.
    """
    actives = [j for j in jambes if j.quantite > 0]
    x = np.array([0.0] + sorted(j.strike for j in actives))
    y = pnl_echeance(actives, x, cout_net)
    points: list[float] = []
    for i in range(1, x.size):
        if y[i - 1] * y[i] < 0 or (y[i] == 0 and y[i - 1] != 0):
            points.append(float(x[i - 1] - y[i - 1] * (x[i] - x[i - 1]) / (y[i] - y[i - 1])))
    pente = sum(j.poids for j in actives if j.phi == 1)
    if y[-1] * pente < 0:
        points.append(float(x[-1] - y[-1] / pente))
    gain = math.inf if pente > 1e-9 else float(y.max())
    perte = -math.inf if pente < -1e-9 else float(y.min())
    return sorted(points), gain, perte


def analyser_position(
    jambes: list[Jambe], S: float, r: float, q: float, vol: float, jours: float
) -> AnalysePosition:
    """Primes, grecques, coût net et profil à l'échéance d'une position.

    Les grecques de la position sont les sommes des grecques des jambes
    pondérées par ``w = sens × quantité`` (la valorisation est linéaire).
    """
    _valider_position(jambes, S, r, q, vol, jours)
    T = jours / JOURS_PAR_AN
    lignes = []
    for j in jambes:
        if j.quantite == 0:
            lignes.append(LigneJambe(j, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0))
            continue
        g = {k: float(v) for k, v in bsm_vectorise(S, j.strike, r, q, vol, T, j.phi).items()}
        w = j.poids
        lignes.append(
            LigneJambe(
                j,
                g["valeur"],
                w * g["valeur"],
                w * g["delta"],
                w * g["gamma"],
                w * g["vega"],
                w * g["theta"],
                w * g["rho"],
            )
        )
    totaux = {
        k: sum(getattr(li, k) for li in lignes)
        for k in ("montant", "delta", "gamma", "vega", "theta", "rho")
    }
    points, gain, perte = profil_echeance(jambes, totaux["montant"])
    return AnalysePosition(
        lignes=lignes,
        cout_net=totaux["montant"],
        delta=totaux["delta"],
        gamma=totaux["gamma"],
        vega=totaux["vega"],
        theta=totaux["theta"],
        rho=totaux["rho"],
        points_morts=points,
        gain_max=gain,
        perte_max=perte,
    )


# ---------------------------------------------------------------------------
# Scénario : P&L expliqué par les grecques
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Scenario:
    """Décomposition du P&L d'un scénario (bloc « Le P&L expliqué par les Grecques »)."""

    contribution_delta: float
    contribution_gamma: float
    contribution_vega: float
    contribution_theta: float
    pnl_reel: float

    @property
    def total_grecques(self) -> float:
        """P&L approché par le développement de Taylor."""
        return (
            self.contribution_delta
            + self.contribution_gamma
            + self.contribution_vega
            + self.contribution_theta
        )

    @property
    def ecart(self) -> float:
        """Écart dû aux effets croisés (vanna, volga, …) et aux ordres supérieurs."""
        return self.pnl_reel - self.total_grecques


def valeur_position(
    jambes: list[Jambe],
    spots: np.ndarray | float,
    r: float,
    q: float,
    vol: float,
    T: float,
    grecque: str | None = None,
) -> np.ndarray:
    """Valeur de la position (ou d'une grecque) pour un ou plusieurs spots."""
    cle = grecque or "valeur"
    x = np.asarray(spots, dtype=float)
    total = np.zeros_like(x)
    for j in jambes:
        if j.quantite > 0:
            total = total + j.poids * bsm_vectorise(x, j.strike, r, q, vol, T, j.phi)[cle]
    return total


def scenario_pnl(
    jambes: list[Jambe],
    S: float,
    r: float,
    q: float,
    vol: float,
    jours: float,
    jours_ecoules: float = 30,
    vol_scenario: float | None = None,
    spot_scenario: float | None = None,
) -> Scenario:
    """P&L d'un scénario et son explication par les grecques d'aujourd'hui.

    Développement de Taylor de la valeur de la position :

    .. math::

        ΔV ≈ Δ·ΔS + ½Γ·ΔS^2 + \\mathcal{V}·Δσ_{pts} + Θ·Δt_{jours}

    Le P&L réel est obtenu par réévaluation BSM complète avec le spot, la
    volatilité et la maturité restante du scénario. L'écart mesure ce que les
    grecques ne capturent pas : termes croisés (vanna = ∂Δ/∂σ, charm = ∂Δ/∂t),
    volga, et la variation des grecques elles-mêmes pour de grands chocs.
    """
    actives = _valider_position(jambes, S, r, q, vol, jours)
    vol_sc = vol if vol_scenario is None else valider_nombre(vol_scenario, "La volatilité σ'")
    spot_sc = S if spot_scenario is None else valider_nombre(spot_scenario, "Le spot S'")
    jours_ecoules = valider_nombre(jours_ecoules, "Le nombre de jours écoulés")
    if jours_ecoules < 0 or vol_sc <= 0 or spot_sc <= 0:
        raise ValueError("Il faut des jours écoulés ≥ 0, σ' > 0 et S' > 0.")
    pos = analyser_position(jambes, S, r, q, vol, jours)
    restant = max(jours - jours_ecoules, 0.0) / JOURS_PAR_AN
    valeur_sc = float(valeur_position(actives, spot_sc, r, q, vol_sc, restant))
    ds = spot_sc - S
    return Scenario(
        contribution_delta=pos.delta * ds,
        contribution_gamma=0.5 * pos.gamma * ds * ds,
        contribution_vega=pos.vega * (vol_sc - vol) * 100.0,
        contribution_theta=pos.theta * jours_ecoules,
        pnl_reel=valeur_sc - pos.cout_net,
    )


# ---------------------------------------------------------------------------
# Graphiques, comparatif et lecture des grecques
# ---------------------------------------------------------------------------


def profils(
    jambes: list[Jambe],
    S: float,
    r: float,
    q: float,
    vol: float,
    jours: float,
    jours_ecoules: float = 30,
    vol_scenario: float | None = None,
    grecque: Grecque = "gamma",
    amplitude: float = 0.30,
    n_points: int = 121,
) -> dict[str, np.ndarray]:
    """Courbes des deux graphiques de l'onglet, en fonction du cours.

    Grille : ``n_points`` cours équirépartis entre ``S(1 − a)`` et ``S(1 + a)``.

    Returns:
        ``spots``, ``pnl_echeance``, ``pnl_j0`` (P&L si l'on dénoue aujourd'hui),
        ``pnl_scenario``, ``grecque_j0`` et ``grecque_scenario``.
    """
    actives = _valider_position(jambes, S, r, q, vol, jours)
    if grecque not in GRECQUES:
        raise ValueError(f"Grecque inconnue : {grecque!r} (choix : {', '.join(GRECQUES)}).")
    amplitude = valider_nombre(amplitude, "L'amplitude")
    if not 0.05 <= amplitude < 1:
        raise ValueError("L'amplitude doit être comprise entre 5 % et 100 % (exclu).")
    vol_sc = vol if vol_scenario is None else vol_scenario
    T = jours / JOURS_PAR_AN
    restant = max(jours - jours_ecoules, 0.0) / JOURS_PAR_AN
    cout = analyser_position(jambes, S, r, q, vol, jours).cout_net
    x = np.linspace(S * (1 - amplitude), S * (1 + amplitude), n_points)
    return {
        "spots": x,
        "pnl_echeance": pnl_echeance(actives, x, cout),
        "pnl_j0": valeur_position(actives, x, r, q, vol, T) - cout,
        "pnl_scenario": valeur_position(actives, x, r, q, vol_sc, restant) - cout,
        "grecque_j0": valeur_position(actives, x, r, q, vol, T, grecque),
        "grecque_scenario": valeur_position(actives, x, r, q, vol_sc, restant, grecque),
    }


def tableau_comparatif(
    S: float,
    r: float,
    q: float,
    vol: float,
    jours: float,
    K0: float = 100.0,
    delta_k: float = 10.0,
) -> list[dict[str, float | str]]:
    """Coût net et grecques des 16 stratégies aux mêmes paramètres."""
    lignes: list[dict[str, float | str]] = []
    for nom, (vue, _) in STRATEGIES.items():
        pos = analyser_position(jambes_strategie(nom, K0, delta_k), S, r, q, vol, jours)
        lignes.append(
            {
                "stratégie": nom,
                "coût net": pos.cout_net,
                "delta": pos.delta,
                "gamma": pos.gamma,
                "vega": pos.vega,
                "theta": pos.theta,
                "vue": vue,
            }
        )
    return lignes


def _fixe(x: float, decimales: int) -> str:
    """Format français à virgule, comme la fonction FIXED d'Excel."""
    return f"{x:.{decimales}f}".replace(".", ",")


def lecture_grecques(
    pos: AnalysePosition, S: float, r: float, q: float, vol: float, jours: float
) -> list[str]:
    """Interprétation en clair des grecques de la position (bloc H24:H28).

    Les seuils sont relatifs à une option à la monnaie (strike = spot) : un
    gamma est « faible » s'il est inférieur au quart de celui d'un call à la
    monnaie, et une vega est « marquée » si elle dépasse la moitié de la sienne.
    """
    T = jours / JOURS_PAR_AN
    atm = {k: float(v) for k, v in bsm_vectorise(S, S, r, q, vol, T, 1).items()}
    vega_ref, gamma_ref = atm["vega"], atm["vega"] * 100 / (S * S * vol * T)
    d, g, v, t = pos.delta, pos.gamma, pos.vega, pos.theta

    if abs(d) < 0.05:
        l_delta = f"Delta {_fixe(d, 2)} : position quasi neutre à la direction du marché."
    else:
        biais = (
            f"biais {'haussier' if d > 0 else 'baissier'} faible."
            if abs(d) < 0.3
            else f"exposition {'haussière' if d > 0 else 'baissière'} marquée."
        )
        l_delta = (
            f"Delta {_fixe(d, 2)} : {'gagne' if d > 0 else 'perd'} ≈ {_fixe(abs(d), 2)} € "
            f"si le sous-jacent monte de 1 € — {biais}"
        )
    if abs(g) < 0.0005:
        l_gamma = "Gamma ≈ 0 : le Delta reste stable quand le sous-jacent bouge."
    elif abs(g) < 0.25 * gamma_ref:
        l_gamma = f"Gamma {_fixe(g, 4)} : faible — le Delta varie peu quand le sous-jacent bouge."
    elif g > 0:
        l_gamma = (
            f"Gamma {_fixe(g, 4)} > 0 : acheteur de convexité — les grands mouvements "
            "jouent en faveur de la position."
        )
    else:
        l_gamma = (
            f"Gamma {_fixe(g, 4)} < 0 : vendeur de convexité — les grands mouvements "
            "coûtent à la position."
        )
    if abs(v) < 0.005:
        l_vega = "Vega ≈ 0 : quasi insensible à la volatilité implicite."
    else:
        fin = (
            "exposition faible à la volatilité)."
            if abs(v) < 0.5 * vega_ref
            else f"{'acheteur' if v > 0 else 'vendeur'} de volatilité)."
        )
        l_vega = (
            f"Vega {_fixe(v, 3)} : {'gagne' if v > 0 else 'perd'} ≈ {_fixe(abs(v), 2)} € "
            f"si la volatilité implicite monte d'1 point ({fin}"
        )
    if abs(t) < 0.0005:
        l_theta = "Theta ≈ 0 : le passage du temps a peu d'effet."
    else:
        l_theta = (
            f"Theta {_fixe(t, 3)} : {'perd' if t < 0 else 'gagne'} ≈ {_fixe(abs(t), 3)} € "
            f"par jour si rien ne bouge (le temps joue {'contre' if t < 0 else 'pour'} "
            "la position)."
        )
    if abs(d) >= 0.3 and abs(v) < 0.5 * vega_ref:
        synthese = "pari directionnel — le Delta domine, faible exposition à la volatilité."
    elif abs(d) >= 0.3:
        synthese = "pari directionnel ET exposition marquée à la volatilité."
    elif v >= 0.5 * vega_ref:
        synthese = (
            "acheteur de volatilité — paie le temps (Theta) pour profiter des "
            "mouvements (Gamma, Vega)."
        )
    elif v <= -0.5 * vega_ref:
        synthese = (
            "vendeur de volatilité — encaisse le temps (Theta) en échange du risque de mouvement."
        )
    else:
        synthese = "exposition modérée — lire chaque Grecque séparément."
    return [l_delta, l_gamma, l_vega, l_theta, f"Synthèse : {synthese}"]

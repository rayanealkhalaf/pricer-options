"""Contrôles de validation des entrées.

Reprise fidèle des contrôles VBA (``LireInputs``, ``ValiderMarche``,
``ValiderEntier``, ``ProbaCRROk``) : chaque fonction lève une ``ValueError`` avec
un message clair en français au lieu d'afficher une ``MsgBox``.
"""

from __future__ import annotations

import math
from numbers import Integral, Real

#: Maturité maximale acceptée (années), comme ``T_MAX`` dans le VBA.
T_MAX = 50.0
#: Seuil de dépassement de capacité de ``exp`` (exp(709) ≈ 8e307).
LIMITE_EXP = 700.0


def valider_nombre(x: object, nom: str) -> float:
    """Vérifie que ``x`` est un nombre réel fini et le renvoie en ``float``.

    Les booléens sont refusés (``True`` serait sinon lu comme 1).
    """
    if isinstance(x, bool) or not isinstance(x, Real):
        raise ValueError(f"{nom} doit être un nombre (reçu : {x!r}).")
    valeur = float(x)
    if not math.isfinite(valeur):
        raise ValueError(f"{nom} doit être un nombre fini (reçu : {valeur}).")
    return valeur


def valider_marche(
    S: float,
    K: float,
    r: float,
    q: float,
    vol: float,
    T: float,
    *,
    vol_nulle_permise: bool = False,
) -> None:
    """Contrôle les paramètres de marché communs à tous les produits.

    Règles (identiques au VBA) :

    - ``S > 0``, ``K > 0`` ;
    - ``σ ≥ 0`` si ``vol_nulle_permise`` (onglet européen), sinon ``σ > 0`` ;
    - ``0 < T ≤ 50`` ;
    - domaine numérique : ``|ln S| + |(r − q − σ²/2)T| + 7σ√T ≤ 700`` et
      ``|rT|, |qT| ≤ 700``, pour qu'aucun ``exp`` ne déborde, même à 7 écarts-types.

    Raises:
        ValueError: si un paramètre est invalide, avec un message explicite.
    """
    S = valider_nombre(S, "Le spot S")
    K = valider_nombre(K, "Le strike K")
    r = valider_nombre(r, "Le taux r")
    q = valider_nombre(q, "Le dividende q")
    vol = valider_nombre(vol, "La volatilité")
    T = valider_nombre(T, "La maturité T")

    if S <= 0:
        raise ValueError("S doit être strictement positif (S > 0).")
    if K <= 0:
        raise ValueError("K doit être strictement positif (K > 0).")
    if vol_nulle_permise:
        if vol < 0:
            raise ValueError("La volatilité ne peut pas être négative (Vol >= 0).")
    elif vol <= 0:
        raise ValueError("La volatilité doit être strictement positive (Vol > 0).")
    if T <= 0:
        raise ValueError("La maturité doit être strictement positive (T > 0).")
    if T > T_MAX:
        raise ValueError(f"Maturité hors domaine : T doit être <= {T_MAX:g} ans.")

    lim = abs(math.log(S)) + abs((r - q - 0.5 * vol * vol) * T) + 7.0 * vol * math.sqrt(T)
    if lim > LIMITE_EXP or abs(r * T) > LIMITE_EXP or abs(q * T) > LIMITE_EXP:
        raise ValueError("Paramètres hors domaine numérique (dépassement de capacité d'exp).")


def valider_entier(x: object, lo: int, hi: int, nom: str) -> int:
    """Vérifie que ``x`` est un entier compris entre ``lo`` et ``hi`` (inclus).

    Un flottant entier (``1000.0``) est accepté, comme dans Excel.
    """
    message = f"{nom} doit être un entier entre {_milliers(lo)} et {_milliers(hi)}."
    flottant_entier = isinstance(x, Real) and math.isfinite(float(x)) and float(x).is_integer()
    if isinstance(x, bool) or not (isinstance(x, Integral) or flottant_entier):
        raise ValueError(message)
    valeur = int(x)
    if not lo <= valeur <= hi:
        raise ValueError(message)
    return valeur


def _milliers(n: int) -> str:
    """Formate un entier avec une espace comme séparateur de milliers (1 000)."""
    return f"{n:,}".replace(",", " ")


def valider_option(option: str) -> bool:
    """Normalise le type d'option et renvoie ``True`` pour un call.

    Accepte ``"call"`` / ``"put"`` (insensible à la casse).
    """
    if not isinstance(option, str) or option.lower() not in {"call", "put"}:
        raise ValueError(f"Le type d'option doit être 'call' ou 'put' (reçu : {option!r}).")
    return option.lower() == "call"


def valider_barriere(H: float) -> float:
    """Contrôle la barrière : ``H > 0``."""
    H = valider_nombre(H, "La barrière H")
    if H <= 0:
        raise ValueError("La barrière H doit être strictement positive (H > 0).")
    return H


def valider_produit(a: int, b: int, plafond: float, message: str) -> None:
    """Plafonne la taille du calcul (simulations × pas), comme dans le VBA."""
    if float(a) * float(b) > plafond:
        raise ValueError(message)


def probabilite_crr(r: float, q: float, vol: float, dt: float) -> float:
    """Probabilité risque-neutre de l'arbre CRR.

    .. math:: u = e^{σ\\sqrt{Δt}},\\quad d = 1/u,\\quad p = \\frac{e^{(r-q)Δt} - d}{u - d}
    """
    u = math.exp(vol * math.sqrt(dt))
    d = 1.0 / u
    return (math.exp((r - q) * dt) - d) / (u - d)


def valider_arbre(S: float, r: float, q: float, vol: float, T: float, n_pas: int) -> None:
    """Contrôles spécifiques à l'arbre CRR (``ProbaCRROk`` et domaine numérique)."""
    if vol * math.sqrt(T * n_pas) + abs(math.log(S)) > LIMITE_EXP:
        raise ValueError(
            "Arbre hors domaine numérique : réduisez le nombre de pas, T ou la volatilité."
        )
    p = probabilite_crr(r, q, vol, T / n_pas)
    if not 0.0 < p < 1.0:
        raise ValueError(
            "Probabilité risque-neutre de l'arbre hors de ]0,1[ : "
            "augmentez le nombre de pas ou la volatilité."
        )

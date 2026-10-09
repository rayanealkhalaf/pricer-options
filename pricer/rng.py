"""Générateurs de nombres aléatoires.

Deux générateurs exposent la même interface ``normales(forme)`` :

- :class:`GenerateurPCG64` : ``numpy.random.Generator(PCG64)``, le choix par
  défaut (rapide, statistiquement excellent, standard NumPy) ;
- :class:`MRG32k3a` : le générateur combiné de L'Ecuyer (1999) suivi de
  Box-Muller, **identique au VBA** du classeur (même initialisation depuis la
  graine, même chauffe de 100 tirages, même ordre de consommation des
  normales). Il permet de rejouer exactement les tirages Excel, à l'arrondi près
  des fonctions ``log``/``cos``/``sin`` de chaque plateforme.

Les tableaux de normales sont remplis dans l'ordre « C » (ligne par ligne) : une
matrice ``(n_chemins, n_pas)`` reçoit les tirages chemin par chemin, exactement
comme les doubles boucles ``For i … For j …`` du VBA.

Graine : ``None`` ou ``0`` signifie « graine aléatoire », comme dans l'Excel.
La graine effectivement utilisée est conservée dans ``graine_utilisee`` pour
pouvoir reproduire un calcul.
"""

from __future__ import annotations

import math
import secrets
from typing import Literal, Protocol

import numpy as np

Methode = Literal["pcg64", "mrg32k3a"]

_MAX_GRAINE = 2_147_483_647  # 2^31 - 1, comme DMod(Int(seed), 2147483647#) en VBA


def _graine_effective(graine: int | None) -> int:
    """Renvoie la graine à utiliser : tirée au hasard si ``None`` ou 0."""
    if graine is None or graine == 0:
        return secrets.randbelow(_MAX_GRAINE - 1) + 1
    if isinstance(graine, bool) or not isinstance(graine, int | np.integer):
        raise ValueError(f"La graine doit être un entier (reçu : {graine!r}).")
    return abs(int(graine))


class GenerateurNormal(Protocol):
    """Interface commune : un générateur de lois normales centrées réduites."""

    graine_utilisee: int

    def normales(self, forme: int | tuple[int, ...]) -> np.ndarray:
        """Renvoie un tableau de N(0, 1) indépendantes de la forme demandée."""
        ...


class GenerateurPCG64:
    """Générateur NumPy PCG64 (O'Neill, 2014), choix par défaut du projet."""

    def __init__(self, graine: int | None = None) -> None:
        self.graine_utilisee = _graine_effective(graine)
        self._gen = np.random.Generator(np.random.PCG64(self.graine_utilisee))

    def normales(self, forme: int | tuple[int, ...]) -> np.ndarray:
        """Tire des N(0, 1) par l'algorithme ziggurat de NumPy."""
        return self._gen.standard_normal(forme)


# ---------------------------------------------------------------------------
# MRG32k3a
# ---------------------------------------------------------------------------

Matrice3 = tuple[tuple[int, int, int], tuple[int, int, int], tuple[int, int, int]]


def _produit_mod(a: Matrice3, b: Matrice3, m: int) -> Matrice3:
    """Produit de deux matrices 3×3 modulo ``m`` (entiers Python, exact)."""
    return tuple(  # type: ignore[return-value]
        tuple(sum(a[i][k] * b[k][j] for k in range(3)) % m for j in range(3)) for i in range(3)
    )


def _puissance_mod(a: Matrice3, e: int, m: int) -> Matrice3:
    """Puissance ``a^e`` modulo ``m`` par exponentiation rapide."""
    resultat: Matrice3 = ((1, 0, 0), (0, 1, 0), (0, 0, 1))
    while e > 0:
        if e & 1:
            resultat = _produit_mod(resultat, a, m)
        a = _produit_mod(a, a, m)
        e >>= 1
    return resultat


def _appliquer_mod(a: Matrice3, v: tuple[int, int, int], m: int) -> tuple[int, int, int]:
    """Produit matrice × vecteur modulo ``m``."""
    return tuple(sum(a[i][k] * v[k] for k in range(3)) % m for i in range(3))  # type: ignore[return-value]


class MRG32k3a:
    """Générateur MRG32k3a de L'Ecuyer (1999) + Box-Muller, identique au VBA.

    Récurrences (deux composantes, combinées) :

    .. math::

        x_{1,n} = (1403580\\,x_{1,n-2} - 810728\\,x_{1,n-3}) \\bmod m_1,
        \\quad m_1 = 2^{32} - 209

        x_{2,n} = (527612\\,x_{2,n-1} - 1370589\\,x_{2,n-3}) \\bmod m_2,
        \\quad m_2 = 2^{32} - 22853

        U_n = \\frac{(x_{1,n} - x_{2,n}) \\bmod m_1}{m_1 + 1} \\in\\ ]0, 1[

    Période ≈ 2^191. Chaque composante est une récurrence **linéaire** :
    l'état ``v`` avance par ``v ← A·v mod m``. On peut donc sauter de ``L`` pas
    d'un coup avec ``A^L`` : c'est ce qui permet de vectoriser la génération
    (plusieurs blocs consécutifs de la suite avancent en parallèle), tout en
    produisant **exactement** la même suite que la boucle séquentielle du VBA.

    Box-Muller : ``(U₁, U₂) → (R cos θ, R sin θ)`` avec ``R = √(−2 ln U₁)`` et
    ``θ = 2πU₂`` ; la seconde normale est conservée pour l'appel suivant.
    """

    M1 = 4_294_967_087
    M2 = 4_294_944_443
    A12 = 1_403_580
    A13N = 810_728
    A21 = 527_612
    A23N = 1_370_589

    #: Matrices de transition des deux composantes (état = (s0, s1, s2)).
    _A1: Matrice3 = ((0, 1, 0), (0, 0, 1), ((-A13N) % M1, A12, 0))
    _A2: Matrice3 = ((0, 1, 0), (0, 0, 1), ((-A23N) % M2, 0, A21))

    _NORME = 1.0 / (M1 + 1.0)
    _DEUX_PI = 8.0 * math.atan(1.0)  # identique à 8# * Atn(1#) en VBA

    def __init__(self, graine: int | None = None) -> None:
        self.graine_utilisee = _graine_effective(graine)
        self._s1: tuple[int, int, int] = (0, 0, 0)
        self._s2: tuple[int, int, int] = (0, 0, 0)
        self._reserve: float | None = None
        self._initialiser(self.graine_utilisee)

    # -- initialisation (RngSeed) -------------------------------------------
    def _initialiser(self, graine: int) -> None:
        """Reproduit ``RngSeed`` : six états dérivés de la graine, puis chauffe."""
        b = graine % _MAX_GRAINE
        s10 = (b + 12345) % self.M1
        s11 = (b * 69069 + 1) % self.M1
        s12 = (b * 1664525 + 1013904223) % self.M1
        s20 = (b + 54321) % self.M2
        s21 = (b * 40014 + 12345) % self.M2
        s22 = (b * 3141592 + 2718281) % self.M2
        if s10 == s11 == s12 == 0:
            s10 = 12345
        if s20 == s21 == s22 == 0:
            s20 = 12345
        self.definir_etat((s10, s11, s12), (s20, s21, s22))
        for _ in range(100):  # chauffe : décorrèle les graines voisines
            self.uniforme()

    def definir_etat(self, etat1: tuple[int, int, int], etat2: tuple[int, int, int]) -> None:
        """Fixe directement l'état interne (utile pour les tests de référence)."""
        self._s1 = tuple(int(x) for x in etat1)  # type: ignore[assignment]
        self._s2 = tuple(int(x) for x in etat2)  # type: ignore[assignment]
        self._reserve = None

    @property
    def etat(self) -> tuple[tuple[int, int, int], tuple[int, int, int]]:
        """État courant ``((s10, s11, s12), (s20, s21, s22))``."""
        return self._s1, self._s2

    # -- version séquentielle (référence, = RngU / GaussBM) ------------------
    def uniforme(self) -> float:
        """Un tirage U(0, 1), version séquentielle identique à ``RngU``."""
        s10, s11, s12 = self._s1
        s20, s21, s22 = self._s2
        p1 = (self.A12 * s11 - self.A13N * s10) % self.M1
        p2 = (self.A21 * s22 - self.A23N * s20) % self.M2
        self._s1 = (s11, s12, p1)
        self._s2 = (s21, s22, p2)
        return (p1 - p2 + self.M1) * self._NORME if p1 <= p2 else (p1 - p2) * self._NORME

    def normale(self) -> float:
        """Une N(0, 1) par Box-Muller, version séquentielle identique à ``GaussBM``."""
        if self._reserve is not None:
            z, self._reserve = self._reserve, None
            return z
        u1 = self.uniforme()
        u2 = self.uniforme()
        rayon = math.sqrt(-2.0 * math.log(u1))
        theta = self._DEUX_PI * u2
        self._reserve = rayon * math.sin(theta)
        return rayon * math.cos(theta)

    # -- version vectorisée -------------------------------------------------
    def uniformes(self, n: int) -> np.ndarray:
        """``n`` tirages U(0, 1) consécutifs, vectorisés par saut en avant.

        La suite est découpée en ``B`` blocs de longueur ``L``. L'état initial
        du bloc ``b`` vaut ``A^{bL}·v₀`` (calcul exact en entiers Python) ; les
        ``B`` blocs avancent ensuite ensemble en ``int64`` NumPy (les produits
        restent < 2^53, donc sans débordement). Résultat identique, tirage par
        tirage, à ``n`` appels de :meth:`uniforme`.
        """
        n = int(n)
        if n <= 0:
            return np.empty(0)
        if n < 256:
            return np.array([self.uniforme() for _ in range(n)])

        n_blocs = min(n, max(64, 2 * math.isqrt(n)))
        longueur = -(-n // n_blocs)  # plafond de n / n_blocs
        saut1 = _puissance_mod(self._A1, longueur, self.M1)
        saut2 = _puissance_mod(self._A2, longueur, self.M2)

        departs1 = [self._s1]
        departs2 = [self._s2]
        for _ in range(n_blocs - 1):
            departs1.append(_appliquer_mod(saut1, departs1[-1], self.M1))
            departs2.append(_appliquer_mod(saut2, departs2[-1], self.M2))
        e1 = np.array(departs1, dtype=np.int64).T  # 3 × B
        e2 = np.array(departs2, dtype=np.int64).T
        s10, s11, s12 = e1[0].copy(), e1[1].copy(), e1[2].copy()
        s20, s21, s22 = e2[0].copy(), e2[1].copy(), e2[2].copy()

        p1s = np.empty((longueur, n_blocs), dtype=np.int64)
        p2s = np.empty((longueur, n_blocs), dtype=np.int64)
        for t in range(longueur):
            p1 = (self.A12 * s11 - self.A13N * s10) % self.M1  # modulo positif en NumPy
            p2 = (self.A21 * s22 - self.A23N * s20) % self.M2
            s10, s11, s12 = s11, s12, p1
            s20, s21, s22 = s21, s22, p2
            p1s[t] = p1
            p2s[t] = p2

        # Ordre de la suite : bloc 0 en entier, puis bloc 1, etc.
        p1 = p1s.T.reshape(-1)[:n]
        p2 = p2s.T.reshape(-1)[:n]
        diff = p1 - p2
        u = np.where(p1 <= p2, diff + self.M1, diff).astype(np.float64) * self._NORME

        # État final = A^n · v₀ (saut exact)
        self._s1 = _appliquer_mod(_puissance_mod(self._A1, n, self.M1), departs1[0], self.M1)
        self._s2 = _appliquer_mod(_puissance_mod(self._A2, n, self.M2), departs2[0], self.M2)
        return u

    def normales(self, forme: int | tuple[int, ...]) -> np.ndarray:
        """Tableau de N(0, 1) par Box-Muller vectorisé (ordre identique au VBA)."""
        forme_t = (forme,) if isinstance(forme, int | np.integer) else tuple(forme)
        n = int(np.prod(forme_t, dtype=np.int64))
        sortie = np.empty(n)
        debut = 0
        if n > 0 and self._reserve is not None:
            sortie[0] = self._reserve
            self._reserve = None
            debut = 1
        reste = n - debut
        if reste > 0:
            n_paires = -(-reste // 2)
            u = self.uniformes(2 * n_paires)
            rayon = np.sqrt(-2.0 * np.log(u[0::2]))
            theta = self._DEUX_PI * u[1::2]
            z = np.empty(2 * n_paires)
            z[0::2] = rayon * np.cos(theta)
            z[1::2] = rayon * np.sin(theta)
            sortie[debut:] = z[:reste]
            if 2 * n_paires > reste:  # nombre impair : la dernière normale est gardée
                self._reserve = float(z[-1])
        return sortie.reshape(forme_t)


def creer_generateur(graine: int | None = None, methode: Methode = "pcg64") -> GenerateurNormal:
    """Fabrique le générateur demandé.

    Args:
        graine: entier > 0 pour un calcul reproductible ; ``None`` ou 0 pour
            une graine aléatoire (convention de l'Excel).
        methode: ``"pcg64"`` (défaut, NumPy) ou ``"mrg32k3a"`` (identique au VBA).
    """
    if methode == "pcg64":
        return GenerateurPCG64(graine)
    if methode == "mrg32k3a":
        return MRG32k3a(graine)
    raise ValueError(f"Générateur inconnu : {methode!r} (choix : 'pcg64' ou 'mrg32k3a').")

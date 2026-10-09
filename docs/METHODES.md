# Méthodes de valorisation

Pour chaque méthode, ce document donne l'intuition, la formule et les limites. Les
notations sont les suivantes : spot `S`, strike `K`, taux sans risque continu `r`,
dividende continu `q`, volatilité `σ`, maturité `T`, `N(·)` la fonction de répartition de la
loi normale et `φ(·)` sa densité.

**Modèle commun.** Sous la probabilité risque-neutre, le sous-jacent suit un mouvement
brownien géométrique `dS = (r − q) S dt + σ S dW`. Une option vaut l'espérance de son payoff
actualisé : `V = e^{−rT} E[payoff]`. Le log-prix est gaussien, donc on peut simuler `S`
**exactement** à n'importe quelle date :

```
S_{t+Δt} = S_t · exp((r − q − σ²/2) Δt + σ √Δt · Z),   Z ~ N(0, 1)
```

Aucune méthode du projet n'a donc de biais de discrétisation du sous-jacent (pas de schéma
d'Euler).

---

## 1. Black-Scholes-Merton (`bsm.py`)

**Intuition.** `S_T` est log-normal. L'espérance de `max(S_T − K, 0)` se calcule alors en
fermé : c'est la probabilité (pondérée) de finir dans la monnaie.

**Formule.**

```
d₁ = [ln(S/K) + (r − q + σ²/2) T] / (σ√T),   d₂ = d₁ − σ√T
Call = S e^{−qT} N(d₁) − K e^{−rT} N(d₂)
Put  = K e^{−rT} N(−d₂) − S e^{−qT} N(−d₁)
```

`N(d₂)` est la probabilité risque-neutre que le call finisse dans la monnaie. Le dividende
`q` réduit le forward `S e^{(r−q)T}`.

**Parité call-put.** `C − P = S e^{−qT} − K e^{−rT}`. Elle découle d'un argument de
non-arbitrage (un call long et un put short répliquent un forward), indépendamment du modèle.
Un écart non nul révèle donc une erreur d'implémentation.

**Volatilité implicite.** C'est le σ qui, injecté dans BSM, redonne le prix observé sur le
marché. Le prix étant strictement croissant en σ (vega > 0), la solution est unique dès que
le prix respecte les bornes de non-arbitrage `max(S e^{−qT} − K e^{−rT}, 0) < C < S e^{−qT}`
(idem pour le put). On la cherche par la méthode de Brent sur `]0 ; 500 %]` : la racine
reste encadrée, donc la méthode converge toujours, alors que Newton-Raphson peut diverger loin
de la monnaie, là où le vega est quasi nul. Quand la valeur temps est négligeable (option très
dans la monnaie, σ faible), le prix ne contient presque plus d'information sur σ : le
problème est mal conditionné, quelle que soit la méthode.

**Limites.** Le modèle suppose une volatilité constante (pas de smile), des taux constants,
pas de frictions et une diffusion continue (pas de sauts).

## 2. Grecques (`greeks.py`)

| Grecque | Call | Put | Convention |
|---|---|---|---|
| Delta | `e^{−qT} N(d₁)` | `e^{−qT}(N(d₁) − 1)` | ∂V/∂S |
| Gamma | `e^{−qT} φ(d₁) / (Sσ√T)` | identique | ∂²V/∂S² |
| Vega | `S e^{−qT} φ(d₁) √T / 100` | identique | pour +1 point de vol |
| Theta | `[−S e^{−qT}φ(d₁)σ/(2√T) − rKe^{−rT}N(d₂) + qSe^{−qT}N(d₁)] / 365` | `[… + rKe^{−rT}N(−d₂) − qSe^{−qT}N(−d₁)] / 365` | par jour calendaire |
| Rho | `K T e^{−rT} N(d₂) / 100` | `−K T e^{−rT} N(−d₂) / 100` | pour +1 point de taux |

**Validation.** Les tests comparent chaque grecque à une différence finie centrée, avec une
tolérance de 1e-4.

**Lecture.** Gamma et vega sont maximaux à la monnaie. Le theta d'un call est négatif : le
temps qui passe coûte au détenteur. Le gamma élevé d'une option courte à la monnaie
s'accompagne d'un theta fortement négatif (relation `Θ + ½σ²S²Γ + (r−q)SΔ = rV`).

## 3. Monte-Carlo européen (`monte_carlo.py`)

**Intuition.** On estime l'espérance par une moyenne empirique sur `N` tirages. La loi des
grands nombres garantit la convergence, et le théorème central limite donne l'erreur.

**Estimateur standard.**

```
V̂ = (1/N) Σ Yᵢ,   SE = s / √N,   IC 95 % = V̂ ± 1,96 · SE,   z = (V̂ − V_BSM) / SE
```

La SE décroît en `1/√N` : pour gagner une décimale, il faut 100 fois plus de simulations.
D'où l'intérêt de réduire la variance.

**Variables antithétiques.** Pour chaque `Z`, on utilise aussi `−Z` et on fait la moyenne
`½[f(Z) + f(−Z)]`. Si `f` est monotone, les deux termes sont négativement corrélés, ce qui
fait baisser la variance. Chaque tirage coûte deux évaluations de payoff, d'où l'« efficacité
AV » `(SE_std / SE_av)² / 2`, à comparer à 1.

**Variable de contrôle.** On choisit `X` corrélé au payoff `Y`, d'espérance connue. Ici
`X = e^{−rT} S_T`, dont l'espérance vaut exactement `S e^{−qT}` (martingale actualisée).

```
V̂_CV = Ȳ − β* (X̄ − E[X]),   β* = Cov(Y, X) / Var(X)
Var(V̂_CV) = Var(Y)(1 − ρ²) / N
```

Le β* optimal est le coefficient de la régression de `Y` sur `X`. Il est estimé sur le même
échantillon, ce qui crée un biais en `O(1/N)`, négligeable ici.

**Limites.** Le gain dépend de `ρ²`. Pour un call à la monnaie, `ρ ≈ 0,91` donne un gain
d'environ ×6. Pour un call très en dehors de la monnaie, la corrélation avec `S_T` est
faible et le gain reste modeste. Remarque : avec ce contrôle, `C − P` est une fonction
linéaire de `X`, si bien que le call et le put ont exactement la même SE résiduelle.

## 4. Arbre de Cox-Ross-Rubinstein (`trees.py`)

**Intuition.** On discrétise le temps en `n` pas. À chaque pas, le spot monte (`×u`) ou
descend (`×d`) avec une probabilité risque-neutre `p`. L'option se valorise ensuite en
remontant l'arbre depuis l'échéance.

```
u = e^{σ√Δt},   d = 1/u,   p = (e^{(r−q)Δt} − d) / (u − d)
V_{i,j} = e^{−rΔt} [p V_{i+1,j+1} + (1 − p) V_{i+1,j}]
Américaine : V_{i,j} = max(continuation, payoff(S_{i,j}))
```

Le `max` avec la valeur d'exercice immédiat est la seule différence entre européenne et
américaine. Comme `u·d = 1`, l'arbre se recombine : il compte `O(n²)` nœuds au total.

**Convergence.** L'erreur est en `O(1/n)`, avec des oscillations qui dépendent de la position
du strike entre deux nœuds.

**Correction par variable de contrôle.** L'arbre commet presque la même erreur sur
l'européenne et sur l'américaine. On connaît l'erreur de l'européenne grâce à BSM, donc :

```
V_am ≈ V_am_arbre + (V_BSM − V_eu_arbre)
```

Avec 1 000 pas, on obtient le put américain `2,320083` (valeur de référence de l'Excel).

**Résultat classique.** Sans dividende, le call américain vaut le call européen : exercer
tôt fait perdre la valeur temps et les intérêts sur le strike (Merton, 1973). L'arbre le
retrouve exactement.

**Limites.** Le coût est en `O(n²)`, et l'arbre est mal adapté aux produits dépendant du
chemin et à la grande dimension. Il faut aussi `p ∈ ]0, 1[`, ce qui impose assez de pas
quand `|r − q|` est grand devant `σ`.

## 5. Longstaff-Schwartz (`lsm.py`)

**Intuition.** À chaque date d'exercice, on exerce si la valeur immédiate dépasse la valeur
de continuation, c'est-à-dire l'espérance conditionnelle des flux futurs. Cette espérance
est inconnue : on l'estime par une **régression** des flux futurs réalisés sur des fonctions
du spot, en remontant le temps.

**Algorithme.**

1. On simule `N` chemins (par paires antithétiques) aux dates `t_j = jT/M`.
2. À l'échéance, le flux vaut `CF = payoff(S_T)`.
3. Pour `j = M−1, …, 1`, sur les chemins **dans la monnaie** uniquement, on régresse
   `CF · e^{−r(τ − t_j)}` sur la base `1, x, x², x³` avec `x = S/K − 1`. On exerce si
   `payoff > continuation estimée`, et on met alors à jour `CF` et `τ`.
4. Le prix vaut `max(payoff(S₀), moyenne des CF actualisés)`, et la SE se calcule sur les
   moyennes des paires antithétiques.

**Pourquoi ne régresser que dans la monnaie ?** La décision d'exercer ne se pose que là, et
la régression y est plus précise. La normalisation `S/K − 1` évite une matrice mal
conditionnée.

**Biais.** La règle d'exercice estimée est sous-optimale, ce qui donne un biais **bas**. Les
dates d'exercice sont discrètes (option bermudéenne), ce qui donne aussi un prix inférieur à
l'américaine. Un estimateur dual (Andersen-Broadie) fournirait une borne haute. Le LSM est
utile surtout en grande dimension (paniers, taux), là où les arbres ne passent pas.

## 6. Asiatiques (`asian.py`)

**Produit.** `max(A − K, 0)`, avec `A` la moyenne arithmétique de `M` fixings équirépartis.

**Pourquoi pas de formule fermée ?** Une somme de log-normales n'est pas log-normale. En
revanche, la moyenne **géométrique** `G` est log-normale, car `ln G` est une moyenne de
gaussiennes :

```
μ_G = ln S + (r − q − σ²/2) T (M+1)/(2M)
σ_G = σ √(T (M+1)(2M+1) / (6M²))
Call_G = e^{−rT} [e^{μ_G + σ_G²/2} N(d₁) − K N(d₂)],   d₁ = (μ_G − ln K + σ_G²)/σ_G,   d₂ = d₁ − σ_G
```

Pour `M = 1`, on retrouve exactement BSM (test unitaire).

**Variable de contrôle géométrique.** `A` et `G` sont corrélées à plus de 0,999. L'estimateur
`Ȳ_A − β*(Ȳ_G − Call_G)` divise la variance par environ 1 300 à 1 500 (×1 337 dans l'Excel).
C'est l'exemple type de la réduction de variance (Kemna-Vorst, 1990).

**Contrôle du moteur.** Le Monte-Carlo de la géométrique seule doit retrouver la formule
exacte (`|z| < 3`). Cela teste le générateur et le schéma de simulation.

**Lecture.** On a `G ≤ A` (inégalité arithmético-géométrique), donc `Call_G < Call_A`. La
moyenne lisse la volatilité, donc l'asiatique vaut moins que la vanille.

## 7. Barrières (`barrier.py`)

**Produit.** Une vanille activée (In) ou désactivée (Out) si le spot touche `H`. Chemin par
chemin, on a toujours **In + Out = vanille**.

**Formules de Reiner-Rubinstein.** On utilise la notation de Haug, avec
`μ = (r − q − σ²/2)/σ²` et `v = σ√T`, et quatre blocs `A, B, C, D`. `A` est la vanille. Les
termes en `(H/S)^{2μ}` viennent du **principe de réflexion** : le nombre de chemins qui
touchent la barrière s'obtient en « réfléchissant » les chemins par rapport à `H`. La table
des combinaisons (dépendant de `K ≥ H` ou `K < H`) est donnée dans la docstring de
`prix_barriere`. Elle a été vérifiée contre les 8 valeurs de l'Excel à 1e-6.

**Cas limite.** Si le spot est déjà au-delà de la barrière, l'option Out vaut 0 et l'option
In vaut la vanille.

**Monte-Carlo : le problème.** Si on ne regarde le chemin qu'aux dates de la grille, on rate
les franchissements entre deux dates. Avec 252 pas, le DOC vaut environ 8,5 au lieu de 8,14.

**Correction de pont brownien.** Entre `x_k` et `x_{k+1}` (log-prix), le brownien conditionné
touche `h = ln H` avec une probabilité exacte :

```
P = exp(−2 (x_k − h)(x_{k+1} − h) / (σ² Δt))
```

La probabilité de survie du chemin vaut alors `s = ∏(1 − P_k)`, et le prix Out vaut
`E[e^{−rT} payoff · s]`. L'estimateur **n'a aucun biais**, même avec 1 seul pas. Seule sa
variance dépend du nombre de pas.

**Surveillance discrète et BGK.** Les produits réels sont souvent observés à la clôture
(surveillance discrète). La correction de Broadie-Glasserman-Kou montre qu'une barrière
discrète équivaut à une barrière continue décalée de `H e^{±0,5826 σ √Δt}` (vers l'extérieur).
Le notebook montre que cette approximation colle au Monte-Carlo discret.

**Limites.** On ne gère ni rebate, ni volatilité locale (les barrières sont très sensibles au
smile), ni double barrière. Près de la barrière, le gamma explose, ce qui rend la couverture
délicate.

## 8. Stratégies et grecques de position (`strategies.py`)

**Intuition.** Une stratégie est une somme d'options. Son prix et ses grecques sont donc les
sommes des prix et grecques des jambes, pondérés par `w = sens × quantité`. La valorisation
BSM est linéaire en position. On lit une stratégie autant par ses grecques (sur quoi
parie-t-on ?) que par son profil à l'échéance.

**Formules.** Pour chaque jambe, on prend le BSM avec `φ = +1` (call) ou `−1` (put), et
`T = jours/365` :

```
V = φ [S e^{−qT} N(φd₁) − K e^{−rT} N(φd₂)],   Δ = φ e^{−qT} N(φd₁)
Position : X_pos = Σ wᵢ Xᵢ   pour X ∈ {V, Δ, Γ, Vega, Θ, ρ}
P&L à l'échéance : Σ wᵢ max(φᵢ(S_T − Kᵢ), 0) − coût net
```

**Points morts et extrêmes exacts.** Le profil à l'échéance est linéaire par morceaux.
On l'évalue en 0 et aux strikes, on interpole entre deux points de signes opposés, et on
traite la demi-droite au-delà du plus haut strike, de pente `Σ w` des calls. Si cette pente
est non nulle, le gain (> 0) ou la perte (< 0) est illimité.

**Scénario et P&L expliqué.**

```
ΔV ≈ Δ·ΔS + ½Γ·ΔS² + Vega·Δσ(points) + Θ·(jours écoulés)
```

On compare cette approximation au P&L réel, obtenu par réévaluation BSM complète. L'écart
correspond aux effets croisés et d'ordre supérieur : vanna, charm, volga, et l'évolution
des grecques pendant le scénario.

**Limites.** Le modèle utilise une volatilité unique pour tous les strikes (pas de smile,
alors qu'un risk reversal ou un strangle y sont très sensibles), ne compte ni coûts de
transaction ni multiplicateur de contrat, et suppose des options européennes.

## 9. Générateurs (`rng.py`)

- **PCG64** (NumPy, par défaut) : rapide, période `2^128`, normales par l'algorithme ziggurat.
- **MRG32k3a** (L'Ecuyer, 1999) : deux récurrences linéaires combinées, de période `≈ 2^191`.
  C'est le générateur du VBA, transformé en normales par Box-Muller. L'implémentation
  vectorisée découpe la suite en blocs et calcule l'état de départ de chaque bloc par **saut
  en avant** (`A^L mod m`, exponentiation matricielle). On obtient exactement les mêmes
  tirages que la boucle séquentielle, ce que vérifie un test.

Graine 0 (ou `None`) signifie graine aléatoire, comme dans l'Excel. La graine effectivement
utilisée est renvoyée pour pouvoir reproduire le calcul.

## 10. Lire un z-score

`z = (MC − formule) / SE`. Si le moteur est sans biais, `z` suit une N(0, 1) : `|z| < 2` dans
95 % des cas et `|z| < 3` dans 99,7 % des cas. Un `|z|` de 5 ne vient pas du hasard : il
signale un biais ou un bug. C'était le cas de l'onglet européen sauvegardé, dont les résultats
Monte-Carlo dataient d'anciens paramètres (voir `ANALYSE_EXCEL.md`).

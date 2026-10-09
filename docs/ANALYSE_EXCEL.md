# Analyse du classeur Excel/VBA d'origine

Sources, lues en **lecture seule** avec `oletools/olevba` (code VBA) et `openpyxl`
(formules et valeurs) :

- `Pricer_Options_Rayane_ALKHALAF.xlsm` (version 2.0, 5 onglets) ;
- `Pricer_Options.xlsm` (version 2.1, 27/09/2026). C'est la version de référence : elle
  contient en plus l'onglet « Stratégies & Grecques » et une Notice mise à jour. Le code
  VBA et les quatre onglets de produits sont identiques à la version 2.0.

Le script `scripts/extraire_excel.py` reproduit cette extraction dans le
dossier `extraction/`, qui n'est pas versionné.

## 1. Structure générale

| Élément | Contenu |
|---|---|
| `Module1.bas` | Tout le code (≈ 1 600 lignes) : 7 macros publiques et leurs utilitaires privés |
| `ThisWorkbook`, `Feuil1` à `Feuil5` | Modules vides |
| Onglet « Options Européennes » | BSM et grecques en **formules de cellule**, Monte-Carlo par la macro `CalculerMC` |
| Onglet « Options Américaines » | BSM en formules, arbre CRR et Longstaff-Schwartz par `CalculerAmericaine` |
| Onglet « Options Asiatiques » | Asiatique géométrique exacte en formules, Monte-Carlo par `CalculerAsiatique` |
| Onglet « Options Barrières » | Reiner-Rubinstein en **formules de cellule**, Monte-Carlo par `CalculerBarriere` |
| Onglet « Stratégies & Grecques » (v2.1) | 16 stratégies + personnalisée, entièrement en **formules de cellule** (aucune macro) |
| Onglet « Notice » | Mode d'emploi, méthodes et limites |

Principes du VBA : les entrées sont lues en un bloc, tous les calculs se font en
mémoire, puis les résultats sont écrits en un seul bloc. Chaque estimateur
Monte-Carlo fait deux passes : la moyenne, puis les moments centrés, ce qui est
plus stable numériquement que la formule E[X²] − E[X]².

## 2. Macros et méthodes

### 2.1 Européennes : `CalculerMC`

- **Diffusion** : log-normale exacte en un seul pas,
  `S_T = S·exp((r − q − σ²/2)T + σ√T·Z)`.
- **Standard** : la moyenne actualisée de `max(S_T − K, 0)` sur les N tirages Z.
- **Antithétique** : à partir des **mêmes N tirages**, la moyenne de
  `½[f(Z) + f(−Z)]`.
- **Variable de contrôle** : `X = e^{−rT}·S_T` (avec Z seulement), dont l'espérance
  exacte est `S·e^{−qT}`. Le coefficient vaut `β* = Cov(Y, X)/Var(X)` (empirique,
  divisé par N − 1), l'estimateur vaut `Ȳ − β*(X̄ − S·e^{−qT})` et la variance
  résiduelle vaut `Var(Y) − β*·Cov(Y, X)`. Si `Var(X) ≤ (10⁻¹²·X̄)²` (cas σ = 0),
  alors β* = 0.
- **Sorties** : prix, SE = √(Var/N), IC 95 % = prix ± 1,96·SE, β*, corrélations,
  « gain de variance » `(SE_std/SE_cv)²` et « efficacité AV » `(SE_std/SE_av)²/2`
  (le facteur 1/2 compte le double coût en évaluations de payoff).
- **Z-score** (formule de cellule) : `(MC − BSM)/SE`, égal à 0 si SE = 0 (IFERROR).

### 2.2 Grecques et parité (formules de cellule, onglet européen)

| Grecque | Call | Put |
|---|---|---|
| Delta | e^{−qT}N(d₁) | e^{−qT}(N(d₁) − 1) |
| Gamma | e^{−qT}φ(d₁)/(Sσ√T) | identique |
| Vega (+1 point) | S e^{−qT}φ(d₁)√T / 100 | identique |
| Theta (par jour) | [−S e^{−qT}φ(d₁)σ/(2√T) − rK e^{−rT}N(d₂) + qS e^{−qT}N(d₁)] / 365 | [−S e^{−qT}φ(d₁)σ/(2√T) + rK e^{−rT}N(−d₂) − qS e^{−qT}N(−d₁)] / 365 |
| Rho (+1 point) | K T e^{−rT}N(d₂)/100 | −K T e^{−rT}N(−d₂)/100 |

Le contrôle de parité vaut `C − P − (S e^{−qT} − K e^{−rT})`. Si σ = 0, le prix
est la valeur intrinsèque forward `max(S e^{−qT} − K e^{−rT}, 0)` et d₁ vaut `#N/A`.

### 2.3 Américaines : `CalculerAmericaine`

- **Arbre CRR** : `u = e^{σ√Δt}`, `d = 1/u`, `p = (e^{(r−q)Δt} − d)/(u − d)`. Une
  seule induction arrière calcule les 4 prix (européen et américain, call et
  put). L'exercice anticipé se fait par `max(continuation, intrinsèque)`.
- **Variable de contrôle** : `Am_CV = Am_arbre + (BSM − Eu_arbre)`, la « valeur de
  référence » de la feuille.
- **Longstaff-Schwartz** :
  - `nEx` dates d'exercice équiréparties (Δt = T/nEx) ;
  - chemins **antithétiques** (lignes impaires Z, lignes paires −Z), nSim arrondi
    au nombre pair supérieur ;
  - régression **cubique** en `x = S/K − 1` (base 1, x, x², x³), sur les seuls
    chemins dans la monnaie, en remontant de `nEx − 1` à 1. La régression n'est
    faite que s'il y a au moins 8 chemins dans la monnaie (système 4×4 résolu
    par Gauss avec pivot partiel) ;
  - on exerce si `intrinsèque > continuation estimée`. Le cash-flow est ensuite
    actualisé depuis sa date d'exercice ;
  - SE calculée sur les **moyennes de paires** antithétiques (nSim/2 échantillons
    indépendants) ;
  - à t = 0 : prix = `max(intrinsèque(S₀), moyenne)`, et SE = 0 si l'on exerce
    immédiatement.
- **Indicateurs** : prime d'exercice anticipé = `Am_CV − BSM`, et écart LSM vs
  CRR+CV en nombre de SE.

### 2.4 Asiatiques : `CalculerAsiatique`

- Moyenne **arithmétique discrète** sur M fixings `t_i = i·T/M` (i = 1..M), strike
  fixe.
- Chemin Z et chemin antithétique −Z simulés ensemble. La moyenne géométrique
  est calculée sur le chemin Z.
- **Asiatique géométrique exacte** (variable de contrôle) :
  `μ_G = ln S + (r − q − σ²/2)·T(M+1)/(2M)`,
  `σ_G = σ·√(T(M+1)(2M+1)/(6M²))`,
  `Call = e^{−rT}[e^{μ_G + σ_G²/2}N(d₁) − K N(d₂)]`, avec
  `d₁ = (μ_G − ln K + σ_G²)/σ_G` et `d₂ = d₁ − σ_G`.
- Trois estimateurs : standard (chemin Z), antithétique (paire), et contrôle
  `Ȳ − β*(Ḡ − G_exact)`.
- **Contrôle du moteur** : `z = (Ḡ_MC − G_exact)/SE(G)`, avec |z| < 2 attendu.

### 2.5 Barrières : formules de cellule et `CalculerBarriere`

- **Formules fermées** de Reiner-Rubinstein (surveillance continue, sans rebate),
  écrites avec les blocs A, B, C, D (notation de Haug) :
  `x₁ = ln(S/K)/(σ√T) + (1+μ)σ√T`, `x₂ = ln(S/H)/(σ√T) + (1+μ)σ√T`,
  `y₁ = ln(H²/(SK))/(σ√T) + (1+μ)σ√T`, `y₂ = ln(H/S)/(σ√T) + (1+μ)σ√T`,
  avec `μ = (r − q − σ²/2)/σ²`.
- **Choix des combinaisons** (colonne F de la feuille) :

| Type | K ≥ H | K < H |
|---|---|---|
| Down-and-Out Call | A − C | B − D |
| Down-and-In Call | C | A − B + D |
| Up-and-Out Call | 0 | A − B + C − D |
| Up-and-In Call | A | B − C + D |
| Down-and-Out Put | A − B + C − D | 0 |
| Down-and-In Put | B − C + D | A |
| Up-and-Out Put | B − D | A − C |
| Up-and-In Put | A − B + D | C |

- **Spot au-delà de la barrière** (S ≤ H pour une barrière basse, S ≥ H pour une
  barrière haute) : Out = 0 et In = vanille.
- **Monte-Carlo** :
  - N = nombre de **paires antithétiques** (Z, −Z), toujours utilisées ;
  - `nMon` pas de Δt = T/nMon ;
  - mode continu (C11 = 0) : à chaque pas, la probabilité de survie est
    multipliée par la probabilité que le pont brownien ne franchisse pas la
    barrière, `1 − exp(−2(x−h)(y−h)/(σ²Δt))` en log-prix. Le chemin meurt si un
    point de la grille franchit la barrière ;
  - mode discret (C11 = 1) : seul le franchissement aux dates de la grille compte ;
  - In est calculée chemin par chemin comme `vanille − Out`, ce qui garantit
    la parité In + Out = vanille.
- **Contrôles** : parités `Out + In − vanille` (= 0) et z-scores MC vs formule.

### 2.6 Générateur : `RngSeed`, `RngU`, `GaussBM`

- **MRG32k3a** (L'Ecuyer 1999), en arithmétique `Double` exacte (tous les produits
  restent < 2⁵³) : `m₁ = 4294967087`, `m₂ = 4294944443`, `a₁₂ = 1403580`,
  `a₁₃ = −810728`, `a₂₁ = 527612`, `a₂₃ = −1370589`, et `U = ((p₁ − p₂) mod m₁)/(m₁+1)`,
  dans ]0, 1[ strict.
- **Initialisation** depuis une graine entière `b = graine mod (2³¹ − 1)` : six
  états dérivés de b par des congruences fixes, suivis de **100 tirages de
  chauffe**. Une graine de 0 donne un tirage aléatoire (horloge et `Rnd`).
- **Box-Muller** : `(U₁, U₂) → (√(−2 ln U₁)·cos 2πU₂, √(−2 ln U₁)·sin 2πU₂)`, la
  seconde normale étant mise en cache pour l'appel suivant.

### 2.7 Stratégies & Grecques (formules de cellule, version 2.1)

- **Paramètres** : S, r, q, σ et la maturité en **jours calendaires** (`T = jours/365`),
  avec par défaut S = 100, r = 5 %, q = 0, σ = 20 % et 100 jours.
- **Stratégie** (liste déroulante G6) : 16 stratégies prédéfinies, à l'achat et à la
  vente (call, put, bull/bear call spread, tunnel, stellage, strangle, papillon,
  condor), plus « Personnalisée » (1 à 4 jambes libres, avec par défaut un iron condor
  90/95/105/110). Les strikes prédéfinis valent `K0 + multiple × ΔK`, avec K0 = 100 et
  ΔK = 10 (table P7:AG23).
- **Position** : prime BSM et grecques (delta, gamma, vega +1 pt, theta /jour, rho
  +1 pt) par jambe, pondérées par `w = sens × quantité`, puis total.
- **Échéance** : le P&L est linéaire par morceaux. Il est évalué en 0 et à chaque
  strike ; les points morts sont trouvés par interpolation linéaire (exacte), plus un
  dernier au-delà du plus haut strike selon la pente `Σ w` des calls. Le gain ou la perte
  est illimité si cette pente est non nulle.
- **Scénario** (jours écoulés, σ', S') : contributions `Δ·ΔS`, `½Γ·ΔS²`,
  `Vega·Δσ(pts)` et `Θ·jours`, comparées au P&L réel (réévaluation BSM complète).
  L'écart correspond aux effets croisés.
- **Lecture des grecques** : cinq phrases générées par formule, avec des seuils relatifs
  à une option à la monnaie (gamma faible < ¼ du gamma ATM, vega marquée > ½ de la vega
  ATM).
- **Graphiques** : grille de 121 cours sur S·(1 ± amplitude). Le premier montre le P&L à
  l'échéance, à J0 et dans le scénario ; le second, la grecque choisie à J0 et dans le
  scénario.
- **Tableau comparatif** : coût net et grecques des 16 stratégies.
- **Valeurs (straddle par défaut)** : coût 8,3628572479 ; delta 0,145357629 ; gamma
  0,0749494896 ; vega 0,4106821348 ; theta −0,041913817 ; points morts 91,6371 et
  108,3629 ; scénario J+30 : P&L réel −1,3685070859, dont theta −1,25741451.

### 2.8 Trajectoires illustratives

`GenererTrajectoire`, `TrajectoireAsiatique` et `TrajectoireBarriere` utilisent
un schéma log-exact avec Δt = 1/252, plus un pas résiduel pour finir exactement
à T. Le graphique de l'asiatique trace la moyenne courante des fixings, celui
de la barrière indique la date du premier franchissement (contrôle journalier).

## 3. Contrôles de validation reproduits

| Contrôle | Message VBA (repris en Python) |
|---|---|
| Cellule en erreur ou non numérique | « La cellule … doit contenir un nombre. » |
| S ≤ 0 / K ≤ 0 | « S doit être strictement positif (S > 0). » |
| σ < 0 (européennes), σ ≤ 0 (autres onglets) | « La volatilité … » |
| T ≤ 0, T > 50 | « La maturité doit être strictement positive » / « T doit être <= 50 ans » |
| Domaine numérique | `|ln S| + |(r−q−σ²/2)T| + 7σ√T > 700`, ou `|rT|`/`|qT| > 700` |
| N européennes | entier de 1 000 à 10 000 000 |
| Arbre | pas de 50 à 5 000 ; `σ√(T·n) + |ln S| ≤ 700` ; p ∈ ]0, 1[ |
| LSM | simulations de 1 000 à 200 000, dates de 10 à 500, produit ≤ 5 000 000 |
| Asiatiques | fixings de 1 à 1 000, simulations de 1 000 à 1 000 000, produit ≤ 50 000 000 |
| Barrières | H > 0, pas de 1 à 10 000, mode ∈ {0, 1}, simulations de 1 000 à 1 000 000, produit ≤ 50 000 000 |

## 4. Valeurs stockées dans le classeur (dernière exécution)

| Onglet | Paramètres | Valeurs |
|---|---|---|
| Asiatiques | S=K=100, r=5 %, q=2 %, σ=20 %, T=1, M=12, N=50 000 | BSM Call 9,227006 ; Put 6,330081 ; géométrique Call 5,327706 ; Put 4,088834 ; arithmétique CV Call 5,519595 (SE 0,00098) ; Put 3,958845 |
| Américaines | S=K=40, r=6 %, q=0, σ=20 %, T=1, 1 000 pas, 20 000 sim., 50 dates | Eu arbre Put 2,065596 ; Am arbre Put 2,319278 ; CRR+CV Put **2,320083** ; LSM Put 2,310722 (SE 0,0118) ; Call Am = Call Eu = 4,395 |
| Barrières | S=K=100, H=90, r=5 %, q=2 %, σ=25 %, T=1 | DOC **8,138811** ; DIC **2,984951** ; UOC 0 ; UIC 11,123762 ; DOP 0,086816 ; DIP 8,140021 ; UOP 0 ; UIP 8,226837 ; parités = 0 |
| Européennes | S=K=100, **r=20 %**, q=0, **σ=52 %**, T=1, N=20 000 | BSM Call 29,044883 ; Put 10,917958 ; grecques en formules |

## 5. Points d'attention relevés

1. **Onglet européen désynchronisé.** Les entrées affichées (r = 20 %,
   σ = 52 %) ne correspondent pas aux résultats Monte-Carlo stockés : les
   z-scores valent −1,7, −3,7 et −5,6, ce qui est impossible statistiquement.
   Les formules BSM se recalculent en direct, mais pas la macro. Les macros
   n'ont donc pas été relancées après la dernière modification. Les valeurs par
   défaut de référence (S=K=100, r=5 %, q=2 %, σ=20 %, N=100 000) sont celles
   de `InitialiserPricer`. Ce sont elles qui sont reprises en Python.
2. **Variable de contrôle S_T et parité.** Avec ce contrôle, `C − P` est une
   fonction linéaire de X : l'estimateur de C − P est donc exact. Cela explique
   pourquoi la SE et le z-score sont identiques pour le call et pour le put
   dans la feuille (0,083314 et −5,5587).
3. **Notice vs code (barrières).** La notice indique qu'en mode continu la
   simulation va « directement jusqu'à maturité », mais le code utilise les
   `nMon` pas dans les deux modes. Comme la correction de pont brownien est
   exacte pour un GBM à paramètres constants, l'espérance ne dépend pas du
   nombre de pas (seule la variance change). Le comportement du code est
   conservé en Python.
4. **Seuil du z-score.** L'Excel indique « |z| < 2 attendu ». Ce seuil est dépassé
   dans environ 5 % des cas. Les tests Python utilisent |z| < 3, avec une graine
   fixée.
5. **Fonction de répartition.** Le VBA utilise l'algorithme de Hart (1968), et
   la feuille utilise `NORM.S.DIST`. Python utilise `scipy.special.ndtr` (précision
   machine).
6. **Classeur non publié.** Les classeurs Excel ne sont pas inclus dans ce dépôt
   (leur projet VBA contient des métadonnées locales). Les valeurs de référence
   utilisées par les tests en sont extraites dans `tests/references.py`.

## 6. Correspondance Excel → Python

| VBA / feuille | Python |
|---|---|
| `BSMPrix`, cellules C12:C16 | `pricer.bsm.prix_bsm`, `pricer.bsm.parite_call_put` |
| Grecques I9:J13 | `pricer.greeks.grecques_bsm` |
| `CalculerMC` | `pricer.monte_carlo.mc_europeenne` |
| `ArbreCRR`, `ProbaCRROk` | `pricer.trees.arbre_crr`, `pricer.trees.americaine_crr_controle` |
| `SimulerCheminsAV`, `PrixLSM`, `Resoudre4` | `pricer.lsm.prix_lsm` (moindres carrés NumPy) |
| `AsiatGeo`, `CalculerAsiatique` | `pricer.asian.asiatique_geometrique`, `pricer.asian.mc_asiatique` |
| Formules F4:F13, C16:C37, `CalculerBarriere` | `pricer.barrier.prix_barriere`, `pricer.barrier.mc_barriere` |
| `RngSeed`, `RngU`, `GaussBM` | `pricer.rng.MRG32k3a` (vectorisé par saut en avant) |
| `LireInputs`, `ValiderMarche`, `ValiderEntier` | `pricer.validation` |
| `GenererTrajectoire`, `Trajectoire*` | `pricer.monte_carlo.simuler_trajectoires`, `grille_journaliere` |
| Onglet « Stratégies & Grecques » | `pricer.strategies` (`analyser_position`, `scenario_pnl`, `profils`, `tableau_comparatif`, `lecture_grecques`) |

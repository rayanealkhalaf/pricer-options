"""Interface Streamlit du pricer d'options.

Lancement : ``streamlit run app.py``

Un onglet par produit (comme les onglets du classeur Excel). Les paramètres
sont dans la barre latérale, avec les mêmes valeurs par défaut que l'Excel.
La présentation (styles, cartes, graphiques) est dans le paquet ``interface``.
"""

from __future__ import annotations

import math

import numpy as np
import streamlit as st

from interface.design import (
    LOGO_ICONE,
    badge_z,
    entete,
    injecter_styles,
    kpis,
    pied_de_page,
    section,
    titre_graphique,
    titre_sidebar,
)
from interface.graphiques import (
    AMBRE,
    CYAN,
    DISCRET,
    PRIMAIRE,
    ROSE,
    TEXTE,
    VERT,
    afficher,
    courbes,
    faisceau,
    regle_h,
    regles_v,
)
from pricer.asian import asiatique_geometrique, mc_asiatique
from pricer.barrier import (
    NOMS_BARRIERE,
    TYPES_BARRIERE,
    barriere_ajustee_bgk,
    mc_barriere,
    parites_barriere,
    prix_barriere,
    prix_barrieres,
)
from pricer.bsm import parite_call_put, prix_bsm, volatilite_implicite
from pricer.greeks import grecques_bsm
from pricer.lsm import prix_lsm
from pricer.monte_carlo import (
    ResultatsMC,
    convergence_europeenne,
    grille_journaliere,
    mc_europeenne,
    simuler_trajectoires,
)
from pricer.strategies import (
    PERSONNALISEE,
    STRATEGIES,
    VUE_PERSONNALISEE,
    Jambe,
    analyser_position,
    jambes_strategie,
    lecture_grecques,
    profils,
    scenario_pnl,
    tableau_comparatif,
)
from pricer.trees import americaine_crr_controle, arbre_crr

st.set_page_config(
    page_title="pricer/opt · Valorisation d'options",
    page_icon=str(LOGO_ICONE),
    layout="wide",
)
injecter_styles()

NOMS_METHODES = {
    "standard": "MC standard",
    "antithetique": "Antithétique (Z, −Z)",
    "controle": "Variable de contrôle (β*)",
    "continue": "MC pont brownien",
    "discrete": "MC discret",
}
FORMAT_6 = st.column_config.NumberColumn(format="%.6f")
FORMAT_2 = st.column_config.NumberColumn(format="%+.2f")
COULEURS_MC = {"standard": PRIMAIRE, "antithetique": CYAN, "controle": AMBRE}


# ---------------------------------------------------------------------------
# Barre latérale : paramètres (valeurs par défaut de l'Excel)
# ---------------------------------------------------------------------------


AIDE = {
    "S": "Cours actuel du sous-jacent (action, indice…).",
    "K": "Prix d'exercice : le prix auquel l'option permet d'acheter (call) ou de vendre (put).",
    "r": "Taux sans risque continu, en % par an.",
    "q": "Rendement du dividende continu, en % par an (0 si aucun dividende).",
    "vol": "Volatilité annuelle du sous-jacent : l'amplitude moyenne de ses variations.",
    "T": "Durée de vie restante de l'option, en années (0,5 = six mois).",
}


def saisie_marche(
    cle: str, S: float, K: float, r: float, q: float, vol: float, T: float, vol_min: float = 0.0001
) -> dict[str, float]:
    """Champs S, K, r, q, σ, T d'un onglet (taux et volatilité saisis en %)."""
    return {
        "S": st.number_input("Spot S", 0.01, 1e6, S, key=f"{cle}_S", help=AIDE["S"]),
        "K": st.number_input("Strike K", 0.01, 1e6, K, key=f"{cle}_K", help=AIDE["K"]),
        "r": st.number_input(
            "Taux sans risque r (%)", -20.0, 50.0, r * 100, key=f"{cle}_r", help=AIDE["r"]
        )
        / 100,
        "q": st.number_input(
            "Dividende q (%)", -20.0, 50.0, q * 100, key=f"{cle}_q", help=AIDE["q"]
        )
        / 100,
        "vol": st.number_input(
            "Volatilité σ (%)", vol_min, 300.0, vol * 100, key=f"{cle}_v", help=AIDE["vol"]
        )
        / 100,
        "T": st.number_input("Maturité T (années)", 0.01, 50.0, T, key=f"{cle}_T", help=AIDE["T"]),
    }


with st.sidebar:
    if st.button(
        "Réinitialiser les paramètres",
        icon=":material/restart_alt:",
        width="stretch",
        help="Revenir aux valeurs par défaut du classeur Excel.",
    ):
        st.session_state.clear()
        st.rerun()
    titre_sidebar("Simulation")
    methode_rng = st.selectbox(
        "Générateur aléatoire",
        ["pcg64", "mrg32k3a"],
        format_func=lambda m: {"pcg64": "NumPy PCG64", "mrg32k3a": "MRG32k3a (identique au VBA)"}[
            m
        ],
    )
    graine = int(st.number_input("Graine (0 = aléatoire)", 0, 2_147_483_646, 0, step=1))

    titre_sidebar("Paramètres par produit")
    with st.expander("Européennes", expanded=True, icon=":material/show_chart:"):
        p_eu = saisie_marche("eu", 100.0, 100.0, 0.05, 0.02, 0.20, 1.0, vol_min=0.0)
        n_eu = int(
            st.number_input(
                "Simulations N",
                1_000,
                2_000_000,
                100_000,
                step=10_000,
                help="Plafonné à 2 millions en ligne pour préserver la mémoire du serveur.",
            )
        )
    with st.expander("Américaines", icon=":material/account_tree:"):
        p_am = saisie_marche("am", 40.0, 40.0, 0.06, 0.0, 0.20, 1.0)
        n_arbre = int(st.number_input("Pas de l'arbre (50 à 5 000)", 50, 5_000, 1_000, step=50))
        n_lsm = int(st.number_input("Simulations LSM", 1_000, 200_000, 20_000, step=1_000))
        n_dates = int(st.number_input("Dates d'exercice LSM", 10, 500, 50, step=5))
    with st.expander("Asiatiques", icon=":material/functions:"):
        p_as = saisie_marche("as", 100.0, 100.0, 0.05, 0.02, 0.20, 1.0)
        n_fix = int(st.number_input("Fixings M (1 à 1 000)", 1, 1_000, 12))
        n_as = int(st.number_input("Simulations N ", 1_000, 1_000_000, 50_000, step=10_000))
    with st.expander("Barrières", icon=":material/vertical_align_bottom:"):
        p_ba = saisie_marche("ba", 100.0, 100.0, 0.05, 0.02, 0.25, 1.0)
        H = st.number_input("Barrière H", 0.01, 1e6, 90.0)
        n_pas_ba = int(st.number_input("Pas de surveillance", 1, 10_000, 252))
        mode_ba = st.radio(
            "Surveillance MC",
            ["continue", "discrete"],
            format_func=lambda m: "Continue (pont brownien)" if m == "continue" else "Discrète",
        )
        n_ba = int(st.number_input("Paires antithétiques N", 1_000, 1_000_000, 50_000, step=10_000))
    with st.expander("Stratégies & grecques", icon=":material/stacked_line_chart:"):
        st_S = st.number_input("Spot S", 0.01, 1e6, 100.0, key="st_S")
        st_r = st.number_input("Taux r (%)", -20.0, 50.0, 5.0, key="st_r") / 100
        st_q = st.number_input("Dividende q (%)", -20.0, 50.0, 0.0, key="st_q") / 100
        st_vol = st.number_input("Volatilité σ (%)", 1.0, 300.0, 20.0, key="st_v") / 100
        st_jours = st.number_input("Maturité (jours calendaires)", 1, 18_250, 100, key="st_j")
        st_nom = st.selectbox("Stratégie", [*STRATEGIES, PERSONNALISEE], index=8, key="st_nom")
        st_k0 = st.number_input("Strike central K0", 0.01, 1e6, 100.0, key="st_k0")
        st_dk = st.number_input("Écart entre strikes ΔK", 0.0, 1e6, 10.0, key="st_dk")
        st.markdown("**Scénario**")
        st_ecoules = st.number_input("Jours écoulés", 0, 18_250, 30, key="st_e")
        st_vol_sc = st.number_input("Volatilité σ' du scénario (%)", 1.0, 300.0, 20.0) / 100
        st_spot_sc = st.number_input("Spot S' du scénario", 0.01, 1e6, 100.0)
        st_grecque = st.selectbox("Grecque du graphique", ["delta", "gamma", "vega", "theta"], 1)
        st_ampl = st.number_input("Amplitude du graphique (± % du spot)", 5.0, 95.0, 30.0) / 100


# ---------------------------------------------------------------------------
# Calculs mis en cache (relancés seulement si les paramètres changent)
# ---------------------------------------------------------------------------

CACHE = 64  # combinaisons de paramètres gardées en mémoire par calcul
calcul_mc_eu = st.cache_data(max_entries=CACHE)(mc_europeenne)
calcul_convergence_eu = st.cache_data(max_entries=CACHE)(convergence_europeenne)
calcul_americaine = st.cache_data(max_entries=CACHE)(americaine_crr_controle)
calcul_lsm = st.cache_data(max_entries=CACHE)(prix_lsm)
calcul_asiatique = st.cache_data(max_entries=CACHE)(mc_asiatique)
calcul_barriere = st.cache_data(max_entries=CACHE)(mc_barriere)


@st.cache_data(max_entries=CACHE)
def convergence_arbre(S, K, r, q, vol, T, pas):
    """Prix (américain, européen) du put pour chaque nombre de pas de l'arbre."""
    arbres = [arbre_crr(S, K, r, q, vol, T, n_pas=int(n)) for n in pas]
    return [a.amer_put for a in arbres], [a.euro_put for a in arbres]


@st.cache_data(max_entries=CACHE)
def trajectoires(S, r, q, vol, T, n, graine, gen):
    """Trajectoires journalières illustratives (pas de 1/252)."""
    temps = grille_journaliere(T)
    return temps, simuler_trajectoires(S, r, q, vol, temps, n, graine or None, gen)


def milliers(x: float) -> str:
    """Entier arrondi avec espace comme séparateur de milliers (100 000)."""
    return f"{x:,.0f}".replace(",", " ")


def statut(z: float) -> str:
    """Verdict lisible d'un z-score (|z| < 2 attendu dans 95 % des cas)."""
    if math.isnan(z):
        return "—"
    return "✓ conforme" if abs(z) < 2 else "△ limite" if abs(z) < 3 else "✕ écart"


def tableau_mc(res: ResultatsMC, options: dict[str, str]) -> list[dict]:
    """Lignes « option / méthode / prix / SE / IC / z » pour l'affichage."""
    lignes = []
    for cle, libelle in options.items():
        ref = res.references.get(cle)
        for methode, est in res.estimations[cle].items():
            z = est.z_score(ref) if ref is not None else float("nan")
            lignes.append(
                {
                    "Option": libelle,
                    "Méthode": NOMS_METHODES.get(methode, methode),
                    "Prix MC": est.prix,
                    "SE": est.se,
                    "IC 95 % bas": est.ic_bas,
                    "IC 95 % haut": est.ic_haut,
                    "Formule fermée": ref if ref is not None else float("nan"),
                    "z-score": z,
                    "Test": statut(z),
                }
            )
    return lignes


def afficher_tableau(lignes: list[dict]) -> None:
    # Sans formule fermée (asiatique arithmétique), les colonnes de test sont retirées.
    if all(math.isnan(li["Formule fermée"]) for li in lignes if "Formule fermée" in li):
        lignes = [
            {k: v for k, v in li.items() if k not in ("Formule fermée", "z-score", "Test")}
            for li in lignes
        ]
    config = {
        k: FORMAT_6 for k in ("Prix MC", "SE", "IC 95 % bas", "IC 95 % haut", "Formule fermée")
    }
    config["z-score"] = FORMAT_2
    st.dataframe(lignes, column_config=config, hide_index=True)


def erreur(e: Exception) -> None:
    st.error(f"Paramètres invalides : {e}", icon=":material/error:")


entete()
onglets = st.tabs(
    [
        ":material/show_chart: Européennes",
        ":material/account_tree: Américaines",
        ":material/functions: Asiatiques",
        ":material/vertical_align_bottom: Barrières",
        ":material/stacked_line_chart: Stratégies & Grecques",
    ]
)

# ---------------------------------------------------------------------------
# Onglet 1 : européennes
# ---------------------------------------------------------------------------
with onglets[0]:
    try:
        bsm_c, bsm_p = prix_bsm(**p_eu, option="call"), prix_bsm(**p_eu, option="put")
        res = calcul_mc_eu(**p_eu, n_sim=n_eu, graine=graine or None, generateur=methode_rng)
        cv_c = res.estimations["call"]["controle"]
        kpis(
            [
                ("Call · Black-Scholes-Merton", f"{bsm_c:.6f}", "", True),
                ("Put · Black-Scholes-Merton", f"{bsm_p:.6f}"),
                ("Call · Monte-Carlo contrôlé", f"{cv_c.prix:.6f}", badge_z(cv_c.z_score(bsm_c))),
                ("Parité call-put", f"{parite_call_put(**p_eu):.1e}"),
            ]
        )

        section("01", "Grecques")
        if p_eu["vol"] > 0:
            gc, gp = grecques_bsm(**p_eu, option="call"), grecques_bsm(**p_eu, option="put")
            st.dataframe(
                [
                    {"Grecque": nom, "Call": gc.en_dict()[cle], "Put": gp.en_dict()[cle]}
                    for cle, nom in [
                        ("delta", "Delta"),
                        ("gamma", "Gamma"),
                        ("vega", "Vega (+1 pt de vol)"),
                        ("theta", "Theta (par jour)"),
                        ("rho", "Rho (+1 pt de taux)"),
                    ]
                ],
                column_config={"Call": FORMAT_6, "Put": FORMAT_6},
                hide_index=True,
            )
        else:
            st.info(
                "Grecques non définies pour σ = 0 (d₁ = #N/A dans l'Excel).", icon=":material/info:"
            )

        section("02", "Volatilité implicite")
        c_opt, c_prix = st.columns([1, 2])
        type_iv = c_opt.segmented_control(
            "Option cotée", ["call", "put"], default="call", format_func=str.capitalize
        )
        type_iv = type_iv or "call"
        prix_ref = bsm_c if type_iv == "call" else bsm_p
        prix_marche = c_prix.number_input(
            "Prix de marché observé",
            0.0001,
            1e6,
            max(round(prix_ref * 1.08, 2), 0.01),
            step=0.05,
            key=f"prix_marche_{type_iv}",
            help="Par défaut : 8 % au-dessus du prix BSM (volatilité implicite plus élevée).",
        )
        marche_iv = {k: v for k, v in p_eu.items() if k != "vol"}
        try:
            sigma_iv = volatilite_implicite(prix_marche, **marche_iv, option=type_iv)
            vega_iv = grecques_bsm(**marche_iv, vol=sigma_iv, option=type_iv).vega
            kpis(
                [
                    ("Volatilité implicite", f"{sigma_iv:.4%}", "", True),
                    ("Écart avec σ saisie", f"{(sigma_iv - p_eu['vol']) * 100:+.2f} pts"),
                    ("Vega au σ implicite", f"{vega_iv:.4f}"),
                    (
                        "Contrôle",
                        f"{prix_bsm(**marche_iv, vol=sigma_iv, option=type_iv) - prix_marche:.1e}",
                    ),
                ]
            )
            titre_graphique("Prix BSM selon la volatilité")
            grille = np.linspace(0.01, max(1.0, 1.5 * sigma_iv), 200)
            afficher(
                courbes(
                    {
                        f"Prix BSM du {type_iv}": (
                            grille * 100,
                            [prix_bsm(**marche_iv, vol=v, option=type_iv) for v in grille],
                        ),
                        "Prix observé": (grille[[0, -1]] * 100, [prix_marche] * 2),
                    },
                    titre_x="Volatilité σ (%)",
                    titre_y="Prix",
                    couleurs=[PRIMAIRE, AMBRE],
                    pointilles=["Prix observé"],
                    couches=[regles_v([sigma_iv * 100], VERT)],
                    hauteur=260,
                )
            )
        except ValueError as e:
            st.warning(str(e), icon=":material/warning:")

        section("03", "Monte-Carlo")
        afficher_tableau(tableau_mc(res, {"call": "Call", "put": "Put"}))
        d = res.diagnostics
        kpis(
            [
                ("β* call / put", f"{d['beta_call']:.4f} / {d['beta_put']:.4f}"),
                ("Corrélation avec S_T", f"{d['corr_call']:.3f} / {d['corr_put']:.3f}"),
                ("Gain de variance · contrôle", f"× {d['gain_cv_call']:.2f}"),
                ("Efficacité · antithétique", f"× {d['efficacite_av_call']:.2f}"),
            ]
        )

        g1, g2 = st.columns(2)
        with g1:
            titre_graphique("Trajectoires simulées")
            temps, chemins = trajectoires(
                p_eu["S"], p_eu["r"], p_eu["q"], p_eu["vol"], p_eu["T"], 25, graine, methode_rng
            )
            afficher(faisceau(temps, chemins, regles=[(p_eu["K"], "Strike K", TEXTE)]))
        with g2:
            titre_graphique("Convergence du call")
            tailles = [1_000, 2_000, 5_000, 10_000, 20_000, 50_000, 100_000, 200_000]
            conv = calcul_convergence_eu(
                **p_eu, tailles=tailles, option="call", graine=graine or 42, generateur=methode_rng
            )
            methodes = ("standard", "antithetique", "controle")
            series = {NOMS_METHODES[m]: (conv["n"], conv[f"prix_{m}"]) for m in methodes}
            series["BSM (exact)"] = (conv["n"], np.full(len(conv["n"]), bsm_c))
            bandes = {
                NOMS_METHODES[m]: (
                    conv["n"],
                    conv[f"prix_{m}"] - 1.96 * conv[f"se_{m}"],
                    conv[f"prix_{m}"] + 1.96 * conv[f"se_{m}"],
                )
                for m in methodes
            }
            afficher(
                courbes(
                    series,
                    titre_x="Nombre de simulations N",
                    titre_y="Prix du call",
                    couleurs=[*COULEURS_MC.values(), TEXTE],
                    pointilles=["BSM (exact)"],
                    log_x=True,
                    points=True,
                    bandes=bandes,
                )
            )
    except ValueError as e:
        erreur(e)

# ---------------------------------------------------------------------------
# Onglet 2 : américaines
# ---------------------------------------------------------------------------
with onglets[1]:
    try:
        am = calcul_americaine(**p_am, n_pas=n_arbre)
        lsm_c = calcul_lsm(
            **p_am,
            option="call",
            n_sim=n_lsm,
            n_dates=n_dates,
            graine=graine or None,
            generateur=methode_rng,
        )
        # Même graine que le call : le put est évalué sur les mêmes chemins (comme le VBA).
        lsm_p = calcul_lsm(
            **p_am,
            option="put",
            n_sim=n_lsm,
            n_dates=n_dates,
            graine=lsm_c.graine,
            generateur=methode_rng,
        )
        kpis(
            [
                ("Put américain · CRR + contrôle", f"{am.cv_put:.6f}", "", True),
                (
                    "Put américain · Longstaff-Schwartz",
                    f"{lsm_p.prix:.6f}",
                    badge_z(lsm_p.z_score(am.cv_put)),
                ),
                ("Prime d'exercice anticipé · put", f"{am.prime_put:.6f}"),
                ("Prime d'exercice anticipé · call", f"{am.prime_call:.6f}"),
            ]
        )

        section("01", "Prix")
        lignes = [
            ("Européenne BSM (exacte)", am.bsm_call, am.bsm_put),
            ("Européenne arbre CRR", am.arbre.euro_call, am.arbre.euro_put),
            ("Américaine arbre CRR", am.arbre.amer_call, am.arbre.amer_put),
            ("Américaine CRR + variable de contrôle (référence)", am.cv_call, am.cv_put),
            ("Longstaff-Schwartz", lsm_c.prix, lsm_p.prix),
            ("  SE LSM", lsm_c.se, lsm_p.se),
            ("  IC 95 % bas", lsm_c.ic_bas, lsm_p.ic_bas),
            ("  IC 95 % haut", lsm_c.ic_haut, lsm_p.ic_haut),
        ]
        st.dataframe(
            [{"Méthode": m, "Call": c, "Put": p} for m, c, p in lignes],
            column_config={"Call": FORMAT_6, "Put": FORMAT_6},
            hide_index=True,
        )

        g1, g2 = st.columns(2)
        with g1:
            titre_graphique("Convergence de l'arbre")
            pas = (50, 100, 200, 300, 500, 750, 1_000, 1_500, 2_000)
            amer, euro = map(np.array, convergence_arbre(**p_am, pas=pas))
            afficher(
                courbes(
                    {
                        "Américaine arbre": (pas, amer),
                        "Américaine CRR + contrôle": (pas, amer + am.bsm_put - euro),
                        "Européenne arbre": (pas, euro),
                        "Européenne BSM": (pas, np.full(len(pas), am.bsm_put)),
                    },
                    titre_x="Nombre de pas n",
                    titre_y="Prix du put",
                    couleurs=[PRIMAIRE, AMBRE, CYAN, TEXTE],
                    pointilles=["Européenne BSM"],
                    points=True,
                )
            )
        with g2:
            titre_graphique("Frontière d'exercice")
            afficher(
                courbes(
                    {
                        "Spot critique S*(t)": (lsm_p.temps, lsm_p.frontiere),
                        "Strike K": (lsm_p.temps, np.full(len(lsm_p.temps), p_am["K"])),
                    },
                    titre_x="Date d'exercice t",
                    titre_y="Spot critique S*(t)",
                    couleurs=[ROSE, TEXTE],
                    pointilles=["Strike K"],
                    points=True,
                    format_y=".3f",
                )
            )
    except ValueError as e:
        erreur(e)

# ---------------------------------------------------------------------------
# Onglet 3 : asiatiques
# ---------------------------------------------------------------------------
with onglets[2]:
    try:
        geo_c = asiatique_geometrique(**p_as, n_fixings=n_fix, option="call")
        geo_p = asiatique_geometrique(**p_as, n_fixings=n_fix, option="put")
        res = calcul_asiatique(
            **p_as, n_fixings=n_fix, n_sim=n_as, graine=graine or None, generateur=methode_rng
        )
        d = res.diagnostics
        kpis(
            [
                (
                    "Arithmétique · call",
                    f"{res.estimations['call']['controle'].prix:.6f}",
                    "",
                    True,
                ),
                ("Arithmétique · put", f"{res.estimations['put']['controle'].prix:.6f}"),
                ("Géométrique exacte · call", f"{geo_c:.6f}"),
                ("Géométrique exacte · put", f"{geo_p:.6f}"),
            ]
        )

        section("01", "Moyenne arithmétique")
        afficher_tableau(tableau_mc(res, {"call": "Call", "put": "Put"}))
        section("02", "Contrôle : moyenne géométrique")
        afficher_tableau(
            tableau_mc(res, {"geo_call": "Call géométrique", "geo_put": "Put géométrique"})
        )
        kpis(
            [
                ("Corrélation arithm. / géom.", f"{d['corr_call']:.5f}"),
                ("Gain de variance · call", f"× {milliers(d['gain_cv_call'])}"),
                ("Gain de variance · put", f"× {milliers(d['gain_cv_put'])}"),
                ("BSM européen · call", f"{d['bsm_call']:.6f}"),
            ]
        )

        g1, g2 = st.columns(2)
        with g1:
            titre_graphique("Trajectoire et moyenne des fixings")
            spf = max(1, round(p_as["T"] / n_fix * 252))
            spf = max(1, min(spf, 100_000 // n_fix))
            temps = np.linspace(0, p_as["T"], spf * n_fix + 1)
            chemin = simuler_trajectoires(
                p_as["S"], p_as["r"], p_as["q"], p_as["vol"], temps, 1, graine or None, methode_rng
            )[0]
            fixings = chemin[spf::spf]
            t_fix = temps[spf::spf]
            afficher(
                courbes(
                    {
                        "S(t)": (temps, chemin),
                        "Moyenne des fixings": (
                            t_fix,
                            np.cumsum(fixings) / np.arange(1, n_fix + 1),
                        ),
                        "Strike K": (temps[[0, -1]], [p_as["K"]] * 2),
                    },
                    titre_x="Temps (années)",
                    titre_y="Cours",
                    couleurs=[PRIMAIRE, AMBRE, TEXTE],
                    pointilles=["Strike K"],
                    escalier=["Moyenne des fixings"],
                    format_y=".2f",
                )
            )
        with g2:
            titre_graphique("Erreur standard selon N")
            tailles = [1_000, 2_000, 5_000, 10_000, 20_000, 50_000]
            series = {m: [] for m in ("standard", "antithetique", "controle")}
            for n in tailles:
                r_n = calcul_asiatique(
                    **p_as, n_fixings=n_fix, n_sim=n, graine=graine or 42, generateur=methode_rng
                )
                for m in series:
                    series[m].append(r_n.estimations["call"][m].se)
            afficher(
                courbes(
                    {NOMS_METHODES[m]: (tailles, se) for m, se in series.items()},
                    titre_x="Nombre de simulations N",
                    titre_y="SE du call",
                    couleurs=list(COULEURS_MC.values()),
                    log_x=True,
                    log_y=True,
                    points=True,
                    format_y=".2e",
                )
            )
    except ValueError as e:
        erreur(e)

# ---------------------------------------------------------------------------
# Onglet 4 : barrières
# ---------------------------------------------------------------------------
with onglets[3]:
    try:
        fermees = prix_barrieres(**p_ba, H=H)
        res = calcul_barriere(
            **p_ba,
            H=H,
            n_pas=n_pas_ba,
            surveillance=mode_ba,
            n_sim=n_ba,
            graine=graine or None,
            generateur=methode_rng,
        )
        doc = res.estimations["DOC"][mode_ba]
        dic = res.estimations["DIC"][mode_ba]
        kpis(
            [
                ("Down-and-Out Call · formule", f"{fermees['DOC']:.6f}", "", True),
                ("Down-and-Out Call · MC", f"{doc.prix:.6f}", badge_z(doc.z_score(fermees["DOC"]))),
                ("Down-and-In Call · formule", f"{fermees['DIC']:.6f}"),
                ("Down-and-In Call · MC", f"{dic.prix:.6f}", badge_z(dic.z_score(fermees["DIC"]))),
            ]
        )

        section("01", "Les huit barrières")
        lignes = []
        for code in TYPES_BARRIERE:
            est = res.estimations[code][mode_ba]
            z = est.z_score(fermees[code])
            lignes.append(
                {
                    "Type": NOMS_BARRIERE[code],
                    "Formule fermée": fermees[code],
                    "Prix MC": est.prix,
                    "SE": est.se,
                    "IC 95 % bas": est.ic_bas,
                    "IC 95 % haut": est.ic_haut,
                    "z-score": z,
                    "Test": statut(z) if mode_ba == "continue" else "—",
                }
            )
        afficher_tableau(lignes)
        if mode_ba == "discrete":
            st.info(
                "Surveillance discrète : les options Out valent plus que la formule continue "
                "(c'est normal). Correction de Broadie-Glasserman-Kou : barrière décalée à "
                f"{barriere_ajustee_bgk(H, p_ba['S'], p_ba['vol'], p_ba['T'], n_pas_ba):.4f}, "
                f"DOC corrigée = {res.diagnostics.get('bgk_DOC', float('nan')):.6f}.",
                icon=":material/info:",
            )

        section("02", "Parité In + Out − vanille")
        par_f = parites_barriere(fermees)
        par_mc = parites_barriere({c: res.estimations[c][mode_ba].prix for c in fermees})
        st.dataframe(
            [{"Famille": f, "Formule fermée": par_f[f], "Monte-Carlo": par_mc[f]} for f in par_f],
            hide_index=True,
            column_config={
                "Formule fermée": st.column_config.NumberColumn(format="%.2e"),
                "Monte-Carlo": st.column_config.NumberColumn(format="%.2e"),
            },
        )

        g1, g2 = st.columns(2)
        with g1:
            titre_graphique("Trajectoires et barrière")
            temps, chemins = trajectoires(
                p_ba["S"], p_ba["r"], p_ba["q"], p_ba["vol"], p_ba["T"], 15, graine, methode_rng
            )
            basse = p_ba["S"] > H
            touche = (chemins <= H) if basse else (chemins >= H)
            afficher(
                faisceau(
                    temps,
                    chemins,
                    touche=touche,
                    regles=[(H, f"Barrière H = {H:g}", ROSE), (p_ba["K"], "Strike K", TEXTE)],
                )
            )
        with g2:
            titre_graphique("Down-and-Out Call selon le nombre de pas")
            pas = np.array([4, 12, 52, 252])
            series, barres = {}, {}
            for mode in ("continue", "discrete"):
                val = [
                    calcul_barriere(
                        **p_ba,
                        H=H,
                        n_pas=int(m),
                        surveillance=mode,
                        n_sim=20_000,
                        graine=graine or 42,
                        generateur=methode_rng,
                    ).estimations["DOC"][mode]
                    for m in pas
                ]
                prix = np.array([v.prix for v in val])
                se = np.array([v.se for v in val])
                series[NOMS_METHODES[mode]] = (pas, prix)
                barres[NOMS_METHODES[mode]] = (pas, prix - 1.96 * se, prix + 1.96 * se)
            series["Formule + correction BGK"] = (
                pas,
                [
                    prix_barriere(
                        **p_ba,
                        H=barriere_ajustee_bgk(H, p_ba["S"], p_ba["vol"], p_ba["T"], int(m)),
                        type_barriere="DOC",
                    )
                    for m in pas
                ],
            )
            series["Formule (continue)"] = (pas, np.full(len(pas), fermees["DOC"]))
            afficher(
                courbes(
                    series,
                    titre_x="Nombre de pas de surveillance",
                    titre_y="Prix DOC",
                    couleurs=[VERT, PRIMAIRE, AMBRE, TEXTE],
                    pointilles=["Formule + correction BGK", "Formule (continue)"],
                    log_x=True,
                    points=True,
                    barres=barres,
                )
            )
    except ValueError as e:
        erreur(e)

# ---------------------------------------------------------------------------
# Onglet 5 : stratégies et grecques
# ---------------------------------------------------------------------------
JAMBES_DEFAUT = [
    {"Option": "Put", "Sens": "Achat", "Quantité": 1.0, "Strike": 90.0},
    {"Option": "Put", "Sens": "Vente", "Quantité": 1.0, "Strike": 95.0},
    {"Option": "Call", "Sens": "Vente", "Quantité": 1.0, "Strike": 105.0},
    {"Option": "Call", "Sens": "Achat", "Quantité": 1.0, "Strike": 110.0},
]


def euros(x: float) -> str:
    return "Illimité" if math.isinf(x) else f"{x:,.4f} €".replace(",", " ").replace(".", ",")


with onglets[4]:
    try:
        marche = {"S": st_S, "r": st_r, "q": st_q, "vol": st_vol, "jours": st_jours}
        if st_nom == PERSONNALISEE:
            section("00", "Jambes")
            saisie = st.data_editor(
                JAMBES_DEFAUT,
                column_config={
                    "Option": st.column_config.SelectboxColumn(options=["Call", "Put"]),
                    "Sens": st.column_config.SelectboxColumn(options=["Achat", "Vente"]),
                    "Quantité": st.column_config.NumberColumn(min_value=0.0, step=1.0),
                    "Strike": st.column_config.NumberColumn(min_value=0.01),
                },
                num_rows="fixed",
                hide_index=True,
                key="jambes_perso",
            )
            jambes = [
                Jambe(
                    ligne["Option"].lower(),
                    1 if ligne["Sens"] == "Achat" else -1,
                    float(ligne["Quantité"]),
                    float(ligne["Strike"]),
                )
                for ligne in saisie
            ]
            vue = VUE_PERSONNALISEE
        else:
            jambes = jambes_strategie(st_nom, st_k0, st_dk)
            vue = STRATEGIES[st_nom][0]

        pos = analyser_position(jambes, **marche)
        pm = pos.points_morts
        texte_pm = " / ".join(f"{x:.2f}" for x in pm) or "aucun"
        kpis(
            [
                (
                    "Coût net · " + ("payé" if pos.cout_net >= 0 else "encaissé"),
                    euros(pos.cout_net),
                    "",
                    True,
                ),
                ("Points morts", texte_pm),
                ("Gain maximum", euros(pos.gain_max)),
                (
                    "Perte maximum",
                    "Illimitée" if math.isinf(pos.perte_max) else euros(pos.perte_max),
                ),
            ]
        )
        st.info(f"Vue de marché : {vue}", icon=":material/insights:")

        section("01", "Position")
        lignes = [
            {
                "Jambe": f"Jambe {i}",
                "Option": li.jambe.option.capitalize(),
                "Sens": "Achat" if li.jambe.sens > 0 else "Vente",
                "Quantité": f"{li.jambe.quantite:g}",
                "Strike": f"{li.jambe.strike:g}",
                "Prime unitaire": f"{li.prime:.4f}",
                "Montant": li.montant,
                "Delta": li.delta,
                "Gamma": li.gamma,
                "Vega (+1 pt)": li.vega,
                "Theta (/jour)": li.theta,
                "Rho (+1 pt)": li.rho,
            }
            for i, li in enumerate(pos.lignes, start=1)
            if li.jambe.quantite > 0
        ]
        lignes.append(
            {
                "Jambe": "TOTAL POSITION",
                "Option": "",
                "Sens": "",
                "Quantité": "",
                "Strike": "",
                "Prime unitaire": "",
                "Montant": pos.cout_net,
                "Delta": pos.delta,
                "Gamma": pos.gamma,
                "Vega (+1 pt)": pos.vega,
                "Theta (/jour)": pos.theta,
                "Rho (+1 pt)": pos.rho,
            }
        )
        st.dataframe(
            lignes,
            hide_index=True,
            column_config={
                k: st.column_config.NumberColumn(format="%.4f")
                for k in (
                    "Montant",
                    "Delta",
                    "Gamma",
                    "Vega (+1 pt)",
                    "Theta (/jour)",
                    "Rho (+1 pt)",
                )
            },
        )

        section("02", "Lecture des grecques")
        for phrase in lecture_grecques(pos, **marche):
            st.markdown(f"- {phrase}")

        section("03", f"Scénario J+{st_ecoules}, σ' = {st_vol_sc:.0%}, S' = {st_spot_sc:g}")
        sc = scenario_pnl(
            jambes,
            **marche,
            jours_ecoules=st_ecoules,
            vol_scenario=st_vol_sc,
            spot_scenario=st_spot_sc,
        )
        st.dataframe(
            [
                {"Source du P&L": "Delta × ΔS", "Contribution": sc.contribution_delta},
                {"Source du P&L": "½ × Gamma × ΔS²", "Contribution": sc.contribution_gamma},
                {"Source du P&L": "Vega × Δσ (en points)", "Contribution": sc.contribution_vega},
                {"Source du P&L": "Theta × jours écoulés", "Contribution": sc.contribution_theta},
                {
                    "Source du P&L": "Total expliqué par les grecques",
                    "Contribution": sc.total_grecques,
                },
                {
                    "Source du P&L": "P&L réel (réévaluation BSM complète)",
                    "Contribution": sc.pnl_reel,
                },
                {
                    "Source du P&L": "Écart (effets croisés, ordre supérieur)",
                    "Contribution": sc.ecart,
                },
            ],
            hide_index=True,
            column_config={"Contribution": FORMAT_6},
        )

        pr = profils(
            jambes,
            **marche,
            jours_ecoules=st_ecoules,
            vol_scenario=st_vol_sc,
            grecque=st_grecque,
            amplitude=st_ampl,
        )
        libelle_sc = f"Scénario J+{st_ecoules}, σ = {st_vol_sc:.0%}"
        visibles = [x for x in pos.points_morts if pr["spots"][0] <= x <= pr["spots"][-1]]
        g1, g2 = st.columns(2)
        with g1:
            titre_graphique("P&L selon le cours du sous-jacent")
            afficher(
                courbes(
                    {
                        "À l'échéance": (pr["spots"], pr["pnl_echeance"]),
                        "Aujourd'hui (J0)": (pr["spots"], pr["pnl_j0"]),
                        libelle_sc: (pr["spots"], pr["pnl_scenario"]),
                    },
                    titre_x="Cours du sous-jacent",
                    titre_y="P&L (€)",
                    couleurs=[TEXTE, PRIMAIRE, AMBRE],
                    couches=[regle_h(0.0, DISCRET, (1, 0)), regles_v(visibles)],
                )
            )
        with g2:
            titre_graphique(f"{st_grecque.capitalize()} de la position")
            afficher(
                courbes(
                    {
                        "Aujourd'hui (J0)": (pr["spots"], pr["grecque_j0"]),
                        libelle_sc: (pr["spots"], pr["grecque_scenario"]),
                    },
                    titre_x="Cours du sous-jacent",
                    titre_y=st_grecque.capitalize(),
                    couleurs=[PRIMAIRE, AMBRE],
                    couches=[regle_h(0.0, DISCRET, (1, 0))],
                    format_y=".6f",
                )
            )

        section("04", "Comparatif")
        comp = tableau_comparatif(**marche, K0=st_k0, delta_k=st_dk)
        st.dataframe(
            [
                {
                    "Stratégie": ("▶ " if li["stratégie"] == st_nom else "") + str(li["stratégie"]),
                    "Coût net (€)": li["coût net"],
                    "Delta": li["delta"],
                    "Gamma": li["gamma"],
                    "Vega (+1 pt)": li["vega"],
                    "Theta (/jour)": li["theta"],
                    "Vue de marché": li["vue"],
                }
                for li in comp
            ],
            hide_index=True,
            column_config={
                k: st.column_config.NumberColumn(format="%.6f")
                for k in ("Coût net (€)", "Delta", "Gamma", "Vega (+1 pt)", "Theta (/jour)")
            },
        )
    except ValueError as e:
        erreur(e)

pied_de_page()

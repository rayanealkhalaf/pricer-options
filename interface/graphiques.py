"""Graphiques interactifs (Altair / Vega-Lite) au thème de l'interface.

Les graphiques partagent un thème sombre, une palette commune, un réticule
qui suit la souris et des infobulles ; le zoom se fait à la molette.
"""

from __future__ import annotations

from collections.abc import Sequence

import altair as alt
import numpy as np
import pandas as pd
import streamlit as st

PRIMAIRE = "#C8F135"
CYAN = "#7DD3FC"
VERT = "#5EEAD4"
AMBRE = "#FF8A65"
ROSE = "#FDA4AF"
ROUGE = "#F87171"
VIOLET = "#C4B5FD"
TEXTE = "#EDEDEF"
DISCRET = "#A1A1AA"
GRILLE = "#1B1D21"
PALETTE = [PRIMAIRE, AMBRE, CYAN, VIOLET, ROSE, ROUGE]
HAUTEUR = 290


@alt.theme.register("pricer", enable=True)
def _theme() -> alt.theme.ThemeConfig:
    axe = {
        "labelColor": DISCRET,
        "titleColor": DISCRET,
        "labelFont": "JetBrains Mono, ui-monospace, monospace",
        "labelFontSize": 11.5,
        "titleFont": "Space Grotesk, sans-serif",
        "titleFontSize": 12,
        "titleFontWeight": 500,
        "titlePadding": 10,
        "gridColor": GRILLE,
        "domainColor": "#2A2D33",
        "tickColor": "#2A2D33",
        "tickSize": 4,
        "labelPadding": 6,
    }
    return {
        "config": {
            "background": "transparent",
            "padding": {"left": 10, "right": 16, "top": 12, "bottom": 6},
            "autosize": {"type": "fit", "contains": "padding"},
            "font": "Space Grotesk, sans-serif",
            "view": {"stroke": None},
            "axis": axe,
            "legend": {
                "orient": "top",
                "direction": "horizontal",
                "labelColor": "#D4D4D8",
                "labelFont": "Space Grotesk, sans-serif",
                "labelFontSize": 12,
                "symbolType": "stroke",
                "symbolStrokeWidth": 3,
                "symbolSize": 140,
                "columnPadding": 14,
                "padding": 0,
                "offset": 10,
                "title": None,
                "columns": 3,
                "labelLimit": 220,
            },
            "range": {"category": PALETTE},
            "line": {"strokeWidth": 2},
        }
    }


def afficher(graphique: alt.TopLevelMixin) -> None:
    st.altair_chart(graphique, width="stretch", theme=None)


def _echelle(log: bool) -> alt.Scale:
    return alt.Scale(type="log" if log else "linear", zero=False, nice=not log)


def _axe(log: bool, compact: bool = True) -> alt.Axis:
    """Axe log : 1k, 10k… (effectifs) ou 1e-3 (petites valeurs), sans chevauchement."""
    if not log:
        return alt.Axis()
    return alt.Axis(format="~s" if compact else ".0e", labelOverlap="greedy")


def regle_h(valeur: float, couleur: str = DISCRET, tirets: Sequence[int] = (4, 4)) -> alt.Chart:
    """Ligne horizontale sans légende (zéro, barrière…)."""
    return (
        alt.Chart(pd.DataFrame({"y": [valeur]}))
        .mark_rule(color=couleur, strokeDash=list(tirets), strokeWidth=1.2)
        .encode(y="y:Q")
    )


def regles_v(valeurs: Sequence[float], couleur: str = DISCRET) -> alt.Chart:
    """Lignes verticales pointillées (points morts…)."""
    return (
        alt.Chart(pd.DataFrame({"x": list(valeurs)}))
        .mark_rule(color=couleur, strokeDash=[2, 3], strokeWidth=1)
        .encode(x="x:Q")
    )


def courbes(
    series: dict[str, tuple[Sequence[float], Sequence[float]]],
    *,
    titre_x: str,
    titre_y: str,
    couleurs: Sequence[str] | None = None,
    pointilles: Sequence[str] = (),
    log_x: bool = False,
    log_y: bool = False,
    points: bool = False,
    escalier: Sequence[str] = (),
    bandes: dict[str, tuple[Sequence[float], Sequence[float], Sequence[float]]] | None = None,
    barres: dict[str, tuple[Sequence[float], Sequence[float], Sequence[float]]] | None = None,
    couches: Sequence[alt.Chart] = (),
    format_y: str = ".4f",
    hauteur: int = HAUTEUR,
) -> alt.LayerChart:
    """Plusieurs séries ``{nom: (x, y)}`` avec réticule et infobulles.

    ``bandes`` et ``barres`` : ``{nom: (x, bas, haut)}``, dessinées dans la
    couleur de la série du même nom (intervalle de confiance, barres d'erreur).
    """
    noms = list(series)
    df = pd.concat(
        [
            pd.DataFrame({"x": np.asarray(x, float), "y": np.asarray(y, float), "serie": n})
            for n, (x, y) in series.items()
        ],
        ignore_index=True,
    )
    couleur = alt.Color(
        "serie:N",
        scale=alt.Scale(domain=noms, range=list(couleurs or PALETTE)[: len(noms)]),
        legend=alt.Legend(),
    )
    x = alt.X("x:Q", title=titre_x, scale=_echelle(log_x), axis=_axe(log_x))
    y = alt.Y("y:Q", title=titre_y, scale=_echelle(log_y), axis=_axe(log_y, compact=False))
    calques: list[alt.Chart] = []

    for donnees, marque in ((bandes, "aire"), (barres, "barre")):
        if not donnees:
            continue
        dfb = pd.concat(
            [
                pd.DataFrame(
                    {
                        "x": np.asarray(xb, float),
                        "bas": np.asarray(b, float),
                        "haut": np.asarray(h, float),
                        "serie": n,
                    }
                )
                for n, (xb, b, h) in donnees.items()
            ],
            ignore_index=True,
        )
        base = alt.Chart(dfb).encode(
            x=x,
            y=alt.Y("bas:Q", title=titre_y, scale=_echelle(log_y), axis=_axe(log_y, compact=False)),
            y2="haut:Q",
            color=couleur,
        )
        calques.append(
            base.mark_area(opacity=0.14, interpolate="monotone")
            if marque == "aire"
            else base.mark_errorbar(ticks=True, thickness=1.5)
        )

    tirets = alt.condition(
        alt.FieldOneOfPredicate(field="serie", oneOf=list(pointilles)),
        alt.value([5, 4]),
        alt.value([1, 0]),
    )
    # Vega-Lite n'accepte pas d'interpolation conditionnelle : un calque par type.
    en_escalier = df["serie"].isin(list(escalier))
    for filtre, interp in ((en_escalier, "step-after"), (~en_escalier, "monotone")):
        if not filtre.any():
            continue
        calques.append(
            alt.Chart(df[filtre])
            .mark_line(interpolate=interp, point=points, strokeCap="round")
            .encode(x=x, y=y, color=couleur, strokeDash=tirets, detail="serie:N")
        )
    # Zoom à la molette, porté par une marque simple (les marques composites
    # comme errorbar n'acceptent pas de sélection).
    i_ligne = next(i for i, c in enumerate(calques) if c.mark.type == "line")
    calques[i_ligne] = calques[i_ligne].add_params(
        alt.selection_interval(bind="scales", encodings=["x", "y"])
    )

    survol = alt.selection_point(
        fields=["x"], nearest=True, on="pointerover", clear="pointerout", empty=False
    )
    calques.append(
        alt.Chart(df)
        .mark_rule(color="#52525B", strokeWidth=1)
        .encode(x="x:Q")
        .transform_filter(survol)
    )
    calques.append(
        alt.Chart(df)
        .mark_circle(size=70, stroke="#08090A", strokeWidth=1.5)
        .encode(
            x=x,
            y=y,
            color=couleur,
            opacity=alt.condition(survol, alt.value(1), alt.value(0)),
            tooltip=[
                alt.Tooltip("serie:N", title="Série"),
                alt.Tooltip("x:Q", title=titre_x, format=",.4~f"),
                alt.Tooltip("y:Q", title=titre_y or "Valeur", format=format_y),
            ],
        )
        .add_params(survol)
    )
    return alt.layer(*calques, *couches).properties(height=hauteur)


def faisceau(
    temps: np.ndarray,
    chemins: np.ndarray,
    *,
    touche: np.ndarray | None = None,
    regles: Sequence[tuple[float, str, str]] = (),
    titre_y: str = "S(t)",
    hauteur: int = HAUTEUR,
) -> alt.LayerChart:
    """Faisceau de trajectoires ; ``touche`` colore les chemins ayant franchi une barrière.

    ``regles`` : ``(niveau, libellé, couleur)`` tracées en pointillé et légendées.
    """
    n, m = chemins.shape
    df = pd.DataFrame(
        {
            "t": np.tile(temps, n),
            "S": chemins.ravel(),
            "chemin": np.repeat(np.arange(n), m),
        }
    )
    x = alt.X("t:Q", title="Temps (années)", scale=alt.Scale(nice=False))
    y = alt.Y("S:Q", title=titre_y, scale=alt.Scale(zero=False))
    if touche is not None:
        df["etat"] = np.repeat(np.where(touche.any(axis=1), "Barrière touchée", "Intact"), m)
        couleur = alt.Color(
            "etat:N",
            scale=alt.Scale(domain=["Intact", "Barrière touchée"], range=[PRIMAIRE, ROSE]),
            legend=alt.Legend(),
        )
    else:
        teintes = [
            f"#{int(a):02x}{int(b):02x}{int(c):02x}"
            for a, b, c in np.linspace([0xC8, 0xF1, 0x35], [0x7D, 0xD3, 0xFC], n)
        ]
        couleur = alt.Color(
            "chemin:N", scale=alt.Scale(domain=list(range(n)), range=teintes), legend=None
        )
    calques: list[alt.Chart] = [
        alt.Chart(df)
        .mark_line(strokeWidth=1.1, opacity=0.75)
        .encode(x=x, y=y, color=couleur, detail="chemin:N")
        .add_params(alt.selection_interval(bind="scales", encodings=["x", "y"]))
    ]
    if touche is not None:
        idx = [(i, int(np.argmax(t))) for i, t in enumerate(touche) if t.any()]
        if idx:
            croix = pd.DataFrame(
                {"t": [temps[j] for _, j in idx], "S": [chemins[i, j] for i, j in idx]}
            )
            calques.append(
                alt.Chart(croix)
                .mark_point(shape="cross", size=60, color=TEXTE, filled=True, opacity=0.9)
                .encode(
                    x="t:Q",
                    y="S:Q",
                    tooltip=[
                        alt.Tooltip("t:Q", title="Premier franchissement", format=".3f"),
                        alt.Tooltip("S:Q", title="Spot", format=".2f"),
                    ],
                )
            )
    if regles:
        dfr = pd.DataFrame(regles, columns=["niveau", "libelle", "couleur"])
        calques.append(
            alt.Chart(dfr)
            .mark_rule(strokeDash=[5, 4], strokeWidth=1.4)
            .encode(
                y="niveau:Q",
                color=alt.Color("couleur:N", scale=None),
                tooltip=[alt.Tooltip("libelle:N", title="Niveau")],
            )
        )
        calques.append(
            alt.Chart(dfr)
            .mark_text(align="right", dx=-4, dy=-7, fontSize=11, fontWeight=500)
            .encode(
                x=alt.datum(float(temps[-1])),
                y="niveau:Q",
                text="libelle:N",
                color=alt.Color("couleur:N", scale=None),
            )
        )
    return alt.layer(*calques).properties(height=hauteur)

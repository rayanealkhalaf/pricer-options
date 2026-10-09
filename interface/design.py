"""Composants visuels de l'interface : styles, en-tête, cartes d'indicateurs.

Tout le HTML passe par ``st.html`` ; les textes dynamiques sont échappés.
"""

from __future__ import annotations

import math
from html import escape
from pathlib import Path

import streamlit as st

ASSETS = Path(__file__).resolve().parent.parent / "assets"
LOGO = ASSETS / "logo.svg"
LOGO_ICONE = ASSETS / "logo-mark.svg"
DEPOT = "https://github.com/rayanealkhalaf/pricer-options"

# Surface du prix BSM d'un call C(S, T) en fil de fer, qui oscille lentement.
# Projection perspective dessinée sur un canvas ; image fixe si l'utilisateur
# demande moins d'animations, et boucle arrêtée quand le canvas disparaît.
SURFACE_3D = """
<figure class="surface3d"><canvas id="surface-bsm"></canvas>
<figcaption>C(S, T) · Black-Scholes</figcaption></figure>
<script>
(() => {
  const cv = document.getElementById("surface-bsm");
  if (!cv || cv.dataset.pret) return;
  cv.dataset.pret = "1";
  const ctx = cv.getContext("2d");
  const N = (x) => {
    const t = 1 / (1 + 0.2316419 * Math.abs(x));
    const d = 0.3989423 * Math.exp(-x * x / 2);
    const poly = 1.781478 + t * (-1.821256 + t * 1.330274);
    const p = d * t * (0.3193815 + t * (-0.3565638 + t * poly));
    return x > 0 ? 1 - p : p;
  };
  const K = 100, r = 0.03, s = 0.25;
  const call = (S, T) => {
    const v = s * Math.sqrt(T), d1 = (Math.log(S / K) + (r + s * s / 2) * T) / v;
    return S * N(d1) - K * Math.exp(-r * T) * N(d1 - v);
  };
  const nx = 28, ny = 18, grille = [];
  for (let i = 0; i < nx; i++) {
    const ligne = [];
    for (let j = 0; j < ny; j++) {
      const S = 60 + 80 * i / (nx - 1), T = 0.05 + 1.95 * j / (ny - 1);
      ligne.push([i / (nx - 1) - 0.5, j / (ny - 1) - 0.5, call(S, T) / 46]);
    }
    grille.push(ligne);
  }
  const reduit = matchMedia("(prefers-reduced-motion: reduce)").matches;
  let t = 0;
  const angleDe = (u) => 0.8 + 0.3 * Math.sin(u);
  let angle = angleDe(0);
  const elev = 0.45, ce = Math.cos(elev), se = Math.sin(elev);
  // Projection perspective sans échelle, centrée sur l'origine.
  const brut = ([x, y, z], a) => {
    const X = x * Math.cos(a) - y * Math.sin(a), Y = x * Math.sin(a) + y * Math.cos(a);
    const Z = z - 0.4, f = 2.4 / (2.4 + Y * ce + Z * se);
    return [X * f, (Y * se - Z * ce) * f];
  };
  // Cadrage fixe calculé sur toute l'oscillation : la surface ne « respire » pas.
  let lx = 0, ymin = Infinity, ymax = -Infinity;
  for (let k = 0; k < 36; k++) {
    for (const ligne of grille) for (const pt of ligne) {
      const [x, y] = brut(pt, angleDe((k * Math.PI) / 18));
      lx = Math.max(lx, Math.abs(x));
      ymin = Math.min(ymin, y);
      ymax = Math.max(ymax, y);
    }
  }
  function dessiner() {
    const w = cv.clientWidth, h = cv.clientHeight, dpr = devicePixelRatio || 1;
    if (!w || !h) return;
    if (cv.width !== Math.round(w * dpr)) {
      cv.width = Math.round(w * dpr);
      cv.height = Math.round(h * dpr);
    }
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, w, h);
    const k = Math.min((w * 0.47) / lx, (h * 0.86) / (ymax - ymin));
    const dy = h / 2 - (k * (ymax + ymin)) / 2;
    const P = grille.map((ligne) =>
      ligne.map((pt) => {
        const [x, y] = brut(pt, angle);
        return [w / 2 + k * x, dy + k * y, pt[2]];
      })
    );
    ctx.lineWidth = 1;
    const segment = (a, b) => {
      ctx.strokeStyle = `rgba(200, 241, 53, ${0.12 + 0.75 * (a[2] + b[2]) / 2})`;
      ctx.beginPath();
      ctx.moveTo(a[0], a[1]);
      ctx.lineTo(b[0], b[1]);
      ctx.stroke();
    };
    for (let i = 0; i < nx; i++) for (let j = 1; j < ny; j++) segment(P[i][j - 1], P[i][j]);
    for (let j = 0; j < ny; j++) for (let i = 1; i < nx; i++) segment(P[i - 1][j], P[i][j]);
  }
  function boucle() {
    if (!cv.isConnected) return;
    if (!document.hidden) {
      t += 0.006;
      angle = angleDe(t);
      dessiner();
    }
    requestAnimationFrame(boucle);
  }
  if (reduit) {
    dessiner();
    addEventListener("resize", dessiner);
  } else {
    boucle();
  }
})();
</script>
"""


def injecter_styles() -> None:
    """Charge la feuille de style globale et le logo de la barre latérale."""
    st.html(f"<style>{(ASSETS / 'style.css').read_text(encoding='utf-8')}</style>")
    st.logo(str(LOGO), icon_image=str(LOGO_ICONE), size="large", link=DEPOT)


def entete() -> None:
    """Bandeau d'accueil : titre court et surface de prix 3D."""
    st.html(
        '<div class="hero"><div>'
        "<h1>Pricer d'options<span>.</span></h1>"
        "<p>Formules fermées, arbres et Monte-Carlo, validés contre la théorie.</p>"
        f"</div>{SURFACE_3D}</div>",
        unsafe_allow_javascript=True,
    )


def titre_sidebar(texte: str) -> None:
    st.html(f'<div class="sidebar-titre">{escape(texte)}</div>')


def section(numero: str, titre: str) -> None:
    """Titre de section numéroté (« 01  Grecques »)."""
    st.html(
        f'<div class="section"><span class="section-numero">{escape(numero)}</span>'
        f"<h3>{escape(titre)}</h3></div>"
    )


def titre_graphique(titre: str) -> None:
    st.html(f'<div class="titre-graphique">{escape(titre)}</div>')


def badge_z(z: float) -> str:
    """Pastille colorée selon |z| : < 2 citron, < 3 ambre, sinon corail."""
    if math.isnan(z):
        return ""
    classe = "ok" if abs(z) < 2 else "alerte" if abs(z) < 3 else "echec"
    return f'<span class="badge badge--{classe}">z = {z:+.2f}</span>'


def kpis(cartes: list[tuple[str, str] | tuple[str, str, str] | tuple[str, str, str, bool]]) -> None:
    """Grille de cartes animées.

    Chaque carte : ``(libellé, valeur[, aide[, mise_en_avant]])``. L'aide peut
    contenir du HTML produit par :func:`badge_z` ; le libellé et la valeur
    sont échappés.
    """
    html = []
    for i, carte in enumerate(cartes):
        libelle, valeur = carte[0], carte[1]
        aide = carte[2] if len(carte) > 2 else ""
        accent = len(carte) > 3 and carte[3]
        html.append(
            f'<div class="kpi{" kpi--accent" if accent else ""}" style="--i:{i}">'
            f'<div class="kpi-libelle">{escape(libelle)}</div>'
            f'<div class="kpi-valeur{" kpi-valeur--long" if len(valeur) > 12 else ""}" '
            f'title="{escape(valeur)}">{escape(valeur)}</div>'
            + (f'<div class="kpi-aide">{aide}</div>' if aide else "")
            + "</div>"
        )
    st.html(f'<div class="kpis" style="--n:{len(cartes)}">{"".join(html)}</div>')


def pied_de_page() -> None:
    st.html(
        '<div class="pied"><span>Rayane ALKHALAF</span>'
        f'<a href="{DEPOT}" target="_blank">GitHub ↗</a></div>'
    )

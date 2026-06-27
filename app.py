#!/usr/bin/env python3
"""
app.py — Interface Streamlit unifiée pour l'Album Photo Generator.

Point d'entrée principal. Fusionne :
  - Frontend Dionysos : wizard 5 étapes (Sélection → Scoring → Palette → Preview → Export)
  - Backend Hephaistos : AlbumDatabase, scoring IA, génération PDF, OneDrive

Usage:
    streamlit run app.py
"""

import logging
import sys
from pathlib import Path

# Ajouter le projet au path
_HERE = Path(__file__).parent
sys.path.insert(0, str(_HERE))

import streamlit as st
import yaml


# ── Configuration ─────────────────────────────────────────────────────────

CSS_PATH = _HERE / "styles" / "app.css"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("app")

# Plan de navigation en wizard
STEPS = [
    ("Sélection", "📂", "Choisir les photos"),
    ("Scoring", "🤖", "Noter et dispatcher"),
    ("Palette", "🎨", "Choisir les couleurs"),
    ("Preview", "👁️", "Prévisualiser l'album"),
    ("Export", "📦", "Voix + PDF"),
]


# ── Initialisation du backend (caché) ───────────────────────────────────

@st.cache_resource(show_spinner="Initialisation de l'application…")
def init_backend():
    """Charge et initialise les modules backend (une seule fois)."""
    # Configuration
    config_path = _HERE / "config.yaml"
    if config_path.exists():
        with open(config_path) as f:
            config = yaml.safe_load(f)
    else:
        config = {}

    # Base de données
    from db import AlbumDatabase
    db_path = config.get("database", {}).get("path", "data/albums.db")
    db = AlbumDatabase(db_path=str(_HERE / db_path))

    # Scoring IA (import silencieux si indisponible)
    scorer = None
    dispatcher = None
    try:
        from album_generator.scoring import PhotoScorer, PhotoDispatcher, SCORE_WEIGHTS
        scorer = PhotoScorer()
        dispatcher = PhotoDispatcher()
    except ImportError:
        logger.warning("PhotoScorer non disponible — mode démo")

    # Génération PDF
    gen = None
    try:
        import generate as gen_module
        gen = gen_module
    except ImportError:
        logger.warning("generate.py non disponible — export simulé")

    return {
        "config": config,
        "db": db,
        "scorer": scorer,
        "dispatcher": dispatcher,
        "generate": gen,
    }


def init_session_state():
    """Initialise les variables de session Streamlit."""
    if "backend" not in st.session_state:
        st.session_state.backend = init_backend()

    # Navigation wizard
    if "page" not in st.session_state:
        st.session_state.page = "Sélection"

    # Album courant
    if "album_id" not in st.session_state:
        st.session_state.album_id = None

    # État du wizard
    if "photos_selected" not in st.session_state:
        st.session_state.photos_selected = []
    if "scoring_done" not in st.session_state:
        st.session_state.scoring_done = False
    if "scoring_results" not in st.session_state:
        st.session_state.scoring_results = {}
    if "palette_set" not in st.session_state:
        st.session_state.palette_set = False
    if "current_palette" not in st.session_state:
        st.session_state.current_palette = "Soleil ☀️"
    if "voice_recorded" not in st.session_state:
        st.session_state.voice_recorded = False
    if "export_done" not in st.session_state:
        st.session_state.export_done = False

    # Preview
    if "preview_page" not in st.session_state:
        st.session_state.preview_page = 0
    if "preview_layout" not in st.session_state:
        st.session_state.preview_layout = "Grille"


# ── Sidebar navigation ────────────────────────────────────────────────

def get_step_status(step_name: str) -> str:
    """Retourne 'done', 'current', ou 'pending'."""
    steps_only = [s[0] for s in STEPS]
    current_idx = steps_only.index(st.session_state.page) if st.session_state.page in steps_only else 0
    step_idx = steps_only.index(step_name)

    done_steps = set()
    if st.session_state.photos_selected:
        done_steps.add("Sélection")
    if st.session_state.scoring_done:
        done_steps.add("Scoring")
    if st.session_state.palette_set:
        done_steps.add("Palette")
    if st.session_state.voice_recorded:
        done_steps.add("Export")

    if step_name in done_steps:
        return "done"
    elif step_idx == current_idx:
        return "current"
    else:
        return "pending"


def render_sidebar():
    """Affiche la barre latérale avec progression wizard."""
    with st.sidebar:
        st.markdown(
            '<div style="text-align:center; padding:0.5rem;">'
            '<h2 style="color:#3a2a1a; margin:0;">📸 Album Photo</h2>'
            '<p style="color:#8a6a3a; font-size:0.8rem;">Générateur intelligent</p>'
            '</div>',
            unsafe_allow_html=True,
        )

        # Infos album courant
        db = st.session_state.backend["db"]
        album_id = st.session_state.album_id
        if album_id:
            album = db.get_album(album_id)
            if album:
                st.markdown(
                    f'<div style="background:#f5ede0; border-radius:8px; padding:0.5rem; margin-bottom:0.5rem;">'
                    f'<strong>📁 {album["name"]}</strong><br/>'
                    f'<span style="font-size:0.75rem; color:#8a6a3a;">{album.get("year", "")} · {album.get("enfant", "")}</span>'
                    f'</div>',
                    unsafe_allow_html=True,
                )
            else:
                st.session_state.album_id = None

        st.markdown("---")

        # Progression dans les étapes
        for step_name, icon, desc in STEPS:
            status = get_step_status(step_name)
            if status == "done":
                prefix = "✅"
                extra = "nav-step-done"
            elif status == "current":
                prefix = "▶️"
                extra = "nav-step-active"
            else:
                prefix = "○"
                extra = "nav-step-pending"

            clicked = st.button(
                f"{prefix} **{step_name}**  \n{desc}",
                key=f"nav_{step_name}",
                help=f"Aller à : {step_name}",
                use_container_width=True,
                type="secondary" if status == "current" else "tertiary",
            )
            if clicked:
                st.session_state.page = step_name
                st.rerun()

        st.markdown("---")
        st.markdown(
            '<div class="app-footer">'
            'Album Generator v1.0.0<br/>'
            'Dionysos 🎭 × Héphaïstos 🔨'
            '</div>',
            unsafe_allow_html=True,
        )


# ── Header ────────────────────────────────────────────────────────────

def render_header():
    """Affiche l'en-tête de page."""
    st.markdown(
        '<div class="app-header">'
        '<h1>📸 Générateur d\'Albums Photo</h1>'
        '<p>Scoring IA · Palette interactive · Récits vocaux · Export PDF</p>'
        '</div>',
        unsafe_allow_html=True,
    )


# ── Routage des pages ─────────────────────────────────────────────────

def render_page():
    """Affiche la page active du wizard."""
    page = st.session_state.page

    if page == "Sélection":
        import pages.selection as p
        p.render()
    elif page == "Scoring":
        import pages.scoring_page as p
        p.render()
    elif page == "Palette":
        import pages.palette as p
        p.render()
    elif page == "Preview":
        import pages.preview as p
        p.render()
    elif page == "Export":
        import pages.export_page as p
        p.render()
    else:
        st.error(f"Page inconnue : {page}")


# ── Main ──────────────────────────────────────────────────────────────

def main():
    # Page config MUST be first Streamlit command
    st.set_page_config(
        page_title="Générateur d'Albums Photo",
        page_icon="📸",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    # CSS personnalisé
    if CSS_PATH.exists():
        with open(CSS_PATH) as f:
            st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)

    # Initialisation
    init_session_state()

    # En-tête
    render_header()

    # Sidebar + contenu
    render_sidebar()
    render_page()

    # Footer
    st.markdown("---")
    st.caption("⚙️ Album Photo Generator · Scoring IA · Streamlit · v1.0.0")


if __name__ == "__main__":
    main()

"""
Page 2 : Scoring IA et dispatch des photos.
Lance le scoring, visualise les résultats, ajuste les dispatches.
"""

import streamlit as st
import sys
from pathlib import Path

WORKSPACE = Path(__file__).parent.parent
if str(WORKSPACE) not in sys.path:
    sys.path.insert(0, str(WORKSPACE))

from pages.page_utils import get_mock_onedrive_photos, get_scores_dict


def render():
    """Affiche la page de scoring."""

    selected = st.session_state.photos_selected
    if not selected:
        st.warning("⚠️ Aucune photo sélectionnée. Retournez à la page Sélection.")
        if st.button("← Retour à la sélection"):
            st.session_state.page = "Sélection"
            st.rerun()
        return

    # ── En-tête ──────────────────────────────────────────────────────
    st.markdown(
        f'<div class="status-card">'
        f'<h3>🤖 Scoring IA — {len(selected)} photos</h3>'
        f'<span class="label">Cliquez sur "Lancer le scoring" pour noter les photos</span>'
        f'</div>',
        unsafe_allow_html=True,
    )

    # ── Lancer le scoring ────────────────────────────────────────────
    if "scoring_results" not in st.session_state:
        st.session_state.scoring_results = {}

    col1, col2 = st.columns([1, 3])

    with col1:
        if st.button("🚀 Lancer le scoring", type="primary", use_container_width=True):
            with st.spinner("🧠 Scoring IA en cours... Analyse des photos..."):
                # Simuler un délai de scoring
                import time
                progress = st.progress(0)
                results = {}
                for i, pid in enumerate(selected):
                    time.sleep(0.15)  # Simule ~0.15s par photo
                    scores = get_scores_dict()
                    results[pid] = scores.get(pid, {"score": 0.5, "category": "filler"})
                    progress.progress((i + 1) / len(selected))

                st.session_state.scoring_results = results
                st.session_state.scoring_done = True
                st.rerun()

    with col2:
        if st.session_state.scoring_done:
            st.success(f"✅ Scoring terminé — {len(selected)} photos notées !")

    # ── Résultats ────────────────────────────────────────────────────
    if st.session_state.scoring_done and st.session_state.scoring_results:
        results = st.session_state.scoring_results

        # Statistiques globales
        scores = [r.get("score", 0) for r in results.values()]
        avg_score = sum(scores) / len(scores) if scores else 0
        best = max(scores) if scores else 0
        worst = min(scores) if scores else 0

        col_s1, col_s2, col_s3, col_s4 = st.columns(4)
        col_s1.metric("📊 Score moyen", f"{avg_score:.2f}")
        col_s2.metric("🏆 Meilleur", f"{best:.2f}")
        col_s3.metric("📉 Plus faible", f"{worst:.2f}")
        col_s4.metric("📸 Photos notées", len(results))

        # Filtres
        st.markdown("### 📋 Résultats détaillés")
        filter_cat = st.radio(
            "Catégorie",
            ["Toutes", "Hero", "Support", "Filler"],
            horizontal=True,
        )

        # Tableau des résultats
        photos_data = []
        for pid in selected:
            r = results.get(pid, {"score": 0, "category": "filler", "sharpness": 0,
                                   "exposure": 0, "contrast": 0, "smile": 0, "faces": 0})
            cat = r.get("category", "filler")
            if filter_cat != "Toutes" and filter_cat.lower() != cat:
                continue

            from pages.page_utils import get_mock_onedrive_photos
            photo_info = next((p for p in get_mock_onedrive_photos() if p["id"] == pid), {})
            score_val = r.get("score", 0)

            badge_class = {"hero": "score-hero", "support": "score-support", "filler": "score-filler"}.get(cat, "")
            st.markdown(
                f'<div class="photo-card">'
                f'<div style="display:flex; justify-content:space-between; align-items:center;">'
                f'<div><strong>{photo_info.get("name", pid)}</strong></div>'
                f'<div><span class="score-badge {badge_class}">{cat.upper()}</span></div>'
                f'</div>'
                f'<div class="photo-meta">Score: {score_val:.2f} · '
                f'Netteté: {r.get("sharpness", 0):.2f} · '
                f'Exposition: {r.get("exposure", 0):.2f} · '
                f'Sourire: {r.get("smile", 0):.2f} · '
                f'Visages: {r.get("faces", 0)}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )

        # Bouton suivant
        st.markdown("---")
        col_n1, col_n2 = st.columns([1, 3])
        with col_n1:
            if st.button("← Retour Sélection"):
                st.session_state.page = "Sélection"
                st.rerun()
        with col_n2:
            if st.button("➡️ Choisir la palette →", type="primary", use_container_width=True):
                st.session_state.page = "Palette"
                st.rerun()

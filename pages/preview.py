"""
Page 4 : Prévisualisation de l'album.
Affiche les pages sous forme de spreads, avec les photos dispatchees,
la palette choisie, et la possibilité de réorganiser.
"""

import streamlit as st
import sys
from pathlib import Path

WORKSPACE = Path(__file__).parent.parent
if str(WORKSPACE) not in sys.path:
    sys.path.insert(0, str(WORKSPACE))

from pages.page_utils import get_mock_onedrive_photos, get_scores_dict

# Layouts de page disponibles (simplifiés depuis config.PAGE_STYLES)
PAGE_LAYOUTS = [
    {"name": "Héroïque", "icon": "🏆", "photos": 1, "desc": "Une photo pleine page"},
    {"name": "Duo", "icon": "👫", "photos": 2, "desc": "Deux photos côte à côte"},
    {"name": "Grille", "icon": "🔲", "photos": 4, "desc": "Grille 2×2 structurée"},
    {"name": "Collage", "icon": "🎭", "photos": 6, "desc": "Mosaïque organique"},
    {"name": "Typo", "icon": "📝", "photos": 0, "desc": "Page de texte / citation"},
]


def render():
    """Affiche la page de prévisualisation."""

    st.markdown(
        f'<div class="status-card">'
        f'<h3>👁️ Prévisualisation de l\'album</h3>'
        f'<span class="label">Disposition, ordre et mise en page</span>'
        f'</div>',
        unsafe_allow_html=True,
    )

    selected = st.session_state.photos_selected
    if not selected:
        st.warning("Aucune photo sélectionnée.")
        if st.button("← Retour à la sélection"):
            st.session_state.page = "Sélection"
            st.rerun()
        return

    all_photos = get_mock_onedrive_photos()
    photo_map = {p["id"]: p for p in all_photos}
    scores_dict = get_scores_dict()

    # ── Configuration de la preview ──────────────────────────────────
    col_c1, col_c2 = st.columns([1, 2])

    with col_c1:
        palette_name = st.session_state.get("current_palette_name", "Soleil ☀️")
        st.markdown(f"**Palette active :** {palette_name}")
        st.markdown(f"**Photos :** {len(selected)} sélectionnées")

        # Trier par score si disponible
        sort_by = st.radio("Trier par", ["Score (desc)", "Date", "Ordre manuel"], horizontal=True)

        if sort_by == "Score (desc)":
            scored = [(pid, scores_dict.get(pid, {}).get("score", 0)) for pid in selected]
            scored.sort(key=lambda x: x[1], reverse=True)
            sorted_photos = [pid for pid, _ in scored]
        elif sort_by == "Date":
            sorted_photos = sorted(selected, key=lambda pid: photo_map.get(pid, {}).get("date", ""))
        else:
            sorted_photos = selected

        # Nombre de pages
        photos_per_page = st.select_slider(
            "Photos par page",
            options=[1, 2, 4, 6, 8],
            value=4,
        )
        total_pages = max(1, (len(sorted_photos) + photos_per_page - 1) // photos_per_page)
        st.markdown(f"**{total_pages} page(s)** au total")

        # Layout de page
        st.markdown("**Layout**")
        layout_cols = st.columns(3)
        layouts_3 = PAGE_LAYOUTS[:3]
        for i, (col, layout) in enumerate(zip(layout_cols, layouts_3)):
            with col:
                if st.button(
                    f"{layout['icon']} {layout['name']}",
                    key=f"layout_{i}",
                    use_container_width=True,
                    type="secondary",
                ):
                    st.session_state.preview_layout = layout["name"]
                    st.rerun()

    with col_c2:
        st.markdown("### 📖 Aperçu des pages")

        palette = st.session_state.get("current_palette_name", "Soleil ☀️")
        bg_color = "#fefcf5"
        accent_color = "#c49a5a"

        # Pagination dans la preview
        page_num = st.session_state.get("preview_page", 0)
        col_p1, col_p2, col_p3 = st.columns([1, 3, 1])
        with col_p1:
            if st.button("◀️ Page précédente", disabled=page_num <= 0):
                st.session_state.preview_page = max(0, page_num - 1)
                st.rerun()
        with col_p2:
            st.markdown(f"<div style='text-align:center;'>Page <strong>{page_num + 1}/{total_pages}</strong></div>",
                        unsafe_allow_html=True)
        with col_p3:
            if st.button("Page suivante ▶️", disabled=page_num >= total_pages - 1):
                st.session_state.preview_page = min(total_pages - 1, page_num + 1)
                st.rerun()

        # Afficher les photos de la page courante
        start_idx = page_num * photos_per_page
        end_idx = min(start_idx + photos_per_page, len(sorted_photos))
        page_photos = sorted_photos[start_idx:end_idx]

        # Layout de la page preview
        layout_name = st.session_state.get("preview_layout", "Grille")
        if layout_name == "Héroïque":
            cols = st.columns(1)
        elif layout_name == "Duo":
            cols = st.columns(2)
        elif layout_name in ("Grille", "Collage"):
            cols = st.columns(min(2, len(page_photos) or 1))

        for i, pid in enumerate(page_photos):
            photo = photo_map.get(pid, {})
            score_info = scores_dict.get(pid, {})
            cat = score_info.get("category", "filler")
            cat_emoji = {"hero": "⭐", "support": "🔷", "filler": "◽"}.get(cat, "")
            col_idx = i % len(cols) if len(cols) > 0 else 0
            col = cols[col_idx] if col_idx < len(cols) else cols[-1]

            with col:
                st.markdown(
                    f'<div class="preview-page" style="'
                    f'background: {bg_color}; '
                    f'border-color: {accent_color};'
                    f'padding: 0.8rem;">'
                    f'<div style="background:#f5ede0; border-radius:6px; height:120px; '
                    f'display:flex; align-items:center; justify-content:center; '
                    f'border:2px dashed {accent_color}; margin-bottom:6px;">'
                    f'<span style="color:#8a6a3a; font-size:0.8rem;">📷 {photo.get("name", "Photo")[:30]}...</span>'
                    f'</div>'
                    f'<div style="display:flex; justify-content:space-between; font-size:0.75rem;">'
                    f'<span>{cat_emoji} {cat}</span>'
                    f'<span style="color:#8a6a3a;">{score_info.get("score", 0):.2f}</span>'
                    f'</div>'
                    f'</div>',
                    unsafe_allow_html=True,
                )

    # ── Navigation ───────────────────────────────────────────────────
    st.markdown("---")
    col_n1, col_n2 = st.columns([1, 3])
    with col_n1:
        if st.button("← Retour Palette"):
            st.session_state.page = "Palette"
            st.rerun()
    with col_n2:
        if st.button("➡️ Exporter l'album →", type="primary", use_container_width=True):
            st.session_state.page = "Export"
            st.rerun()

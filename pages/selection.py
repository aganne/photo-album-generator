"""
Page 1 : Sélection des photos depuis OneDrive (mode mock).
Permet de parcourir les dossiers, filtrer par type, et sélectionner les fichiers.
"""

import streamlit as st
import sys
from pathlib import Path

# Ajouter le workspace au path
WORKSPACE = Path(__file__).parent.parent
if str(WORKSPACE) not in sys.path:
    sys.path.insert(0, str(WORKSPACE))

from pages.page_utils import get_mock_photo_groups, get_mock_onedrive_photos


def render():
    """Affiche la page de sélection des photos."""

    # ── Créer ou choisir un album ────────────────────────────────────
    col1, col2 = st.columns([3, 1])

    with col1:
        album_name = st.text_input(
            "Nom de l'album",
            value=st.session_state.get("album_name", ""),
            placeholder="Ex: Album Mael 2024",
        )
        if album_name:
            st.session_state.album_name = album_name

    with col2:
        album_year = st.number_input(
            "Année",
            min_value=2000,
            max_value=2030,
            value=st.session_state.get("album_year", 2024),
            step=1,
        )
        st.session_state.album_year = album_year

    # ── Statut de sélection ──────────────────────────────────────────
    selected = st.session_state.photos_selected
    st.markdown(
        f'<div class="status-card">'
        f'<h3>📊 Statut de la sélection</h3>'
        f'<span class="label">Photos sélectionnées</span> '
        f'<span class="value">{len(selected)}</span>'
        f'</div>',
        unsafe_allow_html=True,
    )

    # ── Parcourir les photos mock OneDrive ───────────────────────────
    st.markdown("### 📁 Parcourir OneDrive")

    groups = get_mock_photo_groups()
    all_photos = get_mock_onedrive_photos()

    # Filtres
    col_f1, col_f2 = st.columns(2)
    with col_f1:
        # Sélection du dossier
        folder_names = ["Tous les dossiers"] + sorted(groups.keys())
        selected_folder = st.selectbox("Dossier", folder_names)
    with col_f2:
        filter_type = st.radio("Type", ["Tous", "Photos", "Vidéos"], horizontal=True)

    # Filtrer les photos
    if selected_folder == "Tous les dossiers":
        photos_to_show = all_photos
    else:
        photos_to_show = groups.get(selected_folder, [])

    if filter_type == "Photos":
        photos_to_show = [p for p in photos_to_show if p["type"] == "photo"]
    elif filter_type == "Vidéos":
        photos_to_show = [p for p in photos_to_show if p["type"] == "video"]

    # ── Grille de sélection ──────────────────────────────────────────
    st.markdown(f"**{len(photos_to_show)} fichier(s) trouvé(s)**")

    # Afficher en grille de 3 colonnes
    cols = st.columns(3)
    selected_ids = set(st.session_state.photos_selected)

    for i, photo in enumerate(photos_to_show):
        col = cols[i % 3]
        with col:
            is_selected = photo["id"] in selected_ids
            icon = "🎬" if photo["type"] == "video" else "🖼️"
            status_icon = "✅" if is_selected else "⬜"

            card_class = "photo-card selected" if is_selected else "photo-card"
            st.markdown(
                f'<div class="{card_class}">'
                f'<div class="photo-name">{icon} {photo["name"]}</div>'
                f'<div class="photo-meta">📂 {photo["path"]}</div>'
                f'<div class="photo-meta">📅 {photo["date"]} · {photo["size_kb"]//1000} Mo</div>'
                f'</div>',
                unsafe_allow_html=True,
            )

            toggle_label = "✅ Sélectionné" if is_selected else "⬜ Sélectionner"
            if st.button(toggle_label, key=f"sel_{photo['id']}", use_container_width=True):
                if photo["id"] in selected_ids:
                    selected_ids.remove(photo["id"])
                else:
                    selected_ids.add(photo["id"])
                st.session_state.photos_selected = list(selected_ids)
                st.rerun()

    # ── Barre d'actions ──────────────────────────────────────────────
    st.markdown("---")
    col_a1, col_a2, col_a3 = st.columns([1, 1, 2])

    with col_a1:
        if st.button("📋 Tout sélectionner", use_container_width=True):
            st.session_state.photos_selected = [p["id"] for p in all_photos]
            st.rerun()

    with col_a2:
        if st.button("🗑️ Tout désélectionner", use_container_width=True):
            st.session_state.photos_selected = []
            st.rerun()

    with col_a3:
        if len(st.session_state.photos_selected) >= 3:
            if st.button(
                "➡️ Passer au Scoring",
                type="primary",
                use_container_width=True,
            ):
                st.session_state.page = "Scoring"
                st.rerun()
        else:
            st.info("Sélectionnez au moins 3 photos pour continuer")

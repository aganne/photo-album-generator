"""
Page 3 : Palette de couleurs interactive.
Permet de choisir une palette prédéfinie, de customiser les couleurs,
et de prévisualiser l'ambiance de l'album.
"""

import streamlit as st
import sys
from pathlib import Path

WORKSPACE = Path(__file__).parent.parent
if str(WORKSPACE) not in sys.path:
    sys.path.insert(0, str(WORKSPACE))

from pages.page_utils import get_active_palette, save_palette, load_palettes

# Palettes disponibles (copie depuis config.yaml pour accès direct)
PALETTES = {
    "Soleil ☀️": {
        "name": "Soleil ☀️",
        "bg_start": "#fefcf5",
        "bg_mid": "#f5ede0",
        "bg_end": "#e8cfa0",
        "band_top": "#8a6a3a",
        "band_bottom": "#c49a5a",
        "text_primary": "#3a2a1a",
        "text_secondary": "#5a3a1a",
        "accent_1": "#c49a5a",
        "accent_2": "#e8cfa0",
        "photo_border": "#ffffff",
    },
    "Océan 🌊": {
        "name": "Océan 🌊",
        "bg_start": "#e8f4f8",
        "bg_mid": "#d0e8f0",
        "bg_end": "#a8d4e8",
        "band_top": "#1a5276",
        "band_bottom": "#2e86c1",
        "text_primary": "#1a2a3a",
        "text_secondary": "#2a4a5a",
        "accent_1": "#2e86c1",
        "accent_2": "#a8d4e8",
        "photo_border": "#ffffff",
    },
    "Forêt 🌲": {
        "name": "Forêt 🌲",
        "bg_start": "#f0f5e8",
        "bg_mid": "#e0ecd0",
        "bg_end": "#c0d8a0",
        "band_top": "#2d5a1e",
        "band_bottom": "#4a7a2e",
        "text_primary": "#1a2a10",
        "text_secondary": "#2a3a1a",
        "accent_1": "#4a7a2e",
        "accent_2": "#a0c870",
        "photo_border": "#ffffff",
    },
    "Crépuscule 🌆": {
        "name": "Crépuscule 🌆",
        "bg_start": "#f5ece8",
        "bg_mid": "#e8d4cc",
        "bg_end": "#d4b0a0",
        "band_top": "#5a2a3a",
        "band_bottom": "#8a4a5a",
        "text_primary": "#2a1a1a",
        "text_secondary": "#4a2a2a",
        "accent_1": "#8a4a5a",
        "accent_2": "#c89080",
        "photo_border": "#ffffff",
    },
}


def render():
    """Affiche la page de sélection de palette."""

    st.markdown(
        f'<div class="status-card">'
        f'<h3>🎨 Palette de couleurs</h3>'
        f'<span class="label">Choisissez l\'ambiance chromatique de votre album</span>'
        f'</div>',
        unsafe_allow_html=True,
    )

    # Palette active dans la session
    if "current_palette" not in st.session_state:
        st.session_state.current_palette = "Soleil ☀️"

    # ── Sélection de la palette ──────────────────────────────────────
    col1, col2 = st.columns([1, 2])

    with col1:
        st.markdown("### Palette prédéfinie")
        palette_names = list(PALETTES.keys())
        selected_palette = st.selectbox(
            "Choisissez une ambiance",
            palette_names,
            index=palette_names.index(st.session_state.current_palette)
            if st.session_state.current_palette in palette_names else 0,
            label_visibility="collapsed",
        )
        st.session_state.current_palette = selected_palette

        palette = PALETTES[selected_palette]

        # Aperçu des couleurs principales
        st.markdown("#### 🎯 Couleurs")
        for key, label in [
            ("bg_mid", "Fond"),
            ("band_top", "Bande haute"),
            ("band_bottom", "Bande basse"),
            ("text_primary", "Texte principal"),
            ("accent_1", "Accent"),
        ]:
            color = palette.get(key, "#ccc")
            st.markdown(
                f'<div style="display:flex; align-items:center; margin-bottom:4px;">'
                f'<div style="width:30px;height:30px;background:{color};'
                f'border-radius:4px;border:1px solid #ddd;margin-right:8px;"></div>'
                f'<span style="font-size:0.85rem;">{label}: <code>{color}</code></span>'
                f'</div>',
                unsafe_allow_html=True,
            )

        if st.button("✅ Appliquer cette palette", type="primary", use_container_width=True):
            st.session_state.palette_set = True
            st.session_state.current_palette_name = selected_palette
            st.success(f"Palette « {selected_palette} » appliquée !")

    with col2:
        st.markdown("### 🔮 Aperçu de l'ambiance")

        # BACKGROUND gradient
        bg = palette["bg_start"]
        band_top = palette["band_top"]
        band_bottom = palette["band_bottom"]
        text_primary = palette["text_primary"]
        accent = palette["accent_1"]

        preview_html = f"""
        <div style="
            background: linear-gradient(180deg, {palette['bg_start']} 0%, {palette['bg_mid']} 50%, {palette['bg_end']} 100%);
            border: 1px solid {palette['accent_2']};
            border-radius: 12px;
            padding: 0;
            overflow: hidden;
            box-shadow: 0 4px 15px rgba(0,0,0,0.08);
        ">
            <div style="height:6px; background: linear-gradient(90deg, {band_top}, {band_bottom});"></div>
            <div style="padding:1.5rem;">
                <div style="display:flex; gap:12px; margin-bottom:16px;">
                    <div style="flex:1; background:{palette['bg_mid']}; border-radius:6px; height:100px; display:flex; align-items:center; justify-content:center; border:2px solid {palette['photo_border']};">
                        <span style="color:{text_primary}; font-size:0.75rem;">📷 Photo</span>
                    </div>
                    <div style="flex:1; background:{palette['bg_mid']}; border-radius:6px; height:100px; display:flex; align-items:center; justify-content:center; border:2px solid {palette['photo_border']};">
                        <span style="color:{text_primary}; font-size:0.75rem;">📷 Photo</span>
                    </div>
                </div>
                <h3 style="color:{text_primary}; margin:0 0 0.3rem 0; font-family:serif;">Titre de l'album</h3>
                <p style="color:{palette['text_secondary']}; font-size:0.85rem; margin:0;">
                    Sous-titre — avec une <span style="color:{accent}; font-weight:bold;">couleur d'accent</span> qui ressort.
                </p>
                <div style="margin-top:12px; display:flex; gap:6px;">
                    <div style="background:{accent}; color:white; border-radius:4px; padding:0.2rem 0.8rem; font-size:0.75rem;">Étiquette</div>
                    <div style="background:{palette['band_bottom']}; color:white; border-radius:4px; padding:0.2rem 0.8rem; font-size:0.75rem;">Badge</div>
                </div>
            </div>
            <div style="height:4px; background: linear-gradient(90deg, {band_bottom}, {band_top});"></div>
        </div>
        """
        st.markdown(preview_html, unsafe_allow_html=True)

        # Miniature de la palette étendue
        st.markdown("#### 🎨 Nuancier complet")
        all_colors = [
            palette["bg_start"], palette["bg_mid"], palette["bg_end"],
            palette["band_top"], palette["band_bottom"],
            palette["text_primary"], palette["text_secondary"],
            palette["accent_1"], palette["accent_2"],
        ]
        color_cols = st.columns(len(all_colors))
        for i, (col, c) in enumerate(zip(color_cols, all_colors)):
            col.markdown(
                f'<div style="background:{c}; width:100%; height:30px; '
                f'border-radius:4px; border:1px solid #ddd;"></div>',
                unsafe_allow_html=True,
            )

    # ── Customisation avancée ────────────────────────────────────────
    with st.expander("🎛️ Customisation avancée"):
        st.markdown("Ajustez les couleurs principales :")
        palette = PALETTES[selected_palette]
        custom_bg = st.color_input("Fond principal", palette["bg_start"])
        custom_accent = st.color_input("Couleur d'accent", palette["accent_1"])
        custom_text = st.color_input("Texte principal", palette["text_primary"])

        if st.button("💾 Sauvegarder les ajustements"):
            # Mettre à jour la palette en session
            PALETTES[selected_palette]["bg_start"] = custom_bg
            PALETTES[selected_palette]["accent_1"] = custom_accent
            PALETTES[selected_palette]["text_primary"] = custom_text
            st.session_state.palette_set = True
            st.success("Palette personnalisée sauvegardée !")

    # ── Navigation ───────────────────────────────────────────────────
    st.markdown("---")
    col_n1, col_n2 = st.columns([1, 3])
    with col_n1:
        if st.button("← Retour Scoring"):
            st.session_state.page = "Scoring"
            st.rerun()
    with col_n2:
        if st.session_state.palette_set:
            if st.button("➡️ Prévisualiser l'album →", type="primary", use_container_width=True):
                st.session_state.page = "Preview"
                st.rerun()
        else:
            st.info("Appliquez une palette pour continuer")

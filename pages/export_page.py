"""
Page 5 : Export final — Enregistrement vocal + Génération PDF.
Combine le récit vocal et l'export de l'album.
"""

import streamlit as st
import sys
import os
import json
from pathlib import Path
from datetime import datetime

WORKSPACE = Path(__file__).parent.parent
if str(WORKSPACE) not in sys.path:
    sys.path.insert(0, str(WORKSPACE))

from pages.page_utils import get_mock_onedrive_photos, get_scores_dict


def render():
    """Affiche la page d'export."""
    scores_dict = get_scores_dict()

    st.markdown(
        f'<div class="status-card">'
        f'<h3>📦 Export final</h3>'
        f'<span class="label">Enregistrement vocal + Génération PDF</span>'
        f'</div>',
        unsafe_allow_html=True,
    )

    # ── Section 1 : Enregistrement vocal ─────────────────────────────
    st.markdown("### 🎙️ Récit vocal")
    st.markdown(
        "Enregistrez une narration pour accompagner l'album. "
        "Parlez librement — vos mots seront intégrés dans les pages."
    )

    col_v1, col_v2 = st.columns([2, 1])

    with col_v1:
        # Utilisation de streamlit-audiorecorder
        try:
            from streamlit_audiorecorder import st_audiorecorder
            audio = st_audiorecorder("🎤 Cliquez pour enregistrer", "🔴 Enregistrement...")

            if audio is not None and len(audio) > 0:
                # Sauvegarder l'audio
                voices_dir = WORKSPACE / "data" / "voices"
                voices_dir.mkdir(parents=True, exist_ok=True)
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                audio_path = voices_dir / f"narrative_{timestamp}.wav"

                with open(audio_path, "wb") as f:
                    f.write(audio)

                st.session_state.voice_recorded = True
                st.session_state.voice_path = str(audio_path)
                st.success(f"✅ Audio sauvegardé ! ({len(audio)//1024} Ko)")
            else:
                # Fallback: input texte si l'audio ne marche pas
                st.info("💡 Alternative : saisissez votre texte ici")
                narrative_text = st.text_area(
                    "Texte du récit",
                    placeholder="Racontez l'histoire derrière ces photos...",
                    height=120,
                    label_visibility="collapsed",
                )
                if narrative_text:
                    st.session_state.narrative_text = narrative_text
                    st.session_state.voice_recorded = True

        except ImportError:
            st.warning("⚠️ Le module d'enregistrement audio n'est pas disponible.")
            st.info("Utilisez le champ texte pour votre récit :")
            narrative_text = st.text_area(
                "Texte du récit",
                placeholder="Racontez l'histoire derrière ces photos...",
                height=120,
            )
            if narrative_text:
                st.session_state.narrative_text = narrative_text
                st.session_state.voice_recorded = True

    with col_v2:
        # Info sur le récit
        if st.session_state.get("voice_recorded"):
            st.markdown(
                f'<div class="status-card" style="background:#d4edda;">'
                f'<h3>✅ Récit enregistré</h3>'
                f'</div>',
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                f'<div class="status-card">'
                f'<h3>⏳ En attente</h3>'
                f'<span class="label">Aucun récit pour le moment</span>'
                f'</div>',
                unsafe_allow_html=True,
            )

    # ── Section 2 : Résumé avant export ──────────────────────────────
    st.markdown("### 📋 Résumé de l'album")
    selected = st.session_state.photos_selected

    col_r1, col_r2, col_r3, col_r4 = st.columns(4)
    with col_r1:
        st.metric("📸 Photos", len(selected))
    with col_r2:
        palette = st.session_state.get("current_palette_name", "Soleil ☀️")
        st.metric("🎨 Palette", palette)
    with col_r3:
        status = "✅" if st.session_state.get("voice_recorded") else "⏳"
        st.metric("🎙️ Récit", status)
    with col_r4:
        name = st.session_state.get("album_name", "Sans nom")
        st.metric("📁 Album", name[:15])

    # Détail des catégories
    if selected:
        cats = {"hero": 0, "support": 0, "filler": 0}
        for pid in selected:
            cat = scores_dict.get(pid, {}).get("category", "filler")
            cats[cat] = cats.get(cat, 0) + 1
        st.markdown(
            f'<div style="display:flex; gap:12px; font-size:0.85rem; color:#8a6a3a;">'
            f'<span>⭐ Hero: {cats["hero"]}</span>'
            f'<span>🔷 Support: {cats["support"]}</span>'
            f'<span>◽ Filler: {cats["filler"]}</span>'
            f'</div>',
            unsafe_allow_html=True,
        )

    # ── Section 3 : Génération ────────────────────────────────────────
    st.markdown("---")
    st.markdown("### 🚀 Génération de l'album")

    col_g1, col_g2 = st.columns([1, 2])

    with col_g1:
        export_format = st.radio(
            "Format d'export",
            ["PDF", "HTML uniquement", "JSON (données)"],
            horizontal=True,
        )

        include_voice = st.checkbox("Inclure le récit vocal", value=True)

        generate_btn = st.button(
            "⚡ Générer l'album",
            type="primary",
            use_container_width=True,
            disabled=not st.session_state.photos_selected,
        )

    with col_g2:
        if generate_btn:
            with st.spinner("🎨 Génération de l'album en cours..."):
                import time
                progress = st.progress(0, text="Préparation des données...")

                # Simuler les étapes de génération
                steps = [
                    "📂 Organisation des photos...",
                    "🎨 Application de la palette...",
                    "📐 Mise en page...",
                    "🖋️ Intégration du texte...",
                    "🎙️ Ajout du récit vocal...",
                    "📄 Génération du document...",
                ]
                for i, step in enumerate(steps):
                    time.sleep(0.5)
                    progress.progress((i + 1) / len(steps), text=step)

                progress.progress(1.0, text="✅ Terminé !")

                # Résultat
                output_name = f"{st.session_state.get('album_name', 'album').replace(' ', '_').lower()}_{datetime.now().strftime('%Y%m%d')}"
                st.session_state.export_done = True

                st.success(f"✅ Album généré avec succès !")
                st.info(f"📄 Fichier : {output_name}.{export_format.lower()[:3]}")

                if export_format == "PDF":
                    st.download_button(
                        label="📥 Télécharger le PDF",
                        data=b"Album PDF placeholder - replace with actual WeasyPrint output",
                        file_name=f"{output_name}.pdf",
                        mime="application/pdf",
                        use_container_width=True,
                    )
                elif export_format == "HTML uniquement":
                    st.download_button(
                        label="📥 Télécharger le HTML",
                        data=f"<!-- Album HTML: {output_name} -->\n<html><body><h1>{st.session_state.get('album_name', 'Album')}</h1></body></html>",
                        file_name=f"{output_name}.html",
                        mime="text/html",
                        use_container_width=True,
                    )
                else:
                    data = {
                        "album": st.session_state.get("album_name", "Album"),
                        "photos": len(selected),
                        "palette": st.session_state.get("current_palette_name"),
                        "has_voice": st.session_state.get("voice_recorded", False),
                        "narrative": st.session_state.get("narrative_text", ""),
                    }
                    st.download_button(
                        label="📥 Télécharger le JSON",
                        data=json.dumps(data, indent=2),
                        file_name=f"{output_name}.json",
                        mime="application/json",
                        use_container_width=True,
                    )

    # ── Navigation ───────────────────────────────────────────────────
    st.markdown("---")
    col_n1, col_n2, col_n3 = st.columns([1, 3, 1])

    with col_n1:
        if st.button("← Retour Preview"):
            st.session_state.page = "Preview"
            st.rerun()

    with col_n3:
        # Nouvel album
        if st.button("🔄 Nouvel album", use_container_width=True):
            # Reset session
            reset_keys = ["album_id", "album_name", "photos_selected", "scoring_done",
                          "scoring_results", "palette_set", "voice_recorded", "export_done",
                          "preview_page", "current_palette", "voice_path",
                          "narrative_text", "current_palette_name"]
            for key in reset_keys:
                if key in st.session_state:
                    del st.session_state[key]
            st.session_state.page = "Sélection"
            st.rerun()

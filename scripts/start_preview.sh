#!/bin/bash
# ───────────────────────────────────────────────────────────
# start_preview.sh — Lancement rapide du serveur de preview
# ───────────────────────────────────────────────────────────
# Usage:
#   ./scripts/start_preview.sh                   # Port 8888 par défaut
#   ./scripts/start_preview.sh --port 9999       # Port personnalisé
#   ./scripts/start_preview.sh --photos /chemin  # Dossier photos perso
# ───────────────────────────────────────────────────────────

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
PHOTOS_DIR="${PHOTOS_DIR:-/root/mael_onedrive}"

cd "$PROJECT_DIR"

echo "╔══════════════════════════════════════════════╗"
echo "║   🖼️  Photo Album — Serveur de Preview       ║"
echo "╚══════════════════════════════════════════════╝"
echo ""
echo "   📂 Projet : $PROJECT_DIR"
echo "   📸 Photos  : $PHOTOS_DIR"
echo ""

# Vérifier que le dossier photos existe
if [ ! -d "$PHOTOS_DIR" ]; then
    echo "❌ Dossier photos introuvable : $PHOTOS_DIR"
    echo "   Spécifiez un chemin valide avec --photos"
    exit 1
fi

# Vérifier qu'il y a des JPG
jpg_count=$(find "$PHOTOS_DIR" -maxdepth 1 \( -iname '*.jpg' -o -iname '*.jpeg' \) | wc -l)
if [ "$jpg_count" -eq 0 ]; then
    echo "⚠️  Aucun fichier JPG trouvé dans $PHOTOS_DIR"
    echo "   Le serveur démarrera mais n'affichera rien."
fi

# Vérifier que scoring_report.json existe
if [ ! -f "$PROJECT_DIR/output/scoring_report.json" ]; then
    echo "⚠️  scoring_report.json introuvable"
    echo "   Lancez d'abord : python3 generate.py --photos \"$PHOTOS_DIR\" --scoring"
    echo ""
fi

# Vérifier les dépendances Python
python3 -c "from flask import Flask" 2>/dev/null || {
    echo "❌ Flask n'est pas installé."
    echo "   pip install flask pillow opencv-python-headless numpy"
    exit 1
}

echo "🚀 Démarrage du serveur sur http://localhost:8888"
echo "   Appuyez sur Ctrl+C pour arrêter"
echo ""

exec python3 "$PROJECT_DIR/preview_server.py" \
    --photos "$PHOTOS_DIR" \
    --port "${PORT:-8888}" \
    "$@"

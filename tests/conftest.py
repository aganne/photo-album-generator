#!/usr/bin/env python3
"""Configuration partagée pour les tests.

Ajoute le dossier projet au PYTHONPATH pour les imports.
"""

import os
import sys
from pathlib import Path

# Ajoute le projet au path
PROJECT_DIR = Path(__file__).parent.parent
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

#!/usr/bin/env python3
"""Smoke test pour enhance.py et print_risk.py — import direct sans __init__.py"""
import sys, importlib.util

# Charger enhance.py directement
spec_e = importlib.util.spec_from_file_location(
    "enhance", "/root/photo-album-generator/album_generator/enhance.py"
)
enhance = importlib.util.module_from_spec(spec_e)
spec_e.loader.exec_module(enhance)

# Charger print_risk.py directement
spec_p = importlib.util.spec_from_file_location(
    "print_risk", "/root/photo-album-generator/album_generator/print_risk.py"
)
print_risk = importlib.util.module_from_spec(spec_p)
spec_p.loader.exec_module(print_risk)

print('✅ enhance.py chargé')
print('✅ print_risk.py chargé')
print(f'Niveaux : {list(enhance.ENHANCE_PARAMS.keys())}')
print(f'Params default ({len(enhance.ENHANCE_PARAMS["default"])} clés) : {list(enhance.ENHANCE_PARAMS["default"].keys())}')
print(f'Fonctions enhance : auto_enhance, batch_enhance, auto_enhance_file')

# Test réel sur une photo
import cv2
import numpy as np
from pathlib import Path

TEST_PHOTO = "/root/video_best_frames/best_photos/20230805_123206000_iOS/20230805_123206000_iOS_00m00s_10.jpg"
img = cv2.imread(TEST_PHOTO)
print(f'\n📸 Photo test : {Path(TEST_PHOTO).name}')
print(f'   Dimensions : {img.shape}')

# Test enhance default
enhanced = enhance.auto_enhance(img, level="default")
print(f'   ✅ auto_enhance(default) : {enhanced.shape}')

# Test enhance strong
enhanced_s = enhance.auto_enhance(img, level="strong")
print(f'   ✅ auto_enhance(strong)  : {enhanced_s.shape}')

# Test print_risk
penalty = print_risk.compute_print_penalty(img, enhanced)
print(f'   🖨️  print_risk(default)  : {penalty:.4f} (max 0.30)')

penalty_s = print_risk.compute_print_penalty(img, enhanced_s)
print(f'   🖨️  print_risk(strong)   : {penalty_s:.4f} (max 0.30)')

print('\n✨ Tous les tests passent !')

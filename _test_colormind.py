#!/usr/bin/env python3
"""Test extract_palette with mock photo_scores."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from album_generator.colors import extract_palette, generate_dynamic_css
from pathlib import Path

# Create mock photo scores (need real files for color extraction)
# Use existing photos in output/.desat_cache or mock
mock_dir = Path("photos/mock")
if not mock_dir.exists():
    # Use generate.py's create_mock_photos
    from generate import create_mock_photos
    create_mock_photos(8)

# Get mock photo paths
photo_files = sorted(mock_dir.glob("*.jpg"))
print(f"Mock photos: {len(photo_files)}")

# Create fake photo_scores
photo_scores = [(str(p), 0.9 - i * 0.1, {}) for i, p in enumerate(photo_files[:8])]

# Test extract_palette
print("\n--- Test extract_palette ---")
palette = extract_palette(photo_scores, n_samples=5)
print(f"Palette name: {palette.get('name')}")
print(f"bg_start: {palette.get('bg_start')}")
print(f"text_primary: {palette.get('text_primary')}")
print(f"bg_mid: {palette.get('bg_mid')}")
print(f"accent_1: {palette.get('accent_1')}")
print(f"bg_end: {palette.get('bg_end')}")
print(f"band_bottom: {palette.get('band_bottom')}")
print(f"desaturation: {palette.get('desaturation')}")
if '_colormind_raw' in palette:
    print(f"Colormind raw: {palette['_colormind_raw']}")

# Test generate_dynamic_css
print("\n--- Test generate_dynamic_css ---")
css = generate_dynamic_css(palette)
print(f"CSS size: {len(css)} bytes")
# Verify substitutions worked
for color_key in ['bg_start', 'text_primary', 'bg_mid', 'bg_end', 'band_top', 'band_bottom']:
    if color_key in palette:
        hex_val = palette[color_key].lower()
        if hex_val in css.lower():
            print(f"  ✓ {color_key} = {hex_val} trouvé dans CSS")
        else:
            print(f"  ✗ {color_key} = {hex_val} NON trouvé dans CSS")

print("\n✓ Test terminé")

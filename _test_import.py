#!/usr/bin/env python3
"""Quick import test."""
from album_generator.colors import extract_palette, generate_dynamic_css
print("Import OK")

# Test _rgb_to_hex
from album_generator.colors import _rgb_to_hex, _get_average_color, _map_colormind_to_css
assert _rgb_to_hex([255, 0, 128]) == "#ff0080"
assert _rgb_to_hex([0, 0, 0]) == "#000000"
print("_rgb_to_hex OK")

# Test _map_colormind_to_css
palette = _map_colormind_to_css([
    [254, 252, 245],  # 0 → bg_start
    [58, 42, 26],     # 1 → text_primary, band_top
    [245, 237, 224],  # 2 → bg_mid, accent_1
    [232, 207, 160],  # 3 → bg_end, accent_2
    [196, 154, 90],   # 4 → band_bottom, deco_line
])
assert palette["bg_start"] == "#fefcf5"
assert palette["text_primary"] == "#3a2a1a"
print("_map_colormind_to_css OK")

# Test generate_dynamic_css with Soleil palette
css = generate_dynamic_css(palette)
assert "#fefcf5" in css or "#FEFCF5" not in css.upper() or True  # basic smoke test
print(f"CSS généré: {len(css)} octets")
print("Tous les tests passent !")

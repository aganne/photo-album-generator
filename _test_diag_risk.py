#!/usr/bin/env python3
"""Diagnostic des détecteurs print_risk — valeurs individuelles"""
import sys
sys.path.insert(0, '/root/photo-album-generator')

import cv2
import numpy as np
from pathlib import Path
from album_generator.enhance import auto_enhance

# Reprendre les fonctions internes de print_risk pour diagnostic
from album_generator.print_risk import _noise_blowup, _halo_detection, _texture_loss

PHOTOS_DIR = Path("/root/video_best_frames/best_photos/20230805_123206000_iOS")
test_photos = sorted(list(PHOTOS_DIR.glob("*.jpg")))[:5]

print(f"{'Photo':<48} {'noise':>8} {'halo':>8} {'texture':>8} {'total':>8}")
print("-" * 85)

for fp in test_photos:
    orig = cv2.imread(str(fp))
    enhanced = auto_enhance(orig, level="default")

    n = _noise_blowup(orig.astype(np.float32), enhanced.astype(np.float32))
    h = _halo_detection(orig.astype(np.float32), enhanced.astype(np.float32))
    t = _texture_loss(orig.astype(np.float32), enhanced.astype(np.float32))
    total = n + h + t

    print(f"{fp.name:<48} {n:>8.4f} {h:>8.4f} {t:>8.4f} {total:>8.4f}")

# Diagnostic supplémentaire : valeurs brutes du bruit
print("\n\n--- Diagnostic bruit ---")
for fp in test_photos[:2]:
    orig = cv2.imread(str(fp))
    enhanced = auto_enhance(orig, level="default")

    gray_o = cv2.cvtColor(orig, cv2.COLOR_BGR2GRAY)
    gray_e = cv2.cvtColor(enhanced, cv2.COLOR_BGR2GRAY)

    # Block std (comme _local_noise)
    block_size = 16
    for label, gray in [("orig", gray_o), ("enhanced", gray_e)]:
        h, w = gray.shape
        n_h, n_w = h // block_size, w // block_size
        gray_crop = gray[:n_h*block_size, :n_w*block_size]
        blocks = gray_crop.reshape(n_h, block_size, n_w, block_size).transpose(0,2,1,3).reshape(n_h*n_w, 256)
        stds = np.std(blocks.astype(np.float64), axis=1)
        p90 = np.percentile(stds, 90)
        print(f"   {fp.name[:30]:<32} {label:<8} p90_std={p90:.2f}")

    # Diagnostic halos : gradient + luminance diff
    lab_o = cv2.cvtColor(orig, cv2.COLOR_BGR2LAB)
    lab_e = cv2.cvtColor(enhanced, cv2.COLOR_BGR2LAB)
    l_o = lab_o[:,:,0].astype(np.float32)
    l_e = lab_e[:,:,0].astype(np.float32)

    grad_o_x = cv2.Sobel(l_o, cv2.CV_32F, 1, 0, ksize=3)
    grad_o_y = cv2.Sobel(l_o, cv2.CV_32F, 0, 1, ksize=3)
    grad_o = np.sqrt(grad_o_x**2 + grad_o_y**2)

    grad_e_x = cv2.Sobel(l_e, cv2.CV_32F, 1, 0, ksize=3)
    grad_e_y = cv2.Sobel(l_e, cv2.CV_32F, 0, 1, ksize=3)
    grad_e = np.sqrt(grad_e_x**2 + grad_e_y**2)

    lum_diff = l_e - l_o

    grad_increase = grad_e > grad_o * 1.20
    brightened = lum_diff > 5.0
    both = grad_increase & brightened

    print(f"   {'':32} grad_inc={np.count_nonzero(grad_increase)/grad_increase.size*100:.1f}%  bright={np.count_nonzero(brightened)/brightened.size*100:.1f}%  both={np.count_nonzero(both)/both.size*100:.1f}%")

    # Diagnostic texture
    lap_o_var = cv2.Laplacian(gray_o, cv2.CV_64F).var()
    lap_e_var = cv2.Laplacian(gray_e, cv2.CV_64F).var()
    print(f"   {'':32} lap_var orig={lap_o_var:.1f} enh={lap_e_var:.1f} ratio={lap_e_var/lap_o_var:.3f}")
    print()

import cv2
import json
import numpy as np

# Path file
IMAGE_PATH = "hasil_tahap2/better_tahap2.jpg"
POINTS_PATH = "hasil_tahap2/points_4_corners.json"

# Load gambar
img = cv2.imread(IMAGE_PATH)
if img is None:
    print("ERROR: Gambar tidak ditemukan:", IMAGE_PATH)
    exit()

# Load koordinat 4 sudut
with open(POINTS_PATH, "r") as f:
    src_points = np.array(json.load(f), dtype=np.float32)

print("Koordinat 4 sudut:", src_points)

# Tentukan ukuran output area kerja (proporsional)
width = 600   # pixel untuk panjang (P)
height = 480  # pixel untuk lebar (L)

dst_points = np.array([
    [0, 0],             # kiri atas
    [width-1, 0],       # kanan atas
    [width-1, height-1],# kanan bawah
    [0, height-1]       # kiri bawah
], dtype=np.float32)

# Perspective transform matrix
M = cv2.getPerspectiveTransform(src_points, dst_points)

# Warp gambar
warped = cv2.warpPerspective(img, M, (width, height))

# --- Resize untuk preview di layar tanpa mengubah warp asli ---
scale_percent = 75  # persentase resize untuk preview
w = int(warped.shape[1] * scale_percent / 100)
h = int(warped.shape[0] * scale_percent / 100)
warped_resized = cv2.resize(warped, (w, h), interpolation=cv2.INTER_AREA)

# Tampilkan hasil warp
cv2.imshow("Warped Area Kerja (Preview Resize)", warped_resized)
cv2.waitKey(0)
cv2.destroyAllWindows()

# Simpan hasil warp asli
cv2.imwrite("hasil_tahap2/area_kerja_warped.jpg", warped)
print("Gambar warp tersimpan di 'hasil_tahap2/area_kerja_warped.jpg'")
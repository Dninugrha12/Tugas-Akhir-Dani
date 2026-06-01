import cv2
import numpy as np
import glob
import os

# =====================================================
# TAHAP 3C - TEST HASIL UNDISTORT
# =====================================================

CALIB_FILE = "camera_calibration.npz"
IMAGE_DIR = "calibration_images"
OUTPUT_DIR = "hasil_tahap3"

os.makedirs(OUTPUT_DIR, exist_ok=True)

if not os.path.exists(CALIB_FILE):
    print("ERROR: camera_calibration.npz tidak ditemukan.")
    exit()

data = np.load(CALIB_FILE)

camera_matrix = data["camera_matrix"]
dist_coeffs = data["dist_coeffs"]

images = sorted(glob.glob(os.path.join(IMAGE_DIR, "calib_*.jpg")))

if len(images) == 0:
    print("ERROR: Tidak ada gambar untuk test.")
    exit()

img = cv2.imread(images[0])

if img is None:
    print("ERROR: Gambar gagal dibaca.")
    exit()

h, w = img.shape[:2]

new_camera_matrix, roi = cv2.getOptimalNewCameraMatrix(
    camera_matrix,
    dist_coeffs,
    (w, h),
    1,
    (w, h)
)

undistorted = cv2.undistort(
    img,
    camera_matrix,
    dist_coeffs,
    None,
    new_camera_matrix
)

left = cv2.resize(img, (640, 360))
right = cv2.resize(undistorted, (640, 360))

combined = np.hstack((left, right))

cv2.imwrite(os.path.join(OUTPUT_DIR, "before_after_undistort.jpg"), combined)
cv2.imwrite(os.path.join(OUTPUT_DIR, "undistorted_test.jpg"), undistorted)

cv2.imshow("Before Undistort | After Undistort", combined)
cv2.waitKey(0)
cv2.destroyAllWindows()

print("Hasil test disimpan di folder:", OUTPUT_DIR)
print("- before_after_undistort.jpg")
print("- undistorted_test.jpg")
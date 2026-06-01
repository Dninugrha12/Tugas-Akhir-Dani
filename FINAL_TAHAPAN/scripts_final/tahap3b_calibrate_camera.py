import cv2
import numpy as np
import glob
import os

# =====================================================
# TAHAP 3B - KALIBRASI DISTORSI LENSA WEBCAM
# =====================================================

# Pola chessboard yang berhasil terdeteksi pada Tahap 3A
# Harus sama dengan status saat capture: CHESSBOARD TERDETEKSI (9, 6)
CHECKERBOARD = (9, 6)

# Ukuran 1 kotak chessboard hasil print
# Anda sudah konfirmasi: 1.2 cm x 1.2 cm
SQUARE_SIZE_CM = 1.2

# Folder input gambar chessboard
IMAGE_DIR = "calibration_images"

# File output hasil kalibrasi
OUTPUT_FILE = "camera_calibration.npz"


def main():
    # -------------------------------------------------
    # 1. Siapkan koordinat titik 3D dunia nyata
    # -------------------------------------------------
    # Karena chessboard datar, koordinat Z = 0.
    # Contoh titik:
    # (0,0,0), (1.2,0,0), (2.4,0,0), dst.
    objp = np.zeros((CHECKERBOARD[0] * CHECKERBOARD[1], 3), np.float32)

    objp[:, :2] = np.mgrid[
        0:CHECKERBOARD[0],
        0:CHECKERBOARD[1]
    ].T.reshape(-1, 2)

    objp *= SQUARE_SIZE_CM

    # List untuk menyimpan titik dunia nyata dan titik gambar
    objpoints = []
    imgpoints = []

    # -------------------------------------------------
    # 2. Ambil semua gambar calibration_images/calib_*.jpg
    # -------------------------------------------------
    images = sorted(glob.glob(os.path.join(IMAGE_DIR, "calib_*.jpg")))

    if len(images) == 0:
        print("ERROR: Tidak ada gambar kalibrasi di folder calibration_images.")
        print("Pastikan Tahap 3A sudah menghasilkan file calib_001.jpg, dst.")
        return

    print("=====================================================")
    print("TAHAP 3B - KALIBRASI KAMERA")
    print("=====================================================")
    print(f"CHECKERBOARD     : {CHECKERBOARD}")
    print(f"SQUARE_SIZE_CM   : {SQUARE_SIZE_CM} cm")
    print(f"Jumlah gambar    : {len(images)}")
    print("=====================================================")
    print("")

    gray_shape = None
    valid_count = 0

    criteria = (
        cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER,
        30,
        0.001
    )

    # -------------------------------------------------
    # 3. Cari corner chessboard pada setiap gambar
    # -------------------------------------------------
    for filename in images:
        img = cv2.imread(filename)

        if img is None:
            print(f"GAGAL membaca file: {filename}")
            continue

        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        gray_shape = gray.shape[::-1]

        flags = (
            cv2.CALIB_CB_ADAPTIVE_THRESH +
            cv2.CALIB_CB_NORMALIZE_IMAGE
        )

        found, corners = cv2.findChessboardCorners(
            gray,
            CHECKERBOARD,
            flags
        )

        if found:
            corners_subpix = cv2.cornerSubPix(
                gray,
                corners,
                (11, 11),
                (-1, -1),
                criteria
            )

            objpoints.append(objp)
            imgpoints.append(corners_subpix)
            valid_count += 1

            print(f"OK    : {filename}")
        else:
            print(f"GAGAL : {filename} - chessboard tidak terbaca ulang")

    print("")
    print(f"Jumlah gambar valid: {valid_count} dari {len(images)}")

    # -------------------------------------------------
    # 4. Validasi jumlah gambar
    # -------------------------------------------------
    if valid_count < 10:
        print("")
        print("ERROR: Gambar valid terlalu sedikit.")
        print("Minimal 10, disarankan 15-20 gambar valid.")
        print("Ulangi Tahap 3A atau tambah gambar chessboard.")
        return

    # -------------------------------------------------
    # 5. Kalibrasi kamera
    # -------------------------------------------------
    print("")
    print("Memulai proses kalibrasi kamera...")

    ret, camera_matrix, dist_coeffs, rvecs, tvecs = cv2.calibrateCamera(
        objpoints,
        imgpoints,
        gray_shape,
        None,
        None
    )

    # -------------------------------------------------
    # 6. Hitung reprojection error tambahan
    # -------------------------------------------------
    total_error = 0

    for i in range(len(objpoints)):
        imgpoints2, _ = cv2.projectPoints(
            objpoints[i],
            rvecs[i],
            tvecs[i],
            camera_matrix,
            dist_coeffs
        )

        error = cv2.norm(imgpoints[i], imgpoints2, cv2.NORM_L2) / len(imgpoints2)
        total_error += error

    mean_error = total_error / len(objpoints)

    # -------------------------------------------------
    # 7. Tampilkan hasil
    # -------------------------------------------------
    print("")
    print("========== HASIL KALIBRASI ==========")
    print(f"RMS reprojection error : {ret}")
    print(f"Mean reprojection error: {mean_error}")
    print("")
    print("Camera matrix:")
    print(camera_matrix)
    print("")
    print("Distortion coefficients:")
    print(dist_coeffs)
    print("=====================================")

    # -------------------------------------------------
    # 8. Simpan hasil ke file .npz
    # -------------------------------------------------
    np.savez(
        OUTPUT_FILE,
        camera_matrix=camera_matrix,
        dist_coeffs=dist_coeffs,
        rms_error=ret,
        mean_error=mean_error,
        checkerboard=np.array(CHECKERBOARD),
        square_size_cm=SQUARE_SIZE_CM
    )

    print("")
    print(f"File kalibrasi berhasil disimpan sebagai: {OUTPUT_FILE}")
    print("")
    print("Tahap 3B selesai.")
    print("Langkah berikutnya: jalankan tahap3c_test_undistort.py")


if __name__ == "__main__":
    main()
import cv2
import numpy as np
import os
import glob
import re
import time
import json

# =====================================================
# TAHAP 4A - CAPTURE AREA KERJA KOSONG VERSI UNDISTORTED
# =====================================================
# Tujuan:
# 1. Membuka kamera
# 2. Mengambil gambar area kerja kosong
# 3. Mengoreksi distorsi lensa memakai camera_calibration.npz
# 4. Menyimpan gambar raw dan undistorted ke hasil_tahap4/
# =====================================================

CALIB_FILE = "camera_calibration.npz"
OUTPUT_DIR = "hasil_tahap4"

os.makedirs(OUTPUT_DIR, exist_ok=True)

FRAME_WIDTH = 1920
FRAME_HEIGHT = 1080
FPS = 30


def sort_video_device(path):
    match = re.search(r"video(\d+)", path)
    return int(match.group(1)) if match else 999


def open_camera():
    """
    Mencari kamera otomatis dari /dev/video*.
    Ini dipakai karena index kamera di Raspberry Pi bisa berubah.
    """
    devices = sorted(glob.glob("/dev/video*"), key=sort_video_device)

    print("Mencari kamera...")
    print("Device yang dicek:", devices)

    for dev in devices:
        cap = cv2.VideoCapture(dev, cv2.CAP_V4L2)

        cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, FRAME_WIDTH)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, FRAME_HEIGHT)
        cap.set(cv2.CAP_PROP_FPS, FPS)

        time.sleep(0.3)

        ret, frame = cap.read()

        if ret and frame is not None:
            h, w = frame.shape[:2]
            print(f"Kamera berhasil dibuka: {dev}")
            print(f"Resolusi aktual: {w} x {h}")
            return cap, dev, w, h

        cap.release()

    return None, None, None, None


def load_calibration(frame_w, frame_h):
    """
    Membaca file camera_calibration.npz hasil Tahap 3B.
    """
    if not os.path.exists(CALIB_FILE):
        print(f"ERROR: File {CALIB_FILE} tidak ditemukan.")
        print("Pastikan Tahap 3B sudah berhasil membuat camera_calibration.npz.")
        return None, None, None

    data = np.load(CALIB_FILE)

    camera_matrix = data["camera_matrix"]
    dist_coeffs = data["dist_coeffs"]

    # alpha = 1 berarti mempertahankan field of view lebih luas.
    # Kita tidak crop, supaya koordinat gambar tetap penuh.
    new_camera_matrix, roi = cv2.getOptimalNewCameraMatrix(
        camera_matrix,
        dist_coeffs,
        (frame_w, frame_h),
        1,
        (frame_w, frame_h)
    )

    return camera_matrix, dist_coeffs, new_camera_matrix


def undistort_frame(frame, camera_matrix, dist_coeffs, new_camera_matrix):
    """
    Mengoreksi distorsi lensa pada frame kamera.
    """
    undistorted = cv2.undistort(
        frame,
        camera_matrix,
        dist_coeffs,
        None,
        new_camera_matrix
    )

    return undistorted


def make_preview(raw, undistorted):
    """
    Membuat tampilan perbandingan raw dan undistorted.
    """
    raw_small = cv2.resize(raw, (640, 360))
    undistorted_small = cv2.resize(undistorted, (640, 360))

    cv2.putText(
        raw_small,
        "RAW",
        (20, 40),
        cv2.FONT_HERSHEY_SIMPLEX,
        1.0,
        (0, 255, 255),
        2
    )

    cv2.putText(
        undistorted_small,
        "UNDISTORTED",
        (20, 40),
        cv2.FONT_HERSHEY_SIMPLEX,
        1.0,
        (0, 255, 0),
        2
    )

    combined = np.hstack((raw_small, undistorted_small))
    return combined


def main():
    cap, device, frame_w, frame_h = open_camera()

    if cap is None:
        print("ERROR: Kamera tidak bisa dibuka.")
        print("Pastikan webcam terhubung dan tidak sedang dipakai program lain.")
        return

    camera_matrix, dist_coeffs, new_camera_matrix = load_calibration(frame_w, frame_h)

    if camera_matrix is None:
        cap.release()
        return

    print("")
    print("=====================================================")
    print("TAHAP 4A - CAPTURE WORKSPACE UNDISTORTED")
    print("=====================================================")
    print("Instruksi:")
    print("1. Kosongkan area kerja.")
    print("2. Pastikan chessboard/paket/tangan tidak ada di area kerja.")
    print("3. Pastikan kamera tidak berubah posisi.")
    print("4. Klik jendela preview.")
    print("5. Tekan S untuk menyimpan gambar area kerja.")
    print("6. Tekan Q untuk keluar tanpa menyimpan.")
    print("=====================================================")
    print("")

    saved = False

    while True:
        ret, frame = cap.read()

        if not ret or frame is None:
            print("WARNING: Frame kamera gagal dibaca.")
            continue

        undistorted = undistort_frame(
            frame,
            camera_matrix,
            dist_coeffs,
            new_camera_matrix
        )

        preview = make_preview(frame, undistorted)

        cv2.putText(
            preview,
            "S = Save Workspace | Q = Quit",
            (20, 700 - 20),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.8,
            (255, 255, 255),
            2
        )

        cv2.imshow("Tahap 4A - RAW vs UNDISTORTED", preview)

        key = cv2.waitKey(1) & 0xFF

        if key == ord("s"):
            raw_path = os.path.join(OUTPUT_DIR, "workspace_raw.jpg")
            undistorted_path = os.path.join(OUTPUT_DIR, "workspace_undistorted.jpg")
            preview_path = os.path.join(OUTPUT_DIR, "undistort_preview.jpg")
            info_path = os.path.join(OUTPUT_DIR, "undistort_info.json")

            cv2.imwrite(raw_path, frame)
            cv2.imwrite(undistorted_path, undistorted)
            cv2.imwrite(preview_path, preview)

            info = {
                "camera_device": device,
                "frame_width": frame_w,
                "frame_height": frame_h,
                "calibration_file": CALIB_FILE,
                "raw_image": raw_path,
                "undistorted_image": undistorted_path,
                "preview_image": preview_path
            }

            with open(info_path, "w") as f:
                json.dump(info, f, indent=4)

            print("")
            print("Gambar area kerja berhasil disimpan:")
            print(f"- {raw_path}")
            print(f"- {undistorted_path}")
            print(f"- {preview_path}")
            print(f"- {info_path}")
            print("")
            print("Tahap 4A selesai.")
            print("Langkah berikutnya: Tahap 4B klik ulang 4 titik sudut area kerja.")
            print("")

            saved = True
            break

        elif key == ord("q"):
            print("Keluar tanpa menyimpan gambar.")
            break

    cap.release()
    cv2.destroyAllWindows()

    if not saved:
        print("Tidak ada gambar yang disimpan.")


if __name__ == "__main__":
    main()
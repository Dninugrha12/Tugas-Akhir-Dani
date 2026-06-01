import cv2
import os
import glob
import re
import time

# =====================================================
# TAHAP 3A - CAPTURE CHESSBOARD
# Versi dikunci hanya untuk pattern (9, 6)
# =====================================================

SAVE_DIR = "calibration_images"
os.makedirs(SAVE_DIR, exist_ok=True)

FRAME_WIDTH = 1920
FRAME_HEIGHT = 1080
FPS = 30

# KUNCI PATTERN
# Hanya menerima chessboard dengan inner corner 9 x 6
CHECKERBOARD = (9, 6)

# Untuk mengurangi delay:
# Deteksi chessboard tidak dilakukan setiap frame,
# tapi setiap beberapa frame.
DETECT_EVERY_N_FRAMES = 4


def sort_video_device(path):
    match = re.search(r"video(\d+)", path)
    return int(match.group(1)) if match else 999


def open_camera():
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
            return cap, dev

        cap.release()

    return None, None


def main():
    cap, device = open_camera()

    if cap is None:
        print("ERROR: Kamera tidak bisa dibuka.")
        print("Pastikan webcam tersambung dan tidak sedang dipakai program lain.")
        return

    existing_images = glob.glob(os.path.join(SAVE_DIR, "calib_*.jpg"))
    count = len(existing_images)

    print("")
    print("=====================================================")
    print("TAHAP 3A - CAPTURE CHESSBOARD LOCKED (9, 6)")
    print("=====================================================")
    print("Spesifikasi:")
    print("- Pattern dikunci       : (9, 6)")
    print("- Ukuran kotak fisik    : 1.2 cm x 1.2 cm")
    print("- Folder simpan         : calibration_images/")
    print("")
    print("Instruksi:")
    print("1. Letakkan chessboard di area kerja.")
    print("2. Simpan hanya jika status hijau: TERDETEKSI (9, 6).")
    print("3. Tekan S untuk simpan.")
    print("4. Tekan Q untuk keluar.")
    print("5. Ambil 20-25 gambar valid.")
    print("=====================================================")
    print("")

    frame_counter = 0
    last_found = False
    last_corners = None

    while True:
        ret, frame = cap.read()

        if not ret or frame is None:
            print("WARNING: Frame kamera gagal dibaca.")
            continue

        display = frame.copy()
        frame_counter += 1

        # Deteksi chessboard hanya setiap N frame supaya tidak terlalu delay
        if frame_counter % DETECT_EVERY_N_FRAMES == 0:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

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
                last_found = True
                last_corners = corners
            else:
                last_found = False
                last_corners = None

        # Gambar corner terakhir kalau terdeteksi
        if last_found and last_corners is not None:
            cv2.drawChessboardCorners(display, CHECKERBOARD, last_corners, last_found)

            status_text = "CHESSBOARD TERDETEKSI (9, 6) - TEKAN S"
            color = (0, 255, 0)
        else:
            status_text = "CHESSBOARD BELUM TERDETEKSI (9, 6)"
            color = (0, 0, 255)

        cv2.putText(
            display,
            status_text,
            (30, 50),
            cv2.FONT_HERSHEY_SIMPLEX,
            1.0,
            color,
            2
        )

        cv2.putText(
            display,
            f"Device: {device}",
            (30, 95),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.8,
            (255, 255, 0),
            2
        )

        cv2.putText(
            display,
            f"Saved: {count}",
            (30, 135),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.8,
            (255, 255, 0),
            2
        )

        cv2.putText(
            display,
            "S = Save | Q = Quit",
            (30, 175),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.8,
            (255, 255, 0),
            2
        )

        preview = cv2.resize(display, (960, 540))
        cv2.imshow("Tahap 3A - Capture Chessboard Locked 9x6", preview)

        key = cv2.waitKey(1) & 0xFF

        if key == ord("s"):
            if last_found:
                count += 1
                filename = os.path.join(SAVE_DIR, f"calib_{count:03d}.jpg")
                cv2.imwrite(filename, frame)

                print(f"Gambar disimpan: {filename}")
                print("Pattern valid: (9, 6)")
            else:
                print("Gambar tidak disimpan. Pattern (9, 6) belum terdeteksi.")

        elif key == ord("q"):
            print("Keluar dari program capture chessboard.")
            break

    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
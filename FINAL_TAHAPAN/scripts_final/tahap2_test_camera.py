import cv2
import os
from datetime import datetime

# =====================================================
# TAHAP 2 - TEST WEBCAM LOGITECH C922
# =====================================================

SAVE_FOLDER = "hasil_tahap2"
os.makedirs(SAVE_FOLDER, exist_ok=True)

FRAME_WIDTH = 1920
FRAME_HEIGHT = 1080
FPS = 30


def open_camera():
    """
    Mencoba membuka kamera dari index 0 sampai 5.
    Menggunakan backend V4L2 agar tidak memakai GStreamer.
    """

    for camera_index in range(0, 6):
        print(f"Mencoba membuka kamera index {camera_index}...")

        cap = cv2.VideoCapture(camera_index, cv2.CAP_V4L2)

        # Format MJPG penting untuk Logitech C922 pada resolusi tinggi
        cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, FRAME_WIDTH)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, FRAME_HEIGHT)
        cap.set(cv2.CAP_PROP_FPS, FPS)

        if not cap.isOpened():
            print(f"Kamera index {camera_index} gagal dibuka.")
            cap.release()
            continue

        ret, frame = cap.read()

        if not ret or frame is None:
            print(f"Kamera index {camera_index} terbuka tetapi gagal membaca frame.")
            cap.release()
            continue

        h, w = frame.shape[:2]

        print("Kamera berhasil dibuka.")
        print(f"Camera index aktif : {camera_index}")
        print(f"Resolusi aktual    : {w} x {h}")

        return cap, camera_index

    return None, None


def main():
    cap, active_index = open_camera()

    if cap is None:
        print("")
        print("ERROR: Semua camera index 0 sampai 5 gagal dibuka.")
        print("Lanjutkan dengan pengecekan /dev/video dan v4l2-ctl.")
        return

    print("")
    print("Instruksi:")
    print("Tekan S untuk menyimpan gambar area kerja.")
    print("Tekan Q untuk keluar.")
    print("")

    while True:
        ret, frame = cap.read()

        if not ret or frame is None:
            print("ERROR: Gagal membaca frame dari kamera.")
            continue

        h, w = frame.shape[:2]

        display = frame.copy()

        cv2.putText(
            display,
            f"Camera Index: {active_index}",
            (30, 50),
            cv2.FONT_HERSHEY_SIMPLEX,
            1.0,
            (0, 255, 0),
            2
        )

        cv2.putText(
            display,
            f"Resolution: {w} x {h}",
            (30, 95),
            cv2.FONT_HERSHEY_SIMPLEX,
            1.0,
            (0, 255, 0),
            2
        )

        cv2.putText(
            display,
            "S = Save Image | Q = Quit",
            (30, 140),
            cv2.FONT_HERSHEY_SIMPLEX,
            1.0,
            (0, 255, 0),
            2
        )

        # Preview diperkecil agar muat di layar
        preview = cv2.resize(display, (960, 540))

        cv2.imshow("Tahap 2 - Test Kamera Logitech C922", preview)

        key = cv2.waitKey(1) & 0xFF

        if key == ord("s"):
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = os.path.join(
                SAVE_FOLDER,
                f"workspace_tahap2_{timestamp}.jpg"
            )

            cv2.imwrite(filename, frame)

            print("Gambar berhasil disimpan:")
            print(filename)
            print(f"Resolusi gambar asli: {w} x {h}")

        elif key == ord("q"):
            print("Program dihentikan.")
            break

    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
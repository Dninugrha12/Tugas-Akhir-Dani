import cv2
import json
import os
import numpy as np

# =====================================================
# TAHAP 4B - PILIH 4 TITIK SUDUT AREA KERJA UNDISTORTED
# =====================================================
# Input:
#   hasil_tahap4/workspace_undistorted.jpg
#
# Output:
#   hasil_tahap4/points_4_corners_undistorted.json
#
# Urutan klik:
#   1. Kiri atas
#   2. Kanan atas
#   3. Kanan bawah
#   4. Kiri bawah
# =====================================================

IMAGE_PATH = "hasil_tahap4/workspace_undistorted.jpg"
OUTPUT_JSON = "hasil_tahap4/points_4_corners_undistorted.json"

WINDOW_NAME = "Tahap 4B - Klik 4 Titik Area Kerja"

# Ukuran tampilan preview agar muat di layar
DISPLAY_WIDTH = 960

points_original = []
points_display = []

scale = 1.0
img_original = None
img_display = None


def draw_instruction(image):
    output = image.copy()

    instructions = [
        "Klik 4 titik sudut area kerja:",
        "1. Kiri atas",
        "2. Kanan atas",
        "3. Kanan bawah",
        "4. Kiri bawah",
        "",
        "R = reset titik",
        "S = simpan jika sudah 4 titik",
        "Q = keluar"
    ]

    y = 30
    for text in instructions:
        cv2.putText(
            output,
            text,
            (20, y),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            (0, 255, 255),
            2
        )
        y += 28

    return output


def redraw():
    global img_display

    canvas = draw_instruction(img_display)

    # Gambar titik yang sudah diklik
    for i, pt in enumerate(points_display):
        x, y = pt

        cv2.circle(canvas, (x, y), 6, (0, 0, 255), -1)

        cv2.putText(
            canvas,
            str(i + 1),
            (x + 10, y - 10),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.8,
            (0, 0, 255),
            2
        )

    # Gambar garis antar titik
    if len(points_display) >= 2:
        for i in range(len(points_display) - 1):
            cv2.line(
                canvas,
                points_display[i],
                points_display[i + 1],
                (0, 255, 0),
                2
            )

    # Kalau sudah 4 titik, tutup polygon
    if len(points_display) == 4:
        cv2.line(
            canvas,
            points_display[3],
            points_display[0],
            (0, 255, 0),
            2
        )

    cv2.imshow(WINDOW_NAME, canvas)


def mouse_callback(event, x, y, flags, param):
    global points_original, points_display

    if event == cv2.EVENT_LBUTTONDOWN:
        if len(points_display) >= 4:
            print("Sudah 4 titik. Tekan R untuk reset atau S untuk simpan.")
            return

        # Koordinat pada gambar display
        points_display.append((x, y))

        # Konversi koordinat display ke koordinat gambar asli
        original_x = int(x / scale)
        original_y = int(y / scale)

        points_original.append([original_x, original_y])

        print(f"Titik {len(points_original)} diklik:")
        print(f"  display  = ({x}, {y})")
        print(f"  original = ({original_x}, {original_y})")

        redraw()


def save_points():
    if len(points_original) != 4:
        print("ERROR: Titik belum lengkap. Harus 4 titik.")
        return False

    os.makedirs(os.path.dirname(OUTPUT_JSON), exist_ok=True)

    with open(OUTPUT_JSON, "w") as f:
        json.dump(points_original, f, indent=4)

    print("")
    print("Koordinat 4 titik berhasil disimpan:")
    print(OUTPUT_JSON)
    print("")
    print("Urutan titik:")
    print("1. Kiri atas")
    print("2. Kanan atas")
    print("3. Kanan bawah")
    print("4. Kiri bawah")
    print("")
    print(points_original)
    print("")

    return True


def main():
    global img_original, img_display, scale
    global points_original, points_display

    if not os.path.exists(IMAGE_PATH):
        print("ERROR: File gambar tidak ditemukan:")
        print(IMAGE_PATH)
        print("")
        print("Pastikan Tahap 4A sudah dijalankan dan file workspace_undistorted.jpg sudah ada.")
        return

    img_original = cv2.imread(IMAGE_PATH)

    if img_original is None:
        print("ERROR: Gambar gagal dibaca.")
        return

    h, w = img_original.shape[:2]

    scale = DISPLAY_WIDTH / w
    display_height = int(h * scale)

    img_display = cv2.resize(img_original, (DISPLAY_WIDTH, display_height))

    print("=====================================================")
    print("TAHAP 4B - PILIH 4 TITIK AREA KERJA UNDISTORTED")
    print("=====================================================")
    print(f"Input gambar : {IMAGE_PATH}")
    print(f"Resolusi asli: {w} x {h}")
    print(f"Resolusi tampil: {DISPLAY_WIDTH} x {display_height}")
    print("")
    print("Urutan klik:")
    print("1. Kiri atas")
    print("2. Kanan atas")
    print("3. Kanan bawah")
    print("4. Kiri bawah")
    print("")
    print("Keyboard:")
    print("R = reset titik")
    print("S = simpan titik")
    print("Q = keluar")
    print("=====================================================")
    print("")

    cv2.namedWindow(WINDOW_NAME)
    cv2.setMouseCallback(WINDOW_NAME, mouse_callback)

    redraw()

    while True:
        key = cv2.waitKey(1) & 0xFF

        if key == ord("r"):
            points_original = []
            points_display = []
            print("Reset semua titik.")
            redraw()

        elif key == ord("s"):
            if save_points():
                print("Tahap 4B selesai.")
                break

        elif key == ord("q"):
            print("Keluar tanpa menyimpan.")
            break

    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
import cv2
import numpy as np
import json
import os

# =====================================================
# TAHAP 5A - PERSPECTIVE TRANSFORM UNDISTORTED + MARGIN
# =====================================================
# Tujuan:
# Membuat hasil warp area kerja dengan margin tambahan
# agar objek tinggi/miring tidak mudah terpotong.
#
# Input:
#   hasil_tahap4/workspace_undistorted.jpg
#   hasil_tahap4/points_4_corners_undistorted.json
#
# Output:
#   hasil_tahap5_undistorted/area_kerja_warped_undistorted.jpg
#   hasil_tahap5_undistorted/source_with_points.jpg
#   hasil_tahap5_undistorted/before_after_warp.jpg
#   hasil_tahap5_undistorted/warp_info.json
# =====================================================

IMAGE_PATH = "hasil_tahap4/workspace_undistorted.jpg"
POINTS_PATH = "hasil_tahap4/points_4_corners_undistorted.json"
OUTPUT_DIR = "hasil_tahap5_undistorted"

os.makedirs(OUTPUT_DIR, exist_ok=True)

# =====================================================
# UKURAN FISIK AREA KERJA
# =====================================================
WORKSPACE_PANJANG_CM = 19.0
WORKSPACE_LEBAR_CM = 15.0

# Skala utama
PX_PER_CM = 32.0

# Margin tambahan di luar area kerja utama
# 3 cm = 96 px di semua sisi
MARGIN_CM = 3.0

# Ukuran area kerja utama dalam pixel
WORKSPACE_WIDTH_PX = int(WORKSPACE_PANJANG_CM * PX_PER_CM)    # 608 px
WORKSPACE_HEIGHT_PX = int(WORKSPACE_LEBAR_CM * PX_PER_CM)     # 480 px

# Margin dalam pixel
MARGIN_PX = int(MARGIN_CM * PX_PER_CM)                        # 96 px

# Ukuran output final dengan margin
OUTPUT_WIDTH_PX = WORKSPACE_WIDTH_PX + (2 * MARGIN_PX)        # 800 px
OUTPUT_HEIGHT_PX = WORKSPACE_HEIGHT_PX + (2 * MARGIN_PX)      # 672 px

# Posisi area kerja utama di dalam canvas output
WORKSPACE_X0 = MARGIN_PX
WORKSPACE_Y0 = MARGIN_PX
WORKSPACE_X1 = MARGIN_PX + WORKSPACE_WIDTH_PX - 1
WORKSPACE_Y1 = MARGIN_PX + WORKSPACE_HEIGHT_PX - 1


def load_points(json_path):
    if not os.path.exists(json_path):
        print("ERROR: File titik tidak ditemukan:")
        print(json_path)
        return None

    with open(json_path, "r") as f:
        points = json.load(f)

    if len(points) != 4:
        print("ERROR: Jumlah titik harus 4.")
        return None

    return np.array(points, dtype=np.float32)


def draw_points(image, pts):
    output = image.copy()

    labels = ["1", "2", "3", "4"]

    for i, p in enumerate(pts):
        x, y = int(p[0]), int(p[1])

        cv2.circle(output, (x, y), 8, (0, 0, 255), -1)

        cv2.putText(
            output,
            labels[i],
            (x + 10, y - 10),
            cv2.FONT_HERSHEY_SIMPLEX,
            1.0,
            (0, 255, 255),
            2
        )

    for i in range(4):
        p1 = tuple(pts[i].astype(int))
        p2 = tuple(pts[(i + 1) % 4].astype(int))
        cv2.line(output, p1, p2, (0, 255, 0), 2)

    return output


def draw_workspace_reference(warped):
    output = warped.copy()

    # Kotak hijau menunjukkan area kerja asli 19 cm x 15 cm
    cv2.rectangle(
        output,
        (WORKSPACE_X0, WORKSPACE_Y0),
        (WORKSPACE_X1, WORKSPACE_Y1),
        (0, 255, 0),
        2
    )

    cv2.putText(
        output,
        "AREA KERJA 19cm x 15cm",
        (WORKSPACE_X0 + 10, WORKSPACE_Y0 - 15),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.7,
        (0, 255, 0),
        2
    )

    cv2.putText(
        output,
        f"Margin {MARGIN_CM} cm | Scale {PX_PER_CM} px/cm",
        (20, 35),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.7,
        (0, 255, 255),
        2
    )

    return output


def resize_for_preview(image, width):
    h, w = image.shape[:2]
    scale = width / w
    height = int(h * scale)
    return cv2.resize(image, (width, height))


def pad_to_height(img, target_h):
    h, w = img.shape[:2]

    if h >= target_h:
        return img

    pad_bottom = target_h - h

    return cv2.copyMakeBorder(
        img,
        0,
        pad_bottom,
        0,
        0,
        cv2.BORDER_CONSTANT,
        value=(0, 0, 0)
    )


def main():
    print("=====================================================")
    print("TAHAP 5A - PERSPECTIVE TRANSFORM UNDISTORTED + MARGIN")
    print("=====================================================")
    print(f"Input gambar : {IMAGE_PATH}")
    print(f"Input titik  : {POINTS_PATH}")
    print(f"Output folder: {OUTPUT_DIR}")
    print("")
    print("Ukuran fisik area kerja:")
    print(f"Panjang area kerja : {WORKSPACE_PANJANG_CM} cm")
    print(f"Lebar area kerja   : {WORKSPACE_LEBAR_CM} cm")
    print("")
    print("Skala:")
    print(f"PX_PER_CM          : {PX_PER_CM} px/cm")
    print("")
    print("Margin:")
    print(f"MARGIN_CM          : {MARGIN_CM} cm")
    print(f"MARGIN_PX          : {MARGIN_PX} px")
    print("")
    print("Ukuran output:")
    print(f"Workspace utama    : {WORKSPACE_WIDTH_PX} x {WORKSPACE_HEIGHT_PX} px")
    print(f"Output + margin    : {OUTPUT_WIDTH_PX} x {OUTPUT_HEIGHT_PX} px")
    print("")
    print("Koordinat area kerja utama di output:")
    print(f"x0, y0             : {WORKSPACE_X0}, {WORKSPACE_Y0}")
    print(f"x1, y1             : {WORKSPACE_X1}, {WORKSPACE_Y1}")
    print("=====================================================")
    print("")

    if not os.path.exists(IMAGE_PATH):
        print("ERROR: File gambar tidak ditemukan:")
        print(IMAGE_PATH)
        return

    image = cv2.imread(IMAGE_PATH)

    if image is None:
        print("ERROR: Gambar gagal dibaca.")
        return

    pts_src = load_points(POINTS_PATH)

    if pts_src is None:
        return

    # Urutan titik sumber:
    # 1 = kiri atas
    # 2 = kanan atas
    # 3 = kanan bawah
    # 4 = kiri bawah
    #
    # Titik tujuan dibuat masuk ke dalam canvas dengan margin.
    pts_dst = np.array([
        [WORKSPACE_X0, WORKSPACE_Y0],
        [WORKSPACE_X1, WORKSPACE_Y0],
        [WORKSPACE_X1, WORKSPACE_Y1],
        [WORKSPACE_X0, WORKSPACE_Y1]
    ], dtype=np.float32)

    # Matrix perspective transform
    matrix = cv2.getPerspectiveTransform(pts_src, pts_dst)

    # Warp ke canvas lebih besar
    warped = cv2.warpPerspective(
        image,
        matrix,
        (OUTPUT_WIDTH_PX, OUTPUT_HEIGHT_PX),
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=(0, 0, 0)
    )

    warped_with_reference = draw_workspace_reference(warped)
    source_with_points = draw_points(image, pts_src)

    # Preview before-after agar mudah dilihat
    source_preview = resize_for_preview(source_with_points, 500)
    warped_preview = resize_for_preview(warped_with_reference, 500)

    h1, _ = source_preview.shape[:2]
    h2, _ = warped_preview.shape[:2]
    max_h = max(h1, h2)

    source_preview = pad_to_height(source_preview, max_h)
    warped_preview = pad_to_height(warped_preview, max_h)

    cv2.putText(
        source_preview,
        "SOURCE + 4 POINTS",
        (20, 35),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.7,
        (0, 255, 255),
        2
    )

    cv2.putText(
        warped_preview,
        "WARPED + MARGIN",
        (20, 35),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.7,
        (0, 255, 0),
        2
    )

    before_after = np.hstack((source_preview, warped_preview))

    # Path output
    warped_path = os.path.join(OUTPUT_DIR, "area_kerja_warped_undistorted.jpg")
    source_path = os.path.join(OUTPUT_DIR, "source_with_points.jpg")
    preview_path = os.path.join(OUTPUT_DIR, "before_after_warp.jpg")
    info_path = os.path.join(OUTPUT_DIR, "warp_info.json")

    # Simpan file
    cv2.imwrite(warped_path, warped)
    cv2.imwrite(source_path, source_with_points)
    cv2.imwrite(preview_path, before_after)

    info = {
        "input_image": IMAGE_PATH,
        "input_points_json": POINTS_PATH,

        "points_order": {
            "1": "kiri_atas",
            "2": "kanan_atas",
            "3": "kanan_bawah",
            "4": "kiri_bawah"
        },

        "source_points": pts_src.tolist(),
        "destination_points_with_margin": pts_dst.tolist(),

        "workspace_panjang_cm": WORKSPACE_PANJANG_CM,
        "workspace_lebar_cm": WORKSPACE_LEBAR_CM,

        "px_per_cm": PX_PER_CM,
        "px_per_cm_x": PX_PER_CM,
        "px_per_cm_y": PX_PER_CM,

        "margin_cm": MARGIN_CM,
        "margin_px": MARGIN_PX,

        "workspace_width_px": WORKSPACE_WIDTH_PX,
        "workspace_height_px": WORKSPACE_HEIGHT_PX,

        "output_width_px": OUTPUT_WIDTH_PX,
        "output_height_px": OUTPUT_HEIGHT_PX,

        "workspace_x0": WORKSPACE_X0,
        "workspace_y0": WORKSPACE_Y0,
        "workspace_x1": WORKSPACE_X1,
        "workspace_y1": WORKSPACE_Y1,

        "output_warped_image": warped_path,
        "output_source_points_image": source_path,
        "output_preview_image": preview_path
    }

    with open(info_path, "w") as f:
        json.dump(info, f, indent=4)

    print("Output berhasil disimpan:")
    print(f"- {warped_path}")
    print(f"- {source_path}")
    print(f"- {preview_path}")
    print(f"- {info_path}")
    print("")
    print("Tahap 5A revisi margin selesai.")
    print("Langkah berikutnya: jalankan ulang Tahap 6 versi margin.")
    print("")

    cv2.namedWindow("Tahap 5A - Before After Warp Margin", cv2.WINDOW_NORMAL)
    cv2.resizeWindow("Tahap 5A - Before After Warp Margin", 1100, 500)
    cv2.imshow("Tahap 5A - Before After Warp Margin", before_after)

    cv2.namedWindow("Tahap 5A - Warped Margin Result", cv2.WINDOW_NORMAL)
    cv2.resizeWindow("Tahap 5A - Warped Margin Result", 800, 672)
    cv2.imshow("Tahap 5A - Warped Margin Result", warped_with_reference)

    cv2.waitKey(0)
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
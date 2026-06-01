import cv2
import json
import os

# =====================================================
# TAHAP 6 - PIXEL TO CM VERSI MARGIN
# =====================================================
# Tujuan:
# Membuat file skala pixel-to-cm berdasarkan hasil
# Tahap 5A margin.
#
# Input:
#   hasil_tahap5_undistorted/area_kerja_warped_undistorted.jpg
#   hasil_tahap5_undistorted/warp_info.json
#
# Output:
#   hasil_tahap6/pixel_scale.json
#   hasil_tahap6/grid_1cm_reference.jpg
# =====================================================

WARP_IMAGE_PATH = "hasil_tahap5_undistorted/area_kerja_warped_undistorted.jpg"
WARP_INFO_PATH = "hasil_tahap5_undistorted/warp_info.json"

OUTPUT_DIR = "hasil_tahap6"
os.makedirs(OUTPUT_DIR, exist_ok=True)

OUTPUT_SCALE_JSON = os.path.join(OUTPUT_DIR, "pixel_scale.json")
OUTPUT_GRID_IMAGE = os.path.join(OUTPUT_DIR, "grid_1cm_reference.jpg")


def load_json(path):
    if not os.path.exists(path):
        print("ERROR: File tidak ditemukan:")
        print(path)
        return None

    with open(path, "r") as f:
        return json.load(f)


def draw_grid_reference(img, info):
    output = img.copy()

    px_per_cm = float(info["px_per_cm"])

    margin_px = int(info["margin_px"])

    workspace_x0 = int(info["workspace_x0"])
    workspace_y0 = int(info["workspace_y0"])
    workspace_x1 = int(info["workspace_x1"])
    workspace_y1 = int(info["workspace_y1"])

    output_width_px = int(info["output_width_px"])
    output_height_px = int(info["output_height_px"])

    step = int(round(px_per_cm))

    # Grid 1 cm pada seluruh canvas, termasuk margin.
    for x in range(0, output_width_px, step):
        cv2.line(output, (x, 0), (x, output_height_px), (0, 100, 0), 1)

    for y in range(0, output_height_px, step):
        cv2.line(output, (0, y), (output_width_px, y), (0, 100, 0), 1)

    # Garis area kerja utama dibuat lebih tebal.
    cv2.rectangle(
        output,
        (workspace_x0, workspace_y0),
        (workspace_x1, workspace_y1),
        (0, 255, 0),
        2
    )

    # Garis margin luar/canvas.
    cv2.rectangle(
        output,
        (0, 0),
        (output_width_px - 1, output_height_px - 1),
        (255, 255, 0),
        2
    )

    cv2.putText(
        output,
        "Grid 1 cm - Warp + Margin",
        (20, 35),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.8,
        (0, 255, 255),
        2
    )

    cv2.putText(
        output,
        f"Scale: {px_per_cm:.2f} px/cm | Margin: {margin_px}px",
        (20, 70),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.65,
        (0, 255, 255),
        2
    )

    cv2.putText(
        output,
        "Green box = area kerja asli 19cm x 15cm",
        (20, 105),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.6,
        (0, 255, 0),
        2
    )

    return output


def main():
    print("=====================================================")
    print("TAHAP 6 - PIXEL TO CM VERSI MARGIN")
    print("=====================================================")
    print(f"Input gambar   : {WARP_IMAGE_PATH}")
    print(f"Input warp info: {WARP_INFO_PATH}")
    print(f"Output folder  : {OUTPUT_DIR}")
    print("=====================================================")
    print("")

    if not os.path.exists(WARP_IMAGE_PATH):
        print("ERROR: File hasil warp tidak ditemukan.")
        print("Jalankan Tahap 5A revisi margin terlebih dahulu.")
        return

    img = cv2.imread(WARP_IMAGE_PATH)

    if img is None:
        print("ERROR: Gambar warp gagal dibaca.")
        return

    info = load_json(WARP_INFO_PATH)

    if info is None:
        return

    h, w = img.shape[:2]

    output_width_px = int(info["output_width_px"])
    output_height_px = int(info["output_height_px"])

    workspace_panjang_cm = float(info["workspace_panjang_cm"])
    workspace_lebar_cm = float(info["workspace_lebar_cm"])

    workspace_width_px = int(info["workspace_width_px"])
    workspace_height_px = int(info["workspace_height_px"])

    margin_cm = float(info["margin_cm"])
    margin_px = int(info["margin_px"])

    workspace_x0 = int(info["workspace_x0"])
    workspace_y0 = int(info["workspace_y0"])
    workspace_x1 = int(info["workspace_x1"])
    workspace_y1 = int(info["workspace_y1"])

    px_per_cm_x = float(info["px_per_cm_x"])
    px_per_cm_y = float(info["px_per_cm_y"])

    cm_per_px_x = 1.0 / px_per_cm_x
    cm_per_px_y = 1.0 / px_per_cm_y

    print("Data dari gambar warp:")
    print(f"Resolusi gambar terbaca : {w} x {h} px")
    print(f"Resolusi dari warp_info : {output_width_px} x {output_height_px} px")
    print("")

    if w != output_width_px or h != output_height_px:
        print("WARNING: Ukuran gambar tidak sama dengan warp_info.json.")
        print("Periksa ulang Tahap 5A.")
        print("")

    print("Area kerja utama:")
    print(f"Ukuran fisik       : {workspace_panjang_cm} cm x {workspace_lebar_cm} cm")
    print(f"Ukuran pixel       : {workspace_width_px} x {workspace_height_px} px")
    print(f"Koordinat area     : x={workspace_x0}..{workspace_x1}, y={workspace_y0}..{workspace_y1}")
    print("")

    print("Margin:")
    print(f"Margin fisik       : {margin_cm} cm")
    print(f"Margin pixel       : {margin_px} px")
    print("")

    print("========== HASIL SKALA ==========")
    print(f"PX_PER_CM_X        : {px_per_cm_x:.4f} px/cm")
    print(f"PX_PER_CM_Y        : {px_per_cm_y:.4f} px/cm")
    print(f"CM_PER_PX_X        : {cm_per_px_x:.6f} cm/px")
    print(f"CM_PER_PX_Y        : {cm_per_px_y:.6f} cm/px")
    print("=================================")
    print("")

    scale_data = {
        "mode": "warp_with_margin",

        "input_warp_image": WARP_IMAGE_PATH,
        "input_warp_info": WARP_INFO_PATH,

        "workspace_panjang_cm": workspace_panjang_cm,
        "workspace_lebar_cm": workspace_lebar_cm,

        "workspace_width_px": workspace_width_px,
        "workspace_height_px": workspace_height_px,

        "output_width_px": output_width_px,
        "output_height_px": output_height_px,

        "margin_cm": margin_cm,
        "margin_px": margin_px,

        "workspace_x0": workspace_x0,
        "workspace_y0": workspace_y0,
        "workspace_x1": workspace_x1,
        "workspace_y1": workspace_y1,

        "px_per_cm_x": px_per_cm_x,
        "px_per_cm_y": px_per_cm_y,

        "cm_per_px_x": cm_per_px_x,
        "cm_per_px_y": cm_per_px_y
    }

    with open(OUTPUT_SCALE_JSON, "w") as f:
        json.dump(scale_data, f, indent=4)

    grid_img = draw_grid_reference(img, info)
    cv2.imwrite(OUTPUT_GRID_IMAGE, grid_img)

    print("Output berhasil disimpan:")
    print(f"- {OUTPUT_SCALE_JSON}")
    print(f"- {OUTPUT_GRID_IMAGE}")
    print("")
    print("Tahap 6 revisi margin selesai.")
    print("Langkah berikutnya: Tahap 7 harus direvisi agar memakai output 800 x 672 dan koordinat margin.")
    print("")

    cv2.namedWindow("Tahap 6 - Grid 1 cm Margin", cv2.WINDOW_NORMAL)
    cv2.resizeWindow("Tahap 6 - Grid 1 cm Margin", 800, 672)
    cv2.imshow("Tahap 6 - Grid 1 cm Margin", grid_img)

    cv2.waitKey(0)
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
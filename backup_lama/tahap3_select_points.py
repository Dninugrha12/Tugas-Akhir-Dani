import cv2
import json

# Path gambar, ganti sesuai file Anda
IMAGE_PATH = "hasil_tahap2/better_tahap2.jpg"

# List untuk menyimpan koordinat
points = []

def mouse_callback(event, x, y, flags, param):
    global points, scale_x, scale_y
    if event == cv2.EVENT_LBUTTONDOWN:
        # Konversi koordinat klik ke ukuran asli
        orig_x = int(x / scale_x)
        orig_y = int(y / scale_y)
        print(f"Titik diklik: ({orig_x}, {orig_y})")
        points.append([orig_x, orig_y])
        # Gambar lingkaran merah pada tampilan
        cv2.circle(resized_img, (x, y), 5, (0, 0, 255), -1)
        cv2.imshow("Klik 4 Sudut Area Kerja", resized_img)

# Load gambar asli
img = cv2.imread(IMAGE_PATH)
if img is None:
    print("ERROR: Gambar tidak ditemukan di path:", IMAGE_PATH)
    exit()

clone = img.copy()

# Resize agar muat layar
max_width = 1200  # pixel maksimal di layar
max_height = 800
scale_x = min(max_width / img.shape[1], 1.0)
scale_y = min(max_height / img.shape[0], 1.0)
resized_img = cv2.resize(img, (int(img.shape[1]*scale_x), int(img.shape[0]*scale_y)), interpolation=cv2.INTER_AREA)

cv2.namedWindow("Klik 4 Sudut Area Kerja")
cv2.setMouseCallback("Klik 4 Sudut Area Kerja", mouse_callback)

print("Klik 4 sudut area kerja secara berurutan:")
print("1 = kiri atas, 2 = kanan atas, 3 = kanan bawah, 4 = kiri bawah")

while True:
    cv2.imshow("Klik 4 Sudut Area Kerja", resized_img)
    key = cv2.waitKey(1) & 0xFF

    # Reset titik
    if key == ord("r"):
        points = []
        resized_img = cv2.resize(clone, (int(clone.shape[1]*scale_x), int(clone.shape[0]*scale_y)), interpolation=cv2.INTER_AREA)
        print("Reset titik klik")

    # Quit
    elif key == ord("q"):
        break

cv2.destroyAllWindows()

# Simpan koordinat ke file JSON
if len(points) == 4:
    with open("hasil_tahap2/points_4_corners.json", "w") as f:
        json.dump(points, f)
    print("Koordinat 4 sudut tersimpan di 'points_4_corners.json':")
    print(points)
else:
    print("Tidak cukup 4 titik. Titik yang diklik:", points)
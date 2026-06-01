import cv2
import numpy as np

# =====================================
# PIXEL PER CM
# =====================================

PIXEL_PER_CM_X = 32.8
PIXEL_PER_CM_Y = 29.5

# =====================================
# BUKA WEBCAM
# =====================================

kamera = cv2.VideoCapture(0)

if not kamera.isOpened():
    print("Webcam tidak terdeteksi")
    exit()

# =====================================
# AREA KERJA
# =====================================

pts1 = np.float32([
    [175,142],
    [463,143],
    [168,474],
    [466,475]
])

# =====================================
# TOP DOWN SIZE
# =====================================

width = 300
height = 400

pts2 = np.float32([
    [0,0],
    [width,0],
    [0,height],
    [width,height]
])

# =====================================
# PERSPEKTIF
# =====================================

matrix = cv2.getPerspectiveTransform(
    pts1,
    pts2
)

inverse_matrix = cv2.getPerspectiveTransform(
    pts2,
    pts1
)

print("Tekan tombol Q untuk keluar")

# =====================================
# LOOP
# =====================================

while True:

    berhasil, frame = kamera.read()

    if not berhasil:
        break

    frame = cv2.resize(
        frame,
        (640,480)
    )

    # =====================================
    # TOP DOWN VIEW
    # =====================================

    topdown = cv2.warpPerspective(
        frame,
        matrix,
        (width,height)
    )

    # =====================================
    # PREPROCESSING
    # =====================================

    gray = cv2.cvtColor(
        topdown,
        cv2.COLOR_BGR2GRAY
    )

    blur = cv2.GaussianBlur(
        gray,
        (5,5),
        0
    )

    edges = cv2.Canny(
        blur,
        50,
        150
    )

    kernel = np.ones(
        (5,5),
        np.uint8
    )

    edges = cv2.dilate(
        edges,
        kernel,
        iterations=1
    )

    edges = cv2.erode(
        edges,
        kernel,
        iterations=1
    )

    # =====================================
    # CONTOUR
    # =====================================

    contours, _ = cv2.findContours(
        edges,
        cv2.RETR_EXTERNAL,
        cv2.CHAIN_APPROX_SIMPLE
    )

    detected = False

    if contours:

        terbesar = max(
            contours,
            key=cv2.contourArea
        )

        area = cv2.contourArea(
            terbesar
        )

        if area > 2000:

            rect = cv2.minAreaRect(
                terbesar
            )

            (center_x, center_y), (w, h), angle = rect

            # =====================================
            # UKURAN CM
            # =====================================

            panjang_cm = (
                max(w,h) /
                PIXEL_PER_CM_X
            )

            lebar_cm = (
                min(w,h) /
                PIXEL_PER_CM_Y
            )

            # =====================================
            # PRINT TERMINAL
            # =====================================

            print(
                "Panjang =",
                round(panjang_cm,1),
                "cm"
            )

            print(
                "Lebar =",
                round(lebar_cm,1),
                "cm"
            )

            print("===================")

            detected = True

            # =====================================
            # BOX
            # =====================================

            box = cv2.boxPoints(rect)

            box = np.int32(box)

            # =====================================
            # KEMBALIKAN KE FRAME ASLI
            # =====================================

            points = np.float32(box)

            points = np.array(
                [points],
                dtype=np.float32
            )

            original_points = cv2.perspectiveTransform(
                points,
                inverse_matrix
            )

            original_points = np.int32(
                original_points
            )

            # =====================================
            # RECTANGLE HIJAU
            # =====================================

            cv2.drawContours(
                frame,
                [original_points],
                -1,
                (0,255,0),
                4
            )

            # =====================================
            # TITIK MERAH
            # =====================================

            for point in original_points[0]:

                x, y = point

                cv2.circle(
                    frame,
                    (x,y),
                    7,
                    (0,0,255),
                    -1
                )

            # =====================================
            # POSISI TEXT
            # =====================================

            pts = original_points[0]

            x1, y1 = pts[0]
            x3, y3 = pts[3]

            # =====================================
            # TEXT PANJANG
            # =====================================

            cv2.putText(
                frame,
                f"Panjang: {panjang_cm:.1f} cm",
                (x1, y1 - 15),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                (0,0,255),
                2
            )

            # =====================================
            # TEXT LEBAR
            # =====================================

            cv2.putText(
                frame,
                f"Lebar: {lebar_cm:.1f} cm",
                (x3 - 120, y3),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                (255,0,0),
                2
            )

    # =====================================
    # STATUS
    # =====================================

    if not detected:

        cv2.putText(
            frame,
            "Rectangle tidak terdeteksi",
            (10,40),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.8,
            (0,0,255),
            2
        )

    # =====================================
    # TAMPILKAN
    # =====================================

    cv2.imshow(
        "FINAL DIMENSION SYSTEM",
        frame
    )

    # =====================================
    # KELUAR
    # =====================================

    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

# =====================================
# TUTUP
# =====================================

kamera.release()
cv2.destroyAllWindows()
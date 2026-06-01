import cv2
import numpy as np
import time

from gpiozero import DistanceSensor

# ambil function dari loadcell.py
from loadcell import get_weight

# =====================================
# ULTRASONIC
# =====================================

sensor = DistanceSensor(
    echo=24,
    trigger=23
)

TINGGI_KAMERA = 32.0

# =====================================
# PIXEL CALIBRATION
# =====================================

PIXEL_PER_CM_X = 22.5
PIXEL_PER_CM_Y = 22.5

# =====================================
# BUKA WEBCAM
# =====================================

kamera = cv2.VideoCapture(0)

if not kamera.isOpened():

    print("Webcam tidak terdeteksi")
    exit()

# =====================================
# ROI AREA KERJA
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
# PERSPECTIVE
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
# VARIABLE
# =====================================

fixed_weight = 0

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
    # ULTRASONIC AVERAGING
    # =====================================

    jarak_list = []

    for i in range(5):

        jarak = sensor.distance * 100

        jarak_list.append(jarak)

        time.sleep(0.01)

    jarak_sensor = (
        sum(jarak_list) /
        len(jarak_list)
    )

    tinggi_benda = (
        TINGGI_KAMERA - jarak_sensor
    )

    if tinggi_benda < 0:
        tinggi_benda = 0

    # =====================================
    # LOADCELL
    # =====================================

    try:

        fixed_weight = get_weight()

        if fixed_weight < 0:
            fixed_weight = 0

    except Exception as e:

        print("Loadcell Error:", e)

        fixed_weight = 0

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
            # HEIGHT CORRECTION
            # =====================================

            faktor = 1.0 + (
                tinggi_benda * 0.015
            )

            # =====================================
            # HITUNG UKURAN
            # =====================================

            panjang_cm = round(
                (
                    (max(w,h) / PIXEL_PER_CM_X)
                    * faktor
                ),
                1
            )

            lebar_cm = round(
                (
                    (min(w,h) / PIXEL_PER_CM_Y)
                    * faktor
                ),
                1
            )

            # =====================================
            # VOLUMETRIC
            # =====================================

            berat_volumetrik_kg = (
                panjang_cm *
                lebar_cm *
                tinggi_benda
            ) / 6000

            berat_volumetrik_gram = (
                berat_volumetrik_kg * 1000
            )

            # =====================================
            # CHARGEABLE WEIGHT
            # =====================================

            chargeable_weight = max(
                fixed_weight,
                berat_volumetrik_gram
            )

            detected = True

            # =====================================
            # BOX
            # =====================================

            box = cv2.boxPoints(rect)

            box = np.int32(box)

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
            # TEXT
            # =====================================

            cv2.putText(
                frame,
                f"Panjang : {panjang_cm:.1f} cm",
                (10,30),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                (0,0,255),
                2
            )

            cv2.putText(
                frame,
                f"Lebar : {lebar_cm:.1f} cm",
                (10,55),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                (255,0,0),
                2
            )

            cv2.putText(
                frame,
                f"Tinggi : {tinggi_benda:.1f} cm",
                (10,80),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                (0,255,255),
                2
            )

            cv2.putText(
                frame,
                f"Volumetrik : {berat_volumetrik_gram:.1f} gram",
                (10,105),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                (0,255,0),
                2
            )

            cv2.putText(
                frame,
                f"Berat Asli : {fixed_weight:.1f} gram",
                (10,130),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                (255,255,255),
                2
            )

            cv2.putText(
                frame,
                f"Chargeable : {chargeable_weight:.1f} gram",
                (10,155),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                (0,165,255),
                2
            )

            # =====================================
            # TERMINAL
            # =====================================

            print("====================")

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

            print(
                "Tinggi =",
                round(tinggi_benda,1),
                "cm"
            )

            print(
                "Volumetrik =",
                round(berat_volumetrik_gram,1),
                "gram"
            )

            print(
                "Berat Asli =",
                round(fixed_weight,1),
                "gram"
            )

            print(
                "Chargeable =",
                round(chargeable_weight,1),
                "gram"
            )

    # =====================================
    # STATUS
    # =====================================

    if not detected:

        cv2.putText(
            frame,
            "Rectangle tidak terdeteksi",
            (10,190),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
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
    # EXIT
    # =====================================

    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

    time.sleep(0.05)

# =====================================
# CLOSE
# =====================================

kamera.release()

cv2.destroyAllWindows()
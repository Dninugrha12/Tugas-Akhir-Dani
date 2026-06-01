import time
import statistics
from hx711 import HX711

# =====================================
# HX711 CONFIG
# =====================================

DT_PIN = 5
SCK_PIN = 6

CALIBRATION_FACTOR = 373

# =====================================
# HX711 INIT
# =====================================

hx = HX711(
    DT_PIN,
    SCK_PIN
)

hx.setReadingFormat(
    "MSB",
    "MSB"
)

hx.setReferenceUnit(
    CALIBRATION_FACTOR
)

hx.reset()

print("Kalibrasi loadcell...")

# =====================================
# OFFSET
# =====================================

offset_data = []

for _ in range(15):

    value = hx.getWeight()

    offset_data.append(value)

    time.sleep(0.1)

OFFSET = sum(offset_data) / len(offset_data)

print("Loadcell siap")

# =====================================
# PARAMETER
# =====================================

SAMPLES = 5

ZERO_THRESHOLD = 50

# =====================================
# GET WEIGHT FUNCTION
# =====================================

def get_weight():

    readings = []

    for _ in range(SAMPLES):

        try:

            value = hx.getWeight()

            value = value - OFFSET

            readings.append(value)

        except:

            pass

    if len(readings) == 0:

        return 0

    # =================================
    # MEDIAN FILTER
    # =================================

    median = statistics.median(
        readings
    )

    filtered = []

    for r in readings:

        if abs(r - median) < 100:

            filtered.append(r)

    if len(filtered) == 0:

        filtered = readings

    weight = (
        sum(filtered)
        / len(filtered)
    )

    # =================================
    # AUTO ZERO
    # =================================

    if abs(weight) < ZERO_THRESHOLD:

        weight = 0

    return round(weight, 1)

    # =====================================
# TEST SENSOR
# =====================================

# =====================================
# TEST SENSOR
# =====================================

if __name__ == "__main__":

    while True:

        try:

            value = get_weight()

            print(
                f"Berat : {value:.1f} gram"
            )

            time.sleep(0.2)

        except KeyboardInterrupt:

            print("\nProgram dihentikan")

            break
from gpiozero import AngularServo
from time import sleep

servo = AngularServo(
    18,
    min_angle=-180,
    max_angle=180,
    min_pulse_width=0.0005,
    max_pulse_width=0.0025
)

print("Sistem rack pendorong siap")

try:

    while True:

        # ==================================
        # RACK MAJU
        # ==================================

        sudut_maju = 180

        print(f"Rack maju | Sudut servo: {sudut_maju}°")

        servo.angle = sudut_maju

        sleep(2)

        # ==================================
        # RACK MUNDUR
        # ==================================

        sudut_mundur = -180

        print(f"Rack mundur | Sudut servo: {sudut_mundur}°")

        servo.angle = sudut_mundur

        sleep(2)

except KeyboardInterrupt:

    servo.angle = 0

    print("Program dihentikan")
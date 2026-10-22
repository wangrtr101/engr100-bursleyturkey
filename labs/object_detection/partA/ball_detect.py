import cv2
import numpy as np
import pickle
import time

# This step hooks into the ESP32's HTTP server."
cap = cv2.VideoCapture("http://192.168.50.<TODO>/stream")

# Constants (Adjust based on your setup)
KNOWN_DISTANCE = 50.0  # cm (Reference distance of the ball)
KNOWN_DIAMETER = 4.0   # cm (Actual diameter of the orange ball)
CAMERA_FOV_X = 60  # Horizontal Field of View in degrees
CAMERA_FOV_Y = 40  # Vertical Field of View in degrees
FRAME_WIDTH = 640   # Camera frame width in pixels
FRAME_HEIGHT = 480  # Camera frame height in pixels
ALPHA = 0.5  # Exponential moving average smoothing factor, IIR

# Initialize smoothed values
x_smoothed, y_smoothed, z_smoothed = 0, 0, 0

# Initialize Kalman Filter
kalman = cv2.KalmanFilter(6, 3)  # 6 states (x, y, z, dx, dy, dz), 3 measurements (x, y, z)
kalman.measurementMatrix = np.eye(3, 6, dtype=np.float32)
kalman.processNoiseCov = np.eye(6, dtype=np.float32) * 0.03
kalman.measurementNoiseCov = np.eye(3, dtype=np.float32) * 0.1
kalman.errorCovPost = np.eye(6, dtype=np.float32) * 0.1
kalman.transitionMatrix = np.array([[1, 0, 0, 1, 0, 0],
                                    [0, 1, 0, 0, 1, 0],
                                    [0, 0, 1, 0, 0, 1],
                                    [0, 0, 0, 1, 0, 0],
                                    [0, 0, 0, 0, 1, 0],
                                    [0, 0, 0, 0, 0, 1]], dtype=np.float32)


# Function to calculate focal length
def calculate_focal_length(known_distance, known_diameter, pixel_diameter):
    return (pixel_diameter * known_distance) / known_diameter

# Function to calculate distance (Z-coordinate)
def calculate_distance(focal_length, known_diameter, pixel_diameter):
    return (known_diameter * focal_length) / pixel_diameter

# Function to calculate real-world X and Y coordinates
def calculate_xy(pixel_x, pixel_y, z_distance):
    norm_x = (pixel_x - FRAME_WIDTH / 2) / (FRAME_WIDTH / 2)
    norm_y = (FRAME_HEIGHT / 2 - pixel_y) / (FRAME_HEIGHT / 2)

    x_angle = norm_x * (CAMERA_FOV_X / 2) * (np.pi / 180)
    y_angle = norm_y * (CAMERA_FOV_Y / 2) * (np.pi / 180)

    x_real = np.tan(x_angle) * z_distance
    y_real = np.tan(y_angle) * z_distance

    return x_real, y_real

# HSV range for detecting an orange ball
while True:
    choice = input("Select threshold: [n]arrow, [m]edium, [w]ide: ").strip().lower()
    if choice == "n":
        mode = "narrow"
        lower_orange = np.array([5, 35, 100], dtype=np.uint8)
        upper_orange = np.array([25, 255, 255], dtype=np.uint8)
        break
    elif choice == "m":
        mode = "medium"
        lower_orange = np.array([0, 15, 80], dtype=np.uint8)
        upper_orange = np.array([35, 255, 255], dtype=np.uint8)
        break
    elif choice == "w":
        mode = "wide"
        lower_orange = np.array([0, 5, 50], dtype=np.uint8)
        upper_orange = np.array([45, 255, 255], dtype=np.uint8)
        break
    else:
        print(f"Invalid choice {choice!r}; expected 'n', 'm', or 'w'.")

print(f"Using {mode} threshold")

# Kernel for morphological operations
kernel = np.ones((5, 5), np.uint8)

# Calibration step: Capture a reference image with a known distance
time.sleep(2)
ret, frame = cap.read()
# frame = calibrate(frame)
h, w = frame.shape[:2]
print(f"h: {h}")
print(f"w: {w}")

if ret:
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    blurred = cv2.GaussianBlur(hsv, (5, 5), 0)
    mask = cv2.inRange(blurred, lower_orange, upper_orange)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)

    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    if contours:
        c = max(contours, key=cv2.contourArea)
        ((x, y), radius) = cv2.minEnclosingCircle(c)
        if radius > 1:
            focal_length = calculate_focal_length(KNOWN_DISTANCE, KNOWN_DIAMETER, radius * 2)
            print(f"Focal Length: {focal_length:.2f}")
            # Update CAMERA_FOV_X and CAMERA_FOV_Y
            CAMERA_FOV_X = 2.0 * np.degrees(np.arctan((2.0*radius/h)*KNOWN_DISTANCE/(2.0*KNOWN_DIAMETER)))
            CAMERA_FOV_Y = 2.0 * np.degrees(np.arctan((2.0*radius/w)*KNOWN_DISTANCE/(2.0*KNOWN_DIAMETER)))
            print(f"CAMERA_FOV_X: {CAMERA_FOV_X:.2f}")
            print(f"CAMERA_FOV_Y: {CAMERA_FOV_Y:.2f}")

        else:
            print("Ball too small for calibration.")
    else:
        print("Ball not detected for calibration.")

# Continuous position estimation loop
while True:
    ret, frame = cap.read()
    if not ret:
        break

    # frame = calibrate(frame)

    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    blurred = cv2.GaussianBlur(hsv, (3, 3), 0)
    mask = cv2.inRange(blurred, lower_orange, upper_orange)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)

    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    if contours:
        c = max(contours, key=cv2.contourArea)  # Track the largest contour
        ((x, y), radius) = cv2.minEnclosingCircle(c)

        if radius > 1:  # Ensure detection validity
            z_distance = calculate_distance(focal_length, KNOWN_DIAMETER, radius * 2)
            x_real, y_real = calculate_xy(x, y, z_distance)

            # Apply Exponential Moving Average smoothing
            x_smoothed = ALPHA * x_real + (1 - ALPHA) * x_smoothed
            y_smoothed = ALPHA * y_real + (1 - ALPHA) * y_smoothed
            z_smoothed = ALPHA * z_distance + (1 - ALPHA) * z_smoothed

            # Prepare measurement for Kalman Filter
            measurement = np.array([[x_smoothed], [y_smoothed], [z_smoothed]], dtype=np.float32)
            estimated_state = kalman.correct(measurement)
            predicted = kalman.predict()

            # Extract smoothed values
            x_kalman, y_kalman, z_kalman = predicted[:3].flatten()
            vx_kalman, vy_kalman, vz_kalman = estimated_state[3, 0], estimated_state[4, 0], estimated_state[5, 0]

            # Display results
            cv2.circle(frame, (int(x), int(y)), int(radius), (0, 255, 0), 2)
            cv2.putText(frame, f"X: {x_kalman:.2f} cm", (int(x - radius), int(y - radius - 30)), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 0, 0), 2)
            cv2.putText(frame, f"Y: {y_kalman:.2f} cm", (int(x - radius), int(y - radius - 15)), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 0, 0), 2)
            cv2.putText(frame, f"Z: {z_kalman:.2f} cm", (int(x - radius), int(y - radius)), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 0, 0), 2)
            cv2.putText(frame, f"VX: {vx_kalman:.2f} cm", (int(x - radius), int(y - radius + 15)), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 0, 0), 2)
            cv2.putText(frame, f"VY: {vy_kalman:.2f} cm", (int(x - radius), int(y - radius + 30)), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 0, 0), 2)
            cv2.putText(frame, f"VZ: {vz_kalman:.2f} cm", (int(x - radius), int(y - radius + 45)), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 0, 0), 2)

    cv2.imshow("3D Position Estimation with Smoothing", frame)

    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()

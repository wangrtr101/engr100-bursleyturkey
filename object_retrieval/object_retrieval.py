import sys
import cv2
import socket
import numpy as np
import time
from ultralytics import YOLO
import imutils
import threading
import queue

LINE_FOLLOW_IP = '192.168.50.225'
OBJECT_DETECTION_IP = '192.168.50.226'
TCP_PORT = 5005

MODEL_NAME = "yolo11n.pt"
CONFIDENCE_THRESHOLD = 0.25
DEVICE = "cpu"

OBJECT_FRAMES_TO_CONFIRM = 5   # object must show up this many frames in a row before leaving the line
STOP_AREA = 18000              # px^2 bounding box area to stop in front of the object
LOST_FRAMES_TO_STOP = 5        # stop the motors if the object disappears for this many frames during approach

# Terminal line clear codes to make telemetry look a little nicer
LINE_UP = '\033[1A'
LINE_CLEAR = '\x1b[2K'

# Turning around and getting back to the line
SPIN_SPEED = 150               # 0-255, both wheels, turning in opposite directions
SPIN_TIME_180 = 1.2            # seconds of spinning for a 180 degree turn (tune on floor)
SPIN_DIRECTION = 'e'           # 'e' = spin right (clockwise), 'q' = spin left
DRIVE_SPEED = 80               # 0-255, driving straight back toward the line
DRIVE_TIMEOUT = 5.0            # seconds; stop if no line shows up within this time
LINE_MIN_AREA = 2000           # px^2 of tape in the line camera's frame to count as "line found"
LINE_FRAMES_TO_CONFIRM = 3     # tape must show up this many frames in a row

line_follow_url = f'http://{LINE_FOLLOW_IP}/stream'
object_detection_url = f'http://{OBJECT_DETECTION_IP}/stream'

# Orange line-following tape HSV thresholds
low_orange = np.array([0, 0, 20], dtype=np.uint8)
high_orange = np.array([70, 255, 255], dtype=np.uint8)
angle_weight = 0

#setup camera sockets
def socket_setup(ip, port):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    print(f"Connecting to ESP32 at {ip}:{port}...")
    sock.connect((ip, port))
    print(f"Successfully connected to ESP32 at {ip}:{port}.")
    sock.setblocking(False)
    return sock

#get info from the esp32 (usually voice recognition ID)
def recv_line(sock):
    data = b""
    while True:
        try:
            chunk = sock.recv(1)
            if not chunk or chunk == b"\n":
                break
            data += chunk
        except BlockingIOError:
            if not data:
                return None
            time.sleep(0.001)
            continue
    return data.decode("utf-8", errors="ignore").strip()

# get target from esp32
def receive_command(sock):
    objects = {"banana", "teddy bear", "cup"}
    print("Waiting for voice command (banana, teddy bear, cup)...")
    while True:
        cmd = recv_line(sock)
        if cmd is None:
            time.sleep(0.01)
            continue
        if not cmd:
            print("Command reading error")
            return "error"

        normalized = cmd.lower().strip()
        if normalized in objects:
            print(f"Valid command received: {normalized}")
            return normalized
        else:
            print(f"Ignoring unrecognized message: {cmd}")


# Fetch the target id
# defaults to cup if invalid target is given
def pick_model(object_name):
    if object_name == "banana":
        target_class_id = 46
    elif object_name == "teddy bear" or object_name == "teddybear":
        target_class_id = 77
    elif object_name == "cup":
        target_class_id = 41
    else:
        print(f"Unknown object '{object_name}', defaulting to cup (ID 41)")
        target_class_id = 46

    print(f"Loading YOLO model [{MODEL_NAME}] for '{object_name}' (Class ID: {target_class_id})")
    model = YOLO(MODEL_NAME)
    print("YOLO will run on", DEVICE)
    return model, target_class_id

# get frames for object detection stream
def stream_reader(frame_queue, url):
    print("Starting stream_reader thread...")
    vid = cv2.VideoCapture(url)
    time.sleep(2)
    while True:
        ret, frame = vid.read()
        if not ret:
            print("Couldn't read frame. Killing thread.")
            break

        if frame_queue.full():
            try:
                frame_queue.get_nowait()
            except queue.Empty:
                pass

        frame_queue.put(frame)

# line following, from lab
def follow_line(vid, sock):
    ret, frame = vid.read()
    if not ret:
        print("No line read")
        sock.sendall(b"STOP\n")
        return False

    frame = cv2.GaussianBlur(frame, (5, 5), 0)
    hsv_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    gray_threshold = cv2.inRange(hsv_frame, low_orange, high_orange)

    hole_kernel = np.ones((5, 5), np.uint8)
    gray_threshold = cv2.morphologyEx(gray_threshold, cv2.MORPH_CLOSE, hole_kernel)

    gray_threshold_contours, _ = cv2.findContours(
        gray_threshold, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE
    )

    if gray_threshold_contours:
        bestContour = max(gray_threshold_contours, key=cv2.contourArea)
        if cv2.contourArea(bestContour) == 0:
            bestContour = None
    else:
        bestContour = None

    center_of_frame = np.array([frame.shape[1] / 2, frame.shape[0] / 2], int)

    try:
        if bestContour is not None:
            mask = np.zeros_like(gray_threshold)
            cv2.drawContours(mask, [bestContour], -1, 255, -1)
            points = []
            for y in range(frame.shape[0]):
                xs = np.where(mask[y] > 0)[0]
                if len(xs) > 0:
                    x = (xs[0] + xs[-1]) / 2
                    points.append((x, y))

            points = np.array(points)
            slope, intercept = np.polyfit(points[:, 1], points[:, 0], 1)

            y_ref = frame.shape[0] / 2
            x_ref = y_ref * slope + intercept
            offset_error = center_of_frame[0] - x_ref
            angle_error = slope
            error = offset_error + angle_weight * angle_error

            cv2.putText(frame, "Line: FOUND", (0, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)
            cv2.drawContours(frame, [bestContour], -1, (0, 255, 0), 2)

            y1 = 0
            x1 = int(y1 * slope + intercept)
            y2 = frame.shape[0] - 1
            x2 = int(y2 * slope + intercept)
            cv2.line(frame, (x1, y1), (x2, y2), (255, 0, 255), 2)

            cv2.putText(frame, f"Offset error: {offset_error:.1f}  Angle error: {angle_error:.2f}", (0, 45), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255))
            cv2.putText(frame, f"Combined error: {error:.1f}", (0, 65), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255))
            print(LINE_UP, end=LINE_CLEAR)
            print(f"Offset error: {offset_error:.1f}, Angle error: {angle_error:.3f}, Combined error: {error:.1f}")

            sock.sendall((str(error) + "\n").encode("utf-8"))
        else:
            cv2.putText(frame, "Line: NOT FOUND", (0, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 2)
            sock.sendall(b"STOP\n")
    except Exception as e:
        print(f"Exception incurred: {e}")
        sock.sendall(b"STOP\n")

    cv2.circle(frame, (center_of_frame[0], center_of_frame[1]), 7, (255, 255, 255), -1)
    cv2.line(frame, (center_of_frame[0], 0), (center_of_frame[0], frame.shape[0]), (0, 255, 255), 2)

    cv2.imshow("Current Line-Following Output", frame)
    cv2.imshow("Tape Mask", gray_threshold)
    cv2.waitKey(1)
    return True

# send manual motor inputs rather than PID, mostly for turning around
def send_motor(sock, left, right, direction):
    sock.sendall(f"{left},{right},{direction}\n".encode("utf-8"))

# get the area of the "tape" (hopefully its the tape)
# once enough of tape is recognized the robot is back to the line
def tape_area(frame):
    blurred = cv2.GaussianBlur(frame, (5, 5), 0)
    hsv = cv2.cvtColor(blurred, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, low_orange, high_orange)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    area = max((cv2.contourArea(c) for c in contours), default=0.0)
    return area, mask


def show_line_cam(frame, text, mask=None):
    cv2.putText(frame, text, (0, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 2)
    cv2.imshow("Current Line-Following Output", frame)
    if mask is not None:
        cv2.imshow("Tape Mask", mask)
    return cv2.waitKey(1) & 0xFF


def check_quit(key, sock):
    if key == ord('q') or key == 27:
        sock.sendall(b"STOP\n")
        sys.exit(67)

# get objects from pipeline
# returns if found, x offset, and contour area
def find_object(frame_queue, model, target_class_id):
    if frame_queue.empty():
        return None

    found = False
    x_offset = 0.0
    contour_area = 0.0

    curr_frame = frame_queue.get()
    center_of_frame = curr_frame.shape[1] / 2.0

    results = model(
        curr_frame,
        classes=[target_class_id],
        conf=CONFIDENCE_THRESHOLD,
        stream=True,
        device=DEVICE,
        verbose=False
    )

    for result in results:
        annotated_frame = result.plot()
        annotated_frame = imutils.resize(annotated_frame, width=600)

        # Standard Bounding Boxes (result.boxes)
        if result.boxes is not None and len(result.boxes) > 0:
            best_contour = result.boxes[0]
            best_conf = float(best_contour.conf[0])
            if best_conf >= CONFIDENCE_THRESHOLD:
                x_center, y_center, width, height = best_contour.xywh[0].tolist()
                x_offset = center_of_frame - x_center
                contour_area = width * height
                found = True

        # Oriented Bounding Boxes (result.obb)
        elif result.obb is not None and len(result.obb) > 0:
            best_obb = result.obb[0]
            best_conf = float(best_obb.conf[0])
            if best_conf >= CONFIDENCE_THRESHOLD:
                x_center, y_center, width, height, _ = best_obb.xywhr[0].tolist()
                x_offset = center_of_frame - x_center
                contour_area = width * height
                found = True

        if found:
            cv2.putText(
                annotated_frame,
                f"offset: {x_offset:+.1f}  area: {contour_area:.0f}/{STOP_AREA}",
                (10, 25),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                (0, 255, 0),
                2
            )

        cv2.imshow("YOLO Output", annotated_frame)

    return found, x_offset, contour_area

# main state machine
def retrieve_object(line_follow_sock, object_detection_sock, model, frame_queue, target_class_id):
    line_follow_vid = cv2.VideoCapture(line_follow_url)
    time.sleep(2)

    seen_frames = 0
    print("Following line and scanning for object...")
    while True:
        detection = find_object(frame_queue, model, target_class_id)
        if detection is not None:
            found, x_offset, contour_area = detection
            seen_frames = seen_frames + 1 if found else 0

        if seen_frames >= OBJECT_FRAMES_TO_CONFIRM:
            line_follow_sock.sendall(b"STOP\n")
            break

        following = follow_line(line_follow_vid, line_follow_sock)
        key = cv2.waitKey(1) & 0xFF
        if not following or key == ord('q') or key == 27:
            line_follow_sock.sendall(b"STOP\n")
            sys.exit(67)

    print("Object Found! Seeking object...")
    lost_frames = 0
    while True:
        detection = find_object(frame_queue, model, target_class_id)

        if detection is not None:
            found, x_offset, contour_area = detection

            if found:
                lost_frames = 0
                if contour_area >= STOP_AREA:
                    line_follow_sock.sendall(b"STOP\n")
                    print(f"Reached object (area {contour_area:.0f} >= {STOP_AREA}). Stopped.")
                    break
                line_follow_sock.sendall((str(x_offset) + "\n").encode("utf-8"))
            else:
                lost_frames += 1
                if lost_frames == LOST_FRAMES_TO_STOP:
                    print("Lost object :( Stopping until it's seen again")
                    line_follow_sock.sendall(b"STOP\n")

        key = cv2.waitKey(1) & 0xFF
        if key == ord('q') or key == 27:
            line_follow_sock.sendall(b"STOP\n")
            sys.exit(67)

    print("Stopped in front of the object. Press any key in a video window to turn around (q to quit).")
    check_quit(cv2.waitKey(0) & 0xFF, line_follow_sock)

    line_follow_vid.release()
    line_follow_vid = cv2.VideoCapture(line_follow_url)

    print(f"Turning around ({SPIN_TIME_180:.2f} s at speed {SPIN_SPEED})...")
    send_motor(line_follow_sock, SPIN_SPEED, SPIN_SPEED, SPIN_DIRECTION)
    spin_end = time.monotonic() + SPIN_TIME_180
    while time.monotonic() < spin_end:
        ret, frame = line_follow_vid.read()
        key = show_line_cam(frame, "Turning around") if ret else cv2.waitKey(1) & 0xFF
        check_quit(key, line_follow_sock)
    line_follow_sock.sendall(b"STOP\n")
    time.sleep(0.3)

    print("Driving forward to find the line...")
    send_motor(line_follow_sock, DRIVE_SPEED, DRIVE_SPEED, 'w')
    drive_end = time.monotonic() + DRIVE_TIMEOUT
    line_frames = 0
    while line_frames < LINE_FRAMES_TO_CONFIRM:
        if time.monotonic() > drive_end:
            line_follow_sock.sendall(b"STOP\n")
            print(f"No line found within {DRIVE_TIMEOUT} s. Stopped.")
            sys.exit(68)
        ret, frame = line_follow_vid.read()
        if not ret:
            continue
        area, mask = tape_area(frame)
        line_frames = line_frames + 1 if area >= LINE_MIN_AREA else 0
        key = show_line_cam(frame, f"Looking for line: tape area {area:.0f} / {LINE_MIN_AREA}", mask)
        check_quit(key, line_follow_sock)

    print("Line found! Following the line back. Press q to stop.")
    while True:
        following = follow_line(line_follow_vid, line_follow_sock)
        key = cv2.waitKey(1) & 0xFF
        if not following:
            line_follow_sock.sendall(b"STOP\n")
            sys.exit(67)
        check_quit(key, line_follow_sock)


def main():
    time.sleep(2)

    line_following_sock = socket_setup(LINE_FOLLOW_IP, TCP_PORT)
    object_detection_sock = socket_setup(OBJECT_DETECTION_IP, TCP_PORT)

    # use CLI for debugging
    if len(sys.argv) > 1:
        objectName = " ".join(sys.argv[1:]).strip().lower()
        print(f"Using CLI target object: '{objectName}'")
    else:
        # run voice recog
        objectName = receive_command(line_following_sock)
        if not objectName or objectName == "error":
            print("Error retrieving object input")
            line_following_sock.close()
            object_detection_sock.close()
            sys.exit(1)

    model, target_class_id = pick_model(objectName)

    frame_queue = queue.Queue(maxsize=2)
    threading.Thread(
        target=stream_reader,
        args=(frame_queue, object_detection_url),
        daemon=True
    ).start()

    try:
        retrieve_object(line_following_sock, object_detection_sock, model, frame_queue, target_class_id)
    finally:
        line_following_sock.close()
        object_detection_sock.close()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
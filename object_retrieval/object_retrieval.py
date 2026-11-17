import sys
import math
import cv2
import socket
import numpy as np
import time
import select
import torch
from ultralytics import YOLO
import imutils
import threading
import queue

LINE_FOLLOW_IP = '192.168.50.225'
OBJECT_DETECTION_IP = '192.168.50.226'
TCP_PORT = 5005

CONFIDENCE_THRESHOLD = 0.5
X_THRESHOLD = 10
AREA_THRESHOLD = 10000

# to clear line
LINE_UP = '\033[1A'
LINE_CLEAR = '\x1b[2K'

# Run YOLO on the Mac's GPU (mps) when available, else an NVIDIA GPU (cuda), else the CPU
if torch.backends.mps.is_available():
    DEVICE = "mps"
elif torch.cuda.is_available():
    DEVICE = "cuda"
else:
    DEVICE = "cpu"

# Orange ball detection (same narrow HSV threshold as labs/object_detection/partA/ball_detect.py)
BALL_LOW = np.array([5, 35, 100], dtype=np.uint8)
BALL_HIGH = np.array([25, 255, 255], dtype=np.uint8)
BALL_MIN_RADIUS = 8          # px. Smaller blobs are ignored (specks, far-away noise)
BALL_MIN_CIRCULARITY = 0.6   # blob area / enclosing circle area. The ball is ~0.8-1.0, the line tape is much lower
BALL_FRAMES_TO_CONFIRM = 3   # ball must show up this many frames in a row before we leave the line

# Stop distance. At the stop position the ball measured ~142 px across in the 320x240 stream
# (box area ~20,000 px^2). Stop a little early because the rover coasts after STOP.
STOP_AREA = 18000            # px^2, box area (diameter^2). ~134 px across / radius ~67 px
LOST_FRAMES_TO_STOP = 5      # stop the motors if the ball disappears for this many frames during approach

# Turning around and getting back to the line. No gyro or encoders, so the 180 is timed:
# tune SPIN_TIME_180 on the real floor until the rover ends up facing back the way it came.
SPIN_SPEED = 150             # 0-255, both wheels, turning in opposite directions
SPIN_TIME_180 = 2.3          # seconds (1.2 s turned ~92 degrees) of spinning for a 180 degree turn. TUNE THIS
SPIN_DIRECTION = 'e'         # 'e' = spin right (clockwise), 'q' = spin left
DRIVE_SPEED = 80             # 0-255, driving straight back toward the line (same as the ESP32's BASE_SPEED)
DRIVE_TIMEOUT = 5.0          # seconds. Stop if no line shows up within this time
LINE_MIN_AREA = 2000         # px^2 of tape in the line camera's frame to count as "line found"
LINE_FRAMES_TO_CONFIRM = 3   # tape must show up this many frames in a row

line_follow_url='http://' + LINE_FOLLOW_IP + '/stream'
object_detection_url='http://' + OBJECT_DETECTION_IP + '/stream'

low_orange = np.array([0, 0, 20], dtype=np.uint8)
high_orange = np.array([70, 255, 255], dtype=np.uint8)
angle_weight = 0


# MISC TASKS

# delete the line to make printing cleaner
def delete_line():
    print(LINE_UP, end=LINE_CLEAR)

def socket_setup(IP, PORT):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    print(f"Connecting to ESP32 at {IP}:{PORT}...")
    sock.connect((IP, PORT))
    print(f"Successfully connected to ESP32 at {IP}:{PORT}.")

    # make each socket non-blocking
    sock.setblocking(False)

    return sock

def recv_line(sock):
    data = b""
    while True:
        try:
            chunk = sock.recv(1)
            if not chunk or chunk == b"\n":
                break
            data += chunk
        except BlockingIOError:
            # no message has arrived so return
            if not data:
                return None
            # Wait a second before requesting again
            time.sleep(0.001)
            continue
    return data.decode("utf-8", errors="ignore").strip()

# Receive command from esp
def receive_command(sock):
    objects = {"pillbottle", "ball", "tissuepack"}
    print("Waiting for voice command...")
    while True:
        cmd = recv_line(sock)
        if cmd is None:
            # recv_line returns None when nothing has arrived yet: keep waiting
            time.sleep(0.01)
            continue
        if not cmd:
            print("Command reading error")
            return "error"

        if cmd in objects:
            print(f"Command Received: {cmd}")
            return cmd

# Returns the YOLO model for the object, or None for the ball (found by color instead).
# if/elif instead of match: the project venv is Python 3.9, and match needs 3.10+.
def pick_model(object_name):
    if object_name == "ball":
        print("Using orange color detection for the ball")
        return None
    elif object_name == "pillbottle":
        model_name = "yolo11n.pt"  # TODO: replace with the trained pill bottle model file
    elif object_name == "tissuepack":
        model_name = "yolo11n.pt"  # TODO: replace with the trained tissue pack model file
    else:
        model_name = "yolo11n.pt"
    print(f"Loading YOLO model [{model_name}]")
    model = YOLO(model_name)
    print("YOLO will run on", DEVICE)
    return model
# END MISC TASKS


# OBJ DETECTION BACKGROUND RENDER
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
            frame_queue.get()

        frame_queue.put(frame)
        #print(f"Put frame {i} on the queue")

# Follow line pretty much ripped from labs
# now returns True at the end 
def follow_line(vid, sock):
    # Capture current frame from ESP32
    ret, frame = vid.read()
    if not ret:
        print("No line read")
        sock.sendall(b"STOP\n")
        return False

    # Blur the frame to reduce noise
    frame = cv2.GaussianBlur(frame, (5, 5), 0)

    # Detect orange tape in HSV
    hsv_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    gray_threshold = cv2.inRange(
        hsv_frame,
        low_orange,
        high_orange
    )

    # Fill small holes in detection
    hole_kernel = np.ones((5, 5), np.uint8)
    gray_threshold = cv2.morphologyEx(gray_threshold, cv2.MORPH_CLOSE, hole_kernel)

    # Detect contours
    gray_threshold_contours, _ = cv2.findContours(gray_threshold, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)

    # Take the largest contour. Filters out some false positives
    if gray_threshold_contours:
        bestContour = max(gray_threshold_contours, key=cv2.contourArea)
        if cv2.contourArea(bestContour) == 0:
            bestContour = None
    else:
        bestContour = None

    # Get frame center
    center_of_frame = np.array([frame.shape[1] / 2, frame.shape[0] / 2], int)

    try:
        if bestContour is not None:
            # Fit line to contour
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

            # Offset error
            y_ref = frame.shape[0] / 2
            x_ref = y_ref * slope + intercept
            offset_error = center_of_frame[0] - x_ref

            # Angle error (slope relative to vertical)
            angle_error = slope

            # Combined error
            error = offset_error + angle_weight * angle_error

            # Draw detected contour
            cv2.putText(frame, "Line: FOUND", (0, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)
            cv2.drawContours(frame, [bestContour], -1, (0, 255, 0), 2)

            # Draw fitted line across image
            y1 = 0
            x1 = int(y1 * slope + intercept)
            y2 = frame.shape[0] - 1
            x2 = int(y2 * slope + intercept)
            cv2.line(frame, (x1, y1), (x2, y2), (255, 0, 255), 2)

            # Display errors
            cv2.putText(frame, f"Offset error: {offset_error:.1f}  Angle error: {angle_error:.2f}", (0, 45), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255))
            cv2.putText(frame, f"Combined error: {error:.1f}", (0, 65), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255))
            print(f"Offset error: {offset_error:.1f}, Angle error: {angle_error:.3f}, Combined error: {error:.1f}")

            sock.sendall((str(error) + "\n").encode("utf-8"))
        else:
            cv2.putText(frame, "Line: NOT FOUND", (0, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 2)
            sock.sendall(b"STOP\n")
    except Exception as e:
        print(f"Exception incurred: {e}")
        sock.sendall(b"STOP\n")

    # Draw the x-axis median line and frame center
    cv2.circle(frame, (center_of_frame[0], center_of_frame[1]), 7, (255, 255, 255), -1)
    cv2.line(frame, (center_of_frame[0], 0), (center_of_frame[0], frame.shape[0]), (0, 255, 255), 2)

    # Display the current video frame
    cv2.imshow("Current Line-Following Output", frame)
    cv2.imshow("Tape Mask", gray_threshold)
    key = cv2.waitKey(1)
    return True

# Send a direct motor command: left speed, right speed, direction letter
# ('w' forward, 's' back, 'q' spin left, 'e' spin right). The line-follow ESP32
# passes anything with a comma straight to the Nano instead of running PID.
def send_motor(sock, left, right, direction):
    sock.sendall(f"{left},{right},{direction}\n".encode("utf-8"))

# How much tape (px^2) the line camera sees, using the same mask as follow_line().
def tape_area(frame):
    blurred = cv2.GaussianBlur(frame, (5, 5), 0)
    hsv = cv2.cvtColor(blurred, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, low_orange, high_orange)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    area = max((cv2.contourArea(c) for c in contours), default=0.0)
    return area, mask

# Show a line-camera frame with a status line. Returns the key pressed (or -1).
def show_line_cam(frame, text, mask=None):
    cv2.putText(frame, text, (0, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 2)
    cv2.imshow("Current Line-Following Output", frame)
    if mask is not None:
        cv2.imshow("Tape Mask", mask)
    return cv2.waitKey(1) & 0xFF

# Stop and quit if q or Esc was pressed
def check_quit(key, sock):
    if key == ord('q') or key == 27:
        sock.sendall(b"STOP\n")
        sys.exit(67)

# Find the orange ball by color, like ball_detect.py.
# Returns ((x, y, radius) or None, mask).
def find_ball(frame):
    blurred = cv2.GaussianBlur(frame, (5, 5), 0)
    hsv = cv2.cvtColor(blurred, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, BALL_LOW, BALL_HIGH)
    kernel = np.ones((5, 5), np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    best = None
    for c in contours:
        (x, y), r = cv2.minEnclosingCircle(c)
        if r < BALL_MIN_RADIUS:
            continue
        if cv2.contourArea(c) / (math.pi * r * r) < BALL_MIN_CIRCULARITY:
            # Not round: either just the orange line tape, or the ball touching
            # the tape so the two merged into one blob. Look for the ball inside it.
            split = ball_inside_blob(mask.shape, c)
            if split is None:
                continue
            x, y, r = split
        else:
            # Round enough. Measure the ball by its widest row instead of the enclosing
            # circle, so a short piece of tape stuck to the ball doesn't inflate its size.
            x, y, r = widest_row(mask.shape, c)
        if best is None or r > best[2]:
            best = (x, y, r)
    return best, mask

# The ball's diameter is the widest horizontal row of its blob. Returns (x, y, radius).
def widest_row(shape, contour):
    bx, by, bw, bh = cv2.boundingRect(contour)
    blob = np.zeros(shape, np.uint8)
    cv2.drawContours(blob, [contour], -1, 255, -1)
    widths = (blob[by:by + bh, bx:bx + bw] > 0).sum(axis=1)
    row = int(np.argmax(widths))
    xs = np.where(blob[by + row, bx:bx + bw] > 0)[0]
    x = bx + (xs[0] + xs[-1]) / 2.0
    return float(x), float(by + row), widths[row] / 2.0

# Find a ball merged with the line tape. The distance transform's peak is the center
# of the biggest circle that fits in the blob: the ball. If the rest of the blob is
# about as thick as that circle, it's only tape (no ball), so return None.
def ball_inside_blob(shape, contour):
    blob = np.zeros(shape, np.uint8)
    cv2.drawContours(blob, [contour], -1, 255, -1)
    dist = cv2.distanceTransform(blob, cv2.DIST_L2, 5)
    _, r, _, (cx, cy) = cv2.minMaxLoc(dist)
    if r < BALL_MIN_RADIUS:
        return None
    rest = dist.copy()
    cv2.circle(rest, (cx, cy), int(1.5 * r) + 2, 0, -1)
    if rest.max() > 0.7 * r:
        return None
    return float(cx), float(cy), r + 0.5

# Use object detection pipeline
# Returns None if no new camera frame has arrived yet,
# otherwise (found, x offset, area). x offset > 0 means the object is left of center.
# area is the bounding box area (width * height) in px^2.
def find_object(frame_queue, model):
    if frame_queue.empty():
        return None

    found = False
    x_offset = 0.0
    contour_area = 0.0

    curr_frame = frame_queue.get()
    center_of_frame = curr_frame.shape[1] / 2.0

    # Ball: color detection (no YOLO model)
    if model is None:
        ball, mask = find_ball(curr_frame)
        if ball is not None:
            x, y, r = ball
            x_offset = center_of_frame - x
            contour_area = (2 * r) ** 2   # same measure as YOLO's width * height
            found = True
            cv2.circle(curr_frame, (int(x), int(y)), int(r), (0, 255, 0), 2)
            cv2.putText(curr_frame, f"area: {contour_area:.0f}  stop at: {STOP_AREA}", (5, 15),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255, 0), 1)
            cv2.putText(curr_frame, f"x offset: {x_offset:+.0f}", (5, 32),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255, 0), 1)
        cv2.imshow("Object Detection", imutils.resize(curr_frame, width=600))
        cv2.imshow("Ball Mask", mask)
        return found, x_offset, contour_area

    results = model(curr_frame, stream=True, device=DEVICE, verbose=False)

    # find the best model if multiple are found
    for result in results:
        annotated_frame = result.plot()
        annotated_frame = imutils.resize(annotated_frame, width=600)
        cv2.imshow("YOLO Output", annotated_frame)

        # check if result is over conf threshold
        if len(result.boxes) > 0:
            # according to google the boxes are default sorted
            # by highest conf value, so [0] should be the best :/
            best_contour = result.boxes[0]
            best_conf = float(result.boxes.conf[0])
            if best_conf >= CONFIDENCE_THRESHOLD:
                x_center, y_center, width, height = best_contour.xywh[0].tolist()
                x_offset = center_of_frame - x_center
                contour_area = width * height
                found = True
    return found, x_offset, contour_area
                

# Main driver function
# hopefully mimics a state machine like in a robot idk
def retrieve_object(line_follow_sock, object_detection_sock, model, frame_queue):
    # Line follow initialize
    line_follow_vid = cv2.VideoCapture(line_follow_url)
    time.sleep(2)

    objectFound = False
    seen_frames = 0
    # Follow line until object is found
    print("Following line and scanning for object...")
    while True:
        # identify object and return the values
        detection = find_object(frame_queue, model)
        if detection is not None:  # None = no new detection frame yet
            found, x_offset, contour_area = detection
            # count frames in a row with the object, so one bad frame doesn't pull us off the line
            seen_frames = seen_frames + 1 if found else 0

        # exit if found object
        if seen_frames >= BALL_FRAMES_TO_CONFIRM:
            line_follow_sock.sendall(b"STOP\n")
            break

        # else follow line
        following = follow_line(line_follow_vid, line_follow_sock)
        key = cv2.waitKey(1) & 0xFF
        if following == False or key == ord('q') or key == 27:
            line_follow_sock.sendall(b"STOP\n")
            sys.exit(67)


    # Seek out object and pick it up
    print("Object Found! Seeking object...")
    lost_frames = 0
    while True:
        detection = find_object(frame_queue, model)

        if detection is not None:  # only act on new detection frames
            found, x_offset, contour_area = detection

            if found:
                lost_frames = 0
                # MAYBE DONT USE ULTRASONIC :O
                if contour_area >= STOP_AREA:
                    line_follow_sock.sendall(b"STOP\n")
                    print(f"Reached object (area {contour_area:.0f} >= {STOP_AREA}). Stopped.")
                    break
                # Steer toward the object: send its offset from the frame center as the
                # error, the same way follow_line sends the line's offset. The ESP32's
                # PID turns it into wheel speeds, so no firmware change is needed.
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

    # Stopped in front of the object. Grabbing isn't written yet: wait for a key press
    # instead, which also gives you time to check the stop position.
    print("Stopped in front of the object. Press any key in a video window to turn around (q to quit).")
    check_quit(cv2.waitKey(0) & 0xFF, line_follow_sock)

    # # Grab object
    # print("Grabbing object...")
    # (send the grab command to the Nano here and wait for it to finish)

    # The line camera wasn't read during the approach, so its buffer is full of old frames.
    # Reopen it to get live ones.
    line_follow_vid.release()
    line_follow_vid = cv2.VideoCapture(line_follow_url)

    # Turn around: spin in place for a fixed time
    print(f"Turning around ({SPIN_TIME_180:.2f} s at speed {SPIN_SPEED})...")
    send_motor(line_follow_sock, SPIN_SPEED, SPIN_SPEED, SPIN_DIRECTION)
    spin_end = time.monotonic() + SPIN_TIME_180
    while time.monotonic() < spin_end:
        # keep reading frames during the spin so the buffer stays fresh and the window updates
        ret, frame = line_follow_vid.read()
        key = show_line_cam(frame, "Turning around") if ret else cv2.waitKey(1) & 0xFF
        check_quit(key, line_follow_sock)
    line_follow_sock.sendall(b"STOP\n")
    time.sleep(0.3)  # let the rover settle so it doesn't drift sideways into the forward drive

    # Drive straight until the line camera sees the tape
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

    # Back on the line: follow it
    print("Line found! Following the line back. Press q to stop.")
    while True:
        following = follow_line(line_follow_vid, line_follow_sock)
        key = cv2.waitKey(1) & 0xFF
        if following == False:
            line_follow_sock.sendall(b"STOP\n")
            sys.exit(67)
        check_quit(key, line_follow_sock)



def main():
    time.sleep(2)

    # Connect to esps
    line_following_sock = socket_setup(LINE_FOLLOW_IP, TCP_PORT)
    object_detection_sock = socket_setup(OBJECT_DETECTION_IP, TCP_PORT)

    # Voice command disabled for testing: start line following right away, looking for the ball.
    # To turn voice back on, delete the next line and uncomment the block below it.
    objectName = "ball"
    # # Wait until a voice command is given
    # objectName = receive_command(line_following_sock)
    # if objectName == "error":
    #     print("Error retrieving object input")
    #     line_following_sock.close()
    #     object_detection_sock.close()
    #     sys.exit(1)

    model = pick_model(objectName)

    # Initialize background frame queue for obj_detection
    frame_queue = queue.Queue(maxsize = 2)
    threading.Thread(
        target=stream_reader,
        args=(frame_queue, object_detection_url),
        daemon=True
    ).start()

    # Run object retrieval
    try:
        retrieve_object(line_following_sock, object_detection_sock, model, frame_queue)
    finally:
        line_following_sock.close()
        object_detection_sock.close()
        cv2.destroyAllWindows()

if __name__ == "__main__":
    main()

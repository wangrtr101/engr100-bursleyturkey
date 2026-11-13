import sys
import cv2
import socket
import numpy as np
import time
import select
from ultralytics import YOLO
import imutils
import threading
import queue

LINE_FOLLOW_IP = '192.168.50.225'
OBJECT_DETECTION_IP = '192.168.50.226'
TCP_PORT = 5005

CONFIDENCE_THRESHOLD = 0.5

line_follow_url='http://' + LINE_FOLLOW_IP + '/stream'
object_detection_url='http://' + OBJECT_DETECTION_IP + '/stream'

low_orange = np.array([0, 0, 20], dtype=np.uint8)
high_orange = np.array([70, 255, 255], dtype=np.uint8)
angle_weight = 0

# MISC TASKS
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
            # buffer is empty, wait before requesting again
            time.sleep(0.001)
            continue
    return data.decode().strip()

# Receive command from esp
def receive_command(sock):
    objects = {"pillbottle", "ball", "tissuepack"}
    print("Waiting for voice command...")
    while True:
        cmd = recv_line(sock)
        if not cmd:
            print("Command reading error")
            return "error"

        if cmd in objects:
            print(f"Command Received: {cmd}")
            return cmd

def pick_model(object_name):
    match object_name:
        case "ball":
            model_name = #file name
        case "pillbottle":
            model_name = #file name
        case "tissuepack":
            model_name = #file name
        case _:
            model_name = "yolo11n.pt"
    print(f"Loading YOLO model [{model}]")
    model = YOLO(model_name)
    is_gpu = next(model.parameters()).device.type == "cuda"
    print("Loaded YOLO model on", "GPU" if is_gpu else "CPU")
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

def stream_processor(frame_queue, model):
    print("Starting stream_processor thread...")
    while True:
        curr_frame = frame_queue.get()
        results = model(curr_frame, stream=True)
        # annotated_frame = results[0].plot()
        # annotated_frame = imutils.resize(annotated_frame, width=600)
        # Iterate through results (only 1 item for single frame)
        for result in results:
            annotated_frame = result.plot()  # Plot boxes/labels
            annotated_frame = imutils.resize(annotated_frame, width=600)
            cv2.imshow("YOLO Output", annotated_frame)
        cv2.imshow("YOLO Output", annotated_frame)
        if cv2.waitKey(1) == 27:
            break

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

# Use object detection pipeline
# Returns the object found, x offset, contour area 
def find_object(frame_queue, model):
    if frame.queue.empty():
        return False, 0.0, 0.0

    found = False
    x_offset = 0.0
    contour_area = 0.0

    curr_frame = frame.queue.get()
    center_of_frame = curr_frame.shape[1] / 2.0
    results = model(curr_frame, stream=True)

    # find the best model if multiple are found
    for result in results:
        annotated_frame = result.plot()
        annotated_frame = imutils.resize(annotated_frame, width=600)
        cv2.imshow("YOLO Output", annotated_frame)

        # check if result is over conf threshold
        if result.boxes:
            # according to google the boxes are default sorted
            # by highest conf value, so [0] should be the best :/
            best_contour = result.boxes[0]
            best_conf = float(result.boxes[0])
            if best_conf >= CONFIDENCE_THRESHOLD:
                x_center, y_center, width, height = best_contour[0].xywh.cpu().numpy()
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
    # Follow line until object is found
    print("Following line and scanning for object...")
    while True:    
        # identify object and return the values
        found, x_offset, contour_area = find_object(frame_queue, model)
        
        # exit if found object
        if found:
            line_follow_sock.sendall(b"STOP\n")
            break

        # else follow line
        following = follow_line(line_follow_sock, line_follow_vid)
        key = cv2.waitKey(1) & 0xFF
        if following == False or key == ord('q') or key == 27: 
            line_follow_sock.sendall(b"STOP\n")
            sys.exit(67)

            
    # Seek out object and pick it up
    print("Object Found! Seeking object...")
    while True:
        found, x_offset, contour_area = find_object(frame_queue, model)

        if found:
            # MAYBE DONT USE ULTRASONIC :O
            if contour_area >=

        else:
            print("Lost object :(")
            line_follow_sock.sendall(b"STOP\n")

        key = cv2.waitKey(1) & 0xFF
        if key == ord('q') or key == 27:
            line_follow_sock.sendall(b"STOP\n")
            sys.exit(67)

    # Grab object
    print("Grabbing object...")
    while True:
        assert True
    time.sleep(5)
    
    # Turn around and return to the line
    print("Refinding the line")
    while True:
        assert True
    

    # Drive back to the end
    print("Return to the user")
    while True:
        assert True



def main():
    time.sleep(2)

    # Connect to esps
    line_following_sock = socket_setup(LINE_FOLLOW_IP, TCP_PORT)
    object_detection_sock = socket_setup(OBJECT_DETECTION_IP, TCP_PORT)

    # Wait until a voice command is given
    objectName = receive_command(line_following_sock)
    if objectName == "error":
        print("Error retrieving object input")
        line_following_sock.close()
        object_detection_sock.close()
        sys.exit(1)

    model = pick_model(objectName)

    # Initialize background frame queue for obj_detection
    frame_queue = queue.Queue(maxsize = 2)
    threading.Thread(
        target=stream_reader,
        args=(frame_queue, object_detection_url),
        daemon=True
    ).start()
    try:
        retrieve_object(line_following_sock, object_detection_sock, model, frame_queue)
    finally:
        line_follow_sock.close()
        object_detection_sock.close()
        cv2.destroyAllWindows()

if __name__ == "__main__":
    main()

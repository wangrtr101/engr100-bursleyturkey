import cv2
import socket
import numpy as np
import imutils
import threading
import queue
import time
import select

LINE_FOLLOW_IP = '192.168.50.102'
TCP_PORT = 5005

line_follow_url='http://' + LINE_FOLLOW_IP + '/stream'

low_black = np.uint8([55, 55, 55])
high_black = np.uint8([0, 0, 0])
kernel = np.ones((15, 15), np.float32) / 255

def socket_setup():
    line_follow_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    print(f"Connecting to Line-Following ESP32 at {LINE_FOLLOW_IP}:{TCP_PORT}...")
    line_follow_sock.connect((LINE_FOLLOW_IP, TCP_PORT))
    print("Successfully connected to Line Folllowing ESP32.")

    # make each socket non-blocking
    line_follow_sock.setblocking(False)

    return line_follow_sock

def recv_line(sock):
    data = b""
    while True:
        chunk = sock.recv(1)
        if not chunk:
            break
        if chunk == b"\n":
            break
        data += chunk
    return data.decode().strip()

def follow_line(sock):
    vid = cv2.VideoCapture(line_follow_url)
    while True:
        # Capture current frame from ESP32
        ret, frame = vid.read()
        if not ret:
            print("Couldn't read frame. Killing program.")

        # Blur the frame to reduce noise
        frame = cv2.GaussianBlur(frame, (5, 5), 0)
        gray_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

        # Get black pixels (these values depend on room light)
        gray_threshold = cv2.adaptiveThreshold(
            gray_frame,
            255,
            cv2.ADAPTIVE_THRESH_MEAN_C,
            cv2.THRESH_BINARY_INV,
            103,  # block size
            10   # constant to subtract
        )
        # Fill small holes in detection
        hole_kernel = np.ones((5, 5), np.uint8)
        gray_threshold = cv2.morphologyEx(gray_threshold, cv2.MORPH_CLOSE, hole_kernel)

        # Detect contours
        gray_threshold_contours, _ = cv2.findContours(gray_threshold, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)

        # Take the highest (yAxis) contours. Filters out some false positives
        try:
            bestContour = max(gray_threshold_contours, key=lambda c: cv2.boundingRect(c)[3])
        except:
            bestContour = None

        # Get frame center
        center_of_frame = np.array([frame.shape[1] / 2, frame.shape[0] / 2], int)

        try:
            if bestContour is not None:
                cv2.putText(frame, "Line: FOUND", (0, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)
                cv2.drawContours(frame, [bestContour], -1, (0, 255, 0), 2)

                M = cv2.moments(bestContour)
                center_of_contour = np.array([int(M['m10'] / M['m00']), int(M['m01'] / M['m00'])], int)

                # Calculate CTE (Cross-Track Error) between detected line and frame center
                cte_x = center_of_frame[0] - center_of_contour[0]
                cv2.putText(frame, "Cross Track Error (x): " + str(cte_x), (0, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255))
                print(f"X-axis CTE: {cte_x}")
                sock.sendall((str(cte_x) + "\n").encode("utf-8"))

            else:
                cv2.putText(frame, "Line: NOT FOUND", (0, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 2)

        except Exception as e:
            print(f"Exception incurred: {e}")

        # Draw the x-axis median line and frame center
        cv2.circle(frame, (center_of_frame[0], center_of_frame[1]), 7, (255, 255, 255), -1)
        cv2.line(frame, (center_of_frame[0], 0), (center_of_frame[0], frame.shape[0]), (0, 255, 255), 2)

        # Display the current video frame
        cv2.imshow("Current Line-Following Output", frame)
        key = cv2.waitKey(1)
        if key == ord('q'):
            break

        # Read the motor settings from the ESP32
        #res = recv_line(sock)
        #if res is not None:
        #    print(f"Motor settings: {res}")
    sock.close()
    cv2.destroyAllWindows()

def main():
    time.sleep(5)
    # Connect to both the line following and object detection ESP32s
    line_following_sock = socket_setup()

    # start following the line
    follow_line(line_following_sock)

if __name__ == "__main__":
    main()


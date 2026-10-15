import cv2
import socket
import numpy as np
import time
import select

LINE_FOLLOW_IP = '192.168.50.225'
TCP_PORT = 5005

line_follow_url='http://' + LINE_FOLLOW_IP + '/stream'

low_orange = np.array([0, 0, 20], dtype=np.uint8)
high_orange = np.array([70, 255, 255], dtype=np.uint8)
angle_weight = 0

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
            sock.sendall(b"STOP\n")
            break

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
        if key == ord('q'):
            sock.sendall(b"STOP\n")
            break

    vid.release()
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

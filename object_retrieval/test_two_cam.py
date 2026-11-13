import cv2
import socket
import time

LINE_FOLLOW_IP = '192.168.50.225'
OBJECT_DETECTION_IP = '192.168.50.226'
TCP_PORT = 5005

line_follow_url = f'http://{LINE_FOLLOW_IP}/stream'
object_detection_url = f'http://{OBJECT_DETECTION_IP}/stream'

def socket_setup(ip, port):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    print(f"Connecting to ESP32 at {ip}:{port}...")
    sock.connect((ip, port))
    print(f"Successfully connected to ESP32 at {ip}:{port}.")
    sock.setblocking(False)
    return sock

def main():
    # Connect to both ESP32 TCP sockets
    line_follow_sock = socket_setup(LINE_FOLLOW_IP, TCP_PORT)
    object_detection_sock = socket_setup(OBJECT_DETECTION_IP, TCP_PORT)

    # Open both video streams
    print("Opening video streams...")
    line_follow_vid = cv2.VideoCapture(line_follow_url)
    object_detection_vid = cv2.VideoCapture(object_detection_url)
    time.sleep(2)  # Give streams a moment to stabilize

    if not line_follow_vid.isOpened():
        print("Warning: Could not open Line Follow video stream.")
    if not object_detection_vid.isOpened():
        print("Warning: Could not open Object Detection video stream.")

    # Display both streams in a loop
    while True:
        ret1, frame1 = line_follow_vid.read()
        ret2, frame2 = object_detection_vid.read()

        if ret1:
            cv2.imshow("Line Follow Stream", frame1)
        if ret2:
            cv2.imshow("Object Detection Stream", frame2)

        # Press 'q' or 'ESC' to quit
        key = cv2.waitKey(1) & 0xFF
        if key == ord('q') or key == 27:
            break

    # 4. Clean up connections and windows
    line_follow_vid.release()
    object_detection_vid.release()
    line_follow_sock.close()
    object_detection_sock.close()
    cv2.destroyAllWindows()
    print("Closed all streams and sockets.")

if __name__ == "__main__":
    main()
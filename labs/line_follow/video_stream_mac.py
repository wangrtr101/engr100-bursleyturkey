from collections import deque
import numpy as np
import cv2
import imutils
import time
import socket
import threading
import termios
import tty
import sys
import queue

TCP_IP = '192.168.50.225'
TCP_PORT = 5005
url = 'http://192.168.50.225/stream'

def socket_setup():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    print(f"Connecting to ESP32 at {TCP_IP}:{TCP_PORT}...")
    s.connect((TCP_IP, TCP_PORT))
    print("Successfully connected to ESP32.")
    return s

def video_capture(url, frame_queue):
    vid = cv2.VideoCapture(url)
    if not vid.isOpened():
        print("Error: Cannot open video stream.")
        return
    
    
    while True:
        ret, frame = vid.read()
        if not ret:
            print("Couldn't read frame. Stopping video thread.")
            break

        frame = imutils.resize(frame, width=600)

        frame = cv2.rotate(frame, cv2.ROTATE_180)

        if not frame_queue.full():
            frame_queue.put(frame)

def getch():
    """Read a single character (no Enter required). Works on macOS."""
    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        ch = sys.stdin.read(1)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
    return ch

def keyboard_reader(sock):
    while True:
        ch = getch()
        if ch in ("w", "a", "s", "d", "x"):
            sock.sendall((ch + "\n").encode("utf-8"))
            print(f"Sent: {ch}")
        elif ch == "q":
            print("Quitting keyboard thread...")
            break

if __name__ == "__main__":
    sock = socket_setup()
    frame_queue = queue.Queue(maxsize=1)

    # Start the video reader thread
    video_thread = threading.Thread(target=video_capture, args=(url, frame_queue), daemon=True)
    video_thread.start()

    # Start keyboard listener thread
    key_thread = threading.Thread(target=keyboard_reader, args=(sock,), daemon=True)
    key_thread.start()

    print("Press 'q' in the video window to quit.")

    # Display loop must be in MAIN THREAD on macOS
    while True:
        if not frame_queue.empty():
            frame = frame_queue.get()
            cv2.imshow("Frame", frame)

        # cv2.waitKey must run in main thread on macOS too
        key = cv2.waitKey(1) & 0xFF
        if key == ord('q'):
            print("Exiting program...")
            break

    cv2.destroyAllWindows()

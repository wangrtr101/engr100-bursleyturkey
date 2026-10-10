# import the necessary packages
from collections import deque
from imutils.video import VideoStream
import numpy as np
import cv2
import imutils
import time
import socket
import threading
import termios
import tty
import sys

TCP_IP = '192.168.50.101'
TCP_PORT = 5005

url='http://192.168.50.101/stream'
im=None

def socket_setup():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    # Connect to the ESP32
    print(f"Connecting to ESP32 at {TCP_IP}:{TCP_PORT}...")
    s.connect((TCP_IP, TCP_PORT))
    print("Succesfully connected to ESP32.")

    return s

def video_stream(url):
    #Define a video capture object
    vid = cv2.VideoCapture(url)
    #keep looping
    while True:
        #Grab the current frame stored at the ESP32-CAM
        ret, frame=vid.read()
        if not ret:
            print("Couldn't read frame. Killing thread.")
            break

        # resize frame
        frame = imutils.resize(frame, width=600)

        #Show the frame to the computer screen
        cv2.imshow("Frame", frame)
        cv2.waitKey(1)

def getch():
    """Read a single character (no Enter required). Works on Linux/macOS/WSL."""
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
        if ch == "w" or ch == "a" or ch == "s" or ch == "d" or ch == "x":
            sock.sendall((ch + "\n").encode("utf-8"))
            print(f"Sent: {ch}")
        if ch == "q":
            print("Quitting...")
            break


if __name__ == "__main__":
    # Connect to the ESP32
    sock = socket_setup()

    # Start up both the video stream and keyboard reader threads
    threading.Thread(target=video_stream, args=(url,), daemon=True).start()
    keyboard_reader(sock)

"""
Ball trap-threshold calibration.

Streams the object-detection ESP32-CAM, finds the orange ball with the same HSV
approach as labs/object_detection/partA/ball_detect.py, and shows how big the
ball looks on screen. Put the ball where the claw should close on it, read the
numbers, and use them as the trap threshold in object_retrieval.py.

Run from the repo root:
    python3 object_retrieval/ball_area_calibrate.py
    python3 object_retrieval/ball_area_calibrate.py --url http://192.168.50.225/stream   # other camera

Keys (click the video window first):
    n / m / w   narrow / medium / wide orange threshold (same presets as ball_detect.py)
    space       save the current reading to ball_area_log.csv
    q / Esc     quit
The "Trap at %" slider shows TRAP on the video once the ball covers that much of the frame.
"""
import argparse
import csv
import math
import os
import threading
import time
from datetime import datetime

import cv2
import numpy as np

DEFAULT_URL = "http://192.168.50.226/stream"  # object-detection ESP32-CAM

# HSV presets copied from labs/object_detection/partA/ball_detect.py
THRESHOLDS = {
    "narrow": (np.array([5, 35, 100], np.uint8), np.array([25, 255, 255], np.uint8)),
    "medium": (np.array([0, 15, 80], np.uint8), np.array([35, 255, 255], np.uint8)),
    "wide": (np.array([0, 5, 50], np.uint8), np.array([45, 255, 255], np.uint8)),
}

MIN_CIRCULARITY = 0.6  # blob area / enclosing-circle area. A ball is ~0.8-1.0; a strip of tape is far lower.
MIN_RADIUS_PX = 3      # ignore specks
MAX_ATTACHED_THICKNESS = 0.7  # tape attached to a ball must be under 0.7x the ball's radius in half-width
SMOOTHING = 0.3        # weight of each new reading in the running average (higher = less smoothing)
KERNEL = np.ones((5, 5), np.uint8)
DISPLAY_SCALE = 2      # the ESP32 sends 320x240; show it twice as big
WINDOW = "Ball calibration"
LOG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ball_area_log.csv")


class LatestFrame:
    """Reads the MJPEG stream in a background thread and keeps only the newest frame,
    so what you see is what the camera sees now, not a backlog from seconds ago."""

    def __init__(self, url):
        self.url = url
        self.frame = None
        self.lock = threading.Lock()
        self.running = True
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def _run(self):
        cap = cv2.VideoCapture(self.url)
        while self.running:
            ok, frame = cap.read()
            if not ok:
                # Stream dropped or not up yet: reconnect after a short pause.
                cap.release()
                time.sleep(0.5)
                cap = cv2.VideoCapture(self.url)
                continue
            with self.lock:
                self.frame = frame
        cap.release()

    def read(self):
        with self.lock:
            return None if self.frame is None else self.frame.copy()

    def stop(self):
        self.running = False


def detect_ball(frame, lower, upper):
    """Find the largest round orange blob.

    Returns (ball, mask). ball is None if nothing round enough was found, otherwise a dict:
      x, y          center in pixels
      radius        enclosing-circle radius in pixels
      contour_area  pixels inside the blob outline
      box_area      width * height of the bounding box. Same measure as YOLO's xywh
                    width*height in object_retrieval.py's find_object(), so a threshold
                    picked here carries over when you switch to YOLO.
      box           (x, y, w, h) bounding box
      circularity   contour_area / (pi * radius^2), or None if split from the tape
      method        "round blob" or "split from tape"
    """
    blurred = cv2.GaussianBlur(frame, (5, 5), 0)
    hsv = cv2.cvtColor(blurred, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, lower, upper)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, KERNEL)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, KERNEL)

    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    best = None
    for c in contours:
        area = cv2.contourArea(c)
        (x, y), r = cv2.minEnclosingCircle(c)
        if r < MIN_RADIUS_PX:
            continue
        circularity = area / (math.pi * r * r)
        if circularity >= MIN_CIRCULARITY:
            bx, by, bw, bh = cv2.boundingRect(c)
            candidate = {
                "x": x,
                "y": y,
                "radius": r,
                "contour_area": area,
                "box_area": bw * bh,
                "box": (bx, by, bw, bh),
                "circularity": circularity,
                "method": "round blob",
            }
        else:
            # Not round: either just tape, or the ball touching the tape so the two
            # merged into one blob. Look for a ball-sized bulge inside it.
            candidate = ball_inside_blob(mask.shape, c)
        if candidate is not None and (best is None or candidate["contour_area"] > best["contour_area"]):
            best = candidate
    return best, mask


def ball_inside_blob(shape, contour):
    """Find a ball merged with the line tape.

    The distance transform gives, for every pixel of the blob, how far it is from the
    blob's edge. Its peak is the center of the biggest circle that fits inside the blob.
    If the ball is attached to the tape, that circle is the ball, and everywhere else
    (along the tape) the blob is much thinner. If the blob is only tape, the same
    thickness continues along the strip, so the second-thickest spot (away from the
    first) is about as thick as the first, and it's rejected.
    """
    blob = np.zeros(shape, np.uint8)
    cv2.drawContours(blob, [contour], -1, 255, -1)
    dist = cv2.distanceTransform(blob, cv2.DIST_L2, 5)
    _, r, _, (cx, cy) = cv2.minMaxLoc(dist)
    if r < MIN_RADIUS_PX:
        return None
    rest = dist.copy()
    cv2.circle(rest, (cx, cy), int(1.5 * r) + 2, 0, -1)
    if rest.max() > MAX_ATTACHED_THICKNESS * r:
        return None  # thick everywhere: tape (or a tape end), not a ball
    r += 0.5  # distance transform measures to pixel centers; nudge back to the edge
    side = int(round(2 * r))
    return {
        "x": float(cx),
        "y": float(cy),
        "radius": r,
        "contour_area": math.pi * r * r,  # estimate: the tape part is excluded
        "box_area": side * side,           # what a box drawn around just the ball would be
        "box": (int(round(cx - r)), int(round(cy - r)), side, side),
        "circularity": None,
        "method": "split from tape",
    }


def put_lines(img, lines, origin=(10, 24), color=(255, 255, 255)):
    x, y = origin
    for line in lines:
        # dark outline first so the text is readable on any background
        cv2.putText(img, line, (x, y), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 4, cv2.LINE_AA)
        cv2.putText(img, line, (x, y), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 1, cv2.LINE_AA)
        y += 24


def log_reading(mode, ball, frame_area, smoothed_pct, x_offset):
    new_file = not os.path.exists(LOG_FILE)
    with open(LOG_FILE, "a", newline="") as f:
        writer = csv.writer(f)
        if new_file:
            writer.writerow(["time", "threshold", "box_area_px", "box_pct_of_frame",
                             "smoothed_box_pct", "contour_area_px", "radius_px", "x_offset_px", "found_as"])
        writer.writerow([
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"), mode,
            ball["box_area"], round(100 * ball["box_area"] / frame_area, 2),
            round(smoothed_pct, 2), round(ball["contour_area"], 1),
            round(ball["radius"], 1), round(x_offset, 1), ball["method"],
        ])


def main():
    parser = argparse.ArgumentParser(description="Find the ball size at which to trap it.")
    parser.add_argument("--url", default=DEFAULT_URL, help="ESP32-CAM stream URL")
    parser.add_argument("--threshold", choices=THRESHOLDS, default="narrow",
                        help="starting orange threshold preset")
    args = parser.parse_args()

    mode = args.threshold
    print(f"Connecting to {args.url} ...")
    print("Keys: n/m/w = threshold preset, space = save reading, q = quit")
    stream = LatestFrame(args.url)

    cv2.namedWindow(WINDOW)
    cv2.createTrackbar("Trap at %", WINDOW, 15, 100, lambda v: None)

    smoothed_pct = None
    frames, fps, fps_timer = 0, 0.0, time.time()

    try:
        while True:
            frame = stream.read()
            if frame is None:
                waiting = np.zeros((240 * DISPLAY_SCALE, 320 * DISPLAY_SCALE, 3), np.uint8)
                put_lines(waiting, [f"Waiting for {args.url} ...",
                                    "Is the ESP32 on and nothing else viewing the stream?"])
                cv2.imshow(WINDOW, waiting)
                if (cv2.waitKey(100) & 0xFF) in (ord("q"), 27):
                    break
                continue

            h, w = frame.shape[:2]
            frame_area = w * h
            lower, upper = THRESHOLDS[mode]
            ball, mask = detect_ball(frame, lower, upper)

            frames += 1
            if time.time() - fps_timer >= 1.0:
                fps = frames / (time.time() - fps_timer)
                frames, fps_timer = 0, time.time()

            trap_pct = cv2.getTrackbarPos("Trap at %", WINDOW)
            display = cv2.resize(frame, (w * DISPLAY_SCALE, h * DISPLAY_SCALE))
            s = DISPLAY_SCALE
            cv2.line(display, (w * s // 2, 0), (w * s // 2, h * s), (0, 255, 255), 1)  # frame center

            if ball is not None:
                pct = 100.0 * ball["box_area"] / frame_area
                smoothed_pct = pct if smoothed_pct is None else SMOOTHING * pct + (1 - SMOOTHING) * smoothed_pct
                x_offset = w / 2 - ball["x"]  # same sign as object_retrieval.py: + means ball is left of center
                trap = smoothed_pct >= trap_pct

                bx, by, bw, bh = ball["box"]
                color = (0, 0, 255) if trap else (0, 255, 0)
                cv2.rectangle(display, (bx * s, by * s), ((bx + bw) * s, (by + bh) * s), color, 2)
                cv2.circle(display, (int(ball["x"] * s), int(ball["y"] * s)), int(ball["radius"] * s), (255, 0, 0), 1)

                put_lines(display, [
                    f"box area: {ball['box_area']} px  ({pct:.1f}% of frame)",
                    f"smoothed: {smoothed_pct:.1f}%   trap at: {trap_pct}%",
                    f"contour area: {ball['contour_area']:.0f} px   radius: {ball['radius']:.0f} px",
                    f"x offset: {x_offset:+.0f} px   found as: {ball['method']}",
                ])
                if trap:
                    put_lines(display, ["TRAP"], origin=(w * s - 90, 34), color=(0, 0, 255))
            else:
                smoothed_pct = None
                x_offset = 0.0
                put_lines(display, ["no ball"], color=(0, 0, 255))

            put_lines(display, [f"{mode} threshold   {fps:.0f} fps   {w}x{h}"], origin=(10, h * s - 12))
            cv2.imshow(WINDOW, display)
            cv2.imshow("Orange mask", mask)

            key = cv2.waitKey(1) & 0xFF
            if key in (ord("q"), 27):
                break
            if key == ord("n"):
                mode = "narrow"
            elif key == ord("m"):
                mode = "medium"
            elif key == ord("w"):
                mode = "wide"
            elif key == ord(" "):
                if ball is None:
                    print("No ball in view, nothing saved.")
                else:
                    log_reading(mode, ball, frame_area, smoothed_pct, x_offset)
                    print(f"Saved: box area {ball['box_area']} px "
                          f"({100 * ball['box_area'] / frame_area:.1f}% of frame), "
                          f"contour area {ball['contour_area']:.0f} px, x offset {x_offset:+.0f} px "
                          f"-> {os.path.basename(LOG_FILE)}")
    finally:
        stream.stop()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()

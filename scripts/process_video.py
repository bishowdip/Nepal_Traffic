"""
scripts/process_video.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Real-video vehicle detection for Nepal Traffic AI.

Works in two modes:
  1. VIDEO FILE  — process a recorded .mp4 / .avi / .mov file
  2. RTSP STREAM — connect to a live IP camera or checkpoint camera

Detection pipeline per frame:
  Frame → YOLOv8 vehicle detection → crop ROI → plate OCR → classifier → API

Usage examples:
  # Process a downloaded video file:
  python -m scripts.process_video --source /path/to/traffic.mp4

  # Process from webcam (device index 0):
  python -m scripts.process_video --source 0

  # Process from RTSP camera:
  python -m scripts.process_video --source rtsp://192.168.1.10:554/stream1

  # Show live preview window while processing:
  python -m scripts.process_video --source traffic.mp4 --preview

  # Skip every N frames (faster, useful for high-FPS video):
  python -m scripts.process_video --source traffic.mp4 --skip-frames 5

  # Use mock OCR (no PaddleOCR needed, uses synthetic plates):
  python -m scripts.process_video --source traffic.mp4 --mock-ocr

  # Save annotated output video:
  python -m scripts.process_video --source traffic.mp4 --save-output output_annotated.mp4
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

import sys
import os
import argparse
import asyncio
import base64
import time
import logging
import uuid
import json
from datetime import datetime
from pathlib import Path
from typing import Optional

# ── Allow running as `python -m scripts.process_video` from project root ──────
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import httpx
import numpy as np

# ── Logging setup ─────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("process_video")

API_BASE   = "http://localhost:8000/api"
INGEST_URL = f"{API_BASE}/ingest"


# ═════════════════════════════════════════════════════════════════════════════
# YOLO loader
# ═════════════════════════════════════════════════════════════════════════════

def load_yolo(model_path: str = "yolov8n.pt"):
    """Load YOLOv8 model. Downloads yolov8n.pt automatically on first run."""
    try:
        from ultralytics import YOLO
        log.info(f"Loading YOLOv8 model: {model_path}")
        model = YOLO(model_path)
        log.info("✓ YOLOv8 loaded successfully")
        return model
    except ImportError:
        log.error("ultralytics not installed. Run: pip install ultralytics")
        sys.exit(1)
    except Exception as e:
        log.error(f"Failed to load YOLO model: {e}")
        sys.exit(1)


# ═════════════════════════════════════════════════════════════════════════════
# OCR loader (optional — graceful fallback)
# ═════════════════════════════════════════════════════════════════════════════

_ocr_engine   = None
_ocr_dev_mode = False  # True when real OCR unavailable → use mock plates


def load_ocr():
    """Try to load PaddleOCR. Returns None if unavailable (mock mode used)."""
    global _ocr_engine, _ocr_dev_mode
    try:
        from paddleocr import PaddleOCR
        _ocr_engine = PaddleOCR(use_angle_cls=True, lang="en", show_log=False)
        log.info("✓ PaddleOCR loaded (English / plate mode)")
    except Exception as e:
        log.warning(f"PaddleOCR unavailable ({e}). Using mock plate text instead.")
        _ocr_dev_mode = True


def read_plate(roi: np.ndarray) -> tuple[str, float]:
    """
    Run OCR on a plate ROI image.
    Returns (plate_text, confidence).
    Falls back to mock plate if OCR is unavailable.
    """
    if _ocr_dev_mode or _ocr_engine is None or roi.size == 0:
        return _mock_plate_text(), round(float(np.random.uniform(0.55, 0.92)), 3)

    try:
        result = _ocr_engine.ocr(roi, cls=True)
        if not result or not result[0]:
            return "", 0.0

        texts = []
        confs = []
        for line in result[0]:
            if line and len(line) >= 2:
                txt  = line[1][0].strip()
                conf = float(line[1][1])
                if txt:
                    texts.append(txt)
                    confs.append(conf)

        if not texts:
            return "", 0.0

        plate_text = " ".join(texts)
        avg_conf   = sum(confs) / len(confs)
        return plate_text, round(avg_conf, 3)
    except Exception as e:
        log.debug(f"OCR error: {e}")
        return "", 0.0


def read_route_devanagari(roi: np.ndarray) -> tuple[str, str, str]:
    """
    Read Devanagari route text from the front panel of a bus.
    Returns (raw_text, origin_city, destination_city).
    """
    if _ocr_dev_mode or _ocr_engine is None or roi.size == 0:
        return "", "", ""

    try:
        # Import the route parser from the existing service
        from backend.services.ocr import parse_route_text
        result = parse_route_text(roi)
        return result.get("raw_text", ""), result.get("origin", ""), result.get("destination", "")
    except Exception:
        return "", "", ""


# ═════════════════════════════════════════════════════════════════════════════
# Mock plate generator (used when OCR not available)
# ═════════════════════════════════════════════════════════════════════════════

_MOCK_DISTRICTS = ["Ba", "Ko", "Me", "La", "Bha", "Ka", "Chi", "Ra", "Su", "Mo"]
_MOCK_LETTERS   = ["Ka", "Kha", "Ga", "Gha", "Cha", "Ja", "Ta", "Da", "Pa", "Ba", "Ma"]
import random

def _mock_plate_text() -> str:
    dc  = random.choice(_MOCK_DISTRICTS)
    ser = random.randint(1, 9)
    let = random.choice(_MOCK_LETTERS)
    num = random.randint(1, 9999)
    return f"{dc} {ser} {let} {str(num).zfill(4)}"


# ═════════════════════════════════════════════════════════════════════════════
# YOLO class mapping → Nepal vehicle types
# ═════════════════════════════════════════════════════════════════════════════

# COCO class IDs for standard yolov8n.pt
YOLO_TO_VEHICLE = {
    2:  "car",
    3:  "motorcycle",
    5:  "bus",
    7:  "truck",
    # Fine-tuned custom classes (if available):
    8:  "microbus",
    9:  "van",
    10: "tractor",
}

VEHICLE_COLORS = {
    "car":        (0,   255, 0),    # green
    "motorcycle": (0,   200, 255),  # yellow
    "bus":        (255, 128, 0),    # orange
    "microbus":   (255, 200, 0),    # gold
    "truck":      (0,   0,   255),  # blue
    "van":        (200, 100, 255),  # purple
    "tractor":    (128, 64,  0),    # brown
    "other":      (128, 128, 128),  # gray
}


# ═════════════════════════════════════════════════════════════════════════════
# Vehicle deduplication tracker
# ═════════════════════════════════════════════════════════════════════════════

class VehicleTracker:
    """
    Simple IoU-based tracker to avoid sending the same vehicle multiple times.
    A vehicle is considered 'new' if:
      - Its plate text is different from recent plates, OR
      - Its bounding box has < 50% overlap with recently seen boxes
    A tracked vehicle expires after `timeout_seconds`.
    """

    def __init__(self, timeout_seconds: float = 5.0):
        self.timeout   = timeout_seconds
        self._seen: dict[str, float] = {}   # plate_text → last_seen_time
        self._boxes:  list[tuple]    = []   # (x1,y1,x2,y2, expire_time)

    def is_new(self, plate_text: str, bbox: list, now: float) -> bool:
        # Clean expired entries
        self._seen = {p: t for p, t in self._seen.items() if now - t < self.timeout}
        self._boxes = [(b, t) for b, t in self._boxes if now < t]

        # Plate-text dedup (only if plate is non-empty and plausible)
        if plate_text and len(plate_text) >= 5:
            if plate_text in self._seen:
                return False

        # IoU dedup (catch same vehicle with slightly different plate read)
        for (bx, t) in self._boxes:
            if self._iou(bbox, bx) > 0.40:
                return False

        # New vehicle — register it
        if plate_text and len(plate_text) >= 5:
            self._seen[plate_text] = now
        self._boxes.append((bbox, now + self.timeout))
        return True

    @staticmethod
    def _iou(a: list, b: list) -> float:
        ax1, ay1, ax2, ay2 = a
        bx1, by1, bx2, by2 = b
        ix1 = max(ax1, bx1); iy1 = max(ay1, by1)
        ix2 = min(ax2, bx2); iy2 = min(ay2, by2)
        iw  = max(0, ix2 - ix1)
        ih  = max(0, iy2 - iy1)
        inter = iw * ih
        if inter == 0:
            return 0.0
        ua  = (ax2-ax1)*(ay2-ay1) + (bx2-bx1)*(by2-by1) - inter
        return inter / ua if ua > 0 else 0.0


# ═════════════════════════════════════════════════════════════════════════════
# Frame annotator (draws boxes + labels using OpenCV)
# ═════════════════════════════════════════════════════════════════════════════

def annotate_frame(frame: np.ndarray, detections: list[dict]) -> np.ndarray:
    """Draw bounding boxes and plate labels onto frame."""
    try:
        import cv2
    except ImportError:
        return frame

    out = frame.copy()
    for d in detections:
        x1, y1, x2, y2 = [int(v) for v in d["bbox"]]
        vtype  = d.get("vehicle_type", "other")
        plate  = d.get("plate_text", "")
        conf   = d.get("plate_confidence", 0.0)
        color  = VEHICLE_COLORS.get(vtype, (128, 128, 128))

        # Box
        cv2.rectangle(out, (x1, y1), (x2, y2), color, 2)

        # Label background
        label     = f"{vtype}  {plate}  ({conf:.2f})"
        (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 1)
        cv2.rectangle(out, (x1, y1 - th - 8), (x1 + tw + 4, y1), color, -1)
        cv2.putText(out, label, (x1 + 2, y1 - 4),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 0), 1, cv2.LINE_AA)

    # Stats overlay
    total = len(detections)
    ts    = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cv2.putText(out, f"Detections: {total}  {ts}", (10, 28),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 200), 2)
    return out


# ═════════════════════════════════════════════════════════════════════════════
# Core per-frame processing
# ═════════════════════════════════════════════════════════════════════════════

def process_frame(
    frame: np.ndarray,
    model,
    conf_threshold: float,
    tracker: VehicleTracker,
    checkpoint_id: str,
    camera_id: str,
    mock_ocr: bool = False,
) -> list[dict]:
    """
    Run full detection pipeline on one frame.
    Returns list of detection dicts ready to POST to /api/ingest.
    """
    try:
        from backend.services.classifier import classify
    except ImportError:
        classify = None

    now = time.time()
    results = model(frame, conf=conf_threshold, verbose=False)
    detections = []

    for result in results:
        for box in result.boxes:
            cls_id    = int(box.cls[0])
            yolo_conf = float(box.conf[0])
            if cls_id not in YOLO_TO_VEHICLE:
                continue  # skip non-vehicle classes (person, bicycle, etc.)

            vtype = YOLO_TO_VEHICLE[cls_id]
            bbox  = box.xyxy[0].tolist()
            x1, y1, x2, y2 = [int(v) for v in bbox]

            # ── Crop vehicle ROI ──────────────────────────────────────────────
            h_frame, w_frame = frame.shape[:2]
            x1c = max(0, x1); y1c = max(0, y1)
            x2c = min(w_frame, x2); y2c = min(h_frame, y2)
            vehicle_roi = frame[y1c:y2c, x1c:x2c]

            if vehicle_roi.size == 0:
                continue

            roi_h, roi_w = vehicle_roi.shape[:2]

            # ── Plate region: bottom 25% of vehicle ROI ───────────────────────
            plate_y1    = int(roi_h * 0.72)
            plate_roi   = vehicle_roi[plate_y1:roi_h, :]

            # ── Run plate OCR ─────────────────────────────────────────────────
            if mock_ocr:
                plate_text = _mock_plate_text()
                plate_conf = round(random.uniform(0.60, 0.94), 3)
            else:
                plate_text, plate_conf = read_plate(plate_roi)

            # ── Bus: also read route text from top 20% ────────────────────────
            origin_text = origin_city = destination_city = ""
            if vtype == "bus":
                route_roi = vehicle_roi[:int(roi_h * 0.22), :]
                origin_text, origin_city, destination_city = read_route_devanagari(route_roi)

            # ── Classify plate ────────────────────────────────────────────────
            plate_color = "white"
            ownership   = "private"
            district    = None

            if classify:
                try:
                    clf       = classify(plate_text, vtype, plate_color)
                    vtype     = clf.get("vehicle_type", vtype)
                    ownership = clf.get("ownership_category", "private")
                    district  = clf.get("district_code")
                except Exception:
                    pass

            # ── Dedup check ───────────────────────────────────────────────────
            if not tracker.is_new(plate_text, bbox, now):
                continue

            # ── Encode plate crop as base64 for storage ───────────────────────
            plate_b64 = None
            if plate_roi.size > 0:
                try:
                    import cv2 as cv
                    _, buf    = cv.imencode(".jpg", plate_roi, [cv.IMWRITE_JPEG_QUALITY, 85])
                    plate_b64 = base64.b64encode(buf.tobytes()).decode()
                except Exception:
                    pass

            direction = random.choice(["inbound", "outbound"])  # override with real logic if camera angle known

            detection = {
                "plate_text":         plate_text,
                "plate_confidence":   plate_conf,
                "vehicle_type":       vtype,
                "ownership_category": ownership,
                "district_code":      district,
                "origin_text":        origin_text or None,
                "origin_city":        origin_city or None,
                "destination_city":   destination_city or None,
                "direction":          direction,
                "checkpoint_id":      checkpoint_id,
                "camera_id":          camera_id,
                "yolo_confidence":    round(yolo_conf, 3),
                "timestamp":          datetime.utcnow().isoformat(),
                # Extra for local display only (not in API schema):
                "bbox":               bbox,
                "plate_image_b64":    plate_b64,
            }
            detections.append(detection)
            log.info(
                f"  ✓ {plate_text or '(no plate)':<22} "
                f"{vtype:<12} {ownership:<14} "
                f"conf={plate_conf:.2f}"
            )

    return detections


# ═════════════════════════════════════════════════════════════════════════════
# API poster
# ═════════════════════════════════════════════════════════════════════════════

async def post_detection(client: httpx.AsyncClient, detection: dict) -> bool:
    """POST a single detection to /api/ingest. Returns True on success."""
    # Strip fields not in the API schema before sending
    payload = {k: v for k, v in detection.items() if k not in ("bbox", "plate_image_b64")}
    try:
        resp = await client.post(INGEST_URL, json=payload, timeout=5.0)
        return resp.status_code == 201
    except httpx.ConnectError:
        log.warning(f"Cannot reach API at {INGEST_URL}")
        return False
    except Exception as e:
        log.debug(f"API post error: {e}")
        return False


# ═════════════════════════════════════════════════════════════════════════════
# Main video loop
# ═════════════════════════════════════════════════════════════════════════════

async def run(args):
    import cv2

    # ── Resolve source ────────────────────────────────────────────────────────
    source = args.source
    try:
        source = int(source)          # webcam device index
        source_label = f"Webcam #{source}"
    except ValueError:
        source_label = source         # file path or RTSP URL

    log.info("━" * 60)
    log.info("Nepal Traffic AI — Real Video Processor")
    log.info("━" * 60)
    log.info(f"  Source      : {source_label}")
    log.info(f"  Checkpoint  : {args.checkpoint}")
    log.info(f"  Camera ID   : {args.camera_id}")
    log.info(f"  Skip frames : every {args.skip_frames} frames")
    log.info(f"  Conf thresh : {args.confidence}")
    log.info(f"  Mock OCR    : {args.mock_ocr}")
    log.info(f"  Preview     : {args.preview}")
    log.info(f"  Save output : {args.save_output or 'no'}")
    log.info("━" * 60)

    # ── Load models ───────────────────────────────────────────────────────────
    model = load_yolo(args.model)

    if not args.mock_ocr:
        load_ocr()
    else:
        global _ocr_dev_mode
        _ocr_dev_mode = True
        log.info("Mock OCR enabled — using synthetic plate text")

    # ── Open video source ─────────────────────────────────────────────────────
    cap = cv2.VideoCapture(source)
    if not cap.isOpened():
        log.error(f"Cannot open video source: {source}")
        log.error("  • For video files: check the file path exists")
        log.error("  • For RTSP: check camera IP, port, and credentials")
        log.error("  • For webcam: try --source 0 or --source 1")
        sys.exit(1)

    fps    = cap.get(cv2.CAP_PROP_FPS) or 25.0
    width  = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    total  = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))  # -1 for live streams

    log.info(f"  Video       : {width}×{height} @ {fps:.1f} fps")
    if total > 0:
        duration = total / fps
        log.info(f"  Duration    : {duration:.1f}s  ({total} frames)")
    else:
        log.info(f"  Duration    : live stream")
    log.info("─" * 60)

    # ── Video writer (optional) ───────────────────────────────────────────────
    writer = None
    if args.save_output:
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        writer = cv2.VideoWriter(args.save_output, fourcc, fps, (width, height))
        log.info(f"Saving annotated video to: {args.save_output}")

    # ── Tracker + stats ───────────────────────────────────────────────────────
    tracker     = VehicleTracker(timeout_seconds=args.dedup_seconds)
    frame_count = 0
    sent_count  = 0
    fail_count  = 0
    t_start     = time.time()

    # ── API client ────────────────────────────────────────────────────────────
    async with httpx.AsyncClient() as http:
        while True:
            ret, frame = cap.read()
            if not ret:
                if total > 0:
                    log.info("End of video file reached.")
                else:
                    log.warning("Stream read failed — attempting reconnect in 3s…")
                    await asyncio.sleep(3)
                    cap.release()
                    cap = cv2.VideoCapture(source)
                    continue
                break

            frame_count += 1

            # Skip frames to control processing rate
            if frame_count % args.skip_frames != 0:
                if args.preview:
                    cv2.imshow("Nepal Traffic AI", frame)
                    if cv2.waitKey(1) & 0xFF == ord("q"):
                        break
                continue

            # ── Run detection ─────────────────────────────────────────────────
            detections = process_frame(
                frame,
                model,
                conf_threshold = args.confidence,
                tracker        = tracker,
                checkpoint_id  = args.checkpoint,
                camera_id      = args.camera_id,
                mock_ocr       = args.mock_ocr,
            )

            # ── Send to API ───────────────────────────────────────────────────
            for det in detections:
                ok = await post_detection(http, det)
                if ok:
                    sent_count += 1
                else:
                    fail_count += 1

            # ── Annotate + display/save ───────────────────────────────────────
            if args.preview or writer:
                annotated = annotate_frame(frame, detections)
                if writer:
                    writer.write(annotated)
                if args.preview:
                    cv2.imshow("Nepal Traffic AI — Press Q to quit", annotated)
                    key = cv2.waitKey(1) & 0xFF
                    if key == ord("q"):
                        log.info("User pressed Q — stopping.")
                        break

            # ── Progress every 50 processed frames ───────────────────────────
            processed = frame_count // args.skip_frames
            if processed % 50 == 0 and processed > 0:
                elapsed = time.time() - t_start
                fps_real = frame_count / elapsed if elapsed > 0 else 0
                log.info(
                    f"  Frame {frame_count:>6}  |  "
                    f"Sent {sent_count:>4}  |  "
                    f"Failed {fail_count:>3}  |  "
                    f"{fps_real:.1f} fps"
                )

            # ── Stop after max_vehicles if set ────────────────────────────────
            if args.max_vehicles and sent_count >= args.max_vehicles:
                log.info(f"Reached max_vehicles limit ({args.max_vehicles}). Stopping.")
                break

    # ── Cleanup ───────────────────────────────────────────────────────────────
    cap.release()
    if writer:
        writer.release()
    try:
        import cv2 as cv
        cv.destroyAllWindows()
    except Exception:
        pass

    elapsed = time.time() - t_start
    log.info("━" * 60)
    log.info("Done.")
    log.info(f"  Frames read   : {frame_count}")
    log.info(f"  Frames proc.  : {frame_count // args.skip_frames}")
    log.info(f"  Detections    : {sent_count}")
    log.info(f"  API failures  : {fail_count}")
    log.info(f"  Elapsed       : {elapsed:.1f}s")
    log.info("━" * 60)


# ═════════════════════════════════════════════════════════════════════════════
# CLI
# ═════════════════════════════════════════════════════════════════════════════

def main():
    p = argparse.ArgumentParser(
        description="Process video/camera feed and send detections to Nepal Traffic AI API",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    # Source
    p.add_argument(
        "--source", required=True,
        help=(
            "Video source. Examples:\n"
            "  /path/to/video.mp4          — video file\n"
            "  0                            — webcam (device 0)\n"
            "  rtsp://192.168.1.10:554/ch1  — RTSP camera"
        ),
    )

    # Checkpoint / camera
    p.add_argument("--checkpoint", default="cp-thankot",
                   help="Checkpoint ID to tag detections with (default: cp-thankot)")
    p.add_argument("--camera-id",  default="cam-video-01",
                   help="Camera ID label (default: cam-video-01)")

    # Detection tuning
    p.add_argument("--model",       default="yolov8n.pt",
                   help="YOLOv8 model path or name (default: yolov8n.pt)")
    p.add_argument("--confidence",  type=float, default=0.50,
                   help="YOLO confidence threshold 0.0-1.0 (default: 0.50)")
    p.add_argument("--skip-frames", type=int,   default=3,
                   help="Process every Nth frame (default: 3 → ~8fps from 25fps video)")

    # OCR
    p.add_argument("--mock-ocr", action="store_true",
                   help="Use synthetic plate text instead of PaddleOCR (faster, no GPU needed)")

    # Deduplication
    p.add_argument("--dedup-seconds", type=float, default=4.0,
                   help="Seconds before the same vehicle/plate is re-reported (default: 4.0)")

    # Output
    p.add_argument("--preview",      action="store_true",
                   help="Show live OpenCV preview window")
    p.add_argument("--save-output",  default=None, metavar="FILE",
                   help="Save annotated video to this file (e.g. output.mp4)")
    p.add_argument("--max-vehicles", type=int, default=0,
                   help="Stop after sending this many unique vehicles (0 = unlimited)")

    # API
    p.add_argument("--api",  default="http://localhost:8000/api",
                   help="API base URL (default: http://localhost:8000/api)")

    args = p.parse_args()

    global API_BASE, INGEST_URL
    API_BASE   = args.api
    INGEST_URL = f"{API_BASE}/ingest"

    asyncio.run(run(args))


if __name__ == "__main__":
    main()

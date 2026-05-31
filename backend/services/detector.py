"""
Vehicle detection service.
In REAL mode: runs YOLOv8 inference → plate OCR → classifier.
In MOCK mode: generates realistic synthetic detections.
"""
import logging
import random
import base64
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
import numpy as np

from backend.config import settings
from backend.services import classifier, ocr
from backend.services.classifier import DISTRICT_MAP, _LETTERS  # noqa: F401

logger = logging.getLogger(__name__)

_yolo_model = None


def _get_model():
    global _yolo_model
    if _yolo_model is None and not settings.MOCK_MODE:
        try:
            from ultralytics import YOLO
            model_path = "./models/vehicle_detector.pt"
            import os
            if not os.path.exists(model_path):
                model_path = "yolov8n.pt"
            _yolo_model = YOLO(model_path)
            logger.info(f"YOLOv8 model loaded from {model_path}")
        except Exception as e:
            logger.warning(f"YOLO init failed: {e}")
    return _yolo_model


@dataclass
class VehicleDetection:
    frame_id: str
    timestamp: datetime
    bounding_box: list
    vehicle_type: str
    ownership_category: str
    plate_text: str
    plate_confidence: float
    origin_text: str
    origin_city: str
    destination_city: str
    district_code: Optional[str]
    yolo_confidence: float
    plate_image_b64: Optional[str] = None
    camera_id: str = "cam-01"


# ── YOLO class labels ─────────────────────────────────────────────────────────

_YOLO_CLASS_MAP = {
    2: "car",
    3: "motorcycle",
    5: "bus",
    7: "truck",
    # Custom classes (if fine-tuned):
    8: "microbus",
    9: "van",
    10: "tractor",
}


def detect_frame(frame: np.ndarray, camera_id: str = "cam-01") -> list[VehicleDetection]:
    """
    Process a single video frame and return all detected vehicles.
    Falls back to MOCK_MODE if model unavailable.
    """
    if settings.MOCK_MODE:
        return [_mock_detection(camera_id)]

    model = _get_model()
    if model is None:
        return [_mock_detection(camera_id)]

    detections = []
    try:
        results = model(frame, conf=settings.CONFIDENCE_THRESHOLD, verbose=False)
        for result in results:
            for box in result.boxes:
                cls_id = int(box.cls[0])
                yolo_class = _YOLO_CLASS_MAP.get(cls_id, "car")
                yolo_conf  = float(box.conf[0])
                bbox       = box.xyxy[0].tolist()

                # Crop vehicle ROI
                x1, y1, x2, y2 = [int(v) for v in bbox]
                vehicle_roi = frame[max(0, y1):y2, max(0, x1):x2]

                if vehicle_roi.size == 0:
                    continue

                # Estimate plate region = bottom 25% of vehicle ROI
                h = vehicle_roi.shape[0]
                plate_roi = vehicle_roi[int(h * 0.75):h, :]

                # OCR on plate
                plate_result = ocr.parse_plate(plate_roi)
                plate_text   = plate_result["text"]
                plate_conf   = plate_result["confidence"]

                # If bus, OCR on top 20% for route
                origin_text = origin_city = destination_city = ""
                if yolo_class == "bus":
                    route_roi = vehicle_roi[:int(h * 0.20), :]
                    route_result   = ocr.parse_route_text(route_roi)
                    origin_text    = route_result.get("raw_text", "")
                    origin_city    = route_result.get("origin", "")
                    destination_city = route_result.get("destination", "")

                # Classify
                plate_color = "white"
                clf = classifier.classify(plate_text, yolo_class, plate_color)

                # Encode plate image as base64
                plate_b64 = None
                if plate_roi.size > 0:
                    try:
                        import cv2
                        _, buf = cv2.imencode(".jpg", plate_roi)
                        plate_b64 = base64.b64encode(buf.tobytes()).decode()
                    except Exception:
                        pass

                detections.append(VehicleDetection(
                    frame_id=str(uuid.uuid4()),
                    timestamp=datetime.utcnow(),
                    bounding_box=bbox,
                    vehicle_type=clf["vehicle_type"],
                    ownership_category=clf["ownership_category"],
                    plate_text=plate_text,
                    plate_confidence=plate_conf,
                    origin_text=origin_text,
                    origin_city=origin_city,
                    destination_city=destination_city,
                    district_code=clf["district_code"],
                    yolo_confidence=yolo_conf,
                    plate_image_b64=plate_b64,
                    camera_id=camera_id,
                ))
    except Exception as e:
        logger.error(f"Detection error: {e}")

    return detections


# ── Mock detection generator ──────────────────────────────────────────────────

_VEHICLE_TYPES  = ["car", "motorcycle", "bus", "microbus", "truck", "van", "tractor", "other"]
_WEIGHTS_TYPE   = [0.40, 0.28, 0.10, 0.12, 0.07, 0.02, 0.005, 0.005]

_OWNERSHIPS     = ["private", "public", "government", "police", "army",
                   "armed_police", "diplomatic", "un", "ngo"]
_WEIGHTS_OWN    = [0.72, 0.18, 0.05, 0.02, 0.01, 0.005, 0.005, 0.003, 0.002]

_DISTRICT_CODES = list(DISTRICT_MAP.keys())
# _LETTERS imported from classifier

_MOCK_ROUTES = [
    ("काठमाडौं–बुटवल", "Kathmandu", "Butwal"),
    ("काठमाडौं–पोखरा", "Kathmandu", "Pokhara"),
    ("काठमाडौं–विराटनगर", "Kathmandu", "Biratnagar"),
    ("भरतपुर–काठमाडौं", "Bharatpur", "Kathmandu"),
    ("नारायणघाट–काठमाडौं", "Narayanghat", "Kathmandu"),
    ("काठमाडौं–भैरहवा", "Kathmandu", "Bhairahawa"),
    ("धरान–काठमाडौं", "Dharan", "Kathmandu"),
    ("जनकपुर–काठमाडौं", "Janakpur", "Kathmandu"),
    ("", "", ""),
]


def _mock_detection(camera_id: str = "cam-01") -> VehicleDetection:
    vtype     = random.choices(_VEHICLE_TYPES, weights=_WEIGHTS_TYPE)[0]
    ownership = random.choices(_OWNERSHIPS,    weights=_WEIGHTS_OWN)[0]
    dc        = random.choice(_DISTRICT_CODES)
    series    = random.randint(1, 9)
    letter    = random.choice(_LETTERS)
    number    = random.randint(1, 9999)
    plate     = f"{dc} {series} {letter} {str(number).zfill(4)}"

    # Special ownership overrides
    if ownership == "police":
        plate = f"Na Pra {series} {letter} {str(number).zfill(4)}"
    elif ownership == "army":
        plate = f"Na Se {series} {letter} {str(number).zfill(4)}"
    elif ownership == "armed_police":
        plate = f"Sa Pra {series} {letter} {str(number).zfill(4)}"
    elif ownership == "government":
        plate = f"Na Ra Sa {series} {letter} {str(number).zfill(4)}"
    elif ownership == "diplomatic":
        plate = f"CD {random.randint(10, 99)} {random.randint(1000, 9999)}"
    elif ownership == "un":
        plate = f"UN {random.randint(10, 99)} {random.randint(1000, 9999)}"

    origin_text = origin_city = destination_city = ""
    if vtype in ("bus", "microbus"):
        route = random.choice(_MOCK_ROUTES)
        origin_text, origin_city, destination_city = route

    plate_conf = round(random.uniform(0.55, 0.98), 3)
    yolo_conf  = round(random.uniform(0.70, 0.99), 3)

    return VehicleDetection(
        frame_id=str(uuid.uuid4()),
        timestamp=datetime.utcnow(),
        bounding_box=[
            random.randint(50, 200),
            random.randint(100, 300),
            random.randint(300, 600),
            random.randint(400, 700),
        ],
        vehicle_type=vtype,
        ownership_category=ownership,
        plate_text=plate,
        plate_confidence=plate_conf,
        origin_text=origin_text,
        origin_city=origin_city,
        destination_city=destination_city,
        district_code=dc,
        yolo_confidence=yolo_conf,
        plate_image_b64=None,
        camera_id=camera_id,
    )

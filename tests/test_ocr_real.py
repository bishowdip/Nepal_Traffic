"""
tests/test_ocr_real.py
Real OCR tests — verify that the EasyOCR backend actually reads a license
plate from an image (not just mock output).

These tests are skipped automatically if EasyOCR is not installed, so the
core suite still runs on minimal environments.
"""
import importlib
import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

easyocr = pytest.importorskip("easyocr", reason="EasyOCR not installed")
cv2 = pytest.importorskip("cv2", reason="opencv not installed")

from backend.services import ocr as ocr_service


def _make_plate_image(text: str) -> np.ndarray:
    """Render black plate text on a white background (BGR)."""
    img = np.full((120, 460, 3), 255, np.uint8)
    cv2.putText(img, text, (15, 82), cv2.FONT_HERSHEY_SIMPLEX, 1.5, (0, 0, 0), 3, cv2.LINE_AA)
    return img


@pytest.fixture(scope="module", autouse=True)
def _force_easyocr():
    """Force the real EasyOCR engine for this module regardless of MOCK_MODE."""
    prev = os.environ.get("OCR_ENGINE")
    os.environ["OCR_ENGINE"] = "easyocr"
    yield
    if prev is None:
        os.environ.pop("OCR_ENGINE", None)
    else:
        os.environ["OCR_ENGINE"] = prev


def test_engine_resolves_to_easyocr():
    assert ocr_service._resolve_engine() == "easyocr"


def test_preprocess_upscales_small_crop():
    small = np.full((30, 60, 3), 255, np.uint8)
    out = ocr_service._preprocess_plate(small)
    # Small crops get upscaled toward ~400px on the long edge.
    assert max(out.shape[:2]) > 60


def test_reads_spaced_plate():
    out = ocr_service.parse_plate(_make_plate_image("Ba 2 Kha 4521"))
    assert out["confidence"] > 0.4
    text = out["text"].replace(" ", "").upper()
    # The numeric block is the most reliable signal.
    assert "4521" in text
    assert "BA" in text


def test_reads_digits_block():
    out = ocr_service.parse_plate(_make_plate_image("Lu 5 Pa 7788"))
    assert "7788" in out["text"].replace(" ", "")


def test_blank_image_returns_empty_not_mock():
    blank = np.full((120, 460, 3), 255, np.uint8)
    out = ocr_service.parse_plate(blank)
    # No glyphs → empty text (real engine), never a fabricated mock plate.
    assert out["text"] == ""
    assert out["confidence"] == 0.0

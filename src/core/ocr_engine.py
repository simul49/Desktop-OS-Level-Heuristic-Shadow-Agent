"""
Heuristic Shadow Agent - OCR Engine
Performs lightweight OCR on screen regions using EasyOCR.
Captures text around click points or full-screen text on app switches.
"""

import logging
import time
from typing import Optional

import numpy as np
from PIL import ImageGrab, Image

from config import Config

logger = logging.getLogger(__name__)


class OCREngine:
    """
    Lightweight OCR wrapper using EasyOCR.
    Supports region-based and full-screen text extraction.
    """

    def __init__(self):
        self._reader = None
        self._ready = False
        self._init_error: Optional[str] = None
        self.languages = Config.OCR_LANGUAGES
        self._init_reader()

    def _init_reader(self) -> None:
        """Lazy-initialize EasyOCR reader (downloads models on first use)."""
        try:
            import easyocr
            logger.info(f"Initializing EasyOCR with languages: {self.languages}")
            self._reader = easyocr.Reader(
                self.languages,
                gpu=False,  # CPU-only for minimal resource usage
                verbose=False,
            )
            self._ready = True
            logger.info("EasyOCR initialized successfully.")
        except ImportError:
            self._init_error = "EasyOCR not installed. Install: pip install easyocr"
            logger.warning(self._init_error)
        except Exception as e:
            self._init_error = f"EasyOCR init failed: {e}"
            logger.warning(self._init_error)

    @property
    def ready(self) -> bool:
        return self._ready

    def capture_region_text(
        self,
        x: int,
        y: int,
        radius: int = 150,
    ) -> str:
        """
        Capture and OCR text from a screen region around (x, y).
        Returns empty string if OCR is unavailable or fails.
        """
        if not self._ready or self._reader is None:
            return ""

        try:
            # Calculate bounding box
            x1 = max(0, x - radius)
            y1 = max(0, y - radius)
            x2 = x + radius
            y2 = y + radius

            # Capture region
            start_time = time.time()
            screenshot = ImageGrab.grab(bbox=(x1, y1, x2, y2))

            # Convert to numpy array for EasyOCR
            img_array = np.array(screenshot)

            # Run OCR
            results = self._reader.readtext(img_array, detail=0, paragraph=True)

            elapsed_ms = (time.time() - start_time) * 1000
            text = " ".join(results).strip()

            if text:
                logger.debug(f"OCR [{elapsed_ms:.0f}ms] region ({x1},{y1})-({x2},{y2}): {text[:100]}")

            return text[:2000]  # Cap length

        except Exception as e:
            logger.debug(f"OCR region capture error: {e}")
            return ""

    def capture_full_screen_text(self) -> str:
        """
        Capture and OCR the full screen.
        Used on application switches for context awareness.
        """
        if not self._ready or self._reader is None:
            return ""

        try:
            start_time = time.time()
            screenshot = ImageGrab.grab()

            # Downscale large screens for faster processing
            w, h = screenshot.size
            if w > 1920:
                ratio = 1920 / w
                new_size = (1920, int(h * ratio))
                screenshot = screenshot.resize(new_size, Image.LANCZOS)

            img_array = np.array(screenshot)
            results = self._reader.readtext(img_array, detail=0, paragraph=True)

            elapsed_ms = (time.time() - start_time) * 1000
            text = " ".join(results).strip()

            if text:
                logger.debug(f"OCR full-screen [{elapsed_ms:.0f}ms]: {text[:150]}")

            return text[:3000]

        except Exception as e:
            logger.debug(f"OCR full-screen error: {e}")
            return ""

    def extract_text_from_image(self, image: Image.Image) -> str:
        """OCR an arbitrary PIL Image."""
        if not self._ready or self._reader is None:
            return ""
        try:
            results = self._reader.readtext(
                np.array(image), detail=0, paragraph=True
            )
            return " ".join(results).strip()
        except Exception as e:
            logger.debug(f"OCR image error: {e}")
            return ""

    def get_status(self) -> dict:
        """Return OCR engine status."""
        return {
            "ready": self._ready,
            "languages": self.languages,
            "error": self._init_error,
        }

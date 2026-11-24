"""Lecture du QR code d'une carte (image fichier ou image de webcam) avec OpenCV.

Les détecteurs d'OpenCV peuvent rater un QR dense sur une image chargée
(logo, photo, texte). On essaie donc plusieurs détecteurs sur plusieurs
versions de l'image et on garde le premier résultat qui ressemble à un jeton.
"""

import cv2
import numpy as np
from PIL import Image


def _variants(bgr: np.ndarray):
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY) if bgr.ndim == 3 else bgr
    yield bgr
    yield gray
    yield cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]
    yield cv2.resize(gray, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)


def _detectors():
    if hasattr(cv2, "QRCodeDetectorAruco"):
        yield cv2.QRCodeDetectorAruco()
    yield cv2.QRCodeDetector()


def decode_qr(image: np.ndarray | Image.Image, prefix: str = "SID1.") -> str | None:
    """Retourne le texte du QR (commençant par prefix) ou None. image : BGR OpenCV ou image Pillow."""
    if isinstance(image, Image.Image):
        image = cv2.cvtColor(np.array(image.convert("RGB")), cv2.COLOR_RGB2BGR)
    for variant in _variants(image):
        for detector in _detectors():
            try:
                text = detector.detectAndDecode(variant)[0]
            except cv2.error:
                continue
            if text and text.startswith(prefix):
                return text
    return None

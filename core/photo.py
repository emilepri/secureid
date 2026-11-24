"""Photo d'identité : recadrage 3:4, normalisation et empreinte `ph`."""

import hashlib
from pathlib import Path

from PIL import Image, ImageOps

PHOTO_SIZE = (600, 800)  # largeur x hauteur, ratio 3:4


def normalize(source: str | Path | Image.Image) -> Image.Image:
    """Ouvre la photo, corrige l'orientation EXIF, recadre au centre en 3:4 et redimensionne."""
    img = source if isinstance(source, Image.Image) else Image.open(source)
    img = ImageOps.exif_transpose(img).convert("RGB")
    return ImageOps.fit(img, PHOTO_SIZE, method=Image.Resampling.LANCZOS, centering=(0.5, 0.4))


def fingerprint(photo: Image.Image) -> str:
    """Empreinte de la photo normalisée : 8 premiers octets du SHA-256 des pixels, en hexadécimal.

    On hache les pixels (et non le fichier) pour que la même photo donne
    toujours la même empreinte, quel que soit le format d'enregistrement.
    """
    if photo.size != PHOTO_SIZE or photo.mode != "RGB":
        raise ValueError("La photo doit d'abord passer par normalize().")
    return hashlib.sha256(photo.tobytes()).hexdigest()[:16]


def save(photo: Image.Image, path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    photo.save(path, format="PNG")
    return path

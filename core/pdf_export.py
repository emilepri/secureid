"""Export PDF de la carte : une page recto, une page verso, au format CR80 réel."""

from pathlib import Path

from PIL import Image
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

CARD_SIZE = (54 * mm, 85.6 * mm)  # portrait
CARD_SIZE_LANDSCAPE = (85.6 * mm, 54 * mm)


def export_card_pdf(recto: Image.Image, verso: Image.Image, path: str | Path, title: str = "Carte SecureID") -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    size = CARD_SIZE_LANDSCAPE if recto.width > recto.height else CARD_SIZE
    c = canvas.Canvas(str(path), pagesize=size)
    c.setTitle(title)
    c.setAuthor("SecureID")
    for face in (recto, verso):
        c.drawImage(ImageReader(face), 0, 0, width=size[0], height=size[1])
        c.showPage()
    c.save()
    return path

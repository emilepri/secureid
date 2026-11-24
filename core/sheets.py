"""Planches A4 prêtes à imprimer, avec traits de coupe.

- Cartes paysage (85,6 x 54 mm) : 2 colonnes x 5 rangées = 10 cartes par feuille.
- Cartes portrait (54 x 85,6 mm) : 3 colonnes x 3 rangées = 9 cartes par feuille.
- Chaque page de rectos est suivie de la page des versos, en miroir horizontal :
  en impression recto-verso (retournement sur le bord long), chaque verso tombe
  exactement derrière son recto.
- Les traits de coupe sont dans les marges, dans le prolongement des bords des cartes.
"""

from dataclasses import dataclass
from pathlib import Path

from PIL import Image
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

GAP = 3 * mm            # espace entre deux cartes (pour la coupe)
MARK_LEN = 4 * mm       # longueur des traits de coupe
MARK_OFFSET = 1.5 * mm  # écart entre la carte et le début du trait


@dataclass(frozen=True)
class Layout:
    card_w: float
    card_h: float
    cols: int
    rows: int

    @property
    def per_page(self) -> int:
        return self.cols * self.rows

    @property
    def margin_x(self) -> float:
        return (A4[0] - self.cols * self.card_w - (self.cols - 1) * GAP) / 2

    @property
    def margin_y(self) -> float:
        return (A4[1] - self.rows * self.card_h - (self.rows - 1) * GAP) / 2

    def position(self, index: int, mirrored: bool = False) -> tuple[float, float]:
        """Coin inférieur gauche (points PDF) de la carte n° index sur la page."""
        row, col = divmod(index, self.cols)
        if mirrored:
            col = self.cols - 1 - col
        x = self.margin_x + col * (self.card_w + GAP)
        y = A4[1] - self.margin_y - (row + 1) * self.card_h - row * GAP
        return x, y


LANDSCAPE = Layout(85.6 * mm, 54 * mm, cols=2, rows=5)
PORTRAIT = Layout(54 * mm, 85.6 * mm, cols=3, rows=3)


def layout_for(face: Image.Image) -> Layout:
    return LANDSCAPE if face.width > face.height else PORTRAIT


def _crop_marks(c: canvas.Canvas, lay: Layout) -> None:
    c.setLineWidth(0.25)
    c.setStrokeColorRGB(0, 0, 0)
    xs = sorted({lay.margin_x + col * (lay.card_w + GAP) + dx for col in range(lay.cols) for dx in (0, lay.card_w)})
    ys = sorted({A4[1] - lay.margin_y - r * (lay.card_h + GAP) - dy for r in range(lay.rows) for dy in (0, lay.card_h)})
    top, bottom = A4[1] - lay.margin_y, lay.margin_y
    left, right = lay.margin_x, A4[0] - lay.margin_x
    for x in xs:  # traits verticaux en haut et en bas
        c.line(x, top + MARK_OFFSET, x, top + MARK_OFFSET + MARK_LEN)
        c.line(x, bottom - MARK_OFFSET, x, bottom - MARK_OFFSET - MARK_LEN)
    for y in ys:  # traits horizontaux à gauche et à droite
        c.line(left - MARK_OFFSET, y, left - MARK_OFFSET - MARK_LEN, y)
        c.line(right + MARK_OFFSET, y, right + MARK_OFFSET + MARK_LEN, y)


def _footer(c: canvas.Canvas, lay: Layout, text: str) -> None:
    # Centré sous la première colonne : ne chevauche aucun trait de coupe
    c.setFont("Helvetica", 6)
    c.setFillColorRGB(0.4, 0.4, 0.4)
    c.drawCentredString(lay.margin_x + lay.card_w / 2, 2.5 * mm, text)


def export_sheets(faces: list[tuple[Image.Image, Image.Image]], path: str | Path,
                  title: str = "Planches SecureID") -> tuple[Path, int]:
    """faces = [(recto, verso), ...] du même format. Retourne (chemin du PDF, nombre de feuilles)."""
    if not faces:
        raise ValueError("Aucune carte à imprimer.")
    lay = layout_for(faces[0][0])
    if any(layout_for(r) != lay for r, _ in faces):
        raise ValueError("Toutes les cartes d'une planche doivent avoir la même orientation (même modèle).")
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    c = canvas.Canvas(str(path), pagesize=A4)
    c.setTitle(title)
    c.setAuthor("SecureID")
    sheets = [faces[i:i + lay.per_page] for i in range(0, len(faces), lay.per_page)]
    for n, sheet in enumerate(sheets, start=1):
        for side, mirrored in (("RECTO", False), ("VERSO", True)):
            for i, (recto, verso) in enumerate(sheet):
                x, y = lay.position(i, mirrored)
                img = recto if side == "RECTO" else verso
                c.drawImage(ImageReader(img), x, y, width=lay.card_w, height=lay.card_h)
            _crop_marks(c, lay)
            _footer(c, lay, f"Feuille {n}/{len(sheets)} · {side} · imprimer à 100 %, recto-verso bord long")
            c.showPage()
    c.save()
    return path, len(sheets)

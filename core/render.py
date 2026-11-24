"""Rendu de la carte au format CR80 portrait (54 x 85,6 mm) à 300 dpi, avec Pillow."""

from dataclasses import dataclass
from datetime import date

import segno
from PIL import Image, ImageDraw, ImageFont

DPI = 300
CARD_W, CARD_H = 638, 1011  # 54 x 85,6 mm à 300 dpi


BLUE = (30, 79, 168)
BLUE_LIGHT = (59, 130, 246)
NAVY = (16, 42, 92)
GREY = (100, 116, 139)
WHITE = (255, 255, 255)
LINE = (191, 211, 245)

_FONT_CANDIDATES = {
    True: ["arialbd.ttf", "C:/Windows/Fonts/arialbd.ttf", "DejaVuSans-Bold.ttf",
           "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"],
    False: ["arial.ttf", "C:/Windows/Fonts/arial.ttf", "DejaVuSans.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"],
}
_MONO_CANDIDATES = ["consolab.ttf", "C:/Windows/Fonts/consolab.ttf", "DejaVuSansMono-Bold.ttf",
                    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf"]


@dataclass(frozen=True)
class Profile:
    """Organisation émettrice : textes et libellés qui changent entre école et entreprise."""

    kind: str          # "ecole" ou "entreprise"
    org: str           # nom complet
    sigle: str
    title_fr: str      # type de carte
    title_en: str
    owner: str         # « la propriété de ... »
    place: str         # « remettre à ... »
    contact: str       # qui prévenir en cas de perte
    end: str           # quand rendre la carte


SCHOOL = Profile("ecole", "Institut Gestion Numérique de Dakar", "IGND",
                 "Carte d'étudiant", "Student ID card",
                 "de l'Institut Gestion Numérique de Dakar", "l'établissement", "l'administration",
                 "à la fin de la scolarité")
COMPANY = Profile("entreprise", "Dakar Data Systems", "DDS",
                  "Carte professionnelle", "Employee ID card",
                  "de Dakar Data Systems", "l'entreprise", "le service sécurité",
                  "au départ de l'entreprise")
PROFILES = {"ecole": SCHOOL, "entreprise": COMPANY}

# Compatibilité avec le code existant
ETABLISSEMENT = SCHOOL.org
SIGLE = SCHOOL.sigle


@dataclass
class CardData:
    prenom: str
    nom: str
    card_id: str
    role: str
    naiss: str  # AAAA-MM-JJ
    exp: str    # AAAA-MM-JJ
    token: str  # jeton SID1 signé
    photo: Image.Image  # photo déjà normalisée (core.photo.normalize)
    emis: str = ""  # AAAA-MM-JJ, optionnel
    fonction: str = ""  # entreprise : poste occupé
    service: str = ""   # entreprise : département
    profile: Profile = SCHOOL


def short_fields(data: CardData) -> list[tuple[str, str, str]]:
    """Trois champs principaux (libellé FR, libellé EN, valeur) selon le profil."""
    if data.profile.kind == "entreprise":
        first = [("Fonction", "Position", data.fonction), ("Service", "Department", data.service)]
    else:
        first = [("Statut", "Status", data.role), ("Né(e) le", "Date of birth", _fr_date(data.naiss))]
    return first + [("Valide jusqu'au", "Valid until", _fr_date(data.exp))]


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    for name in _FONT_CANDIDATES[bold]:
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default(size)


def mono_font(size: int) -> ImageFont.FreeTypeFont:
    for name in _MONO_CANDIDATES:
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return font(size, bold=True)


def _fr_date(iso: str) -> str:
    return date.fromisoformat(iso).strftime("%d/%m/%Y")


def _fit_font(draw: ImageDraw.ImageDraw, text: str, max_width: int, size: int, bold: bool) -> ImageFont.FreeTypeFont:
    """Réduit la taille de police jusqu'à ce que le texte tienne dans max_width."""
    while size > 14:
        f = font(size, bold)
        if draw.textlength(text, font=f) <= max_width:
            return f
        size -= 2
    return font(size, bold)


def _wrap(draw: ImageDraw.ImageDraw, text: str, f: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    lines, current = [], ""
    for word in text.split():
        test = f"{current} {word}".strip()
        if draw.textlength(test, font=f) <= max_width:
            current = test
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def qr_image(token: str, size: int) -> Image.Image:
    """QR code net (modules entiers, zone de silence de 4 modules) d'au plus size pixels."""
    qr = segno.make(token, error="m", micro=False)
    matrix = list(qr.matrix)
    n = len(matrix)
    border = 4  # zone de silence recommandée par la norme
    scale = max(1, size // (n + 2 * border))
    side = (n + 2 * border) * scale
    img = Image.new("RGB", (side, side), WHITE)
    px = ImageDraw.Draw(img)
    for y, row in enumerate(matrix):
        for x, dark in enumerate(row):
            if dark:
                x0, y0 = (x + border) * scale, (y + border) * scale
                px.rectangle([x0, y0, x0 + scale - 1, y0 + scale - 1], fill=(0, 0, 0))
    return img


def _logo(draw: ImageDraw.ImageDraw, cx: int, cy: int, r: int, sigle: str = SIGLE) -> None:
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=WHITE)
    draw.ellipse([cx - r + 6, cy - r + 6, cx + r - 6, cy + r - 6], outline=BLUE, width=3)
    f = font(int(r * 0.48), bold=True)
    draw.text((cx, cy), sigle, font=f, fill=BLUE, anchor="mm")


def render_recto(data: CardData) -> Image.Image:
    card = Image.new("RGB", (CARD_W, CARD_H), WHITE)
    d = ImageDraw.Draw(card)

    # Bandeau supérieur bleu à bord inférieur arrondi
    d.ellipse([-260, 150, CARD_W + 260, 330], fill=BLUE_LIGHT)
    d.rectangle([0, 0, CARD_W, 220], fill=BLUE)
    d.ellipse([-260, 120, CARD_W + 260, 310], fill=BLUE)

    _logo(d, 92, 105, 58, data.profile.sigle)
    f_school = font(32, bold=True)
    for i, line in enumerate(_wrap(d, data.profile.org, f_school, CARD_W - 175 - 24)):
        d.text((175, 62 + i * 40), line, font=f_school, fill=WHITE)

    # Photo avec cadre blanc
    pw, ph = 240, 320
    px, py = (CARD_W - pw) // 2, 178
    d.rounded_rectangle([px - 8, py - 8, px + pw + 8, py + ph + 8], radius=18, fill=WHITE, outline=LINE, width=2)
    card.paste(data.photo.resize((pw, ph), Image.Resampling.LANCZOS), (px, py))

    # Nom et numéro
    full_name = f"{data.prenom} {data.nom.upper()}"
    d.text((CARD_W // 2, 548), full_name, font=_fit_font(d, full_name, CARD_W - 60, 44, True), fill=NAVY, anchor="mm")
    d.text((CARD_W // 2, 598), data.card_id, font=font(34, bold=True), fill=BLUE, anchor="mm")
    d.line([40, 634, CARD_W - 40, 634], fill=BLUE, width=3)

    # Informations à gauche, QR à droite
    rows = [(label, value) for label, _, value in short_fields(data)]
    f_label, f_value = font(20), font(28, bold=True)
    for i, (label, value) in enumerate(rows):
        y = 662 + i * 92
        d.ellipse([40, y + 6, 56, y + 22], fill=BLUE)
        d.text((68, y), label, font=f_label, fill=GREY)
        d.text((68, y + 26), value, font=_fit_font(d, value, 250, 28, True) if d.textlength(value, font=f_value) > 250 else f_value, fill=NAVY)

    qr = qr_image(data.token, 310)  # modules de 4 px, soit 0,34 mm à l'impression
    card.paste(qr, (CARD_W - 20 - qr.width, 646))

    # Bandeau inférieur
    d.rectangle([0, CARD_H - 44, CARD_W, CARD_H], fill=BLUE)
    d.text((CARD_W // 2, CARD_H - 22), "Carte sécurisée · vérifiable par QR code", font=font(20, bold=True), fill=WHITE, anchor="mm")
    return card


def render_verso(data: CardData) -> Image.Image:
    card = Image.new("RGB", (CARD_W, CARD_H), WHITE)
    d = ImageDraw.Draw(card)

    d.rectangle([0, 0, CARD_W, 150], fill=BLUE)
    p = data.profile
    _logo(d, 80, 75, 46, p.sigle)
    f_school = font(28, bold=True)
    for i, line in enumerate(_wrap(d, p.org, f_school, CARD_W - 150 - 24)):
        d.text((150, 42 + i * 36), line, font=f_school, fill=WHITE)

    paragraphs = [
        f"Cette carte est personnelle. Elle reste la propriété {p.owner}.",
        f"En cas de perte ou de vol, prévenez immédiatement {p.contact} : la carte sera révoquée.",
        "Le QR code au recto contient les données du titulaire signées numériquement. Toute modification est détectée à la vérification.",
        f"Si vous trouvez cette carte, merci de la remettre à {p.place}.",
    ]
    f_text = font(24)
    y = 190
    for p in paragraphs:
        for line in _wrap(d, p, f_text, CARD_W - 80):
            d.text((40, y), line, font=f_text, fill=NAVY)
            y += 32
        y += 18

    # Zone de signature
    y = max(y + 10, 760)
    d.text((40, y), "Signature du titulaire", font=font(20), fill=GREY)
    d.rounded_rectangle([40, y + 30, CARD_W - 40, y + 130], radius=12, outline=LINE, width=2)

    d.rectangle([0, CARD_H - 44, CARD_W, CARD_H], fill=BLUE)
    d.text((CARD_W // 2, CARD_H - 22), f"N° {data.card_id}", font=font(20, bold=True), fill=WHITE, anchor="mm")
    return card

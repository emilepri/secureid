"""Modèles de cartes supplémentaires.

Chaque modèle est une fonction recto(data) -> Image. Les éléments de sécurité
visuels (guilloches, micro-texte, image fantôme, pastille irisée) compliquent
la contrefaçon par photocopie, en complément du QR signé.
"""

import colorsys
import math

from PIL import Image, ImageDraw, ImageEnhance, ImageOps

from core.render import (
    BLUE, BLUE_LIGHT, CARD_H, CARD_W, GREY, NAVY, WHITE,
    CardData, _fit_font, _fr_date, _wrap, font, mono_font, qr_image, render_recto, short_fields,
)

LAND_W, LAND_H = CARD_H, CARD_W  # paysage : 85,6 x 54 mm à 300 dpi
VIOLET = (109, 40, 217)
SKY = (14, 165, 233)
PALE = (219, 234, 254)
SS = 2  # sur-échantillonnage des formes pour des bords lisses


# ---------------------------------------------------------------- outils
def _gradient(size, c1, c2, horizontal=True) -> Image.Image:
    mask = Image.linear_gradient("L")
    if horizontal:
        mask = mask.rotate(90)  # 0 à droite -> 255 à gauche
        mask = ImageOps.mirror(mask)
    mask = mask.resize(size)
    return Image.composite(Image.new("RGB", size, c2), Image.new("RGB", size, c1), mask)


def _guilloche(size, color, lines=26, amp=18, period=210, step=3, width=1) -> Image.Image:
    """Réseau de courbes sinusoïdales entrelacées, dessiné en 2x puis réduit."""
    w, h = size[0] * SS, size[1] * SS
    layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    gap = h / lines
    for k in range(lines + 2):
        base = k * gap
        for phase in (0, math.pi):
            pts = [(x, base + amp * SS * math.sin(2 * math.pi * x / (period * SS) + phase + k * 0.45))
                   for x in range(0, w + step, step * SS)]
            d.line(pts, fill=color, width=width * SS)
    return layer.resize(size, Image.Resampling.LANCZOS)


def _microtext(d: ImageDraw.ImageDraw, x0, y, x1, color, sigle, size=11):
    f = font(size, bold=True)
    motif = f"{sigle} · SECUREID · "
    text = motif * (int((x1 - x0) / max(1, d.textlength(motif, font=f))) + 1)
    while d.textlength(text, font=f) > x1 - x0:
        text = text[:-1]
    d.text((x0, y), text, font=f, fill=color)


def _iridescent_seal(card: Image.Image, cx, cy, r, sigle):
    """Pastille irisée (évoque un hologramme) avec le sigle au centre."""
    size = 2 * r * SS
    layer = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    c = size / 2
    for a in range(0, 360, 2):
        rgb = tuple(int(v * 255) for v in colorsys.hsv_to_rgb(a / 360, 0.35, 1.0))
        t = math.radians(a)
        d.line([(c + 0.55 * c * math.cos(t), c + 0.55 * c * math.sin(t)),
                (c + 0.98 * c * math.cos(t), c + 0.98 * c * math.sin(t))], fill=rgb + (230,), width=7 * SS)
    d.ellipse([c * 0.5, c * 0.5, c * 1.5, c * 1.5], fill=(255, 255, 255, 235))
    layer = layer.resize((2 * r, 2 * r), Image.Resampling.LANCZOS)
    card.paste(layer, (cx - r, cy - r), layer)
    ImageDraw.Draw(card).text((cx, cy), sigle, font=font(int(r * 0.34), bold=True), fill=NAVY, anchor="mm")


def _rounded_photo(photo: Image.Image, size, radius) -> tuple[Image.Image, Image.Image]:
    img = photo.resize(size, Image.Resampling.LANCZOS)
    mask = Image.new("L", (size[0] * SS, size[1] * SS), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, size[0] * SS - 1, size[1] * SS - 1], radius=radius * SS, fill=255)
    return img, mask.resize(size, Image.Resampling.LANCZOS)


def _circle_photo(photo: Image.Image, diameter) -> tuple[Image.Image, Image.Image]:
    img = ImageOps.fit(photo, (diameter, diameter), centering=(0.5, 0.35))
    mask = Image.new("L", (diameter * SS, diameter * SS), 0)
    ImageDraw.Draw(mask).ellipse([0, 0, diameter * SS - 1, diameter * SS - 1], fill=255)
    return img, mask.resize((diameter, diameter), Image.Resampling.LANCZOS)


def _logo_badge(d: ImageDraw.ImageDraw, cx, cy, r, sigle, ring=BLUE, text=BLUE, bg=WHITE):
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=bg)
    d.ellipse([cx - r + 5, cy - r + 5, cx + r - 5, cy + r - 5], outline=ring, width=3)
    d.text((cx, cy), sigle, font=font(int(r * 0.5) if len(sigle) > 3 else int(r * 0.6), bold=True), fill=text, anchor="mm")


def _field(d, x, y, label, value, max_w, label_color=GREY, value_color=NAVY, vsize=27):
    d.text((x, y), label, font=font(18), fill=label_color)
    d.text((x, y + 24), value, font=_fit_font(d, value, max_w, vsize, True), fill=value_color)


# ---------------------------------------------------------------- modèle 1 : Horizon (paysage, sobre)
def recto_horizon(data: CardData) -> Image.Image:
    card = Image.new("RGB", (LAND_W, LAND_H), WHITE)
    panel_w = 330

    # Panneau gauche : dégradé marine -> bleu avec fines diagonales
    panel = _gradient((panel_w, LAND_H), NAVY, BLUE, horizontal=False)
    stripes = Image.new("RGBA", (panel_w * SS, LAND_H * SS), (0, 0, 0, 0))
    sd = ImageDraw.Draw(stripes)
    for x in range(-LAND_H * SS, panel_w * SS, 26 * SS):
        sd.line([(x, LAND_H * SS), (x + LAND_H * SS, 0)], fill=(255, 255, 255, 18), width=2 * SS)
    stripes = stripes.resize((panel_w, LAND_H), Image.Resampling.LANCZOS)
    panel.paste(stripes, (0, 0), stripes)
    card.paste(panel, (0, 0))
    d = ImageDraw.Draw(card)

    p = data.profile
    _logo_badge(d, 70, 62, 38, p.sigle)
    d.text((122, 42), p.sigle, font=font(30, bold=True), fill=WHITE)
    d.text((122, 78), "Dakar", font=font(18), fill=PALE)

    pw, ph = 216, 288
    px, py = (panel_w - pw) // 2, 128
    d.rounded_rectangle([px - 6, py - 6, px + pw + 6, py + ph + 6], radius=20, fill=WHITE)
    img, mask = _rounded_photo(data.photo, (pw, ph), 16)
    card.paste(img, (px, py), mask)

    d.text((panel_w // 2, 456), data.card_id, font=mono_font(30), fill=WHITE, anchor="mm")
    role_f = font(22, bold=True)
    rw = d.textlength(data.role.upper(), font=role_f) + 40
    d.rounded_rectangle([(panel_w - rw) / 2, 488, (panel_w + rw) / 2, 530], radius=21, fill=BLUE_LIGHT)
    d.text((panel_w // 2, 509), data.role.upper(), font=role_f, fill=WHITE, anchor="mm")
    _microtext(d, 24, 596, panel_w - 24, (120, 150, 210), p.sigle, size=10)

    # Partie droite
    x0 = panel_w + 40
    f_school = font(27, bold=True)
    for i, line in enumerate(_wrap(d, p.org, f_school, LAND_W - x0 - 30)):
        d.text((x0, 34 + i * 34), line, font=f_school, fill=NAVY)
    d.text((x0, 112), f"{p.title_fr}  ·  {p.title_en}".upper(), font=font(18, bold=True), fill=BLUE_LIGHT)
    d.rectangle([x0, 144, x0 + 70, 149], fill=BLUE_LIGHT)

    d.text((x0, 172), data.prenom, font=font(30), fill=GREY)
    d.text((x0, 208), data.nom.upper(), font=_fit_font(d, data.nom.upper(), LAND_W - x0 - 30, 50, True), fill=NAVY)

    qr = qr_image(data.token, 310)
    qx, qy = LAND_W - 22 - qr.width, LAND_H - 22 - qr.height
    card.paste(qr, (qx, qy))

    col_w = qx - x0 - 20
    if p.kind == "entreprise":
        rows = [(lab, val) for lab, _, val in short_fields(data)]
    else:
        rows = [("Né(e) le", _fr_date(data.naiss)), ("Émise le", _fr_date(data.emis) if data.emis else "—"),
                ("Valide jusqu'au", _fr_date(data.exp))]
    for i, (label, value) in enumerate(rows):
        _field(d, x0, 300 + i * 80, label, value, col_w, value_color=BLUE if i == 2 else NAVY)

    d.rectangle([panel_w, LAND_H - 10, qx - 20, LAND_H], fill=BLUE_LIGHT)
    return card


# ---------------------------------------------------------------- modèle 2 : Dégradé (portrait, moderne)
def recto_degrade(data: CardData) -> Image.Image:
    card = Image.new("RGB", (CARD_W, CARD_H), WHITE)
    guill = _guilloche((CARD_W, CARD_H), (59, 130, 246, 38), lines=34, amp=14, period=180)
    card.paste(guill, (0, 0), guill)

    # En-tête en dégradé avec bord inférieur en diagonale
    head = _gradient((CARD_W, 330), BLUE, VIOLET)
    mask = Image.new("L", (CARD_W * SS, 330 * SS), 0)
    ImageDraw.Draw(mask).polygon([(0, 0), (CARD_W * SS, 0), (CARD_W * SS, 230 * SS), (0, 330 * SS)], fill=255)
    card.paste(head, (0, 0), mask.resize((CARD_W, 330), Image.Resampling.LANCZOS))
    deco = Image.new("RGBA", (CARD_W * SS, 330 * SS), (0, 0, 0, 0))
    dd = ImageDraw.Draw(deco)
    dd.ellipse([440 * SS, -120 * SS, 760 * SS, 200 * SS], outline=(255, 255, 255, 40), width=26 * SS)
    dd.ellipse([520 * SS, 40 * SS, 700 * SS, 220 * SS], outline=(255, 255, 255, 28), width=14 * SS)
    deco = deco.resize((CARD_W, 330), Image.Resampling.LANCZOS)
    card.paste(deco, (0, 0), Image.composite(deco, Image.new("RGBA", deco.size), mask.resize((CARD_W, 330))).split()[3])
    d = ImageDraw.Draw(card)

    p = data.profile
    _logo_badge(d, 82, 82, 46, p.sigle, ring=VIOLET, text=VIOLET)
    f_school = font(29, bold=True)
    for i, line in enumerate(_wrap(d, p.org, f_school, CARD_W - 150 - 30)):
        d.text((150, 50 + i * 36), line, font=f_school, fill=WHITE)

    # Photo ronde avec anneau en dégradé
    dia, cx, cy = 250, CARD_W // 2, 330
    ring = _gradient((dia + 28, dia + 28), SKY, VIOLET)
    rmask = Image.new("L", ((dia + 28) * SS,) * 2, 0)
    ImageDraw.Draw(rmask).ellipse([0, 0, (dia + 28) * SS - 1, (dia + 28) * SS - 1], fill=255)
    card.paste(ring, (cx - (dia + 28) // 2, cy - (dia + 28) // 2), rmask.resize((dia + 28,) * 2, Image.Resampling.LANCZOS))
    d.ellipse([cx - dia // 2 - 6, cy - dia // 2 - 6, cx + dia // 2 + 6, cy + dia // 2 + 6], fill=WHITE)
    img, m = _circle_photo(data.photo, dia)
    card.paste(img, (cx - dia // 2, cy - dia // 2), m)

    full = f"{data.prenom} {data.nom.upper()}"
    d.text((CARD_W // 2, 500), full, font=_fit_font(d, full, CARD_W - 60, 42, True), fill=NAVY, anchor="mm")
    idf = mono_font(28)
    iw = d.textlength(data.card_id, font=idf) + 44
    d.rounded_rectangle([(CARD_W - iw) / 2, 528, (CARD_W + iw) / 2, 572], radius=22, fill=(237, 233, 254))
    d.text((CARD_W // 2, 550), data.card_id, font=idf, fill=VIOLET, anchor="mm")

    qr = qr_image(data.token, 310)
    qx, qy = CARD_W - 20 - qr.width, 606
    d.rounded_rectangle([qx - 6, qy - 6, qx + qr.width + 6, qy + qr.height + 6], radius=14, fill=WHITE, outline=(221, 214, 254), width=2)
    card.paste(qr, (qx, qy))

    rows = [(label, value) for label, _, value in short_fields(data)]
    for i, (label, value) in enumerate(rows):
        y = 618 + i * 98
        d.rounded_rectangle([34, y + 4, 40, y + 52], radius=3, fill=VIOLET if i == 2 else BLUE_LIGHT)
        _field(d, 54, y, label, value, qx - 54 - 20, value_color=VIOLET if i == 2 else NAVY)

    strip = _gradient((CARD_W, 40), BLUE, VIOLET)
    card.paste(strip, (0, CARD_H - 40))
    _microtext(d, 20, CARD_H - 28, CARD_W - 20, (226, 232, 255), p.sigle, size=12)
    return card


# ---------------------------------------------------------------- modèle 3 : Officiel (paysage, sécurisé)
def recto_officiel(data: CardData) -> Image.Image:
    card = Image.new("RGB", (LAND_W, LAND_H), (250, 251, 255))
    guill = _guilloche((LAND_W, LAND_H), (30, 79, 168, 34), lines=30, amp=16, period=260)
    card.paste(guill, (0, 0), guill)

    # Filigrane : grand sceau très clair au centre
    wm = Image.new("RGBA", (420 * SS, 420 * SS), (0, 0, 0, 0))
    wd = ImageDraw.Draw(wm)
    for k in range(6):
        wd.ellipse([k * 22 * SS, k * 22 * SS, (420 - k * 22) * SS, (420 - k * 22) * SS], outline=(30, 79, 168, 22), width=3 * SS)
    wm = wm.resize((420, 420), Image.Resampling.LANCZOS)
    card.paste(wm, (300, 150), wm)
    d = ImageDraw.Draw(card)
    p = data.profile
    d.text((510, 360), p.sigle, font=font(110, bold=True), fill=(226, 234, 250), anchor="mm")

    # Bandeau supérieur
    card.paste(_gradient((LAND_W, 104), NAVY, BLUE), (0, 0))
    d.rectangle([0, 104, LAND_W, 110], fill=(212, 175, 55))  # filet doré
    _logo_badge(d, 60, 52, 38, p.sigle)
    d.text((116, 18), p.org.upper(), font=_fit_font(d, p.org.upper(), LAND_W - 140, 27, True), fill=WHITE)
    d.text((116, 60), f"{p.title_fr}  /  {p.title_en}", font=font(20), fill=PALE)

    # Photo principale
    pw, ph = 216, 288
    px, py = 30, 132
    d.rectangle([px - 4, py - 4, px + pw + 4, py + ph + 4], fill=WHITE, outline=(203, 213, 225), width=2)
    card.paste(data.photo.resize((pw, ph), Image.Resampling.LANCZOS), (px, py))

    # Champs bilingues
    qr = qr_image(data.token, 310)
    qx, qy = LAND_W - 22 - qr.width, 124
    fx, fw = 274, qx - 274 - 24
    if p.kind == "entreprise":
        middle = [("Fonction / Position", data.fonction), ("Service / Department", data.service)]
    else:
        middle = [("Né(e) le / Date of birth", _fr_date(data.naiss)), ("Statut / Status", data.role)]
    fields = [("Nom / Surname", data.nom.upper()), ("Prénoms / Given names", data.prenom),
              *middle, ("Expire le / Expiry", _fr_date(data.exp))]
    for i, (label, value) in enumerate(fields):
        _field(d, fx, 128 + i * 64, label, value, fw, label_color=(71, 85, 105), vsize=25)
    d.rectangle([qx - 6, qy - 6, qx + qr.width + 6, qy + qr.height + 6], fill=WHITE, outline=(203, 213, 225), width=2)
    card.paste(qr, (qx, qy))

    # Zone basse : image fantôme, pastille irisée, micro-texte, numéro
    ghost = ImageOps.grayscale(data.photo.resize((78, 104), Image.Resampling.LANCZOS))
    ghost = ImageEnhance.Brightness(ImageOps.autocontrast(ghost)).enhance(1.0)
    ghost = Image.blend(Image.new("L", ghost.size, 255), ghost, 0.28).convert("RGB")
    card.paste(ghost, (30, 470))
    _iridescent_seal(card, 172, 522, 52, p.sigle)
    d = ImageDraw.Draw(card)

    _microtext(d, fx, 468, LAND_W - 22, (148, 163, 184), p.sigle, size=10)
    _microtext(d, fx, 482, LAND_W - 22, (148, 163, 184), p.sigle, size=10)
    id_label = "Matricule / Employee No." if p.kind == "entreprise" else "N° de carte / Card No."
    d.text((fx, 506), id_label, font=font(18), fill=(71, 85, 105))
    d.text((fx, 530), data.card_id, font=mono_font(44), fill=NAVY)
    d.text((LAND_W - 22, 548), f"Émise le {_fr_date(data.emis)}" if data.emis else "", font=font(18), fill=GREY, anchor="ra")

    d.rectangle([0, LAND_H - 18, LAND_W, LAND_H], fill=NAVY)
    return card


TEMPLATES = {
    "classique": render_recto,
    "horizon": recto_horizon,
    "degrade": recto_degrade,
    "officiel": recto_officiel,
}


def verso_officiel(data: CardData) -> Image.Image:
    p = data.profile
    card = Image.new("RGB", (LAND_W, LAND_H), (250, 251, 255))
    guill = _guilloche((LAND_W, LAND_H), (30, 79, 168, 30), lines=30, amp=16, period=260)
    card.paste(guill, (0, 0), guill)

    card.paste(_gradient((LAND_W, 84), NAVY, BLUE), (0, 0))
    d = ImageDraw.Draw(card)
    d.rectangle([0, 84, LAND_W, 89], fill=(212, 175, 55))
    _logo_badge(d, 48, 42, 30, p.sigle)
    d.text((92, 14), p.org.upper(), font=_fit_font(d, p.org.upper(), LAND_W - 120, 24, True), fill=WHITE)
    d.text((92, 48), "Conditions d'utilisation  /  Terms of use", font=font(19), fill=PALE)

    # Conditions (colonne gauche)
    paragraphs = [
        f"Cette carte est strictement personnelle. Elle reste la propriété {p.owner} et doit être restituée {p.end}.",
        f"En cas de perte ou de vol, prévenez immédiatement {p.contact} : la carte sera révoquée et refusée à tout contrôle.",
        "Le QR code au recto contient les données du titulaire signées numériquement. Toute modification ou contrefaçon est détectée par l'application de vérification.",
        f"Carte trouvée ? Merci de la remettre à {p.place}.",
    ]
    f_text = font(20)
    col_w = 560
    y = 112
    for para in paragraphs:
        for line in _wrap(d, para, f_text, col_w):
            d.text((30, y), line, font=f_text, fill=NAVY)
            y += 26
        y += 12

    # Signatures (colonne droite)
    x0, x1 = 625, LAND_W - 30
    d.text((x0, 112), "Signature du titulaire / Holder's signature", font=font(17), fill=(71, 85, 105))
    d.rectangle([x0, 138, x1, 248], fill=WHITE, outline=(203, 213, 225), width=2)
    d.text((x0, 272), "Pour l'émetteur / For the issuer", font=font(17), fill=(71, 85, 105))
    d.rectangle([x0, 298, x1, 408], fill=WHITE, outline=(203, 213, 225), width=2)
    _iridescent_seal(card, x1 - 58, 353, 44, p.sigle)
    d = ImageDraw.Draw(card)
    f_org = font(18, bold=True)
    org_lines = _wrap(d, p.org, f_org, x1 - x0 - 130)
    oy = 353 - len(org_lines) * 12
    for i, line in enumerate(org_lines):
        d.text((x0 + 16, oy + i * 24), line, font=f_org, fill=NAVY)

    # Bas : micro-texte, numéro, dates
    _microtext(d, 30, 470, LAND_W - 30, (148, 163, 184), p.sigle, size=10)
    _microtext(d, 30, 484, LAND_W - 30, (148, 163, 184), p.sigle, size=10)
    d.text((30, 512), data.card_id, font=mono_font(40), fill=NAVY)
    dates = f"Délivrée le {_fr_date(data.emis)}   ·   Expire le {_fr_date(data.exp)}" if data.emis \
        else f"Expire le {_fr_date(data.exp)}"
    d.text((LAND_W - 30, 528), dates, font=font(19), fill=GREY, anchor="ra")
    d.text((30, 570), "Vérification : application SecureID, scan du QR code au recto.", font=font(17), fill=GREY)

    d.rectangle([0, LAND_H - 18, LAND_W, LAND_H], fill=NAVY)
    return card


DEFAULT_TEMPLATE = "officiel"
VERSOS = {"officiel": verso_officiel}


def render_card(data: CardData, template: str = DEFAULT_TEMPLATE) -> tuple[Image.Image, Image.Image]:
    """Retourne (recto, verso) pour le modèle demandé."""
    from core.render import render_verso
    recto = TEMPLATES[template](data)
    verso = VERSOS.get(template, render_verso)(data)
    return recto, verso

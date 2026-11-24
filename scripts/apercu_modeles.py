"""Génère l'aperçu de tous les modèles, pour une école et pour une entreprise.

Lancer depuis la racine du projet :  python -m scripts.apercu_modeles
Résultat : sortie/modele_<profil>_<modele>.png et sortie/apercu_modeles.png
"""

from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from PIL import Image, ImageDraw

from core.render import CardData, font
from core.templates import TEMPLATES
from scripts.demo_carte import EXEMPLES, build_card

def carte_exemple(profil: str) -> CardData:
    # Clé jetable : l'aperçu sert à juger le visuel, pas à émettre une vraie carte
    return build_card(profil, Ed25519PrivateKey.generate(), "apercu")


def main() -> None:
    out = Path("sortie")
    out.mkdir(exist_ok=True)
    rows = []
    for profil in EXEMPLES:
        data = carte_exemple(profil)
        cards = []
        for name, render in TEMPLATES.items():
            img = render(data)
            img.save(out / f"modele_{profil}_{name}.png", dpi=(300, 300))
            cards.append((name, img))
        rows.append((profil, cards))

    pad, label_h = 40, 60
    width = max(sum(c.width for _, c in cards) + pad * (len(cards) + 1) for _, cards in rows)
    row_h = max(c.height for _, cards in rows for _, c in cards) + label_h + pad
    sheet = Image.new("RGB", (width, row_h * len(rows) + pad), (226, 232, 240))
    d = ImageDraw.Draw(sheet)
    for r, (profil, cards) in enumerate(rows):
        x, y = pad, pad + r * row_h
        for name, img in cards:
            d.text((x, y), f"{name.capitalize()} · {profil}", font=font(34, bold=True), fill=(15, 23, 42))
            sheet.paste(img, (x, y + label_h))
            x += img.width + pad
    sheet.save(out / "apercu_modeles.png")
    print(f"Aperçu : {(out / 'apercu_modeles.png').resolve()}")


if __name__ == "__main__":
    main()

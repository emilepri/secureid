"""Démo : génère une carte fictive signée (PNG recto/verso + PDF).

Lancer depuis la racine du projet :
    python -m scripts.demo_carte                       # école, modèle officiel
    python -m scripts.demo_carte --profil entreprise
    python -m scripts.demo_carte --modele horizon
"""

import argparse
import getpass
from datetime import date, timedelta
from pathlib import Path

from PIL import Image, ImageDraw

from core import crypto, photo, sid_token
from core.pdf_export import export_card_pdf
from core.render import COMPANY, SCHOOL, CardData
from core.templates import DEFAULT_TEMPLATE, TEMPLATES, render_card

KID = "demo2026"
KEYS_DIR = Path("keys")
OUT_DIR = Path("sortie")

# Personnes fictives : jamais de vraies données pour les démos
EXEMPLES = {
    "ecole": dict(prenom="Awa", nom="DIOP", card_id="STU-2026-001", role="Étudiante",
                  naiss="2003-01-15", profile=SCHOOL),
    "entreprise": dict(prenom="Fatou", nom="SALL", card_id="EMP-2026-014", role="Employée",
                       naiss="1994-06-02", fonction="Analyste cybersécurité",
                       service="Sécurité des SI", profile=COMPANY),
}


def photo_fictive() -> Image.Image:
    """Silhouette neutre : on n'utilise jamais la photo d'une vraie personne pour les démos."""
    img = Image.new("RGB", (600, 800), (226, 232, 240))
    d = ImageDraw.Draw(img)
    d.ellipse([190, 150, 410, 390], fill=(148, 163, 184))
    d.ellipse([90, 430, 510, 900], fill=(148, 163, 184))
    return img


def build_card(profil: str, private_key, kid: str) -> CardData:
    """Construit les données d'une carte fictive et signe son jeton."""
    e = EXEMPLES[profil]
    pic = photo.normalize(photo_fictive())
    today = date.today()
    champs = {"kid": kid, "id": e["card_id"], "nom": e["nom"], "prenom": e["prenom"],
              "naiss": e["naiss"], "role": e.get("fonction") or e["role"],
              "emis": today.isoformat(), "exp": (today + timedelta(days=365)).isoformat(),
              "ph": photo.fingerprint(pic)}
    if e.get("service"):
        champs["svc"] = e["service"]
    token = sid_token.encode_token(champs, private_key)
    return CardData(e["prenom"], e["nom"], e["card_id"], e["role"], e["naiss"], champs["exp"],
                    token, pic, emis=champs["emis"], fonction=e.get("fonction", ""),
                    service=e.get("service", ""), profile=e["profile"])


def charger_ou_creer_cle():
    priv_path = KEYS_DIR / f"{KID}_private.pem"
    if not priv_path.exists():
        print("Aucune clé trouvée : création d'une nouvelle paire de clés de démo.")
        password = getpass.getpass("Choisis un mot de passe (12 caractères minimum) : ")
        crypto.generate_keypair(KID, password, KEYS_DIR)
    else:
        password = getpass.getpass("Mot de passe de la clé de démo : ")
    return crypto.load_private_key(priv_path, password)


def main() -> None:
    parser = argparse.ArgumentParser(description="Génère une carte de démonstration.")
    parser.add_argument("--profil", choices=EXEMPLES, default="ecole")
    parser.add_argument("--modele", choices=TEMPLATES, default=DEFAULT_TEMPLATE)
    args = parser.parse_args()

    private_key = charger_ou_creer_cle()
    public_key = crypto.load_public_key(KEYS_DIR / f"{KID}_public.pem")

    data = build_card(args.profil, private_key, KID)
    recto, verso = render_card(data, args.modele)

    OUT_DIR.mkdir(exist_ok=True)
    base = OUT_DIR / f"{data.card_id}_{args.modele}"
    recto.save(f"{base}_recto.png", dpi=(300, 300))
    verso.save(f"{base}_verso.png", dpi=(300, 300))
    pdf = export_card_pdf(recto, verso, f"{base}.pdf", title=f"Carte {data.profile.org}")

    check = sid_token.verify_token(data.token, {KID: public_key})
    print(f"Carte générée : {pdf.resolve()}")
    print(f"Taille du jeton : {len(data.token)} caractères")
    print(f"Vérification immédiate : {check.status} ({check.reason})")


if __name__ == "__main__":
    main()

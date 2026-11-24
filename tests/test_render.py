from datetime import date

import pytest
from PIL import Image

from core import crypto, photo, sid_token
from core.pdf_export import export_card_pdf
from core.render import CARD_H, CARD_W, CardData, render_recto, render_verso

PASSWORD = "mot-de-passe-de-test-123"


@pytest.fixture
def card(tmp_path):
    priv_path, pub_path = crypto.generate_keypair("k1", PASSWORD, tmp_path)
    priv = crypto.load_private_key(priv_path, PASSWORD)
    pic = photo.normalize(Image.new("RGB", (1200, 900), (200, 180, 160)))
    champs = {"kid": "k1", "id": "STU-2026-001", "nom": "DIOP", "prenom": "Awa",
              "naiss": "2003-01-15", "role": "Étudiante",
              "emis": "2026-11-24", "exp": "2027-11-23", "ph": photo.fingerprint(pic)}
    token = sid_token.encode_token(champs, priv)
    data = CardData("Awa", "DIOP", "STU-2026-001", "Étudiante", "2003-01-15", "2027-11-23", token, pic)
    return data, {"k1": crypto.load_public_key(pub_path)}


def test_photo_normalisee_3_4():
    pic = photo.normalize(Image.new("RGB", (1000, 1000)))
    assert pic.size == photo.PHOTO_SIZE


def test_empreinte_stable_et_sensible():
    a = photo.normalize(Image.new("RGB", (900, 1200), (10, 20, 30)))
    b = photo.normalize(Image.new("RGB", (900, 1200), (10, 20, 30)))
    c = photo.normalize(Image.new("RGB", (900, 1200), (10, 20, 31)))
    assert photo.fingerprint(a) == photo.fingerprint(b)
    assert photo.fingerprint(a) != photo.fingerprint(c)


def test_dimensions_cr80(card):
    data, _ = card
    assert render_recto(data).size == (CARD_W, CARD_H)
    assert render_verso(data).size == (CARD_W, CARD_H)


def test_qr_de_la_carte_se_relit_et_se_verifie(card):
    """Le QR imprimé sur la carte, relu par OpenCV, redonne un jeton authentique."""
    pytest.importorskip("cv2")
    from core.qr_reader import decode_qr
    data, pubs = card
    texte = decode_qr(render_recto(data))
    assert texte == data.token
    assert sid_token.verify_token(texte, pubs, today=date(2027, 1, 1)).ok


def test_export_pdf_deux_pages(card, tmp_path):
    data, _ = card
    pdf = export_card_pdf(render_recto(data), render_verso(data), tmp_path / "carte.pdf")
    contenu = pdf.read_bytes()
    assert contenu.startswith(b"%PDF")
    assert contenu.count(b"/Type /Page\n") + contenu.count(b"/Type /Page ") >= 2 or b"/Count 2" in contenu


@pytest.mark.parametrize("profil", ["ecole", "entreprise"])
def test_modele_officiel_complet(profil, tmp_path):
    """Recto + verso officiels, PDF paysage, QR relu et authentique, pour chaque profil."""
    pytest.importorskip("cv2")
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from core.qr_reader import decode_qr
    from core.templates import render_card
    from scripts.demo_carte import build_card

    key = Ed25519PrivateKey.generate()
    data = build_card(profil, key, "k1")
    recto, verso = render_card(data, "officiel")
    assert recto.size == verso.size == (CARD_H, CARD_W)  # paysage
    assert sid_token.verify_token(decode_qr(recto), {"k1": key.public_key()}).ok
    pdf = export_card_pdf(recto, verso, tmp_path / "carte.pdf")
    assert pdf.read_bytes().startswith(b"%PDF")

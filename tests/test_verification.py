from datetime import date

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from PIL import Image

from core import revocation, sid_token
from core.issuer_service import CardRequest, IssuerService
from core.templates import render_card
from core.verifier_service import REVOQUEE, VerifierService
from db.database import get_engine, init_db


@pytest.fixture
def env(tmp_path):
    Session = init_db(get_engine(tmp_path / "t.db"))
    key = Ed25519PrivateKey.generate()
    issuer = IssuerService(Session, key, "k1", "admin", tmp_path / "data", tmp_path / "sortie")
    return issuer, key, tmp_path


def emettre(issuer, nom="Diop"):
    return issuer.issue(CardRequest(profil="ecole", nom=nom, prenom="Awa", naiss=date(2003, 1, 15),
                                    role="Étudiante", photo_source=Image.new("RGB", (600, 800), (90, 120, 150))))


# ---------------------------------------------------------------- liste de révocation
def test_liste_revocation_signee(env):
    _, key, tmp = env
    path = revocation.write(tmp / "rl.sid", ["B", "A", "A"], key, "k1")
    rl = revocation.load(path, {"k1": key.public_key()})
    assert rl.revoquees == {"A", "B"} and "A" in rl


def test_liste_revocation_alteree_refusee(env):
    _, key, tmp = env
    text = revocation.build(["STU-2026-002"], key, "k1")
    prefix, body, sig = text.split(".")
    faux = sid_token._b64e(sid_token.canonical({"kid": "k1", "emis": "2026-01-01T00:00:00+00:00", "revoquees": []}))
    with pytest.raises(revocation.RevocationListError):
        revocation.parse(f"{prefix}.{faux}.{sig}", {"k1": key.public_key()})


def test_liste_revocation_mauvaise_cle(env):
    _, key, _ = env
    text = revocation.build(["X"], Ed25519PrivateKey.generate(), "k1")
    with pytest.raises(revocation.RevocationListError):
        revocation.parse(text, {"k1": key.public_key()})


# ---------------------------------------------------------------- bout en bout
def test_scenario_complet(env):
    """Émission -> export -> vérification : authentique, puis révoquée après mise à jour de la liste."""
    issuer, _, tmp = env
    card = emettre(issuer)
    issuer.export_for_verifier(tmp / "verif")
    verifier, warnings = VerifierService.from_folder(tmp / "verif", photos_dir=tmp / "data" / "photos")
    assert warnings == []

    v = verifier.verify_token(card.token)
    assert v.ok and v.payload["nom"] == "DIOP" and v.photo_conforme is True

    issuer.revoke(card.card_id, "Carte volée")
    issuer.export_for_verifier(tmp / "verif")
    verifier, _ = VerifierService.from_folder(tmp / "verif")
    assert verifier.verify_token(card.token).status == REVOQUEE


def test_verification_depuis_image_de_carte(env):
    pytest.importorskip("cv2")
    issuer, _, tmp = env
    card = emettre(issuer)
    issuer.export_for_verifier(tmp / "verif")
    verifier, _ = VerifierService.from_folder(tmp / "verif")
    # On reconstruit le recto à partir du jeton émis, comme une photo de la carte
    from core.render import CardData, SCHOOL
    from core import photo
    p = sid_token.verify_token(card.token, verifier.public_keys).payload
    data = CardData(p["prenom"], p["nom"], p["id"], "Étudiante", p["naiss"], p["exp"], card.token,
                    photo.normalize(Image.new("RGB", (600, 800))), emis=p["emis"], profile=SCHOOL)
    recto, _ = render_card(data)
    assert verifier.verify_image(recto).ok
    assert verifier.verify_image(Image.new("RGB", (400, 300), "white")).status == sid_token.INVALIDE


def test_carte_falsifiee_et_expiree(env):
    issuer, _, tmp = env
    card = emettre(issuer)
    issuer.export_for_verifier(tmp / "verif")
    verifier, _ = VerifierService.from_folder(tmp / "verif")
    prefix, body, sig = card.token.split(".")
    faux = sid_token._b64e(sid_token._b64d(body).replace(b"DIOP", b"FALL"))
    assert verifier.verify_token(f"{prefix}.{faux}.{sig}").status == sid_token.FALSIFIEE
    assert verifier.verify_token(card.token, today=date(2100, 1, 1)).status == sid_token.EXPIREE


def test_photo_remplacee_detectee(env):
    issuer, _, tmp = env
    card = emettre(issuer)
    issuer.export_for_verifier(tmp / "verif")
    Image.new("RGB", (600, 800), (255, 0, 0)).save(tmp / "data" / "photos" / f"{card.card_id}.png")
    verifier, _ = VerifierService.from_folder(tmp / "verif", photos_dir=tmp / "data" / "photos")
    assert verifier.verify_token(card.token).photo_conforme is False


def test_dossier_vide_avertit(tmp_path):
    verifier, warnings = VerifierService.from_folder(tmp_path / "rien")
    assert len(warnings) == 2 and verifier.public_keys == {}

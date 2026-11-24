from datetime import date

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from PIL import Image

from core import sid_token
from core.issuer_service import CardRequest, IssuerService, ValidationError, validate
from db.database import get_engine, init_db
from db.models import Card


@pytest.fixture
def service(tmp_path):
    Session = init_db(get_engine(tmp_path / "t.db"))
    key = Ed25519PrivateKey.generate()
    svc = IssuerService(Session, key, "k1", "operateur-test", tmp_path / "data", tmp_path / "sortie")
    return svc, key


def demande(**kw):
    base = dict(profil="ecole", nom="Diop", prenom="Awa", naiss=date(2003, 1, 15), role="Étudiante",
                photo_source=Image.new("RGB", (800, 1000), (180, 160, 140)))
    base.update(kw)
    return CardRequest(**base)


def test_emission_complete(service):
    svc, key = service
    card = svc.issue(demande())
    assert card.card_id == f"STU-{date.today().year}-001"
    assert card.statut == "ACTIVE"
    assert sid_token.verify_token(card.token, {"k1": key.public_key()}).payload["nom"] == "DIOP"
    from pathlib import Path
    assert Path(card.pdf_path).exists()
    assert svc.check_audit().ok


def test_numerotation_par_profil(service):
    svc, _ = service
    y = date.today().year
    svc.issue(demande())
    svc.issue(demande(prenom="Moussa"))
    ent = svc.issue(demande(profil="entreprise", fonction="Analyste", service="DSI", role="Employé"))
    assert svc.next_card_id("ecole") == f"STU-{y}-003"
    assert ent.card_id == f"EMP-{y}-001"


def test_jeton_entreprise_contient_service(service):
    svc, key = service
    card = svc.issue(demande(profil="entreprise", fonction="Analyste", service="DSI", role="Employé"))
    payload = sid_token.verify_token(card.token, {"k1": key.public_key()}).payload
    assert payload["role"] == "Analyste" and payload["svc"] == "DSI"


@pytest.mark.parametrize("champ,valeur", [
    ("nom", ""), ("nom", "D1op<script>"), ("naiss", date(2024, 1, 1)), ("photo_source", None), ("validite_mois", 0),
])
def test_validation_refuse(champ, valeur):
    with pytest.raises(ValidationError):
        validate(demande(**{champ: valeur}))


def test_entreprise_sans_service_refusee():
    with pytest.raises(ValidationError):
        validate(demande(profil="entreprise", fonction="Analyste", service=""))


def test_revocation_et_audit(service):
    svc, _ = service
    card = svc.issue(demande())
    svc.revoke(card.card_id, "Carte perdue")
    rows = svc.list_cards(card.card_id)
    assert rows[0]["statut"] == "REVOQUEE"
    with pytest.raises(ValidationError):
        svc.revoke(card.card_id, "Encore")
    with pytest.raises(ValidationError):
        svc.revoke("INCONNUE", "x")
    rapport = svc.check_audit()
    assert rapport.ok and rapport.entries == 3  # clé + émission + révocation


def test_recherche(service):
    svc, _ = service
    svc.issue(demande())
    svc.issue(demande(nom="Sall", prenom="Fatou"))
    assert [r["nom"] for r in svc.list_cards("sall")] == ["SALL"]
    assert len(svc.list_cards()) == 2


def test_apercu_n_enregistre_rien(service):
    svc, _ = service
    recto, verso = svc.preview(demande())
    assert recto.size == verso.size
    with svc.Session() as s:
        assert s.query(Card).count() == 0

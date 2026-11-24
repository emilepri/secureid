from datetime import date

import pytest

from core import crypto, sid_token

PASSWORD = "mot-de-passe-de-test-123"

CARD = {
    "kid": "k2026",
    "id": "STU-2026-001",
    "nom": "DIOP",
    "prenom": "Awa",
    "naiss": "2003-01-15",
    "role": "Etudiante",
    "etab": "ESTM",
    "emis": "2026-11-22",
    "exp": "2027-11-21",
    "ph": "0123456789abcdef0123456789abcdef",
}


@pytest.fixture
def keys(tmp_path):
    priv_path, pub_path = crypto.generate_keypair("k2026", PASSWORD, tmp_path)
    return crypto.load_private_key(priv_path, PASSWORD), {"k2026": crypto.load_public_key(pub_path)}


def test_cle_privee_est_chiffree(tmp_path):
    priv_path, _ = crypto.generate_keypair("k1", PASSWORD, tmp_path)
    assert b"ENCRYPTED PRIVATE KEY" in priv_path.read_bytes()
    with pytest.raises(ValueError):
        crypto.load_private_key(priv_path, "mauvais-mot-de-passe")


def test_mot_de_passe_trop_court(tmp_path):
    with pytest.raises(ValueError):
        crypto.generate_keypair("k1", "court", tmp_path)


def test_jeton_valide(keys):
    priv, pubs = keys
    token = sid_token.encode_token(CARD, priv)
    assert token.startswith("SID1.")
    result = sid_token.verify_token(token, pubs, today=date(2027, 1, 1))
    assert result.ok
    assert result.payload["nom"] == "DIOP"


def test_un_caractere_modifie_est_detecte(keys):
    priv, pubs = keys
    token = sid_token.encode_token(CARD, priv)
    prefix, body, sig = token.split(".")
    i = len(body) // 2
    altered_body = body[:i] + ("A" if body[i] != "A" else "B") + body[i + 1:]
    result = sid_token.verify_token(f"{prefix}.{altered_body}.{sig}", pubs)
    assert result.status in (sid_token.FALSIFIEE, sid_token.INVALIDE)
    assert not result.ok


def test_nom_change_dans_payload_detecte(keys):
    priv, pubs = keys
    token = sid_token.encode_token(CARD, priv)
    _, _, sig = token.split(".")
    faux = sid_token._b64e(sid_token.canonical({"v": 1, **CARD, "nom": "FALL"}))
    result = sid_token.verify_token(f"SID1.{faux}.{sig}", pubs)
    assert result.status == sid_token.FALSIFIEE


def test_fausse_cle_detectee(keys, tmp_path):
    _, pubs = keys
    autre_priv_path, _ = crypto.generate_keypair("k2026", PASSWORD, tmp_path / "pirate")
    autre_priv = crypto.load_private_key(autre_priv_path, PASSWORD)
    token = sid_token.encode_token(CARD, autre_priv)
    assert sid_token.verify_token(token, pubs).status == sid_token.FALSIFIEE


def test_carte_expiree(keys):
    priv, pubs = keys
    token = sid_token.encode_token(CARD, priv)
    result = sid_token.verify_token(token, pubs, today=date(2028, 1, 1))
    assert result.status == sid_token.EXPIREE


def test_qr_illisible(keys):
    _, pubs = keys
    assert sid_token.verify_token("n'importe quoi", pubs).status == sid_token.INVALIDE
    assert sid_token.verify_token("SID1.%%%.###", pubs).status == sid_token.INVALIDE


def test_champ_manquant_refuse(keys):
    priv, _ = keys
    incomplet = {k: v for k, v in CARD.items() if k != "exp"}
    with pytest.raises(ValueError):
        sid_token.encode_token(incomplet, priv)

"""Test de fumée de l'application de vérification (sans caméra)."""

import os
from datetime import date

import pytest

pytest.importorskip("PySide6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey  # noqa: E402
from PIL import Image  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from apps.verifier.main import VerifierWindow  # noqa: E402
from core.issuer_service import CardRequest, IssuerService  # noqa: E402
from core.verifier_service import VerifierService  # noqa: E402
from db.database import get_engine, init_db  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def test_verdicts_affiches(app, tmp_path):
    issuer = IssuerService(init_db(get_engine(tmp_path / "t.db")), Ed25519PrivateKey.generate(), "k1", "t",
                           tmp_path / "data", tmp_path / "out")
    card = issuer.issue(CardRequest(profil="ecole", nom="Diop", prenom="Awa", naiss=date(2003, 1, 15),
                                    role="Étudiante", photo_source=Image.new("RGB", (600, 800))))
    issuer.export_for_verifier(tmp_path / "verif")
    service, warnings = VerifierService.from_folder(tmp_path / "verif", tmp_path / "data" / "photos")
    win = VerifierWindow(service, warnings)

    win.show_verdict(service.verify_token(card.token))
    assert win.banner.text() == "CARTE AUTHENTIQUE"
    assert win.fields["nom"].text() == "DIOP"
    assert "conforme" in win.photo_status.text()

    win.show_verdict(service.verify_token("SID1.abc.def"))
    assert win.history.count() == 2

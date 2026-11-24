"""Test de fumée de l'interface : la fenêtre se construit, l'aperçu se calcule, la liste se remplit."""

import os

import pytest

pytest.importorskip("PySide6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey  # noqa: E402
from PIL import Image  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from apps.issuer.main import MainWindow  # noqa: E402
from core.issuer_service import IssuerService  # noqa: E402
from db.database import get_engine, init_db  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def test_fenetre_apercu_et_liste(app, tmp_path):
    Session = init_db(get_engine(tmp_path / "t.db"))
    svc = IssuerService(Session, Ed25519PrivateKey.generate(), "k1", "test", tmp_path / "data", tmp_path / "out")
    win = MainWindow(svc)
    tab = win.issue_tab

    photo = tmp_path / "photo.png"
    Image.new("RGB", (600, 800), (120, 140, 160)).save(photo)
    tab.photo_path = str(photo)
    tab.nom.setText("Diop")
    tab.prenom.setText("Awa")
    tab.refresh_preview()
    assert not tab.recto_label.pixmap().isNull()

    # Passage en profil entreprise : les champs fonction/service s'activent
    tab.profil.setCurrentIndex(tab.profil.findData("entreprise"))
    assert tab.fonction.isEnabled() and tab.card_id.text().startswith("EMP-")

    tab.fonction.setText("Analyste")
    tab.service_field.setText("DSI")
    svc.issue(tab.request())
    win.cards_tab.refresh()
    assert win.cards_tab.table.rowCount() == 1
    assert win.cards_tab.table.item(0, 6).text() == "ACTIVE"


def test_onglet_emission_en_masse(app, tmp_path):
    from apps.issuer.batch_tab import BatchTab
    Session = init_db(get_engine(tmp_path / "t.db"))
    svc = IssuerService(Session, Ed25519PrivateKey.generate(), "k1", "test", tmp_path / "data", tmp_path / "out")
    photos = tmp_path / "photos"
    photos.mkdir()
    Image.new("RGB", (600, 800)).save(photos / "a.jpg")
    f = tmp_path / "lot.csv"
    f.write_text("nom;prenom;date_naissance;photo\nDiop;Awa;15/01/2003;a.jpg\nFall;Ibou;99/99/2000;a.jpg\n",
                 encoding="utf-8")
    tab = BatchTab(svc, tmp_path / "out", on_issued=lambda: None)
    tab.file, tab.photos = f, photos
    tab.analyse()
    assert tab.table.rowCount() == 2 and tab.issue_btn.isEnabled()
    assert "1 ligne(s) valide(s), 1 ligne(s) en erreur" in tab.summary.text()

"""Régénère les captures du README (docs/img) avec des données fictives, sans écran.

Lancer depuis la racine du projet :  python -m scripts.captures
"""

import os
import shutil
import tempfile
from datetime import date
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey  # noqa: E402
from PySide6.QtWidgets import QApplication, QTabWidget  # noqa: E402

from apps.issuer.dialogs import LoginDialog  # noqa: E402
from apps.issuer.main import MainWindow, apply_light_theme, pil_to_pixmap  # noqa: E402
from apps.verifier.main import VerifierWindow  # noqa: E402
from core import batch  # noqa: E402
from core.auth import AuthService  # noqa: E402
from core.issuer_service import CardRequest, IssuerService  # noqa: E402
from core.sheets import export_sheets  # noqa: E402
from core.verifier_service import VerifierService  # noqa: E402
from db.database import get_engine, init_db  # noqa: E402
from scripts.demo_carte import photo_fictive  # noqa: E402

OUT = Path("docs/img")
MDP = "Teranga-2026-ok"


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp())
    app = QApplication.instance() or QApplication([])
    apply_light_theme(app)

    Session = init_db(get_engine(tmp / "t.db"))
    auth = AuthService(Session)
    auth.create_operator("e.priso", MDP, "admin", "Emile PRISO")
    auth.create_operator("a.diallo", MDP, "operateur", "Aminata DIALLO")
    user = auth.authenticate("e.priso", MDP)
    svc = IssuerService(Session, Ed25519PrivateKey.generate(), "sid2026", user.login, tmp / "data", tmp / "out")

    photos = tmp / "photos"
    photos.mkdir()
    for n in ("diop", "sall", "ndiaye", "fall", "ba"):
        photo_fictive().save(photos / f"{n}.jpg")
    c_ent, recto_ent, verso_ent = svc.issue_with_faces(CardRequest(
        profil="entreprise", nom="Sall", prenom="Fatou", naiss=date(1994, 6, 2), role="Employée",
        fonction="Analyste cybersécurité", service="Sécurité des SI", photo_source=photos / "sall.jpg"))
    recto_ent.save(OUT / "carte_recto.png")
    verso_ent.save(OUT / "carte_verso.png")
    c_rev = svc.issue(CardRequest(profil="ecole", nom="Ndiaye", prenom="Moussa", naiss=date(2002, 3, 4),
                                  role="Étudiant", photo_source=photos / "ndiaye.jpg"))
    svc.revoke(c_rev.card_id, "Carte perdue")

    csv = tmp / "lot.csv"
    csv.write_text("nom;prenom;date_naissance;photo\nDIOP;Awa;15/01/2003;diop.jpg\nFALL;Ibrahima;31/02/2001;fall.jpg\n"
                   "BA;Mariama;06/06/2002;ba.jpg\nGUEYE;Lat;01/01/2000;absente.jpg\n", encoding="utf-8")

    # Connexion
    dlg = LoginDialog(auth, "Tu es déconnecté.")
    dlg.login.setText("e.priso")
    dlg.show()
    app.processEvents()
    dlg.grab().save(str(OUT / "connexion.png"))

    # Fenêtre principale
    win = MainWindow(svc, auth, user, lambda *a, **k: None)
    win.resize(1280, 820)
    win.show()
    tabs = win.findChild(QTabWidget)
    t = win.issue_tab
    t.profil.setCurrentIndex(t.profil.findData("ecole"))
    t.photo_path = str(photos / "diop.jpg")
    t.nom.setText("Diop")
    t.prenom.setText("Awa")
    t.refresh_preview()
    app.processEvents()
    win.grab().save(str(OUT / "emission.png"))

    tabs.setCurrentIndex(1)
    b = win.batch_tab
    b.file, b.photos = csv, photos
    b.file_label.setText("titulaires.csv")
    b.photo_label.setText(r"C:\Users\USER\Desktop\photos")
    b.analyse()
    app.processEvents()
    win.grab().save(str(OUT / "emission_masse.png"))

    tabs.setCurrentIndex(2)
    win.cards_tab.refresh()
    app.processEvents()
    win.grab().save(str(OUT / "cartes_emises.png"))

    tabs.setCurrentIndex(3)
    app.processEvents()
    win.grab().save(str(OUT / "operateurs.png"))

    # Planches A4
    rep = batch.analyse(csv, photos)
    issued = batch.issue_valid(svc, rep)
    pdf, _ = export_sheets([(recto_ent, verso_ent)] + [(r, v) for _, r, v in issued], tmp / "planches.pdf")
    try:
        from pdf2image import convert_from_path
        convert_from_path(str(pdf), dpi=60)[0].save(OUT / "planche_a4.png")
    except Exception:  # pdf2image/poppler absent : on saute cette image
        pass

    # Vérification
    svc.export_for_verifier(tmp / "verif")
    vsvc, warnings = VerifierService.from_folder(tmp / "verif", tmp / "data" / "photos")
    vwin = VerifierWindow(vsvc, warnings)
    vwin.resize(1280, 800)
    vwin.show()
    vwin.show_verdict(vsvc.verify_token(c_rev.token))
    from PySide6.QtCore import Qt
    vwin.view.setPixmap(pil_to_pixmap(recto_ent).scaled(vwin.view.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))
    vwin.show_verdict(vsvc.verify_image(recto_ent))
    app.processEvents()
    vwin.grab().save(str(OUT / "verification.png"))

    shutil.rmtree(tmp, ignore_errors=True)
    print(f"Captures enregistrées dans {OUT.resolve()}")


if __name__ == "__main__":
    main()

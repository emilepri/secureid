from datetime import date

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from PIL import Image
from pypdf import PdfReader

from core import batch
from core.issuer_service import IssuerService
from core.sheets import LANDSCAPE, PORTRAIT, export_sheets
from db.database import get_engine, init_db

HEADER = "Nom;Prénom;Date de naissance;Statut;Fonction;Service;Photo;Profil;Validité mois\n"


@pytest.fixture
def env(tmp_path):
    photos = tmp_path / "photos"
    photos.mkdir()
    for name in ("a.jpg", "b.png", "c.jpg"):
        Image.new("RGB", (600, 800), (100, 120, 140)).save(photos / name)
    svc = IssuerService(init_db(get_engine(tmp_path / "t.db")), Ed25519PrivateKey.generate(), "k1", "admin",
                        tmp_path / "data", tmp_path / "out")
    return svc, photos, tmp_path


def _csv(tmp, body, name="lot.csv"):
    p = tmp / name
    p.write_text(HEADER + body, encoding="utf-8-sig")
    return p


def test_analyse_lignes_valides_et_erreurs(env):
    _, photos, tmp = env
    f = _csv(tmp, "Diop;Awa;15/01/2003;Étudiante;;;a.jpg;;\n"
                  "Sall;Fatou;1994-06-02;Employée;Analyste;DSI;b;entreprise;24\n"
                  "Ndiaye;Moussa;31/02/2002;;;;c.jpg;;\n"
                  "Fall;Ibou;01/01/2001;;;;absente.jpg;;\n"
                  "Diop;Awa;15/01/2003;;;;a.jpg;;\n"
                  "Gueye;Lat;01/01/2000;;;;..\\..\\secret.png;;\n"
                  ";;;;;;;;\n")
    rep = batch.analyse(f, photos)
    assert [ln.line for ln in rep.valid] == [2, 3]
    assert rep.valid[1].request.profil == "entreprise" and rep.valid[1].request.validite_mois == 24
    erreurs = {ln.line: ln.error for ln in rep.invalid}
    assert "non reconnue" in erreurs[4] and "introuvable" in erreurs[5]
    assert "doublon" in erreurs[6] and "refusé" in erreurs[7]
    assert len(rep.lines) == 6  # la ligne vide est ignorée


def test_colonnes_obligatoires(env):
    _, photos, tmp = env
    p = tmp / "mauvais.csv"
    p.write_text("nom;prenom\nDiop;Awa\n", encoding="utf-8")
    with pytest.raises(batch.BatchFileError, match="date_naissance"):
        batch.analyse(p, photos)


def test_excel(env):
    from openpyxl import Workbook
    _, photos, tmp = env
    wb = Workbook()
    ws = wb.active
    ws.append(["NOM", "PRENOM", "DATE_NAISSANCE", "PHOTO"])
    ws.append(["Diop", "Awa", date(2003, 1, 15), "a.jpg"])
    wb.save(tmp / "lot.xlsx")
    rep = batch.analyse(tmp / "lot.xlsx", photos)
    assert len(rep.valid) == 1 and rep.valid[0].request.naiss == date(2003, 1, 15)


def test_emission_en_masse_et_rapport(env):
    svc, photos, tmp = env
    f = _csv(tmp, "Diop;Awa;15/01/2003;;;;a.jpg;;\nSall;Fatou;02/06/1994;;;;b.png;;\nX1;Y;01/01/2001;;;;c.jpg;;\n")
    rep = batch.analyse(f, photos)
    issued = batch.issue_valid(svc, rep)
    assert [ln.card_id for ln, _, _ in issued] == [f"STU-{date.today().year}-001", f"STU-{date.today().year}-002"]
    rapport = batch.write_report(rep, tmp / "rapport.csv").read_text(encoding="utf-8-sig")
    assert rapport.count("EMISE") == 2 and "ERREUR" in rapport
    assert svc.check_audit().ok


def test_modele_csv_relisible(env):
    _, photos, tmp = env
    p = batch.write_template(tmp / "modele.csv")
    rows = batch.read_rows(p)
    assert len(rows) == 2 and rows[1][1]["fonction"] == "Analyste cybersécurité"


# ---------------------------------------------------------------- planches
def test_disposition_dans_la_feuille():
    for lay in (LANDSCAPE, PORTRAIT):
        assert lay.margin_x > 5 * 2.83 and lay.margin_y > 5 * 2.83  # marges > 5 mm (zone imprimable)
    assert LANDSCAPE.per_page == 10 and PORTRAIT.per_page == 9
    # Miroir : la 1re carte du recto est derrière, à droite, sur la page verso
    assert LANDSCAPE.position(0, mirrored=True) == LANDSCAPE.position(1)


def test_planches_pdf(env, tmp_path):
    svc, photos, tmp = env
    f = _csv(tmp, "".join(f"N{chr(65 + i)};P;01/01/2000;;;;a.jpg;;\n" for i in range(11)))
    issued = batch.issue_valid(svc, batch.analyse(f, photos))
    pdf, feuilles = export_sheets([(r, v) for _, r, v in issued], tmp_path / "planches.pdf")
    assert feuilles == 2
    reader = PdfReader(str(pdf))
    assert len(reader.pages) == 4  # recto + verso par feuille
    w, h = reader.pages[0].mediabox.width, reader.pages[0].mediabox.height
    assert round(float(w)) == 595 and round(float(h)) == 842  # A4


def test_planches_depuis_cartes_existantes(env, tmp_path):
    svc, photos, tmp = env
    f = _csv(tmp, "Diop;Awa;15/01/2003;;;;a.jpg;;\n")
    (line, _, _), = batch.issue_valid(svc, batch.analyse(f, photos))
    recto, verso = svc.render_existing(line.card_id)
    assert recto.size == (1011, 638)
    _, feuilles = export_sheets([(recto, verso)], tmp_path / "p.pdf")
    assert feuilles == 1

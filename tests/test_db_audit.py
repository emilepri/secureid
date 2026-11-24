import pytest
from sqlalchemy import text

from core import audit
from db.database import get_engine, init_db
from db.models import Card, Holder


@pytest.fixture
def session(tmp_path):
    engine = get_engine(tmp_path / "test.db")
    Session = init_db(engine)
    with Session() as s:
        yield s


def _remplir_journal(session, n=3):
    for i in range(n):
        audit.add_entry(session, "admin", "EMISSION", f"STU-2026-00{i + 1}")
    session.commit()


def test_tables_et_carte(session):
    h = Holder(nom="DIOP", prenom="Awa", date_naissance="2003-01-15",
               role="Etudiante", etablissement="ESTM")
    session.add(h)
    session.flush()
    session.add(Card(card_id="STU-2026-001", holder_id=h.id, kid="k2026",
                     emis_le="2026-11-24", expire_le="2027-11-23", token="SID1.x.y"))
    session.commit()
    assert session.get(Card, "STU-2026-001").holder.nom == "DIOP"


def test_cle_etrangere_appliquee(session):
    session.add(Card(card_id="X", holder_id=999, kid="k", emis_le="", expire_le="", token=""))
    with pytest.raises(Exception):
        session.commit()


def test_journal_intact(session):
    _remplir_journal(session)
    rapport = audit.verify_chain(session)
    assert rapport.ok and rapport.entries == 3


def test_journal_vide_est_valide(session):
    assert audit.verify_chain(session).ok


def test_modification_detectee(session):
    _remplir_journal(session)
    session.execute(text("UPDATE audit_log SET cible = 'STU-FAUX' WHERE id = 2"))
    session.commit()
    session.expire_all()
    rapport = audit.verify_chain(session)
    assert not rapport.ok and rapport.first_bad_id == 2


def test_suppression_detectee(session):
    _remplir_journal(session)
    session.execute(text("DELETE FROM audit_log WHERE id = 2"))
    session.commit()
    session.expire_all()
    rapport = audit.verify_chain(session)
    assert not rapport.ok and rapport.first_bad_id == 3


def test_hash_recalcule_ne_suffit_pas(session):
    """Un attaquant qui modifie une ligne ET recalcule son hash casse le lien avec la suivante."""
    _remplir_journal(session)
    e2 = session.get(audit.AuditLog, 2)
    e2.cible = "STU-FAUX"
    e2.hash = audit._compute_hash(e2.hash_precedent, e2.horodatage, e2.operateur,
                                  e2.action, e2.cible, e2.details)
    session.commit()
    rapport = audit.verify_chain(session)
    assert not rapport.ok and rapport.first_bad_id == 3

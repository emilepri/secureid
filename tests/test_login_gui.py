"""Connexion, droits par rôle et déconnexion dans l'interface (sans affichage réel)."""

import os

import pytest

pytest.importorskip("PySide6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey  # noqa: E402
from PySide6.QtWidgets import QApplication, QTabWidget  # noqa: E402
from sqlalchemy import select  # noqa: E402

from apps.issuer.dialogs import LoginDialog  # noqa: E402
from apps.issuer.main import MainWindow, SessionController  # noqa: E402
from core.auth import AuthService  # noqa: E402
from core.issuer_service import IssuerService  # noqa: E402
from db.database import get_engine, init_db  # noqa: E402
from db.models import AuditLog  # noqa: E402

MDP = "Teranga-2026-ok"


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def env(tmp_path):
    Session = init_db(get_engine(tmp_path / "t.db"))
    auth = AuthService(Session)
    auth.create_operator("admin1", MDP, "admin", "Admin Un")
    auth.create_operator("agent1", MDP, "operateur", "Agent Un")
    svc = IssuerService(Session, Ed25519PrivateKey.generate(), "k1", "poste", tmp_path / "data", tmp_path / "out")
    return Session, auth, svc


def test_ecran_de_connexion(app, env):
    _, auth, _ = env
    dlg = LoginDialog(auth)
    dlg.login.setText("agent1")
    dlg.password.setText("mauvais-mdp-1")
    dlg._accept()
    assert dlg.user is None and dlg.error.text() == "Identifiant ou mot de passe incorrect."
    dlg.password.setText(MDP)
    dlg._accept()
    assert dlg.user.login == "agent1"


def _tab_titles(win):
    tabs = win.findChild(QTabWidget)
    return [tabs.tabText(i) for i in range(tabs.count())]


def test_droits_operateur(app, env):
    _, auth, svc = env
    user = auth.authenticate("agent1", MDP)
    win = MainWindow(svc, auth, user, lambda *a, **k: None)
    assert "Opérateurs" not in _tab_titles(win)
    assert not win.cards_tab.revoke_btn.isEnabled()


def test_droits_admin(app, env):
    _, auth, svc = env
    user = auth.authenticate("admin1", MDP)
    win = MainWindow(svc, auth, user, lambda *a, **k: None)
    assert "Opérateurs" in _tab_titles(win)
    assert win.cards_tab.revoke_btn.isEnabled()


def test_deconnexion_tracee(app, env, monkeypatch):
    Session, auth, svc = env
    ctrl = SessionController(app, svc, auth)
    monkeypatch.setattr(ctrl, "start", lambda *a, **k: None)  # pas de nouvel écran de connexion en test
    ctrl.user = auth.authenticate("agent1", MDP)
    ctrl.window = MainWindow(svc, auth, ctrl.user, ctrl.end_session)
    ctrl.end_session("inactivité")
    assert ctrl.user is None and ctrl.window is None
    with Session() as s:
        last = s.scalars(select(AuditLog).order_by(AuditLog.id.desc())).first()
    assert last.action == "DECONNEXION" and last.details == "inactivité"

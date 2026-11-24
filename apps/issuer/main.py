"""Application d'émission SecureID (PySide6).

Lancer depuis la racine du projet :  python -m apps.issuer
"""

import io
import sys
from datetime import date
from pathlib import Path

from PIL import Image
from PySide6.QtCore import QDate, QEvent, QObject, Qt, QTimer, QUrl
from PySide6.QtGui import QColor, QDesktopServices, QPalette, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QComboBox, QDateEdit, QDialog, QFileDialog,
    QFormLayout, QFrame, QGroupBox, QScrollArea, QHBoxLayout, QHeaderView, QInputDialog, QLabel, QLineEdit, QMainWindow,
    QMessageBox, QPushButton, QSpinBox, QTableWidget, QTableWidgetItem, QTabWidget, QVBoxLayout, QWidget,
)

from core.auth import AuthService, CurrentUser
from core.issuer_service import CardRequest, IssuerService, ValidationError
from core.render import PROFILES
from core.templates import DEFAULT_TEMPLATE, TEMPLATES
from db.database import get_engine, init_db

KID = "sid2026"
from core.paths import DATA_DIR, KEYS_DIR, OUT_DIR, TRUST_DIR  # noqa: E402

STYLE = """
QWidget { color: #0f172a; }
QMainWindow, QDialog { background: #f1f5f9; }
QComboBox QAbstractItemView { background: white; color: #0f172a; selection-background-color: #1e4fa8; selection-color: white; }
QTabBar::tab { background: transparent; }
QGroupBox { background: white; border: 1px solid #cbd5e1; border-radius: 10px; margin-top: 14px; padding: 12px; font-weight: 600; color: #0f2a5c; }
QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 4px; }
QLineEdit, QComboBox, QDateEdit, QSpinBox { padding: 6px; border: 1px solid #cbd5e1; border-radius: 6px; background: white; }
QLineEdit:focus, QComboBox:focus, QDateEdit:focus, QSpinBox:focus { border: 1px solid #1e4fa8; }
QLineEdit:disabled { background: #e2e8f0; color: #94a3b8; }
QComboBox::drop-down, QDateEdit::drop-down { border: none; width: 26px; }
QSpinBox::up-button, QSpinBox::down-button { border: none; width: 22px; }
QPushButton { padding: 8px 14px; border-radius: 6px; border: 1px solid #cbd5e1; background: white; }
QPushButton:hover { background: #e2e8f0; }
QPushButton#primary { background: #1e4fa8; color: white; border: none; font-weight: 600; }
QPushButton#primary:hover { background: #10306f; }
QPushButton#danger { background: #b91c1c; color: white; border: none; }
QTabWidget::pane { border: none; }
QTabBar::tab { padding: 10px 22px; font-weight: 600; color: #475569; }
QTabBar::tab:selected { color: #1e4fa8; border-bottom: 3px solid #1e4fa8; }
QTableWidget { background: white; border: 1px solid #cbd5e1; border-radius: 8px; gridline-color: #e2e8f0; }
QHeaderView::section { background: #0f2a5c; color: white; padding: 6px; border: none; font-weight: 600; }
QLabel#header { background: #0f2a5c; color: white; font-size: 18px; font-weight: 700; padding: 14px 18px; }
QLabel#hint { color: #64748b; }
QLabel#dialogTitle { font-size: 16px; font-weight: 700; color: #0f2a5c; }
QLabel#brand { font-size: 30px; font-weight: 800; color: #0f2a5c; padding-top: 8px; }
QLabel#error { background: #fee2e2; color: #991b1b; border-radius: 6px; padding: 8px; }
QLabel#info { background: #e0f2fe; color: #075985; border-radius: 6px; padding: 8px; }
QWidget#headerBar { background: #0f2a5c; }
QLabel#userLabel { color: #cbd5e1; padding-right: 8px; }
QPushButton#headerBtn { background: transparent; color: white; border: 1px solid #3b5998; }
QPushButton#headerBtn:hover { background: #1e4fa8; }
QScrollArea { border: none; background: transparent; }
QScrollArea > QWidget > QWidget { background: transparent; }
QScrollBar:vertical { width: 12px; background: #e2e8f0; border-radius: 6px; }
QScrollBar::handle:vertical { background: #94a3b8; border-radius: 6px; min-height: 40px; }
QScrollBar::handle:vertical:hover { background: #1e4fa8; }
QScrollBar::add-line, QScrollBar::sub-line { height: 0; }
"""


def apply_light_theme(app: QApplication) -> None:
    """Thème clair forcé : sinon le mode sombre de Windows rend le texte blanc sur fond blanc."""
    hints = app.styleHints()
    if hasattr(hints, "setColorScheme"):  # Qt 6.8 et plus
        hints.setColorScheme(Qt.ColorScheme.Light)
    app.setStyle("Fusion")
    pal = QPalette()
    colors = {
        QPalette.Window: "#f1f5f9", QPalette.WindowText: "#0f172a", QPalette.Base: "#ffffff",
        QPalette.AlternateBase: "#f8fafc", QPalette.Text: "#0f172a", QPalette.Button: "#ffffff",
        QPalette.ButtonText: "#0f172a", QPalette.Highlight: "#1e4fa8", QPalette.HighlightedText: "#ffffff",
        QPalette.ToolTipBase: "#ffffff", QPalette.ToolTipText: "#0f172a", QPalette.PlaceholderText: "#94a3b8",
        QPalette.BrightText: "#b91c1c", QPalette.Link: "#1e4fa8",
    }
    for role, color in colors.items():
        pal.setColor(role, QColor(color))
    for role in (QPalette.WindowText, QPalette.Text, QPalette.ButtonText):
        pal.setColor(QPalette.Disabled, role, QColor("#94a3b8"))
    app.setPalette(pal)
    app.setStyleSheet(STYLE)


def pil_to_pixmap(img: Image.Image) -> QPixmap:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    pix = QPixmap()
    pix.loadFromData(buf.getvalue(), "PNG")
    return pix


# ------------------------------------------------------------------ onglet émission
class IssueTab(QWidget):
    def __init__(self, service: IssuerService, on_issued):
        super().__init__()
        self.service = service
        self.on_issued = on_issued
        self.photo_path: str | None = None
        self.timer = QTimer(self, singleShot=True, interval=350)
        self.timer.timeout.connect(self.refresh_preview)

        root = QHBoxLayout(self)

        # Formulaire
        box = QGroupBox("Titulaire")
        form = QFormLayout(box)
        self.profil = QComboBox()
        for key, prof in PROFILES.items():
            self.profil.addItem(f"{prof.title_fr} – {prof.org}", key)
        self.modele = QComboBox()
        for name in TEMPLATES:
            self.modele.addItem(name.capitalize(), name)
        self.modele.setCurrentIndex(list(TEMPLATES).index(DEFAULT_TEMPLATE))
        self.card_id = QLabel()
        self.card_id.setStyleSheet("font-family: Consolas, monospace; font-weight: 700; color: #1e4fa8;")
        self.nom, self.prenom = QLineEdit(), QLineEdit()
        self.naiss = QDateEdit(QDate(2000, 1, 1), calendarPopup=True, displayFormat="dd/MM/yyyy")
        self.role = QLineEdit("Étudiant(e)")
        self.fonction, self.service_field = QLineEdit(), QLineEdit()
        self.validite = QSpinBox(minimum=1, maximum=60, value=12, suffix=" mois")
        self.photo_btn = QPushButton("Choisir une photo…")
        self.photo_label = QLabel("Aucune photo")
        self.photo_label.setObjectName("hint")

        form.addRow("Profil", self.profil)
        form.addRow("Modèle", self.modele)
        form.addRow("N° attribué", self.card_id)
        form.addRow("Nom", self.nom)
        form.addRow("Prénom(s)", self.prenom)
        form.addRow("Date de naissance", self.naiss)
        form.addRow("Statut", self.role)
        form.addRow("Fonction", self.fonction)
        form.addRow("Service", self.service_field)
        form.addRow("Validité", self.validite)
        form.addRow("Photo", self.photo_btn)
        form.addRow("", self.photo_label)

        self.issue_btn = QPushButton("Émettre et exporter le PDF", objectName="primary")
        self.issue_btn.clicked.connect(self.issue)
        left = QVBoxLayout()
        left.addWidget(box)
        left.addWidget(self.issue_btn)
        note = QLabel("L'aperçu est signé par une clé jetable : il n'a aucune valeur. "
                      "Seul le bouton « Émettre » signe avec la clé de l'établissement.")
        note.setWordWrap(True)
        note.setObjectName("hint")
        left.addWidget(note)
        left.addStretch()

        # Aperçu
        prev_box = QGroupBox("Aperçu en direct")
        pv = QVBoxLayout(prev_box)
        self.recto_label, self.verso_label = QLabel(alignment=Qt.AlignCenter), QLabel(alignment=Qt.AlignCenter)
        pv.addWidget(QLabel("Recto"))
        pv.addWidget(self.recto_label)
        pv.addWidget(QLabel("Verso"))
        pv.addWidget(self.verso_label)
        pv.addStretch()

        # Chaque colonne défile indépendamment : utile sur les petits écrans
        root.addWidget(self._scrollable(left), 2)
        prev_wrap = QVBoxLayout()
        prev_wrap.addWidget(prev_box)
        root.addWidget(self._scrollable(prev_wrap), 3)

        for w in (self.nom, self.prenom, self.role, self.fonction, self.service_field):
            w.textChanged.connect(self.schedule_preview)
        self.naiss.dateChanged.connect(self.schedule_preview)
        self.validite.valueChanged.connect(self.schedule_preview)
        self.modele.currentIndexChanged.connect(self.schedule_preview)
        self.profil.currentIndexChanged.connect(self.profil_changed)
        self.photo_btn.clicked.connect(self.choose_photo)
        self.profil_changed()

    @staticmethod
    def _scrollable(layout) -> QScrollArea:
        inner = QWidget()
        layout.setContentsMargins(0, 0, 18, 0)  # place pour la barre de défilement
        inner.setLayout(layout)
        area = QScrollArea(widgetResizable=True)
        area.setFrameShape(QFrame.NoFrame)
        area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        area.setWidget(inner)
        return area

    # --------------------------------------------------------------
    def profil_changed(self) -> None:
        entreprise = self.profil.currentData() == "entreprise"
        self.fonction.setEnabled(entreprise)
        self.service_field.setEnabled(entreprise)
        if self.role.text() in ("", "Étudiant(e)", "Employé(e)"):
            self.role.setText("Employé(e)" if entreprise else "Étudiant(e)")
        self.card_id.setText(self.service.next_card_id(self.profil.currentData()))
        self.schedule_preview()

    def choose_photo(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Photo d'identité", "", "Images (*.png *.jpg *.jpeg *.bmp *.webp)")
        if path:
            self.photo_path = path
            self.photo_label.setText(Path(path).name)
            self.schedule_preview()

    def schedule_preview(self) -> None:
        self.timer.start()

    def request(self) -> CardRequest:
        q = self.naiss.date()
        return CardRequest(profil=self.profil.currentData(), nom=self.nom.text(), prenom=self.prenom.text(),
                           naiss=date(q.year(), q.month(), q.day()), role=self.role.text(),
                           validite_mois=self.validite.value(), fonction=self.fonction.text(),
                           service=self.service_field.text(), modele=self.modele.currentData(),
                           photo_source=self.photo_path)

    def refresh_preview(self) -> None:
        req = self.request()
        req.nom = req.nom or "NOM"
        req.prenom = req.prenom or "Prénom"
        try:
            recto, verso = self.service.preview(req)
        except Exception as exc:  # photo illisible, etc. : l'aperçu ne doit jamais planter l'appli
            self.recto_label.setText(f"Aperçu indisponible : {exc}")
            return
        width = 520
        for label, img in ((self.recto_label, recto), (self.verso_label, verso)):
            label.setPixmap(pil_to_pixmap(img).scaledToWidth(width if img.width > img.height else 300,
                                                             Qt.SmoothTransformation))

    def issue(self) -> None:
        try:
            card = self.service.issue(self.request())
        except ValidationError as exc:
            QMessageBox.warning(self, "Données à corriger", str(exc))
            return
        except Exception as exc:
            QMessageBox.critical(self, "Erreur", f"Émission impossible : {exc}")
            return
        box = QMessageBox(self)
        box.setWindowTitle("Carte émise")
        box.setText(f"Carte {card.card_id} émise et signée.\n\nPDF : {Path(card.pdf_path).resolve()}")
        open_btn = box.addButton("Ouvrir le PDF", QMessageBox.AcceptRole)
        box.addButton("Fermer", QMessageBox.RejectRole)
        box.exec()
        if box.clickedButton() is open_btn:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(card.pdf_path).resolve())))
        for w in (self.nom, self.prenom, self.fonction, self.service_field):
            w.clear()
        self.photo_path = None
        self.photo_label.setText("Aucune photo")
        self.card_id.setText(self.service.next_card_id(self.profil.currentData()))
        self.on_issued()


# ------------------------------------------------------------------ onglet cartes émises
class CardsTab(QWidget):
    COLUMNS = ["N° de carte", "Nom", "Prénom", "Profil", "Émise le", "Expire le", "Statut"]

    def __init__(self, service: IssuerService):
        super().__init__()
        self.service = service
        lay = QVBoxLayout(self)

        top = QHBoxLayout()
        self.search = QLineEdit(placeholderText="Rechercher par numéro, nom ou prénom…")
        self.search.textChanged.connect(self.refresh)
        top.addWidget(self.search)
        lay.addLayout(top)

        self.table = QTableWidget(0, len(self.COLUMNS))
        self.table.setHorizontalHeaderLabels(self.COLUMNS)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        lay.addWidget(self.table)
        lay.addWidget(QLabel("Astuce : Ctrl+clic ou Maj+clic pour sélectionner plusieurs cartes à imprimer sur planches.",
                             objectName="hint"))

        actions = QHBoxLayout()
        self.sheets_btn = QPushButton("Planches A4 de la sélection")
        self.sheets_btn.clicked.connect(self.print_sheets)
        self.open_btn = QPushButton("Ouvrir le PDF")
        self.revoke_btn = QPushButton("Révoquer…", objectName="danger")
        self.audit_btn = QPushButton("Vérifier le journal d'audit")
        self.open_btn.clicked.connect(self.open_pdf)
        self.revoke_btn.clicked.connect(self.revoke)
        self.audit_btn.clicked.connect(self.check_audit)
        actions.addWidget(self.open_btn)
        actions.addWidget(self.sheets_btn)
        actions.addWidget(self.revoke_btn)
        self.export_btn = QPushButton("Exporter pour le vérificateur")
        self.export_btn.clicked.connect(self.export_verifier)
        actions.addStretch()
        actions.addWidget(self.export_btn)
        actions.addWidget(self.audit_btn)
        lay.addLayout(actions)
        self.rows: list[dict] = []
        self.refresh()

    def refresh(self) -> None:
        self.rows = self.service.list_cards(self.search.text())
        self.table.setRowCount(len(self.rows))
        today = date.today().isoformat()
        for r, row in enumerate(self.rows):
            statut = row["statut"]
            if statut == "ACTIVE" and row["exp"] < today:
                statut = "EXPIRÉE"
            values = [row["card_id"], row["nom"], row["prenom"], {"ecole": "École", "entreprise": "Entreprise"}.get(row["profil"], row["profil"]),
                      date.fromisoformat(row["emis"]).strftime("%d/%m/%Y"),
                      date.fromisoformat(row["exp"]).strftime("%d/%m/%Y"),
                      "RÉVOQUÉE" if statut == "REVOQUEE" else statut]
            for c, v in enumerate(values):
                item = QTableWidgetItem(v)
                if c == 6:
                    color = {"ACTIVE": "#15803d", "EXPIRÉE": "#c2410c"}.get(values[6], "#b91c1c")
                    item.setForeground(QColor(color))
                self.table.setItem(r, c, item)

    def selected(self) -> dict | None:
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            QMessageBox.information(self, "SecureID", "Sélectionne d'abord une carte dans la liste.")
            return None
        return self.rows[rows[0].row()]

    def print_sheets(self) -> None:
        rows = sorted(i.row() for i in self.table.selectionModel().selectedRows())
        if not rows:
            QMessageBox.information(self, "SecureID", "Sélectionne une ou plusieurs cartes (Ctrl+clic).")
            return
        cards = [self.rows[r] for r in rows]
        revoked = [c["card_id"] for c in cards if c["statut"] == "REVOQUEE"]
        if revoked:
            QMessageBox.warning(self, "SecureID", "Impossible d'imprimer des cartes révoquées : " + ", ".join(revoked))
            return
        from datetime import datetime
        from core.sheets import export_sheets
        try:
            faces = [self.service.render_existing(c["card_id"]) for c in cards]
            path, n = export_sheets(faces, OUT_DIR / f"planches_{datetime.now():%Y%m%d_%H%M%S}.pdf")
        except (ValueError, ValidationError) as exc:
            QMessageBox.warning(self, "SecureID", str(exc))
            return
        QMessageBox.information(self, "Planches A4", f"{len(cards)} carte(s) sur {n} feuille(s) recto-verso.\n\n"
                                "Imprime à 100 % (taille réelle), en recto-verso sur le bord long.")
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path.resolve())))

    def open_pdf(self) -> None:
        row = self.selected()
        if row and row["pdf"] and Path(row["pdf"]).exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(row["pdf"]).resolve())))
        elif row:
            QMessageBox.warning(self, "SecureID", "Le fichier PDF de cette carte est introuvable.")

    def revoke(self) -> None:
        row = self.selected()
        if not row:
            return
        motif, ok = QInputDialog.getText(self, "Révoquer la carte",
                                         f"Motif de révocation de {row['card_id']} ({row['prenom']} {row['nom']}) :")
        if not ok:
            return
        try:
            self.service.revoke(row["card_id"], motif)
        except ValidationError as exc:
            QMessageBox.warning(self, "SecureID", str(exc))
            return
        self.export_verifier(silent=True)  # la liste de révocation locale reste à jour
        self.refresh()

    def apply_rights(self, is_admin: bool) -> None:
        """Révoquer, exporter et contrôler le journal sont réservés aux administrateurs."""
        for btn in (self.revoke_btn, self.export_btn, self.audit_btn):
            btn.setEnabled(is_admin)
            btn.setToolTip("" if is_admin else "Réservé aux administrateurs")

    def export_verifier(self, silent: bool = False) -> None:
        """Met à jour verif/ : clé publique + liste de révocation signée, pour l'appli de vérification."""
        try:
            path = self.service.export_for_verifier(TRUST_DIR)
        except Exception as exc:
            QMessageBox.critical(self, "SecureID", f"Export impossible : {exc}")
            return
        if not silent:
            QMessageBox.information(self, "Export pour le vérificateur",
                                    f"Dossier de confiance mis à jour :\n{path.parent.resolve()}\n\n"
                                    "Copie ce dossier « verif » sur les postes de contrôle.")

    def check_audit(self) -> None:
        report = self.service.check_audit()
        if report.ok:
            QMessageBox.information(self, "Journal d'audit", f"Journal intact : {report.entries} entrées vérifiées.")
        else:
            QMessageBox.critical(self, "Journal d'audit",
                                 f"ALERTE : journal altéré à l'entrée n°{report.first_bad_id}.\n{report.reason}")


# ------------------------------------------------------------------ fenêtre principale
class MainWindow(QMainWindow):
    def __init__(self, service: IssuerService, auth: AuthService | None = None,
                 user: CurrentUser | None = None, on_logout=None):
        super().__init__()
        self.service, self.auth, self.user, self.on_logout = service, auth, user, on_logout
        self.logging_out = False
        self.setWindowTitle("SecureID – Émission de cartes")
        self.resize(1280, 860)
        central = QWidget()
        lay = QVBoxLayout(central)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        bar = QWidget(objectName="headerBar")
        bl = QHBoxLayout(bar)
        bl.setContentsMargins(0, 0, 14, 0)
        bl.addWidget(QLabel("SecureID  ·  Émission de cartes sécurisées", objectName="header"))
        bl.addStretch()
        if user:
            bl.addWidget(QLabel(f"Connecté : {user.label}", objectName="userLabel"))
            pwd_btn = QPushButton("Changer mon mot de passe", objectName="headerBtn")
            out_btn = QPushButton("Se déconnecter", objectName="headerBtn")
            pwd_btn.clicked.connect(self.change_password)
            out_btn.clicked.connect(lambda: self.logout("manuelle"))
            bl.addWidget(pwd_btn)
            bl.addWidget(out_btn)
        lay.addWidget(bar)

        tabs = QTabWidget()
        self.cards_tab = CardsTab(service)
        self.issue_tab = IssueTab(service, on_issued=self.cards_tab.refresh)
        from apps.issuer.batch_tab import BatchTab
        self.batch_tab = BatchTab(service, OUT_DIR, on_issued=self.cards_tab.refresh)
        tabs.addTab(self.issue_tab, "Émettre une carte")
        batch_scroll = QScrollArea(widgetResizable=True)
        batch_scroll.setFrameShape(QFrame.NoFrame)
        batch_scroll.setWidget(self.batch_tab)
        tabs.addTab(batch_scroll, "Émission en masse")
        tabs.addTab(self.cards_tab, "Cartes émises")
        is_admin = user.is_admin if user else True
        self.cards_tab.apply_rights(is_admin)
        if user and is_admin and auth:
            from apps.issuer.operators_tab import OperatorsTab
            tabs.addTab(OperatorsTab(auth, user), "Opérateurs")
        lay.addWidget(tabs)
        self.setCentralWidget(central)
        who = user.login if user else service.operateur
        self.statusBar().showMessage(f"Opérateur : {who}   ·   Clé : {service.kid}   ·   "
                                     f"Déconnexion automatique après {INACTIVITY_MIN} min d'inactivité")

    def change_password(self) -> None:
        from apps.issuer.dialogs import ChangePasswordDialog
        ChangePasswordDialog(self.auth, self.user).exec()

    def logout(self, reason: str) -> None:
        if self.logging_out:
            return
        self.logging_out = True
        if self.on_logout:
            self.on_logout(reason)

    def closeEvent(self, event) -> None:
        # Fermer la fenêtre = se déconnecter et quitter l'application
        if not self.logging_out and self.on_logout:
            self.logging_out = True
            self.on_logout("fermeture", quit_app=True)
        super().closeEvent(event)


INACTIVITY_MIN = 10


class InactivityWatcher(QObject):
    """Déconnecte l'opérateur après une période sans clavier ni souris."""

    EVENTS = {QEvent.KeyPress, QEvent.MouseButtonPress, QEvent.MouseMove, QEvent.Wheel}

    def __init__(self, minutes: int, on_timeout):
        super().__init__()
        self.timer = QTimer(self, singleShot=True, interval=minutes * 60 * 1000)
        self.timer.timeout.connect(on_timeout)

    def eventFilter(self, obj, event) -> bool:
        if event.type() in self.EVENTS and self.timer.isActive():
            self.timer.start()
        return False


class SessionController:
    """Enchaîne : connexion -> fenêtre principale -> déconnexion -> connexion..."""

    def __init__(self, app: QApplication, service: IssuerService, auth: AuthService):
        self.app, self.service, self.auth = app, service, auth
        self.window: MainWindow | None = None
        self.user: CurrentUser | None = None
        self.watcher = InactivityWatcher(INACTIVITY_MIN, lambda: self.end_session("inactivité"))
        app.installEventFilter(self.watcher)

    def start(self, message: str = "") -> None:
        from apps.issuer.dialogs import AccountForm, LoginDialog
        if not self.auth.has_operators():
            first = AccountForm(self.auth, "Créer le premier administrateur",
                                "Aucun compte n'existe encore. Crée le compte administrateur : il pourra ensuite "
                                "créer les comptes des opérateurs.", fixed_role="admin")
            if first.exec() != QDialog.Accepted:
                self.app.quit()
                return
            message = "Compte administrateur créé. Connecte-toi pour continuer."
        login = LoginDialog(self.auth, message)
        if login.exec() != QDialog.Accepted:
            self.app.quit()
            return
        self.user = login.user
        self.service.operateur = self.user.login
        self.window = MainWindow(self.service, self.auth, self.user, self.end_session)
        screen = self.app.primaryScreen().availableGeometry()
        if screen.width() < 1300 or screen.height() < 900:
            self.window.showMaximized()
        else:
            self.window.show()
        self.watcher.timer.start()

    def end_session(self, reason: str, quit_app: bool = False) -> None:
        if self.user is None:
            return
        self.watcher.timer.stop()
        self.auth.logout(self.user, reason)
        self.user = None
        window, self.window = self.window, None
        if window is not None:
            window.logging_out = True
            window.close()
            window.deleteLater()
        if quit_app:
            self.app.quit()
            return
        msg = ("Session fermée après 10 minutes d'inactivité." if reason == "inactivité"
               else "Tu es déconnecté.")
        QTimer.singleShot(0, lambda: self.start(msg))


def main() -> None:
    app = QApplication(sys.argv)
    apply_light_theme(app)
    app.setQuitOnLastWindowClosed(False)  # on gère nous-mêmes la fin (retour à l'écran de connexion)
    from apps.issuer.dialogs import UnlockKeyDialog
    unlock = UnlockKeyDialog(KEYS_DIR / f"{KID}_private.pem", KID)
    if unlock.exec() != QDialog.Accepted:
        sys.exit(0)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    Session = init_db(get_engine(DATA_DIR / "secureid.db"))
    service = IssuerService(Session, unlock.private_key, KID, "poste", DATA_DIR, OUT_DIR)
    controller = SessionController(app, service, AuthService(Session))
    QTimer.singleShot(0, controller.start)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

"""Application d'émission SecureID (PySide6).

Lancer depuis la racine du projet :  python -m apps.issuer
"""

import io
import sys
from datetime import date
from pathlib import Path

from PIL import Image
from PySide6.QtCore import QDate, Qt, QTimer, QUrl
from PySide6.QtGui import QColor, QDesktopServices, QPalette, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QComboBox, QDateEdit, QDialog, QDialogButtonBox, QFileDialog,
    QFormLayout, QFrame, QGroupBox, QScrollArea, QHBoxLayout, QHeaderView, QInputDialog, QLabel, QLineEdit, QMainWindow,
    QMessageBox, QPushButton, QSpinBox, QTableWidget, QTableWidgetItem, QTabWidget, QVBoxLayout, QWidget,
)

from core import crypto
from core.issuer_service import CardRequest, IssuerService, ValidationError
from core.render import PROFILES
from core.templates import DEFAULT_TEMPLATE, TEMPLATES
from db.database import get_engine, init_db

KID = "sid2026"
KEYS_DIR = Path("keys")
DATA_DIR = Path("data")
OUT_DIR = Path("sortie")

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


# ------------------------------------------------------------------ déverrouillage
class UnlockDialog(QDialog):
    """Demande l'opérateur et le mot de passe de la clé ; crée la clé au premier lancement."""

    def __init__(self, priv_path: Path):
        super().__init__()
        self.priv_path = priv_path
        self.new_key = not priv_path.exists()
        self.private_key = None
        self.setWindowTitle("SecureID – Déverrouillage")
        self.setMinimumWidth(420)

        lay = QVBoxLayout(self)
        intro = ("Première utilisation : choisis le mot de passe qui protégera la clé de signature "
                 "(12 caractères minimum). Il n'est enregistré nulle part : ne le perds pas."
                 if self.new_key else "Saisis le mot de passe de la clé de signature pour émettre des cartes.")
        hint = QLabel(intro)
        hint.setWordWrap(True)
        hint.setObjectName("hint")
        lay.addWidget(hint)

        form = QFormLayout()
        self.operator = QLineEdit()
        self.operator.setPlaceholderText("ex. e.priso")
        self.password = QLineEdit(echoMode=QLineEdit.Password)
        form.addRow("Opérateur", self.operator)
        form.addRow("Mot de passe", self.password)
        if self.new_key:
            self.confirm = QLineEdit(echoMode=QLineEdit.Password)
            form.addRow("Confirmation", self.confirm)
        lay.addLayout(form)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("Créer la clé" if self.new_key else "Déverrouiller")
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)

    def _accept(self) -> None:
        op, pwd = self.operator.text().strip(), self.password.text()
        if not op:
            QMessageBox.warning(self, "SecureID", "Indique ton nom d'opérateur.")
            return
        try:
            if self.new_key:
                if pwd != self.confirm.text():
                    raise ValueError("Les deux mots de passe ne correspondent pas.")
                crypto.generate_keypair(KID, pwd, self.priv_path.parent)
            self.private_key = crypto.load_private_key(self.priv_path, pwd)
        except (ValueError, TypeError) as exc:
            msg = str(exc) if self.new_key else "Mot de passe incorrect."
            QMessageBox.warning(self, "SecureID", msg)
            self.password.clear()
            return
        self.accept()


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
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        lay.addWidget(self.table)

        actions = QHBoxLayout()
        self.open_btn = QPushButton("Ouvrir le PDF")
        self.revoke_btn = QPushButton("Révoquer…", objectName="danger")
        self.audit_btn = QPushButton("Vérifier le journal d'audit")
        self.open_btn.clicked.connect(self.open_pdf)
        self.revoke_btn.clicked.connect(self.revoke)
        self.audit_btn.clicked.connect(self.check_audit)
        actions.addWidget(self.open_btn)
        actions.addWidget(self.revoke_btn)
        actions.addStretch()
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
        self.refresh()

    def check_audit(self) -> None:
        report = self.service.check_audit()
        if report.ok:
            QMessageBox.information(self, "Journal d'audit", f"Journal intact : {report.entries} entrées vérifiées.")
        else:
            QMessageBox.critical(self, "Journal d'audit",
                                 f"ALERTE : journal altéré à l'entrée n°{report.first_bad_id}.\n{report.reason}")


# ------------------------------------------------------------------ fenêtre principale
class MainWindow(QMainWindow):
    def __init__(self, service: IssuerService):
        super().__init__()
        self.setWindowTitle("SecureID – Émission de cartes")
        self.resize(1280, 860)
        central = QWidget()
        lay = QVBoxLayout(central)
        lay.setContentsMargins(0, 0, 0, 0)
        header = QLabel("SecureID  ·  Émission de cartes sécurisées", objectName="header")
        lay.addWidget(header)

        tabs = QTabWidget()
        self.cards_tab = CardsTab(service)
        self.issue_tab = IssueTab(service, on_issued=self.cards_tab.refresh)
        tabs.addTab(self.issue_tab, "Émettre une carte")
        tabs.addTab(self.cards_tab, "Cartes émises")
        lay.addWidget(tabs)
        self.setCentralWidget(central)
        self.statusBar().showMessage(f"Opérateur : {service.operateur}   ·   Clé : {service.kid}")


def main() -> None:
    app = QApplication(sys.argv)
    apply_light_theme(app)
    dialog = UnlockDialog(KEYS_DIR / f"{KID}_private.pem")
    if dialog.exec() != QDialog.Accepted:
        sys.exit(0)
    DATA_DIR.mkdir(exist_ok=True)
    Session = init_db(get_engine(DATA_DIR / "secureid.db"))
    service = IssuerService(Session, dialog.private_key, KID, dialog.operator.text().strip(), DATA_DIR, OUT_DIR)
    window = MainWindow(service)
    screen = app.primaryScreen().availableGeometry()
    if screen.width() < 1300 or screen.height() < 900:
        window.showMaximized()  # petit écran : on prend toute la place disponible
    else:
        window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

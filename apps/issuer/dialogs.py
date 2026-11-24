"""Fenêtres de dialogue : déverrouillage du poste, premier administrateur, connexion, comptes."""

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QFormLayout, QLabel, QLineEdit, QMessageBox, QVBoxLayout,
)

from core import crypto
from core.auth import ROLES, AuthError, AuthService, CurrentUser


def _hint(text: str) -> QLabel:
    label = QLabel(text)
    label.setWordWrap(True)
    label.setObjectName("hint")
    return label


def _password() -> QLineEdit:
    return QLineEdit(echoMode=QLineEdit.Password)


class UnlockKeyDialog(QDialog):
    """Déverrouillage du poste : le responsable saisit le mot de passe de la clé de signature."""

    def __init__(self, priv_path: Path, kid: str):
        super().__init__()
        self.priv_path, self.kid = priv_path, kid
        self.new_key = not priv_path.exists()
        self.private_key = None
        self.setWindowTitle("SecureID – Déverrouillage du poste")
        self.setMinimumWidth(460)

        lay = QVBoxLayout(self)
        title = QLabel("Clé de signature de l'établissement", objectName="dialogTitle")
        lay.addWidget(title)
        lay.addWidget(_hint(
            "Première mise en service : choisis le mot de passe qui protège la clé de signature "
            "(12 caractères minimum). Il n'est stocké nulle part : conserve-le en lieu sûr."
            if self.new_key else
            "À faire par le responsable du poste, une fois au démarrage. "
            "Les opérateurs se connectent ensuite avec leur propre compte."))
        form = QFormLayout()
        self.password = _password()
        form.addRow("Mot de passe de la clé", self.password)
        if self.new_key:
            self.confirm = _password()
            form.addRow("Confirmation", self.confirm)
        lay.addLayout(form)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("Créer la clé" if self.new_key else "Déverrouiller")
        buttons.button(QDialogButtonBox.Ok).setObjectName("primary")
        buttons.button(QDialogButtonBox.Cancel).setText("Quitter")
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)

    def _accept(self) -> None:
        pwd = self.password.text()
        try:
            if self.new_key:
                if pwd != self.confirm.text():
                    raise ValueError("Les deux mots de passe ne correspondent pas.")
                crypto.generate_keypair(self.kid, pwd, self.priv_path.parent)
            self.private_key = crypto.load_private_key(self.priv_path, pwd)
        except (ValueError, TypeError) as exc:
            QMessageBox.warning(self, "SecureID", str(exc) if self.new_key else "Mot de passe de la clé incorrect.")
            self.password.clear()
            return
        self.accept()


class AccountForm(QDialog):
    """Formulaire de création de compte (premier administrateur ou nouvel opérateur)."""

    def __init__(self, auth: AuthService, title: str, intro: str, fixed_role: str | None = None,
                 created_by: str = "systeme"):
        super().__init__()
        self.auth, self.fixed_role, self.created_by = auth, fixed_role, created_by
        self.user: CurrentUser | None = None
        self.setWindowTitle(f"SecureID – {title}")
        self.setMinimumWidth(480)

        lay = QVBoxLayout(self)
        lay.addWidget(QLabel(title, objectName="dialogTitle"))
        lay.addWidget(_hint(intro))
        form = QFormLayout()
        self.login = QLineEdit(placeholderText="ex. e.priso")
        self.nom = QLineEdit(placeholderText="ex. Emile PRISO")
        self.role = QComboBox()
        for key, label in ROLES.items():
            self.role.addItem(label, key)
        if fixed_role:
            self.role.setCurrentIndex(self.role.findData(fixed_role))
            self.role.setEnabled(False)
        self.password, self.confirm = _password(), _password()
        form.addRow("Identifiant", self.login)
        form.addRow("Nom complet", self.nom)
        form.addRow("Rôle", self.role)
        form.addRow("Mot de passe", self.password)
        form.addRow("Confirmation", self.confirm)
        lay.addLayout(form)
        lay.addWidget(_hint("Mot de passe : 12 caractères minimum, avec des lettres et au moins un chiffre, "
                            "sans l'identifiant."))
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("Créer le compte")
        buttons.button(QDialogButtonBox.Ok).setObjectName("primary")
        buttons.button(QDialogButtonBox.Cancel).setText("Annuler")
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)

    def _accept(self) -> None:
        if self.password.text() != self.confirm.text():
            QMessageBox.warning(self, "SecureID", "Les deux mots de passe ne correspondent pas.")
            return
        try:
            self.user = self.auth.create_operator(self.login.text(), self.password.text(),
                                                  self.role.currentData(), self.nom.text(), self.created_by)
        except AuthError as exc:
            QMessageBox.warning(self, "SecureID", str(exc))
            return
        self.accept()


class LoginDialog(QDialog):
    """Écran de connexion des opérateurs."""

    def __init__(self, auth: AuthService, message: str = ""):
        super().__init__()
        self.auth = auth
        self.user: CurrentUser | None = None
        self.setWindowTitle("SecureID – Connexion")
        self.setMinimumWidth(420)

        lay = QVBoxLayout(self)
        brand = QLabel("SecureID", objectName="brand")
        brand.setAlignment(Qt.AlignCenter)
        lay.addWidget(brand)
        sub = _hint("Émission de cartes sécurisées · Connexion opérateur")
        sub.setAlignment(Qt.AlignCenter)
        lay.addWidget(sub)
        self.info = QLabel(message, objectName="info")
        self.info.setWordWrap(True)
        self.info.setVisible(bool(message))
        lay.addWidget(self.info)

        form = QFormLayout()
        self.login = QLineEdit(placeholderText="Identifiant")
        self.password = _password()
        self.password.setPlaceholderText("Mot de passe")
        form.addRow("Identifiant", self.login)
        form.addRow("Mot de passe", self.password)
        lay.addLayout(form)
        self.error = QLabel("", objectName="error")
        self.error.setWordWrap(True)
        self.error.setVisible(False)
        lay.addWidget(self.error)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("Se connecter")
        buttons.button(QDialogButtonBox.Ok).setObjectName("primary")
        buttons.button(QDialogButtonBox.Cancel).setText("Quitter")
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)
        self.login.setFocus()

    def _accept(self) -> None:
        try:
            self.user = self.auth.authenticate(self.login.text(), self.password.text())
        except AuthError as exc:
            self.error.setText(str(exc))
            self.error.setVisible(True)
            self.info.setVisible(False)
            self.password.clear()
            self.password.setFocus()
            return
        self.accept()


class ChangePasswordDialog(QDialog):
    def __init__(self, auth: AuthService, user: CurrentUser):
        super().__init__()
        self.auth, self.user = auth, user
        self.setWindowTitle("SecureID – Changer mon mot de passe")
        self.setMinimumWidth(420)
        lay = QVBoxLayout(self)
        form = QFormLayout()
        self.old, self.new, self.confirm = _password(), _password(), _password()
        form.addRow("Mot de passe actuel", self.old)
        form.addRow("Nouveau mot de passe", self.new)
        form.addRow("Confirmation", self.confirm)
        lay.addLayout(form)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("Enregistrer")
        buttons.button(QDialogButtonBox.Ok).setObjectName("primary")
        buttons.button(QDialogButtonBox.Cancel).setText("Annuler")
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)

    def _accept(self) -> None:
        if self.new.text() != self.confirm.text():
            QMessageBox.warning(self, "SecureID", "Les deux nouveaux mots de passe ne correspondent pas.")
            return
        try:
            self.auth.change_own_password(self.user, self.old.text(), self.new.text())
        except AuthError as exc:
            QMessageBox.warning(self, "SecureID", str(exc))
            return
        QMessageBox.information(self, "SecureID", "Mot de passe modifié.")
        self.accept()

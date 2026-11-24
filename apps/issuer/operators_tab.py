"""Onglet « Opérateurs » (administrateurs uniquement) : comptes, activation, réinitialisation."""

from datetime import datetime

from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView, QHBoxLayout, QHeaderView, QInputDialog, QLineEdit, QMessageBox, QPushButton,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from apps.issuer.dialogs import AccountForm
from core.auth import ROLES, AuthError, AuthService, CurrentUser


class OperatorsTab(QWidget):
    COLUMNS = ["Identifiant", "Nom complet", "Rôle", "État", "Dernière connexion"]

    def __init__(self, auth: AuthService, user: CurrentUser):
        super().__init__()
        self.auth, self.user = auth, user
        lay = QVBoxLayout(self)
        self.table = QTableWidget(0, len(self.COLUMNS))
        self.table.setHorizontalHeaderLabels(self.COLUMNS)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        lay.addWidget(self.table)

        actions = QHBoxLayout()
        new_btn = QPushButton("Nouveau compte…", objectName="primary")
        toggle_btn = QPushButton("Activer / désactiver")
        reset_btn = QPushButton("Réinitialiser le mot de passe…")
        new_btn.clicked.connect(self.new_account)
        toggle_btn.clicked.connect(self.toggle)
        reset_btn.clicked.connect(self.reset)
        for b in (new_btn, toggle_btn, reset_btn):
            actions.addWidget(b)
        actions.addStretch()
        lay.addLayout(actions)
        self.rows: list[dict] = []
        self.refresh()

    def refresh(self) -> None:
        self.rows = self.auth.list_operators()
        self.table.setRowCount(len(self.rows))
        for r, row in enumerate(self.rows):
            etat = "Verrouillé" if row["verrouille"] else ("Actif" if row["actif"] else "Désactivé")
            derniere = (datetime.fromisoformat(row["derniere"]).astimezone().strftime("%d/%m/%Y %H:%M")
                        if row["derniere"] else "Jamais")
            for c, v in enumerate([row["login"], row["nom"], ROLES[row["role"]], etat, derniere]):
                item = QTableWidgetItem(v)
                if c == 3:
                    item.setForeground(QColor({"Actif": "#15803d", "Verrouillé": "#c2410c"}.get(etat, "#b91c1c")))
                self.table.setItem(r, c, item)

    def _selected(self) -> dict | None:
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            QMessageBox.information(self, "SecureID", "Sélectionne d'abord un compte.")
            return None
        return self.rows[rows[0].row()]

    def new_account(self) -> None:
        dlg = AccountForm(self.auth, "Nouveau compte", "Crée un compte pour un opérateur ou un administrateur.",
                          created_by=self.user.login)
        if dlg.exec():
            self.refresh()

    def toggle(self) -> None:
        row = self._selected()
        if not row:
            return
        try:
            self.auth.set_active(row["login"], not row["actif"], self.user)
        except AuthError as exc:
            QMessageBox.warning(self, "SecureID", str(exc))
        self.refresh()

    def reset(self) -> None:
        row = self._selected()
        if not row:
            return
        pwd, ok = QInputDialog.getText(self, "Réinitialiser le mot de passe",
                                       f"Nouveau mot de passe provisoire pour {row['login']} :", QLineEdit.Password)
        if not ok:
            return
        try:
            self.auth.reset_password(row["login"], pwd, self.user)
        except AuthError as exc:
            QMessageBox.warning(self, "SecureID", str(exc))
            return
        QMessageBox.information(self, "SecureID", f"Mot de passe de {row['login']} réinitialisé. "
                                                  "Communique-le-lui en main propre.")
        self.refresh()

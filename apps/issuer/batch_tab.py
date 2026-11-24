"""Onglet « Émission en masse » : fichier CSV/Excel + dossier de photos -> cartes + planches A4."""

from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QColor, QDesktopServices
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QComboBox, QFileDialog, QFormLayout, QGroupBox, QHBoxLayout, QHeaderView,
    QLabel, QMessageBox, QProgressDialog, QPushButton, QSpinBox, QTableWidget, QTableWidgetItem, QVBoxLayout,
    QWidget,
)

from core import batch
from core.issuer_service import IssuerService
from core.render import PROFILES
from core.sheets import export_sheets
from core.templates import DEFAULT_TEMPLATE, TEMPLATES


class BatchTab(QWidget):
    COLUMNS = ["Ligne", "Nom", "Prénom", "Profil", "Résultat"]

    def __init__(self, service: IssuerService, out_dir: Path, on_issued):
        super().__init__()
        self.service, self.out_dir, self.on_issued = service, Path(out_dir), on_issued
        self.file: Path | None = None
        self.photos: Path | None = None
        self.report: batch.BatchReport | None = None
        lay = QVBoxLayout(self)

        # 1. Fichier et photos
        box = QGroupBox("1. Fichier et photos")
        form = QFormLayout(box)
        tpl_btn = QPushButton("Télécharger le modèle CSV…")
        tpl_btn.clicked.connect(self.save_template)
        file_row = QHBoxLayout()
        self.file_btn = QPushButton("Choisir le fichier (CSV ou Excel)…")
        self.file_btn.clicked.connect(self.choose_file)
        self.file_label = QLabel("Aucun fichier", objectName="hint")
        file_row.addWidget(self.file_btn)
        file_row.addWidget(self.file_label, 1)
        photo_row = QHBoxLayout()
        self.photo_btn = QPushButton("Choisir le dossier des photos…")
        self.photo_btn.clicked.connect(self.choose_photos)
        self.photo_label = QLabel("Aucun dossier", objectName="hint")
        photo_row.addWidget(self.photo_btn)
        photo_row.addWidget(self.photo_label, 1)
        self.profil = QComboBox()
        for key, prof in PROFILES.items():
            self.profil.addItem(f"{prof.title_fr} – {prof.org}", key)
        self.modele = QComboBox()
        for name in TEMPLATES:
            self.modele.addItem(name.capitalize(), name)
        self.modele.setCurrentIndex(list(TEMPLATES).index(DEFAULT_TEMPLATE))
        self.validite = QSpinBox(minimum=1, maximum=60, value=12, suffix=" mois")
        form.addRow("Modèle de fichier", tpl_btn)
        form.addRow("Fichier", file_row)
        form.addRow("Photos", photo_row)
        form.addRow("Profil par défaut", self.profil)
        form.addRow("Modèle de carte", self.modele)
        form.addRow("Validité par défaut", self.validite)
        lay.addWidget(box)

        # 2. Contrôle
        check_box = QGroupBox("2. Contrôle des lignes (rien n'est émis à cette étape)")
        cl = QVBoxLayout(check_box)
        top = QHBoxLayout()
        self.analyse_btn = QPushButton("Analyser le fichier")
        self.analyse_btn.clicked.connect(self.analyse)
        self.summary = QLabel("", objectName="hint")
        top.addWidget(self.analyse_btn)
        top.addWidget(self.summary, 1)
        cl.addLayout(top)
        self.table = QTableWidget(0, len(self.COLUMNS))
        self.table.setHorizontalHeaderLabels(self.COLUMNS)
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(4, QHeaderView.Stretch)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.setMinimumHeight(220)
        cl.addWidget(self.table)
        lay.addWidget(check_box, 1)

        # 3. Émission
        self.issue_btn = QPushButton("Émettre les cartes valides", objectName="primary")
        self.issue_btn.setEnabled(False)
        self.issue_btn.clicked.connect(self.issue)
        lay.addWidget(self.issue_btn)

    # ------------------------------------------------------------
    def save_template(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Enregistrer le modèle", "modele_emission.csv", "CSV (*.csv)")
        if path:
            batch.write_template(path)
            QMessageBox.information(self, "Modèle CSV", "Modèle enregistré. Ouvre-le dans Excel, remplis une ligne par "
                                    "personne et indique dans « photo » le nom du fichier image.")

    def choose_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Fichier des titulaires", "", "Tableurs (*.csv *.xlsx)")
        if path:
            self.file = Path(path)
            self.file_label.setText(self.file.name)
            self._reset()

    def choose_photos(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Dossier des photos")
        if path:
            self.photos = Path(path)
            self.photo_label.setText(str(self.photos))
            self._reset()

    def _reset(self) -> None:
        self.report = None
        self.table.setRowCount(0)
        self.summary.setText("")
        self.issue_btn.setEnabled(False)
        self.issue_btn.setText("Émettre les cartes valides")

    def analyse(self) -> None:
        if not (self.file and self.photos):
            QMessageBox.information(self, "SecureID", "Choisis d'abord le fichier et le dossier des photos.")
            return
        try:
            self.report = batch.analyse(self.file, self.photos, self.profil.currentData(),
                                        self.validite.value(), self.modele.currentData())
        except (batch.BatchFileError, OSError) as exc:
            QMessageBox.warning(self, "Fichier refusé", str(exc))
            return
        self._fill_table()
        n_ok, n_err = len(self.report.valid), len(self.report.invalid)
        self.summary.setText(f"{n_ok} ligne(s) valide(s), {n_err} ligne(s) en erreur."
                             + (" Corrige le fichier puis relance l'analyse, ou émets seulement les lignes valides."
                                if n_err else ""))
        self.issue_btn.setEnabled(n_ok > 0)
        self.issue_btn.setText(f"Émettre les {n_ok} carte(s) valide(s)")

    def _fill_table(self) -> None:
        lines = self.report.lines
        self.table.setRowCount(len(lines))
        for r, ln in enumerate(lines):
            if ln.card_id:
                result, color = f"Émise : {ln.card_id}", "#15803d"
            elif ln.error:
                result, color = ln.error, "#b91c1c"
            else:
                result, color = "Prête à émettre", "#1e4fa8"
            profil = ln.request.profil if ln.request else str(ln.raw.get("profil", ""))
            for c, v in enumerate([str(ln.line), str(ln.raw.get("nom", "")), str(ln.raw.get("prenom", "")),
                                   PROFILES[profil].title_fr if profil in PROFILES else profil, result]):
                item = QTableWidgetItem(v)
                if c == 4:
                    item.setForeground(QColor(color))
                self.table.setItem(r, c, item)

    def issue(self) -> None:
        valid = self.report.valid
        if QMessageBox.question(self, "Confirmer l'émission",
                                f"Émettre et signer {len(valid)} carte(s) ? Chaque émission est définitive "
                                "et inscrite au journal d'audit.") != QMessageBox.Yes:
            return
        progress = QProgressDialog("Émission des cartes…", None, 0, len(valid), self)
        progress.setWindowModality(Qt.WindowModal)
        progress.setMinimumDuration(0)

        def step(i, total):
            progress.setValue(i)
            progress.setLabelText(f"Émission des cartes… {i}/{total}")
            QApplication.processEvents()

        issued = batch.issue_valid(self.service, self.report, on_progress=step)
        progress.close()

        folder = self.out_dir / f"lot_{datetime.now():%Y%m%d_%H%M%S}"
        report_path = batch.write_report(self.report, folder / "rapport.csv")
        sheets_path, n_sheets = (export_sheets([(r, v) for _, r, v in issued], folder / "planches_A4.pdf",
                                               title=f"Lot {folder.name}") if issued else (None, 0))
        self._fill_table()
        self.issue_btn.setEnabled(False)
        self.on_issued()

        box = QMessageBox(self)
        box.setWindowTitle("Lot terminé")
        box.setText(f"{len(issued)} carte(s) émise(s) sur {len(self.report.lines)} ligne(s).\n"
                    f"Planches A4 : {n_sheets} feuille(s) recto-verso.\n\nDossier : {folder.resolve()}")
        open_btn = box.addButton("Ouvrir le dossier", QMessageBox.AcceptRole)
        box.addButton("Fermer", QMessageBox.RejectRole)
        box.exec()
        if box.clickedButton() is open_btn:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder.resolve())))
        del report_path, sheets_path

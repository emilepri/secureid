"""Application de vérification SecureID (PySide6 + OpenCV), hors ligne.

Lancer depuis la racine du projet :  python -m apps.verifier
Le dossier de confiance « verif/ » est préparé par l'application d'émission
(bouton « Exporter pour le vérificateur »).
"""

import sys
import time
from datetime import date
from pathlib import Path

import cv2
from PIL import Image
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QApplication, QFileDialog, QFormLayout, QFrame, QGroupBox, QHBoxLayout, QLabel, QListWidget,
    QListWidgetItem, QMainWindow, QPushButton, QScrollArea, QSpinBox, QVBoxLayout, QWidget,
)

from apps.issuer.main import apply_light_theme, pil_to_pixmap
from core.qr_reader import decode_qr
from core.verifier_service import VerifierService, Verdict

TRUST_DIR = Path("verif")
PHOTOS_DIR = Path("data") / "photos"  # photos de référence, si le vérificateur est sur le poste d'émission
SCAN_EVERY_N_FRAMES = 4
SAME_CARD_DELAY = 3.0  # secondes avant de réafficher la même carte


def _fr(iso: str | None) -> str:
    try:
        return date.fromisoformat(iso).strftime("%d/%m/%Y")
    except (TypeError, ValueError):
        return "—"


class VerifierWindow(QMainWindow):
    def __init__(self, service: VerifierService, warnings: list[str]):
        super().__init__()
        self.service = service
        self.capture: cv2.VideoCapture | None = None
        self.frame_count = 0
        self.last_token, self.last_time = None, 0.0
        self.timer = QTimer(self, interval=30)
        self.timer.timeout.connect(self.next_frame)

        self.setWindowTitle("SecureID – Vérification de cartes")
        self.resize(1200, 800)
        central = QWidget()
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(QLabel("SecureID  ·  Vérification de cartes", objectName="header"))
        body = QHBoxLayout()
        body.setContentsMargins(10, 10, 10, 10)
        root.addLayout(body)

        # ---- Colonne gauche : caméra / image
        left_box = QGroupBox("Lecture du QR code")
        left = QVBoxLayout(left_box)
        self.view = QLabel("Caméra arrêtée.\nDémarre la caméra ou ouvre une image de carte.", alignment=Qt.AlignCenter)
        self.view.setMinimumSize(560, 420)
        self.view.setStyleSheet("background: #0f172a; color: #cbd5e1; border-radius: 8px;")
        left.addWidget(self.view)
        controls = QHBoxLayout()
        self.cam_btn = QPushButton("Démarrer la caméra", objectName="primary")
        self.cam_btn.clicked.connect(self.toggle_camera)
        self.cam_index = QSpinBox(minimum=0, maximum=5, prefix="Caméra n° ")
        open_btn = QPushButton("Ouvrir une image…")
        open_btn.clicked.connect(self.open_image)
        controls.addWidget(self.cam_btn)
        controls.addWidget(self.cam_index)
        controls.addStretch()
        controls.addWidget(open_btn)
        left.addLayout(controls)
        body.addWidget(left_box, 3)

        # ---- Colonne droite : verdict, données signées, historique
        right_inner = QWidget()
        right = QVBoxLayout(right_inner)
        right.setContentsMargins(0, 0, 12, 0)
        self.banner = QLabel("En attente d'une carte", alignment=Qt.AlignCenter)
        self.banner.setMinimumHeight(70)
        self._set_banner("En attente d'une carte", "#64748b")
        right.addWidget(self.banner)
        self.reason = QLabel("", objectName="hint", wordWrap=True)
        right.addWidget(self.reason)

        details_box = QGroupBox("Données signées lues dans le QR")
        dl = QHBoxLayout(details_box)
        self.form = QFormLayout()
        self.fields = {}
        for key, label in [("id", "N° de carte"), ("nom", "Nom"), ("prenom", "Prénom(s)"), ("role", "Statut / fonction"),
                           ("svc", "Service"), ("naiss", "Né(e) le"), ("emis", "Émise le"), ("exp", "Expire le"),
                           ("kid", "Clé de l'émetteur")]:
            self.fields[key] = QLabel("—", textInteractionFlags=Qt.TextSelectableByMouse)
            self.fields[key].setStyleSheet("font-weight: 600;")
            self.form.addRow(label, self.fields[key])
        dl.addLayout(self.form, 3)
        photo_col = QVBoxLayout()
        self.photo = QLabel("Pas de photo\nde référence", alignment=Qt.AlignCenter)
        self.photo.setFixedSize(150, 200)
        self.photo.setStyleSheet("background: #e2e8f0; border-radius: 6px; color: #64748b;")
        self.photo_status = QLabel("", alignment=Qt.AlignCenter, wordWrap=True)
        photo_col.addWidget(self.photo)
        photo_col.addWidget(self.photo_status)
        photo_col.addStretch()
        dl.addLayout(photo_col, 1)
        right.addWidget(details_box)

        hist_box = QGroupBox("Historique de la session")
        hl = QVBoxLayout(hist_box)
        self.history = QListWidget()
        hl.addWidget(self.history)
        right.addWidget(hist_box)

        reload_btn = QPushButton("Recharger les clés et la liste de révocation")
        reload_btn.clicked.connect(self.reload_trust)
        right.addWidget(reload_btn)
        scroll = QScrollArea(widgetResizable=True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setWidget(right_inner)
        body.addWidget(scroll, 2)

        self.setCentralWidget(central)
        self._update_status(warnings)

    # ------------------------------------------------------------ affichage
    def _set_banner(self, text: str, color: str) -> None:
        self.banner.setText(text)
        self.banner.setStyleSheet(f"background: {color}; color: white; font-size: 24px; font-weight: 700; "
                                  "border-radius: 10px; padding: 12px;")

    def _update_status(self, warnings: list[str]) -> None:
        msg = f"{len(self.service.public_keys)} clé(s) d'émetteur  ·  {self.service.revocation_info}"
        if warnings:
            msg += "   ⚠ " + " | ".join(warnings)
        self.statusBar().showMessage(msg)

    def show_verdict(self, v: Verdict) -> None:
        self._set_banner(v.title.upper(), v.color)
        self.reason.setText(v.reason)
        for key, label in self.fields.items():
            value = v.payload.get(key)
            label.setText(_fr(value) if key in ("naiss", "emis", "exp") and value else (value or "—"))
        if v.photo_ref is not None:
            self.photo.setPixmap(pil_to_pixmap(v.photo_ref).scaled(150, 200, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            ok = v.photo_conforme
            self.photo_status.setText("Photo de référence conforme" if ok else "⚠ Photo de référence NON conforme")
            self.photo_status.setStyleSheet(f"color: {'#15803d' if ok else '#b91c1c'}; font-weight: 600;")
        else:
            self.photo.clear()
            self.photo.setText("Pas de photo\nde référence")
            self.photo_status.setText("Compare le visage avec le titulaire." if v.payload else "")
            self.photo_status.setStyleSheet("color: #64748b;")
        who = f"{v.payload.get('prenom', '')} {v.payload.get('nom', '')}".strip() or "—"
        item = QListWidgetItem(f"{v.at:%H:%M:%S}   {v.title:<24}   {v.payload.get('id', '—')}   {who}")
        item.setForeground(Qt.GlobalColor.black)
        item.setData(Qt.UserRole, v.status)
        self.history.insertItem(0, item)
        while self.history.count() > 50:
            self.history.takeItem(self.history.count() - 1)

    # ------------------------------------------------------------ sources
    def open_image(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Image ou scan de carte", "",
                                              "Images (*.png *.jpg *.jpeg *.bmp *.webp)")
        if not path:
            return
        img = Image.open(path).convert("RGB")
        self.view.setPixmap(pil_to_pixmap(img).scaled(self.view.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))
        self.show_verdict(self.service.verify_image(img))

    def toggle_camera(self) -> None:
        if self.capture is not None:
            self.stop_camera()
            return
        backend = cv2.CAP_DSHOW if sys.platform.startswith("win") else cv2.CAP_ANY
        cap = cv2.VideoCapture(self.cam_index.value(), backend)
        if not cap.isOpened():
            self.view.setText("Impossible d'ouvrir la caméra.\nVérifie qu'elle est branchée, non utilisée par une autre "
                              "application,\net autorisée dans Paramètres > Confidentialité > Caméra.")
            return
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
        self.capture = cap
        self.cam_btn.setText("Arrêter la caméra")
        self.timer.start()

    def stop_camera(self) -> None:
        self.timer.stop()
        if self.capture is not None:
            self.capture.release()
        self.capture = None
        self.cam_btn.setText("Démarrer la caméra")
        self.view.clear()
        self.view.setText("Caméra arrêtée.")

    def next_frame(self) -> None:
        ok, frame = self.capture.read() if self.capture else (False, None)
        if not ok:
            return
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        h, w, _ = rgb.shape
        qimg = QImage(rgb.data, w, h, 3 * w, QImage.Format_RGB888)
        self.view.setPixmap(QPixmap.fromImage(qimg).scaled(self.view.size(), Qt.KeepAspectRatio, Qt.FastTransformation))

        self.frame_count += 1
        if self.frame_count % SCAN_EVERY_N_FRAMES:
            return
        token = decode_qr(frame, fast=True)
        if token and (token != self.last_token or time.monotonic() - self.last_time > SAME_CARD_DELAY):
            self.last_token, self.last_time = token, time.monotonic()
            self.show_verdict(self.service.verify_token(token))
            QApplication.beep()

    def reload_trust(self) -> None:
        self.service, warnings = VerifierService.from_folder(TRUST_DIR, PHOTOS_DIR)
        self._update_status(warnings)

    def closeEvent(self, event) -> None:
        self.stop_camera()
        super().closeEvent(event)


def main() -> None:
    app = QApplication(sys.argv)
    apply_light_theme(app)
    service, warnings = VerifierService.from_folder(TRUST_DIR, PHOTOS_DIR)
    window = VerifierWindow(service, warnings)
    screen = app.primaryScreen().availableGeometry()
    if screen.width() < 1300 or screen.height() < 900:
        window.showMaximized()
    else:
        window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

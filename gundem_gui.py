# -*- coding: utf-8 -*-
"""
BAP Gündem Üretici - Windows Masaüstü Arayüzü (PyQt5)

Kullanım (kaynak kod):
    python gundem_gui.py

Windows'ta EXE derlemek:      EXE_KUR.bat        -> dist\\BAP_Gundem.exe
Günlük tek tıkla başlatma:    GUNDEM_BASLAT.bat  -> exe varsa exe, yoksa Python
"""
from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
import threading
import traceback

from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                             QHBoxLayout, QLabel, QLineEdit, QPushButton,
                             QFileDialog, QMessageBox, QGroupBox, QTextEdit,
                             QProgressBar, QStyleFactory, QDesktopWidget, QSizePolicy)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QSettings, QTimer
from PyQt5.QtGui import QIcon, QFont, QColor, QTextCursor, QTextCharFormat
import qtawesome as qta


def taban_yolu():
    """Kayıt yazılabilir çalışma klasörü: exe'nin bulunduğu klasör / script klasörü."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def kaynak_yolu():
    """Paket içine gömülü dosyaların yeri (demo girdi/config/logo)."""
    if getattr(sys, "frozen", False):
        return getattr(sys, "_MEIPASS", taban_yolu())
    return taban_yolu()


class Worker(QThread):
    """Arka planda üretimi yapan iş parçacığı"""
    log_signal = pyqtSignal(str, str)
    finished_signal = pyqtSignal(str, str, str)
    error_signal = pyqtSignal(str)

    def __init__(self, girdi, config, cikti, logo):
        super().__init__()
        self.girdi = girdi
        self.config = config
        self.cikti = cikti
        self.logo = logo

    def _dinle(self, seviye, metin):
        self.log_signal.emit(seviye, metin)

    def run(self):
        try:
            modul = self._paket_modul()
            cikti_path, rapor_path, uretim_raporu = modul.uretim_yap(
                girdi_kok=self.girdi,
                config_yolu=self.config,
                cikti_yolu=self.cikti,
                logo_yolu=self.logo,
                dinleyici=self._dinle
            )
            self.log_signal.emit("OK", "TAMAMLANDI")
            self.finished_signal.emit(cikti_path, rapor_path, uretim_raporu)
        except Exception as e:
            self.error_signal.emit(traceback.format_exc(limit=8))

    def _paket_modul(self):
        """gundem_uret.py çekirdeğini dosya yolundan içe aktarır (exe'de de çalışır)."""
        yol = os.path.join(taban_yolu(), "gundem_uret.py")
        if not os.path.exists(yol):
            yol = os.path.join(kaynak_yolu(), "gundem_uret.py")
        spec = importlib.util.spec_from_file_location("gundem_uret_modulden", yol)
        modul = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = modul
        spec.loader.exec_module(modul)
        return modul


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("BAP Gündem Üretici")
        self.setMinimumSize(850, 700)
        self.settings = QSettings("BAP_Gundem", "Ayarlar")

        # Fluent Design Style QSS
        self.setStyleSheet("""
            QMainWindow {
                background-color: #F3F3F3;
            }
            QWidget {
                font-family: 'Segoe UI', Arial, sans-serif;
                font-size: 14px;
                color: #202020;
            }
            QGroupBox {
                border: 1px solid #D0D0D0;
                border-radius: 8px;
                margin-top: 24px;
                background-color: #FFFFFF;
                padding: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top left;
                padding: 0 10px;
                background-color: transparent;
                font-weight: bold;
                color: #005A9E;
            }
            QLineEdit {
                border: 1px solid #C0C0C0;
                border-radius: 4px;
                padding: 6px;
                background-color: #FDFDFD;
                selection-background-color: #0078D7;
            }
            QLineEdit:focus {
                border: 2px solid #0078D7;
                background-color: #FFFFFF;
            }
            QPushButton {
                background-color: #E1E1E1;
                border: 1px solid #ADADAD;
                border-radius: 4px;
                padding: 8px 12px;
                min-width: 80px;
            }
            QPushButton:hover {
                background-color: #E5F1FB;
                border: 1px solid #0078D7;
            }
            QPushButton:pressed {
                background-color: #CCE4F7;
            }
            QPushButton#primaryButton {
                background-color: #0078D7;
                color: white;
                border: none;
                font-weight: bold;
                font-size: 15px;
            }
            QPushButton#primaryButton:hover {
                background-color: #005A9E;
            }
            QPushButton#primaryButton:pressed {
                background-color: #004578;
            }
            QPushButton#primaryButton:disabled {
                background-color: #A0A0A0;
                color: #E0E0E0;
            }
            QTextEdit {
                border: 1px solid #D0D0D0;
                border-radius: 6px;
                background-color: #FFFFFF;
                font-family: 'Consolas', 'Courier New', monospace;
                font-size: 13px;
                padding: 5px;
            }
            QProgressBar {
                border: 1px solid #C0C0C0;
                border-radius: 4px;
                text-align: center;
                background-color: #E6E6E6;
            }
            QProgressBar::chunk {
                background-color: #0078D7;
                width: 10px;
                margin: 0.5px;
            }
        """)

        self._init_ui()
        self._load_settings()
        self._center_window()
        self.worker = None

        self._son_cikti = None
        self._son_rapor = None
        self._son_klasor = None

    def _init_ui(self):
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QVBoxLayout(main_widget)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(15)

        # 1. Dosya ve Klasör Yolları
        paths_group = QGroupBox("Dosya ve Klasör Yolları")
        paths_layout = QVBoxLayout(paths_group)
        paths_layout.setSpacing(12)

        # Girdi Klasörü
        h1 = QHBoxLayout()
        h1.addWidget(QLabel("Proje Klasörü:"), 1)
        self.edit_girdi = QLineEdit()
        self.edit_girdi.setPlaceholderText("PDF dosyalarının bulunduğu klasör (Örn: girdi/19.08.2026)")
        h1.addWidget(self.edit_girdi, 4)
        btn_girdi = QPushButton(qta.icon('fa5s.folder-open', color='#0078D7'), "Seç")
        btn_girdi.clicked.connect(lambda: self._browse("girdi"))
        h1.addWidget(btn_girdi)
        paths_layout.addLayout(h1)

        # Config
        h2 = QHBoxLayout()
        h2.addWidget(QLabel("Yapılandırma (Excel):"), 1)
        self.edit_config = QLineEdit()
        self.edit_config.setPlaceholderText("Şablon Excel dosyası (Örn: config/19.08.2026.xlsx)")
        h2.addWidget(self.edit_config, 4)
        btn_config = QPushButton(qta.icon('fa5s.file-excel', color='#107C41'), "Seç")
        btn_config.clicked.connect(lambda: self._browse("config"))
        h2.addWidget(btn_config)
        paths_layout.addLayout(h2)

        # Logo
        h3 = QHBoxLayout()
        h3.addWidget(QLabel("Logo (İsteğe Bağlı):"), 1)
        self.edit_logo = QLineEdit()
        self.edit_logo.setPlaceholderText("Gündem için logo (Örn: logo/sbu_logo.jpg)")
        h3.addWidget(self.edit_logo, 4)
        btn_logo = QPushButton(qta.icon('fa5s.image', color='#D83B01'), "Seç")
        btn_logo.clicked.connect(lambda: self._browse("logo"))
        h3.addWidget(btn_logo)
        paths_layout.addLayout(h3)

        # Çıktı
        h4 = QHBoxLayout()
        h4.addWidget(QLabel("Çıktı Word Dosyası:"), 1)
        self.edit_cikti = QLineEdit()
        self.edit_cikti.setPlaceholderText("Üretilecek docx dosyasının adı ve yeri (Örn: cikti/Gündem.docx)")
        h4.addWidget(self.edit_cikti, 4)
        btn_cikti = QPushButton(qta.icon('fa5s.file-word', color='#2B579A'), "Seç")
        btn_cikti.clicked.connect(lambda: self._browse("cikti"))
        h4.addWidget(btn_cikti)
        paths_layout.addLayout(h4)

        main_layout.addWidget(paths_group)

        # 2. Araçlar ve Eylemler
        tools_layout = QHBoxLayout()

        btn_yeni_sablon = QPushButton(qta.icon('fa5s.plus-square', color='#107C41'), "Yeni Excel Şablonu")
        btn_yeni_sablon.clicked.connect(self.sablon_uret)
        tools_layout.addWidget(btn_yeni_sablon)

        btn_sablon_ac = QPushButton(qta.icon('fa5s.external-link-alt', color='#107C41'), "Excel'i Aç")
        btn_sablon_ac.clicked.connect(self.sablon_ac)
        tools_layout.addWidget(btn_sablon_ac)

        btn_demo = QPushButton(qta.icon('fa5s.lightbulb', color='#FFB900'), "Demo Klasörü Aç")
        btn_demo.clicked.connect(self.demo_ac)
        tools_layout.addWidget(btn_demo)

        tools_layout.addStretch()

        main_layout.addLayout(tools_layout)

        # 3. Üretim Butonu
        self.btn_uret = QPushButton("GÜNDEMİ ÜRET")
        self.btn_uret.setObjectName("primaryButton")
        self.btn_uret.setFixedHeight(45)
        self.btn_uret.clicked.connect(self.baslat)
        main_layout.addWidget(self.btn_uret)

        # 4. Durum ve İlerleme
        self.lbl_durum = QLabel("Hazır.")
        self.lbl_durum.setStyleSheet("color: #666; font-style: italic;")
        main_layout.addWidget(self.lbl_durum)

        self.progress = QProgressBar()
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(10)
        self.progress.hide()
        main_layout.addWidget(self.progress)

        # 5. Log Ekranı
        self.log_area = QTextEdit()
        self.log_area.setReadOnly(True)
        main_layout.addWidget(self.log_area)

        # 6. Çıktı Araçları (Başlangıçta kapalı, üretim bitince aktifleşir)
        self.out_tools_layout = QHBoxLayout()

        self.btn_cikti_ac = QPushButton(qta.icon('fa5s.folder-open'), "Çıktı Klasörünü Aç")
        self.btn_cikti_ac.clicked.connect(self.cikti_klasoru_ac)
        self.btn_cikti_ac.setEnabled(False)
        self.out_tools_layout.addWidget(self.btn_cikti_ac)

        self.btn_rapor_ac = QPushButton(qta.icon('fa5s.file-alt'), "Üretim Raporunu (.md) Aç")
        self.btn_rapor_ac.clicked.connect(self.raporu_ac)
        self.btn_rapor_ac.setEnabled(False)
        self.out_tools_layout.addWidget(self.btn_rapor_ac)

        self.out_tools_layout.addStretch()
        main_layout.addLayout(self.out_tools_layout)

    def _center_window(self):
        qr = self.frameGeometry()
        cp = QDesktopWidget().availableGeometry().center()
        qr.moveCenter(cp)
        self.move(qr.topLeft())

    def _load_settings(self):
        self.edit_girdi.setText(self.settings.value("girdi", os.path.join(kaynak_yolu(), "girdi", "19.08.2026")))
        self.edit_config.setText(self.settings.value("config", os.path.join(kaynak_yolu(), "config", "19.08.2026.xlsx")))
        self.edit_logo.setText(self.settings.value("logo", os.path.join(kaynak_yolu(), "logo", "sbu_logo.jpg")))

        default_cikti = os.path.join(taban_yolu(), "cikti", "Gündem.docx")
        self.edit_cikti.setText(self.settings.value("cikti", default_cikti))

    def _save_settings(self):
        self.settings.setValue("girdi", self.edit_girdi.text())
        self.settings.setValue("config", self.edit_config.text())
        self.settings.setValue("logo", self.edit_logo.text())
        self.settings.setValue("cikti", self.edit_cikti.text())

    def closeEvent(self, event):
        self._save_settings()
        event.accept()

    def _browse(self, tur):
        if tur == "girdi":
            yol = QFileDialog.getExistingDirectory(self, "Proje PDF klasörünü seç", self.edit_girdi.text())
            if yol:
                self.edit_girdi.setText(yol)
        elif tur == "config":
            yol, _ = QFileDialog.getOpenFileName(self, "Yapılandırma dosyası seç", self.edit_config.text(), "Excel (*.xlsx);;Tümü (*.*)")
            if yol:
                self.edit_config.setText(yol)
        elif tur == "logo":
            yol, _ = QFileDialog.getOpenFileName(self, "Logo dosyası seç", self.edit_logo.text(), "Görseller (*.jpg *.jpeg *.png);;Tümü (*.*)")
            if yol:
                self.edit_logo.setText(yol)
        elif tur == "cikti":
            yol, _ = QFileDialog.getSaveFileName(self, "Çıktı dosyasını seç", self.edit_cikti.text(), "Word (*.docx)")
            if yol:
                self.edit_cikti.setText(yol)

    def _yaz(self, seviye, metin):
        renkler = {
            "OK": QColor("#1e7d32"),     # Yeşil
            "UYARI": QColor("#e65100"),  # Turuncu
            "BİLGİ": QColor("#1565c0"),  # Mavi
            "HATA": QColor("#b71c1c"),   # Kırmızı
            "DUZ": QColor("#333333")     # Koyu Gri
        }

        color = renkler.get(seviye, renkler["DUZ"])
        is_bold = seviye in ("OK", "UYARI", "HATA")

        cursor = self.log_area.textCursor()
        cursor.movePosition(QTextCursor.End)

        format = QTextCharFormat()
        format.setForeground(color)
        if is_bold:
            format.setFontWeight(QFont.Bold)

        cursor.insertText(f"{seviye:<6} {metin}\n", format)
        self.log_area.setTextCursor(cursor)
        self.log_area.ensureCursorVisible()

    def sablon_uret(self):
        yol, _ = QFileDialog.getSaveFileName(self, "Yeni yapılandırma şablonu kaydet", "toplanti.xlsx", "Excel (*.xlsx)")
        if not yol:
            return

        cevap = QMessageBox.question(self, "Şablon içeriği",
            "Örnek verilerle dolu şablon mu oluşturulsun?\n\n"
            "Evet  -> örnek satırlar hazır (ilk deneme için)\n"
            "Hayır -> boş şablon (kendi verileriniz için)",
            QMessageBox.Yes | QMessageBox.No)

        demo = (cevap == QMessageBox.Yes)

        try:
            from gundem_uret.config_dosya import sablon_olustur
            sablon_olustur(yol, ornek=demo)
        except Exception as hata:
            QMessageBox.critical(self, "Şablon oluşturulamadı", str(hata))
            return

        self.edit_config.setText(yol)
        self._yaz("OK", f"Şablon oluşturuldu: {yol}")
        QMessageBox.information(self, "Şablon hazır",
                            "Şablon oluşturuldu.\nExcel'deki sayfaları doldurun:\n"
                            "Toplantı | Maddeler | Düzeltmeler | Hakemler | KararMaddeleri\n\n"
                            "Hazır olunca 'Gündemi Üret'e tıklayın.")

    def sablon_ac(self):
        yol = self.edit_config.text().strip()
        if not os.path.exists(yol):
            QMessageBox.warning(self, "Dosya yok", f"Dosya bulunamadı:\n{yol}")
            return
        self._ac(yol)

    def cikti_klasoru_ac(self):
        klasor = self._son_klasor
        if not klasor or not os.path.isdir(klasor):
            klasor = os.path.join(taban_yolu(), "cikti")
            os.makedirs(klasor, exist_ok=True)
        self._ac(klasor)

    def raporu_ac(self):
        if self._son_rapor and os.path.exists(self._son_rapor):
            self._ac(self._son_rapor)
        else:
            QMessageBox.information(self, "Rapor yok", "Henüz üretim yapılmadı.")

    def demo_ac(self):
        klasor = self.edit_girdi.text().strip()
        if klasor and os.path.isdir(klasor):
            self._ac(klasor)
        else:
            QMessageBox.information(self, "Örnek veri yok", "Seçili proje klasörü bulunamıyor.")

    @staticmethod
    def _ac(yol):
        try:
            if sys.platform.startswith("win"):
                os.startfile(yol)  # noqa
            elif sys.platform == "darwin":
                subprocess.Popen(["open", yol])
            else:
                subprocess.Popen(["xdg-open", yol])
        except Exception as e:
            print(f"Acilirken hata: {e}")

    def baslat(self):
        girdi = self.edit_girdi.text().strip()
        config = self.edit_config.text().strip()
        cikti = self.edit_cikti.text().strip()
        logo = self.edit_logo.text().strip()

        if not os.path.isdir(girdi):
            QMessageBox.warning(self, "Klasör yok", f"Proje PDF klasörü bulunamadı:\n{girdi}")
            return
        if not os.path.exists(config):
            QMessageBox.warning(self, "Yapılandırma yok",
                f"Dosya bulunamadı:\n{config}\n\n'Yeni Şablon…' ile oluşturup Excel'de doldurun.")
            return

        if not self.bagimlilik_kontrol():
            return

        self._save_settings()
        self.btn_uret.setEnabled(False)
        self.progress.show()
        self.progress.setRange(0, 0) # Indeterminate mode
        self.lbl_durum.setText("Üretiliyor… Lütfen bekleyin.")
        self.log_area.clear()
        self._yaz("BİLGİ", "Üretim başladı.")

        self.worker = Worker(girdi, config, cikti, logo)
        self.worker.log_signal.connect(self._yaz)
        self.worker.finished_signal.connect(self._on_finished)
        self.worker.error_signal.connect(self._on_error)
        self.worker.start()

    def _on_finished(self, cikti, rapor, uretim_raporu):
        self._son_cikti = cikti
        self._son_rapor = rapor
        self._son_klasor = os.path.dirname(cikti)

        self.progress.hide()
        self.btn_uret.setEnabled(True)
        self.lbl_durum.setText("Bitti.")
        self.btn_cikti_ac.setEnabled(True)
        self.btn_rapor_ac.setEnabled(True)

        QMessageBox.information(self, "Tamamlandı",
                            "Gündem belgesi üretildi.\n\n"
                            f"{self._son_cikti}\n\n"
                            "Çıktı klasörünü açmak için 'Çıktı Klasörünü Aç' düğmesini kullanın.")

    def _on_error(self, err_text):
        self.progress.hide()
        self.btn_uret.setEnabled(True)
        self.lbl_durum.setText("Hata oluştu.")
        QMessageBox.critical(self, "Hata", str(err_text)[:2000])

    def bagimlilik_kontrol(self):
        eksik = []
        for ad in ("pypdf", "pdfplumber", "docx", "openpyxl"):
            try:
                __import__(ad)
            except Exception:
                eksik.append(ad)
        if not eksik:
            return True

        if getattr(sys, "frozen", False):
            QMessageBox.critical(self, "Eksik bileşen",
                                 "Programda gerekli bileşenler yok:\n" + ", ".join(eksik) +
                                 "\n\nEXE_KUR.bat ile yeniden derleyin.")
            return False

        cevap = QMessageBox.question(self, "Eksik bağımlılıklar",
            "Gerekli Python paketleri bulunamadı:\n" + ", ".join(eksik) +
            "\n\nŞimdi otomatik kurulsun mu?\n(pip install -r gereksinimler.txt)",
            QMessageBox.Yes | QMessageBox.No)

        if cevap == QMessageBox.No:
            return False

        self.lbl_durum.setText("Bağımlılıklar kuruluyor…")
        self._yaz("BİLGİ", "pip ile bağımlılıklar kuruluyor…")
        QApplication.processEvents() # UI'ı güncelle

        try:
            gizle = 0x08000000 if sys.platform.startswith("win") else 0
            surec = subprocess.Popen(
                [sys.executable, "-m", "pip", "install", "-r",
                 os.path.join(taban_yolu(), "gereksinimler.txt")],
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding="utf-8", errors="replace",
                creationflags=gizle)

            for satir in surec.stdout:
                satir = satir.strip()
                if satir:
                    self._yaz("DUZ", satir[:160])
                    QApplication.processEvents()
            kod = surec.wait()
        except Exception as hata:
            QMessageBox.critical(self, "Kurulum hatası", str(hata))
            return False

        if kod != 0:
            QMessageBox.critical(self, "Kurulum hatası",
                "pip kurulumu başarısız. Komut isteminde el ile çalıştırın:\n"
                "python -m pip install -r gereksinimler.txt")
            return False

        self._yaz("OK", "Bağımlılıklar kuruldu.")
        return True


def main():
    if hasattr(Qt, 'AA_EnableHighDpiScaling'):
        QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    if hasattr(Qt, 'AA_UseHighDpiPixmaps'):
        QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    app = QApplication(sys.argv)

    app.setStyle('Fusion') # Temel tarz, üzerine QSS uygulanır

    window = MainWindow()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()

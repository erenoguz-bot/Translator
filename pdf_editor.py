import sys
import os
import fitz  # PyMuPDF
import qtawesome as qta
from PyQt5.QtWidgets import (QApplication, QMainWindow, QAction, QFileDialog,
                             QLabel, QScrollArea, QToolBar, QMessageBox,
                             QInputDialog, QDockWidget, QTextEdit, QVBoxLayout,
                             QWidget, QTabWidget, QListWidget, QListWidgetItem,
                             QSplitter, QStatusBar, QPushButton, QHBoxLayout,
                             QComboBox, QSpinBox, QColorDialog)
from PyQt5.QtGui import QImage, QPixmap, QIcon, QKeySequence, QColor, QFont
from PyQt5.QtCore import Qt, QSize, QPointF

# Modern Dark Theme QSS
DARK_THEME_QSS = """
QMainWindow, QDialog {
    background-color: #2b2b2b;
    color: #e0e0e0;
}
QToolBar {
    background-color: #333333;
    border-bottom: 1px solid #444;
    padding: 5px;
}
QToolBar::separator {
    width: 1px;
    background-color: #555;
    margin: 5px;
}
QToolButton {
    background-color: transparent;
    border: 1px solid transparent;
    padding: 6px;
    border-radius: 4px;
    color: #e0e0e0;
}
QToolButton:hover {
    background-color: #444;
    border: 1px solid #555;
}
QToolButton:pressed {
    background-color: #555;
}
QTabWidget::pane {
    border: 1px solid #444;
    background: #2b2b2b;
}
QTabBar::tab {
    background: #333;
    color: #aaa;
    border: 1px solid #444;
    padding: 8px 20px;
    margin-right: 2px;
    border-top-left-radius: 4px;
    border-top-right-radius: 4px;
}
QTabBar::tab:selected {
    background: #2b2b2b;
    color: #fff;
    border-bottom-color: #2b2b2b;
}
QListWidget {
    background-color: #1e1e1e;
    color: #e0e0e0;
    border: none;
}
QListWidget::item {
    padding: 10px;
}
QListWidget::item:selected {
    background-color: #007acc;
    color: white;
}
QDockWidget {
    color: #e0e0e0;
    font-weight: bold;
}
QDockWidget::title {
    background: #333;
    padding: 5px;
}
QTextEdit {
    background-color: #1e1e1e;
    color: #d4d4d4;
    border: 1px solid #444;
}
QStatusBar {
    background-color: #007acc;
    color: white;
}
QScrollBar:vertical {
    border: none;
    background: #2b2b2b;
    width: 12px;
    margin: 0px 0px 0px 0px;
}
QScrollBar::handle:vertical {
    background: #555;
    min-height: 20px;
    border-radius: 6px;
}
QScrollBar::handle:vertical:hover {
    background: #777;
}
"""

class PDFDocument:
    def __init__(self, file_path):
        self.file_path = file_path
        self.name = os.path.basename(file_path)
        self.doc = fitz.open(file_path)
        self.current_page = 0
        self.zoom_factor = 1.5

class PDFEditor(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Nitro PDF Pro Alternatifi - Studio v2")
        self.setGeometry(50, 50, 1400, 900)
        self.documents = []
        self.active_doc_idx = -1

        self.setStyleSheet(DARK_THEME_QSS)
        self.initUI()

    def initUI(self):
        # Üst Ribbon Araç Çubuğu
        self.toolbar = QToolBar("Ana Ribbon")
        self.toolbar.setIconSize(QSize(28, 28))
        self.toolbar.setMovable(False)
        self.addToolBar(self.toolbar)

        # --- DOSYA VE SİSTEM GRUBU ---
        openAct = QAction(qta.icon('fa5s.folder-open', color='white'), 'Aç', self)
        openAct.triggered.connect(self.openPDF)
        self.toolbar.addAction(openAct)

        saveAct = QAction(qta.icon('fa5s.save', color='white'), 'Kaydet', self)
        saveAct.triggered.connect(self.savePDF)
        self.toolbar.addAction(saveAct)

        closeAct = QAction(qta.icon('fa5s.times', color='#ff6b6b'), 'Kapat', self)
        closeAct.triggered.connect(self.close_current_tab)
        self.toolbar.addAction(closeAct)

        self.toolbar.addSeparator()

        # --- GEZİNME GRUBU ---
        self.prevPageAct = QAction(qta.icon('fa5s.chevron-left', color='white'), 'Önceki', self)
        self.prevPageAct.triggered.connect(self.prev_page)
        self.toolbar.addAction(self.prevPageAct)

        self.nextPageAct = QAction(qta.icon('fa5s.chevron-right', color='white'), 'Sonraki', self)
        self.nextPageAct.triggered.connect(self.next_page)
        self.toolbar.addAction(self.nextPageAct)

        self.toolbar.addSeparator()

        # --- GÖRÜNÜM GRUBU ---
        zoomInAct = QAction(qta.icon('fa5s.search-plus', color='white'), 'Yakınlaştır', self)
        zoomInAct.triggered.connect(self.zoom_in)
        self.toolbar.addAction(zoomInAct)

        zoomOutAct = QAction(qta.icon('fa5s.search-minus', color='white'), 'Uzaklaştır', self)
        zoomOutAct.triggered.connect(self.zoom_out)
        self.toolbar.addAction(zoomOutAct)

        rotateAct = QAction(qta.icon('fa5s.redo', color='white'), 'Döndür', self)
        rotateAct.triggered.connect(self.rotate_page)
        self.toolbar.addAction(rotateAct)

        self.toolbar.addSeparator()

        # --- DÜZENLEME & ANOTASYON GRUBU ---
        addTextAct = QAction(qta.icon('fa5s.font', color='#4dabf7'), 'Metin Ekle', self)
        addTextAct.triggered.connect(self.add_text_annotation)
        self.toolbar.addAction(addTextAct)

        highlightAct = QAction(qta.icon('fa5s.highlighter', color='#fcc419'), 'Vurgula', self)
        highlightAct.triggered.connect(self.highlight_search_text)
        self.toolbar.addAction(highlightAct)

        redactAct = QAction(qta.icon('fa5s.eraser', color='white'), 'Sansürle', self)
        redactAct.setToolTip("Aranan kelimeyi siyah bir kutu ile kapatır (Redaction)")
        redactAct.triggered.connect(self.redact_text)
        self.toolbar.addAction(redactAct)

        watermarkAct = QAction(qta.icon('fa5s.stamp', color='#8ce99a'), 'Filigran', self)
        watermarkAct.triggered.connect(self.add_watermark)
        self.toolbar.addAction(watermarkAct)

        drawAct = QAction(qta.icon('fa5s.pen', color='#ff922b'), 'Serbest Çizim', self)
        drawAct.setToolTip("Sayfaya basit bir imza/çizgi ekler (Prototip)")
        drawAct.triggered.connect(self.add_ink)
        self.toolbar.addAction(drawAct)

        self.toolbar.addSeparator()

        # --- SAYFA İŞLEMLERİ ---
        delPageAct = QAction(qta.icon('fa5s.file-excel', color='#ff6b6b'), 'Sayfa Sil', self)
        delPageAct.triggered.connect(self.delete_current_page)
        self.toolbar.addAction(delPageAct)

        insertPageAct = QAction(qta.icon('fa5s.file-medical', color='#20c997'), 'Boş Sayfa', self)
        insertPageAct.triggered.connect(self.insert_blank_page)
        self.toolbar.addAction(insertPageAct)

        self.toolbar.addSeparator()

        # --- ARAÇLAR ---
        extractAct = QAction(qta.icon('fa5s.file-alt', color='white'), 'Metni Çıkar', self)
        extractAct.triggered.connect(self.extract_text)
        self.toolbar.addAction(extractAct)

        infoAct = QAction(qta.icon('fa5s.info-circle', color='white'), 'Bilgi', self)
        infoAct.triggered.connect(self.show_info)
        self.toolbar.addAction(infoAct)

        # Arayüz Yapısı
        main_splitter = QSplitter(Qt.Horizontal)
        self.setCentralWidget(main_splitter)

        # Sol Taraf: Sayfa Önizlemeleri (Thumbnails)
        self.thumbnail_list = QListWidget()
        self.thumbnail_list.setIconSize(QSize(120, 160))
        self.thumbnail_list.setResizeMode(QListWidget.Adjust)
        self.thumbnail_list.itemClicked.connect(self.thumbnail_clicked)

        left_dock = QDockWidget("Sayfalar", self)
        left_dock.setWidget(self.thumbnail_list)
        self.addDockWidget(Qt.LeftDockWidgetArea, left_dock)

        # Orta: Sekmeli Görüntüleyici
        self.tabs = QTabWidget()
        self.tabs.setTabsClosable(True)
        self.tabs.tabCloseRequested.connect(self.close_tab)
        self.tabs.currentChanged.connect(self.tab_changed)
        main_splitter.addWidget(self.tabs)

        # Sağ: Extracted Text (Varsayılan gizli)
        self.right_dock = QDockWidget("Metin Çıkarımı", self)
        self.text_edit = QTextEdit()
        self.text_edit.setReadOnly(True)
        self.right_dock.setWidget(self.text_edit)
        self.addDockWidget(Qt.RightDockWidgetArea, self.right_dock)
        self.right_dock.hide()

        # Status Bar
        self.statusbar = QStatusBar()
        self.setStatusBar(self.statusbar)
        self.page_info_label = QLabel("Sayfa: 0 / 0")
        self.zoom_info_label = QLabel("Zoom: 100%")
        self.statusbar.addPermanentWidget(self.page_info_label)
        self.statusbar.addPermanentWidget(self.zoom_info_label)

        self.update_ui_state()

    # --- YARDIMCI METOTLAR ---
    def get_active_doc(self):
        if 0 <= self.active_doc_idx < len(self.documents):
            return self.documents[self.active_doc_idx]
        return None

    def get_active_scroll_area(self):
        if self.tabs.count() > 0 and self.active_doc_idx != -1:
            return self.tabs.currentWidget()
        return None

    def update_ui_state(self):
        has_doc = self.get_active_doc() is not None
        self.prevPageAct.setEnabled(has_doc)
        self.nextPageAct.setEnabled(has_doc)
        if not has_doc:
            self.thumbnail_list.clear()
            self.page_info_label.setText("Sayfa: 0 / 0")
            self.zoom_info_label.setText("Zoom: 100%")

    # --- DOSYA İŞLEMLERİ ---
    def openPDF(self):
        fileName, _ = QFileDialog.getOpenFileName(self, "PDF Aç", "", "PDF Dosyaları (*.pdf)")
        if fileName:
            try:
                pdf_doc = PDFDocument(fileName)
                self.documents.append(pdf_doc)
                self.active_doc_idx = len(self.documents) - 1

                scroll_area = QScrollArea()
                image_label = QLabel()
                image_label.setAlignment(Qt.AlignCenter)
                scroll_area.setStyleSheet("background-color: #1e1e1e;")
                scroll_area.setWidget(image_label)
                scroll_area.setWidgetResizable(True)

                idx = self.tabs.addTab(scroll_area, pdf_doc.name)
                self.tabs.setCurrentIndex(idx)

                self.load_thumbnails()
                self.render_current_page()
                self.update_ui_state()
            except Exception as e:
                QMessageBox.critical(self, "Hata", f"Dosya açılamadı:\n{e}")

    def close_current_tab(self):
        idx = self.tabs.currentIndex()
        if idx != -1:
            self.close_tab(idx)

    def close_tab(self, index):
        if 0 <= index < len(self.documents):
            doc_to_close = self.documents.pop(index)
            doc_to_close.doc.close()

            widget_to_remove = self.tabs.widget(index)
            self.tabs.removeTab(index)
            if widget_to_remove:
                widget_to_remove.deleteLater()

            if len(self.documents) == 0:
                self.active_doc_idx = -1
            else:
                self.active_doc_idx = self.tabs.currentIndex()

            self.load_thumbnails()
            self.update_ui_state()

    def tab_changed(self, index):
        if index != -1 and len(self.documents) > 0:
            self.active_doc_idx = index
            self.load_thumbnails()
            self.render_current_page()
            self.update_ui_state()

    def savePDF(self):
        pdf_doc = self.get_active_doc()
        if pdf_doc:
            fileName, _ = QFileDialog.getSaveFileName(self, "PDF'i Kaydet", pdf_doc.name, "PDF Dosyaları (*.pdf)")
            if fileName:
                try:
                    pdf_doc.doc.save(fileName)
                    QMessageBox.information(self, "Başarılı", "Tüm gelişmiş düzenlemeler PDF'e kalıcı olarak işlendi.")
                except Exception as e:
                    QMessageBox.critical(self, "Hata", f"Kaydetme hatası:\n{e}")

    # --- RENDER İŞLEMLERİ ---
    def load_thumbnails(self):
        self.thumbnail_list.clear()
        pdf_doc = self.get_active_doc()
        if not pdf_doc: return

        num_pages = min(len(pdf_doc.doc), 50)
        for i in range(num_pages):
            page = pdf_doc.doc.load_page(i)
            mat = fitz.Matrix(0.15, 0.15)
            pix = page.get_pixmap(matrix=mat)
            img = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format_RGB888)

            icon = QIcon(QPixmap.fromImage(img))
            item = QListWidgetItem(icon, f"Sayfa {i+1}")
            item.setTextAlignment(Qt.AlignCenter)
            item.setData(Qt.UserRole, i)
            self.thumbnail_list.addItem(item)

    def thumbnail_clicked(self, item):
        page_idx = item.data(Qt.UserRole)
        if page_idx is not None:
            pdf_doc = self.get_active_doc()
            if pdf_doc:
                pdf_doc.current_page = page_idx
                self.render_current_page()

    def render_current_page(self):
        pdf_doc = self.get_active_doc()
        scroll_area = self.get_active_scroll_area()
        if not pdf_doc or not scroll_area: return

        if pdf_doc.current_page >= len(pdf_doc.doc):
            pdf_doc.current_page = max(0, len(pdf_doc.doc) - 1)

        page = pdf_doc.doc.load_page(pdf_doc.current_page)
        mat = fitz.Matrix(pdf_doc.zoom_factor, pdf_doc.zoom_factor)
        pix = page.get_pixmap(matrix=mat)
        img = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format_RGB888)

        image_label = scroll_area.widget()
        image_label.setPixmap(QPixmap.fromImage(img))

        self.page_info_label.setText(f"Sayfa: {pdf_doc.current_page + 1} / {len(pdf_doc.doc)}")
        self.zoom_info_label.setText(f"Zoom: {int(pdf_doc.zoom_factor * 100)}%")

        if pdf_doc.current_page < self.thumbnail_list.count():
            self.thumbnail_list.setCurrentRow(pdf_doc.current_page)

    # --- GEZİNME VE GÖRÜNÜM ---
    def prev_page(self):
        pdf_doc = self.get_active_doc()
        if pdf_doc and pdf_doc.current_page > 0:
            pdf_doc.current_page -= 1
            self.render_current_page()

    def next_page(self):
        pdf_doc = self.get_active_doc()
        if pdf_doc and pdf_doc.current_page < len(pdf_doc.doc) - 1:
            pdf_doc.current_page += 1
            self.render_current_page()

    def zoom_in(self):
        pdf_doc = self.get_active_doc()
        if pdf_doc:
            pdf_doc.zoom_factor *= 1.2
            self.render_current_page()

    def zoom_out(self):
        pdf_doc = self.get_active_doc()
        if pdf_doc:
            pdf_doc.zoom_factor /= 1.2
            self.render_current_page()

    def rotate_page(self):
        pdf_doc = self.get_active_doc()
        if pdf_doc:
            page = pdf_doc.doc.load_page(pdf_doc.current_page)
            page.set_rotation((page.rotation + 90) % 360)
            self.render_current_page()
            self.load_thumbnails() # Thumbnail da güncellensin

    # --- YENİ SÜPER ÖZELLİKLER ---

    def add_text_annotation(self):
        pdf_doc = self.get_active_doc()
        if pdf_doc:
            text, ok = QInputDialog.getText(self, 'Metin Ekle', 'Eklenecek metni girin (Kırmızı olarak eklenecek):')
            if ok and text:
                page = pdf_doc.doc.load_page(pdf_doc.current_page)
                # Orta kısma ekle
                rect = fitz.Rect(100, 100, 400, 150)
                annot = page.add_freetext_annot(rect, text, fontsize=16, fontname="helv", text_color=(1, 0, 0))
                annot.update()
                self.render_current_page()

    def highlight_search_text(self):
        pdf_doc = self.get_active_doc()
        if pdf_doc:
            text, ok = QInputDialog.getText(self, 'Vurgula', 'Vurgulanacak kelimeyi girin:')
            if ok and text:
                page = pdf_doc.doc.load_page(pdf_doc.current_page)
                text_instances = page.search_for(text)
                if text_instances:
                    for inst in text_instances:
                        annot = page.add_highlight_annot(inst)
                        annot.update()
                    self.render_current_page()
                else:
                    QMessageBox.information(self, "Bulunamadı", "Kelime bulunamadı.")

    def redact_text(self):
        """Sansürleme (Redact) işlemi: Metni bulur ve üzerini siyah bir kutu ile tamamen kapatır."""
        pdf_doc = self.get_active_doc()
        if pdf_doc:
            text, ok = QInputDialog.getText(self, 'Sansürle', 'Gizlenecek/Sansürlenecek metni girin:')
            if ok and text:
                page = pdf_doc.doc.load_page(pdf_doc.current_page)
                text_instances = page.search_for(text)
                if text_instances:
                    for inst in text_instances:
                        page.add_redact_annot(inst, fill=(0, 0, 0))
                    page.apply_redactions() # İşlemi kalıcı olarak uygular
                    self.render_current_page()
                    QMessageBox.information(self, "Başarılı", f"'{text}' kalıcı olarak sansürlendi.")
                else:
                    QMessageBox.information(self, "Bulunamadı", "Kelime bulunamadı.")

    def add_watermark(self):
        """Tüm sayfalara ortalanmış ve döndürülmüş bir şeffaf filigran ekler."""
        pdf_doc = self.get_active_doc()
        if pdf_doc:
            text, ok = QInputDialog.getText(self, 'Filigran', 'Filigran metnini girin (Örn: GİZLİ):')
            if ok and text:
                for page_idx in range(len(pdf_doc.doc)):
                    page = pdf_doc.doc.load_page(page_idx)
                    rect = page.rect
                    # Sayfanın ortasına büyük bir metin yerleştir
                    page.insert_text((rect.width/4, rect.height/2), text, fontsize=72,
                                     color=(0.8, 0.8, 0.8), rotate=45, fill_opacity=0.5)
                self.render_current_page()
                self.load_thumbnails()
                QMessageBox.information(self, "Başarılı", "Tüm sayfalara filigran eklendi.")

    def add_ink(self):
        """Belirli bir alana serbest çizim (imza çizgisi) simülasyonu ekler."""
        pdf_doc = self.get_active_doc()
        if pdf_doc:
            page = pdf_doc.doc.load_page(pdf_doc.current_page)
            # Fare olayları olmadan demo için rastgele dalgalı bir imza çizgisi çiziyoruz
            points = [(100, 200), (120, 180), (150, 210), (180, 190), (220, 200), (260, 180)]
            annot = page.add_ink_annot([points])
            annot.set_colors(stroke=(0, 0, 1)) # Mavi tükenmez kalem
            annot.update()
            self.render_current_page()
            QMessageBox.information(self, "Serbest Çizim", "Mavi tükenmez kalem izi eklendi.")

    def delete_current_page(self):
        pdf_doc = self.get_active_doc()
        if pdf_doc and len(pdf_doc.doc) > 1:
            reply = QMessageBox.question(self, 'Onay', 'Geçerli sayfayı silmek istediğinize emin misiniz?',
                                         QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if reply == QMessageBox.Yes:
                pdf_doc.doc.delete_page(pdf_doc.current_page)
                self.load_thumbnails()
                self.render_current_page()
        elif pdf_doc:
            QMessageBox.warning(self, "Uyarı", "Son kalan sayfayı silemezsiniz!")

    def insert_blank_page(self):
        pdf_doc = self.get_active_doc()
        if pdf_doc:
            # Geçerli sayfanın ardına boş sayfa ekle
            pdf_doc.doc.insert_page(pdf_doc.current_page + 1)
            pdf_doc.current_page += 1
            self.load_thumbnails()
            self.render_current_page()

    def extract_text(self):
        pdf_doc = self.get_active_doc()
        if pdf_doc:
            page = pdf_doc.doc.load_page(pdf_doc.current_page)
            text = page.get_text()
            self.text_edit.setPlainText(text)
            self.right_dock.setWindowTitle(f"Sayfa {pdf_doc.current_page + 1} Metni")
            self.right_dock.show()

    def show_info(self):
        pdf_doc = self.get_active_doc()
        if pdf_doc:
            info = pdf_doc.doc.metadata
            info_text = (
                f"<b>Dosya:</b> {pdf_doc.name}<br>"
                f"<b>Sayfa:</b> {len(pdf_doc.doc)}<br>"
                f"<b>Başlık:</b> {info.get('title', 'Bilinmiyor')}<br>"
                f"<b>Format:</b> {info.get('format', 'PDF')}"
            )
            QMessageBox.information(self, "Belge Bilgisi", info_text)

if __name__ == '__main__':
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    editor = PDFEditor()
    editor.show()
    sys.exit(app.exec_())

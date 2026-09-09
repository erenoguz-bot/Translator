import sys
import os
import fitz  # PyMuPDF
from PyQt5.QtWidgets import (QApplication, QMainWindow, QAction, QFileDialog,
                             QLabel, QScrollArea, QToolBar, QMessageBox,
                             QInputDialog, QDockWidget, QTextEdit, QVBoxLayout,
                             QWidget, QTabWidget, QListWidget, QListWidgetItem,
                             QSplitter, QStatusBar, QPushButton, QHBoxLayout)
from PyQt5.QtGui import QImage, QPixmap, QIcon, QKeySequence, QColor
from PyQt5.QtCore import Qt, QSize, QPointF

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
        self.setWindowTitle("Gelişmiş PDF Editör - Nitro Benzeri")
        self.setGeometry(100, 100, 1200, 800)

        self.documents = []  # List of PDFDocument instances
        self.active_doc_idx = -1

        self.initUI()
        self.setStyleSheet("""
            QMainWindow {
                background-color: #f0f0f0;
            }
            QToolBar {
                background-color: #e1e1e1;
                border-bottom: 1px solid #ccc;
                spacing: 5px;
            }
            QToolButton {
                background-color: transparent;
                border: 1px solid transparent;
                padding: 4px;
                border-radius: 4px;
            }
            QToolButton:hover {
                background-color: #d1d1d1;
                border: 1px solid #aaa;
            }
            QTabWidget::pane {
                border: 1px solid #ccc;
                background: white;
            }
            QTabBar::tab {
                background: #e1e1e1;
                border: 1px solid #ccc;
                padding: 8px 15px;
                margin-right: 2px;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
            }
            QTabBar::tab:selected {
                background: white;
                border-bottom-color: white;
            }
            QListWidget {
                border: none;
                background-color: #fafafa;
            }
            QListWidget::item:selected {
                background-color: #cce8ff;
                border: 1px solid #99d1ff;
            }
        """)

    def initUI(self):
        # 1. Menü Çubuğu (Menu Bar)
        menubar = self.menuBar()
        fileMenu = menubar.addMenu('Dosya')

        # Dosya Menüsü Aksiyonları
        openAct = QAction('Dosya Aç...', self)
        openAct.setShortcut('Ctrl+O')
        openAct.triggered.connect(self.openPDF)
        fileMenu.addAction(openAct)

        closeTabAct = QAction('Sekmeyi Kapat', self)
        closeTabAct.setShortcut('Ctrl+W')
        closeTabAct.triggered.connect(self.close_current_tab)
        fileMenu.addAction(closeTabAct)

        saveAct = QAction('Farklı Kaydet...', self)
        saveAct.setShortcut('Ctrl+S')
        saveAct.triggered.connect(self.savePDF)
        fileMenu.addAction(saveAct)

        fileMenu.addSeparator()

        exitAct = QAction('Çıkış', self)
        exitAct.setShortcut('Ctrl+Q')
        exitAct.triggered.connect(self.close)
        fileMenu.addAction(exitAct)

        # 2. Ana Araç Çubuğu (Ribbon benzeri)
        toolbar = QToolBar("Ana Araç Çubuğu")
        toolbar.setIconSize(QSize(24, 24))
        self.addToolBar(toolbar)

        # Araçlar
        toolbar.addAction(openAct)
        toolbar.addAction(saveAct)
        toolbar.addSeparator()

        # Sayfa Gezinme
        self.prevPageAct = QAction('◀ Önceki Sayfa', self)
        self.prevPageAct.triggered.connect(self.prev_page)
        toolbar.addAction(self.prevPageAct)

        self.nextPageAct = QAction('Sonraki Sayfa ▶', self)
        self.nextPageAct.triggered.connect(self.next_page)
        toolbar.addAction(self.nextPageAct)

        toolbar.addSeparator()

        # Yakınlaştırma/Uzaklaştırma
        zoomInAct = QAction('🔍 Yakınlaştır', self)
        zoomInAct.setShortcut('Ctrl++')
        zoomInAct.triggered.connect(self.zoom_in)
        toolbar.addAction(zoomInAct)

        zoomOutAct = QAction('🔍 Uzaklaştır', self)
        zoomOutAct.setShortcut('Ctrl+-')
        zoomOutAct.triggered.connect(self.zoom_out)
        toolbar.addAction(zoomOutAct)

        toolbar.addSeparator()

        # Döndürme
        rotateAct = QAction('↻ Sayfayı Döndür (Kalıcı)', self)
        rotateAct.setShortcut('Ctrl+R')
        rotateAct.triggered.connect(self.rotate_page)
        toolbar.addAction(rotateAct)

        toolbar.addSeparator()

        # Düzenleme Araçları
        addTextAct = QAction('✍️ Metin Ekle', self)
        addTextAct.triggered.connect(self.add_text_annotation)
        toolbar.addAction(addTextAct)

        highlightAct = QAction('🖍️ Vurgula (Arama ile)', self)
        highlightAct.triggered.connect(self.highlight_search_text)
        toolbar.addAction(highlightAct)

        toolbar.addSeparator()

        # Ekstra Araçlar
        extractTextAct = QAction('📝 Metni Çıkar', self)
        extractTextAct.triggered.connect(self.extract_text)
        toolbar.addAction(extractTextAct)

        searchAct = QAction('🔎 Ara', self)
        searchAct.setShortcut('Ctrl+F')
        searchAct.triggered.connect(self.search_text)
        toolbar.addAction(searchAct)

        infoAct = QAction('ℹ️ Belge Bilgisi', self)
        infoAct.triggered.connect(self.show_info)
        toolbar.addAction(infoAct)

        # 3. Ana Arayüz (Splitter: Sol Panel + Orta Sekmeler + Sağ Panel)
        main_splitter = QSplitter(Qt.Horizontal)
        self.setCentralWidget(main_splitter)

        # Sol Panel (Sayfa Küçük Resimleri - Thumbnails)
        self.thumbnail_list = QListWidget()
        self.thumbnail_list.setIconSize(QSize(100, 150))
        self.thumbnail_list.setResizeMode(QListWidget.Adjust)
        self.thumbnail_list.setSpacing(10)
        self.thumbnail_list.itemClicked.connect(self.thumbnail_clicked)

        left_dock = QDockWidget("Sayfalar", self)
        left_dock.setWidget(self.thumbnail_list)
        left_dock.setFeatures(QDockWidget.DockWidgetClosable | QDockWidget.DockWidgetMovable)
        self.addDockWidget(Qt.LeftDockWidgetArea, left_dock)

        # Orta Panel (Sekmeli PDF Görüntüleyici)
        self.tabs = QTabWidget()
        self.tabs.setTabsClosable(True)
        self.tabs.tabCloseRequested.connect(self.close_tab)
        self.tabs.currentChanged.connect(self.tab_changed)
        main_splitter.addWidget(self.tabs)

        # Sağ Panel (Metin Çıkarma, Özellikler vb.)
        self.right_dock = QDockWidget("Araçlar / Metin Çıkarımı", self)
        self.right_dock.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)
        self.text_edit = QTextEdit()
        self.text_edit.setReadOnly(True)
        self.right_dock.setWidget(self.text_edit)
        self.addDockWidget(Qt.RightDockWidgetArea, self.right_dock)
        self.right_dock.hide() # Başlangıçta gizli

        # 4. Durum Çubuğu (Status Bar)
        self.statusbar = QStatusBar()
        self.setStatusBar(self.statusbar)
        self.page_info_label = QLabel("Sayfa: 0 / 0")
        self.zoom_info_label = QLabel("Yakınlaştırma: 100%")
        self.statusbar.addPermanentWidget(self.page_info_label)
        self.statusbar.addPermanentWidget(self.zoom_info_label)

        # Başlangıç Durumu
        self.update_ui_state()

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
            self.zoom_info_label.setText("Yakınlaştırma: 100%")

    def openPDF(self):
        options = QFileDialog.Options()
        fileName, _ = QFileDialog.getOpenFileName(self, "PDF Dosyası Aç", "", "PDF Files (*.pdf)", options=options)
        if fileName:
            try:
                # Yeni doküman objesi oluştur
                pdf_doc = PDFDocument(fileName)
                self.documents.append(pdf_doc)
                self.active_doc_idx = len(self.documents) - 1

                # Yeni sekme için UI oluştur
                scroll_area = QScrollArea()
                image_label = QLabel()
                image_label.setAlignment(Qt.AlignCenter)
                # Gri arkaplan
                scroll_area.setStyleSheet("background-color: #525659;")
                scroll_area.setWidget(image_label)
                scroll_area.setWidgetResizable(True)

                # Sekmeyi ekle
                idx = self.tabs.addTab(scroll_area, pdf_doc.name)
                self.tabs.setCurrentIndex(idx)

                # Görünümü güncelle
                self.load_thumbnails()
                self.render_current_page()
                self.update_ui_state()

            except Exception as e:
                QMessageBox.critical(self, "Hata", f"PDF açılamadı:\n{str(e)}")

    def close_current_tab(self):
        idx = self.tabs.currentIndex()
        if idx != -1:
            self.close_tab(idx)

    def close_tab(self, index):
        if 0 <= index < len(self.documents):
            # Önce dokümanı kapat ve listeden çıkar, böylece UI sinyalleri tetiklendiğinde hata oluşmaz
            doc_to_close = self.documents.pop(index)
            doc_to_close.doc.close()
            widget_to_remove = self.tabs.widget(index)
            self.tabs.removeTab(index)
            if widget_to_remove:
                widget_to_remove.deleteLater()

            if len(self.documents) == 0:
                self.active_doc_idx = -1
            else:
                # Geçerli sekmeyi güncelle
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
            options = QFileDialog.Options()
            fileName, _ = QFileDialog.getSaveFileName(self, "PDF'i Farklı Kaydet", pdf_doc.name, "PDF Files (*.pdf)", options=options)
            if fileName:
                try:
                    pdf_doc.doc.save(fileName)
                    QMessageBox.information(self, "Başarılı", "PDF başarıyla kaydedildi.\n(Değişiklikler kalıcı olarak kaydedildi.)")
                except Exception as e:
                    QMessageBox.critical(self, "Hata", f"PDF kaydedilemedi:\n{str(e)}")

    def load_thumbnails(self):
        self.thumbnail_list.clear()
        pdf_doc = self.get_active_doc()
        if not pdf_doc:
            return

        # Sadece performans için ilk 50 sayfayı veya hepsini yükle
        num_pages_to_load = min(len(pdf_doc.doc), 50)

        for i in range(num_pages_to_load):
            page = pdf_doc.doc.load_page(i)
            mat = fitz.Matrix(0.2, 0.2)
            pix = page.get_pixmap(matrix=mat)
            img = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format_RGB888)
            pixmap = QPixmap.fromImage(img)

            icon = QIcon(pixmap)
            item = QListWidgetItem(icon, f"Sayfa {i+1}")
            item.setTextAlignment(Qt.AlignCenter)
            item.setData(Qt.UserRole, i)
            self.thumbnail_list.addItem(item)

        if len(pdf_doc.doc) > 50:
            item = QListWidgetItem(f"... ve {len(pdf_doc.doc)-50} sayfa daha")
            item.setTextAlignment(Qt.AlignCenter)
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

        if not pdf_doc or not scroll_area:
            return

        if pdf_doc.current_page < 0:
            pdf_doc.current_page = 0
        elif pdf_doc.current_page >= len(pdf_doc.doc):
            pdf_doc.current_page = len(pdf_doc.doc) - 1

        page = pdf_doc.doc.load_page(pdf_doc.current_page)

        # Sadece zoom'u dikkate alıyoruz, rotasyon dökümanın kalıcı rotasyonundan gelir.
        mat = fitz.Matrix(pdf_doc.zoom_factor, pdf_doc.zoom_factor)

        pix = page.get_pixmap(matrix=mat)
        img = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format_RGB888)

        image_label = scroll_area.widget()
        image_label.setPixmap(QPixmap.fromImage(img))

        self.page_info_label.setText(f"Sayfa: {pdf_doc.current_page + 1} / {len(pdf_doc.doc)}")
        self.zoom_info_label.setText(f"Yakınlaştırma: {int(pdf_doc.zoom_factor * 100)}%")

        if pdf_doc.current_page < self.thumbnail_list.count():
            self.thumbnail_list.setCurrentRow(pdf_doc.current_page)

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
        """Kalıcı olarak sayfayı döndürür"""
        pdf_doc = self.get_active_doc()
        if pdf_doc:
            page = pdf_doc.doc.load_page(pdf_doc.current_page)
            rotation = page.rotation
            page.set_rotation((rotation + 90) % 360)
            self.render_current_page()

    def add_text_annotation(self):
        """Sayfaya basit bir metin notasyon (FreeText) ekler"""
        pdf_doc = self.get_active_doc()
        if pdf_doc:
            text, ok = QInputDialog.getText(self, 'Metin Ekle', 'Eklenecek metni girin:')
            if ok and text:
                page = pdf_doc.doc.load_page(pdf_doc.current_page)
                # Metni sayfanın orta-üst kısmına ekler
                rect = fitz.Rect(50, 50, 300, 100)
                annot = page.add_freetext_annot(rect, text, fontsize=14, fontname="helv", text_color=(1, 0, 0))
                annot.update()
                self.render_current_page()
                QMessageBox.information(self, "Başarılı", "Metin eklendi. Düzenlemeleri kalıcı yapmak için Farklı Kaydet'i kullanın.")

    def highlight_search_text(self):
        """Kullanıcının girdiği kelimeyi sayfada bulup kalıcı olarak vurgular (Highlight)"""
        pdf_doc = self.get_active_doc()
        if pdf_doc:
            text, ok = QInputDialog.getText(self, 'Vurgulanacak Metin', 'Bulunup vurgulanacak kelimeyi girin:')
            if ok and text:
                page = pdf_doc.doc.load_page(pdf_doc.current_page)
                text_instances = page.search_for(text)
                if text_instances:
                    for inst in text_instances:
                        annot = page.add_highlight_annot(inst)
                        annot.update()
                    self.render_current_page()
                    QMessageBox.information(self, "Başarılı", f"'{text}' bulundu ve vurgulandı.")
                else:
                    QMessageBox.information(self, "Bulunamadı", f"'{text}' bu sayfada bulunamadı.")

    def extract_text(self):
        pdf_doc = self.get_active_doc()
        if pdf_doc:
            page = pdf_doc.doc.load_page(pdf_doc.current_page)
            text = page.get_text()
            self.text_edit.setPlainText(text)
            self.right_dock.setWindowTitle(f"Sayfa {pdf_doc.current_page + 1} Metni")
            self.right_dock.show()

    def search_text(self):
        pdf_doc = self.get_active_doc()
        if pdf_doc:
            text, ok = QInputDialog.getText(self, 'Belgede Ara', 'Aranacak kelime veya cümleyi girin:')
            if ok and text:
                total_found = 0
                first_found_page = -1

                # Tüm sayfaları ara
                for i in range(len(pdf_doc.doc)):
                    page = pdf_doc.doc.load_page(i)
                    text_instances = page.search_for(text)
                    if text_instances:
                        total_found += len(text_instances)
                        if first_found_page == -1:
                            first_found_page = i

                if total_found > 0:
                    QMessageBox.information(self, "Arama Sonucu",
                        f"'{text}' ifadesi belgede toplam {total_found} kez bulundu.\nİlk bulunduğu sayfaya gidiliyor.")
                    pdf_doc.current_page = first_found_page
                    self.render_current_page()
                else:
                    QMessageBox.information(self, "Bulunamadı", f"'{text}' ifadesi belgede bulunamadı.")

    def show_info(self):
        pdf_doc = self.get_active_doc()
        if pdf_doc:
            info = pdf_doc.doc.metadata
            file_size_kb = os.path.getsize(pdf_doc.file_path) / 1024

            info_text = (
                f"<b>Dosya Adı:</b> {pdf_doc.name}<br>"
                f"<b>Dosya Boyutu:</b> {file_size_kb:.2f} KB<br>"
                f"<b>Sayfa Sayısı:</b> {len(pdf_doc.doc)}<br><br>"
                f"<b>Başlık:</b> {info.get('title', 'Bilinmiyor')}<br>"
                f"<b>Yazar:</b> {info.get('author', 'Bilinmiyor')}<br>"
                f"<b>Oluşturan (Creator):</b> {info.get('creator', 'Bilinmiyor')}<br>"
                f"<b>Uygulama (Producer):</b> {info.get('producer', 'Bilinmiyor')}<br>"
                f"<b>Oluşturulma Tarihi:</b> {info.get('creationDate', 'Bilinmiyor')}<br>"
                f"<b>Format:</b> {info.get('format', 'PDF')}"
            )
            QMessageBox.information(self, "Belge Özellikleri", info_text)
        else:
            QMessageBox.warning(self, "Uyarı", "Lütfen önce bir PDF belgesi açın.")

if __name__ == '__main__':
    app = QApplication(sys.argv)
    app.setStyle("Fusion") # Modern bir görünüm için
    editor = PDFEditor()
    editor.show()
    sys.exit(app.exec_())

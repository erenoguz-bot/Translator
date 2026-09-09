import sys
import os
import pymupdf  # Previously fitz
import qtawesome as qta
from PyQt5.QtWidgets import (QApplication, QMainWindow, QAction, QFileDialog,
                             QLabel, QScrollArea, QToolBar, QMessageBox,
                             QInputDialog, QDockWidget, QTextEdit, QVBoxLayout,
                             QWidget, QTabWidget, QListWidget, QListWidgetItem,
                             QSplitter, QStatusBar, QPushButton, QHBoxLayout)
from PyQt5.QtGui import QImage, QPixmap, QIcon, QPainter, QPen, QColor
from PyQt5.QtCore import Qt, QSize, QPoint, QRect

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
QToolButton:pressed, QToolButton:checked {
    background-color: #007acc;
    border: 1px solid #005c99;
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
QStatusBar {
    background-color: #007acc;
    color: white;
}
QScrollBar:vertical, QScrollBar:horizontal {
    border: none;
    background: #2b2b2b;
}
"""

class PDFDocument:
    def __init__(self, file_path):
        self.file_path = file_path
        self.name = os.path.basename(file_path)
        self.doc = pymupdf.open(file_path)
        self.current_page = 0
        self.zoom_factor = 1.5

class InteractiveCanvas(QLabel):
    def __init__(self, pdf_doc, update_callback, parent_window):
        super().__init__()
        self.pdf_doc = pdf_doc
        self.update_callback = update_callback
        self.parent_window = parent_window

        self.setAlignment(Qt.AlignCenter)
        self.setMouseTracking(True)

        self.active_tool = 'select'

        self.drawing = False
        self.last_point = QPoint()
        self.current_ink_points = []

        self.selecting = False
        self.start_pos = QPoint()
        self.current_rect = QRect()

    def set_active_tool(self, tool_name):
        self.active_tool = tool_name
        if tool_name == 'select':
            self.setCursor(Qt.ArrowCursor)
        elif tool_name == 'ink':
            self.setCursor(Qt.CrossCursor)
        elif tool_name in ['highlight', 'redact']:
            self.setCursor(Qt.IBeamCursor)
        elif tool_name in ['edit_text', 'delete_image']:
            self.setCursor(Qt.PointingHandCursor)

    def map_to_pdf_coord(self, screen_point):
        if not self.pixmap():
            return None
        px_x_offset = (self.width() - self.pixmap().width()) // 2
        px_y_offset = (self.height() - self.pixmap().height()) // 2
        real_x = (screen_point.x() - px_x_offset) / self.pdf_doc.zoom_factor
        real_y = (screen_point.y() - px_y_offset) / self.pdf_doc.zoom_factor
        return (real_x, real_y)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            if self.active_tool == 'ink':
                self.drawing = True
                self.last_point = event.pos()
                pdf_point = self.map_to_pdf_coord(event.pos())
                if pdf_point:
                    self.current_ink_points = [pdf_point]

            elif self.active_tool in ['highlight', 'redact']:
                self.selecting = True
                self.start_pos = event.pos()
                self.current_rect = QRect(self.start_pos, self.start_pos)
                self.update()

            elif self.active_tool == 'edit_text':
                pdf_point = self.map_to_pdf_coord(event.pos())
                if pdf_point:
                    self.handle_edit_text(pdf_point)

            elif self.active_tool == 'delete_image':
                pdf_point = self.map_to_pdf_coord(event.pos())
                if pdf_point:
                    self.handle_delete_image(pdf_point)

    def mouseMoveEvent(self, event):
        if (event.buttons() & Qt.LeftButton):
            if self.drawing and self.active_tool == 'ink':
                pdf_point = self.map_to_pdf_coord(event.pos())
                if pdf_point:
                    self.current_ink_points.append(pdf_point)
                self.last_point = event.pos()
                self.update()

            elif self.selecting and self.active_tool in ['highlight', 'redact']:
                self.current_rect = QRect(self.start_pos, event.pos()).normalized()
                self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            if self.drawing and self.active_tool == 'ink':
                self.drawing = False
                if len(self.current_ink_points) > 1:
                    page = self.pdf_doc.doc.load_page(self.pdf_doc.current_page)
                    annot = page.add_ink_annot([self.current_ink_points])
                    annot.set_colors(stroke=(0.2, 0.5, 1.0))
                    annot.update()
                self.current_ink_points = []
                self.update_callback()

            elif self.selecting and self.active_tool in ['highlight', 'redact']:
                self.selecting = False
                page = self.pdf_doc.doc.load_page(self.pdf_doc.current_page)
                top_left = self.map_to_pdf_coord(self.current_rect.topLeft())
                bottom_right = self.map_to_pdf_coord(self.current_rect.bottomRight())

                if top_left and bottom_right:
                    rect = pymupdf.Rect(top_left[0], top_left[1], bottom_right[0], bottom_right[1])
                    if self.active_tool == 'highlight':
                        annot = page.add_highlight_annot(rect)
                        annot.update()
                    elif self.active_tool == 'redact':
                        page.add_redact_annot(rect, fill=(0, 0, 0))
                        page.apply_redactions()

                self.current_rect = QRect()
                self.update_callback()

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        if self.selecting and self.active_tool in ['highlight', 'redact']:
            color = QColor(255, 255, 0, 100) if self.active_tool == 'highlight' else QColor(0, 0, 0, 200)
            painter.setBrush(color)
            painter.setPen(QPen(Qt.black, 1, Qt.DashLine))
            painter.drawRect(self.current_rect)

    def handle_edit_text(self, pt):
        page = self.pdf_doc.doc.load_page(self.pdf_doc.current_page)
        p = pymupdf.Point(pt[0], pt[1])
        blocks = page.get_text("dict")["blocks"]
        for b in blocks:
            if b['type'] == 0: # Text block
                r = pymupdf.Rect(b['bbox'])
                if r.contains(p):
                    text = ""
                    for l in b["lines"]:
                        for s in l["spans"]:
                            text += s["text"]

                    new_text, ok = QInputDialog.getText(self.parent_window, 'Metin Düzenle', 'Yeni metni girin:', text=text)
                    if ok and new_text != text:
                        # Gelişmiş düzenleme simülasyonu: Eskisini beyaza boya, yenisini yaz
                        page.add_redact_annot(r, fill=(1, 1, 1))
                        page.apply_redactions()
                        # Yenisini yerleştir (aynı font size ve koordinatlarla yaklaşık olarak)
                        # Enterprise seviyesinde font eşleştirme çok zordur, standart bir font ile yazıyoruz.
                        fontsize = b["lines"][0]["spans"][0]["size"]
                        page.insert_textbox(r, new_text, fontsize=fontsize, fontname="helv", color=(0,0,0))
                        self.update_callback()
                        QMessageBox.information(self.parent_window, "Başarılı", "Metin başarıyla değiştirildi.")
                    return

    def handle_delete_image(self, pt):
        page = self.pdf_doc.doc.load_page(self.pdf_doc.current_page)
        p = pymupdf.Point(pt[0], pt[1])
        # Resimleri bul ve kontrol et
        img_list = page.get_image_info()
        for img in img_list:
            r = pymupdf.Rect(img['bbox'])
            if r.contains(p):
                reply = QMessageBox.question(self.parent_window, 'Görsel Sil', 'Tıklanan görseli PDF üzerinden silmek istediğinize emin misiniz?',
                                         QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
                if reply == QMessageBox.Yes:
                    page.add_redact_annot(r, fill=(1, 1, 1))
                    page.apply_redactions()
                    self.update_callback()
                return
        QMessageBox.information(self.parent_window, "Bilgi", "Bu noktada düzenlenebilir bir görsel veya metin bulunamadı.")


class PDFEditor(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Nitro PDF Pro Enterprise - Tam Denetim")
        self.setGeometry(50, 50, 1400, 900)
        self.documents = []
        self.active_doc_idx = -1

        self.setStyleSheet(DARK_THEME_QSS)
        self.initUI()

    def initUI(self):
        # Üst Ribbon Araç Çubuğu
        self.toolbar = QToolBar("Ana Ribbon")
        self.toolbar.setIconSize(QSize(24, 24))
        self.toolbar.setMovable(False)
        self.addToolBar(self.toolbar)

        # --- DOSYA VE SİSTEM GRUBU ---
        openAct = QAction(qta.icon('fa5s.folder-open', color='white'), 'Aç', self)
        openAct.triggered.connect(self.openPDF)
        self.toolbar.addAction(openAct)

        saveAct = QAction(qta.icon('fa5s.save', color='white'), 'Kaydet', self)
        saveAct.triggered.connect(self.savePDF)
        self.toolbar.addAction(saveAct)
        self.toolbar.addSeparator()

        # --- ARAÇ SEÇİM GRUBU ---
        self.toolGroup = []

        self.selectAct = QAction(qta.icon('fa5s.mouse-pointer', color='white'), 'Seç', self)
        self.selectAct.setCheckable(True)
        self.selectAct.setChecked(True)
        self.selectAct.triggered.connect(lambda: self.set_global_tool('select'))
        self.toolbar.addAction(self.selectAct)
        self.toolGroup.append(self.selectAct)

        self.editTextAct = QAction(qta.icon('fa5s.edit', color='#4dabf7'), 'Metin Düzenle', self)
        self.editTextAct.setToolTip("PDF üzerindeki mevcut bir metne tıklayarak değiştirin (Enterprise Edit)")
        self.editTextAct.setCheckable(True)
        self.editTextAct.triggered.connect(lambda: self.set_global_tool('edit_text'))
        self.toolbar.addAction(self.editTextAct)
        self.toolGroup.append(self.editTextAct)

        self.delImageAct = QAction(qta.icon('fa5s.image', color='#ff6b6b'), 'Görsel Sil', self)
        self.delImageAct.setToolTip("PDF üzerindeki bir görsele tıklayarak silin")
        self.delImageAct.setCheckable(True)
        self.delImageAct.triggered.connect(lambda: self.set_global_tool('delete_image'))
        self.toolbar.addAction(self.delImageAct)
        self.toolGroup.append(self.delImageAct)

        self.inkAct = QAction(qta.icon('fa5s.pen', color='#4dabf7'), 'Çizim', self)
        self.inkAct.setToolTip("Sayfa üzerinde serbest çizim yapın")
        self.inkAct.setCheckable(True)
        self.inkAct.triggered.connect(lambda: self.set_global_tool('ink'))
        self.toolbar.addAction(self.inkAct)
        self.toolGroup.append(self.inkAct)

        self.highlightAct = QAction(qta.icon('fa5s.highlighter', color='#fcc419'), 'Vurgula', self)
        self.highlightAct.setToolTip("Fare ile bir alan seçerek sarı renkle vurgulayın")
        self.highlightAct.setCheckable(True)
        self.highlightAct.triggered.connect(lambda: self.set_global_tool('highlight'))
        self.toolbar.addAction(self.highlightAct)
        self.toolGroup.append(self.highlightAct)

        self.redactAct = QAction(qta.icon('fa5s.eraser', color='#ff6b6b'), 'Sansürle', self)
        self.redactAct.setToolTip("Fare ile seçtiğiniz alanı siyah bir kutuyla kaplayıp gizleyin")
        self.redactAct.setCheckable(True)
        self.redactAct.triggered.connect(lambda: self.set_global_tool('redact'))
        self.toolbar.addAction(self.redactAct)
        self.toolGroup.append(self.redactAct)

        self.toolbar.addSeparator()

        addTextAct = QAction(qta.icon('fa5s.font', color='#4dabf7'), 'Yazı Ekle', self)
        addTextAct.triggered.connect(self.add_text_annotation)
        self.toolbar.addAction(addTextAct)

        self.toolbar.addSeparator()

        # --- GÖRÜNÜM & GEZİNME GRUBU ---
        self.prevPageAct = QAction(qta.icon('fa5s.chevron-left', color='white'), 'Önceki', self)
        self.prevPageAct.triggered.connect(self.prev_page)
        self.toolbar.addAction(self.prevPageAct)

        self.nextPageAct = QAction(qta.icon('fa5s.chevron-right', color='white'), 'Sonraki', self)
        self.nextPageAct.triggered.connect(self.next_page)
        self.toolbar.addAction(self.nextPageAct)

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

        delPageAct = QAction(qta.icon('fa5s.file-excel', color='#ff6b6b'), 'Sayfa Sil', self)
        delPageAct.triggered.connect(self.delete_current_page)
        self.toolbar.addAction(delPageAct)

        insertPageAct = QAction(qta.icon('fa5s.file-medical', color='#20c997'), 'Boş Sayfa', self)
        insertPageAct.triggered.connect(self.insert_blank_page)
        self.toolbar.addAction(insertPageAct)

        self.toolbar.addSeparator()

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

        # Status Bar
        self.statusbar = QStatusBar()
        self.setStatusBar(self.statusbar)
        self.page_info_label = QLabel("Sayfa: 0 / 0")
        self.zoom_info_label = QLabel("Zoom: 100%")
        self.tool_info_label = QLabel("Aktif Araç: Seçim")
        self.statusbar.addPermanentWidget(self.tool_info_label)
        self.statusbar.addPermanentWidget(self.page_info_label)
        self.statusbar.addPermanentWidget(self.zoom_info_label)

    def set_global_tool(self, tool_name):
        for action in self.toolGroup:
            if action.text() == 'Seç' and tool_name == 'select': action.setChecked(True)
            elif action.text() == 'Metin Düzenle' and tool_name == 'edit_text': action.setChecked(True)
            elif action.text() == 'Görsel Sil' and tool_name == 'delete_image': action.setChecked(True)
            elif action.text() == 'Çizim' and tool_name == 'ink': action.setChecked(True)
            elif action.text() == 'Vurgula' and tool_name == 'highlight': action.setChecked(True)
            elif action.text() == 'Sansürle' and tool_name == 'redact': action.setChecked(True)
            else: action.setChecked(False)

        tool_texts = {'select': 'Seçim', 'edit_text': 'Tıklayarak Metin Düzenleme', 'delete_image': 'Tıklayarak Görsel Silme',
                      'ink': 'Serbest Çizim', 'highlight': 'Seçim Vurgulama', 'redact': 'Kutu Sansürleme'}
        self.tool_info_label.setText(f"Aktif Araç: {tool_texts.get(tool_name, 'Bilinmiyor')}")

        for i in range(self.tabs.count()):
            scroll_area = self.tabs.widget(i)
            canvas = scroll_area.widget()
            if isinstance(canvas, InteractiveCanvas):
                canvas.set_active_tool(tool_name)

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
        if not has_doc:
            self.thumbnail_list.clear()
            self.page_info_label.setText("Sayfa: 0 / 0")
            self.zoom_info_label.setText("Zoom: 100%")

    def openPDF(self):
        fileName, _ = QFileDialog.getOpenFileName(self, "PDF Aç", "", "PDF Dosyaları (*.pdf)")
        if fileName:
            try:
                pdf_doc = PDFDocument(fileName)
                self.documents.append(pdf_doc)
                self.active_doc_idx = len(self.documents) - 1

                scroll_area = QScrollArea()
                canvas = InteractiveCanvas(pdf_doc, self.render_current_page, self)
                scroll_area.setStyleSheet("background-color: #1e1e1e;")
                scroll_area.setWidget(canvas)
                scroll_area.setWidgetResizable(True)

                idx = self.tabs.addTab(scroll_area, pdf_doc.name)
                self.tabs.setCurrentIndex(idx)

                active_tool = 'select'
                for action in self.toolGroup:
                    if action.isChecked():
                        if action.text() == 'Çizim': active_tool = 'ink'
                        elif action.text() == 'Vurgula': active_tool = 'highlight'
                        elif action.text() == 'Sansürle': active_tool = 'redact'
                        elif action.text() == 'Metin Düzenle': active_tool = 'edit_text'
                        elif action.text() == 'Görsel Sil': active_tool = 'delete_image'
                canvas.set_active_tool(active_tool)

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

    def load_thumbnails(self):
        self.thumbnail_list.clear()
        pdf_doc = self.get_active_doc()
        if not pdf_doc: return

        num_pages = min(len(pdf_doc.doc), 50)
        for i in range(num_pages):
            page = pdf_doc.doc.load_page(i)
            mat = pymupdf.Matrix(0.15, 0.15)
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
        mat = pymupdf.Matrix(pdf_doc.zoom_factor, pdf_doc.zoom_factor)
        pix = page.get_pixmap(matrix=mat)
        img = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format_RGB888)

        canvas = scroll_area.widget()
        canvas.setPixmap(QPixmap.fromImage(img))

        self.page_info_label.setText(f"Sayfa: {pdf_doc.current_page + 1} / {len(pdf_doc.doc)}")
        self.zoom_info_label.setText(f"Zoom: {int(pdf_doc.zoom_factor * 100)}%")

        if pdf_doc.current_page < self.thumbnail_list.count():
            self.thumbnail_list.setCurrentRow(pdf_doc.current_page)

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
            self.load_thumbnails()

    def add_text_annotation(self):
        pdf_doc = self.get_active_doc()
        if pdf_doc:
            text, ok = QInputDialog.getText(self, 'Metin Ekle', 'Eklenecek metni girin:')
            if ok and text:
                page = pdf_doc.doc.load_page(pdf_doc.current_page)
                rect = pymupdf.Rect(100, 100, 400, 150)
                annot = page.add_freetext_annot(rect, text, fontsize=16, fontname="helv", text_color=(1, 0, 0))
                annot.update()
                self.render_current_page()

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
            pdf_doc.doc.insert_page(pdf_doc.current_page + 1)
            pdf_doc.current_page += 1
            self.load_thumbnails()
            self.render_current_page()

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

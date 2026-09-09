import sys
import os
import pymupdf
import qtawesome as qta
from PyQt5.QtWidgets import (QApplication, QMainWindow, QAction, QFileDialog,
                             QLabel, QScrollArea, QToolBar, QMessageBox,
                             QInputDialog, QDockWidget, QVBoxLayout, QWidget,
                             QTabWidget, QListWidget, QListWidgetItem, QSplitter,
                             QStatusBar, QPushButton, QHBoxLayout, QGraphicsView,
                             QGraphicsScene, QGraphicsPixmapItem, QGraphicsRectItem,
                             QGraphicsTextItem, QGraphicsItem, QToolButton, QFormLayout,
                             QSpinBox, QColorDialog, QFrame, QSizePolicy)
from PyQt5.QtGui import (QImage, QPixmap, QIcon, QPainter, QPen, QColor, QFont,
                         QBrush, QCursor, QPainterPath)
from PyQt5.QtCore import Qt, QSize, QPointF, QRectF, pyqtSignal

# --- MODERN THEME (Windows 11 / Fluent Style) ---
MODERN_THEME_QSS = """
QMainWindow {
    background-color: #f3f3f3;
}
QToolBar {
    background-color: #ffffff;
    border-bottom: 1px solid #dcdcdc;
    padding: 3px;
    spacing: 5px;
}
QToolButton {
    background-color: transparent;
    border: none;
    padding: 5px 10px;
    border-radius: 4px;
    font-size: 12px;
    color: #333333;
}
QToolButton:hover {
    background-color: #e5f1fb;
}
QToolButton:checked {
    background-color: #cce4f7;
    border: 1px solid #0078d4;
}
/* Ribbon Tabs */
QTabWidget::pane {
    border: none;
    border-top: 1px solid #dcdcdc;
    background: #ffffff;
}
QTabBar::tab {
    background: transparent;
    color: #555555;
    padding: 6px 16px;
    border: none;
    border-bottom: 3px solid transparent;
}
QTabBar::tab:selected {
    color: #0078d4;
    border-bottom: 3px solid #0078d4;
}
QTabBar::tab:hover {
    background: #f3f3f3;
}
QDockWidget {
    color: #333333;
    font-weight: bold;
}
QDockWidget::title {
    background: #eaeaea;
    padding: 6px;
    border-bottom: 1px solid #dcdcdc;
}
QListWidget {
    background-color: #fafafa;
    border: none;
}
QListWidget::item:selected {
    background-color: #cce4f7;
    color: #000;
    border: 1px solid #0078d4;
}
QGraphicsView {
    background-color: #cccccc;
    border: none;
}
QStatusBar {
    background-color: #ffffff;
    border-top: 1px solid #dcdcdc;
    color: #555555;
}
"""

class PDFDocument:
    def __init__(self, file_path):
        self.file_path = file_path
        self.name = os.path.basename(file_path)
        self.doc = pymupdf.open(file_path)
        self.current_page = 0
        self.zoom_factor = 1.0

class PDFGraphicsView(QGraphicsView):
    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        self.scene = QGraphicsScene(self)
        self.setScene(self.scene)

        self.setRenderHint(QPainter.Antialiasing)
        self.setRenderHint(QPainter.TextAntialiasing)
        self.setRenderHint(QPainter.SmoothPixmapTransform)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.AnchorUnderMouse)
        self.setDragMode(QGraphicsView.NoDrag)

        self.pdf_pixmap_item = None
        self.pdf_doc = None

        # Tools: 'select', 'pan', 'highlight', 'text', 'redact', 'ink'
        self.active_tool = 'select'

        self.drawing = False
        self.start_pos = QPointF()
        self.current_rect_item = None
        self.current_ink_path = QPainterPath()
        self.current_ink_item = None

    def set_document(self, pdf_doc):
        self.pdf_doc = pdf_doc
        self.render_page()

    def render_page(self):
        if not self.pdf_doc: return
        self.scene.clear()

        page = self.pdf_doc.doc.load_page(self.pdf_doc.current_page)
        mat = pymupdf.Matrix(self.pdf_doc.zoom_factor * 2, self.pdf_doc.zoom_factor * 2) # High DPI
        pix = page.get_pixmap(matrix=mat)
        img = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format_RGB888)

        self.pdf_pixmap_item = QGraphicsPixmapItem(QPixmap.fromImage(img))
        self.scene.addItem(self.pdf_pixmap_item)
        self.setSceneRect(self.pdf_pixmap_item.boundingRect())

        # Render visual shadow for the page
        shadow = QGraphicsRectItem(self.pdf_pixmap_item.boundingRect())
        shadow.setBrush(QColor(0, 0, 0, 0))
        shadow.setPen(QPen(QColor("#999999"), 2))
        self.scene.addItem(shadow)
        shadow.setZValue(10)

    def set_active_tool(self, tool):
        self.active_tool = tool
        if tool == 'pan':
            self.setDragMode(QGraphicsView.ScrollHandDrag)
        else:
            self.setDragMode(QGraphicsView.NoDrag)
            if tool == 'select': self.setCursor(Qt.ArrowCursor)
            elif tool in ['highlight', 'redact']: self.setCursor(Qt.CrossCursor)
            elif tool == 'text': self.setCursor(Qt.IBeamCursor)
            elif tool == 'ink': self.setCursor(Qt.CrossCursor)

    def wheelEvent(self, event):
        if event.modifiers() == Qt.ControlModifier:
            if event.angleDelta().y() > 0:
                self.scale(1.1, 1.1)
            else:
                self.scale(0.9, 0.9)
        else:
            super().wheelEvent(event)

    def mousePressEvent(self, event):
        if self.active_tool == 'pan':
            super().mousePressEvent(event)
            return

        scene_pos = self.mapToScene(event.pos())

        if self.active_tool in ['highlight', 'redact']:
            self.drawing = True
            self.start_pos = scene_pos
            self.current_rect_item = QGraphicsRectItem()
            color = QColor(255, 255, 0, 100) if self.active_tool == 'highlight' else QColor(0, 0, 0, 255)
            self.current_rect_item.setBrush(QBrush(color))
            self.current_rect_item.setPen(QPen(Qt.NoPen))
            self.current_rect_item.setZValue(5)
            self.scene.addItem(self.current_rect_item)

        elif self.active_tool == 'ink':
            self.drawing = True
            self.start_pos = scene_pos
            self.current_ink_path = QPainterPath(scene_pos)
            self.current_ink_item = self.scene.addPath(self.current_ink_path, QPen(Qt.blue, 3 * self.pdf_doc.zoom_factor))
            self.current_ink_item.setZValue(5)

        elif self.active_tool == 'text':
            text, ok = QInputDialog.getText(self, 'Metin Ekle', 'Eklenecek metni girin:')
            if ok and text:
                text_item = QGraphicsTextItem(text)
                text_item.setDefaultTextColor(self.main_window.current_text_color)
                text_item.setFont(QFont("Arial", self.main_window.current_font_size))
                text_item.setPos(scene_pos)
                text_item.setFlags(QGraphicsItem.ItemIsMovable | QGraphicsItem.ItemIsSelectable)
                text_item.setZValue(6)
                self.scene.addItem(text_item)
                # Auto switch back to select after placing text
                self.main_window.set_global_tool('select')
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.active_tool == 'pan':
            super().mouseMoveEvent(event)
            return

        scene_pos = self.mapToScene(event.pos())

        if self.drawing and self.active_tool in ['highlight', 'redact']:
            rect = QRectF(self.start_pos, scene_pos).normalized()
            self.current_rect_item.setRect(rect)

        elif self.drawing and self.active_tool == 'ink':
            self.current_ink_path.lineTo(scene_pos)
            self.current_ink_item.setPath(self.current_ink_path)

        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self.active_tool == 'pan':
            super().mouseReleaseEvent(event)
            return

        if self.drawing:
            self.drawing = False
            scene_pos = self.mapToScene(event.pos())

            # Map GraphicScene coordinates (which are based on high-DPI zoom*2) to raw PDF coordinates
            page = self.pdf_doc.doc.load_page(self.pdf_doc.current_page)
            scale_factor = (self.pdf_doc.zoom_factor * 2)

            if self.active_tool in ['highlight', 'redact']:
                rect = self.current_rect_item.rect()
                # If area is too small, ignore
                if rect.width() > 5 and rect.height() > 5:
                    x0, y0 = rect.left() / scale_factor, rect.top() / scale_factor
                    x1, y1 = rect.right() / scale_factor, rect.bottom() / scale_factor
                    pdf_rect = pymupdf.Rect(x0, y0, x1, y1)

                    if self.active_tool == 'highlight':
                        annot = page.add_highlight_annot(pdf_rect)
                        annot.update()
                    elif self.active_tool == 'redact':
                        page.add_redact_annot(pdf_rect, fill=(0, 0, 0))
                        page.apply_redactions()

                # Re-render to show actual PDF burned-in result
                self.render_page()

            elif self.active_tool == 'ink':
                # Convert QPainterPath to a list of points
                poly = self.current_ink_path.toFillPolygon()
                points = []
                for i in range(poly.count()):
                    pt = poly.at(i)
                    points.append((pt.x() / scale_factor, pt.y() / scale_factor))

                if len(points) > 1:
                    annot = page.add_ink_annot([points])
                    annot.set_colors(stroke=(0, 0, 1)) # Blue
                    annot.update()
                self.render_page()

        super().mouseReleaseEvent(event)

    def save_floating_items(self):
        """Burns QGraphicsTextItem into the PDF before saving"""
        if not self.pdf_doc: return
        page = self.pdf_doc.doc.load_page(self.pdf_doc.current_page)
        scale_factor = (self.pdf_doc.zoom_factor * 2)

        for item in self.scene.items():
            if isinstance(item, QGraphicsTextItem):
                x = item.pos().x() / scale_factor
                y = item.pos().y() / scale_factor
                # Add 12 to roughly align baseline vs top-left
                rect = pymupdf.Rect(x, y, x+500, y+500)

                color_q = item.defaultTextColor()
                r, g, b = color_q.redF(), color_q.greenF(), color_q.blueF()
                fontsize = item.font().pointSize() / scale_factor

                page.insert_textbox(rect, item.toPlainText(), fontsize=fontsize*2, fontname="helv", color=(r,g,b))
                self.scene.removeItem(item)
        self.render_page()

class PDFEditor(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Nitro PDF Pro - Ultimate Edition")
        self.setGeometry(50, 50, 1400, 900)
        self.documents = []
        self.active_doc_idx = -1

        self.current_font_size = 14
        self.current_text_color = QColor(0, 0, 0)

        self.setStyleSheet(MODERN_THEME_QSS)
        self.initUI()

    def initUI(self):
        # 1. Ribbon System
        self.ribbon = QTabWidget()
        self.ribbon.setFixedHeight(120)
        self.setMenuWidget(self.ribbon)

        # --- TAB: ANA SAYFA ---
        home_tab = QWidget()
        home_layout = QHBoxLayout(home_tab)
        home_layout.setAlignment(Qt.AlignLeft)

        self.btn_open = self.create_ribbon_btn('fa5s.folder-open', 'Dosya Aç')
        self.btn_open.clicked.connect(self.openPDF)
        self.btn_save = self.create_ribbon_btn('fa5s.save', 'Kaydet')
        self.btn_save.clicked.connect(self.savePDF)

        self.add_ribbon_group(home_layout, "Dosya", [self.btn_open, self.btn_save])

        self.btn_select = self.create_ribbon_btn('fa5s.mouse-pointer', 'Seçim', checkable=True, checked=True)
        self.btn_select.clicked.connect(lambda: self.set_global_tool('select'))
        self.btn_pan = self.create_ribbon_btn('fa5s.hand-paper', 'Kaydır', checkable=True)
        self.btn_pan.clicked.connect(lambda: self.set_global_tool('pan'))

        self.add_ribbon_group(home_layout, "Araçlar", [self.btn_select, self.btn_pan])

        self.btn_zoom_in = self.create_ribbon_btn('fa5s.search-plus', 'Yaklaş')
        self.btn_zoom_in.clicked.connect(self.zoom_in)
        self.btn_zoom_out = self.create_ribbon_btn('fa5s.search-minus', 'Uzaklaş')
        self.btn_zoom_out.clicked.connect(self.zoom_out)

        self.add_ribbon_group(home_layout, "Görünüm", [self.btn_zoom_in, self.btn_zoom_out])

        self.ribbon.addTab(home_tab, "Ana Sayfa")

        # --- TAB: DÜZENLE VE ANOTE ET ---
        edit_tab = QWidget()
        edit_layout = QHBoxLayout(edit_tab)
        edit_layout.setAlignment(Qt.AlignLeft)

        self.btn_text = self.create_ribbon_btn('fa5s.font', 'Metin Kutusu', checkable=True)
        self.btn_text.clicked.connect(lambda: self.set_global_tool('text'))
        self.btn_ink = self.create_ribbon_btn('fa5s.pen', 'Kalem', checkable=True)
        self.btn_ink.clicked.connect(lambda: self.set_global_tool('ink'))

        self.add_ribbon_group(edit_layout, "İçerik", [self.btn_text, self.btn_ink])

        self.btn_highlight = self.create_ribbon_btn('fa5s.highlighter', 'Vurgula', checkable=True)
        self.btn_highlight.clicked.connect(lambda: self.set_global_tool('highlight'))
        self.btn_redact = self.create_ribbon_btn('fa5s.eraser', 'Sansürle', checkable=True)
        self.btn_redact.clicked.connect(lambda: self.set_global_tool('redact'))

        self.add_ribbon_group(edit_layout, "Güvenlik & İnceleme", [self.btn_highlight, self.btn_redact])

        self.btn_watermark = self.create_ribbon_btn('fa5s.stamp', 'Filigran')
        self.btn_watermark.clicked.connect(self.add_watermark)
        self.add_ribbon_group(edit_layout, "Sayfa", [self.btn_watermark])

        self.ribbon.addTab(edit_tab, "Düzenle ve Anote Et")

        # Keep track of checkable tools
        self.tools = [self.btn_select, self.btn_pan, self.btn_text, self.btn_ink, self.btn_highlight, self.btn_redact]

        # 2. Main Interface
        main_splitter = QSplitter(Qt.Horizontal)
        self.setCentralWidget(main_splitter)

        # Left Panel (Thumbnails)
        self.thumbnail_list = QListWidget()
        self.thumbnail_list.setIconSize(QSize(100, 140))
        self.thumbnail_list.setResizeMode(QListWidget.Adjust)
        self.thumbnail_list.itemClicked.connect(self.thumbnail_clicked)

        left_dock = QDockWidget("Sayfalar", self)
        left_dock.setWidget(self.thumbnail_list)
        left_dock.setFeatures(QDockWidget.NoDockWidgetFeatures)
        self.addDockWidget(Qt.LeftDockWidgetArea, left_dock)

        # Center (Tabs of QGraphicsView)
        self.tabs = QTabWidget()
        self.tabs.setTabsClosable(True)
        self.tabs.tabCloseRequested.connect(self.close_tab)
        self.tabs.currentChanged.connect(self.tab_changed)
        main_splitter.addWidget(self.tabs)

        # Right Panel (Properties)
        self.right_dock = QDockWidget("Özellikler", self)
        self.right_dock.setFeatures(QDockWidget.NoDockWidgetFeatures)

        prop_widget = QWidget()
        prop_layout = QFormLayout(prop_widget)

        self.spin_fontsize = QSpinBox()
        self.spin_fontsize.setRange(8, 72)
        self.spin_fontsize.setValue(14)
        self.spin_fontsize.valueChanged.connect(self.change_font_size)
        prop_layout.addRow("Yazı Tipi Boyutu:", self.spin_fontsize)

        self.btn_color = QPushButton("Renk Seç")
        self.btn_color.setStyleSheet("background-color: black; color: white;")
        self.btn_color.clicked.connect(self.choose_color)
        prop_layout.addRow("Yazı Rengi:", self.btn_color)

        self.right_dock.setWidget(prop_widget)
        self.addDockWidget(Qt.RightDockWidgetArea, self.right_dock)

        main_splitter.setSizes([200, 900, 250])

    def create_ribbon_btn(self, icon_name, text, checkable=False, checked=False):
        btn = QToolButton()
        # Windows fluent blue icon colors for elegance
        btn.setIcon(qta.icon(icon_name, color='#0078d4'))
        btn.setText(text)
        btn.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
        if checkable:
            btn.setCheckable(True)
            btn.setChecked(checked)
        return btn

    def add_ribbon_group(self, layout, title, buttons):
        group_widget = QWidget()
        group_layout = QVBoxLayout(group_widget)
        group_layout.setContentsMargins(5, 0, 5, 0)
        group_layout.setSpacing(2)

        btn_layout = QHBoxLayout()
        for btn in buttons:
            btn_layout.addWidget(btn)

        group_layout.addLayout(btn_layout)

        lbl = QLabel(title)
        lbl.setAlignment(Qt.AlignCenter)
        lbl.setStyleSheet("color: #777; font-size: 10px; font-weight: normal;")
        group_layout.addWidget(lbl)

        line = QFrame()
        line.setFrameShape(QFrame.VLine)
        line.setFrameShadow(QFrame.Sunken)
        line.setStyleSheet("color: #dcdcdc;")

        layout.addWidget(group_widget)
        layout.addWidget(line)

    def set_global_tool(self, tool_name):
        for btn in self.tools:
            btn.setChecked(False)

        if tool_name == 'select': self.btn_select.setChecked(True)
        elif tool_name == 'pan': self.btn_pan.setChecked(True)
        elif tool_name == 'text': self.btn_text.setChecked(True)
        elif tool_name == 'ink': self.btn_ink.setChecked(True)
        elif tool_name == 'highlight': self.btn_highlight.setChecked(True)
        elif tool_name == 'redact': self.btn_redact.setChecked(True)

        for i in range(self.tabs.count()):
            view = self.tabs.widget(i)
            if isinstance(view, PDFGraphicsView):
                view.set_active_tool(tool_name)

    def get_active_view(self):
        if self.tabs.count() > 0:
            return self.tabs.currentWidget()
        return None

    def openPDF(self):
        fileName, _ = QFileDialog.getOpenFileName(self, "PDF Aç", "", "PDF Dosyaları (*.pdf)")
        if fileName:
            try:
                pdf_doc = PDFDocument(fileName)
                self.documents.append(pdf_doc)
                self.active_doc_idx = len(self.documents) - 1

                view = PDFGraphicsView(self)
                view.set_document(pdf_doc)

                idx = self.tabs.addTab(view, pdf_doc.name)
                self.tabs.setCurrentIndex(idx)

                self.load_thumbnails()
            except Exception as e:
                QMessageBox.critical(self, "Hata", f"Dosya açılamadı:\n{e}")

    def close_tab(self, index):
        if 0 <= index < len(self.documents):
            doc_to_close = self.documents.pop(index)
            doc_to_close.doc.close()
            widget = self.tabs.widget(index)
            self.tabs.removeTab(index)
            if widget: widget.deleteLater()
            self.load_thumbnails()

    def tab_changed(self, index):
        if index != -1 and len(self.documents) > 0:
            self.active_doc_idx = index
            self.load_thumbnails()

    def savePDF(self):
        view = self.get_active_view()
        if view and view.pdf_doc:
            # Burn graphics items into PDF before saving
            view.save_floating_items()
            fileName, _ = QFileDialog.getSaveFileName(self, "PDF'i Kaydet", view.pdf_doc.name, "PDF Dosyaları (*.pdf)")
            if fileName:
                try:
                    view.pdf_doc.doc.save(fileName)
                    QMessageBox.information(self, "Başarılı", "Tüm profesyonel düzenlemeler PDF'e işlendi.")
                except Exception as e:
                    QMessageBox.critical(self, "Hata", f"Kaydetme hatası:\n{e}")

    def load_thumbnails(self):
        self.thumbnail_list.clear()
        view = self.get_active_view()
        if not view or not view.pdf_doc: return

        pdf_doc = view.pdf_doc
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
            if i == pdf_doc.current_page:
                item.setSelected(True)
            self.thumbnail_list.addItem(item)

    def thumbnail_clicked(self, item):
        page_idx = item.data(Qt.UserRole)
        if page_idx is not None:
            view = self.get_active_view()
            if view and view.pdf_doc:
                # Save items from current page before switching
                view.save_floating_items()
                view.pdf_doc.current_page = page_idx
                view.render_page()

    def zoom_in(self):
        view = self.get_active_view()
        if view:
            view.scale(1.2, 1.2)

    def zoom_out(self):
        view = self.get_active_view()
        if view:
            view.scale(1/1.2, 1/1.2)

    def add_watermark(self):
        view = self.get_active_view()
        if view and view.pdf_doc:
            text, ok = QInputDialog.getText(self, 'Filigran', 'Filigran metni (Örn: TASLAK):')
            if ok and text:
                for page_idx in range(len(view.pdf_doc.doc)):
                    page = view.pdf_doc.doc.load_page(page_idx)
                    rect = page.rect
                    page.insert_text((rect.width/4, rect.height/2), text, fontsize=96,
                                     color=(0.9, 0.9, 0.9), morph=(pymupdf.Point(rect.width/4, rect.height/2), pymupdf.Matrix(-45)))
                view.render_page()
                self.load_thumbnails()

    def change_font_size(self, val):
        self.current_font_size = val
        view = self.get_active_view()
        if view:
            for item in view.scene.selectedItems():
                if isinstance(item, QGraphicsTextItem):
                    item.setFont(QFont("Arial", val))

    def choose_color(self):
        color = QColorDialog.getColor(self.current_text_color, self)
        if color.isValid():
            self.current_text_color = color
            self.btn_color.setStyleSheet(f"background-color: {color.name()}; color: {'white' if color.lightness() < 128 else 'black'};")
            view = self.get_active_view()
            if view:
                for item in view.scene.selectedItems():
                    if isinstance(item, QGraphicsTextItem):
                        item.setDefaultTextColor(color)

if __name__ == '__main__':
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    editor = PDFEditor()
    editor.show()
    sys.exit(app.exec_())

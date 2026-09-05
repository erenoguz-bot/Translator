#!/usr/bin/env python3
"""PDF Parser & Translator — desktop app (PySide6).

Usage:
    python desktop/main.py              # start the GUI
    python desktop/main.py --smoke-test # headless self-test (offscreen Qt)

The app reuses the whole backend from the `server` package — same parser,
OCR, language detection, NMT engine and PDF writers as the web UI.
"""
from __future__ import annotations

import math
import os
import sys
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

if __package__ in (None, ""):
    # running as a script (python desktop/main.py)
    from desktop import worker as _worker_pkg  # noqa: F401
    from desktop.theme import COLORS, QSS
else:
    from .theme import COLORS, QSS

from PySide6.QtCore import (
    Qt,
    QThread,
    QTimer,
)
from PySide6.QtGui import (
    QColor,
    QFont,
    QIcon,
    QImage,
    QPainter,
    QPixmap,
)
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QStatusBar,
    QTableWidget,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

APP_NAME = "PDF Parser & Translator"
KEEP_OUTPUTS = 10


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_icon() -> QIcon:
    pm = QPixmap(64, 64)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setBrush(QColor(COLORS["brand"]))
    p.setPen(Qt.NoPen)
    p.drawRoundedRect(2, 2, 60, 60, 14, 14)
    p.setPen(QColor("white"))
    f = QFont()
    f.setPixelSize(34)
    f.setBold(True)
    p.setFont(f)
    p.drawText(pm.rect(), Qt.AlignCenter, "译")
    p.end()
    return QIcon(pm)


def parse_page_range(value: str, page_count: int):
    """'all' / '1-3,5' → list of 1-based page numbers or None (= all)."""
    value = (value or "").strip()
    if not value or value.lower() == "all":
        return None
    out = []
    for part in [x for x in value.replace(";", ",").split(",") if x.strip()]:
        if "-" in part:
            a, b = part.split("-", 1)
            a, b = int(a), int(b)
            out.extend(range(max(1, a), min(page_count, b) + 1))
        else:
            out.append(int(part))
    out = sorted({p for p in out if 1 <= p <= page_count})
    return out or None


def fmt_bytes(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


# ---------------------------------------------------------------------------
# Drop zone
# ---------------------------------------------------------------------------


class DropZone(QFrame):
    def __init__(self, on_file):
        super().__init__()
        self.setObjectName("DropZone")
        self.setAcceptDrops(True)
        self.setCursor(Qt.PointingHandCursor)
        self._on_file = on_file

        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 18, 14, 18)
        lay.setSpacing(2)
        ico = QLabel("📄")
        ico.setAlignment(Qt.AlignCenter)
        ico.setStyleSheet("font-size: 30px;")
        t = QLabel("Drop a PDF here  ·  or click to browse")
        t.setObjectName("DropTitle")
        t.setAlignment(Qt.AlignCenter)
        s = QLabel("Text-based or scanned PDFs · up to 100 MB")
        s.setObjectName("DropSub")
        s.setAlignment(Qt.AlignCenter)
        lay.addWidget(ico)
        lay.addWidget(t)
        lay.addWidget(s)

    def enterEvent(self, e):
        if e.mimeData() and e.mimeData().hasUrls():
            self.setProperty("DragOver", True)
            self.style().unpolish(self)
            self.style().polish(self)

    def leaveEvent(self, e):
        self.setProperty("DragOver", False)
        self.style().unpolish(self)
        self.style().polish(self)

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dragMoveEvent(self, e):
        e.acceptProposedAction()

    def dropEvent(self, e):
        for url in e.mimeData().urls():
            p = Path(url.toLocalFile())
            if p.suffix.lower() == ".pdf":
                self._on_file(p)
                return
        QMessageBox.warning(self, APP_NAME,
                            "Please drop a PDF file (.pdf).")

    def mousePressEvent(self, e):
        self._on_file(None)


# ---------------------------------------------------------------------------
# Main window
# ---------------------------------------------------------------------------


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(make_icon())
        self.resize(1280, 820)
        self.setMinimumSize(1024, 680)

        self.doc = None                 # ParsedDocument
        self.worker = None
        self.thread = None
        self.outputs: dict = {}
        self.stats: dict = {}

        self._build_ui()
        self._check_engine()
        self._build_sample_btn_state()

    # ---------------- UI construction ----------------

    def _build_ui(self):
        central = QWidget()
        central.setObjectName("Root")
        root = QVBoxLayout(central)
        root.setContentsMargins(18, 14, 18, 10)
        root.setSpacing(12)

        # header
        header = QHBoxLayout()
        logo = QLabel("译")
        logo.setObjectName("Logo")
        titles_w = QWidget()
        titles = QVBoxLayout(titles_w)
        titles.setContentsMargins(0, 0, 0, 0)
        titles.setSpacing(0)
        t = QLabel(APP_NAME)
        t.setObjectName("AppTitle")
        st = QLabel("Layout-aware parsing · OCR · 60+ languages "
                    "(9 offline) · bilingual PDFs")
        st.setObjectName("Tagline")
        titles.addWidget(t)
        titles.addWidget(st)
        self._badge_labels = []
        badges_w = QWidget()
        badges_lay = QHBoxLayout(badges_w)
        badges_lay.setContentsMargins(0, 0, 0, 0)
        for _ in range(3):
            b = QLabel("")
            b.setStyleSheet(
                f"background:{COLORS['brand_soft']};color:{COLORS['brand2']}"
                f";border:1px solid #c7d2fe;border-radius:10px;"
                f"padding:3px 10px;font-size:11px;font-weight:700;")
            badges_lay.addWidget(b)
            self._badge_labels.append(b)
        header.addWidget(logo)
        header.addWidget(titles_w, 1)
        header.addWidget(badges_w)
        root.addLayout(header)

        # body: side panel + results
        body = QHBoxLayout()
        body.setSpacing(14)
        body.addWidget(self._build_side(), 0)
        body.addWidget(self._build_results(), 1)
        root.addLayout(body, 1)
        self.setCentralWidget(central)
        self.setStatusBar(QStatusBar())
        self.statusBar().showMessage("Ready")

    def _build_side(self) -> QWidget:
        panel = QFrame()
        panel.setObjectName("SidePanel")
        panel.setFixedWidth(368)
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(10)

        h = QLabel("1 · DOCUMENT")
        h.setObjectName("SectionTitle")
        lay.addWidget(h)
        self.drop = DropZone(self.on_pick_file)
        lay.addWidget(self.drop)

        row = QHBoxLayout()
        self.open_btn = QPushButton("📂 Open PDF…")
        self.sample_btn = QPushButton("✨ Sample document")
        self.open_btn.clicked.connect(lambda: self.on_pick_file(None))
        self.sample_btn.clicked.connect(self.load_sample)
        row.addWidget(self.open_btn)
        row.addWidget(self.sample_btn)
        lay.addLayout(row)

        # document info
        self.doc_info = QFrame()
        self.doc_info.setStyleSheet(
            f"border-top:1px solid {COLORS['line']}; padding-top:8px;")
        dil = QVBoxLayout(self.doc_info)
        dil.setContentsMargins(0, 8, 0, 0)
        dil.setSpacing(4)
        top = QHBoxLayout()
        self.doc_name = QLabel("No document loaded")
        self.doc_name.setObjectName("DocName")
        self.doc_name.setWordWrap(True)
        top.addWidget(self.doc_name, 1)
        dil.addLayout(top)
        self.doc_meta = QLabel("")
        self.doc_meta.setObjectName("DocMeta")
        self.doc_meta.setWordWrap(True)
        dil.addWidget(self.doc_meta)
        self.doc_info.hide()
        lay.addWidget(self.doc_info)

        # thumbnails
        self.thumb_scroll = QScrollArea()
        self.thumb_scroll.setWidgetResizable(True)
        self.thumb_scroll.setFixedHeight(96)
        self.thumb_inner = QWidget()
        self.thumb_lay = QHBoxLayout(self.thumb_inner)
        self.thumb_lay.setContentsMargins(2, 6, 2, 6)
        self.thumb_lay.setSpacing(6)
        self.thumb_lay.addStretch(1)
        self.thumb_scroll.setWidget(self.thumb_inner)
        self.thumb_scroll.hide()
        lay.addWidget(self.thumb_scroll)

        lay.addSpacing(4)
        h2 = QLabel("2 · TRANSLATION")
        h2.setObjectName("SectionTitle")
        lay.addWidget(h2)

        grid = QGridLayout()
        grid.setSpacing(8)
        self.src_combo = QComboBox()
        self.tgt_combo = QComboBox()
        self.mode_combo = QComboBox()
        self.mode_combo.addItems([
            "Bilingual PDF (side by side)",
            "Translated PDF only",
        ])
        self.pages_edit = self._line_edit()
        grid.addWidget(QLabel("From"), 0, 0)
        grid.addWidget(self.src_combo, 0, 1)
        grid.addWidget(QLabel("To"), 1, 0)
        grid.addWidget(self.tgt_combo, 1, 1)
        grid.addWidget(QLabel("Output"), 2, 0)
        grid.addWidget(self.mode_combo, 2, 1)
        grid.addWidget(QLabel("Pages"), 3, 0)
        grid.addWidget(self.pages_edit, 3, 1)
        self.ocr_chk = QCheckBox("OCR scanned pages")
        self.ocr_chk.setChecked(True)
        grid.addWidget(self.ocr_chk, 4, 0, 1, 2)
        lay.addLayout(grid)

        self.translate_btn = QPushButton("Translate document  →")
        self.translate_btn.setObjectName("Primary")
        self.translate_btn.setEnabled(False)
        self.translate_btn.clicked.connect(self.start_translation)
        lay.addWidget(self.translate_btn)

        lay.addSpacing(2)
        h3 = QLabel("PROGRESS")
        h3.setObjectName("SectionTitle")
        lay.addWidget(h3)
        prow = QHBoxLayout()
        self.stage_label = QLabel("Idle")
        self.stage_label.setObjectName("StageLabel")
        self.stage_pct = QLabel("")
        self.stage_pct.setStyleSheet(f"color:{COLORS['brand']};font-weight:700;")
        prow.addWidget(self.stage_label, 1)
        prow.addWidget(self.stage_pct)
        lay.addLayout(prow)
        self.bar = QProgressBar()
        self.bar.setRange(0, 100)
        self.bar.setValue(0)
        lay.addWidget(self.bar)
        self.stage_msg = QLabel("")
        self.stage_msg.setObjectName("StageMsg")
        self.stage_msg.setWordWrap(True)
        lay.addWidget(self.stage_msg)
        lay.addStretch(1)
        return panel

    def _line_edit(self):
        le = QLineEdit("all")
        le.setPlaceholderText("all (e.g. 1-3,5)")
        return le

    def _build_results(self) -> QWidget:
        panel = QFrame()
        panel.setObjectName("ResultPanel")
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(16, 12, 16, 14)
        lay.setSpacing(8)

        self.tabs = QTabWidget()
        self.tab_status = QLabel("No job yet")
        self.tab_status.setObjectName("TabStatus")
        self.tabs.tabBar().setExpanding(False)

        # tab 1: side-by-side
        t1 = QWidget()
        v1 = QVBoxLayout(t1)
        v1.setContentsMargins(0, 0, 0, 0)
        self.empty = QLabel(
            "🌐\n\nDrop a PDF on the left (or generate the sample),\n"
            "pick a target language and press Translate.\n\n"
            "The 9 local languages run fully offline;\n"
            "other languages use the online service (internet).")
        self.empty.setAlignment(Qt.AlignCenter)
        self.empty.setStyleSheet(f"color:{COLORS['ink2']};font-size:14px;")
        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(
            ["Original", "Translated"])
        from PySide6.QtWidgets import QHeaderView
        self.table.horizontalHeader().setSectionResizeMode(
            QHeaderView.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.hide()
        v1.addWidget(self.empty, 1)
        v1.addWidget(self.table, 2)
        self.tabs.addTab(t1, "Side-by-side")

        # tab 2: preview of generated PDF
        t2 = QWidget()
        v2 = QVBoxLayout(t2)
        v2.setContentsMargins(0, 0, 0, 0)
        pvrow = QHBoxLayout()
        pvrow.addWidget(QLabel("Preview:"))
        self.preview_combo = QComboBox()
        self.preview_combo.addItems(["Bilingual PDF", "Translated PDF"])
        self.preview_combo.currentIndexChanged.connect(self.render_preview)
        pvrow.addWidget(self.preview_combo)
        pvrow.addStretch(1)
        v2.addLayout(pvrow)
        pv_scroll = QScrollArea()
        pv_scroll.setWidgetResizable(True)
        self.preview_lay = QVBoxLayout()
        self.preview_lay.setAlignment(Qt.AlignHCenter)
        pv_inner = QWidget()
        pv_inner.setLayout(self.preview_lay)
        pv_scroll.setWidget(pv_inner)
        v2.addWidget(pv_scroll, 1)
        self.tabs.addTab(t2, "PDF preview")

        # tab 3: save
        t3 = QWidget()
        v3 = QVBoxLayout(t3)
        v3.setContentsMargins(0, 0, 0, 0)
        self.stats_label = QLabel("—")
        self.stats_label.setWordWrap(True)
        self.stats_label.setStyleSheet(f"color:{COLORS['ink2']};")
        v3.addWidget(self.stats_label)
        self.save_list = QListWidget()
        v3.addWidget(self.save_list, 1)
        savrow = QHBoxLayout()
        self.save_one = QPushButton("💾 Save selected…")
        self.save_one.setObjectName("SaveBtn")
        self.save_all_btn = QPushButton("📁 Save all to folder…")
        self.save_all_btn.setObjectName("SaveBtn")
        self.save_one.clicked.connect(self.save_selected)
        self.save_all_btn.clicked.connect(self.save_all)
        savrow.addWidget(self.save_one)
        savrow.addWidget(self.save_all_btn)
        savrow.addStretch(1)
        v3.addLayout(savrow)
        self.tabs.addTab(t3, "Save")

        lay.addWidget(self.tabs, 1)
        self.tab_status.hide()  # status moved to status bar
        return panel

    # ---------------- engine info ----------------

    def _check_engine(self):
        from server.nmt import get_engine
        from server.ocr import get_ocr
        try:
            engine = get_engine()
            pairs = len(engine.available_pairs)
        except Exception:
            pairs = 0
        ocr_ok = get_ocr().available
        labels = self._badge_labels
        labels[0].setText("Opus-MT · offline")
        labels[1].setText(f"{pairs} models" if pairs else "⚠ no models")
        labels[2].setText("OCR ready" if ocr_ok else "OCR off")
        if not pairs:
            self.statusBar().showMessage(
                "No translation models found — run "
                "python scripts/fetch_models.py first")

    def _build_sample_btn_state(self):
        from server import config
        from server.config import LOCAL_LANGUAGES
        langs = config.LANGUAGES
        names = sorted(langs, key=lambda c: langs[c])
        local = [c for c in names if c in LOCAL_LANGUAGES]
        online = [c for c in names if c not in LOCAL_LANGUAGES]

        self.src_combo.addItem("🔍 Auto-detect", "auto")
        for code in local:
            self.src_combo.addItem(langs[code], code)
        self.src_combo.insertSeparator(self.src_combo.count())
        for code in online:
            self.src_combo.addItem(f"{langs[code]}  (online)", code)

        for code in local:
            self.tgt_combo.addItem(f"{langs[code]}  (offline)", code)
        self.tgt_combo.insertSeparator(self.tgt_combo.count())
        for code in online:
            self.tgt_combo.addItem(f"{langs[code]}  (online)", code)

        # default target: Turkish (the most common "online" ask)
        tr_index = self.tgt_combo.findData("tr")
        self.tgt_combo.setCurrentIndex(max(0, tr_index))

    # ---------------- document loading ----------------

    def on_pick_file(self, path: Path | None):
        if path is None:
            path = QFileDialog.getOpenFileName(
                self, "Open PDF", str(Path.home()),
                "PDF files (*.pdf)")[0]
            if not path:
                return
            path = Path(path)
        self.load_file(path)

    def load_file(self, path: Path):
        from server import pdf_parser
        if Path(path).suffix.lower() != ".pdf":
            QMessageBox.warning(self, APP_NAME, "Please choose a PDF file.")
            return
        self.statusBar().showMessage(f"Parsing {Path(path).name} …")
        self.drop.setFocus()
        self.process_events()
        try:
            doc = pdf_parser.parse_pdf(Path(path))
        except Exception as e:
            QMessageBox.critical(self, APP_NAME, f"Could not parse PDF:\n{e}")
            return
        self.doc = doc
        self._show_doc()
        self.translate_btn.setEnabled(True)
        self.statusBar().showMessage(
            f"Parsed {doc.page_count} pages, {doc.word_count} words")

    def load_sample(self):
        from server import sample_doc
        from server.config import DOCS_DIR
        try:
            dest = DOCS_DIR / f"desktop_{uuid.uuid4().hex[:8]}.pdf"
            sample_doc.make_sample_pdf(dest)
            self.load_file(dest)
        except Exception as e:
            QMessageBox.critical(self, APP_NAME, f"Sample failed:\n{e}")

    def process_events(self):
        QApplication.processEvents()

    def _show_doc(self):
        d = self.doc
        self.doc_info.show()
        scanned = [p.number for p in d.pages if not p.has_text]
        self.doc_name.setText(d.filename)
        meta = (f"{d.page_count} pages · {d.word_count:,} words · "
                f"{len(d.paragraphs)} paragraphs")
        if d.title and d.title.lower() != d.filename.lower():
            meta += f"\n“{d.title}”"
        if scanned:
            meta += f"\n⚠ {len(scanned)} scanned page(s) — OCR will be used"
        self.doc_meta.setText(meta)
        self._render_thumbs()

    def _render_thumbs(self):
        # clear
        while self.thumb_lay.count() > 1:
            item = self.thumb_lay.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        import pymupdf as fitz
        fdoc = fitz.open(str(self.doc.path))
        shown = min(fdoc.page_count, 18)
        for i in range(shown):
            pix = fdoc[i].get_pixmap(dpi=55)
            img = QImage(pix.samples, pix.width, pix.height, pix.stride,
                         QImage.Format_RGB888).copy()
            lbl = QLabel()
            pm = QPixmap.fromImage(img)
            target_h = 78
            lbl.setPixmap(pm.scaledToHeight(
                target_h, Qt.SmoothTransformation))
            lbl.setToolTip(f"Page {i + 1}")
            self.thumb_lay.addWidget(lbl)
        if fdoc.page_count > shown:
            more = QLabel(f"+{fdoc.page_count - shown}")
            more.setStyleSheet(f"color:{COLORS['ink3']};font-weight:700;")
            more.setAlignment(Qt.AlignCenter)
            self.thumb_lay.addWidget(more)
        fdoc.close()
        self.thumb_scroll.show()

    # ---------------- translation ----------------

    def start_translation(self):
        if not self.doc or self.worker:
            return
        try:
            pages = parse_page_range(self.pages_edit.text(),
                                     self.doc.page_count)
        except ValueError:
            QMessageBox.warning(self, APP_NAME,
                                "Bad page range — use e.g. 'all' or '1-3,5'.")
            return
        from server.config import LOCAL_LANGUAGES, WORK_DIR
        from server.nmt import get_engine
        source = self.src_combo.currentData()
        target = self.tgt_combo.currentData()

        # pick engine: offline model when it can cover the pair,
        # otherwise the online service (needs internet)
        if source == target:
            engine = "local"
        elif source == "auto":
            engine = "local" if target in LOCAL_LANGUAGES else "online"
        else:
            eng = get_engine()
            covers = (eng.route(source, target)
                      or (eng.route(source, "en")
                          and eng.route("en", target)))
            engine = "local" if covers else "online"

        if engine == "online":
            scanned = [p.number for p in self.doc.pages if not p.has_text]
            if scanned:
                QMessageBox.warning(
                    self, APP_NAME,
                    "This document has scanned pages — OCR is an offline "
                    "feature and works only with the 9 local languages.\n"
                    "Re-run with a local target, or online-translate the "
                    "text pages only.")
                return
        out_dir = WORK_DIR / "desktop" / uuid.uuid4().hex[:10]

        if __package__ in (None, ""):
            from desktop.worker import TranslateWorker
        else:
            from .worker import TranslateWorker
        self.thread = QThread()
        self.worker = TranslateWorker(
            self.doc, source, target,
            "bilingual" if self.mode_combo.currentIndex() == 0
            else "translated",
            pages, self.ocr_chk.isChecked(), out_dir,
            engine_name=engine)
        if engine == "online":
            self.statusBar().showMessage(
                "Using the online translation service (internet required)")
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.progress.connect(self.on_progress)
        self.worker.finished.connect(self.on_finished)
        self.worker.failed.connect(self.on_failed)
        self.thread.finished.connect(self._thread_finished)
        self.thread.start()

        self.translate_btn.setEnabled(False)
        self.drop.setEnabled(False)
        self._set_stage("Queued", 0, "Starting…")

    def on_progress(self, stage: str, pct: float, msg: str):
        names = {"parse": "Parsing text", "ocr": "OCR (scanned pages)",
                 "detect": "Language detection", "translate": "Translating",
                 "build": "Building PDFs", "done": "Finished"}
        self._set_stage(names.get(stage, stage), pct, msg)
        self.statusBar().showMessage(msg)

    def _set_stage(self, stage, pct, msg):
        self.stage_label.setText(stage)
        self.stage_pct.setText(f"{int(pct)}%")
        self.bar.setValue(int(pct))
        self.stage_msg.setText(msg)

    def _thread_finished(self):
        self.worker = None
        self.thread = None

    def on_finished(self, result: dict):
        self.outputs = result["outputs"]
        self.stats = result["stats"]
        try:
            self._render_side_by_side(result["paragraphs"])
            self._render_save_tab()
            self.render_preview()
            self.tabs.setCurrentIndex(0)
            self.statusBar().showMessage(
                f"Done in {self.stats['elapsed']:.1f}s — "
                f"{self.stats['words']:,} words translated")
        except Exception as e:  # never leave the UI locked on a render bug
            self.statusBar().showMessage(f"Render warning: {e}")
        self._unblock()
        # preview tab: default to the selected mode
        self.preview_combo.setCurrentIndex(
            0 if self.mode_combo.currentIndex() == 0 else 1)
        QTimer.singleShot(0, self._reap_thread)

    def _reap_thread(self):
        if self.thread:
            self.thread.quit()
            self.thread.wait(3000)
            self.thread.deleteLater()
            self.thread = None

    def on_failed(self, err: str):
        self._unblock()
        self._set_stage("Error", self.bar.value(), err)
        self.statusBar().showMessage(f"Error: {err}")
        QTimer.singleShot(0, self._reap_thread)
        QTimer.singleShot(150, lambda: QMessageBox.critical(
            self, APP_NAME, f"Translation failed:\n{err}"))

    def _unblock(self):
        self.worker = None
        self.translate_btn.setEnabled(self.doc is not None)
        self.drop.setEnabled(True)

    # ---------------- results rendering ----------------

    def _cell_html(self, text: str, kind: str) -> str:
        import html
        text = html.escape(text or "")
        if kind == "title":
            return (f'<div style="font-size:16px;font-weight:800;'
                    f'color:{COLORS["brand2"]};">{text}</div>')
        if kind == "heading":
            return (f'<div style="font-size:13.5px;font-weight:700;'
                    f'color:{COLORS["brand2"]};'
                    f'background:{COLORS["brand_soft"]};'
                    f'border-radius:4px;padding:2px 6px;">{text}</div>')
        if kind == "caption":
            return (f'<div style="font-size:11px;color:{COLORS["ink3"]};'
                    f'font-style:italic;">{text}</div>')
        prefix = "• " if kind == "list" else ""
        return f'<div style="line-height:1.45;">{prefix}{text}</div>'

    def _est_height(self, text: str, kind: str, col_width: int) -> int:
        size = {"title": 20, "heading": 18, "caption": 14}.get(kind, 16)
        cpl = max(col_width // (size * 6 // 10), 20)
        lines = max(1, math.ceil(len(text or "") / cpl))
        return lines * (size + 4) + 14

    def _cell_widget(self, html: str, ocr: bool) -> QWidget:
        # QTableWidgetItem cannot render HTML → QLabel cell widget.
        # (Some PySide6 builds, e.g. the sandbox's, lack setHtml entirely —
        # fall back to stripped plain text.)
        import re
        w = QWidget()
        wl = QVBoxLayout(w)
        wl.setContentsMargins(10, 6, 10, 6)
        lbl = QLabel()
        if hasattr(lbl, "setHtml"):
            lbl.setHtml(html)
        else:
            lbl.setText(re.sub(r"<[^>]+>", "", html).strip())
        lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
        wl.addWidget(lbl)
        if ocr:
            w.setToolTip("Extracted via OCR")
        return w

    def _render_side_by_side(self, paras: list[dict]):
        self.empty.hide()
        self.table.show()
        self.table.setRowCount(0)
        col_w = max(self.table.width() // 2 - 40, 200)
        for p in paras:
            r = self.table.rowCount()
            self.table.insertRow(r)
            cpl = self._cell_html(p.get("text", ""), p.get("kind", "body"))
            cpr = self._cell_html(p.get("translation", ""),
                                  p.get("kind", "body"))
            ocr = p.get("source") == "ocr"
            self.table.setCellWidget(r, 0, self._cell_widget(cpl, ocr))
            self.table.setCellWidget(r, 1, self._cell_widget(cpr, ocr))
            h = max(self._est_height(p.get("text", ""),
                                     p.get("kind", "body"), col_w),
                    self._est_height(p.get("translation", ""),
                                     p.get("kind", "body"), col_w))
            self.table.setRowHeight(r, h)

    def _render_save_tab(self):
        self.save_list.clear()
        s = self.stats
        route = " → ".join(s.get("route", []))
        self.stats_label.setText(
            f"Source: <b>{s.get('source')}</b> → "
            f"Target: <b>{s.get('target')}</b><br>"
            f"Words: <b>{s.get('words', 0):,}</b> · "
            f"Paragraphs: <b>{s.get('paragraphs', 0)}</b><br>"
            f"Route: <b>{route}</b> · "
            f"OCR used: <b>{'yes' if s.get('ocr_used') else 'no'}</b> · "
            f"Time: <b>{s.get('elapsed', 0):.1f}s</b><br>"
            f"Engine: {s.get('engine', 'Opus-MT (Argos, CTranslate2)')}")
        items = [
            ("bilingual_pdf", "📑 Bilingual PDF", "Original + translation"),
            ("translated_pdf", "📄 Translated PDF",
             "Target language only"),
            ("text_bilingual", "📝 Bilingual text (.txt)", "Plain text"),
            ("text_translation", "📝 Translated text (.txt)", "Plain text"),
        ]
        for key, name, sub in items:
            path = self.outputs.get(key)
            if not path:
                continue
            it = QListWidgetItem(f"{name}\n{sub}  ·  {fmt_bytes(Path(path).stat().st_size)}")
            it.setData(Qt.UserRole, path)
            self.save_list.addItem(it)

    def render_preview(self, *_):
        while self.preview_lay.count():
            item = self.preview_lay.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        key = ("bilingual_pdf" if self.preview_combo.currentIndex() == 0
               else "translated_pdf")
        path = self.outputs.get(key)
        if not path or not Path(path).exists():
            lbl = QLabel("No PDF generated yet — run a translation first.")
            lbl.setStyleSheet(f"color:{COLORS['ink3']};")
            self.preview_lay.addWidget(lbl)
            return
        import pymupdf as fitz
        d = fitz.open(str(path))
        shown = min(d.page_count, 8)
        for i in range(shown):
            pix = d[i].get_pixmap(dpi=90)
            img = QImage(pix.samples, pix.width, pix.height, pix.stride,
                         QImage.Format_RGB888).copy()
            lbl = QLabel()
            pm = QPixmap.fromImage(img)
            max_w = 620
            if pm.width() > max_w:
                pm = pm.scaledToWidth(max_w, Qt.SmoothTransformation)
            lbl.setPixmap(pm)
            lbl.setFixedSize(pm.size())
            lbl.setStyleSheet(
                f"border:1px solid {COLORS['line']};"
                f"border-radius:8px;background:white;")
            self.preview_lay.addWidget(lbl, 0, Qt.AlignHCenter)
        if d.page_count > shown:
            more = QLabel(f"… {d.page_count - shown} more page(s) — "
                          "see the Save tab to download the full file")
            more.setStyleSheet(f"color:{COLORS['ink3']};")
            self.preview_lay.addWidget(more)
        d.close()

    # ---------------- saving ----------------

    def save_selected(self):
        it = self.save_list.currentItem()
        if not it:
            return
        src = Path(it.data(Qt.UserRole))
        ext = src.suffix
        dest = QFileDialog.getSaveFileName(
            self, "Save", str(Path.home() / src.name),
            f"Files (*{ext})")[0]
        if dest:
            import shutil
            shutil.copyfile(src, dest)
            self.statusBar().showMessage(f"Saved → {dest}")

    def save_all(self):
        dest = QFileDialog.getExistingDirectory(
            self, "Choose a folder", str(Path.home()))
        if not dest:
            return
        import shutil
        for p in self.outputs.values():
            shutil.copyfile(p, Path(dest) / Path(p).name)
        self.statusBar().showMessage(f"Saved {len(self.outputs)} files → {dest}")
        if QMessageBox.question(
                self, APP_NAME,
                f"Saved {len(self.outputs)} files to {dest}\n\nOpen folder?") \
                == QMessageBox.Yes:
            self._open_folder(Path(dest))

    def _open_folder(self, folder: Path):
        from PySide6.QtCore import QDesktopServices, QUrl
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))

    # ---------------- window-level drop ----------------

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        for url in e.mimeData().urls():
            p = Path(url.toLocalFile())
            if p.suffix.lower() == ".pdf":
                self.load_file(p)
                return
        QMessageBox.warning(self, APP_NAME,
                            "Please drop a PDF file (.pdf).")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def run_smoke_test(app: QApplication, win: MainWindow) -> int:
    """Headless end-to-end: sample doc → translate page 1 → outputs."""
    import pymupdf as fitz

    win.load_sample()
    assert win.doc is not None, "sample document did not load"
    win.pages_edit.setText("1")
    win.src_combo.setCurrentIndex(0)      # auto
    de_index = win.tgt_combo.findData("de")
    win.tgt_combo.setCurrentIndex(de_index if de_index > 0 else 1)
    win.start_translation()

    deadline = time.time() + 180
    while win.worker is not None and time.time() < deadline:
        app.processEvents()
        time.sleep(0.1)
    assert win.worker is None, "translation did not finish in time"
    assert win.outputs, "no outputs produced"
    for key, p in win.outputs.items():
        assert Path(p).exists() and Path(p).stat().st_size > 500, (
            key, p)
    d = fitz.open(win.outputs["bilingual_pdf"])
    assert d.page_count >= 1
    d.close()
    print(f"SMOKE OK  outputs={list(win.outputs)} "
          f"stats={win.stats}")
    return 0


def main() -> int:
    smoke = "--smoke-test" in sys.argv
    if smoke:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        # modal dialogs would block forever offscreen → fail loudly instead
        def _no_dialog(*args, **_kw):
            raise RuntimeError("dialog: " + " | ".join(
                str(a) for a in args if isinstance(a, str)))
        QMessageBox.critical = staticmethod(_no_dialog)
        QMessageBox.warning = staticmethod(_no_dialog)
        QMessageBox.information = staticmethod(_no_dialog)
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setStyleSheet(QSS)
    win = MainWindow()
    win.show()
    if smoke:
        try:
            return run_smoke_test(app, win)
        except Exception as e:
            print(f"SMOKE FAIL: {e}")
            return 1
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())

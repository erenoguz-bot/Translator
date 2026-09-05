"""QSS theme for the desktop app (mirrors the web UI: indigo on light)."""

COLORS = {
    "bg": "#f4f5fb",
    "panel": "#ffffff",
    "ink": "#111827",
    "ink2": "#4b5563",
    "ink3": "#9ca3af",
    "line": "#e5e7eb",
    "brand": "#4f46e5",
    "brand2": "#4338ca",
    "brand_soft": "#eef2ff",
    "ok": "#059669",
    "err": "#dc2626",
    "warn": "#b45309",
}

QSS = f"""
* {{
    font-family: "Segoe UI", "SF Pro Text", "Noto Sans", "Noto Sans CJK SC",
                 "Noto Naskh Arabic", "DejaVu Sans", sans-serif;
    font-size: 13px;
    color: {COLORS['ink']};
}}
QMainWindow, #Root {{
    background: {COLORS['bg']};
}}
QFrame#SidePanel, QFrame#ResultPanel {{
    background: {COLORS['panel']};
    border: 1px solid {COLORS['line']};
    border-radius: 12px;
}}
QLabel#SectionTitle {{
    font-size: 11px;
    font-weight: 700;
    color: {COLORS['ink3']};
    letter-spacing: 1px;
}}
QLabel#DocName {{ font-size: 14px; font-weight: 650; }}
QLabel#DocMeta {{ color: {COLORS['ink2']}; font-size: 12px; }}
QLabel#Logo {{
    font-size: 26px;
    background: {COLORS['brand_soft']};
    color: {COLORS['brand2']};
    border: 1px solid #c7d2fe;
    border-radius: 10px;
    padding: 4px 12px;
}}
QLabel#AppTitle {{ font-size: 17px; font-weight: 750; }}
QLabel#Tagline {{ color: {COLORS['ink2']}; font-size: 12px; }}

/* ---------- drop zone ---------- */
QFrame#DropZone {{
    border: 2px dashed #c7d2fe;
    border-radius: 10px;
    background: #fafaff;
}}
QFrame#DropZone[DragOver="true"] {{
    border: 2px solid {COLORS['brand']};
    background: {COLORS['brand_soft']};
}}
QLabel#DropTitle {{ font-weight: 650; font-size: 14px; }}
QLabel#DropSub {{ color: {COLORS['ink2']}; font-size: 12px; }}

/* ---------- buttons ---------- */
QPushButton {{
    background: #ffffff;
    border: 1px solid {COLORS['line']};
    border-radius: 9px;
    padding: 8px 14px;
    font-weight: 600;
}}
QPushButton:hover {{ border-color: {COLORS['brand']}; color: {COLORS['brand']}; }}
QPushButton:disabled {{ color: {COLORS['ink3']}; background: #fafafa; }}
QPushButton#Primary {{
    background: {COLORS['brand']};
    border: none;
    color: white;
    font-size: 14px;
    font-weight: 700;
    padding: 11px 16px;
    border-radius: 10px;
}}
QPushButton#Primary:hover {{ background: {COLORS['brand2']}; color: white; }}
QPushButton#Primary:disabled {{ background: #c7c9e8; color: white; }}
QPushButton#SaveBtn {{ padding: 7px 12px; }}

/* ---------- inputs ---------- */
QComboBox, QLineEdit {{
    border: 1px solid {COLORS['line']};
    border-radius: 8px;
    padding: 7px 10px;
    background: white;
    selection-background-color: {COLORS['brand']};
    selection-color: white;
}}
QComboBox:hover, QLineEdit:focus {{ border-color: {COLORS['brand']}; }}
QComboBox::drop-down {{ border: none; width: 24px; }}
QCheckBox {{ spacing: 6px; }}
QCheckBox::indicator {{ width: 16px; height: 16px; border-radius: 4px;
    border: 1px solid {COLORS['line']}; background: white; }}
QCheckBox::indicator:checked {{ background: {COLORS['brand']};
    border-color: {COLORS['brand']}; }}

/* ---------- progress ---------- */
QProgressBar {{
    border: none; border-radius: 6px;
    background: {COLORS['brand_soft']};
    text-align: center;
    font-weight: 700;
    color: white;
    height: 18px;
}}
QProgressBar::chunk {{
    border-radius: 6px;
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 #6366f1, stop:1 {COLORS['brand']});
}}
QLabel#StageLabel {{ font-weight: 700; }}
QLabel#StageMsg {{ color: {COLORS['ink2']}; font-size: 12px; }}

/* ---------- tabs ---------- */
QTabWidget::pane {{ border: none; }}
QTabBar::tab {{
    padding: 9px 14px;
    font-weight: 650;
    color: {COLORS['ink2']};
    border-bottom: 2.5px solid transparent;
}}
QTabBar::tab:selected {{ color: {COLORS['brand']};
    border-bottom: 2.5px solid {COLORS['brand']}; }}
QLabel#TabStatus {{ color: {COLORS['ink3']}; font-size: 12px; }}

/* ---------- side-by-side table ---------- */
QTableWidget {{
    border: none;
    background: white;
    gridline-color: #f1f2f6;
}}
QHeaderView::section {{
    background: white;
    border: none;
    border-bottom: 1px solid {COLORS['line']};
    padding: 8px;
    font-weight: 700;
    color: {COLORS['ink3']};
    font-size: 11px;
}}
QTableWidget::item {{ padding: 6px; border: none; }}
QTableWidget::item:selected {{ background: {COLORS['brand_soft']}; }}

/* ---------- downloads list ---------- */
QListWidget {{ border: none; background: white; font-size: 13px; }}
QListWidget::item {{
    border: 1px solid {COLORS['line']};
    border-radius: 10px;
    padding: 10px;
    margin: 4px 2px;
    background: white;
}}
QListWidget::item:hover {{ border-color: {COLORS['brand']}; }}

/* ---------- status bar / scrollbars ---------- */
QStatusBar {{ background: white; border-top: 1px solid {COLORS['line']};
    color: {COLORS['ink2']}; font-size: 12px; }}
QScrollBar:vertical {{ background: transparent; width: 10px; }}
QScrollBar::handle:vertical {{ background: #d1d5db; border-radius: 5px;
    min-height: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; }}
QScrollBar::handle:horizontal {{ background: #d1d5db; border-radius: 5px;
    min-width: 30px; }}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}

QToolTip {{
    background: {COLORS['ink']}; color: white;
    border: none; border-radius: 6px; padding: 6px 8px;
}}
QMenu {{ background: white; border: 1px solid {COLORS['line']};
    border-radius: 8px; padding: 4px; }}
QMenu::item {{ padding: 6px 18px; border-radius: 6px; }}
QMenu::item:selected {{ background: {COLORS['brand_soft']};
    color: {COLORS['brand2']}; }}
"""

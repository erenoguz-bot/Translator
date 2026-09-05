"""Headless test for the PySide6 desktop app (offscreen platform).

Skipped automatically when PySide6 is not installed or cannot start an
offscreen QApplication (e.g. missing system GL libraries).
"""
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

STUBS = ROOT / "tools" / "stub-libs"


def _qt_offscreen_ready() -> bool:
    try:
        import PySide6  # noqa: F401
    except Exception:
        return False
    # glibc ignores LD_LIBRARY_PATH changes after process start, so
    # pre-load the (sandbox) stub libs into the global symbol table.
    if STUBS.exists():
        import ctypes
        for name in ("libGL.so.1", "libEGL.so.1", "libxkbcommon.so.0",
                     "libdbus-1.so.3"):
            try:
                ctypes.CDLL(str(STUBS / name), mode=ctypes.RTLD_GLOBAL)
            except OSError:
                pass
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    try:
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance() or QApplication([])
        app.processEvents()
        return True
    except Exception:
        return False


requires_qt = pytest.mark.skipif(
    not _qt_offscreen_ready(),
    reason="PySide6 / offscreen Qt not available",
)


@requires_qt
def test_desktop_smoke(tmp_path):
    """Full desktop pipeline: sample doc → auto-detect → MT → PDFs."""
    from PySide6.QtWidgets import QApplication, QMessageBox

    app = QApplication.instance() or QApplication([])

    # fail loudly on modal dialogs (they would block offscreen)
    def _no_dialog(*args, **_kw):
        raise RuntimeError(
            "dialog: " + " | ".join(
                str(a) for a in args if isinstance(a, str)))
    QMessageBox.critical = staticmethod(_no_dialog)
    QMessageBox.warning = staticmethod(_no_dialog)
    QMessageBox.information = staticmethod(_no_dialog)

    import desktop.main as m

    win = m.MainWindow()
    win.show()

    win.load_sample()
    assert win.doc is not None, "sample document did not load"
    win.pages_edit.setText("1")
    # pick an OFFLINE (local) target so the smoke test stays deterministic
    # and does not depend on internet access
    de_index = win.tgt_combo.findData("de")
    assert de_index > 0, "German (local model) missing from target combo"
    win.tgt_combo.setCurrentIndex(de_index)
    win.start_translation()

    import time
    deadline = time.time() + 240
    while win.worker is not None and time.time() < deadline:
        app.processEvents()
        time.sleep(0.1)
    app.processEvents()

    assert win.worker is None, "translation did not finish in time"
    assert win.outputs, "no outputs produced"
    for key, p in win.outputs.items():
        assert Path(p).exists() and Path(p).stat().st_size > 500, (key, p)

    # the side-by-side table must have been populated
    assert win.table.rowCount() > 5

    import pymupdf as fitz
    d = fitz.open(win.outputs["bilingual_pdf"])
    assert d.page_count >= 1
    d.close()

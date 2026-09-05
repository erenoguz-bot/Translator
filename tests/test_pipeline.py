"""End-to-end tests: sample PDF → parse → detect → translate → outputs."""
import json
import sys
import time
import urllib.parse
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from server import pdf_parser, pdf_writer, sample_doc
from server.langid import detect_language
from server.nmt import get_engine
from server.pipeline import run_translation


@pytest.fixture(scope="module")
def sample_doc_file(tmp_path_factory):
    p = tmp_path_factory.mktemp("docs") / "sample.pdf"
    sample_doc.make_sample_pdf(p)
    return p


@pytest.fixture(scope="module")
def parsed(sample_doc_file):
    return pdf_parser.parse_pdf(sample_doc_file)


class TestParsing:
    def test_metadata(self, parsed):
        assert parsed.page_count >= 2
        assert parsed.title
        assert parsed.word_count > 400

    def test_paragraphs(self, parsed):
        assert len(parsed.paragraphs) > 15
        kinds = {p.kind for p in parsed.paragraphs}
        assert "heading" in kinds
        assert "body" in kinds
        assert any(p.kind == "title" for p in parsed.paragraphs)

    def test_pages(self, parsed):
        assert all(p.has_text for p in parsed.pages)
        assert sum(p.words for p in parsed.pages) > 400


class TestLanguageDetection:
    def test_english(self, parsed):
        code, conf, how = detect_language(parsed.text())
        assert code == "en", (code, how)

    def test_cjk(self):
        code, _, _ = detect_language("这是中文测试文本，用于语言检测。" * 4)
        assert code == "zh"

    def test_cyrillic(self):
        code, _, _ = detect_language(
            "Машинный перевод изменил общение между людьми." * 4)
        assert code == "ru"

    def test_arabic_script(self):
        code, _, _ = detect_language("هذه جملة عربية للاختبار والتجربة." * 4)
        assert code == "ar"


class TestNMT:
    def test_pairs_discovered(self):
        engine = get_engine()
        assert len(engine.available_pairs) >= 16
        assert ("en", "de") in engine.available_pairs
        assert ("en", "zh") in engine.available_pairs

    def test_routing(self):
        engine = get_engine()
        assert engine.route("en", "de") == [("en", "de")]
        assert engine.route("de", "fr") == [("de", "en"), ("en", "fr")]
        assert engine.route("de", "de") == []

    def test_translate_en_de(self):
        out = get_engine().translate_text("en", "de", "Hello, this is a test.")
        assert out
        assert "Hallo" in out or "hallo" in out.lower()

    def test_translate_en_zh(self):
        out = get_engine().translate_text("en", "zh", "The weather is nice.")
        assert out

    def test_sentence_splitting(self):
        from server.nmt import split_sentences
        s = split_sentences(
            "First sentence. Second one! Third? And a fourth. Fifth.", "en")
        assert len(s) == 5
        z = split_sentences("这是第一句。这是第二句！这是第三句。", "zh")
        assert len(z) == 3


class TestPipeline:
    def _wait(self, job, timeout=240):
        t0 = time.time()
        while job.status not in ("done", "error"):
            if time.time() - t0 > timeout:
                raise TimeoutError(f"job {job.id} stuck in {job.stage}: {job.message}")
            time.sleep(0.5)
        return job

    def test_full_translation_en_fr(self, parsed):
        job = run_translation(parsed, "auto", "fr", "bilingual",
                              pages=[1, 2])
        job = self._wait(job)
        assert job.status == "done", job.error
        assert job.source_lang == "en"
        assert job.stats["words"] > 100
        # all outputs exist and are non-trivial
        for key, path in job.outputs.items():
            p = Path(path)
            assert p.exists(), key
            assert p.stat().st_size > 500, (key, p.stat().st_size)

        # PDFs are valid
        import pymupdf as fitz
        for pdf_key in ("translated_pdf", "bilingual_pdf"):
            d = fitz.open(job.outputs[pdf_key])
            assert d.page_count >= 1
            txt = d[0].get_text()
            assert len(txt) > 100
            d.close()
        # the translated PDF must actually contain French, not the English
        d = fitz.open(job.outputs["translated_pdf"])
        tr_txt = d[0].get_text()
        d.close()
        assert "The State of Machine Translation" not in tr_txt
        assert any(w in tr_txt.lower() for w in
                   ("état", "traduction", "modèle", "neural", "la", "le"))

        # French text present in translation
        txt = Path(job.outputs["text_translation"]).read_text(encoding="utf-8")
        assert any(w in txt.lower() for w in ("la", "le", "et", "une", "des"))

    def test_pivoted_translation_de_fr(self, parsed):
        # en→fr direct is not the point here; force de source on english doc
        job = run_translation(parsed, "de", "fr", "translated")
        job = self._wait(job, timeout=300)
        # source 'de' given explicitly for an English document — engine will
        # translate whatever the text is; just assert it completes or errors
        # cleanly (never hangs, never crashes the process).
        assert job.status in ("done", "error")
        if job.status == "done":
            assert Path(job.outputs["translated_pdf"]).exists()

    def test_same_language_copy(self, parsed):
        job = run_translation(parsed, "en", "en", "translated", pages=[1])
        job = self._wait(job)
        assert job.status == "done", job.error
        txt = Path(job.outputs["text_translation"]).read_text(encoding="utf-8")
        assert "Machine translation" in txt

    def test_routing_and_unknown(self):
        engine = get_engine()
        # every supported language connects through the English hub
        for a in ("de", "fr", "es", "it", "pt", "ru", "ar", "zh"):
            for b in ("de", "fr", "es", "it", "pt", "ru", "ar", "zh"):
                if a != b:
                    assert engine.route(a, b), f"{a}->{b} should route"
        # unknown languages route nowhere
        assert engine.route("xx", "yy") == []
        assert engine.route("en", "xx") == []


class TestScannedOCR:
    """Build an image-only (scanned) PDF and run it through OCR + MT."""

    def _wait(self, job, timeout=300):
        t0 = time.time()
        while job.status not in ("done", "error"):
            if time.time() - t0 > timeout:
                raise TimeoutError(
                    f"job {job.id} stuck in {job.stage}: {job.message}")
            time.sleep(0.5)
        return job

    @staticmethod
    def _make_scanned_pdf(path: Path) -> None:
        import tempfile

        import pymupdf as fitz
        from PIL import Image, ImageDraw, ImageFont

        doc = fitz.open()
        for pno in range(2):
            page = doc.new_page(width=595, height=842)
            img = Image.new("RGB", (1190, 1684), "white")
            d = ImageDraw.Draw(img)
            f = ImageFont.truetype(
                "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 26)
            fb = ImageFont.truetype(
                "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 34)
            y = 100
            d.text((100, y), "Quarterly Logistics Report", font=fb,
                   fill="black")
            y += 90
            for para in (
                "Our distribution centers handled a record volume this quarter.",
                "Delivery times improved by twelve percent overall.",
                "The routing algorithm reduced fuel costs significantly.",
            ):
                d.text((100, y), para, font=f, fill="black")
                y += 60
            tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
            img.save(tmp.name)
            page.insert_image(page.rect, filename=tmp.name)
            tmp.close()
            import os
            os.unlink(tmp.name)
        doc.save(str(path))
        doc.close()

    def test_ocr_pipeline(self, tmp_path):
        scanned = tmp_path / "scanned.pdf"
        self._make_scanned_pdf(scanned)
        doc = pdf_parser.parse_pdf(scanned)
        # parser must flag both pages as scanned (no text layer)
        assert not any(p.has_text for p in doc.pages)
        assert doc.paragraphs == []

        from server.ocr import get_ocr
        assert get_ocr().available

        job = run_translation(doc, "auto", "fr", "bilingual")
        self._wait(job, timeout=300)
        assert job.status == "done", job.error
        assert job.stats.get("ocr_used") is True
        assert job.stats.get("source_language") == "en"
        txt = Path(job.outputs["text_translation"]).read_text(encoding="utf-8")
        assert len(txt) > 100
        # French output words
        assert any(w in txt.lower() for w in ("le", "la", "de", "des", "centres"))


class TestGiantParagraph:
    """A single 3000+ char block must not break PDF building (ReportLab
    'too large on page') — parser chunks it, writer splits defensively."""

    def test_giant_block(self, tmp_path):
        import pymupdf as fitz
        big = ("Machine translation is the use of software to translate text "
               "or content from one language to another. ") * 30
        doc = fitz.open()
        page = doc.new_page()
        page.insert_textbox(fitz.Rect(50, 50, 545, 800), big, fontsize=10)
        p = tmp_path / "giant.pdf"
        doc.save(str(p))
        doc.close()

        d = pdf_parser.parse_pdf(p)
        assert d.paragraphs, "no paragraphs parsed"
        assert all(len(x.text) <= 1900 for x in d.paragraphs)

        eng = get_engine()
        paras = []
        for para in d.paragraphs:
            para.translation = eng.translate_text("en", "fr", para.text)
            paras.append({"text": para.text,
                          "translation": para.translation,
                          "kind": para.kind,
                          "align": para.align,
                          "page": para.page})
        info = pdf_writer.DocInfo(title="Giant", filename="giant.pdf",
                                  page_count=1, word_count=600)
        b = tmp_path / "bi.pdf"
        t = tmp_path / "tr.pdf"
        pdf_writer.build_bilingual_pdf(paras, info, "en", "fr", b)
        pdf_writer.build_translated_pdf(paras, info, "fr", t)
        assert b.stat().st_size > 1000
        assert t.stat().st_size > 1000


class TestOnlineMT:
    """Mocked-network tests for the online fallback engine."""

    def _install_fake(self, monkeypatch, seen):
        from server import online_mt

        class FakeResp:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def read(self):
                qs = urllib.parse.parse_qs(
                    seen[-1].split("?", 1)[1], keep_blank_values=True)
                texts = [t for t in qs.get("q", [])]
                data = [
                    [[[t[::-1]]] for t in texts],  # reversed = fake MT
                    "fake",
                    "en",
                ]
                return json.dumps(data).encode("utf-8")

        def fake_urlopen(req, timeout=None):
            seen.append(req.full_url)
            return FakeResp()

        monkeypatch.setattr(online_mt.urllib.request, "urlopen",
                            fake_urlopen)

    def test_batching_and_parsing(self, monkeypatch):
        from server import online_mt
        seen = []
        self._install_fake(monkeypatch, seen)
        monkeypatch.setattr(online_mt, "DELAY_S", 0.0)

        texts = [f"sentence number {i}" for i in range(25)]
        out = online_mt.translate_texts(texts, "en", "tr")
        assert len(out) == 25
        assert len(seen) == 3  # 12 + 12 + 1 batches
        assert all(o == t[::-1] for o, t in zip(out, texts))
        assert "tl=tr" in seen[0] and "sl=en" in seen[0]

    def test_empty_passthrough_and_progress(self, monkeypatch):
        from server import online_mt
        seen = []
        self._install_fake(monkeypatch, seen)
        monkeypatch.setattr(online_mt, "DELAY_S", 0.0)

        calls = []
        out = online_mt.translate_texts(
            ["", "hello"], "en", "tr",
            on_batch=lambda d, t: calls.append((d, t)))
        assert out[0] == ""
        assert out[1] == "olleh"
        assert calls == [(2, 2)]


class TestClientBuild:
    """Server-side PDF building from browser-provided translations."""

    def _wait(self, job, timeout=120):
        t0 = time.time()
        while job.status not in ("done", "error"):
            if time.time() - t0 > timeout:
                raise TimeoutError(f"job stuck: {job.stage} {job.message}")
            time.sleep(0.2)
        return job

    def test_build_outputs(self, parsed):
        from server.pipeline import run_client_build
        paras = [
            {"text": "Machine translation improves communication.",
             "translation": "Makine çevirisi iletişimi geliştirir.",
             "kind": "body", "align": "left", "page": 0,
             "source": "text"},
            {"text": "Second line of the document.",
             "translation": "Belgenin ikinci satırı.",
             "kind": "body", "align": "left", "page": 1,
             "source": "text"},
        ]
        job = run_client_build(parsed, "en", "tr", "bilingual", paras)
        job = self._wait(job)
        assert job.status == "done", job.error
        for key in ("bilingual_pdf", "translated_pdf", "text_bilingual",
                    "text_translation", "json"):
            assert key in job.outputs, key
            assert Path(job.outputs[key]).stat().st_size > 100, key

        txt = Path(job.outputs["text_translation"]).read_text(
            encoding="utf-8")
        assert "Makine" in txt  # Turkish with proper glyphs
        payload = json.loads(Path(job.outputs["json"]).read_text(
            encoding="utf-8"))
        assert payload["target_language"] == "tr"
        assert payload["engine"].startswith("Online")
        assert job.stats["source_language"] == "en"

    def test_validation(self, parsed):
        from server.pipeline import run_client_build
        with pytest.raises(ValueError):
            run_client_build(parsed, "en", "tr", "bilingual", [])
        with pytest.raises(ValueError):
            run_client_build(parsed, "en", "tr", "bilingual",
                             [{"text": "only text"}])


class TestEngineSelection:
    """auto/local/online engine routing for pairs without local models."""

    def _wait(self, job, timeout=240):
        t0 = time.time()
        while job.status not in ("done", "error"):
            if time.time() - t0 > timeout:
                raise TimeoutError(f"job stuck: {job.stage} {job.message}")
            time.sleep(0.5)
        return job

    def test_online_pair_unavailable_raises(self, parsed, monkeypatch):
        from server import online_mt
        monkeypatch.setattr(online_mt, "is_available",
                            lambda timeout=3.0: False)
        with pytest.raises(ValueError, match="online"):
            run_translation(parsed, "auto", "tr", "bilingual")

    def test_local_engine_refuses_online_pair(self, parsed):
        with pytest.raises(ValueError, match="local model"):
            run_translation(parsed, "en", "ja", "bilingual",
                            engine_name="local")

    def test_online_pipeline_with_stubbed_service(self, parsed, monkeypatch):
        """Full pipeline through the online branch (service stubbed)."""
        from server import online_mt
        monkeypatch.setattr(online_mt, "is_available",
                            lambda timeout=3.0: True)
        monkeypatch.setattr(
            online_mt, "translate_texts",
            lambda texts, src, tgt, on_batch=None: [
                f"[tr] {t[:40]}" for t in texts])

        job = run_translation(parsed, "en", "tr", "translated", pages=[1])
        assert job.engine_name == "online"
        job = self._wait(job)
        assert job.status == "done", job.error
        txt = Path(job.outputs["text_translation"]).read_text(
            encoding="utf-8")
        assert "[tr] " in txt
        assert job.stats["route"] == ["online engine"]


class TestPdfWriter:
    def test_bilingual_cjk_fonts(self, tmp_path):
        paras = [
            {"text": "标题", "translation": "Headline", "kind": "title",
             "align": "center"},
            {"text": "这是中文段落。", "translation": "This is a paragraph.",
             "kind": "body", "align": "left"},
        ]
        info = pdf_writer.DocInfo(title="T", filename="t.pdf")
        out = tmp_path / "bi.pdf"
        pdf_writer.build_bilingual_pdf(paras, info, "zh", "en", out)
        assert out.stat().st_size > 1000
        import pymupdf as fitz
        d = fitz.open(str(out))
        assert d.page_count >= 1
        d.close()

    def test_arabic_shaping(self, tmp_path):
        from server.pdf_writer import shape_text
        shaped = shape_text("الترجمة", "ar")
        assert shaped != "الترجمة"  # reshaped into presentation forms

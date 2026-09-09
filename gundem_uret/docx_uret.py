# -*- coding: utf-8 -*-
"""
Gündem .docx üreticisi.

Örnek gündem PDF'i birebir ölçülerek çözümlenmiştir; aynı görsel dil Word'de
şöyle kurulur:

  - Sayfa : A4 dikey, sol/sağ kenar boşluğu ~1,1 cm
  - Başlık: logo solda + "T.C. / SAĞLIK BİLİMLERİ ÜNİVERSİTESİ /
             Bilimsel Araştırma Projeleri Koordinatörlüğü" (Times New Roman 12 pt bold)
  - Bilgi satırları: Toplantı Tarihi / Toplantı Sayısı (TNR 11 pt), "GÜNDEM"
  - Ana tablo (6 sütun): Sıra No | Proje Türü | Proje Adı | Süre | Yürütücü
    | Önerilen Tutar  (başlıklar: Arial italic 9 pt; içerik: Calibri 9 pt)
  - Madde bloğu: ana satır + hakem özeti satırı + hakem satırları
    (ad-A.B.D. | kurum | karar) + raportör satırı
  - İkinci bölüm: KARAR MADDELERİ (iptal/ek süre/tür değişikliği...)

Tüm ayarlar ToplantiBilgisi ve maddelerden gelir; kod görünümü değiştirmek
istenirse buradaki sabitler (SUTUN_GENISLIKLERI, FONTLAR) yeterlidir.
"""
from __future__ import annotations

import os
from typing import List, Optional

from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_ALIGN_VERTICAL
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

from .model import GundemMaddesi, HakemGorusu, KararMaddesi, ToplantiBilgisi

# ---------------------------------------------------------------------------
# Görsel sabitler (örnek PDF'ten ölçüldü)
# ---------------------------------------------------------------------------
F_BAŞLIK = "Times New Roman"
F_TABLO = "Calibri"
F_BASLIK_KOLON = "Arial"

SUTUN_GENISLIK_CM = [1.0, 3.4, 4.6, 1.3, 5.2, 3.3]   # toplam 18.8 cm
SAYFA_GENISLIK_CM = 21.0
# A4 (21 cm) - sol/sag 1,1 cm kenarlik = 11906 - 2*624 = 10658 twip metin alani
METIN_ALAN_DXA = 10658

SUTUN_HIZA = {
    0: WD_ALIGN_PARAGRAPH.CENTER,
    1: WD_ALIGN_PARAGRAPH.LEFT,
    2: WD_ALIGN_PARAGRAPH.LEFT,
    3: WD_ALIGN_PARAGRAPH.CENTER,
    4: WD_ALIGN_PARAGRAPH.LEFT,
    5: WD_ALIGN_PARAGRAPH.CENTER,
}

YAZI = 9            # tablo içi punto
BASLIK_YAZI = 12    # üst kurum adı
BILGI_YAZI = 11


# ---------------------------------------------------------------------------
# Düşük seviye yardımcılar
# ---------------------------------------------------------------------------
def _paragraf_ayarla(p, once: float = 0, sonra: float = 0, satir: float = 1.0):
    p.paragraph_format.space_before = Pt(once)
    p.paragraph_format.space_after = Pt(sonra)
    p.paragraph_format.line_spacing = satir


def _calistir(p, metin: str, boyut: int = YAZI, koyu: bool = False,
              italik: bool = False, font: str = F_TABLO,
              hiza: Optional[int] = None):
    """Bir paragrafa yeni satır parçaları ekler (çok satırlı hücreler için)."""
    parcalar = str(metin).split("\n") if metin else [""]
    for i, parca in enumerate(parcalar):
        if i > 0:
            p.add_run().add_break()
        r = p.add_run(parca)
        r.font.name = font
        r.font.size = Pt(boyut)
        r.font.bold = koyu
        r.font.italic = italik
        # Türkçe karakterler için Doğu Asya font adını da ata
        r._element.rPr.rFonts.set(qn("w:eastAsia"), font)
        r._element.rPr.rFonts.set(qn("w:cs"), font)
    if hiza is not None:
        p.alignment = hiza


def _hucre_yaz(cell, satirlar, hiza=None, dikey: str = "center"):
    """satirlar: list[(metin, {boyut, koyu, italik, font})]"""
    ilk = True
    for metin, stil in satirlar:
        p = cell.paragraphs[0] if ilk else cell.add_paragraph()
        ilk = False
        _paragraf_ayarla(p, 0, 0, 1.0)
        _calistir(p, metin,
                  boyut=stil.get("boyut", YAZI),
                  koyu=stil.get("koyu", False),
                  italik=stil.get("italik", False),
                  font=stil.get("font", F_TABLO),
                  hiza=hiza)
    if dikey == "center":
        cell.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
    elif dikey == "top":
        cell.vertical_alignment = WD_ALIGN_VERTICAL.TOP
    return cell


def _hucre_kenarlik(cell, kenar: str, boyut: int = 4):
    """Kenar çizgisi: kenar: 'top'|'bottom'|'start'|'end'|'insideH'..."""
    tcPr = cell._tc.get_or_add_tcPr()
    kenarlik = tcPr.find(qn("w:tcBorders"))
    if kenarlik is None:
        kenarlik = OxmlElement("w:tcBorders")
        tcPr.append(kenarlik)
    el = kenarlik.find(qn(f"w:{kenar}"))
    if el is None:
        el = OxmlElement(f"w:{kenar}")
        kenarlik.append(el)
    el.set(qn("w:val"), "single")
    el.set(qn("w:sz"), str(boyut))
    el.set(qn("w:color"), "000000")


def _hucre_dolgu(cell, ust: int = 30, alt: int = 30, sol: int = 80, sag: int = 80):
    tcPr = cell._tc.get_or_add_tcPr()
    dolgu = OxmlElement("w:tcMar")
    for ad, deger in (("top", ust), ("start", sol), ("bottom", alt), ("end", sag)):
        el = OxmlElement(f"w:{ad}")
        el.set(qn("w:w"), str(deger))
        el.set(qn("w:type"), "dxa")
        dolgu.append(el)
    tcPr.append(dolgu)


def _twips_kesin(genislikler_cm, toplam_dxa: int) -> List[int]:
    """cm listesini, toplamı tam toplam_dxa olan twip listesine çevirir.
    Artık twip'ler kesiri en büyük sütunlara tek tek dağıtılır."""
    ham = [g * 566.929 for g in genislikler_cm]
    tw = [int(h) for h in ham]
    artan = sorted(range(len(ham)), key=lambda i: ham[i] - int(ham[i]),
                   reverse=True)
    for i in artan[: toplam_dxa - sum(tw)]:
        tw[i] += 1
    return tw


def _tablo_sabitlestir(tablo, genislikler_cm: List[float],
                       toplam_dxa: int, cerceve: bool = True):
    """Tabloyu Word'ün kırpma/taşırma yapmadan çizeceği tutarlı modele
    getirir: tblW (dxa, tam metin alanı) + doğru tblGrid + tek tblLayout
    (fixed), şema sırasında; hücre tcW'leri kaldırılır, sütunlar yalnız
    ızgaradan gelir (tüm satırlarda aynı genişlik garantisi)."""
    tbl = tablo._tbl
    tblPr = tbl.tblPr
    for el in list(tblPr):
        tblPr.remove(el)
    tw = _twips_kesin(genislikler_cm, toplam_dxa)
    # CT_TblPrBase sırası: tblW, jc, tblBorders, tblLayout
    tblW = OxmlElement("w:tblW")
    tblW.set(qn("w:w"), str(toplam_dxa))
    tblW.set(qn("w:type"), "dxa")
    tblPr.append(tblW)
    jc = OxmlElement("w:jc")
    jc.set(qn("w:val"), "center")
    tblPr.append(jc)
    if cerceve:
        kenarlik = OxmlElement("w:tblBorders")
        for ad in ("top", "left", "bottom", "right", "insideH", "insideV"):
            el = OxmlElement("w:" + ad)
            el.set(qn("w:val"), "single")
            el.set(qn("w:sz"), "4")
            el.set(qn("w:color"), "000000")
            kenarlik.append(el)
        tblPr.append(kenarlik)
    yerlesim = OxmlElement("w:tblLayout")
    yerlesim.set(qn("w:type"), "fixed")
    tblPr.append(yerlesim)
    # ızgara: hedef sütun genişlikleri
    tblGrid = tbl.find(qn("w:tblGrid"))
    if tblGrid is None:
        tblGrid = OxmlElement("w:tblGrid")
        tblPr.addnext(tblGrid)
    for gc in list(tblGrid):
        tblGrid.remove(gc)
    for w in tw:
        gc = OxmlElement("w:gridCol")
        gc.set(qn("w:w"), str(w))
        tblGrid.append(gc)
    # hücre genişlik bildirimlerini kaldir -> tek otorite ızgara
    for tr in tbl.tr_lst:
        for tc in tr.tc_lst:
            tcPr = tc.find(qn("w:tcPr"))
            if tcPr is None:
                continue
            tcW = tcPr.find(qn("w:tcW"))
            if tcW is not None:
                tcPr.remove(tcW)


def _tablo_grid(tablo, genislikler_cm: List[float]):
    """Ana gündem tablosu: sayfa metin alanına tam oturan sabit düzen."""
    _tablo_sabitlestir(tablo, genislikler_cm, METIN_ALAN_DXA, cerceve=True)


def _satir_ekle(tablo, hucre_sayisi: int):
    return tablo.add_row()


# ---------------------------------------------------------------------------
# Belge iskeleti
# ---------------------------------------------------------------------------
def _belge_ac(logo_yolu: Optional[str], bilgi: ToplantiBilgisi) -> Document:
    doc = Document()
    # sayfa: A4 dikey, dar kenarlıklar
    bolum = doc.sections[0]
    bolum.page_width = Cm(21.0)
    bolum.page_height = Cm(29.7)
    bolum.left_margin = Cm(1.1)
    bolum.right_margin = Cm(1.1)
    bolum.top_margin = Cm(1.4)
    bolum.bottom_margin = Cm(1.4)

    # ---- Başlık bloğu: logo + kurum adı (yalnız ilk sayfada, gövdede) ----
    tablo_baslik = doc.add_table(rows=1, cols=2)
    tablo_baslik.autofit = False
    tablo_baslik.alignment = WD_TABLE_ALIGNMENT.CENTER
    hucre_logo, hucre_metin = tablo_baslik.rows[0].cells

    if logo_yolu and os.path.exists(logo_yolu):
        p_logo = hucre_logo.paragraphs[0]
        p_logo.alignment = WD_ALIGN_PARAGRAPH.CENTER
        _paragraf_ayarla(p_logo, 0, 0, 1.0)
        p_logo.add_run().add_picture(logo_yolu, width=Cm(2.2), height=Cm(1.96))
    hucre_logo.vertical_alignment = WD_ALIGN_VERTICAL.CENTER

    for metin in (bilgi.kurum_ust, bilgi.kurum_adi, bilgi.kurum_alt):
        p = hucre_metin.paragraphs[0] if metin == bilgi.kurum_ust else hucre_metin.add_paragraph()
        _paragraf_ayarla(p, 0, 0, 1.0)
        _calistir(p, metin, boyut=BASLIK_YAZI, koyu=True, font=F_BAŞLIK,
                  hiza=WD_ALIGN_PARAGRAPH.CENTER)
    hucre_metin.vertical_alignment = WD_ALIGN_VERTICAL.CENTER

    # ---- Toplantı bilgisi (örnekteki gibi iki sütun, çerçevesiz) ----
    tablo_bilgi = doc.add_table(rows=1, cols=2)
    tablo_bilgi.autofit = False
    tablo_bilgi.alignment = WD_TABLE_ALIGNMENT.CENTER
    sol, sag = tablo_bilgi.rows[0].cells

    for hucre, etiket, deger in ((sol, "Toplantı Tarihi", bilgi.tarih),
                                 (sag, "Toplantı Sayısı", bilgi.sayi)):
        p1 = hucre.paragraphs[0]
        _paragraf_ayarla(p1, 4, 0, 1.0)
        _calistir(p1, etiket, boyut=BILGI_YAZI, koyu=True, font=F_BAŞLIK,
                  hiza=WD_ALIGN_PARAGRAPH.LEFT)
        p2 = hucre.add_paragraph()
        _paragraf_ayarla(p2, 0, 0, 1.0)
        # örnekte değer etiketin hafif sağında başlar
        p2.paragraph_format.left_indent = Cm(0.25)
        _calistir(p2, deger, boyut=BILGI_YAZI, font=F_BAŞLIK,
                  hiza=WD_ALIGN_PARAGRAPH.LEFT)

    # ---- GÜNDEM ----
    p = doc.add_paragraph()
    _paragraf_ayarla(p, 6, 8, 1.0)
    _calistir(p, "GÜNDEM", boyut=BILGI_YAZI, koyu=True, font=F_BAŞLIK,
              hiza=WD_ALIGN_PARAGRAPH.CENTER)

    return doc


def _icerik_tablosu(doc: Document) -> object:
    """6 sütunlu ana tabloyu kurar ve başlık satırını yazar."""
    tablo = doc.add_table(rows=1, cols=6)
    _tablo_grid(tablo, SUTUN_GENISLIK_CM)
    basliklar = ["Sıra No", "Proje Türü", "Proje Adı", "Süre", "Yürütücü",
                 "Önerilen Tutar"]
    hucreler = tablo.rows[0].cells
    for i, metin in enumerate(basliklar):
        _hucre_dolgu(hucreler[i])
        _hucre_yaz(hucreler[i], [(metin, {"koyu": True, "italik": True,
                                          "font": F_BASLIK_KOLON, "boyut": YAZI})],
                   hiza=WD_ALIGN_PARAGRAPH.CENTER)
    return tablo


def _dolu_satir(tablo, hucre_icerikleri) -> None:
    """Verilen 6 hücre içeriğini [(metin, stil), ...] yeni satıra yazar."""
    satir = tablo.add_row()
    for i, icerik in enumerate(hucre_icerikleri):
        hucre = satir.cells[i]
        _hucre_dolgu(hucre)
        _hucre_yaz(hucre, icerik, hiza=SUTUN_HIZA.get(i, WD_ALIGN_PARAGRAPH.LEFT))
    return satir


def _bos_satir(tablo, yukseklik_cm: float = 0.25) -> None:
    satir = tablo.add_row()
    hucre = satir.cells[0]
    _hucre_dolgu(hucre, ust=20, alt=20, sol=20, sag=20)
    # yüksekliği sabitle (küçük hava payı)
    trPr = satir._tr.get_or_add_trPr()
    yuk = OxmlElement("w:trHeight")
    yuk.set(qn("w:val"), str(int(yukseklik_cm * 567)))
    yuk.set(qn("w:hRule"), "exact")
    trPr.append(yuk)


def _not_satiri(tablo, yukseklik_cm: float = 0.7):
    """Madde sonunda notlar için boş (çerçeveli) satır."""
    satir = tablo.add_row()
    hucre = _birlestir(satir, 0, 5)
    _hucre_dolgu(hucre, ust=60, alt=60, sol=60, sag=60)
    trPr = satir._tr.get_or_add_trPr()
    yuk = OxmlElement("w:trHeight")
    yuk.set(qn("w:val"), str(int(yukseklik_cm * 567)))
    yuk.set(qn("w:hRule"), "atLeast")
    trPr.append(yuk)


def _birlestir(satir, baslangic: int, bitis: int):
    """satir.cells[baslangic..bitis] aralığını birleştirir."""
    hucre = satir.cells[baslangic]
    for i in range(baslangic + 1, bitis + 1):
        hucre = hucre.merge(satir.cells[i])
    return hucre


def _alt_bolum_metni(madde: GundemMaddesi) -> str:
    """'3 Olumlu Hakem Görüşü' özet satırını üretir."""
    from .model import hakem_ozet_metni
    kararlar = [h.karar_kisa for h in madde.hakemler]
    return hakem_ozet_metni(kararlar)


# ---------------------------------------------------------------------------
# Madde çizimi
# ---------------------------------------------------------------------------
def _madde_ciz(tablo, madde: GundemMaddesi, sıra_no: int) -> None:
    # --- ana satır ---
    tutar_parcalar = [(f"{madde.butce_tl} TL", {"koyu": True})]
    if madde.tekrar_gundem:
        tutar_parcalar.append(("(Tekrar Gündem)", {}))
    _dolu_satir(tablo, [
        [(str(sıra_no), {"koyu": True})],
        [(madde.proje_turu or "-", {"koyu": True})],
        [(madde.proje_adi or "-", {"koyu": True})],
        [(madde.sure_ay, {"koyu": True})],
        [(satir, {"koyu": idx == 0})
         for idx, satir in enumerate(madde.yurutucu_gosterim().split("\n"))],
        tutar_parcalar,
    ])

    # --- hakem özeti satırı ---
    ozet = _alt_bolum_metni(madde)
    if ozet:
        satir = tablo.add_row()
        hucre = _birlestir(satir, 0, 5)
        _hucre_dolgu(hucre, ust=40, alt=40)
        _hucre_yaz(hucre, [(ozet, {})], hiza=WD_ALIGN_PARAGRAPH.CENTER)
        hucre.vertical_alignment = WD_ALIGN_VERTICAL.CENTER

    # --- hakem satırları ---
    for hakem in madde.hakemler:
        satir = tablo.add_row()
        ad_blok = []
        if hakem.hakem_adi:
            ad_blok.append((hakem.hakem_adi, {}))
        if hakem.abd:
            ad_blok.append((hakem.abd, {}))
        hucre = _birlestir(satir, 0, 1)
        _hucre_dolgu(hucre)
        _hucre_yaz(hucre, ad_blok, hiza=WD_ALIGN_PARAGRAPH.LEFT)
        hucre = _birlestir(satir, 2, 4)
        _hucre_dolgu(hucre)
        _hucre_yaz(hucre, [(hakem.kurum, {})], hiza=WD_ALIGN_PARAGRAPH.LEFT)
        hucre = satir.cells[5]
        _hucre_dolgu(hucre)
        _hucre_yaz(hucre, [(hakem.karar_kisa, {"koyu": hakem.karar_kisa == "TEKRAR DÜZENLENMELİ"})],
                   hiza=WD_ALIGN_PARAGRAPH.CENTER)

    # --- raportör satırı ---
    if madde.raportor:
        satir = tablo.add_row()
        hucre = _birlestir(satir, 0, 5)
        _hucre_dolgu(hucre, ust=40, alt=40)
        _hucre_yaz(hucre, [(madde.raportor, {"koyu": True})],
                   hiza=WD_ALIGN_PARAGRAPH.CENTER)
        hucre.vertical_alignment = WD_ALIGN_VERTICAL.CENTER

    # --- raportörden (yoksa hakem listesinden) sonra: notlar için boş satır ---
    _not_satiri(tablo, 0.7)


def _karar_maddesi_ciz(tablo, madde: KararMaddesi, sıra_no: int) -> None:
    tur_metni = madde.proje_turu
    if madde.proje_no:
        tur_metni = f"{tur_metni}\n({madde.proje_no})" if tur_metni else f"({madde.proje_no})"
    tutar_parcalar = []
    if madde.butce_tl:
        tutar_parcalar.append((f"{madde.butce_tl} TL", {"koyu": True}))
    if madde.harcanan_tl:
        tutar_parcalar.append((f"(Harcanan: {madde.harcanan_tl} TL)", {}))

    _dolu_satir(tablo, [
        [(str(sıra_no), {"koyu": True})],
        [(satir, {"koyu": True}) for satir in tur_metni.split("\n")],
        [(madde.proje_adi or "-", {"koyu": True})],
        [(madde.sure_ay, {"koyu": True})],
        [((satir if i == 0 else satir), {"koyu": i == 0})
         for i, satir in enumerate(
             (f"{madde.yurutucu_adi} ({madde.birim})" if madde.birim
              else madde.yurutucu_adi).split("\n"))],
        tutar_parcalar,
    ])

    # işlem metni (örn. PROJENİN İPTALİ)
    if madde.islem:
        satir = tablo.add_row()
        hucre = _birlestir(satir, 0, 5)
        _hucre_dolgu(hucre, ust=40, alt=40)
        _hucre_yaz(hucre, [(madde.islem, {"koyu": True})],
                   hiza=WD_ALIGN_PARAGRAPH.CENTER)
        hucre.vertical_alignment = WD_ALIGN_VERTICAL.CENTER

    _bos_satir(tablo, 0.1)

    # alt satır (KOMİSYON vb.)
    satir = tablo.add_row()
    hucre = _birlestir(satir, 0, 5)
    _hucre_dolgu(hucre, ust=40, alt=40)
    _hucre_yaz(hucre, [("KOMİSYON", {})], hiza=WD_ALIGN_PARAGRAPH.CENTER)
    hucre.vertical_alignment = WD_ALIGN_VERTICAL.CENTER

    _bos_satir(tablo, 0.3)


# ---------------------------------------------------------------------------
# Ana işlev
# ---------------------------------------------------------------------------
def olustur(bilgi: ToplantiBilgisi,
            maddeler: List[GundemMaddesi],
            karar_maddeleri: List[KararMaddesi],
            cikti_yolu: str,
            logo_yolu: Optional[str] = None,
            numara_goster: bool = True) -> str:
    doc = _belge_ac(logo_yolu, bilgi)
    tablo = _icerik_tablosu(doc)

    # --- 1. bölüm: PDF tabanlı maddeler ---
    for i, madde in enumerate(maddeler, start=1):
        _madde_ciz(tablo, madde, sıra_no=i)

    # --- 2. bölüm: karar maddeleri ---
    if karar_maddeleri:
        if bilgi.alt_bolum_basligi:
            satir = tablo.add_row()
            hucre = _birlestir(satir, 0, 5)
            _hucre_dolgu(hucre, ust=60, alt=60)
            _hucre_yaz(hucre, [(bilgi.alt_bolum_basligi, {"koyu": True})],
                       hiza=WD_ALIGN_PARAGRAPH.CENTER)
            hucre.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
        for i, madde in enumerate(karar_maddeleri, start=1):
            _karar_maddesi_ciz(tablo, madde, sıra_no=i)

    # alt bilgi: sayfa numarası (sağ alt)
    if numara_goster:
        alt = doc.sections[0].footer
        p = alt.paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        p.paragraph_format.space_before = Pt(0)
        p.paragraph_format.space_after = Pt(0)
        r = p.add_run()
        r.font.size = Pt(9)
        fld1 = OxmlElement("w:fldChar"); fld1.set(qn("w:fldCharType"), "begin")
        instr = OxmlElement("w:instrText"); instr.set(qn("xml:space"), "preserve")
        instr.text = " PAGE "
        fld2 = OxmlElement("w:fldChar"); fld2.set(qn("w:fldCharType"), "end")
        r._r.append(fld1); r._r.append(instr); r._r.append(fld2)

    # normal stil varsayılan fontunu da netleştir
    stiller = doc.styles["Normal"]
    stiller.font.name = F_TABLO
    stiller.font.size = Pt(YAZI)

    # Son kalibrasyon: tüm tablolar tam metin alanına oturur (taşma olmaz)
    for tbl, genislik, cerceve in ((doc.tables[0], [3.6, 15.2], False),
                                   (doc.tables[1], [9.4, 9.4], False),
                                   (doc.tables[2], SUTUN_GENISLIK_CM, True)):
        _tablo_sabitlestir(tbl, genislik, METIN_ALAN_DXA, cerceve=cerceve)

    os.makedirs(os.path.dirname(os.path.abspath(cikti_yolu)), exist_ok=True)
    doc.save(cikti_yolu)
    return cikti_yolu

# -*- coding: utf-8 -*-
"""
PDF'ten yapılandırılmış veri çıkarma.

İki tür girdi desteklenir (içerikten otomatik tanınır):
  1. PROJE ÖNERİ FORMU (F-1)      -> proje bilgileri
  2. PROJE DEĞERLENDİRME FORMU    -> hakem adı, puanı, kararı

Ek olarak "belge bölme" desteklenir: tek bir PDF içinde birden çok form
(ör. 1 proje formu + 3 hakem formu üst üste) varsa sayfalar türlerine göre
ayrılıp her form ayrı belge gibi okunur.

Not: Bu formlar tarayıcıdan yazdırılmış tablo tipi PDF'lerdir; metin katmanı
her satırda etiket ve değeri ayrı sütunlarda tutar. Çıkarımda kelime
koordinatları (pdfplumber) + düz metin kalıpları (pypdf) birlikte kullanılır.
"""
from __future__ import annotations

import re
from typing import List, Optional, Tuple

import pdfplumber
from pypdf import PdfReader

from .model import kisa_karar

PARA_RE = re.compile(r"^\d{1,3}(?:\.\d{3})*,\d{2}$")
SAYI_RE = re.compile(r"^(\d{1,3}(?:\.\d{3})*,\d{2})")

# --------------------------------------------------------------------------
# Sayfa türü belirleme ve belge bölme
# --------------------------------------------------------------------------
def _sayfa_metni(p) -> str:
    """Sayfa metnini alır; e-imzalı PDF'lerdeki NUL vb. denetim karakterlerini
    temizler (bu karakterler 'PROJE DEĞERLENDİRME FORMU' gibi aramaları bozar)."""
    return ((p.extract_text() or "").replace("\u0000", "").replace("\x00", ""))


def pdf_sayfa_tipleri(path: str) -> List[str]:
    """Her sayfa için 'proje' | 'hakem' | 'diger' döndürür.

    Ayraç işaretler:
      - hakem formu sayfası (uzun biçim): 'PROJE DEĞERLENDİRME FORMU' /
        'TOPLAM PUAN' / 'DEĞERLENDİRME SONUCUNUZ'
      - hakem formu sayfası (kısa biçim): 'EVET HAYIR KISMEN' /
        'DEĞERLENDİRME SONUCU' / 'PROJENİN BAŞLIĞI'
      - proje formu sayfası: 'PROJE ÖNERİ FORMU' / '1.PROJE BİLGİLERİ'
    Etiketsiz sayfalar 'diger' olur (önceki formun devamı sayılır).
    """
    oku = PdfReader(path)
    tipler = []
    for p in oku.pages:
        t = _sayfa_metni(p).upper()
        if ("PROJE DEĞERLENDİRME FORMU" in t or "TOPLAM PUAN" in t
                or "DEĞERLENDİRME SONUCUNUZ" in t
                or "EVET HAYIR KISMEN" in t
                or "DEĞERLENDİRME SONUCU" in t):
            tipler.append("hakem")
        elif ("PROJE ÖNERİ FORMU" in t or "1.PROJE" in t.replace(" ", "")
              or ("PROJE BİLGİLERİ" in t and "BÜTÇESİ" not in t)):
            tipler.append("proje")
        else:
            tipler.append("diger")
    return tipler


def belge_bol(path: str) -> List[Tuple[str, int, int]]:
    """Bir PDF içindeki ardışık formları ayırır.

    Dönen: [(tip, ilk_sayfa, son_sayfa), ...]  (tip: 'proje' | 'hakem')
    """
    oku = PdfReader(path)
    n = len(oku.pages)
    tipler = pdf_sayfa_tipleri(path)
    dokumanlar = []
    akim = None
    bas = 0
    for i, tip in enumerate(tipler):
        if tip in ("proje", "hakem") and tip != akim:
            if akim in ("proje", "hakem"):
                dokumanlar.append((akim, bas, i - 1))
            akim, bas = tip, i
    if akim in ("proje", "hakem"):
        dokumanlar.append((akim, bas, n - 1))
    return dokumanlar


def dosya_turu(path: str) -> str:
    """'proje' | 'hakem' | 'karisik' | 'bilinmiyor' (ilk ~4 sayfaya bakar)."""
    tipler = pdf_sayfa_tipleri(path)[:4]
    proje = tipler.count("proje") > 0
    hakem = tipler.count("hakem") > 0
    if proje and hakem:
        return "karisik"
    if proje:
        return "proje"
    if hakem:
        return "hakem"
    return "bilinmiyor"


# --------------------------------------------------------------------------
# Genel yardımcılar
# --------------------------------------------------------------------------
def _duz_metin(path: str, ilk_sayfa: int = 0, son_sayfa: Optional[int] = None) -> str:
    oku = PdfReader(path)
    sayfalar = oku.pages[ilk_sayfa:(son_sayfa + 1) if son_sayfa is not None else None]
    return "\n".join(_sayfa_metni(p) for p in sayfalar)


def _kelimeler(path: str, sayfa: int = 0) -> List[dict]:
    """Bir sayfanın kelimelerini (metin, x0, x1, top, bottom) döndürür."""
    with pdfplumber.open(path) as pdf:
        page = pdf.pages[sayfa]
        return page.extract_words()


def _bolge_metni(kelimeler, x0: float, y0: float, x1: float, y1: float) -> str:
    """Verilen dikdörtgen bölgedeki kelimeleri satır satır birleştirir."""
    sec = [k for k in kelimeler if k["x0"] >= x0 - 2 and k["x1"] <= x1 + 2
           and k["top"] >= y0 - 2 and k["bottom"] <= y1 + 2]
    satirlar: dict = {}
    for k in sec:
        satirlar.setdefault(round(k["top"] / 4), []).append(k)
    metinler = []
    for anahtar in sorted(satirlar):
        sozler = sorted(satirlar[anahtar], key=lambda k: k["x0"])
        metinler.append(" ".join(s["text"] for s in sozler))
    return "\n".join(metinler)


def _isaretli_satir(blok: str) -> str:
    """'( X )' işareti hangi satırdaysa o satırın tamamını döndürür.

    İşaret satırın başında ('( X ) Öncelikle desteklenmelidir') ya da sonunda
    ('Proje önerilen haliyle desteklenmeli ( X )') olabilir; bu yüzden
    satır bazında arama yapılır (regex \\s* satır atlamasına yol açmaz).
    """
    for satir in (blok or "").splitlines():
        if re.search(r"\(\s*X\s*\)", satir, re.I):
            return satir.strip()
    return ""


def _etiket_sonrasi(duz_metin: str, etiket: str, sonraki_etiketler, en_fazla: int = 12) -> str:
    """Düz metinde bir etiketten sonra gelen değeri (sonraki etikete kadar) bulur."""
    idx = duz_metin.find(etiket)
    if idx < 0:
        return ""
    son = len(duz_metin)
    for sonraki in sonraki_etiketler:
        i2 = duz_metin.find(sonraki, idx + len(etiket))
        if 0 <= i2 < son:
            son = i2
    parca = duz_metin[idx + len(etiket):son].strip()
    parca = re.sub(r"\s+", " ", parca)
    sozler = parca.split()
    return " ".join(sozler[:en_fazla])


# --------------------------------------------------------------------------
# Proje formu (F-1) çıkarımı
# --------------------------------------------------------------------------
def proje_formu_oku(path: str, ilk_sayfa: int = 0, son_sayfa: Optional[int] = None) -> dict:
    """
    F-1 proje öneri formundan: tür, ad, süre, yürütücü, kurum, A.B.D., bütçe.
    Etiket sütunu solda (x~33-130), değerler aynı satırın sağında veya bir
    sonraki satırdadır.
    """
    duz = _duz_metin(path, ilk_sayfa, son_sayfa)
    sayfa0 = _kelimeler(path, ilk_sayfa)

    def deger(etiket: str, sonraki: List[str]) -> str:
        """Etiket satırının sağındaki değeri döndürür (y koordinatına göre)."""
        eslesen = [k for k in sayfa0 if etiket.split()[0] in k["text"] and k["x0"] < 150]
        if not eslesen:
            return _etiket_sonrasi(duz, etiket, sonraki, 30)
        k = eslesen[0]
        sag = [w for w in sayfa0
               if abs(w["top"] - k["top"]) < 14 and w["x0"] > k["x1"] + 20]
        sag.sort(key=lambda w: (w["top"], w["x0"]))
        return " ".join(w["text"] for w in sag).strip()

    # --- Proje adı: '1.1. Proje Başlığı'ndan sonraki 1-2 satır (tam genişlik) ---
    proje_adi = ""
    for w in sayfa0:
        if w["text"] == "Başlığı" and w["x0"] < 130:
            devam = [v for v in sayfa0 if v["top"] > w["top"] + 5 and v["top"] < w["top"] + 45
                     and v["x0"] > 25]
            satirlar: dict = {}
            for v in devam:
                satirlar.setdefault(round(v["top"] / 4), []).append(v)
            for anahtar in sorted(satirlar):
                sozler = sorted(satirlar[anahtar], key=lambda v: v["x0"])
                proje_adi += " ".join(s["text"] for s in sozler) + " "
            break
    proje_adi = re.sub(r"\s+", " ", proje_adi).strip()
    if not proje_adi:
        proje_adi = _etiket_sonrasi(duz, "Proje Başlığı", ["1.3.", "1.2."], 40)

    sonuc = {
        "proje_turu": deger("Türü", ["1.4.", "1.5."]),
        "proje_adi": proje_adi,
        "sure_ay": "",
        "yurutucu_adi": "",
        "yurutucu_kurum": "",
        "yurutucu_abd": "",
        "butce_tl": "",
    }

    # --- Süre: 'Önerilen Proje Süresi' başlığının altında '6 ay' ---
    adaylar = [w for w in sayfa0 if w["text"] == "Süresi" and w["x0"] < 130]
    if adaylar:
        w = adaylar[-1]
        asagi = [v for v in sayfa0 if v["top"] > w["top"] + 10 and v["top"] < w["top"] + 40
                 and v["x0"] < 200]
        asagi.sort(key=lambda v: (v["top"], v["x0"]))
        if asagi:
            # '1.5.' gibi bölüm etiketinden sonrasını at (sonraki bölüm başlığı)
            kesim = None
            for v in asagi:
                if re.match(r"^\d+\.\d+\.?$", v["text"]):
                    kesim = v["top"]
                    break
            sec = [v for v in asagi if kesim is None or v["top"] < kesim - 2]
            sonuc["sure_ay"] = " ".join(
                v["text"] for v in sec
                if not re.match(r"^\d{2}[-.]\d{2}[-.]\d{4}$", v["text"])
                and not re.match(r"^\d{1,2}:\d{2}:\d{2}$", v["text"])
                and (not v["text"].isdigit() or len(v["text"]) < 4)
            ).strip()
    m = re.search(r"(\d{1,3})\s*(ay|AY|Ay)", duz)
    if m and not sonuc["sure_ay"]:
        sonuc["sure_ay"] = m.group(0)

    # --- Yürütücü adı: 'SOYADI' etiketinin sağında ---
    # Önce düz metinden (satır kaydırmalı adları da yakalar), olmazsa kelime katmanı
    m_ad = re.search(
        r"Ünvanı, Adı\s*SOYADI\s*([A-Za-zÇĞİÖŞÜçğıöşü0-9./' -]{3,90}?)"
        r"\s*(?:Bölümü|Fakülte|Ana Bilim|Elektronik|Tel|Cep)", duz)
    if m_ad:
        sonuc["yurutucu_adi"] = re.sub(r"\s+", " ", m_ad.group(1)).strip()
    if not sonuc["yurutucu_adi"]:
        for w in sayfa0:
            if w["text"] == "SOYADI" and w["x0"] < 150:
                sag = sorted([v for v in sayfa0 if abs(v["top"] - w["top"]) < 10
                              and v["x0"] > w["x1"] + 15], key=lambda v: v["x0"])
                if sag:
                    sonuc["yurutucu_adi"] = " ".join(v["text"] for v in sag).strip()
                break

    # --- Kurum: 'Fakülte/Enstitü/YO/Merkez' etiketinin sağındaki metin ---
    for w in sayfa0:
        if w["text"] == "Merkez" and w["x0"] < 130:
            sag = sorted([v for v in sayfa0 if abs(v["top"] - w["top"]) < 14
                          and v["x0"] > w["x1"] + 15], key=lambda v: v["x0"])
            if sag:
                sonuc["yurutucu_kurum"] = " ".join(v["text"] for v in sag).strip()
            break

    # --- A.B.D.: 'Ana Bilim Dalı' etiketinin sağındaki metin ---
    for w in sayfa0:
        if w["text"] == "Dalı" and w["x0"] < 130:
            sag = sorted([v for v in sayfa0 if abs(v["top"] - w["top"]) < 14
                          and v["x0"] > w["x1"] + 15], key=lambda v: v["x0"])
            if sag:
                sonuc["yurutucu_abd"] = " ".join(v["text"] for v in sag).strip()
            break

    # --- Bütçe: 'BAPK Destek Miktarı' satırındaki para ---
    for w in sayfa0:
        if w["text"] == "Miktarı" and w["x0"] < 130 and 500 < w["top"] < 700:
            satir = [v for v in sayfa0 if abs(v["top"] - w["top"]) < 10]
            satir.sort(key=lambda v: v["x0"])
            metin = " ".join(v["text"] for v in satir)
            m = re.search(r"(\d{1,3}(?:\.\d{3})*,\d{2})", metin)
            if m:
                sonuc["butce_tl"] = m.group(1)
            break

    if not sonuc["yurutucu_kurum"]:
        m = re.search(r"Fakülte/Enstitü/YO/Merkez\s*([A-Za-zÇĞİÖŞÜçğıöşü 0-9./-]{5,80})", duz)
        if m:
            sonuc["yurutucu_kurum"] = re.sub(r"\s+", " ", m.group(1)).strip()
    if not sonuc["butce_tl"]:
        m = re.search(r"BAPK\s+Destek\s+Miktarı\s*([\d.,]+)\s*(TL)?", duz)
        if m:
            sonuc["butce_tl"] = m.group(1)
    if not sonuc["yurutucu_adi"]:
        m = re.search(r"Ünvanı, Adı SOYADI\s*(.*?)\s*(Bölümü|Fakülte)", duz)
        if m:
            sonuc["yurutucu_adi"] = re.sub(r"\s+", " ", m.group(1)).strip()

    return sonuc


# --------------------------------------------------------------------------
# Hakem değerlendirme formu çıkarımı
# --------------------------------------------------------------------------
def hakem_formu_oku(path: str, ilk_sayfa: int = 0, son_sayfa: Optional[int] = None) -> dict:
    duz = _duz_metin(path, ilk_sayfa, son_sayfa)

    # --- Proje adı (eşleştirme ve doğrulama için) ---
    proje_adi = ""
    m = re.search(r"Proje Adı\s*(.*?)\s*Proje Yürütücüsü", duz, re.S)
    if m:
        proje_adi = re.sub(r"\s+", " ", m.group(1)).strip()
        proje_adi = re.sub(r"\s+(Proje Yürütücüsü|Önerilen|TOPLAM|Hakem)", "", proje_adi).strip()
    # bazen değer satırı 'Proje Yürütücüsü ... Projenin Türü' arasında yalnız ad olur
    if not proje_adi:
        m = re.search(r"Proje Adı\s*(.{8,220}?)\s*(?:Önerilen|Projenin|Proje Yürütücüsü)", duz)
        if m:
            proje_adi = re.sub(r"\s+", " ", m.group(1)).strip()

    # --- Hakem adı: 'Ünvanı/Adı Soyadı' etiketi ---
    hakem_adi = ""
    m = re.search(r"Ünvanı/Adı Soyadı\s*([A-Za-zÇĞİÖŞÜçğıöşü\s./']+?)\s*(?:E-Posta|e-posta)", duz)
    if m:
        hakem_adi = re.sub(r"\s+", " ", m.group(1)).strip()
    if not hakem_adi:
        m = re.search(r"bilimsel hakemin\s*\n?\s*Ünvanı/Adı Soyadı\s*([^\n]+)", duz)
        if m:
            hakem_adi = m.group(1).strip()

    # --- Puan ---
    puan = None
    m = re.search(r"TOPLAM\s*PUAN:\s*(\d{1,3})", duz)
    if m:
        puan = int(m.group(1))

    # --- Karar: '( X )' işaretli seçenek ---
    karar_uzun = ""
    pass
    m = re.search(r"DEĞERLENDİRME SONUCUNUZ(.*?)(?:Projeyi tekrar|EK DOSYA|Ünvanı/Adı)", duz, re.S)
    if m:
        karar_uzun = _isaretli_satir(m.group(1))

    # --- Ek dosya ---
    ek_dosya = "dosya yüklenmiştir" in duz or "yüklenmiştir (indirmek" in duz

    # --- Adres alanı (kurum/üniversite çıkarımı için ham veri) ---
    adres = ""
    m = re.search(r"Adresi\s*(.{5,120}?)\s*(?:Tarih|İmza)", duz, re.S)
    if m:
        adres = re.sub(r"\s+", " ", m.group(1)).strip()

    # =====================================================================
    # KISA FORM DESTEĞİ (1 sayfalık "EVET/HAYIR/KISMEN" değerlendirmesi):
    # Uzun formda bulunamayan alanları bu biçimden doldurur.
    #   - başlık : "Projenin başlığı:"
    #   - karar  : "DEĞERLENDİRME SONUCU:" altındaki "( X )" işaretli seçenek
    #   - hakem  : "Hakem unvanı, adı ve soyadı:"
    #   - adres  : e-imza bloğundaki "Adres :" satırı (kurum çıkarımı için)
    # =====================================================================
    if not proje_adi:
        m = re.search(r"Projenin\s*başlığı\s*:\s*(.{5,300}?)\s*(?:Lütfen|EVET|DEĞERLENDİRME)",
                      duz, re.S)
        if m:
            proje_adi = re.sub(r"\s+", " ", m.group(1)).strip()

    if not karar_uzun:
        blok2 = ""
        m = re.search(r"DEĞERLENDİRME\s*SONUCU\s*:?\s*(.*?)(?:Hakem unvanı|İmza)", duz, re.S)
        if m:
            blok2 = m.group(1)
        else:
            blok2 = duz
        karar_uzun = _isaretli_satir(blok2)

    if not hakem_adi:
        m = re.search(r"Hakem\s*unvanı,\s*adı\s*ve\s*soyadı\s*:\s*([^\n]{3,120})", duz)
        if m:
            hakem_adi = re.sub(r"\s+", " ", m.group(1)).strip()

    if not adres:
        # e-imza bloğu: "Adres : ..." (NUL temizlenmiş halde bile harfler düşebilir)
        m = re.search(r"(?:^|\n)\s*Adres\s*:\s*([^\n]{3,120})", duz)
        if m:
            adres = re.sub(r"\s+", " ", m.group(1)).strip()

    return {
        "hakem_adi": hakem_adi,
        "puan": puan,
        "proje_adi": proje_adi,
        "karar_uzun": karar_uzun,
        "karar_kisa": kisa_karar(karar_uzun),
        "ek_dosya": ek_dosya,
        "adres": adres,
    }


# --------------------------------------------------------------------------
# Adresten kurum adı çıkarımı (yerel, kural tabanlı ilk katman)
# --------------------------------------------------------------------------
KURUM_KALIP = re.compile(
    r"([A-ZÇĞİÖŞÜ][A-ZÇĞİÖŞÜ0-9İ\s./'-]{3,120}?"
    r"(?:ÜNİVERSİTESİ|HASTANESİ|FAKÜLTESİ|ENSTİTÜSÜ|MERKEZİ)"
    r"(?:-[A-ZÇĞİÖŞÜ0-9İ]+)*)")


def adresten_kurum(adres: str) -> str:
    """'MERAM TIP FAKÜLTESİ / NECMETTİN ERBAKAN ÜNİVERSİTESİ' gibi adres
    alanlarından büyük harfli kurum adını ayıklamaya çalışır."""
    if not adres:
        return ""
    ust = adres.upper()
    bolumler = [b.strip() for b in re.split(r"[/,;|]", ust)]
    kurumlar = []
    for b in bolumler:
        m = KURUM_KALIP.search(b)
        if m:
            kurumlar.append(m.group(1).strip())
    for k in kurumlar:
        if "ÜNİVERSİTESİ" in k:
            return k
    return kurumlar[0] if kurumlar else ""

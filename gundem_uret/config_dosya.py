# -*- coding: utf-8 -*-
"""
Excel yapılandırma dosyası: şablon üretimi ve okuma.

Şablon 5 sayfadan oluşur:
  Toplantı      : toplantı tarihi/sayısı, bölüm başlıkları (anahtar/değer)
  Maddeler      : 1. bölüm maddeleri -> PDF klasörü + (Tekrar Gündem) + raportör
  Düzeltmeler   : PDF'ten çıkan herhangi bir alanı elle ezin (üstünlük: Excel)
  Hakemler      : hakem kurumu ve A.B.D.'si (PDF'te yoksa; yerel belge havuzundan/eski gündemden ya da el ile)
  KararMaddeleri: 2. bölüm (iptal / ek süre / tür değişikliği / ek malzeme)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from .model import KararMaddesi, ToplantiBilgisi

BASLIK_RENGI = PatternFill("solid", fgColor="D9E2F3")
ONEMLI_RENGI = PatternFill("solid", fgColor="FFF2CC")
UYARI_RENGI = PatternFill("solid", fgColor="FCE4EC")


def _sayfa_yaz(ws, basliklar: List[str], satirlar: List[List], not_metni: str = ""):
    ws.append(basliklar)
    for hucre in ws[1]:
        hucre.font = Font(bold=True, color="1F3864")
        hucre.fill = BASLIK_RENGI
        hucre.alignment = Alignment(vertical="center", wrap_text=True)
    for satir in satirlar:
        ws.append(satir)
    if not_metni:
        ws.append([not_metni] + [""] * (len(basliklar) - 1))
        for hucre in ws[ws.max_row]:
            hucre.font = Font(italic=True, color="808080")
    # genişlikler
    for i in range(1, len(basliklar) + 1):
        ws.column_dimensions[get_column_letter(i)].width = 22
    ws.freeze_panes = "A2"


@dataclass
class Yapilandirma:
    toplanti: ToplantiBilgisi = field(default_factory=ToplantiBilgisi)
    madde_kayitlari: list = field(default_factory=list)      # (klasör, tekrar, raportör)
    duzeltmeler: Dict[str, Dict[str, str]] = field(default_factory=dict)
    hakemler: Dict[str, list] = field(default_factory=dict)  # klasör -> [satır sözlükleri]
    kararlar: List[KararMaddesi] = field(default_factory=list)
    uyarilar: list = field(default_factory=list)


# --------------------------------------------------------------------------
# Şablon
# --------------------------------------------------------------------------
def sablon_olustur(yol: str, ornek: bool = True) -> str:
    """Boş (ornek=False) ya da demo verili (ornek=True) yapılandırma xlsx'i üretir."""
    wb = Workbook()

    # ---------- Toplantı ----------
    ws = wb.active
    ws.title = "Toplantı"
    satirlar = [
        ["toplanti_tarihi", "19/08/2026", "Gündem başlığında görünecek tarih (örn. 19/08/2026)"],
        ["toplanti_sayisi", "2026/09", "Toplantı sayısı (örn. 2026/09)"],
        ["alt_bolum_basligi", "KARAR MADDELERİ", "2. bölümden önce basılacak başlık; boş = başlık yok"],
        ["karar_alt_satir", "KOMİSYON", "Karar maddeleri altındaki satır metni"],
        ["kurum_ust", "T.C.", "Üst blok 1. satır (genelde değişmez)"],
        ["kurum_adi", "SAĞLIK BİLİMLERİ ÜNİVERSİTESİ", "Üst blok 2. satır"],
        ["kurum_alt", "Bilimsel Araştırma Projeleri Koordinatörlüğü", "Üst blok 3. satır"],
    ]
    _sayfa_yaz(ws, ["Alan", "Değer", "Açıklama"], satirlar)

    # ---------- Maddeler ----------
    ws = wb.create_sheet("Maddeler")
    satirlar = []
    if ornek:
        satirlar.append([
            1, "01_cem_atabey", "E", "Prof. Dr. Kerim Bora YILMAZ",
            "Klasör içinde proje formu + hakem formları olmalı; türü içerikten tanınır"])
    _sayfa_yaz(ws, ["Sıra", "Klasör", "Tekrar Gündem (E/H)", "Raportör", "Açıklama"],
               satirlar,
               "NOT: 'Klasör' sütunu --girdi köküne göre yazılır; PDF türleri içerikten otomatik tanınır.")

    # ---------- Düzeltmeler ----------
    ws = wb.create_sheet("Düzeltmeler")
    satirlar = []
    if ornek:
        satirlar.append([
            "01_cem_atabey", "yurutucu_abd", "Beyin ve Sinir A.B.D.",
            "F-1'deki 'Ana Bilim Dalı' alanı yerine örnek gündemdeki gösterim"])
    _sayfa_yaz(ws, ["Klasör", "Alan", "Değer", "Kaynak / Açıklama"], satirlar,
               "NOT: Alan sütunu şunlardan biri olabilir: proje_turu, proje_adi, sure_ay, "
               "yurutucu_adi, yurutucu_kurum, yurutucu_abd, butce_tl. "
               "Buraya yazılan değer PDF'ten çıkanı ezer.")

    # ---------- Hakemler ----------
    ws = wb.create_sheet("Hakemler")
    satirlar = []
    if ornek:
        satirlar += [
            ["01_cem_atabey", "Doç. Dr. Osman TANRIVERDİ",
             "Başakşehir Çam ve Sakura Şehir Hastanesi, SUAM", "Beyin ve Sinir A.B.D.",
             "Web: SBÜ personel CV (tip.sbu.edu.tr) + dergi danışma kurulu"],
            ["01_cem_atabey", "Prof. Dr. Cihan İŞLER",
             "İstanbul Üniversitesi-Cerrahpaşa", "Beyin ve Sinir A.B.D.",
             "Web: AVESIS profili (avesis.iuc.edu.tr/cihan.isler)"],
            ["01_cem_atabey", "Prof. Dr. Ahmet ÖNDER GÜNEY",
             "Necmettin Erbakan Üniversitesi", "Beyin ve Sinir A.B.D.",
             "Web: NEÜ Cerrahi Tıp Bilimleri / BSC A.B.D. sayfası"],
        ]
    _sayfa_yaz(ws, ["Klasör", "Hakem", "Kurum", "A.B.D.", "Kaynak (URL / not)"], satirlar,
               "NOT: 'Hakem' PDF'ten okunan adla eşleşir. Kurum/A.B.D. BOŞ bırakılırsa sistem "
               "önce form adresinden, sonra girdi klasöründeki eski gündem PDF'lerinden bulur "
               "(bulunamayan kuruma 'Buraya Hakem Kurumu Yaz' yazılır). Elle yazılan değer "
               "kazanır; kaynak sütununa not/URL koyabilirsiniz.")

    # ---------- Karar Maddeleri ----------
    ws = wb.create_sheet("KararMaddeleri")
    satirlar = []
    if ornek:
        satirlar += [
            [1, "2025/073", "Tıpta Uzmanlık Projesi",
             "Talasemi Hastalarında, Demir Birikiminin Ekzokrin Pankreas Fonksiyonları Üzerine Etkisi",
             "12 AY", "Doç. Dr. Aysel ÜNLÜSOY AKSU",
             "Gülhane Tıp Fakültesi / Çocuk Sağlığı ve Hastalıkları A.B.D.",
             "49.489,90", "", "PROJENİN İPTALİ"],
            [2, "2025/072", "Yüksek Lisans Tez Projesi",
             "Akut İskemik İnmeli Olgularda Asimetrik Dimetilarjinin Düzeylerinin İnme Alt Tipleri İle İlişkisi",
             "12 AY", "Prof. Dr. Macit KOLDAŞ",
             "Hamidiye Tıp Fakültesi / Tıbbi Biyokimya A.B.D.",
             "41.333,82", "35.148,00",
             "PROJE TÜRÜ DEĞİŞTİRME TALEBİ -> BİLİMSEL ARAŞTIRMA PROJELERİ"],
            [3, "2025/072", "Yüksek Lisans Tez Projesi",
             "Akut İskemik İnmeli Olgularda Asimetrik Dimetilarjinin Düzeylerinin İnme Alt Tipleri İle İlişkisi",
             "12 AY", "Prof. Dr. Macit KOLDAŞ",
             "Hamidiye Tıp Fakültesi / Tıbbi Biyokimya A.B.D.",
             "41.333,82", "35.148,00", "EK SÜRE (3 AY) TALEBİ"],
        ]
    _sayfa_yaz(ws, ["Sıra", "Proje No", "Proje Türü", "Proje Adı", "Süre",
                    "Yürütücü", "Birim", "Önerilen Tutar (TL)", "Harcanan (TL)",
                    "İşlem Metni"], satirlar,
               "NOT: Tutarlar sayısal ya da '1.234,56' biçiminde yazılabilir; işlem metni "
               "(ör. PROJENİN İPTALİ) maddenin altında ortalanır.")

    wb.save(yol)
    return yol


# --------------------------------------------------------------------------
# Okuma
# --------------------------------------------------------------------------
def _hucre(d) -> str:
    """openpyxl hücresini metne çevirir; None -> ''."""
    if d is None:
        return ""
    if isinstance(d, float) and d.is_integer():
        return str(int(d))
    return str(d).strip()


def yapilandirma_oku(yol: str) -> Yapilandirma:
    wb = load_workbook(yol, data_only=True)
    yap = Yapilandirma()

    def sayfa(ad):
        return wb[ad] if ad in wb.sheetnames else None

    # --- Toplantı ---
    # Excel'deki anahtar adları ile model alan adları arasındaki eşleme
    ALAN_ESLE = {"toplanti_tarihi": "tarih", "toplanti_sayisi": "sayi",
                 "alt_bolum_basligi": "alt_bolum_basligi",
                 "karar_alt_satir": "karar_alt_satir",
                 "kurum_ust": "kurum_ust", "kurum_adi": "kurum_adi",
                 "kurum_alt": "kurum_alt", "raportor_atamasi": "raportor_atamasi"}
    ws = sayfa("Toplantı")
    if ws:
        eslesen = {}
        for satir in ws.iter_rows(min_row=2, values_only=True):
            if satir[0] and str(satir[0]).strip().upper() != "NOT":
                eslesen[str(satir[0]).strip()] = satir[1] if len(satir) > 1 else ""
        t = ToplantiBilgisi()
        for anahtar, deger in eslesen.items():
            alan = ALAN_ESLE.get(anahtar)
            if alan and hasattr(t, alan):
                setattr(t, alan, _hucre(deger))
        yap.toplanti = t

    # --- Maddeler ---
    ws = sayfa("Maddeler")
    if ws:
        for satir in ws.iter_rows(min_row=2, values_only=True):
            if satir and satir[1] and str(satir[1]).strip():
                try:
                    sira = int(float(_hucre(satir[0]))) if satir[0] is not None else 0
                except (ValueError, TypeError):
                    sira = 0
                yap.madde_kayitlari.append({
                    "sira": sira,
                    "klasor": _hucre(satir[1]),
                    "tekrar": _hucre(satir[2]).upper() in ("E", "EVET", "1", "TRUE"),
                    "raportor": _hucre(satir[3]) if len(satir) > 3 else "",
                })

    # --- Düzeltmeler ---
    ws = sayfa("Düzeltmeler")
    if ws:
        for satir in ws.iter_rows(min_row=2, values_only=True):
            if satir and satir[0] and satir[1]:
                yap.duzeltmeler.setdefault(_hucre(satir[0]), {})[_hucre(satir[1])] = _hucre(satir[2])

    # --- Hakemler ---
    ws = sayfa("Hakemler")
    if ws:
        for satir in ws.iter_rows(min_row=2, values_only=True):
            if not satir or not satir[0]:
                continue
            if str(satir[0]).strip().upper().startswith("NOT"):
                continue
            yap.hakemler.setdefault(_hucre(satir[0]), []).append({
                    "hakem": _hucre(satir[1]) if len(satir) > 1 else "",
                    "kurum": _hucre(satir[2]) if len(satir) > 2 else "",
                    "abd": _hucre(satir[3]) if len(satir) > 3 else "",
                    "kaynak": _hucre(satir[4]) if len(satir) > 4 else "",
                })

    # --- Karar maddeleri ---
    ws = sayfa("KararMaddeleri")
    if ws:
        for satir in ws.iter_rows(min_row=2, values_only=True):
            if not satir or not (satir[1] or satir[3] or satir[9]):
                continue
            try:
                sira_no = int(float(_hucre(satir[0]))) if satir[0] is not None else 0
            except (ValueError, TypeError):
                sira_no = 0
            km = KararMaddesi(
                sira=sira_no,
                proje_no=_hucre(satir[1]),
                proje_turu=_hucre(satir[2]),
                proje_adi=_hucre(satir[3]),
                sure_ay=_hucre(satir[4]),
                yurutucu_adi=_hucre(satir[5]),
                birim=_hucre(satir[6]),
                butce_tl=_hucre(satir[7]),
                harcanan_tl=_hucre(satir[8]),
                islem=_hucre(satir[9]),
            )
            # "1.234,56" biçimini düzelt (openpyxl sayıya çevirmiş olabilir)
            for alan in ("butce_tl", "harcanan_tl"):
                deger = getattr(km, alan)
                if deger:
                    try:
                        sayi = float(deger.replace(".", "").replace(",", "."))
                        setattr(km, alan, f"{sayi:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
                    except Exception:
                        pass
            yap.kararlar.append(km)

    if not yap.toplanti.tarih:
        yap.uyarilar.append("Toplantı sayfasında 'toplanti_tarihi' dolu değil.")
    return yap

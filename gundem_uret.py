# -*- coding: utf-8 -*-
"""
BAP Gündem Üretim Aracı - komut satırı girişi + üretim çekirdeği.

OTOMATİK TARAMA (varsayılan):
  Toplantı klasöründe PDF'ler nasıl dizilmiş olursa olsun çalışır:

  A) Klasör içinde alt klasörler varsa -> her alt klasör bir talep sayılır.
  B) PDF'ler düz duruyorsa (t1.pdf, t2.pdf, ...) -> dosyalar sıralanır;
     her proje formu yeni bir talep başlatır, ardından gelen hakem formları
     o talebe bağlanır. Proje adları çapraz doğrulanır (hakem formundaki
     proje adı, talep projesiyle uyuşmazsa uyarı yazılır).
  C) Tek PDF içinde birden çok form varsa (proje + hakemler üst üste)
     sayfalar türlerine göre otomatik bölünür.

  Excel 'Maddeler' satırları OPSİYONELDİR: sadece "(Tekrar Gündem)" ve
  raportör atamak için kullanılır (Klasör = alt klasör adı ya da 'kok').

Kullanım:
  python gundem_uret.py --sablon config/2026-09.xlsx          # şablon üret (demo)
  python gundem_uret.py --girdi girdi/19.08.2026 --config config/19.08.2026.xlsx
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from typing import Dict, List, Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from gundem_uret import pdf_ayikla
from gundem_uret.config_dosya import sablon_olustur, yapilandirma_oku
from gundem_uret.docx_uret import olustur
from gundem_uret.model import (GundemMaddesi, HakemGorusu, KararMaddesi,
                               ToplantiBilgisi, UretimRaporu)
from gundem_uret.zenginlestir import (abd_gecerli_mi, hakem_zenginlestir,
                                      yurutucu_abd_bul)

ALAN_ADLARI = {"proje_turu", "proje_adi", "sure_ay", "yurutucu_adi",
               "yurutucu_kurum", "yurutucu_abd", "butce_tl"}


def _temiz(metin: str) -> str:
    return re.sub(r"\s+", " ", (metin or "")).strip()


def _normalize(metin: str) -> str:
    return _temiz(metin or "").lower().replace(".", "").replace(",", "")


# ---------------------------------------------------------------------------
# Otomatik tarama
# ---------------------------------------------------------------------------
def _dogal_anahtar(isim: str):
    """Sayısal sıralama anahtarı: '10_xyz' < '2_abc' DEĞİL; 2 < 10 olur.

    '1_ilk', '2_ikinci', '10_onuncu' -> 1, 2, 10 sırası (insan sıralaması).
    """
    parcalar = re.split(r"(\d+)", isim.lower())
    return [(0, int(p)) if p.isdigit() else (1, p) for p in parcalar if p]


def _pdf_dosyalari(girdi_kok: str) -> List[str]:
    """Toplantı klasörü altındaki tüm PDF'leri toplar (doğal sıralı)."""
    sonuc = []
    for dizin, alt, dosyalar in os.walk(girdi_kok):
        alt[:] = [a for a in alt if not a.startswith(".")]
        for f in dosyalar:
            if f.lower().endswith(".pdf"):
                sonuc.append(os.path.join(dizin, f))
    return sorted(sonuc, key=lambda yol: _dogal_anahtar(os.path.relpath(yol, girdi_kok)))


def _yerel_pdf_havuzu(girdi_kok: str) -> Dict[str, str]:
    """Eldeki PDF'lerin düz metinlerini toplar (kurum/A.B.D. çıkarımı için).

    Kapsam:
      - hedef toplantı klasöründeki tüm PDF'ler,
      - bir üst klasörde (girdi/) adında 'Gündem' geçen PDF'ler
        (önceki toplantı gündemleri -> hakem/yürütücü bilgi kaynağı).
    Metinler satır sonları boşluk yapılmış hâlde tutulur.
    """
    import re as _re
    havuz: Dict[str, str] = {}
    pdf_listesi = _pdf_dosyalari(girdi_kok)
    ust = os.path.dirname(os.path.abspath(girdi_kok))
    for yol in _pdf_dosyalari(ust):
        mutlak = os.path.abspath(yol)
        if mutlak.startswith(os.path.abspath(girdi_kok) + os.sep):
            continue  # hedef klasördekiler zaten listede
        if _re.search(r"g[uü]ndem", os.path.basename(yol), _re.I):
            pdf_listesi.append(yol)
    for yol in pdf_listesi:
        try:
            metin = pdf_ayikla._duz_metin(yol)
        except Exception:
            continue
        if metin:
            havuz[os.path.basename(yol)] = _re.sub(r"\s+", " ", metin)
    return havuz


def _kapsayici_haritasi(girdi_kok: str) -> Dict[str, List[str]]:
    """PDF'leri üst klasöre göre gruplar.

    Dönen: { 'kok': [doğrudan toplantı klasöründeki PDF'ler],
             'alt_klasor_adi': [o alt klasördeki PDF'ler], ... }
    """
    kok = os.path.abspath(girdi_kok)
    harita: Dict[str, List[str]] = {}
    for yol in _pdf_dosyalari(kok):
        goreli = os.path.relpath(yol, kok)
        parcacik = goreli.split(os.sep)
        anahtar = "kok" if len(parcacik) == 1 else parcacik[0]
        harita.setdefault(anahtar, []).append(yol)
    for k in harita:
        harita[k].sort()
    return harita


def _dosyadaki_dokumanlar(yol: str) -> List[dict]:
    """Bir PDF'teki proje/hakem formlarını (sayfa aralıklarıyla) döndürür."""
    bolumler = pdf_ayikla.belge_bol(yol)
    return [{"yol": yol, "tip": tip, "ilk": ilk, "son": son}
            for tip, ilk, son in bolumler]


def _duz_proje_adi(metin: str) -> str:
    return _normalize(metin)


def _hizli_proje_adi(yol: str, ilk: int = 0, son: int = 0) -> str:
    """Eşleştirme için proje adını hafifçe çıkarır.

    F-1 düzeni: '1.1. Proje Başlığı   [Tarih:...]' satırından sonraki
    1-3 satır proje adıdır ve '1.3.' etiketiyle biter.
    """
    import re as _re
    from pypdf import PdfReader
    try:
        oku = PdfReader(yol)
        t = "\n".join((p.extract_text() or "").replace("\x00", "")
                       for p in oku.pages[ilk:son + 1])
        m = _re.search(r"Proje Başlığı(.*?)(?:1\.3\.|Projenin Türü)", t, _re.S)
        if not m:
            return ""
        parca = m.group(1)
        satirlar = [ln.strip() for ln in parca.splitlines()
                    if ln.strip() and not _re.match(r"^\s*(Tarih|1\.\d|$)", ln.strip())]
        return _temiz(" ".join(satirlar[:4]))
    except Exception:
        return ""


def _eslesme_puani(a: str, b: str) -> float:
    """İki proje adı metninin benzerliği (0-1). Küçük parçaları atlar."""
    import re as _re
    def kokler(metin):
        metin = _re.sub(r"[^0-9a-zçğıöşü ]", " ", _duz_proje_adi(metin))
        sozler = [s for s in metin.split() if len(s) > 2]
        return set(sozler[:24])
    A, B = kokler(a), kokler(b)
    if not A or not B:
        return 0.0
    kesisim = A & B
    return 2 * len(kesisim) / (len(A) + len(B))


def maddeleri_isle(girdi_kok: str, yap, rapor: UretimRaporu) -> List[GundemMaddesi]:
    """1. bölüm maddelerini toplantı klasörünü tarayarak kurar."""
    maddeler: List[GundemMaddesi] = []

    satir_by_label = {k.get("klasor", ""): k for k in yap.madde_kayitlari}

    # satırların sırasını koruyarak isim->sıra sözlüğü
    sira_by_label: Dict[str, int] = {}
    for i, k in enumerate(yap.madde_kayitlari):
        lbl = k.get("klasor", "")
        if lbl and lbl not in sira_by_label:
            sira_by_label[lbl] = k.get("sira") or (i + 1)

    harita = _kapsayici_haritasi(girdi_kok)
    if not harita:
        rapor.uyari(f"{girdi_kok} altında PDF bulunamadı.")
        return maddeler

    # kurum/A.B.D. için ELDEKİ belge havuzu (eski gündemler + formlar)
    yerel_belgeler = _yerel_pdf_havuzu(girdi_kok)

    # kapsayıcı sıralaması:
    #   1. Excel 'Maddeler' sayfasında satırı olanlar, 'Sıra' sütununa göre,
    #   2. geri kalanlar DOĞAL (sayısal) sırayla: 1, 2, 3, ..., 10, ...
    #      (alfabetik değil! '10_x' ile '2_y' karışmasın diye)
    def kapsayici_anahtar(isim: str):
        if isim in sira_by_label:
            return (0, sira_by_label[isim])
        return (1, _dogal_anahtar(isim))

    kapsayicilar = sorted(harita, key=kapsayici_anahtar)
    rapor.bilgi("Klasör sıralaması: " + " → ".join(str(k) for k in kapsayicilar))

    rapor.bilgi(f"Tarama: {len(kapsayicilar)} grup bulundu "
                f"({', '.join(kapsayicilar[:8])}{'…' if len(kapsayicilar) > 8 else ''}).")

    for kapsayici in kapsayicilar:
        dosyalar = harita[kapsayici]

        # kapsayıcı içindeki tüm formları topla
        dokumanlar = []
        for yol in dosyalar:
            try:
                dokumanlar.extend(_dosyadaki_dokumanlar(yol))
            except Exception:
                rapor.uyari(f"{os.path.basename(yol)} okunamadı (bozuk PDF olabilir).")
        if not dokumanlar:
            continue
        dokumanlar.sort(key=lambda d: (d["yol"].lower(), d["ilk"]))

        projeler = [d for d in dokumanlar if d["tip"] == "proje"]
        hakemler = [d for d in dokumanlar if d["tip"] == "hakem"]

        # DOSYA SIRASINDAN BAĞIMSIZ EŞLEŞTİRME:
        # her hakem formunun içindeki proje adı, proje formununkiyle eşleştirilir.
        proje_adi_cache = {}
        for p in projeler:
            proje_adi_cache[id(p)] = _hizli_proje_adi(p["yol"], p["ilk"], p["son"])

        gruplar = [{"proje": p, "hakemler": []} for p in projeler]
        atanmayan = []
        for h in hakemler:
            h_ad = pdf_ayikla.hakem_formu_oku(h["yol"], h["ilk"], h["son"]).get("proje_adi", "")
            en_iyi, en_puan = None, 0.25
            for p in projeler:
                puan = _eslesme_puani(h_ad, proje_adi_cache[id(p)])
                if puan > en_puan:
                    en_iyi, en_puan = p, puan
            if en_iyi is not None:
                for g in gruplar:
                    if g["proje"] is en_iyi:
                        g["hakemler"].append(h)
                        break
                if h_ad:
                    rapor.bilgi(f"Eşleşti: {os.path.basename(h['yol'])} -> "
                                f"{os.path.basename(en_iyi['yol'])} "
                                f"(benzerlik %{en_puan * 100:.0f})")
            else:
                atanmayan.append(h)

        # eşleşmeyen hakemler: tek proje varsa ona; yoksa ayrı grup
        for h in atanmayan:
            h_ad = pdf_ayikla.hakem_formu_oku(h["yol"], h["ilk"], h["son"]).get("proje_adi", "")
            if len(projeler) == 1:
                gruplar[0]["hakemler"].append(h)
                rapor.uyari(f"{os.path.basename(h['yol'])} adıyla eşleşen proje bulunamadı; "
                            f"tek proje olduğundan ona bağlandı.")
            elif not projeler:
                rapor.uyari(f"{os.path.basename(h['yol'])} için hiç proje formu yok.")
                gruplar.append({"proje": None, "hakemler": [h]})
            else:
                rapor.uyari(f"{os.path.basename(h['yol'])} ({h_ad[:40]}…) hangi projeye ait "
                            f"olduğu belirlenemedi; hiçbir talebe bağlanmadı. Excel 'Hakemler' "
                            f"sayfasından veya dosya adlandırmasıyla netleştirin.")

        tek_grup = len(gruplar) == 1
        for i, grp in enumerate(gruplar):
            etiket = kapsayici if tek_grup else f"{kapsayici}#{i + 1}"
            # Excel satırları (tekrar/raportör/düzeltme/hakem bilgisi) önce
            # gruba özel etiketle ('kok#2' gibi), tek grup varsa kapsayıcı
            # adıyla ('kok' gibi) eşleşir.
            satir = satir_by_label.get(etiket) or (
                satir_by_label.get(kapsayici) if tek_grup else None)
            duzeltmeler = yap.duzeltmeler.get(etiket) or (
                yap.duzeltmeler.get(kapsayici, {}) if tek_grup else {})
            hakem_satirlari = yap.hakemler.get(etiket) or (
                yap.hakemler.get(kapsayici, []) if tek_grup else [])
            madde = _madde_isle(etiket, grp, kapsayici, satir, duzeltmeler,
                                hakem_satirlari, rapor, yerel_belgeler)
            if madde is not None:
                maddeler.append(madde)

    # sonuç: gündemdeki sıra ile kaynak klasör eşlemesi (rapora)
    for idx, m in enumerate(maddeler, start=1):
        rapor.bilgi(f"Sıra {idx}  <--  '{m.klasor}'  "
                    f"({m.proje_adi[:45]}…)")

    return maddeler


def _madde_isle(etiket: str, grp: dict, kapsayici: str, satir: Optional[dict],
                duzeltmeler: dict, hakem_satirlari: list,
                rapor: UretimRaporu,
                yerel_belgeler: Optional[Dict[str, str]] = None
                ) -> Optional[GundemMaddesi]:
    """Bir talep grubunu (1 proje + N hakem) GundemMaddesi'ne çevirir."""
    madde = GundemMaddesi(klasor=etiket)
    if satir:
        madde.tekrar_gundem = bool(satir.get("tekrar"))
        madde.raportor = _temiz(satir.get("raportor", ""))

    proje_d = grp.get("proje")
    hakem_docs = grp.get("hakemler", [])

    if proje_d is None:
        rapor.uyari(f"{etiket}: proje formu bulunamadı; yalnızca {len(hakem_docs)} "
                    f"hakem dosyası var. Madde yine de eklendi (bilgiler eksik olabilir).")

    # ---------------- proje formu ----------------
    proje_veri = {}
    if proje_d:
        proje_veri = pdf_ayikla.proje_formu_oku(proje_d["yol"], proje_d["ilk"], proje_d["son"])
        for alan in ("proje_turu", "proje_adi", "sure_ay", "yurutucu_adi",
                     "yurutucu_kurum", "yurutucu_abd", "butce_tl"):
            setattr(madde, alan, _temiz(proje_veri.get(alan, "")))
        sayi_sure = re.search(r"(\d{1,3})", madde.sure_ay or "")
        if sayi_sure:
            madde.sure_ay = f"{sayi_sure.group(1)} AY"

    # Excel düzeltmeleri (proje PDF'ten çıkanı ezer)
    for alan, deger in (duzeltmeler or {}).items():
        if alan not in ALAN_ADLARI:
            rapor.uyari(f"{etiket}: bilinmeyen düzeltme alanı '{alan}'.")
            continue
        setattr(madde, alan, _temiz(deger))
        rapor.bilgi(f"{etiket} .{alan}: Excel'den düzeltildi -> '{deger}'")

    # --- Yürütücü A.B.D.: PDF'te gerçek A.B.D. yoksa/generikse ELDEKİ
    # belgelerden bul (eski gündem PDF'leri vb.; internet yok).
    # (Excel 'Düzeltmeler'den girilen değer her zaman kazanır ve aramayı atlar.)
    if not abd_gecerli_mi(madde.yurutucu_abd):
        onceki = madde.yurutucu_abd or "(boş)"
        havuz = None
        if yerel_belgeler:
            kendi = os.path.basename(proje_d["yol"]) if proje_d else None
            havuz = {k: v for k, v in yerel_belgeler.items() if k != kendi}
        bul = yurutucu_abd_bul(madde.yurutucu_adi, havuz)
        if bul.get("abd"):
            madde.yurutucu_abd = bul["abd"]
            rapor.ok(f"{etiket}: yürütücü A.B.D. bulundu "
                     f"('{onceki}' -> {madde.yurutucu_abd}; "
                     f"{bul.get('kaynak', '')[:70]})")
        else:
            rapor.uyari(f"{etiket}: yürütücü A.B.D. '{onceki}' gündem için "
                        f"yetersiz ve eldeki belgelerde bulunamadı "
                        f"('{madde.yurutucu_adi}'). Excel 'Düzeltmeler' "
                        f"sayfasına yurutucu_abd yazın ya da girdi köküne "
                        f"eski gündem PDF'i koyun.")

    # ---------------- hakemler ----------------
    for h in hakem_docs:
        veri = pdf_ayikla.hakem_formu_oku(h["yol"], h["ilk"], h["son"])
        hakem = HakemGorusu(
            hakem_adi=_temiz(veri.get("hakem_adi", "")),
            karar_kisa=veri.get("karar_kisa", ""),
            puan=veri.get("puan"),
            ek_dosya=veri.get("ek_dosya", False),
        )
        ad_norm = _normalize(hakem.hakem_adi)

        # Excel onay satırını ad ile eşle (klasör = kapsayıcı adı)
        onay = None
        for a in hakem_satirlari:
            if a.get("hakem") and _normalize(a["hakem"]) == ad_norm:
                onay = a
                break
        if onay is None and len(hakem_satirlari) == 1 \
                and not hakem_satirlari[0].get("hakem"):
            onay = hakem_satirlari[0]

        havuz = None
        if yerel_belgeler:
            kendi = os.path.basename(h["yol"])
            havuz = {k: v for k, v in yerel_belgeler.items() if k != kendi}
        zengin = hakem_zenginlestir(hakem, veri, onay,
                                    yerel_belgeler=havuz)
        hakem.kurum = _temiz(zengin.get("kurum", ""))
        hakem.abd = _temiz(zengin.get("abd", ""))
        hakem.kaynak = _temiz(zengin.get("kaynak", ""))

        # proje adı çapraz doğrulama
        if proje_d and veri.get("proje_adi"):
            h_proje = _duz_proje_adi(veri["proje_adi"])
            m_proje = _duz_proje_adi(madde.proje_adi)
            anahtar_h = h_proje[:40]
            anahtar_m = m_proje[:40]
            if anahtar_h and anahtar_m and anahtar_h not in m_proje \
                    and anahtar_m not in h_proje:
                rapor.uyari(f"{etiket}: {os.path.basename(h['yol'])} içindeki proje adı "
                            f"('{veri['proje_adi'][:50]}…') bu talebin projesiyle "
                            f"uyuşmuyor ('{madde.proje_adi[:50]}…'). Dosya yanlış "
                            f"klasöre/gruba karışmış olabilir.")

        # Kural: A.B.D. hiçbir kaynaktan gelmediyse yürütücünün A.B.D.'si geçer
        if not hakem.abd and abd_gecerli_mi(madde.yurutucu_abd):
            hakem.abd = madde.yurutucu_abd
            hakem.kaynak = (hakem.kaynak + " | " if hakem.kaynak else "") \
                + "yürütücü A.B.D. (kural)"
            rapor.ok(f"{etiket}: {hakem.hakem_adi} - A.B.D. bulunamadı; "
                     f"yürütücünün A.B.D.'si kullanıldı: {hakem.abd}")
        elif not hakem.abd:
            rapor.uyari(f"{etiket}: {hakem.hakem_adi} - A.B.D. bulunamadı "
                        f"(yürütücünün A.B.D.'si de geçerli değil); boş "
                        f"bırakıldı.")
        # Kural: kurum eldeki kaynaklarda yoksa yer tutucu yazılır
        if not hakem.kurum:
            hakem.kurum = "Buraya Hakem Kurumu Yaz"
            hakem.kaynak = (hakem.kaynak + " | " if hakem.kaynak else "") \
                + "YER TUTUCU (elle doldurulmalı)"
            rapor.uyari(f"{etiket}: {hakem.hakem_adi} - kurumu eldeki "
                        f"belgelerde bulunamadı; '{hakem.kurum}' yer tutucusu "
                        f"yazıldı. Excel 'Hakemler' sayfasına kurum "
                        f"girilebilir.")

        if not hakem.karar_kisa:
            rapor.uyari(f"{etiket}: {hakem.hakem_adi} - karar işareti PDF'ten "
                        f"okunamadı (config 'Hakemler' sayfasından netleştirin).")
        rapor.bilgi(f"Hakem: {hakem.hakem_adi} | karar={hakem.karar_kisa or '?'} "
                    f"puan={hakem.puan} | kurum='{hakem.kurum}' abd='{hakem.abd}' "
                    f"| kaynak: {hakem.kaynak[:80]}")
        madde.hakemler.append(hakem)

    if not proje_d:
        rapor.uyari(f"{etiket}: proje bilgisi boş olduğundan madde atlandı.")
        return None
    if not madde.hakemler:
        rapor.uyari(f"{etiket}: hakem formu bulunamadı (yalnızca proje formu).")
    rapor.ok(f"Talep: {madde.proje_adi[:55]}… ({madde.proje_turu}, {madde.sure_ay}, "
             f"{madde.yurutucu_adi}) — {len(madde.hakemler)} hakem.")
    return madde


def karsilastirmali_kontrol(maddeler: List[GundemMaddesi], rapor: UretimRaporu) -> None:
    for madde in maddeler:
        if not madde.yurutucu_abd:
            rapor.uyari(f"{madde.klasor}: yürütücü A.B.D. boş; "
                        f"Excel 'Düzeltmeler'den girin.")


def uretim_yap(girdi_kok: str, config_yolu: str,
               cikti_yolu: str = "", logo_yolu: str = "",
               rapor_yolu: str = "", dinleyici=None):
    """Üretim çekirdeği: CLI ve GUI tarafından ortak kullanılır.

    Dönen: (cikti_yolu, rapor_yolu, UretimRaporu)
    """
    rapor = UretimRaporu()
    if dinleyici:
        rapor.dinle(dinleyici)
    yap = yapilandirma_oku(config_yolu)
    for u in yap.uyarilar:
        rapor.uyari(u)
    t: ToplantiBilgisi = yap.toplanti

    # ---------- maddeler ----------
    maddeler = maddeleri_isle(girdi_kok, yap, rapor)
    karsilastirmali_kontrol(maddeler, rapor)

    # ---------- çıktı yolları ----------
    sayi_temiz = re.sub(r"[^0-9A-Za-zÇĞİÖŞÜçğıöşü-]+", "-", t.sayi or "gundem").strip("-")
    if not cikti_yolu:
        cikti_yolu = os.path.join(os.path.dirname(config_yolu), "..", "cikti",
                                  f"Gündem {sayi_temiz}.docx")
    cikti_yolu = os.path.abspath(cikti_yolu)
    rapor_yolu = os.path.abspath(rapor_yolu or os.path.join(
        os.path.dirname(cikti_yolu), f"uretim_raporu_{sayi_temiz}.md"))

    # ---------- docx ----------
    olustur(t, maddeler, yap.kararlar, cikti_yolu,
            logo_yolu=logo_yolu if logo_yolu and os.path.exists(logo_yolu) else None)
    if logo_yolu and not os.path.exists(logo_yolu):
        rapor.uyari(f"Logo bulunamadı ({logo_yolu}); üst blok logosuz üretildi.")

    # ---------- rapor dosyası ----------
    os.makedirs(os.path.dirname(rapor_yolu) or ".", exist_ok=True)
    with open(rapor_yolu, "w", encoding="utf-8") as f:
        f.write(f"# Üretim Raporu — Toplantı {t.sayi} ({t.tarih})\n\n")
        f.write(f"**Çıktı:** {os.path.basename(cikti_yolu)}\n\n")
        f.write(f"**1. bölüm maddesi:** {len(maddeler)}  "
                f"**2. bölüm (karar) maddesi:** {len(yap.kararlar)}\n\n")
        f.write(rapor.md())
        f.write("\n\n---\n*Rapor: eksik ya da şüpheli alanlar docx'e geçmeden önce "
                "Excel 'Düzeltmeler'/'Hakemler' sayfalarından netleştirilmelidir.*\n")

    rapor.ok(f"Belge üretildi: {cikti_yolu}")
    rapor.ok(f"Üretim raporu: {rapor_yolu}")
    return cikti_yolu, rapor_yolu, rapor


def main() -> int:
    ap = argparse.ArgumentParser(description="BAP Gündem .docx üretici",
                                 formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    ap.add_argument("--girdi", default="girdi/19.08.2026",
                    help="Toplantı klasörü: PDF'ler burada (alt klasörler de taranır)")
    ap.add_argument("--config", default="config/19.08.2026.xlsx",
                    help="Excel yapılandırma dosyası")
    ap.add_argument("--cikti", default="", help="Çıktı docx yolu (boşsa otomatik)")
    ap.add_argument("--logo", default="logo/sbu_logo.jpg", help="Üst blok logosu")
    ap.add_argument("--rapor", default="", help="Üretim raporu .md yolu (boşsa otomatik)")
    ap.add_argument("--sablon", default="", help="Bu yola yapılandırma şablonu üret ve çık")
    ap.add_argument("--bos", action="store_true", help="Şablonu boş üret (demo verisiz)")
    args = ap.parse_args()

    kok = os.path.dirname(os.path.abspath(__file__))

    if args.sablon:
        yol = args.sablon if os.path.isabs(args.sablon) else os.path.join(kok, args.sablon)
        sablon_olustur(yol, ornek=not args.bos)
        print(f"✔ Şablon üretildi: {yol}")
        print("  Sayfalar: Toplantı | Maddeler (opsiyonel) | Düzeltmeler | Hakemler "
              "| KararMaddeleri")
        return 0

    config_yolu = args.config if os.path.isabs(args.config) else os.path.join(kok, args.config)
    if not os.path.exists(config_yolu):
        print(f"✘ Yapılandırma bulunamadı: {config_yolu}")
        print(f"  Önce şablon üretin:  python gundem_uret.py --sablon {args.config}")
        return 1

    girdi_kok = args.girdi if os.path.isabs(args.girdi) else os.path.join(kok, args.girdi)
    if not os.path.isdir(girdi_kok):
        print(f"✘ Toplantı klasörü bulunamadı: {girdi_kok}")
        print("  PDF'leri şuraya koyun ve klasörü oluşturun; program tarar:")
        print(f"    {girdi_kok}")
        return 1

    logo_yolu = args.logo if os.path.isabs(args.logo) else os.path.join(kok, args.logo)

    dinleyici = lambda seviye, metin: print(f"[{seviye}] {metin}")
    cikti_yolu, rapor_yolu, rapor = uretim_yap(
        girdi_kok, config_yolu,
        cikti_yolu=args.cikti, logo_yolu=logo_yolu,
        rapor_yolu=args.rapor,
        dinleyici=dinleyici)

    print(f"\n✔ Gündem üretildi: {cikti_yolu}")
    print(f"✔ Üretim raporu   : {rapor_yolu}")
    uyarilar = [s for s in rapor.satirlar if s[0] == "UYARI"]
    if uyarilar:
        print(f"\n⚠ {len(uyarilar)} uyarı var (ayrıntı için rapora bakın):")
        for _, m in uyarilar[:12]:
            print(f"   - {m}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

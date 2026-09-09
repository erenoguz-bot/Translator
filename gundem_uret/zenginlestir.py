# -*- coding: utf-8 -*-
"""
Eksik bilgi zenginleştirme katmanı.

PDF'lerde her zaman bulunmayan alanlar (hakemin kurumu, A.B.D.'si vb.)
için kaynak zinciri — yalnızca ELDEKİ belgeler, internet/yapay zeka yok:

   1. Excel/config satırı        (en güvenilir; "onaylanmış değer")
   2. PDF'teki "Adresi" alanından yerel kural tabanlı çıkarım
   3. Yerel belge havuzu (eski gündem PDF'leri, girdi klasöründeki formlar)
   4. Bulunamadı -> uyarı; kurum için çağıran "Buraya Hakem Kurumu Yaz"
      yer tutucusunu koyar, A.B.D. için yürütücünün A.B.D.'si devreye girer
"""
from __future__ import annotations

import re
from typing import Optional

from .model import HakemGorusu
from .pdf_ayikla import adresten_kurum

KUCUK_SOZCUKLER = {"ve", "ile", "vs", "a.b.d."}


def _title_tr(metin: str) -> str:
    """BÜYÜK HARF bir kurum adını Türkçe kurallara uygun başlık biçimine çevirir:
    NECMETTİN ERBAKAN ÜNİVERSİTESİ -> Necmettin Erbakan Üniversitesi"""
    if not metin:
        return ""
    ilk_harf = {"I": "I", "İ": "İ", "A": "A", "Ç": "Ç", "Ğ": "Ğ", "Ö": "Ö",
                "Ş": "Ş", "Ü": "Ü"}
    def kelime_cikar(k):
        k = k.lower().replace("i̇", "i")
        if not k:
            return k
        ust = "İ" if k[0] == "i" else k[0].upper()
        return ust + k[1:]

    sonuc = []
    for soz in metin.split():
        parcalar = soz.split("-")
        yeni = [kelime_cikar(p) for p in parcalar if p]
        birlesik = "-".join(yeni)
        if birlesik.lower() not in KUCUK_SOZCUKLER:
            sonuc.append(birlesik)
        else:
            sonuc.append(birlesik.lower())
    return " ".join(sonuc)


def _kk(metin: str) -> str:
    """Türkçe güvenli küçük harf: 'İ'.casefold() 2 karaktere açılır ve
    konum kayması yaratır; önce İ -> i yapılır."""
    return (metin or "").replace("İ", "i").lower()


ABD_KALIP = re.compile(
    r"([A-ZÇĞİÖŞÜa-zçğıöşü0-9 ,./()-]{2,60}?)\s*(?:anabilim dalı|a\.b\.d\.|a\.d\.)",
    re.I)

UNVAN_ONEK = re.compile(
    r"^\s*(?:(?:Prof|Doç|Dr|Uzm|Arş\.?Gör|Öğr\.?Gör)\.?\s*"
    r"(?:Dr\.?|Öğr\.?\s*Üyesi|Gör\.?)?\s*)+")


def _ad_duz(ham: str) -> str:
    """'Prof.Dr. Mehmet ŞAHİN' -> 'Mehmet ŞAHİN' (unvan olmadan)."""
    if not ham:
        return ""
    return UNVAN_ONEK.sub("", ham).strip()


def _kurum_bicimle(ham: str) -> str:
    """Ham kurum parçasını düzgün Türkçe başlığa çevirir; İngilizce
    'X University' biçimini 'X Üniversitesi'ne çevirir."""
    if not ham:
        return ""
    s = ham.strip()
    s = re.sub(r"\s+University\s+of\b.*$", "", s, flags=re.I)
    s = re.sub(r"\s+(?:University|Universities)\b", " Üniversitesi", s,
               flags=re.I)
    s = re.sub(r"^[^A-Za-zÇĞİÖŞÜçğıöşü0-9]+", "", s)
    s = re.sub(r"[\s,;|:/]+$", "", s)
    if len(s) < 3:
        return ""
    return _title_tr(s)


def _metin_kurumlari(metin: str) -> list:
    """Metindeki kurum adayları: 'X Üniversitesi/Hastanesi/Fakültesi/...' ve
    İngilizce 'X University' kalıpları."""
    adaylar = []
    for m in re.finditer(
            r"([A-ZÇĞİÖŞÜ][^.;|()\"«»]{1,80}?)\s+"
            r"(Üniversitesi|Hastanesi|Fakültesi|Enstitüsü|Merkezi)\b",
            metin, re.I):
        adaylar.append(_kurum_bicimle(m.group(1) + " " + m.group(2)))
    for m in re.finditer(
            r"([A-ZÇĞİÖŞÜ][\w&.'\- ]{1,70}?)\s+"
            r"(?:University|Universities)\b", metin):
        adaylar.append(_kurum_bicimle(m.group(1) + " University"))
    return [a for a in adaylar if a]


ABD_OLMAYAN = {"sağlık bilimleri", "sağlık bilimleri enstitüsü", "temel tıp bilimleri",
              "cerrahi tıp bilimleri", "dahili tıp bilimleri", "tıp", "diş hekimliği",
              "eczacılık", "sağlık bilimleri fakültesi"}


def abd_gecerli_mi(abd: str) -> bool:
    """F-1'deki 'Ana Bilim Dalı' değeri gerçek bir A.B.D. gibi mi görünüyor?
    ('Sağlık Bilimleri' gibi genel bölüm adları gündemde işe yaramaz.)"""
    t = (abd or "").strip().lower().replace("a.b.d.", "").strip()
    if not t:
        return False
    return t not in ABD_OLMAYAN and len(t) >= 4


def _abd_bicimle(ham: str) -> str:
    """'beyin ve sinir cerrahisi anabilim dalı' gibi ham metni
    'Beyin ve Sinir Cerrahisi A.B.D.' biçimine getirir."""
    if not ham:
        return ""
    ham = re.sub(r"(?:ana\s*bilim\s*dalı|anabilim\s*dalı|a\.?\s*b\.?\s*d\.?|abd)\s*$",
                 "", ham, flags=re.I)
    ham = re.sub(r"\s*\(.*?\)", "", ham)
    ham = re.sub(r"^[^A-Za-zÇĞİÖŞÜçğıöşü0-9]+", "", ham)
    ham = re.sub(r"[\s,;:-]+$", "", ham).strip()
    if len(ham) < 4:
        return ""
    # kurum/bölüm ön eklerini at (ör. 'Tıp Fakültesi Beyin...', 'SAĞLIK BİLİMLERİ ÜNİVERSİTESİ')
    for onek in ("T.C.", "SAĞLIK BİLİMLERİ ÜNİVERSİTESİ", "SBÜ", "İSTANBUL ÜNİVERSİTESİ",
                 "TIP FAKÜLTESİ", "TIP FAKÜLTESİ "):
        if ham.upper().startswith(onek):
            ham = ham[len(onek):].strip(" /,-")
            break
    ham = _title_tr(ham)
    return (ham + " A.B.D.") if ham else ""


def yurutucu_abd_bul(ad: str, yerel_belgeler: Optional[dict] = None) -> dict:
    """Yürütücünün A.B.D.'sini ELDEKİ belgelerden bulur (internet yok).

    Dönen: {"abd": "... A.B.D.", "kaynak": "açıklama"} (bulunamazsa abd='')
    """
    if not ad or not yerel_belgeler:
        return {"abd": "", "kaynak": ""}
    bul = _yerel_zenginlestir(ad, yerel_belgeler)
    if bul.get("abd"):
        return {"abd": bul["abd"],
                "kaynak": bul.get("kaynak", "Yerel belgeler")}
    return {"abd": "", "kaynak": ""}


def _ad_arama_parcalari(ad: str) -> list:
    """'Prof.Dr. Mehmet ŞAHİN' -> ['mehmet şahin', 'şahin'] (unvansız)."""
    sozler = [w for w in re.split(r"\s+", (_ad_duz(ad or "") or "")) if w]
    if not sozler:
        return []
    if len(sozler) >= 2:
        return [_kk(" ".join(sozler[-2:])), _kk(sozler[-1])]
    return [_kk(sozler[0])]


def _yerel_zenginlestir(ad: str, belgeler: dict) -> dict:
    """ELDEKİ belgelerden (eski gündem PDF'leri, diğer formlar) kurum/A.B.D.
    çıkarır. Her belge metninde adın geçtiği yerin hemen sağındaki bağlama
    bakar; satır sonu boşlukla birleştirilmiştir.

    Gündem satır biçimleri:
      hakem   : 'Doç. Dr. Osman TANRIVERDİ  Beyin ve Sinir A.B.D. Başakşehir
                 Çam ve Sakura Şehir Hastanesi, SUAM DESTEKLENMELİ'
      yürütücü: 'Zeynep Büşra BOLAT (Hamidiye Sağlık Bilimleri Enstitüsü /
                 Moleküler Biyoloji ve Genetik A.B.D.) 150.000,00 TL'

    Dönen: {kurum, abd, kaynak} (kaynak: dosya adları)
    """
    if not ad or not belgeler:
        return {}
    anahtar = _ad_arama_parcalari(ad)
    if not anahtar:
        return {}
    kurum_say: dict = {}
    abd_say: dict = {}
    par_abd_say: dict = {}
    gorulen: set = set()
    for dosya, t in belgeler.items():
        kucuk = _kk(t)
        yerler = []
        bas = 0
        while True:
            i = kucuk.find(anahtar[0], bas)
            if i < 0:
                break
            yerler.append(i)
            bas = i + len(anahtar[0])
        if not yerler:
            # tam ad bulunamadı; tek kelimelik kısa ad güvenilmez -> atla
            continue
        for i in yerler:
            # adın HEMEN sağındaki bağlam (satır sonları boşluk yapıldı)
            sag = t[i + len(anahtar[0]): i + len(anahtar[0]) + 260]
            sag = re.sub(r"\s+", " ", sag)
            # satırın gerçek sonu: karar/bölüm başlangıcı
            for kes in ("desteklen", "olumlu hakem görüşü", "tekrar gündem"):
                i2 = _kk(sag).find(kes)
                if 0 < i2 < len(sag):
                    sag = sag[:i2]
            if not sag.strip():
                continue
            gorulen.add(dosya)
            for k in _metin_kurumlari(sag):
                anahtar_k = " ".join(k.split())
                kurum_say[anahtar_k] = kurum_say.get(anahtar_k, 0) + 1
            # A.B.D. 1) parantezli '(Kurum / A.B.D.)' biçimi (yürütücü satırı)
            par = re.search(r"\(([^()]{2,170}?)\)", sag)
            if par and "a.b.d." in _kk(par.group(1)) and "/" in par.group(1):
                a = _abd_bicimle(par.group(1).split("/")[-1])
                if a:
                    anahtar_a = " ".join(a.split())
                    par_abd_say[anahtar_a] = par_abd_say.get(anahtar_a, 0) + 1
            else:
                # 2) çıplak 'X A.B.D.' biçimi (hakem satırı): ilk eşleşme
                m = ABD_KALIP.search(sag)
                if m:
                    a = _abd_bicimle(m.group(1))
                    if a:
                        anahtar_a = " ".join(a.split())
                        abd_say[anahtar_a] = abd_say.get(anahtar_a, 0) + 1
    if par_abd_say:
        abd = max(par_abd_say, key=par_abd_say.get)
    elif abd_say:
        abd = max(abd_say, key=abd_say.get)
    kurum = max(kurum_say, key=kurum_say.get) if kurum_say else ""
    if not (kurum or abd):
        return {}
    return {"kurum": kurum, "abd": abd,
            "kaynak": "Yerel belge: " + ", ".join(sorted(gorulen))[:150]}


# --------------------------------------------------------------------------
# OpenAI uyumlu LLM uç noktası (isteğe bağlı)
# --------------------------------------------------------------------------
def hakem_zenginlestir(hakem: HakemGorusu, pdf_veri: dict,
                       onay: Optional[dict],
                       yerel_belgeler: Optional[dict] = None) -> dict:
    """Hakemin kurum/A.B.D. bilgisini ELDEKİ kaynaklardan toplar (internet yok).

    Kural:
      - kurum: Excel onayı -> kendi formundaki 'Adres' -> diğer belgeler
        (eski gündem PDF'leri vb.); bulunamazsa çağıran 'Buraya Hakem Kurumu
        Yaz' yer tutucusunu koyar.
      - A.B.D.: Excel onayı -> diğer belgeler; bulunamazsa çağıran
        yürütücünün A.B.D.'sini kullanır.
    pdf_veri : pdf_ayikla.hakem_formu_oku çıktısı (adres, karar vb.)
    onay     : config 'Hakemler' sayfasındaki satır ({kurum, abd, kaynak})
               veya None
    yerel_belgeler: {dosya_adı: düz metin} (girdi klasöründeki PDF'ler)

    Dönen: {kurum, abd, kaynak}  (kaynak hangi katmanın kazandığını söyler)
    """
    if onay and (onay.get("kurum") or onay.get("abd")):
        kaynak = onay.get("kaynak") or "Excel (onaylı)"
        return {"kurum": onay.get("kurum", ""),
                "abd": onay.get("abd", ""),
                "kaynak": kaynak}

    kurum, abd, kaynaklar = "", "", []
    adres_kurum = adresten_kurum(pdf_veri.get("adres", ""))
    if adres_kurum:
        kurum = _title_tr(adres_kurum)
        kaynaklar.append("PDF 'Adresi' alanı")
    if yerel_belgeler:
        bul = _yerel_zenginlestir(pdf_veri.get("hakem_adi", ""), yerel_belgeler)
        if bul.get("kurum") and not kurum:
            kurum = bul["kurum"]
        if bul.get("abd"):
            abd = bul["abd"]
        if bul.get("kurum") or bul.get("abd"):
            kaynaklar.append(bul.get("kaynak", "Yerel belgeler"))
    if kurum or abd:
        return {"kurum": kurum, "abd": abd,
                "kaynak": " | ".join(dict.fromkeys(kaynaklar))}
    return {"kurum": "", "abd": "", "kaynak": "bulunamadı"}

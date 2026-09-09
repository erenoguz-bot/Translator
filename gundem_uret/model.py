# -*- coding: utf-8 -*-
"""
Veri modelleri: Toplantı, Gündem maddesi (proje + hakem görüşleri),
karar maddesi (iptal / ek süre / tür değişikliği vb.) ve üretim raporu.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Optional


# --------------------------------------------------------------------------
# Karar eşleştirmeleri
# --------------------------------------------------------------------------
# Hakem formundaki "DEĞERLENDİRME SONUCUNUZ" seçenekleri -> gündemdeki kısa karar
# Uzun form (3 sayfa, puanlı) ve kısa form (1 sayfa, EVET/HAYIR/KISMEN)
# için karar ifadeleri -> gündemdeki kısa karar.
KARAR_RULE = [
    # TEKRAR DÜZENLENMELİ (uzun + kısa form ifadeleri)
    ("tekrar değerlendirilmelidir", "TEKRAR DÜZENLENMELİ"),
    ("düzeltilmeli", "TEKRAR DÜZENLENMELİ"),
    # DESTEKLENMEMELİ
    ("uygun değildir", "DESTEKLENMEMELİ"),
    ("nitelikte değil", "DESTEKLENMEMELİ"),
    # DESTEKLENMELİ
    ("öncelikle desteklenmelidir", "DESTEKLENMELİ"),
    ("desteklenmeli", "DESTEKLENMELİ"),
]


def kisa_karar(uzun_metin: str) -> Optional[str]:
    """Hakem formundaki işaretlenmiş karar metnini kısa karara çevirir.

    Sıralama önemlidir: önce 'tekrar/düzeltilmeli', sonra 'değil',
    en son genel 'desteklenmeli' aranır.
    """
    t = (uzun_metin or "").lower()
    for anahtar, kisa in KARAR_RULE:
        if anahtar in t:
            return kisa
    return None


def hakem_ozet_metni(kararlar) -> str:
    """Karar listesinden '3 Olumlu Hakem Görüşü' / '2 Olumlu ve 1 Tekrar
    Düzenlenmeli Hakem Görüşü' biçiminde özet satırı üretir."""
    olumlu = sum(1 for k in kararlar if k == "DESTEKLENMELİ")
    tekrar = sum(1 for k in kararlar if k == "TEKRAR DÜZENLENMELİ")
    diger = len(kararlar) - olumlu - tekrar
    parcalar = []
    if olumlu:
        parcalar.append(f"{olumlu} Olumlu")
    if tekrar:
        parcalar.append(f"{tekrar} Tekrar Düzenlenmeli")
    if diger:
        parcalar.append(f"{diger} Desteklenmemeli")
    kok = " ve ".join(parcalar)
    return f"{kok} Hakem Görüşü" if kok else ""


# --------------------------------------------------------------------------
# Veri modelleri
# --------------------------------------------------------------------------
@dataclass
class ToplantiBilgisi:
    tarih: str = ""                     # örn. 19/08/2026
    sayi: str = ""                      # örn. 2026/09
    kurum_ust: str = "T.C."
    kurum_adi: str = "SAĞLIK BİLİMLERİ ÜNİVERSİTESİ"
    kurum_alt: str = "Bilimsel Araştırma Projeleri Koordinatörlüğü"
    alt_bolum_basligi: str = "KARAR MADDELERİ"   # bölüm-2 başlığı (boş = başlık basma)
    karar_alt_satir: str = "KOMİSYON"            # karar maddelerinin alt satırı
    raportor_atamasi: str = "elle"               # "elle" | "sira" (sırayla dağıt)


    def kaynak(self) -> dict:
        return asdict(self)


@dataclass
class HakemGorusu:
    hakem_adi: str = ""          # PDF'ten okunan unvan+ad (ör. Prof. Dr. Cem ATABEY)
    karar_kisa: str = ""         # DESTEKLENMELİ / TEKRAR DÜZENLENMELİ / ...
    puan: Optional[int] = None
    ek_dosya: bool = False
    # --- zenginleştirilen alanlar ---
    abd: str = ""                # görünen A.B.D. satırı
    kurum: str = ""              # görünen kurum satırı
    kaynak: str = ""             # alanların kaynağı (pdf/web/el; url vs.)


@dataclass
class GundemMaddesi:
    """Birinci bölüm: PDF'lerden (proje formu + hakem formları) üretilen madde."""
    sira: int = 0
    klasor: str = ""             # kaynak klasör adı
    proje_turu: str = ""
    proje_adi: str = ""
    sure_ay: str = ""            # örn. 6 / 12 / 24 AY
    yurutucu_adi: str = ""
    yurutucu_kurum: str = ""     # yürütücünün bağlı olduğu hastane/fakülte
    yurutucu_abd: str = ""       # A.B.D.
    butce_tl: str = ""           # örn. 225.000,00
    tekrar_gundem: bool = False  # "(Tekrar Gündem)" etiketi
    raportor: str = ""           # maddeden sorumlu komisyon üyesi
    hakemler: list = field(default_factory=list)   # list[HakemGorusu]
    uyarilar: list = field(default_factory=list)   # üretim sırasında toplanan notlar

    def yurutucu_gosterim(self) -> str:
        """Yürütücü hücresi: 'Unvan Ad SOYADI (Kurum / A.B.D.)'"""
        parca = []
        if self.yurutucu_adi:
            parca.append(self.yurutucu_adi)
        birim = " / ".join(x for x in (self.yurutucu_kurum, self.yurutucu_abd) if x)
        if birim:
            parca.append(f"({birim})")
        elif self.yurutucu_abd:
            parca.append(f"({self.yurutucu_abd})")
        return "\n".join(parca)


@dataclass
class KararMaddesi:
    """İkinci bölüm: İPTAL / EK SÜRE / TÜR DEĞİŞİKLİĞİ / EK MALZEME vb. kararlar."""
    sira: int = 0
    proje_no: str = ""           # örn. 2025/073
    proje_turu: str = ""         # örn. Tıpta Uzmanlık Projesi
    proje_adi: str = ""
    sure_ay: str = ""
    yurutucu_adi: str = ""
    birim: str = ""              # Fakülte/Hastane + A.B.D. gösterimi
    butce_tl: str = ""
    harcanan_tl: str = ""        # opsiyonel: (Harcanan: ... TL)
    islem: str = ""              # örn. PROJENİN İPTALİ
    uyarilar: list = field(default_factory=list)


@dataclass
class UretimRaporu:
    """Her alanın hangi kaynaktan geldiğini ve uyarıları tutar."""
    satirlar: list = field(default_factory=list)
    _dinleyici: object = None

    def dinle(self, fn) -> None:
        """GUI vb. arayüzler için satır eklendikçe çağrılan geri çağırım."""
        self._dinleyici = fn

    def ekle(self, seviye: str, metin: str) -> None:
        self.satirlar.append((seviye, metin))
        if self._dinleyici:
            try:
                self._dinleyici(seviye, metin)
            except Exception:
                pass

    def uyari(self, metin: str) -> None:
        self.ekle("UYARI", metin)

    def bilgi(self, metin: str) -> None:
        self.ekle("BİLGİ", metin)

    def ok(self, metin: str) -> None:
        self.ekle("OK", metin)

    def md(self) -> str:
        """Markdown rapor metni üretir."""
        simgeler = {"OK": "✔", "BİLGİ": "•", "UYARI": "⚠"}
        cikti = []
        for seviye, metin in self.satirlar:
            cikti.append(f"- {simgeler.get(seviye, '•')} **[{seviye}]** {metin}")
        return "\n".join(cikti)

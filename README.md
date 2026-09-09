# BAP Gündem Üretim Sistemi

İndirilen **proje formlarını (F-1) ve hakem değerlendirme formlarını PDF olarak
otomatik okuyup**, örnek gündemle birebir aynı düzende **Word (.docx) gündem
belgesi** üreten araç. Windows'ta **masaüstü arayüzü (GUI)** ve istenirse
**EXE** ile; komut satırından da çalışır.

```
19.08.2026/                          ← toplantı klasörü (GUI'de bunu seçin)
├── t1.pdf                           ← talep 1: proje formu (adı önemli değil)
├── h1.pdf                           ← talep 1'in hakem raporu
├── h2.pdf
├── h3.pdf
├── t2.pdf                           ← talep 2: proje formu
├── h4.pdf                           ← talep 2'nin hakem raporu (sayısı değişir)
└── ...
        │   program tarar, eşleştirir, sıralar
        ▼
Gündem 19.08.2026.docx  +  üretim_raporu_2026-09.md
```

## Öne çıkan davranış

- **Klasör tarama otomatiktir.** PDF'leri toplantı klasörüne nasıl koyarsanız
  koyun (düz: `t1.pdf`, `t2.pdf`… veya her proje için alt klasör), program:
  1. her PDF'in türünü **içerikten** tanır (proje formu mu, hakem formu mu);
     Hakem formlarının **her iki şablonu** da desteklenir: uzun puanlı form
     (3 sayfa, "TOPLAM PUAN") ve kısa form (1 sayfa, EVET/HAYIR/KISMEN +
     e-imza). E-imzalı PDF'lerdeki boş (NUL) karakterler otomatik temizlenir;
  2. tek PDF içinde **birden çok form** varsa (proje + hakemler üst üste)
     sayfaları türlerine göre otomatik böler;
  3. hakem formlarını **dosya adına değil, içindeki proje adına göre**
     projesiyle eşleştirir (% benzerlik rapora yazılır) — böylece dosyaların
     sırası/karışık adlandırılması sonucu bozmaz;
  4. projeleri **sayısal (doğal) sırayla** numaralandırır: alt klasör adları
     insan sıralamasına göre dizilir (`1_x`, `2_y`, `10_z` → 1, 2, 10;
     alfabetik değil!). Klasörlerinizi `01_`, `02_`, … veya `1_`, `2_`, …
     diye adlandırmanız yeterlidir. Excel **'Maddeler' > 'Sıra'** sütunu
     doldurulursa o sıra kesin olarak kullanılır. Üretim raporunda her
     maddenin hangi klasörden geldiği yazar (`Sıra 3 <-- '2_ikinci'`);
  5. her adımı ve şüpheyi **üretim raporuna** yazar.
- **Excel artık zorunlu değildir.** Yalnızca şunlar için kullanılır:
  toplantı tarihi/sayısı, `(Tekrar Gündem)` bayrağı, raportör adı, alan
  düzeltmeleri, hakem kurum/A.B.D. bilgisi ve **ikinci bölüm karar maddeleri**
  (İPTAL / EK SÜRE / TÜR DEĞİŞİKLİĞİ vb.).
- PDF'te olmayan hakem kurumu/A.B.D. bilgisi yalnızca ELDEKİ belgelerden
  doldurulur (internet/yapay zeka YOK): **Excel onayı → formun "Adresi" alanı
  → yerel belge havuzu (eski gündem PDF'leri vb.)**; kurum bulunamazsa
  "Buraya Hakem Kurumu Yaz" yer tutucusu yazılır, A.B.D. bulunamazsa
  yürütücünün A.B.D.'si kullanılır ve rapora uyarı düşer.

---

## 1. Windows: GUI + EXE + BAT

1. `gundem-sistemi` klasörünü Windows'a kopyalayın (ör. `C:\BAP\`).
2. **`EXE_KUR.bat`** → çift tıklayın (tek seferlik): Python'u bulur, paketleri
   kurar, `dist\BAP_Gundem.exe`'yi derler. Python yoksa ekranda adım adım
   anlatır (python.org + "Add python.exe to PATH" işaretli olmalı).
3. Günlük kullanım: **`GUNDEM_BASLAT.bat`** → çift tıklayın (exe varsa onu,
   yoksa Python'u kullanır).
4. Arayüzde toplantı klasörünü gösterin → "Gündemi Üret". Excel gerektirmez;
   kutu içi demo veriler (`girdi/19.08.2026/`) hazırdır.

> EXE ancak Windows'ta derlenebilir (PyInstaller çapraz derleme yapmaz);
> `EXE_KUR.bat` bunu otomatik yapar. İlk çalıştırmada exe yanına `girdi/`,
> `config/`, `logo/` demo dosyaları kopyalanır; sonrasında taşınabilir.

## 2. Komut satırı

```bash
cd gundem-sistemi
pip install -r gereksinimler.txt

# yapılandırma şablonu (yalnızca Excel kullanacaksanız)
python gundem_uret.py --sablon config/19.08.2026.xlsx
python gundem_uret.py --sablon config/bos.xlsx --bos        # boş şablon

# üretim: PDF'leri toplantı klasörüne koyun, çalıştırın
python gundem_uret.py --girdi girdi/19.08.2026 --config config/19.08.2026.xlsx --logo logo/sbu_logo.jpg

# öneri: eski gündem PDF'lerini girdi/ köküne koyun (kurum/A.B.D. havuzu olur)
# örn. girdi/Gündem 2025-01.pdf
```

`--girdi` verilmezse varsayılan `girdi/19.08.2026` kullanılır. Çıktılar
`cikti/` altına iner; `--cikti` ve `--rapor` ile değiştirilebilir.

## 3. Excel yapılandırması (opsiyonel kısımlar)

Şablon sayfaları:

| Sayfa | Açıklama |
|---|---|
| **Toplantı** | `toplanti_tarihi`, `toplanti_sayisi`, `alt_bolum_basligi`, `karar_alt_satir` ("KOMİSYON"), kurum adı blokları |
| **Maddeler** | *İsteğe bağlı.* Sıra, **Klasör** (alt klasör adı veya düz dosyalar için `kok`), Tekrar Gündem (E/H), Raportör. Satır yoksa program otomatik sıralar |
| **Düzeltmeler** | Klasör + Alan + Değer: PDF'ten çıkanı ezer (`proje_turu, proje_adi, sure_ay, yurutucu_adi, yurutucu_kurum, yurutucu_abd, butce_tl`) |
| **Hakemler** | Klasör + Hakem adı + Kurum + A.B.D. + Kaynak(URL). Kurum/A.B.D. PDF'te yoksa buradan gelir |
| **KararMaddeleri** | 2. bölüm: İPTAL / EK SÜRE / TÜR DEĞİŞİKLİĞİ vb. (Sıra, Proje No, Tür, Ad, Süre, Yürütücü, Birim, Tutar, Harcanan, İşlem) |

Düz dosya durumunda Excel **Klasör** sütununa `kok` yazılır; alt klasör
kullanıyorsanız alt klasör adını yazın.

## 4. Nasıl çalışıyor?

```
Toplantı klasöründeki PDF'ler
   ├─ sayfa türü algılama (PROJE ÖNERİ FORMU / PROJE DEĞERLENDİRME FORMU)
   ├─ tek PDF içinde çoklu form → sayfa aralıklarına bölme
   ├─ hakem ↔ proje eşleştirme (içindeki proje adı benzerliği)
   └─ her talep = 1 proje + N hakem
          │
          ▼
Veri çıkarımı (koordinat + kalıp tabanlı; eksikler zenginleştirme katmanı —
yalnız eldeki belgeler: Excel > form adresi > yerel belge havuzu > uyarı)
          │
          ▼
docx üretici (ölçülmüş düzen)  +  üretim raporu .md (kaynak & uyarılar)
```

Demo bulguları: hakemlerin kurumları form PDF'lerinde yok; örnek gündem
PDF'inden (yerel belge havuzu) kurum + A.B.D. birlikte çıkarıldı (kaynaklar
üretim raporunda ve `config/*.xlsx > Hakemler > Kaynak` sütununda görünür).

## 5. Görsel düzen

Örnek gündem PDF'i karakter koordinatlarıyla ölçülüp Word'e aktarıldı:
A4 dikey (kenar 1,1 cm), logo + Times New Roman 12 pt kurum bloğu, tarih/sayı
satırı, 6 sütunlu tablo (Arial italic 9 pt başlıklar, Calibri 9 pt içerik,
sıra/tür/ad/süre/yürütücü/tutar kalın), madde bloğu: ana satır → "N Olumlu
Hakem Görüşü" → hakemler (ad-A.B.D. | kurum | karar) → raportör; ayrı
numaralı ikinci bölüm. Değişiklikler `gundem_uret/docx_uret.py`
sabitlerinden yapılır.


### Yürütücü A.B.D. gösterimi (eldeki belgelerden)

Örnek gündemde yürütücünün bulunduğu yerde Anabilim Dalı yer alır. Sistem
şöyle davranır:

1. Excel `Düzeltmeler` sayfasına `yurutucu_abd` yazılmışsa o değer kazanır
   (örn. `kok#1` -> Beyin ve Sinir A.B.D.).
2. Yoksa proje PDF'indeki ifade kullanılır.
3. A.B.D. boşsa ya da "Sağlık Bilimleri" gibi genel/enstitü düzeyi bir
   ifadeyse önce YEREL belge havuzundan (eski gündem PDF'leri) bulunur —
   örn. `Zeynep Büşra BOLAT`, önceki gündemdeki
   `(Hamidiye Sağlık Bilimleri Enstitüsü / Moleküler Biyoloji ve Genetik
   A.B.D.)` satırından otomatik doldurulur.
4. Belgelerde de yoksa rapor uyarı yazar; Excel `Düzeltmeler`'den elle
   doldurulabilir ya da girdi köküne ilgili eski gündem PDF'i koyulup yeniden
   üretilir.

### Hakemlerin kurumu ve A.B.D.'si (ELDEKİ belgeler öncelikli)

Hakem formlarında kurum/A.B.D. bilgisi bulunmaz; sistem bunları ELDEKİ
belgelerden toplar (internet kullanılmaz):

1. Excel `Hakemler` sayfasındaki onay satırı (varsa her zaman kazanır).
2. Hakem formunun kendi **"Adres"** alanı -> kurum.
3. **Yerel belge havuzu**: hedef toplantı klasöründeki tüm PDF'ler + girdi
   kökünde adı "Gündem" olan PDF'ler (önceki toplantı gündemleri). Havuzda
   hakemin adının geçtiği satırın hemen sağındaki bağlam taranır; örneğin
   önceki gündemdeki
   `Doç. Dr. X ... Beyin ve Sinir A.B.D. Başakşehir Çam ve Sakura Şehir
   Hastanesi DESTEKLENMELİ` biçimli satırlardan kurum ve A.B.D. birlikte
   alınır. Böylece aynı hakemler önceki toplantılarda raporlanmışsa bilgileri
   doğru ve güncel hâliyle gelir. Öneri: eski gündem PDF'lerini `girdi/`
   köküne (örn. `girdi/Gündem 2025-01.pdf`) koyun; hepsi otomatik havuz olur.
4. A.B.D. yine bulunamadıysa **yürütücüyle aynı A.B.D.** kullanılır
   (kaynağa "yürütücü A.B.D. (kural)" yazılır).
5. Kurum bulunamadıysa **"Buraya Hakem Kurumu Yaz"** yer tutucusu yazılır ve
   rapora uyarı düşer (elle doldurma işareti).

Sonuç yanlış/eksikse Excel `Hakemler` sayfasına kurum/A.B.D. yazılıp yeniden
üretilebilir (Excel her zaman tüm kaynaklardan üstündür).

Hakem görüşü sayısı 3 ile sınırlı değildir: formda kaç hakem varsa o kadar
satır gelir (5 hakemle test edildi -> "5 Olumlu Hakem Görüşü"). Raportör
satırından sonra notlar için boş (çerçeveli) bir satır eklenir.


## 6. Sınırlar ve ipuçları

- Form sürümü değişirse çıkarım etiketleri güncellenir; üretim raporu boş
  kalan alanı söyler (Excel'den doldurulabilir).
- Karar işareti `(X)` metin katmanına yazılmamışsa uyarı üretilir.
- Taranmış (OCR'siz) PDF'ler için önce OCR gerekir.
- Hakemlerin "farklı farklı kararları" gerçektir: her hakem kendi seçeneğini
  işaretler; özet satırı otomatik toplanır (örnek gündemdeki karışık
  maddelerle aynı mantık).

## 7. Büyütme fikirleri

Hakem havuzu dosyasından otomatik eşleme, raportör otomatik dağıtımı, portal
indirme botu, tutanak üretimi, toplu toplantı üretimi.

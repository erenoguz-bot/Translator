@echo off
title BAP Gundem - Tani
cd /d "%~dp0"
echo ============================================================
echo  TANI EKRANI
echo  Bu ekran acik kaldiysa .bat dosyalariniz normal calisiyordur.
echo  Eger bu ekran bile aninda kapaniyorsa sorun bat dosyalarinda
echo  degil, Windows ayarlarindadir (asagidaki notlara bakin).
echo ============================================================
echo.
echo Python testi:
where python
where py
echo.
echo EXE testi:
if exist "dist\BAP_Gundem.exe" echo BAP_Gundem.exe MEVCUT
if not exist "dist\BAP_Gundem.exe" echo BAP_Gundem.exe YOK
echo.
echo ============================================================
echo  NOTLAR:
echo  1) .bat dosyalarini ZIP icinden degil, ONCE masaustune veya
echo     bir klasore ACIKARAK (sag tik - Tumunu Ayikla) calistirin.
echo  2) Internetten inen dosyalar engellenmis olabilir: dosyaya
echo     sag tik - Ozellikler - "Engellemeyi kaldir" kutusunu
echo     isaretleyin - Tamam.
echo  3) .bat dosyalari Notepad ile aciliyorsa (cift tiklayinca
echo     metin editoru aciliyorsa) dosya iliskisi bozulmustur:
echo     bir .bat dosyasina sag tik - Birlikte ac - Komut Istemi
echo     secin ve "Her zaman kullan" isaretleyin.
echo ============================================================
pause

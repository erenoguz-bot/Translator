@echo off
title BAP Gundem Uretici - Kurulum
cd /d "%~dp0"
set PY=
set PYV=

echo ============================================================
echo   BAP Gundem Uretici - TEK SEFERLIK KURULUM
echo   Calisma klasoru: %~dp0
echo ============================================================
echo.

rem ---------- 1) Python bul (python, sonra py denensin) ----------
where python >nul 2>nul
if errorlevel 1 goto PYDENE
set PY=python
%PY% --version >nul 2>nul
if not errorlevel 1 goto PYBULUNDU
set PY=

:PYDENE
where py >nul 2>nul
if errorlevel 1 goto PYYOK
set PY=py -3
%PY% --version >nul 2>nul
if not errorlevel 1 goto PYBULUNDU
goto PYYOK

:PYBULUNDU
echo [OK] Python bulundu:
%PY% --version
echo.
goto PIPKUR

:PYYOK
echo.
echo [HATA] Python bulunamadi veya calismiyor.
echo.
echo NE YAPMALI:
echo   1) https://www.python.org/downloads/ adresinden Python 3.9 veya
echo      daha yenisini indirin.
echo   2) Kurulum sihirbazinin ILK ekraninda en alttaki
echo      "Add python.exe to PATH" kutusunu MUTLAKA isaretleyin.
echo   3) Kurulum bitince bu pencereyi kapatin ve EXE_KUR.bat
echo      dosyasini TEKRAR cift tiklayin.
echo.
echo   Not: Microsoft Store Python'u ise yaramazsa python.org
echo   kurulumunu kullanin.
echo.
pause
exit /b 1

:PIPKUR
echo [1/3] Python paketleri kuruluyor... (ilk adim uzun surebilir)
%PY% -m pip install --upgrade pip setuptools wheel
if errorlevel 1 goto PIPHATA
%PY% -m pip install pyinstaller
if errorlevel 1 goto PAKETHATA
%PY% -m pip install -r gereksinimler.txt
if errorlevel 1 goto PAKETHATA
echo.
goto DERLE

:PIPHATA
echo.
echo [HATA] pip calistirilamadi. Internet baglantinizi kontrol edin.
pause
exit /b 1

:PAKETHATA
echo.
echo [HATA] Paketler kurulamadi.
echo Oneri: pencereye sag tiklayip "Yonetici olarak calistir" secin,
echo        ya da internet baglantisini kontrol edip tekrar deneyin.
echo        (Kurumsal bilgisayarlarda guvenlik yazilimi pip'i
echo        engelleyebilir; o durumda BT desteginizden yardim isteyin.)
pause
exit /b 1

:DERLE
echo [2/3] EXE derleniyor... (2-4 dakika surebilir, lutfen bekleyin)
if exist "dist\BAP_Gundem.exe" del "dist\BAP_Gundem.exe" >nul 2>nul
%PY% -m PyInstaller --noconfirm --clean --onefile --windowed --name BAP_Gundem --collect-all pdfplumber --collect-all pypdf --collect-all PyQt5 --collect-all qtawesome --hidden-import gundem_uret.pdf_ayikla --hidden-import gundem_uret.config_dosya --hidden-import gundem_uret.docx_uret --hidden-import gundem_uret.model --hidden-import gundem_uret.zenginlestir --add-data "gundem_uret.py;." --add-data "gundem_uret;gundem_uret" --add-data "girdi;girdi" --add-data "config;config" --add-data "logo;logo" gundem_gui.py
if errorlevel 1 goto DERLEHATA
if not exist "dist\BAP_Gundem.exe" goto DERLEHATA
echo.
echo [3/3] KURULUM TAMAMLANDI!
echo.
echo dist\BAP_Gundem.exe hazir.
echo Bundan sonra GUNDEM_BASLAT.bat dosyasini kullanin.
echo.
echo Programi simdi acmak icin E tusuna basin, kapatmak icin herhangi bir tusa basin.
set /p SECIM="> "
if /i "%SECIM%"=="E" start "" "dist\BAP_Gundem.exe"
pause
exit /b 0

:DERLEHATA
echo.
echo [HATA] EXE derlenemedi. Yukaridaki hata metnini kopyalayip paylasin.
pause
exit /b 1

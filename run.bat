@echo off
title Gelismis PDF Editor
echo PDF Editor baslatiliyor...

:: Python yüklü mü kontrol et
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo Python sisteminizde bulunamadi.
    echo Lutfen https://www.python.org adresinden Python'u yukleyin ve PATH'e ekleyin.
    pause
    goto end
)

:: Gereksinimleri kontrol et ve kur
echo Gerekli kutuphaneler kontrol ediliyor...
pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo Kutuphaneler kurulurken bir hata olustu!
    pause
    goto end
)

:: Uygulamayı Başlat
echo PDF Editor aciliyor...
python pdf_editor.py

:end
pause

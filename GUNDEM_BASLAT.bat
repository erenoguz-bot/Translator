@echo off
title BAP Gundem Uretici
cd /d "%~dp0"

if exist "dist\BAP_Gundem.exe" goto EXEVAR

set PY=
where python >nul 2>nul
if errorlevel 1 goto PYDENE
set PY=python
%PY% --version >nul 2>nul
if not errorlevel 1 goto PYVAR
set PY=

:PYDENE
where py >nul 2>nul
if errorlevel 1 goto PYYOK
set PY=py -3
%PY% --version >nul 2>nul
if errorlevel 1 goto PYYOK

:PYVAR
echo [BILGI] BAP_Gundem.exe yok; Python ile baslatiliyor...
%PY% gundem_gui.py
if errorlevel 1 goto CALISHATA
exit /b 0

:EXEVAR
start "" "dist\BAP_Gundem.exe"
exit /b 0

:PYYOK
echo.
echo [HATA] BAP_Gundem.exe henuz uretilmemis VE Python calismiyor.
echo.
echo ONERILEN ADIM:
echo   Bu klasordeki EXE_KUR.bat dosyasini cift tiklayin.
echo   (Python yoksa once python.org adresinden kurun ve kurulumda
echo    "Add python.exe to PATH" kutusunu isaretleyin;
echo    EXE_KUR.bat gerisini otomatik yapar.)
echo.
pause
exit /b 1

:CALISHATA
echo.
echo [HATA] Program Python ile baslatilamadi.
echo Oneri: EXE_KUR.bat dosyasini calistirin (paketleri kurar ve
echo        BAP_Gundem.exe uretir), sonra bu dosyayi tekrar kullanin.
echo.
pause
exit /b 1

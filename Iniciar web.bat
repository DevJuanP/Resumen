@echo off
rem Arranca la interfaz web local y abre el navegador.
cd /d "%~dp0"
python web.py --abrir
if errorlevel 1 pause

@echo off
echo ====================================
echo  PD Live Chat Tracker - Build to EXE
echo ====================================
echo.
echo Installing dependencies...
python -m pip install pyperclip pyinstaller
echo.
echo Building EXE... (this takes 1-2 minutes)
python -m PyInstaller --onefile --noconsole --add-data "icon.ico;." --icon "icon.ico" --name "PD-Live-Chat-Tracker" app.py
echo.
echo Building Installer...
"C:\Program Files (x86)\NSIS\makensis.exe" installer.nsi
echo.
echo ====================================
echo  DONE!
echo  EXE:       dist\PD-Live-Chat-Tracker.exe
echo  Installer: PD-Live-Chat-Tracker-Setup-v1.0.0.exe
echo ====================================
pause

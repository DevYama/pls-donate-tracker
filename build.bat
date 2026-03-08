@echo off
echo ====================================
echo  PLS DONATE Tracker - Build to EXE
echo ====================================
echo.
echo Installing dependencies...
python -m pip install pyperclip pyinstaller
echo.
echo Building EXE... (this takes 1-2 minutes)
python -m PyInstaller --onefile --noconsole --name "PLS-DONATE-Tracker" app.py
echo.
echo Building Installer...
"C:\Program Files (x86)\NSIS\makensis.exe" installer.nsi
echo.
echo ====================================
echo  DONE!
echo  EXE:       dist\PLS-DONATE-Tracker.exe
echo  Installer: PLS-DONATE-Tracker-Setup-v1.0.0.exe
echo ====================================
pause

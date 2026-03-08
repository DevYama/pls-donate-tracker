; =====================================================
;  PLS DONATE Tracker - NSIS Installer
; =====================================================

!define APP_NAME     "PLS DONATE Tracker"
!define APP_VERSION  "1.0.0"
!define APP_EXE      "PLS-DONATE-Tracker.exe"
!define PUBLISHER    "YourNameHere"

SetCompressor /SOLID lzma
Name            "${APP_NAME} v${APP_VERSION}"
OutFile         "PLS-DONATE-Tracker-Setup-v${APP_VERSION}.exe"
InstallDir      "$PROGRAMFILES64\PLS DONATE Tracker"
RequestExecutionLevel admin
ShowInstDetails show

!include "MUI2.nsh"
!define MUI_ABORTWARNING
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_LANGUAGE "English"

Section "Install"
    SetOutPath "$INSTDIR"
    File "dist\${APP_EXE}"

    CreateShortcut "$DESKTOP\${APP_NAME}.lnk" "$INSTDIR\${APP_EXE}"
    CreateDirectory "$SMPROGRAMS\${APP_NAME}"
    CreateShortcut "$SMPROGRAMS\${APP_NAME}\${APP_NAME}.lnk" "$INSTDIR\${APP_EXE}"
    CreateShortcut "$SMPROGRAMS\${APP_NAME}\Uninstall.lnk"   "$INSTDIR\Uninstall.exe"

    WriteUninstaller "$INSTDIR\Uninstall.exe"

    WriteRegStr   HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\PLSDONATETracker" "DisplayName"     "${APP_NAME}"
    WriteRegStr   HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\PLSDONATETracker" "DisplayVersion"  "${APP_VERSION}"
    WriteRegStr   HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\PLSDONATETracker" "Publisher"       "${PUBLISHER}"
    WriteRegStr   HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\PLSDONATETracker" "UninstallString" '"$INSTDIR\Uninstall.exe"'
    WriteRegDWORD HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\PLSDONATETracker" "NoModify"        1
    WriteRegDWORD HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\PLSDONATETracker" "NoRepair"        1
SectionEnd

Section "Uninstall"
    ExecWait 'taskkill /F /IM "${APP_EXE}"'
    Delete "$INSTDIR\${APP_EXE}"
    Delete "$INSTDIR\Uninstall.exe"
    RMDir  "$INSTDIR"
    Delete "$DESKTOP\${APP_NAME}.lnk"
    Delete "$SMPROGRAMS\${APP_NAME}\${APP_NAME}.lnk"
    Delete "$SMPROGRAMS\${APP_NAME}\Uninstall.lnk"
    RMDir  "$SMPROGRAMS\${APP_NAME}"
    DeleteRegKey HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\PLSDONATETracker"
SectionEnd

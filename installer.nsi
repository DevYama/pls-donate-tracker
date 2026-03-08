; =====================================================
;  PD Live Chat Tracker - NSIS Installer
; =====================================================

!define APP_NAME     "PD Live Chat Tracker"
!define APP_VERSION  "1.0.0"
!define APP_EXE      "PD-Live-Chat-Tracker.exe"
!define PUBLISHER    "DevYama"

SetCompressor /SOLID lzma
Name            "${APP_NAME} v${APP_VERSION}"
OutFile         "PD-Live-Chat-Tracker-Setup-v${APP_VERSION}.exe"
InstallDir      "$PROGRAMFILES64\PD Live Chat Tracker"
RequestExecutionLevel admin
ShowInstDetails show

!include "MUI2.nsh"
!define MUI_ABORTWARNING
!define MUI_ICON "icon.ico"
!define MUI_UNICON "icon.ico"
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
    File "icon.ico"

    CreateShortcut "$DESKTOP\${APP_NAME}.lnk" "$INSTDIR\${APP_EXE}" "" "$INSTDIR\icon.ico"
    CreateDirectory "$SMPROGRAMS\${APP_NAME}"
    CreateShortcut "$SMPROGRAMS\${APP_NAME}\${APP_NAME}.lnk" "$INSTDIR\${APP_EXE}" "" "$INSTDIR\icon.ico"
    CreateShortcut "$SMPROGRAMS\${APP_NAME}\Uninstall.lnk"   "$INSTDIR\Uninstall.exe"

    WriteUninstaller "$INSTDIR\Uninstall.exe"

    WriteRegStr   HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\PDLiveChatTracker" "DisplayName"     "${APP_NAME}"
    WriteRegStr   HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\PDLiveChatTracker" "DisplayVersion"  "${APP_VERSION}"
    WriteRegStr   HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\PDLiveChatTracker" "Publisher"       "${PUBLISHER}"
    WriteRegStr   HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\PDLiveChatTracker" "UninstallString" '"$INSTDIR\Uninstall.exe"'
    WriteRegDWORD HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\PDLiveChatTracker" "NoModify"        1
    WriteRegDWORD HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\PDLiveChatTracker" "NoRepair"        1
SectionEnd

Section "Uninstall"
    ExecWait 'taskkill /F /IM "${APP_EXE}"'
    Delete "$INSTDIR\${APP_EXE}"
    Delete "$INSTDIR\icon.ico"
    Delete "$INSTDIR\Uninstall.exe"
    RMDir  "$INSTDIR"
    Delete "$DESKTOP\${APP_NAME}.lnk"
    Delete "$SMPROGRAMS\${APP_NAME}\${APP_NAME}.lnk"
    Delete "$SMPROGRAMS\${APP_NAME}\Uninstall.lnk"
    RMDir  "$SMPROGRAMS\${APP_NAME}"
    DeleteRegKey HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\PDLiveChatTracker"
SectionEnd

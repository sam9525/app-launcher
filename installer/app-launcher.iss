#ifndef AppVersion
#error AppVersion not set - build with installer\build.bat
#endif
; Inno Setup script -> AppLauncher-Setup.exe (per-user, no admin required).
[Setup]
AppName=App Launcher
AppVersion={#AppVersion}
DefaultDirName={autopf}\App Launcher
DefaultGroupName=App Launcher
UninstallDisplayName=App Launcher
OutputBaseFilename=AppLauncher-Setup
OutputDir=Output
Compression=lzma2
SolidCompression=yes
PrivilegesRequired=lowest
ArchitecturesInstallIn64BitMode=x64compatible
SetupIconFile=..\assets\app-launcher-icon.ico
UninstallDisplayIcon={app}\AppLauncher.exe

[Files]
Source: "..\dist\AppLauncher.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\App Launcher"; Filename: "{app}\AppLauncher.exe"
Name: "{group}\Uninstall App Launcher"; Filename: "{uninstallexe}"

[Tasks]
Name: startup; Description: "Start App Launcher when Windows starts"; GroupDescription: "Startup:"

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; \
  ValueName: "AppLauncher"; ValueData: """{app}\AppLauncher.exe"""; \
  Flags: uninsdeletevalue; Tasks: startup

[Run]
Filename: "{app}\AppLauncher.exe"; Description: "Launch App Launcher now"; \
  Flags: nowait postinstall skipifsilent

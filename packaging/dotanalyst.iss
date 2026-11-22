; Inno Setup script: the installer for build\dist\DotAnalyst (packaging\dotanalyst.spec). Build with packaging\build.ps1.
; Installs for the current user only, so it asks for no admin rights and the in-app update can run it silently.
#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

[Setup]
AppId={{6C1F3A52-8E4B-4D7A-9B1E-2F5D8C7A4E19}
AppName=DotAnalyst
AppVersion={#AppVersion}
AppPublisher=DotAnalyst
DefaultDirName={localappdata}\Programs\DotAnalyst
DefaultGroupName=DotAnalyst
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=..\build\installer
OutputBaseFilename=DotAnalyst-Setup
Compression=lzma2
SolidCompression=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=yes
UninstallDisplayIcon={app}\DotAnalyst.exe

[Tasks]
Name: desktopicon; Description: "Create a desktop shortcut"; Flags: unchecked

[InstallDelete]
; files a new version no longer has would stay next to the new ones and could be imported instead
Type: filesandordirs; Name: "{app}\_internal"

[Files]
Source: "..\build\dist\DotAnalyst\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion

[Icons]
Name: "{autoprograms}\DotAnalyst"; Filename: "{app}\DotAnalyst.exe"
Name: "{autodesktop}\DotAnalyst"; Filename: "{app}\DotAnalyst.exe"; Tasks: desktopicon

[Run]
; not after a silent update: that runs once the window was closed, so the user meant to quit
Filename: "{app}\DotAnalyst.exe"; Description: "Start DotAnalyst"; Flags: nowait postinstall skipifsilent

; the data in %LOCALAPPDATA%\DotAnalyst (database, .env, replays) stays when DotAnalyst is uninstalled

; Dannify Windows installer (Inno Setup 6)
; Build:
;   "C:\Users\Riskraptor\AppData\Local\Programs\Inno Setup 6\ISCC.exe" dannify.iss
; Output: packaging\out\Dannify-Setup-<version>.exe

#define MyAppName "Dannify"
#define MyAppVersion "3.3.0"
#define MyAppPublisher "Dannify"
#define MyAppExeName "Dannify.exe"
#define BuildDir "..\Backend\dist\Dannify"

[Setup]
AppId={{7E1D8F0C-5A53-4D7B-9C2B-DA221F900001}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
; Per-user install: no admin prompt, installs to %LOCALAPPDATA%\Programs
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputDir=out
OutputBaseFilename=Dannify-Setup-{#MyAppVersion}
SetupIconFile=..\Backend\assets\dannify.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
; The running app owns this mutex (see desktop.py): Inno then asks the user
; to close it instead of failing on locked files.
AppMutex=Local\DannifyAppMutex
Compression=lzma2/ultra64
LZMAUseSeparateProcess=yes
LZMANumBlockThreads=4
LZMADictionarySize=262144
SolidCompression=yes
WizardStyle=modern
; The app binds a LAN port; closing running instance before upgrade
CloseApplications=yes
RestartApplications=no
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "french"; MessagesFile: "compiler:Languages\French.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "{#BuildDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
; Ship-time settings (update repo, Paystack keys): see config\README.md.
Source: "config\*.json"; DestDir: "{app}\config"; Flags: ignoreversion

[Icons]
; AppUserModelID must match APP_USER_MODEL_ID in the app, or Windows files
; the running program and its shortcut separately: the taskbar button will
; not pin, and the now-playing overlay falls back to "Unknown app".
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; AppUserModelID: "Dannify.Player"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon; AppUserModelID: "Dannify.Player"

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Remove runtime state but keep the user's music (~\Music\Dannify stays!)
Type: filesandordirs; Name: "{localappdata}\Dannify"

[Code]
// Kill a running Dannify before install/uninstall so files aren't locked.
procedure TaskKill();
var
  R: Integer;
begin
  Exec('taskkill.exe', '/F /IM Dannify.exe', '', SW_HIDE, ewWaitUntilTerminated, R);
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  TaskKill();
  Result := '';
end;

function InitializeUninstall(): Boolean;
begin
  TaskKill();
  Result := True;
end;

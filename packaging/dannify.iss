; Dannify Windows installer (Inno Setup 6)
; Build:
;   "C:\Users\Riskraptor\AppData\Local\Programs\Inno Setup 6\ISCC.exe" dannify.iss
; Output: packaging\out\Dannify-Setup-<version>.exe

#define MyAppName "Dannify"
#define MyAppVersion "3.4.0"
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
; Deliberately no AppMutex. With one set, Setup stops and asks the user to
; go and close the app themselves, which is the "Dannify is running" wall
; people kept hitting on an upgrade. PrepareToInstall below asks the app to
; close itself instead, and Restart Manager picks up anything left.
Compression=lzma2/ultra64
LZMAUseSeparateProcess=yes
LZMANumBlockThreads=4
LZMADictionarySize=262144
SolidCompression=yes
WizardStyle=modern
; Close anything still holding our files, and do not bring it back: the
; user either asked for this install from inside the app (which restarts
; itself) or ran the installer by hand, and neither wants a surprise launch.
CloseApplications=force
CloseApplicationsFilter=*.exe,*.dll,*.pyd
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
// Closing a running Dannify before its files are replaced.
//
// This used to be a straight `taskkill /F`, which is why an upgrade could
// take the app out mid-write and lose whatever it had not saved yet. Ask
// first: `--quit` signals the running instance to shut down properly,
// which a window close cannot do because close-to-tray swallows it.
// Force is still there, but only for a copy that ignored the request.

function DannifyIsRunning(): Boolean;
begin
  Result := CheckForMutexes('Local\DannifyAppMutex');
end;

procedure StopDannify();
var
  Exe: String;
  ResultCode, Waited: Integer;
begin
  if not DannifyIsRunning() then
    Exit;

  Exe := ExpandConstant('{app}\{#MyAppExeName}');
  if FileExists(Exe) then
    Exec(Exe, '--quit', '', SW_HIDE, ewNoWait, ResultCode);

  // Give it six seconds to drain and let go of its files.
  Waited := 0;
  while (Waited < 6000) and DannifyIsRunning() do
  begin
    Sleep(250);
    Waited := Waited + 250;
  end;

  // Still there: it is not going to leave on its own.
  if DannifyIsRunning() then
  begin
    Exec('taskkill.exe', '/F /IM {#MyAppExeName}', '', SW_HIDE,
         ewWaitUntilTerminated, ResultCode);
    Sleep(800);
  end;
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  StopDannify();
  Result := '';
end;

function InitializeUninstall(): Boolean;
begin
  StopDannify();
  Result := True;
end;

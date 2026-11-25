; Inno Setup script: the installer for build\dist\DotAnalyst (packaging\dotanalyst.spec). Build with packaging\build.ps1.
; Installs for the current user only, so it asks for no admin rights and the in-app update can run it silently.
; The answers go to HKCU\Software\DotAnalyst (DataDir, ReplayDir), where dotanalyst/app.py reads them. A silent run (the
; in-app update) shows no pages and writes neither, so it keeps what the last interactive run stored.
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
DisableWelcomePage=yes
DisableDirPage=no
DisableReadyPage=yes
PrivilegesRequired=lowest
OutputDir=..\build\installer
OutputBaseFilename=DotAnalyst-Setup
Compression=lzma2
SolidCompression=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=yes
SetupIconFile=dotanalyst.ico
UninstallDisplayIcon={app}\DotAnalyst.exe
; tells Explorer to drop its in-memory icons at the end: it keys them by path, and kept 0.1.0's PyInstaller icon for
; DotAnalyst.exe on the taskbar after updates
ChangesAssociations=yes
; the app's colours; the logo band is drawn in [Code]
WizardStyle=modern dark hidebevels
WizardBackColor=#151a21
WizardSmallImageFile=
WizardImageFile=

[Tasks]
Name: desktopicon; Description: "Create a desktop shortcut"; Flags: unchecked
Name: startup; Description: "Start DotAnalyst with Windows, in the tray, so it keeps fetching your matches"; Flags: unchecked

[InstallDelete]
; files a new version no longer has would stay next to the new ones and could be imported instead
Type: filesandordirs; Name: "{app}\_internal"

[Files]
Source: "..\build\dist\DotAnalyst\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion
Source: "..\frontend\public\logo.png"; Flags: dontcopy

[Icons]
; the app's taskbar id (app.py), so a pinned or started shortcut and the running window share one button
Name: "{autoprograms}\DotAnalyst"; Filename: "{app}\DotAnalyst.exe"; AppUserModelID: "DotAnalyst.DotAnalyst"
Name: "{autodesktop}\DotAnalyst"; Filename: "{app}\DotAnalyst.exe"; Tasks: desktopicon; AppUserModelID: "DotAnalyst.DotAnalyst"

[Registry]
; the key with the setup's answers goes with the program; the data folder it names only if the user says so
Root: HKCU; Subkey: "Software\DotAnalyst"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "DotAnalyst"; \
  ValueData: """{app}\DotAnalyst.exe"" --tray"; Flags: uninsdeletevalue; Tasks: startup

[Run]
; not after a silent update: that runs once the window was closed, so the user meant to quit
Filename: "{app}\DotAnalyst.exe"; Description: "Start DotAnalyst"; Flags: nowait postinstall skipifsilent
; an update the app installed from the tray (/TRAY) puts it back there
Filename: "{app}\DotAnalyst.exe"; Parameters: "--tray"; Flags: nowait; Check: FromTray

[UninstallRun]
; also when it hides in the tray, with its parser (/T): their files would be locked
Filename: "{sys}\taskkill.exe"; Parameters: "/F /T /IM DotAnalyst.exe"; Flags: runhidden; RunOnceId: "StopDotAnalyst"

[Code]
const
  Key = 'Software\DotAnalyst';
  DotaReplays = 'steamapps\common\dota 2 beta\game\dota\replays';
  Band = $2E251E;       // #1e252e as Delphi's $BBGGRR
  Secondary = $C8BEB6;  // #b6bec8

var
  DataPage, ReplayPage: TInputDirWizardPage;
  UseReplays: TNewCheckBox;
  NotFound: TNewStaticText;
  AskData: Boolean;
  UninstallData: String;

function FromTray: Boolean;
var
  I: Integer;
begin
  Result := False;
  for I := 1 to ParamCount do
    if CompareText(ParamStr(I), '/TRAY') = 0 then
      Result := True;
end;

function DefaultData: String;
begin
  Result := ExpandConstant('{localappdata}\DotAnalyst');
end;

{ The first Steam library that has Dota's replay folder: Steam's own folder, then every "path" in libraryfolders.vdf. }
function FindDotaReplays: String;
var
  Steam, Lib, Line: String;
  Lines: TArrayOfString;
  I, P: Integer;
begin
  Result := '';
  if not RegQueryStringValue(HKCU, 'Software\Valve\Steam', 'SteamPath', Steam) then
    Exit;
  StringChangeEx(Steam, '/', '\', True);
  if DirExists(AddBackslash(Steam) + DotaReplays) then begin
    Result := AddBackslash(Steam) + DotaReplays;
    Exit;
  end;
  if not LoadStringsFromFile(AddBackslash(Steam) + 'steamapps\libraryfolders.vdf', Lines) then
    Exit;
  for I := 0 to GetArrayLength(Lines) - 1 do begin
    Line := Lines[I];
    P := Pos('"path"', Line);
    if P = 0 then
      Continue;
    Line := Copy(Line, P + 6, MaxInt);       // "path"   "D:\\SteamLibrary"
    Delete(Line, 1, Pos('"', Line));
    Lib := Copy(Line, 1, Pos('"', Line) - 1);
    StringChangeEx(Lib, '\\', '\', True);
    if (Lib <> '') and DirExists(AddBackslash(Lib) + DotaReplays) then begin
      Result := AddBackslash(Lib) + DotaReplays;
      Exit;
    end;
  end;
end;

procedure UseReplaysClick(Sender: TObject);
begin
  ReplayPage.Edits[0].Enabled := UseReplays.Checked;
  ReplayPage.Buttons[0].Enabled := UseReplays.Checked;
end;

procedure AddBand(Parent: TWinControl; Height: Integer);
var
  Fill, Logo: TBitmapImage;
begin
  Fill := TBitmapImage.Create(WizardForm);
  Fill.Parent := Parent;
  Fill.SetBounds(0, 0, Parent.Width, Height);
  Fill.BackColor := Band;

  Logo := TBitmapImage.Create(WizardForm);
  Logo.Parent := Parent;
  Logo.SetBounds(ScaleX(20), ScaleY(14), ScaleX(235), ScaleY(36));  // 418x64 shrunk to 36 px high
  Logo.Stretch := True;
  Logo.BackColor := Band;
  Logo.PngImage.LoadFromFile(ExpandConstant('{tmp}\logo.png'));
end;

{ The logo on a #1e252e band at the top; the page's heading and description below it, on the window's colour. The
  finished page has no such header: there the band replaces the empty picture strip on its left. }
procedure DrawBand;
var
  Page: TNewNotebookPage;
  Height, Shift, I: Integer;
begin
  Height := ScaleY(64);
  ExtractTemporaryFile('logo.png');
  WizardForm.ClientHeight := WizardForm.ClientHeight + Height;
  WizardForm.InnerNotebook.Top := WizardForm.InnerNotebook.Top + Height;
  WizardForm.MainPanel.Height := WizardForm.MainPanel.Height + Height;
  WizardForm.PageNameLabel.Top := WizardForm.PageNameLabel.Top + Height;
  WizardForm.PageDescriptionLabel.Top := WizardForm.PageDescriptionLabel.Top + Height;
  WizardForm.PageDescriptionLabel.Font.Color := Secondary;
  WizardForm.WizardSmallBitmapImage.Visible := False;
  AddBand(WizardForm.MainPanel, Height);

  Page := WizardForm.FinishedPage;
  WizardForm.WizardBitmapImage2.Visible := False;
  Shift := WizardForm.FinishedHeadingLabel.Left - WizardForm.PageNameLabel.Left;
  for I := 0 to Page.ControlCount - 1 do
    if Page.Controls[I] <> WizardForm.WizardBitmapImage2 then begin
      Page.Controls[I].Left := Page.Controls[I].Left - Shift;
      Page.Controls[I].Width := Page.Controls[I].Width + Shift;
      Page.Controls[I].Top := Page.Controls[I].Top + Height;
    end;
  // the wider heading may need fewer lines; the text below follows it up (the run list follows the text by itself)
  WizardForm.FinishedLabel.Top := WizardForm.FinishedLabel.Top + WizardForm.AdjustLabelHeight(WizardForm.FinishedHeadingLabel);
  AddBand(Page, Height);
end;

procedure InitializeWizard;
var
  Previous, Found: String;
  Shift: Integer;
begin
  DrawBand;

  // only on a first install: a 0.1.0 install has its data in the default folder without DataDir recorded
  AskData := not RegValueExists(HKCU, Key, 'DataDir') and not DirExists(DefaultData + '\data');
  DataPage := CreateInputDirPage(wpSelectDir, 'Data folder',
    'Where DotAnalyst keeps your matches, settings and the replays it downloads.',
    'The database, settings and downloaded replays go in this folder. It can grow to several GB.', False, '');
  DataPage.Add('');
  DataPage.Values[0] := DefaultData;

  ReplayPage := CreateInputDirPage(DataPage.ID, 'Dota replays',
    'DotAnalyst can read the replays Dota downloaded instead of downloading them again.',
    'Every replay you watched in the Dota client is saved in this folder.', False, '');
  ReplayPage.Add('');
  UseReplays := TNewCheckBox.Create(ReplayPage);
  UseReplays.Parent := ReplayPage.Surface;
  UseReplays.Caption := 'Use the replays Dota already downloaded';
  UseReplays.SetBounds(0, ReplayPage.Edits[0].Top, ReplayPage.SurfaceWidth, ScaleY(20));
  UseReplays.OnClick := @UseReplaysClick;
  Shift := ScaleY(28);
  ReplayPage.Edits[0].Top := ReplayPage.Edits[0].Top + Shift;
  ReplayPage.Buttons[0].Top := ReplayPage.Buttons[0].Top + Shift;
  NotFound := TNewStaticText.Create(ReplayPage);
  NotFound.Parent := ReplayPage.Surface;
  NotFound.Top := ReplayPage.Edits[0].Top + ReplayPage.Edits[0].Height + ScaleY(10);
  NotFound.Caption := 'Dota 2 wasn''t found on this PC. Tick the box and pick its replay folder if it is somewhere else.';
  NotFound.Font.Color := Secondary;
  NotFound.Visible := False;

  Found := FindDotaReplays;
  if RegQueryStringValue(HKCU, Key, 'ReplayDir', Previous) then begin  // a reinstall: the last answer
    UseReplays.Checked := Previous <> '';
    if Previous <> '' then
      ReplayPage.Values[0] := Previous
    else
      ReplayPage.Values[0] := Found;
  end else begin
    UseReplays.Checked := Found <> '';
    ReplayPage.Values[0] := Found;
  end;
  NotFound.Visible := Found = '';
  UseReplaysClick(nil);
end;

function ShouldSkipPage(PageID: Integer): Boolean;
begin
  Result := (PageID = DataPage.ID) and not AskData;
end;

function NextButtonClick(CurPageID: Integer): Boolean;
begin
  Result := True;
  if (CurPageID = ReplayPage.ID) and UseReplays.Checked and not DirExists(ReplayPage.Values[0]) then begin
    MsgBox('This folder doesn''t exist. Pick Dota''s replay folder, or untick the box.', mbError, MB_OK);
    Result := False;
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep <> ssPostInstall then
    Exit;
  if not WizardIsTaskSelected('startup') then  // unticked on a reinstall: no longer at login
    RegDeleteValue(HKCU, 'Software\Microsoft\Windows\CurrentVersion\Run', 'DotAnalyst');
  if WizardSilent then
    Exit;
  if AskData then
    RegWriteStringValue(HKCU, Key, 'DataDir', DataPage.Values[0]);
  if UseReplays.Checked then
    RegWriteStringValue(HKCU, Key, 'ReplayDir', ReplayPage.Values[0])
  else
    RegWriteStringValue(HKCU, Key, 'ReplayDir', '');  // "" = off; no value at all = Steam's default folder
end;

function InitializeUninstall: Boolean;
begin
  if not RegQueryStringValue(HKCU, Key, 'DataDir', UninstallData) or (UninstallData = '') then
    UninstallData := DefaultData;  // read now: the key is gone by the time the files are
  Result := True;
end;

{ Only what DotAnalyst itself puts there, never the folder as a whole: the user may have picked one with other files. }
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if (CurUninstallStep <> usPostUninstall) or UninstallSilent or not DirExists(UninstallData) then
    Exit;
  if MsgBox('Also delete your DotAnalyst data (database, settings, downloaded replays) in ' + UninstallData + '?',
      mbConfirmation, MB_YESNO or MB_DEFBUTTON2) <> IDYES then
    Exit;
  DelTree(UninstallData + '\data', True, True, True);
  DelTree(UninstallData + '\update', True, True, True);
  DeleteFile(UninstallData + '\.env');
  DeleteFile(UninstallData + '\dotanalyst.log');
  RemoveDir(UninstallData);  // only if nothing else is left in it
end;

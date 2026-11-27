[Setup]
AppId={{AF9937F2-6352-482C-90A6-A568BA2B6BCC}
AppName=Naraka Atelier
AppVersion={#AtelierVersion}
DefaultDirName={localappdata}\Programs\Naraka Atelier
DisableDirPage=no
DisableProgramGroupPage=yes
DisableWelcomePage=no
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
PrivilegesRequired=lowest
WizardStyle=modern
ShowLanguageDialog=yes
UninstallDisplayIcon={app}\NarakaAtelier.exe
CloseApplications=yes
RestartApplications=no
OutputBaseFilename=NarakaAtelier-v{#AtelierVersion}-Setup-x64
Compression=lzma2/fast
SolidCompression=yes

[Languages]
Name: en; MessagesFile: "compiler:Default.isl"
Name: zh; MessagesFile: "{#ChineseMessages}"

[Messages]
en.WelcomeLabel2=Setup will install Naraka Atelier and its built-in catalogue. Have your Naraka installation folder handy and close Naraka and Atelier before continuing.
zh.WelcomeLabel2=安装程序会安装 Naraka Atelier 及内置外观目录。请准备好《永劫无间》的安装路径，并在继续前关闭游戏和 Atelier。

[CustomMessages]
en.GameTitle=Naraka installation
en.GameSubtitle=Choose where Naraka is already installed.
en.GameDescription=Select the folder containing NarakaBladepoint.exe. Atelier checks game compatibility when it starts.
en.GameInvalid=Select a Naraka folder containing NarakaBladepoint.exe and the installed game resources.
en.InstallOverlap=Choose an Atelier destination outside the Naraka game folder.
en.SaveFailed=Setup could not save the Naraka folder.
zh.GameTitle=选择《永劫无间》安装目录
zh.GameSubtitle=请选择已安装《永劫无间》的文件夹。
zh.GameDescription=请选择包含 NarakaBladepoint.exe 的文件夹。Atelier 启动后会检查游戏版本是否兼容。
zh.GameInvalid=请选择同时包含 NarakaBladepoint.exe 和游戏资源文件的安装目录。
zh.InstallOverlap=请将 Atelier 安装到《永劫无间》游戏文件夹以外的位置。
zh.SaveFailed=安装程序无法保存游戏目录。

[Tasks]
Name: desktopicon; Description: "{cm:CreateDesktopIcon}"; Flags: unchecked

[Files]
Source: "{#PayloadDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\Naraka Atelier"; Filename: "{app}\NarakaAtelier.exe"
Name: "{autodesktop}\Naraka Atelier"; Filename: "{app}\NarakaAtelier.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\NarakaAtelier.exe"; Description: "{cm:LaunchProgram,Naraka Atelier}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: files; Name: "{app}\game-folder.txt"

[Code]
var
  GamePage: TInputDirWizardPage;

function IsGameFolder(const Folder: String): Boolean;
begin
  Result := (Folder <> '') and
    FileExists(AddBackslash(Folder) + 'NarakaBladepoint.exe') and
    FileExists(AddBackslash(Folder) + 'NarakaBladepoint_Data\StreamingAssets\AppRes.info');
end;

function VdfValue(Line, Key: String): String;
var
  Prefix: String;
  Quote: Integer;
begin
  Result := '';
  Line := Trim(Line);
  Prefix := '"' + Key + '"';
  if CompareText(Copy(Line, 1, Length(Prefix)), Prefix) <> 0 then
    exit;
  Line := Trim(Copy(Line, Length(Prefix) + 1, Length(Line)));
  if Copy(Line, 1, 1) <> '"' then
    exit;
  Line := Copy(Line, 2, Length(Line));
  Quote := Pos('"', Line);
  if Quote > 0 then
    Result := Copy(Line, 1, Quote - 1);
end;

function GameInLibrary(const Library: String): String;
var
  Entries: TArrayOfString;
  I: Integer;
  Name, Folder: String;
begin
  Result := '';
  if not LoadStringsFromFile(AddBackslash(Library) + 'steamapps\appmanifest_1203220.acf', Entries) then
    exit;
  for I := 0 to GetArrayLength(Entries) - 1 do begin
    Name := VdfValue(Entries[I], 'installdir');
    if Name <> '' then begin
      Folder := AddBackslash(Library) + 'steamapps\common\' + Name;
      if IsGameFolder(Folder) then
        Result := Folder;
      exit;
    end;
  end;
end;

function DetectSteamGame: String;
var
  Root, Library, Folder: String;
  Entries: TArrayOfString;
  I: Integer;
begin
  Result := '';
  if not RegQueryStringValue(HKCU, 'Software\Valve\Steam', 'SteamPath', Root) then
    if not RegQueryStringValue(HKLM32, 'Software\Valve\Steam', 'InstallPath', Root) then
      exit;
  StringChangeEx(Root, '/', '\', True);
  Result := GameInLibrary(Root);
  if not LoadStringsFromFile(AddBackslash(Root) + 'steamapps\libraryfolders.vdf', Entries) then
    exit;
  for I := 0 to GetArrayLength(Entries) - 1 do begin
    Library := VdfValue(Entries[I], 'path');
    if Library <> '' then begin
      StringChangeEx(Library, '\\', '\', True);
      Folder := GameInLibrary(Library);
      if Folder <> '' then begin
        if (Result <> '') and (CompareText(Result, Folder) <> 0) then begin
          Result := '';
          exit;
        end;
        Result := Folder;
      end;
    end;
  end;
end;

procedure InitializeWizard;
var
  Folder: String;
begin
  GamePage := CreateInputDirPage(wpSelectDir, CustomMessage('GameTitle'),
    CustomMessage('GameSubtitle'), CustomMessage('GameDescription'), False, '');
  GamePage.Add('');
  Folder := ExpandConstant('{param:GAMEPATH|}');
  if Folder = '' then begin
    Folder := GetPreviousData('NarakaFolder', '');
    if not IsGameFolder(Folder) then
      Folder := DetectSteamGame;
  end;
  GamePage.Values[0] := Folder;
end;

function ValidateFolders: String;
var
  GameFolder, InstallFolder: String;
begin
  Result := '';
  GameFolder := Trim(GamePage.Values[0]);
  if not IsGameFolder(GameFolder) then begin
    Result := CustomMessage('GameInvalid');
    exit;
  end;
  InstallFolder := AddBackslash(ExpandFileName(WizardDirValue));
  GameFolder := AddBackslash(ExpandFileName(GameFolder));
  if Pos(Lowercase(GameFolder), Lowercase(InstallFolder)) = 1 then
    Result := CustomMessage('InstallOverlap');
end;

function NextButtonClick(PageId: Integer): Boolean;
var
  Problem: String;
begin
  Result := True;
  if PageId = GamePage.ID then begin
    Problem := ValidateFolders;
    Result := Problem = '';
    if not Result then
      SuppressibleMsgBox(Problem, mbError, MB_OK, IDOK);
  end;
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  Result := ValidateFolders;
end;

procedure RegisterPreviousData(PreviousDataKey: Integer);
begin
  SetPreviousData(PreviousDataKey, 'NarakaFolder', ExpandFileName(Trim(GamePage.Values[0])));
end;

procedure CurStepChanged(Step: TSetupStep);
var
  Lines: TArrayOfString;
begin
  if Step = ssPostInstall then begin
    SetArrayLength(Lines, 1);
    Lines[0] := ExpandFileName(Trim(GamePage.Values[0]));
    if not SaveStringsToUTF8File(ExpandConstant('{app}\game-folder.txt'), Lines, False) then
      RaiseException(CustomMessage('SaveFailed'));
  end;
end;

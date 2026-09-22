; Ёхо (Yo-Voice) Windows installer. Compile with installer\build-setup.ps1
; (ISCC.exe). Output: E:\yo-voice\Yo-Voice-Setup.exe
;
; Wizard: welcome → choose install folder → tasks → progress bar → finish.
; Analog of Linux scripts/install.sh: Start Menu + Desktop «Ёхо», optional
; autostart. The checkbox has no Flags: checked, so it starts unchecked.
; Tasks also require a model choice (download now is the default). That pair
; is exclusive and is not in the autostart group.
; No administrator rights unless the chosen folder requires them
; (PrivilegesRequiredOverridesAllowed=dialog).

#define MyAppName "Ёхо"
#define MyAppNameFull "Ёхо (Yo-Voice)"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "iammedved"
#define MyAppURL "https://github.com/iammedved/Yo-Voice"
#define MyAppExeName "Yo-Voice.exe"

[Setup]
AppId={{E8C0A1B2-4D3E-4F5A-9B8C-1A2B3C4D5E6F}
AppName={#MyAppNameFull}
AppVerName={#MyAppNameFull} {#MyAppVersion}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
AppCopyright=Copyright (c) 2026 iammedved
VersionInfoVersion=1.0.0.0
VersionInfoProductName={#MyAppName}
VersionInfoProductVersion={#MyAppVersion}
VersionInfoCompany={#MyAppPublisher}
VersionInfoCopyright=Copyright (c) 2026 iammedved
VersionInfoDescription={#MyAppNameFull} Setup
DefaultDirName={localappdata}\Programs\Yo-Voice
DefaultGroupName={#MyAppName}
DisableWelcomePage=no
DisableDirPage=no
DisableProgramGroupPage=yes
DisableReadyPage=no
AlwaysShowDirOnReadyPage=yes
AllowRootDirectory=no
DirExistsWarning=auto
EnableDirDoesntExistWarning=no
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
UsedUserAreasWarning=no
OutputDir=E:\yo-voice
OutputBaseFilename=Yo-Voice-Setup
Compression=lzma2
SolidCompression=yes
LZMAUseSeparateProcess=yes
WizardStyle=modern
WizardSizePercent=120
SetupLogging=no
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
UninstallDisplayName={#MyAppNameFull}
UninstallDisplayIcon={app}\{#MyAppExeName}
UninstallFilesDir={app}
CloseApplications=yes
CloseApplicationsFilter=Yo-Voice.exe
RestartApplications=no
RestartIfNeededByRun=no
AllowNoIcons=no
UsePreviousAppDir=yes
UsePreviousTasks=yes
ShowLanguageDialog=no
#if FileExists("..\\assets\\yo-voice.ico")
SetupIconFile=..\assets\yo-voice.ico
#endif

[Languages]
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"

[Messages]
SetupWindowTitle=Установка — {#MyAppNameFull}
BeveledLabel={#MyAppNameFull}

[CustomMessages]
AutostartGroup=Автозапуск
AutostartTask=Запускать Ёхо при входе в Windows (рекомендуется)
LaunchNow=Запустить Ёхо сейчас
ModelGroup=Модель распознавания
ModelDownloadNow=Скачать модель распознавания сейчас (около 0,8 ГБ)
ModelDownloadLater=Скачать модель после первого запуска

[Tasks]
; Own group. exclusive is only on these two, so autostart stays a normal checkbox.
; Inno has no "checked" flag. A task without unchecked starts selected, so modelnow is the default radio.
Name: modelnow; Description: "{cm:ModelDownloadNow}"; GroupDescription: "{cm:ModelGroup}"; Flags: exclusive
Name: modellater; Description: "{cm:ModelDownloadLater}"; GroupDescription: "{cm:ModelGroup}"; Flags: exclusive unchecked
Name: autostart; Description: "{cm:AutostartTask}"; GroupDescription: "{cm:AutostartGroup}"

[Files]
; CUDA DLLs are a separate entry. On a PC with no NVIDIA (Ryzen + Radeon)
; ShouldInstallNvidiaRuntime is false and they are not unpacked.
Source: "..\dist\Yo-Voice\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs; Excludes: "nvidia\cublas\bin\*,nvidia\cudnn\bin\*,nvidia\cuda_runtime\bin\*,nvidia\cuda_nvrtc\bin\*"
Source: "..\dist\Yo-Voice\_internal\nvidia\*"; DestDir: "{app}\_internal\nvidia"; Flags: ignoreversion recursesubdirs createallsubdirs; Check: ShouldInstallNvidiaRuntime
#if FileExists("Uninstall.exe")
Source: "Uninstall.exe"; DestDir: "{app}"; Flags: ignoreversion
#endif

[Icons]
; Frozen Yo-Voice.exe with no args also starts the daemon (tray). Parameters
; keep older builds that defaulted to toggle working after a rebuild.
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Parameters: "daemon"; WorkingDir: "{app}"; Comment: "Голосовой ввод в любое текстовое поле"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Parameters: "daemon"; WorkingDir: "{app}"; Comment: "Голосовой ввод в любое текстовое поле"

[Registry]
; Drop a previous Run value, then write it again only if Autostart is checked.
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueName: "Yo-Voice"; Flags: deletevalue uninsdeletevalue dontcreatekey
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "Yo-Voice"; ValueData: """{app}\{#MyAppExeName}"" daemon"; Flags: uninsdeletevalue; Tasks: autostart

[Run]
; App window is the progress UI. Do not hide it and do not use nowait.
Filename: "{app}\{#MyAppExeName}"; Parameters: "prefetch"; StatusMsg: "Скачивание модели распознавания"; Tasks: modelnow; Flags: waituntilterminated
Filename: "{app}\{#MyAppExeName}"; Parameters: "daemon"; Description: "{cm:LaunchNow}"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "{app}\{#MyAppExeName}"; Parameters: "quit"; Flags: runhidden skipifdoesntexist waituntilterminated; RunOnceId: "YoVoiceQuit"
Filename: "{sys}\taskkill.exe"; Parameters: "/IM Yo-Voice.exe /F"; Flags: runhidden waituntilterminated; RunOnceId: "YoVoiceKill"

[Code]
var
  HwReady: Boolean;
  HwKnown: Boolean;
  HwNvidia: Boolean;
  HwGpu: String;
  HwCpu: String;

function EnsureHardware: Boolean;
var
  I: Integer;
  Key, Desc, Cpu: String;
begin
  if HwReady then
  begin
    Result := True;
    Exit;
  end;
  HwReady := True;
  HwKnown := False;
  HwNvidia := False;
  HwGpu := '';
  HwCpu := '';
  if RegQueryStringValue(HKLM, 'HARDWARE\DESCRIPTION\System\CentralProcessor\0', 'ProcessorNameString', Cpu) then
    HwCpu := Trim(Cpu);
  for I := 0 to 15 do
  begin
    Key := 'SYSTEM\CurrentControlSet\Control\Class\{4d36e968-e325-11ce-bfc1-08002be10318}\' + Format('%.4d', [I]);
    if not RegQueryStringValue(HKLM, Key, 'DriverDesc', Desc) then
      Continue;
    Desc := Trim(Desc);
    if Desc = '' then
      Continue;
    if (Pos('MICROSOFT', Uppercase(Desc)) > 0) and (Pos('BASIC', Uppercase(Desc)) > 0) then
      Continue;
    HwKnown := True;
    if HwGpu <> '' then
      HwGpu := HwGpu + ', ';
    HwGpu := HwGpu + Desc;
    if (Pos('NVIDIA', Uppercase(Desc)) > 0) or (Pos('GEFORCE', Uppercase(Desc)) > 0) then
      HwNvidia := True;
  end;
  Result := True;
end;

function ShouldInstallNvidiaRuntime: Boolean;
begin
  EnsureHardware;
  if not HwKnown then
    Result := True
  else
    Result := HwNvidia;
end;

function InitializeSetup: Boolean;
begin
  EnsureHardware;
  Result := True;
end;

function ComputeNote(const NewLine: String): String;
begin
  EnsureHardware;
  if not HwKnown then
  begin
    Result :=
      'Видеокарту определить не удалось. Библиотеки NVIDIA будут установлены.' + NewLine +
      'Если карты NVIDIA нет, распознавание пойдёт на процессоре.';
    Exit;
  end;
  if HwNvidia then
  begin
    Result := 'Режим этого компьютера: видеокарта NVIDIA.' + NewLine +
      'Распознавание будет на NVIDIA CUDA.';
    if HwGpu <> '' then
      Result := Result + NewLine + 'Видеоадаптер: ' + HwGpu;
    Exit;
  end;
  Result := 'Режим этого компьютера: процессор.' + NewLine +
    'Видеокарты NVIDIA нет, библиотеки CUDA не копируются.' + NewLine;
  if HwCpu <> '' then
    Result := Result + 'Процессор: ' + HwCpu + NewLine;
  if HwGpu <> '' then
    Result := Result + 'Видеоадаптер: ' + HwGpu + NewLine;
  Result := Result +
    'Распознавание и перевод идут на процессоре (int8). Встроенная графика AMD не используется:' + NewLine +
    'модель считает только через NVIDIA CUDA, а у Radeon для неё мало памяти.' + NewLine +
    'Драйвер NVIDIA ставить не нужно. Пауза после фразы будет длиннее, чем на отдельной видеокарте.';
end;

function UpdateReadyMemo(Space, NewLine, MemoUserInfoInfo, MemoDirInfo, MemoTypeInfo, MemoComponentsInfo, MemoGroupInfo, MemoTasksInfo: String): String;
begin
  Result := '';
  if MemoUserInfoInfo <> '' then
    Result := Result + MemoUserInfoInfo + NewLine + NewLine;
  if MemoDirInfo <> '' then
    Result := Result + MemoDirInfo + NewLine + NewLine;
  if MemoTypeInfo <> '' then
    Result := Result + MemoTypeInfo + NewLine + NewLine;
  if MemoComponentsInfo <> '' then
    Result := Result + MemoComponentsInfo + NewLine + NewLine;
  if MemoGroupInfo <> '' then
    Result := Result + MemoGroupInfo + NewLine + NewLine;
  if MemoTasksInfo <> '' then
    Result := Result + MemoTasksInfo + NewLine + NewLine;
  Result := Result + ComputeNote(NewLine);
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  ResultCode: Integer;
  ExePath: String;
begin
  NeedsRestart := False;
  ExePath := ExpandConstant('{app}\{#MyAppExeName}');
  if FileExists(ExePath) then
  begin
    Exec(ExePath, 'quit', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
    Sleep(800);
  end;
  Exec(ExpandConstant('{sys}\taskkill.exe'), '/IM Yo-Voice.exe /F', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  Result := '';
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  ChoiceDir, ChoicePath, Choice: String;
begin
  if CurStep <> ssPostInstall then
    Exit;
  ChoiceDir := ExpandConstant('{localappdata}\yo-voice');
  ChoicePath := ChoiceDir + '\prefetch.choice';
  if not ForceDirectories(ChoiceDir) then
  begin
    Log('prefetch.choice directory was not created: ' + ChoiceDir);
    Exit;
  end;
  if IsTaskSelected('modelnow') then
    Choice := 'now'
  else
    Choice := 'later';
  // ASCII, so the bytes are UTF-8 with no BOM. Not config.json.
  if not SaveStringToFile(ChoicePath, Choice, False) then
    Log('prefetch.choice was not written: ' + ChoicePath);
end;

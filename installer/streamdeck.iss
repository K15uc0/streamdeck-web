; Instalador do Stream Deck (Inno Setup 6.3+).
; Empacota a versao em pasta (PyInstaller --onedir --noconsole) gerada em dist\onedir\StreamDeck.
; Uso (na raiz do repositorio):
;   iscc /DMyAppVersion=2.5.0 installer\streamdeck.iss
; Saida: dist-installer\StreamDeck-Instalador.exe
;
; Instala so para o usuario atual, sem pedir administrador, em
; %LOCALAPPDATA%\Programs\StreamDeck. Os dados do usuario (Documentos\StreamDeck)
; nunca sao tocados: nem na instalacao, nem na atualizacao, nem na desinstalacao.
;
; Parametros extras de linha de comando:
;   /RESTARTAPP=1  abre o programa no fim mesmo em modo silencioso (usado pela
;                  atualizacao automatica do proprio app).

#ifndef MyAppVersion
  #error "Passe a versao: iscc /DMyAppVersion=x.y.z installer\streamdeck.iss"
#endif
#ifndef SourceDir
  #define SourceDir "..\dist\onedir\StreamDeck"
#endif

#define MyAppName "Stream Deck"
#define MyAppExe "StreamDeck.exe"
#define MyRunKey "Software\Microsoft\Windows\CurrentVersion\Run"

[Setup]
; AppId fixo: nunca mude (e o que liga as atualizacoes a instalacao existente)
AppId={{73098DD7-0665-44D1-A8B9-D8776131CCA5}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher=Stream Deck caseiro
AppPublisherURL=https://github.com/K15uc0/streamdeck-web
AppSupportURL=https://github.com/K15uc0/streamdeck-web/issues
AppUpdatesURL=https://github.com/K15uc0/streamdeck-web/releases
VersionInfoVersion={#MyAppVersion}
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=commandline
DefaultDirName={localappdata}\Programs\StreamDeck
DisableProgramGroupPage=yes
DisableDirPage=auto
UsePreviousAppDir=yes
UsePreviousTasks=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\dist-installer
OutputBaseFilename=StreamDeck-Instalador
SetupIconFile=..\icon.ico
UninstallDisplayIcon={app}\{#MyAppExe}
UninstallDisplayName={#MyAppName}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
; o [Code] pede para o app fechar pela API; o Restart Manager fica de reserva
CloseApplications=yes
CloseApplicationsFilter=*.exe,*.dll,*.pyd
RestartApplications=no

[Languages]
Name: "ptbr"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Tasks]
Name: "desktopicon"; Description: "Criar atalho na Área de Trabalho"; Flags: unchecked
Name: "autostart"; Description: "Iniciar com o Windows"; Flags: unchecked

[InstallDelete]
; versao em pasta: tira bibliotecas da versao anterior que nao existem mais
Type: filesandordirs; Name: "{app}\_internal"

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExe}"; WorkingDir: "{app}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExe}"; WorkingDir: "{app}"; Tasks: desktopicon

[Registry]
; mesmo nome e formato que o app usa (winapi._autostart_command)
Root: HKCU; Subkey: "{#MyRunKey}"; ValueType: string; ValueName: "StreamDeck"; ValueData: """{app}\{#MyAppExe}"" --minimizado"; Tasks: autostart; Flags: uninsdeletevalue

[Run]
Filename: "{app}\{#MyAppExe}"; Description: "Abrir o Stream Deck agora"; WorkingDir: "{app}"; Flags: nowait postinstall skipifsilent
; atualizacao automatica (silenciosa): reabre o programa
Filename: "{app}\{#MyAppExe}"; WorkingDir: "{app}"; Flags: nowait; Check: RestartAppPedido

[UninstallDelete]
Type: filesandordirs; Name: "{app}\_internal"
Type: files; Name: "{app}\instalado.txt"

[Code]
const
  RunKey = '{#MyRunKey}';

function RestartAppPedido: Boolean;
begin
  Result := ExpandConstant('{param:RESTARTAPP|0}') = '1';
end;

{ GET/POST em 127.0.0.1:porta; devolve True se respondeu 200 }
function Pedir(const Metodo, Url: String): Boolean;
var
  Http: Variant;
begin
  Result := False;
  try
    Http := CreateOleObject('WinHttp.WinHttpRequest.5.1');
    Http.SetTimeouts(1000, 1000, 2000, 3000);
    Http.Open(Metodo, Url, False);
    Http.SetRequestHeader('X-StreamDeck', '1');
    Http.SetRequestHeader('Content-Type', 'application/json');
    if Metodo = 'POST' then
      Http.Send('{}')
    else
      Http.Send('');
    Result := (Http.Status = 200) and ((Metodo = 'POST') or (Pos('streamdeck', Http.ResponseText) > 0));
  except
    Result := False;
  end;
end;

function AlgumRodando: Boolean;
var
  Porta: Integer;
begin
  Result := False;
  for Porta := 8765 to 8767 do
    if Pedir('GET', Format('http://127.0.0.1:%d/api/local/hello', [Porta])) then
    begin
      Result := True;
      Exit;
    end;
end;

{ Pede para o Stream Deck aberto fechar (POST /api/local/quit) e espera ate 15 s }
procedure FecharApp;
var
  Porta, I: Integer;
  Pediu: Boolean;
begin
  Pediu := False;
  for Porta := 8765 to 8767 do
    if Pedir('GET', Format('http://127.0.0.1:%d/api/local/hello', [Porta])) then
    begin
      Log(Format('Stream Deck aberto na porta %d, pedindo para fechar', [Porta]));
      Pedir('POST', Format('http://127.0.0.1:%d/api/local/quit', [Porta]));
      Pediu := True;
    end;
  if not Pediu then
    Exit;
  for I := 1 to 30 do
  begin
    if not AlgumRodando then
      Break;
    Sleep(500);
  end;
  { a porta fecha um pouco antes do processo sair e soltar os arquivos }
  Sleep(1500);
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  FecharApp;
  Result := '';
end;

function InitializeUninstall: Boolean;
begin
  FecharApp;
  Result := True;
end;

{ marcador lido pelo app (updates.install_kind): "esta pasta veio do instalador" }
procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
    if not SaveStringToFile(ExpandConstant('{app}\instalado.txt'),
        'Stream Deck {#MyAppVersion} instalado pelo instalador. Nao apague: a atualizacao automatica usa este arquivo.' + #13#10, False) then
      Log('aviso: nao gravou instalado.txt');
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  Valor: String;
begin
  { o proprio app pode ter ligado "iniciar com o Windows": remove se aponta para esta pasta
    (um StreamDeck.exe portatil em outra pasta continua iniciando) }
  if (CurUninstallStep = usUninstall) and
     RegQueryStringValue(HKEY_CURRENT_USER, RunKey, 'StreamDeck', Valor) and
     (Pos(Lowercase(ExpandConstant('{app}')), Lowercase(Valor)) > 0) then
    RegDeleteValue(HKEY_CURRENT_USER, RunKey, 'StreamDeck');
end;

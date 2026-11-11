; Instalador do Moleka PDV (Inno Setup 6).
; Uso, na raiz do repositório, depois do PyInstaller:
;   ISCC /DAppVersion=0.1.0 packaging\moleka.iss
; Instala só para o usuário atual (sem pedir senha de administrador) e não apaga os dados
; do sistema, que ficam em %APPDATA%\MolekaPDV.

#define AppName "Moleka PDV"
#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

[Setup]
AppId={{4BBD98A4-61B1-4EE2-BC8E-B4E21CEC63FF}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher=Moleka Sorvetes
DefaultDirName={autopf}\MolekaPDV
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
DisableDirPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\dist
OutputBaseFilename=MolekaPDV-Instalador-{#AppVersion}
SetupIconFile=..\assets\brand\moleka.ico
UninstallDisplayIcon={app}\MolekaPDV.exe
UninstallDisplayName={#AppName}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
; O sistema cria este mutex enquanto está aberto: o instalador pede para fechar antes de atualizar.
AppMutex=MolekaPDV_Aberto

[Languages]
Name: "ptbr"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Tasks]
Name: "atalhomesa"; Description: "Criar atalho na Área de Trabalho"; GroupDescription: "Atalhos:"

[Files]
Source: "..\dist\MolekaPDV\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
; Instalador do WebView2 (componente da Microsoft que desenha as telas). Só é usado se faltar.
Source: "..\build\MicrosoftEdgeWebview2Setup.exe"; DestDir: "{tmp}"; Flags: deleteafterinstall; Check: FaltaWebView2

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\MolekaPDV.exe"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\MolekaPDV.exe"; Tasks: atalhomesa

[Run]
Filename: "{tmp}\MicrosoftEdgeWebview2Setup.exe"; Parameters: "/silent /install"; StatusMsg: "Instalando o componente WebView2 da Microsoft (precisa de internet)..."; Flags: waituntilterminated; Check: FaltaWebView2
Filename: "{app}\MolekaPDV.exe"; Description: "Abrir o {#AppName} agora"; Flags: nowait postinstall skipifsilent

[Code]
function VersaoWebView2(Raiz: Integer; Chave: String): String;
begin
  Result := '';
  RegQueryStringValue(Raiz, Chave, 'pv', Result);
end;

function Vazia(Versao: String): Boolean;
begin
  Result := (Versao = '') or (Versao = '0.0.0.0');
end;

// Verdadeiro quando o WebView2 Runtime não está instalado (chaves da documentação da Microsoft).
function FaltaWebView2(): Boolean;
var
  Chave: String;
begin
  Chave := 'Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}';
  Result := Vazia(VersaoWebView2(HKLM32, 'SOFTWARE\' + Chave))
        and Vazia(VersaoWebView2(HKCU, 'Software\' + Chave));
  if Result and IsWin64 then
    Result := Vazia(VersaoWebView2(HKLM64, 'SOFTWARE\' + Chave));
end;

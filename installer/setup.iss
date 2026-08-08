; Inno Setup 6 script for Clipboard Translator
; Compile: ISCC /DMyAppVersion=0.2.0 setup.iss
; Expects PyInstaller onedir at ..\dist\app\

#ifndef MyAppVersion
  #define MyAppVersion "0.0.0"
#endif

#define MyAppName "Clipboard Translator"
#define MyAppPublisher "clipboard-translator"
#define MyAppURL "https://github.com/zhuji423/clipboard-translator"
#define MyAppExeName "ClipboardTranslator.exe"
#define MyAppNmHostName "ClipboardTranslatorNmHost.exe"
#define MyOnboardingURL "https://zhuji423.github.io/clipboard-translator/onboarding/"

[Setup]
AppId={{A8E6C2F1-4B3D-4E9A-9C1F-7D2E8B5A0C31}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}/releases
DefaultDirName={localappdata}\Programs\ClipboardTranslator
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=..\dist
OutputBaseFilename=ClipboardTranslator-{#MyAppVersion}-Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\{#MyAppExeName}
SetupIconFile=..\assets\app.ico
CloseApplications=yes
RestartApplications=no
SetupLogging=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional icons:"; Flags: unchecked
Name: "autostart"; Description: "Start {#MyAppName} when Windows starts"; GroupDescription: "Startup:"; Flags: unchecked
Name: "openextensionguide"; Description: "Open browser extension setup guide"; GroupDescription: "Browser extension:"; Flags: checkedonce

[Files]
Source: "..\dist\app\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon
Name: "{userstartup}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: autostart

[Registry]
; Native Messaging host (manifest written in [Code]; cleaned on uninstall)
Root: HKCU; Subkey: "Software\Google\Chrome\NativeMessagingHosts\com.clipboard_translator.bridge"; ValueType: string; ValueName: ""; ValueData: "{userappdata}\ClipboardTranslator\native_messaging\com.clipboard_translator.bridge.json"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Microsoft\Edge\NativeMessagingHosts\com.clipboard_translator.bridge"; ValueType: string; ValueName: ""; ValueData: "{userappdata}\ClipboardTranslator\native_messaging\com.clipboard_translator.bridge.json"; Flags: uninsdeletekey

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppName}"; Flags: nowait postinstall skipifsilent
Filename: "{#MyOnboardingURL}"; Description: "Open extension setup guide"; Flags: nowait postinstall shellexec skipifsilent; Tasks: openextensionguide

[Code]
procedure WriteNativeMessagingManifest();
var
  Dir, Path, HostPath, Content: String;
begin
  Dir := ExpandConstant('{userappdata}\ClipboardTranslator\native_messaging');
  ForceDirectories(Dir);
  Path := Dir + '\com.clipboard_translator.bridge.json';
  HostPath := ExpandConstant('{app}\{#MyAppNmHostName}');
  StringChangeEx(HostPath, '\', '\\', True);
  Content :=
    '{' + #13#10 +
    '  "name": "com.clipboard_translator.bridge",' + #13#10 +
    '  "description": "Clipboard Translator bridge credentials",' + #13#10 +
    '  "path": "' + HostPath + '",' + #13#10 +
    '  "type": "stdio",' + #13#10 +
    '  "allowed_origins": [' + #13#10 +
    '    "chrome-extension://oekjpiafgkdjacgpgacclehegnbaokmo/"' + #13#10 +
    '  ]' + #13#10 +
    '}' + #13#10;
  SaveStringToFile(Path, Content, False);
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
    WriteNativeMessagingManifest();
end;

[UninstallDelete]
; Leave %APPDATA%\ClipboardTranslator (config + history) intact on uninstall
Type: files; Name: "{userappdata}\ClipboardTranslator\native_messaging\com.clipboard_translator.bridge.json"

[Setup]
AppName=PO Scanner
AppVersion=2.0
AppPublisher=Inteplast
DefaultDirName={sd}\PO Scanner
DefaultGroupName=PO Scanner
OutputDir=dist
OutputBaseFilename=PO_Scanner_Setup
SetupIconFile=PO Scanner.ico
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin
DisableDirPage=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional icons:"

[Dirs]
Name: "{app}\Template"
Name: "{app}\Template\CSV"

[Files]
; Main app (po_scanner.exe, settings.exe, config/, etc.)
Source: "dist\po_scanner\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

; OCR runtime
Source: "dist\ocr_runtime\*"; DestDir: "{app}\ocr_runtime"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\PO Scanner";           Filename: "{app}\po_scanner.exe"; IconFilename: "{app}\po_scanner.exe"
Name: "{group}\PO Scanner Settings";  Filename: "{app}\settings.exe";   IconFilename: "{app}\settings.exe"
Name: "{group}\Uninstall PO Scanner"; Filename: "{uninstallexe}"
Name: "{autodesktop}\PO Scanner";     Filename: "{app}\po_scanner.exe"; IconFilename: "{app}\po_scanner.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\po_scanner.exe"; Description: "Launch PO Scanner"; Flags: nowait postinstall skipifsilent unchecked

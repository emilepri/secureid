; Installateur Windows de SecureID (Inno Setup 6).
; Construit automatiquement par .github/workflows/windows-installer.yml,
; ou à la main : ISCC.exe /DAppVersion=1.0.0 installer\secureid.iss (après build.bat).

#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif

[Setup]
AppId={{8F3C2A51-7B6E-4D2A-9C1F-5E2B7A9D4C10}
AppName=SecureID
AppVersion={#AppVersion}
AppPublisher=Emile Abdoulaye PRISO
AppPublisherURL=https://emilepri.github.io/secureid/
AppSupportURL=https://github.com/emilepri/secureid
DefaultDirName={autopf}\SecureID
DefaultGroupName=SecureID
DisableProgramGroupPage=yes
; Installation pour l'utilisateur courant : pas besoin de droits administrateur
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputDir=..\dist\installer
OutputBaseFilename=SecureID-Setup-{#AppVersion}
SetupIconFile=..\assets\emission.ico
UninstallDisplayIcon={app}\Emission\SecureID-Emission.exe
UninstallDisplayName=SecureID
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
LicenseFile=..\LICENSE

[Languages]
Name: "french"; MessagesFile: "compiler:Languages\French.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "..\dist\SecureID-Emission\*"; DestDir: "{app}\Emission"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\dist\SecureID-Verification\*"; DestDir: "{app}\Verification"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\SecureID Émission"; Filename: "{app}\Emission\SecureID-Emission.exe"
Name: "{group}\SecureID Vérification"; Filename: "{app}\Verification\SecureID-Verification.exe"
Name: "{group}\Dossier des données SecureID"; Filename: "{%USERPROFILE}\SecureID"
Name: "{group}\Désinstaller SecureID"; Filename: "{uninstallexe}"
Name: "{autodesktop}\SecureID Émission"; Filename: "{app}\Emission\SecureID-Emission.exe"; Tasks: desktopicon
Name: "{autodesktop}\SecureID Vérification"; Filename: "{app}\Verification\SecureID-Verification.exe"; Tasks: desktopicon

[Dirs]
; Les données (clé, base, PDF) vivent ici et NE sont PAS supprimées à la désinstallation
Name: "{%USERPROFILE}\SecureID"; Flags: uninsneveruninstall

[Run]
Filename: "{app}\Emission\SecureID-Emission.exe"; Description: "Lancer SecureID Émission"; Flags: nowait postinstall skipifsilent

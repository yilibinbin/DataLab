#define AppName "DataLab"
#define AppVersion GetEnv("DATALAB_APP_VERSION")
#define SourceDir GetEnv("DATALAB_WINDOWS_DIST_DIR")
#define OutputDir GetEnv("DATALAB_WINDOWS_INSTALLER_DIR")

[Setup]
AppId={{E1A55165-87D3-4D80-B9E8-59D80160C3F9}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=DataLab Contributors
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
OutputDir={#OutputDir}
OutputBaseFilename=DataLab-{#AppVersion}-Windows-x64
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=admin
CloseApplications=yes
RestartApplications=no
SetupLogging=yes
UninstallDisplayIcon={app}\DataLab.exe

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\DataLab.exe"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\DataLab.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\DataLab.exe"; Description: "{cm:LaunchProgram,{#StringChange(AppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

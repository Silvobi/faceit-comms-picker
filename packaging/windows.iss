#ifndef AppVersion
  #error AppVersion is required
#endif
#ifndef ProjectRoot
  #define ProjectRoot ".."
#endif

[Setup]
AppId=Silvobi.FACEITCommsPicker
AppName=FACEIT Comms Picker
AppVersion={#AppVersion}
AppPublisher=Silvobi
AppPublisherURL=https://github.com/Silvobi/faceit-comms-picker
DefaultDirName={localappdata}\Programs\FACEIT Comms Picker
DefaultGroupName=FACEIT Comms Picker
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputDir={#ProjectRoot}\dist\packages
OutputBaseFilename=FACEIT-Comms-Picker-{#AppVersion}-windows-x64-Setup
SetupIconFile={#ProjectRoot}\assets\faceit-comms-picker.ico
UninstallDisplayIcon={app}\FACEIT-Comms-Picker.exe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
RestartApplications=no

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Shortcuts:"; Flags: unchecked

[Files]
Source: "{#ProjectRoot}\dist\FACEIT-Comms-Picker\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{userprograms}\FACEIT Comms Picker"; Filename: "{app}\FACEIT-Comms-Picker.exe"; WorkingDir: "{app}"
Name: "{userdesktop}\FACEIT Comms Picker"; Filename: "{app}\FACEIT-Comms-Picker.exe"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\FACEIT-Comms-Picker.exe"; Description: "Launch FACEIT Comms Picker"; Flags: nowait postinstall skipifsilent

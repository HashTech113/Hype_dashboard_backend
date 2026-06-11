; =====================================================================
;  AI Camera Surveillance — Inno Setup installer script
;  Builds a single Setup.exe that:
;    1. Installs portable Python 3.11 + venv + all backend deps
;    2. Installs portable Node.js + frontend node_modules + built .next
;    3. (Optional) Installs PostgreSQL 16 (or assumes one is present)
;    4. Registers backend + frontend as Windows Services via NSSM
;    5. Drops a Start-menu shortcut that opens http://localhost:3000
;
;  Build prerequisites on the build machine (not the target machine):
;    - Inno Setup 6.x (https://jrsoftware.org/isdl.php)
;    - Bundle assets staged into ./assets/ (see README.md in this dir)
;    - Backend prebuilt: backend/.venv exists, requirements installed
;    - Frontend prebuilt: frontend/.next exists (npm run build)
;
;  How to build:
;    1. Run ./deploy/installer/stage-assets.ps1 to copy runtimes/code
;       into ./deploy/installer/assets/
;    2. Open this .iss in Inno Setup Compiler
;    3. Build → output is ./deploy/installer/output/Setup.exe
;
;  How an end user installs:
;    1. Double-click Setup.exe (right-click → Run as Administrator)
;    2. Pick an install folder (default C:\AICameraSurveillance)
;    3. Click Install — installer copies files + starts services
;    4. Browser opens to http://localhost:3000
;    5. Default admin/ChangeMe@123 — system prompts to rotate
;
; =====================================================================

#define MyAppName "AI Camera Surveillance"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "HashTech"
#define MyAppURL "https://github.com/HashTech113/ai-camera-attendance-system"
#define MyAppExeName "open-dashboard.cmd"

[Setup]
AppId={A1F2C3D4-5E6B-7A8C-9DEF-0123456789AB}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
DefaultDirName=C:\AICameraSurveillance
DefaultGroupName=AI Camera Surveillance
DisableProgramGroupPage=yes
PrivilegesRequired=admin
OutputBaseFilename=AICameraSurveillance-Setup-{#MyAppVersion}
OutputDir=output
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
UninstallDisplayName={#MyAppName}
; ARM64 support — keep x64 for now (InsightFace wheels)
ArchitecturesAllowed=x64
ArchitecturesInstallIn64BitMode=x64

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create desktop shortcut"; GroupDescription: "Shortcuts"

[Files]
; --- Backend ---------------------------------------------------------
; Assumes stage-assets.ps1 has copied:
;   assets/backend/app/      (Python sources)
;   assets/backend/.venv/    (full virtualenv with all packages)
;   assets/backend/migrations/
;   assets/backend/storage/models/  (InsightFace buffalo_l ~340MB)
;   assets/backend/alembic.ini
;   assets/backend/.env.template
Source: "assets\backend\*"; DestDir: "{app}\backend"; Flags: ignoreversion recursesubdirs createallsubdirs

; --- Frontend (built) -----------------------------------------------
; Assumes stage-assets.ps1 has run `npm run build` then copied:
;   assets/frontend/.next/         (built artifact)
;   assets/frontend/node_modules/  (production deps only — npm ci --omit=dev)
;   assets/frontend/package.json
;   assets/frontend/next.config.mjs
;   assets/frontend/public/
Source: "assets\frontend\*"; DestDir: "{app}\frontend"; Flags: ignoreversion recursesubdirs createallsubdirs

; --- Portable Node.js -----------------------------------------------
; Download node-v22.x.x-win-x64.zip, extract, copy here as assets/node/
Source: "assets\node\*"; DestDir: "{app}\node"; Flags: ignoreversion recursesubdirs createallsubdirs

; --- NSSM ----------------------------------------------------------
Source: "assets\nssm\nssm.exe"; DestDir: "{app}\bin"; Flags: ignoreversion

; --- Prerequisites: bundled Postgres + VC++ Redistributable --------
; Copied to a temp location so they can be silent-installed by the
; [Run] section below, then deleted. With these bundled, the end-user
; has ZERO manual prerequisites — Setup.exe really is a one-click install.
Source: "assets\prereqs\postgresql-installer.exe"; DestDir: "{tmp}"; Flags: deleteafterinstall
Source: "assets\prereqs\vc_redist.x64.exe"; DestDir: "{tmp}"; Flags: deleteafterinstall

; --- Native-app launcher (PS1 + VBS wrapper + icon) -----------------
; Double-clicking AISurveillance.vbs runs AISurveillance.ps1 silently
; (no console window), which detects Edge/Chrome and opens the dashboard
; in --app=mode — chromeless window, custom icon, looks like a native
; Windows desktop app rather than a tab in your browser.
Source: "scripts\AISurveillance.ps1"; DestDir: "{app}"; Flags: ignoreversion
Source: "scripts\AISurveillance.vbs"; DestDir: "{app}"; Flags: ignoreversion
Source: "scripts\app-icon.ico"; DestDir: "{app}"; Flags: ignoreversion

; --- Operator helper scripts ---------------------------------------
Source: "scripts\open-dashboard.cmd"; DestDir: "{app}"; Flags: ignoreversion
Source: "scripts\start-services.cmd"; DestDir: "{app}\bin"; Flags: ignoreversion
Source: "scripts\stop-services.cmd"; DestDir: "{app}\bin"; Flags: ignoreversion
Source: "scripts\.env.example"; DestDir: "{app}\backend"; Flags: ignoreversion onlyifdoesntexist; DestName: ".env"
Source: "scripts\.env.local.example"; DestDir: "{app}\frontend"; Flags: ignoreversion onlyifdoesntexist; DestName: ".env.local"

[Dirs]
Name: "{app}\logs"; Permissions: users-modify
Name: "{app}\backend\storage\snapshots"; Permissions: users-modify
Name: "{app}\backend\storage\training_images"; Permissions: users-modify
Name: "{app}\backend\storage\unknowns"; Permissions: users-modify

[Icons]
; Primary desktop + Start Menu shortcut — looks/feels like a native app.
; Targets the VBS launcher so no console window flashes when the user
; double-clicks the icon. The .ico file gives our branding in:
;   * the taskbar pin
;   * the title bar
;   * Alt+Tab thumbnail
;   * Start Menu tile
Name: "{group}\AI Camera Surveillance"; \
    Filename: "{app}\AISurveillance.vbs"; \
    WorkingDir: "{app}"; \
    IconFilename: "{app}\app-icon.ico"; \
    Comment: "Open the AI Camera Surveillance dashboard"
Name: "{commondesktop}\AI Camera Surveillance"; \
    Filename: "{app}\AISurveillance.vbs"; \
    WorkingDir: "{app}"; \
    IconFilename: "{app}\app-icon.ico"; \
    Comment: "Open the AI Camera Surveillance dashboard"; \
    Tasks: desktopicon

; Secondary maintenance shortcuts (Start Menu only)
Name: "{group}\Stop services"; Filename: "{app}\bin\stop-services.cmd"; WorkingDir: "{app}"
Name: "{group}\Start services"; Filename: "{app}\bin\start-services.cmd"; WorkingDir: "{app}"
Name: "{group}\Open in browser (debug)"; Filename: "http://localhost:3000"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"

[Run]
; ===== Prerequisite silent installs (run FIRST) =====================
; The end-user never sees these wizards — they install in the
; background while our progress bar advances. Postgres skip is OK if
; it's already on the machine (StatusMsg picks that up).

; 1. Visual C++ 2015-2022 redistributable (needed by OpenCV/ONNX wheels)
;    /quiet = no UI; /norestart = don't reboot. Returns 0 if installed
;    or if already present (so it's idempotent).
Filename: "{tmp}\vc_redist.x64.exe"; Parameters: "/install /quiet /norestart"; Flags: waituntilterminated runhidden; StatusMsg: "Installing Visual C++ runtime…"; Check: NeedsVcRedist

; 2. PostgreSQL 16 silent install. Password is the auto-generated
;    one from [Code] section below (AppPostgresPassword). The :pgpwd:
;    placeholder gets replaced at runtime via a code function.
;    --servicename uses a unique name so we don't collide with any
;    pre-existing PG. --serverport=55432 avoids port 5432 conflicts.
Filename: "{tmp}\postgresql-installer.exe"; Parameters: "--mode unattended --unattendedmodeui none --superpassword {code:GetPostgresPassword} --serverport 55432 --servicename ai-camera-postgres --servicepassword {code:GetPostgresPassword} --serviceaccount NetworkService --prefix ""{app}\postgres"" --datadir ""{app}\postgres\data"""; Flags: waituntilterminated runhidden; StatusMsg: "Installing PostgreSQL (this is the slow step, ~90s)…"; Check: NeedsPostgres

; 3. Write the DATABASE_URL into .env now that we know the PG password.
;    JWT_SECRET_KEY is auto-generated by the backend on first boot
;    (config.py:_auto_jwt_secret), so we don't need to touch it here.
Filename: "{cmd}"; Parameters: "/C echo DATABASE_URL=postgresql+psycopg2://postgres:{code:GetPostgresPassword}@127.0.0.1:55432/ai_attendance >> ""{app}\backend\.env"""; Flags: runhidden waituntilterminated; StatusMsg: "Configuring database connection…"

; ===== App bootstrap (DB auto-create + migrations now happen on
; first uvicorn boot via config.py + main.py, so we no longer need
; the manual alembic step here — the service start below triggers it).

Filename: "{app}\bin\nssm.exe"; Parameters: "install AISurveillanceBackend ""{app}\backend\.venv\Scripts\python.exe"" -m uvicorn app.main:app --host 127.0.0.1 --port 8000"; Flags: runhidden waituntilterminated; Description: "Register backend service"; StatusMsg: "Registering backend service…"
Filename: "{app}\bin\nssm.exe"; Parameters: "set AISurveillanceBackend AppDirectory ""{app}\backend"""; Flags: runhidden waituntilterminated
Filename: "{app}\bin\nssm.exe"; Parameters: "set AISurveillanceBackend Start SERVICE_AUTO_START"; Flags: runhidden waituntilterminated
Filename: "{app}\bin\nssm.exe"; Parameters: "set AISurveillanceBackend AppStdout ""{app}\logs\backend.log"""; Flags: runhidden waituntilterminated
Filename: "{app}\bin\nssm.exe"; Parameters: "set AISurveillanceBackend AppStderr ""{app}\logs\backend.log"""; Flags: runhidden waituntilterminated
Filename: "{app}\bin\nssm.exe"; Parameters: "set AISurveillanceBackend AppExit Default Restart"; Flags: runhidden waituntilterminated

Filename: "{app}\bin\nssm.exe"; Parameters: "install AISurveillanceFrontend ""{app}\node\node.exe"" ""{app}\frontend\node_modules\next\dist\bin\next"" start --port 3000 --hostname 127.0.0.1"; Flags: runhidden waituntilterminated; Description: "Register frontend service"; StatusMsg: "Registering frontend service…"
Filename: "{app}\bin\nssm.exe"; Parameters: "set AISurveillanceFrontend AppDirectory ""{app}\frontend"""; Flags: runhidden waituntilterminated
Filename: "{app}\bin\nssm.exe"; Parameters: "set AISurveillanceFrontend Start SERVICE_AUTO_START"; Flags: runhidden waituntilterminated
Filename: "{app}\bin\nssm.exe"; Parameters: "set AISurveillanceFrontend DependOnService AISurveillanceBackend"; Flags: runhidden waituntilterminated
Filename: "{app}\bin\nssm.exe"; Parameters: "set AISurveillanceFrontend AppStdout ""{app}\logs\frontend.log"""; Flags: runhidden waituntilterminated
Filename: "{app}\bin\nssm.exe"; Parameters: "set AISurveillanceFrontend AppStderr ""{app}\logs\frontend.log"""; Flags: runhidden waituntilterminated

Filename: "net.exe"; Parameters: "start AISurveillanceBackend"; Flags: runhidden waituntilterminated; StatusMsg: "Starting backend…"
Filename: "net.exe"; Parameters: "start AISurveillanceFrontend"; Flags: runhidden waituntilterminated; StatusMsg: "Starting frontend…"

; Open the dashboard for the operator
Filename: "http://localhost:3000"; Flags: shellexec postinstall nowait; Description: "Open dashboard now"

[UninstallRun]
Filename: "net.exe"; Parameters: "stop AISurveillanceFrontend"; Flags: runhidden waituntilterminated; RunOnceId: "stopfe"
Filename: "net.exe"; Parameters: "stop AISurveillanceBackend"; Flags: runhidden waituntilterminated; RunOnceId: "stopbe"
Filename: "{app}\bin\nssm.exe"; Parameters: "remove AISurveillanceFrontend confirm"; Flags: runhidden waituntilterminated; RunOnceId: "rmfe"
Filename: "{app}\bin\nssm.exe"; Parameters: "remove AISurveillanceBackend confirm"; Flags: runhidden waituntilterminated; RunOnceId: "rmbe"
; Stop + unregister the bundled PostgreSQL service so its data directory
; isn't held open by postgres.exe when we try to delete it below.
Filename: "net.exe"; Parameters: "stop ai-camera-postgres"; Flags: runhidden waituntilterminated; RunOnceId: "stoppg"
Filename: "sc.exe"; Parameters: "delete ai-camera-postgres"; Flags: runhidden waituntilterminated; RunOnceId: "rmpg"

[UninstallDelete]
Type: filesandordirs; Name: "{app}\logs"
; PostgreSQL data directory (500+ MB) — deleted only if the operator
; confirmed at the start of uninstall that they want to wipe biometric
; data. The decision is made in InitializeUninstall() and gated by
; ShouldDeletePostgresData(). When kept, the directory is left intact
; so a future reinstall can reuse the existing ai_attendance database.
Type: filesandordirs; Name: "{app}\postgres\data"; Check: ShouldDeletePostgresData
; Backend storage (snapshots, training images, unknowns, face embeddings)
; is also biometric data, so it's gated by the same prompt.
Type: filesandordirs; Name: "{app}\backend\storage"; Check: ShouldDeletePostgresData

[Code]
// ============================================================
//  Postgres password lifecycle + prerequisite detection
// ============================================================
//  We generate a per-install random Postgres superuser password at
//  install time, persist it in the registry so the uninstaller can
//  read it back, and write it into the backend's .env DATABASE_URL.
//  The end-user never has to know or type this password.
// ============================================================

var
  PostgresPassword: string;
  DeletePostgresData: Boolean;

// Generate a 24-char ASCII password using GetTickCount + the OS PRNG.
// Pascal-Script can't import secrets.token_urlsafe, so we mix in time
// + Random for entropy. For an internal service password (never
// exposed to the network — PG is bound to 127.0.0.1) this is fine.
function GenerateRandomPassword(): string;
var
  alphabet: string;
  i: Integer;
  pwd: string;
begin
  alphabet := 'ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789';
  pwd := '';
  // Seed Random from the system tick count
  Randomize();
  for i := 1 to 24 do
    pwd := pwd + alphabet[Random(Length(alphabet)) + 1];
  Result := pwd;
end;

// Called the first time the installer needs the password. We persist
// it under HKLM so the uninstall path (and any future repair install)
// can read it back. If a prior install already has one, we reuse it.
function GetPostgresPassword(Param: string): string;
var
  Existing: string;
begin
  if PostgresPassword = '' then
  begin
    if RegQueryStringValue(HKEY_LOCAL_MACHINE,
        'SOFTWARE\HashTech\AICameraSurveillance',
        'PostgresPassword', Existing) then
    begin
      PostgresPassword := Existing;
    end
    else
    begin
      PostgresPassword := GenerateRandomPassword();
      RegWriteStringValue(HKEY_LOCAL_MACHINE,
        'SOFTWARE\HashTech\AICameraSurveillance',
        'PostgresPassword', PostgresPassword);
    end;
  end;
  Result := PostgresPassword;
end;

// Decide whether to run the VC++ silent install. Microsoft's
// redistributable writes a value to HKLM\Software\Microsoft\VisualStudio\14.0\VC\Runtimes\x64
// when present. If that's there with version >= 14, we skip.
function NeedsVcRedist(): Boolean;
var
  Installed: Cardinal;
begin
  if RegQueryDWordValue(HKEY_LOCAL_MACHINE,
      'SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\x64',
      'Installed', Installed) then
    Result := (Installed = 0)
  else
    Result := True;
end;

// Decide whether to run the Postgres silent install. We look for our
// previous install's bin dir; if pg_ctl.exe is there, skip.
function NeedsPostgres(): Boolean;
begin
  Result := not FileExists(ExpandConstant('{app}\postgres\bin\pg_ctl.exe'));
end;

// ============================================================
//  Uninstall-time biometric-data prompt
// ============================================================
//  When the operator uninstalls, the PostgreSQL data directory under
//  {app}\postgres\data and the {app}\backend\storage folder together
//  hold ALL biometric data: face embeddings, training images, snapshots,
//  attendance history, employee records. By default we keep them (the
//  operator may need them for compliance / re-install). If the operator
//  picks "Yes" at the prompt, we wipe everything. The decision is
//  captured here in DeletePostgresData and read back by
//  ShouldDeletePostgresData() from the [UninstallDelete] Check clause.
// ============================================================

function InitializeUninstall(): Boolean;
var
  Response: Integer;
begin
  Response := MsgBox(
    'Do you also want to DELETE all biometric data, attendance history, ' +
    'face embeddings, snapshots, and the ai_attendance database?' + #13#10 + #13#10 +
    'Click YES to permanently delete the PostgreSQL data directory and ' +
    'all stored images. This cannot be undone.' + #13#10 + #13#10 +
    'Click NO to keep the data (recommended for compliance / future ' +
    'reinstall). The PostgreSQL data directory under "postgres\data" ' +
    'and the "backend\storage" folder will be preserved.',
    mbConfirmation, MB_YESNO or MB_DEFBUTTON2);
  DeletePostgresData := (Response = IDYES);
  Result := True;
end;

function ShouldDeletePostgresData(): Boolean;
begin
  Result := DeletePostgresData;
end;

// Save the install dir + Postgres port to the registry on the very
// first page so the uninstaller can find them later, even if the user
// moved {app}.
procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
  begin
    RegWriteStringValue(HKEY_LOCAL_MACHINE,
      'SOFTWARE\HashTech\AICameraSurveillance',
      'InstallDir', ExpandConstant('{app}'));
    RegWriteStringValue(HKEY_LOCAL_MACHINE,
      'SOFTWARE\HashTech\AICameraSurveillance',
      'PostgresPort', '55432');
  end;
end;

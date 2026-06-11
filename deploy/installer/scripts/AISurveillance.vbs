' AI Camera Surveillance — silent launcher
'
' Runs AISurveillance.ps1 with NO visible console window. The desktop
' shortcut targets this .vbs file so when the user double-clicks the
' icon, they don't see a black PowerShell window flash before the app
' opens. The Windows shell ASsociates .vbs with wscript.exe by default,
' which runs scripts without a console.

Dim shell, scriptDir, ps1Path
Set shell = CreateObject("WScript.Shell")
scriptDir = CreateObject("Scripting.FileSystemObject").GetParentFolderName(WScript.ScriptFullName)
ps1Path = scriptDir & "\AISurveillance.ps1"

' 0 = SW_HIDE  — don't show the PowerShell window at all
' False = don't wait — return immediately; the PS1 manages its own lifetime
shell.Run "powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File """ & ps1Path & """", 0, False

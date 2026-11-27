' Doppelklick-Starter fuer die Tametsi-GUI.
' Startet gui.py mit pythonw (ohne Konsolenfenster) im Ordner dieser Datei.
Option Explicit

Dim shell, fso, scriptDir, pyexe, target

Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

scriptDir = fso.GetParentFolderName(WScript.ScriptFullName)
target = scriptDir & "\gui.py"

If Not fso.FileExists(target) Then
  MsgBox "gui.py wurde nicht gefunden neben dieser Datei:" & vbCrLf & target, _
         vbCritical, "Tametsi Level Generator"
  WScript.Quit 1
End If

' pythonw.exe (kein Konsolenfenster); faellt auf den py-Launcher pyw.exe zurueck.
pyexe = "pythonw.exe"

shell.CurrentDirectory = scriptDir

On Error Resume Next
shell.Run """" & pyexe & """ """ & target & """", 0, False
If Err.Number <> 0 Then
  Err.Clear
  shell.Run "pyw.exe """ & target & """", 0, False
  If Err.Number <> 0 Then
    MsgBox "Python (pythonw) konnte nicht gestartet werden." & vbCrLf & _
           "Bitte Python installieren oder zum PATH hinzufuegen.", _
           vbCritical, "Tametsi Level Generator"
  End If
End If
On Error Goto 0

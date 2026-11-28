' Double-click launcher for the Tametsi GUI.
' Starts gui.py with pythonw (no console window) in this file's folder.
Option Explicit

Dim shell, fso, scriptDir, pyexe, target

Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

scriptDir = fso.GetParentFolderName(WScript.ScriptFullName)
target = scriptDir & "\gui.py"

If Not fso.FileExists(target) Then
  MsgBox "gui.py was not found next to this file:" & vbCrLf & target, _
         vbCritical, "Tametsi Level Generator"
  WScript.Quit 1
End If

' pythonw.exe (no console window); falls back to the py launcher pyw.exe.
pyexe = "pythonw.exe"

shell.CurrentDirectory = scriptDir

On Error Resume Next
shell.Run """" & pyexe & """ """ & target & """", 0, False
If Err.Number <> 0 Then
  Err.Clear
  shell.Run "pyw.exe """ & target & """", 0, False
  If Err.Number <> 0 Then
    MsgBox "Python (pythonw) could not be started." & vbCrLf & _
           "Please install Python or add it to PATH.", _
           vbCritical, "Tametsi Level Generator"
  End If
End If
On Error Goto 0

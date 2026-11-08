@echo off
chcp 65001 >nul
cd /d "%~dp0"
set "SCRIPT=%~dp0sensor_color_tool.py"

rem Pick a Python that actually ships tkinter (the bundled portable one does not).
for %%V in (3.10 3.12 3.11 3.13 3) do (
  py -%%V -c "import tkinter" >nul 2>nul
  if not errorlevel 1 (
    start "" pyw -%%V "%SCRIPT%"
    exit /b 0
  )
)

rem Fallback: common Python/conda installs without hard-coded user paths.
for %%V in (313 312 311 310) do (
  if exist "%LOCALAPPDATA%\Programs\Python\Python%%V\pythonw.exe" (
    start "" "%LOCALAPPDATA%\Programs\Python\Python%%V\pythonw.exe" "%SCRIPT%"
    exit /b 0
  )
)
for %%D in (C D E F G) do (
  if exist "%%D:\anaconda3\pythonw.exe" (
    start "" "%%D:\anaconda3\pythonw.exe" "%SCRIPT%"
    exit /b 0
  )
)

echo Python 3 with tkinter is required but was not found.
echo Install Python 3 from python.org with the "tcl/tk and IDLE" option enabled.
pause

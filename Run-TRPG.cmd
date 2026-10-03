@echo off
wsl.exe --cd "%~dp0." --exec bash ./trpg %*
set "trpg_exit=%errorlevel%"
pause
exit /b %trpg_exit%

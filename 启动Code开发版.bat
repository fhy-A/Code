@echo off
setlocal
cd /d "%~dp0"

set "CODE_DEV_PORT=3011"
set "DEV_URL=http://127.0.0.1:%CODE_DEV_PORT%"

REM Reuse the existing Code Dev service only when port 3011 belongs to this repo.
netstat -ano 2>nul | find ":%CODE_DEV_PORT% " | find "LISTENING" >nul
if errorlevel 1 goto :start_server

powershell -NoProfile -Command "try {$r=Invoke-RestMethod -Uri '%DEV_URL%/api/version' -TimeoutSec 2; $expected=[IO.Path]::GetFullPath('%~dp0').TrimEnd('\'); $actual=[IO.Path]::GetFullPath($r.appDir).TrimEnd('\'); if ($r.name -eq 'Code' -and $actual -eq $expected) {exit 0} else {exit 1}} catch {exit 1}" >nul 2>&1
if errorlevel 1 goto :port_conflict

powershell -NoProfile -Command "try {$r=Invoke-RestMethod -Uri '%DEV_URL%/api/has-browser' -TimeoutSec 2; if ($r.hasBrowser) {exit 0} else {exit 1}} catch {exit 1}" >nul 2>&1
if errorlevel 1 goto :open_existing_service
powershell -NoProfile -Command "try {Invoke-WebRequest -Uri '%DEV_URL%/api/request-browser-refresh' -TimeoutSec 2 -UseBasicParsing | Out-Null; exit 0} catch {exit 1}" >nul 2>&1
if errorlevel 1 goto :open_existing_service
goto :eof

:open_existing_service
start "" "%DEV_URL%"
goto :eof

:port_conflict
echo Code Dev cannot start: port %CODE_DEV_PORT% is used by another service.
pause
goto :eof

:start_server

REM Find Python (prefer pythonw so the development tray controls the process).
set "PY="
where pythonw >nul 2>nul && set "PY=pythonw"
if not defined PY where python >nul 2>nul && set "PY=python"
if not defined PY (
  echo Python not found. Please install Python first.
  pause
  goto :eof
)

start "Code Dev" /B %PY% dev_server.py

set RETRY=0
:wait
timeout /t 1 /nobreak >nul
powershell -NoProfile -Command "try {$r=Invoke-WebRequest -Uri '%DEV_URL%' -TimeoutSec 1 -UseBasicParsing; exit 0} catch {exit 1}" >nul 2>&1 && goto :open
set /a RETRY+=1
if %RETRY% LSS 30 goto :wait
echo Code Dev did not become ready within 30 seconds.
goto :eof

:open
REM Give an existing development page time to reconnect after a tray restart.
set PAGE_RETRY=0
:wait_page
timeout /t 1 /nobreak >nul
powershell -NoProfile -Command "try {$r=Invoke-RestMethod -Uri '%DEV_URL%/api/has-browser' -TimeoutSec 1; if ($r.hasBrowser) {exit 0} else {exit 1}} catch {exit 1}" >nul 2>&1 && goto :page_connected
set /a PAGE_RETRY+=1
if %PAGE_RETRY% LSS 5 goto :wait_page

start "" "%DEV_URL%"
goto :eof

:page_connected
goto :eof

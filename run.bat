@echo off
REM Khoi dong Game Hub. Server se in ra dia chi de chia se.
cd /d "%~dp0"

python -c "import fastapi, uvicorn, websockets, PIL, multipart" 2>nul
if errorlevel 1 (
  echo Thieu thu vien. Dang cai...
  python -m pip install -r requirements.txt || goto :fail
)

start "" http://127.0.0.1:8780
python server.py
goto :eof

:fail
echo.
echo Cai dat that bai. Chay thu cong: python -m pip install -r requirements.txt
pause

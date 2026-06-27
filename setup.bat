@echo off
echo ================================================
echo  PageCap - Setup (Windows)
echo ================================================

:: Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERRO] Python nao encontrado. Instale Python 3.10+ de https://python.org
    pause
    exit /b 1
)

:: Check Node.js
node --version >nul 2>&1
if errorlevel 1 (
    echo [ERRO] Node.js nao encontrado. Instale Node.js 18+ de https://nodejs.org
    pause
    exit /b 1
)

echo.
echo [1/4] Instalando dependencias Python...
cd engine
pip install -r requirements.txt
if errorlevel 1 ( echo [ERRO] Falha ao instalar dependencias Python && pause && exit /b 1 )

echo.
echo [2/4] Instalando Playwright (Chromium)...
playwright install chromium
if errorlevel 1 ( echo [AVISO] Playwright install falhou - verifique manualmente )

cd ..

echo.
echo [3/4] Instalando dependencias Node.js...
npm install
if errorlevel 1 ( echo [ERRO] Falha ao instalar dependencias Node && pause && exit /b 1 )

echo.
echo [4/4] Construindo pacote TypeScript core...
npm run build --workspace=packages/core

echo.
echo ================================================
echo  Setup concluido!
echo.
echo  Para rodar a interface WEB:
echo    npm run dev:web
echo    (abra http://localhost:5173 no browser)
echo.
echo  Para rodar o app DESKTOP (Electron):
echo    npm run dev
echo.
echo  Para usar o CLI:
echo    cd engine
echo    python cli.py --help
echo    python cli.py https://exemplo.com --type all
echo ================================================
pause

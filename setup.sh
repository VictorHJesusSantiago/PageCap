#!/usr/bin/env bash
set -e

echo "================================================"
echo " PageCap - Setup (Linux/macOS)"
echo "================================================"

# Check Python
if ! command -v python3 &>/dev/null; then
  echo "[ERRO] Python3 não encontrado. Instale Python 3.10+."
  exit 1
fi

# Check Node.js
if ! command -v node &>/dev/null; then
  echo "[ERRO] Node.js não encontrado. Instale Node.js 18+."
  exit 1
fi

echo ""
echo "[1/4] Instalando dependências Python..."
cd engine
pip3 install -r requirements.txt

echo ""
echo "[2/4] Instalando Playwright (Chromium)..."
playwright install chromium || echo "[AVISO] playwright install falhou — verifique manualmente"

cd ..

echo ""
echo "[3/4] Instalando dependências Node.js..."
npm install

echo ""
echo "[4/4] Construindo pacote TypeScript core..."
npm run build --workspace=packages/core

echo ""
echo "================================================"
echo " Setup concluído!"
echo ""
echo " Interface WEB:        npm run dev:web"
echo "                       http://localhost:5173"
echo ""
echo " App DESKTOP:          npm run dev"
echo ""
echo " CLI:                  cd engine && python3 cli.py --help"
echo "================================================"

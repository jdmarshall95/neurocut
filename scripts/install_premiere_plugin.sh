#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SOURCE_DIR="${ROOT_DIR}/premiere/NeuroCut"

if [[ ! -d "${SOURCE_DIR}/CSXS" ]]; then
  echo "Extension source not found: ${SOURCE_DIR}" >&2
  exit 1
fi

OS_NAME="$(uname -s)"
case "${OS_NAME}" in
  Darwin)
    TARGET_DIR="${HOME}/Library/Application Support/Adobe/CEP/extensions/NeuroCut"
    ;;
  Linux)
    TARGET_DIR="${HOME}/.config/Adobe/CEP/extensions/NeuroCut"
    ;;
  MINGW*|MSYS*|CYGWIN*)
    TARGET_DIR="${APPDATA}/Adobe/CEP/extensions/NeuroCut"
    ;;
  *)
    echo "Unsupported OS: ${OS_NAME}" >&2
    exit 1
    ;;
esac

mkdir -p "$(dirname "${TARGET_DIR}")"
rm -rf "${TARGET_DIR}"
cp -R "${SOURCE_DIR}" "${TARGET_DIR}"

echo "Installed NeuroCut CEP extension to:"
echo "  ${TARGET_DIR}"
echo
echo "Enable unsigned extensions (one-time, per OS):"
echo "  macOS:"
echo "    defaults write com.adobe.CSXS.11 PlayerDebugMode 1"
echo "    defaults write com.adobe.CSXS.12 PlayerDebugMode 1"
echo "  Windows (PowerShell as admin):"
echo "    reg add HKCU\\Software\\Adobe\\CSXS.11 /v PlayerDebugMode /t REG_SZ /d 1 /f"
echo "    reg add HKCU\\Software\\Adobe\\CSXS.12 /v PlayerDebugMode /t REG_SZ /d 1 /f"
echo
echo "Restart Premiere Pro, then open: Window > Extensions > NeuroCut"
echo "API server (local): http://127.0.0.1:8000"
echo "Set PLUGIN_ALLOW_ANY_LOCAL_PATH=true in .env for development."

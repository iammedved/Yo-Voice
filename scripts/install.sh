#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "→ виртуальное окружение"
python3 -m venv --without-pip --system-site-packages "$ROOT/.venv"
if [[ -f "$ROOT/.venv/pyvenv.cfg" ]]; then
  sed -i 's/include-system-site-packages = false/include-system-site-packages = true/' "$ROOT/.venv/pyvenv.cfg"
fi
VPY="$ROOT/.venv/bin/python"
if ! "$VPY" -m pip --version >/dev/null 2>&1; then
  curl -fsSL https://bootstrap.pypa.io/get-pip.py -o /tmp/yo-get-pip.py
  "$VPY" /tmp/yo-get-pip.py
fi
# shellcheck disable=SC1091
source "$ROOT/.venv/bin/activate"
python -m pip install --upgrade pip wheel
echo "→ зависимости (модель скачается при первом запуске)"
python -m pip install -e "$ROOT"
python -m pip install nvidia-cublas-cu12 nvidia-cudnn-cu12 || true

chmod +x "$ROOT/scripts/yo-voice"

APP_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
AUTOSTART="$HOME/.config/autostart"
DESKTOP_DIR="$HOME/Desktop"
mkdir -p "$APP_DIR" "$AUTOSTART" "$DESKTOP_DIR" "$HOME/.local/bin"

ICON="$ROOT/assets/mascot.png"
EXEC="$ROOT/scripts/yo-voice"

write_desktop() {
  local dest="$1"
  local cmd="$2"
  local extra="${3:-}"
  cat > "$dest" <<EOF
[Desktop Entry]
Type=Application
Name=Ёхо
Comment=Голосовой ввод в любое текстовое поле
Exec=$cmd
Icon=$ICON
Terminal=false
Categories=Utility;AudioVideo;
StartupNotify=false
$extra
EOF
  chmod +x "$dest"
}

write_desktop "$APP_DIR/yo-voice.desktop" "$EXEC toggle"
write_desktop "$AUTOSTART/yo-voice.desktop" "$EXEC daemon" "X-GNOME-Autostart-enabled=true
X-GNOME-Autostart-Delay=3"
write_desktop "$DESKTOP_DIR/yo-voice.desktop" "$EXEC toggle"

ln -sf "$EXEC" "$HOME/.local/bin/yo-voice"

if command -v gio >/dev/null 2>&1; then
  gio set "$DESKTOP_DIR/yo-voice.desktop" metadata::trusted true 2>/dev/null || true
fi

echo
echo "Ёхо установлена."
echo "  Ярлык: $DESKTOP_DIR/yo-voice.desktop"
echo "  Команда: yo-voice"
echo "  Горячая клавиша после запуска Ёхо в фоне: ё или \`"
echo "Первый запуск скачает модель распознавания (~1.6 ГБ)."

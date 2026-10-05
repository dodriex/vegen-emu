#!/usr/bin/env bash
set -euo pipefail

APP_NAME="vegen-emu"
SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/$APP_NAME"
BIN_DIR="$HOME/.local/bin"
APPLICATIONS_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
DESKTOP_DIR="$(xdg-user-dir DESKTOP 2>/dev/null || printf '%s/Desktop' "$HOME")"

mkdir -p "$INSTALL_DIR/work" "$INSTALL_DIR/outputs" "$BIN_DIR" "$APPLICATIONS_DIR" "$DESKTOP_DIR"

install -m 755 "$SOURCE_DIR/work/swipe_loop.py" "$INSTALL_DIR/work/swipe_loop.py"
install -m 755 "$SOURCE_DIR/outputs/tellingen_popup.py" "$INSTALL_DIR/outputs/tellingen_popup.py"

if [ ! -f "$INSTALL_DIR/outputs/veegtellingen.json" ]; then
  cat > "$INSTALL_DIR/outputs/veegtellingen.json" <<'JSON'
{
  "bijgewerkt_utc": "nog niet gestart",
  "succesvol_links": 0,
  "succesvol_rechts": 0,
  "succesvol_totaal": 0
}
JSON
fi

cat > "$BIN_DIR/vegen-emu" <<EOF
#!/usr/bin/env bash
exec python3 "$INSTALL_DIR/outputs/tellingen_popup.py" "\$@"
EOF
chmod 755 "$BIN_DIR/vegen-emu"

cat > "$APPLICATIONS_DIR/vegen-emu.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Vegen Emu
Comment=Live teller en bediening voor Android-emulator vegen
Exec=$BIN_DIR/vegen-emu
Path=$INSTALL_DIR
Terminal=false
Categories=Utility;
EOF
chmod 755 "$APPLICATIONS_DIR/vegen-emu.desktop"

cp "$APPLICATIONS_DIR/vegen-emu.desktop" "$DESKTOP_DIR/Vegen Emu.desktop"
chmod 755 "$DESKTOP_DIR/Vegen Emu.desktop"
gio set "$DESKTOP_DIR/Vegen Emu.desktop" metadata::trusted true >/dev/null 2>&1 || true

python3 - <<'PY'
import importlib.util
missing = []
for module in ("PIL", "tkinter"):
    if importlib.util.find_spec(module) is None:
        missing.append(module)
if missing:
    print("Let op: ontbrekende Python modules:", ", ".join(missing))
    print("Installeer op Ubuntu bijvoorbeeld: sudo apt install python3-tk python3-pil")
PY

cat <<EOF
Vegen Emu is geinstalleerd.

Openen:
  $BIN_DIR/vegen-emu

Of via de bureaubladsnelkoppeling:
  $DESKTOP_DIR/Vegen Emu.desktop

De Start-knop zoekt een user-service met 'android-emulator' in de naam.
ADB wordt automatisch gezocht. Als dat nodig is kun je dit instellen:
  export VEGEN_EMU_ADB=/pad/naar/platform-tools/adb
  export VEGEN_EMU_ADB_PORT=5038
  export VEGEN_EMU_ADB_SERIAL=emulator-5554
EOF

#!/bin/zsh
# Switch the real Kodi profile back to another skin (kscape has no Settings screens yet).
# Usage: tools/revert_kodi_skin.sh [skin-id]      default: skin.aeon.nox.silvo
# Quits Kodi first if it is running; add-ons stay installed.
SKIN=${1:-skin.aeon.nox.silvo}
G="$HOME/Library/Application Support/Kodi/userdata/guisettings.xml"
if pgrep -f 'Kodi.app/Contents/MacOS/Kodi' >/dev/null; then
    osascript -e 'quit app "Kodi"' 2>/dev/null; sleep 8
fi
if pgrep -f 'Kodi.app/Contents/MacOS/Kodi' >/dev/null; then
    echo "Kodi is still running; quit it and run this again." >&2; exit 1
fi
sed -i '' "s#<setting id=\"lookandfeel.skin\"[^<]*<#<setting id=\"lookandfeel.skin\">$SKIN<#" "$G"
grep -o '<setting id="lookandfeel.skin"[^<]*' "$G"

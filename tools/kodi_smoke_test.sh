#!/bin/zsh
# Isolated Kodi smoke test: copies the skin and wall add-on into a throwaway HOME, enables them,
# launches a second Kodi on JSON-RPC port 9091, and reports skin load result.
# Only the Kodi this script started (PID in /tmp/kscape-test.pid) is ever stopped, so a real
# Kodi running on the same machine is left alone.
SRC="$(cd "$(dirname "$0")/.." && pwd)/skin.kscape"
H=/tmp/kscape-home; K="$H/Library/Application Support/Kodi"
DB="$K/userdata/Database/Addons33.db"
PIDF=/tmp/kscape-test.pid
if [[ -f $PIDF ]] && kill -0 "$(cat $PIDF)" 2>/dev/null; then
    kill -TERM "$(cat $PIDF)"; sleep 5
fi
rm -rf "$K/addons/skin.kscape" "$K/addons/skin.kscapeprobe" "$K/addons/script.kscape.wall" && cp -R "$SRC" "$K/addons/"
cp -R "$(dirname "$SRC")/script.kscape.wall" "$K/addons/" && find "$K/addons/script.kscape.wall" -name __pycache__ -prune -exec rm -rf {} +
# Manually copied add-ons are registered disabled by Kodi 17+; enable ours in the throwaway profile only.
sqlite3 "$DB" "delete from installed where addonID='skin.kscapeprobe'; update installed set enabled=1 where addonID in ('skin.kscape','script.kscape.wall');"
G="$K/userdata/guisettings.xml"
sed -i '' 's#<setting id="lookandfeel.skin"[^<]*<#<setting id="lookandfeel.skin">skin.kscape<#' "$G"
# Local-only JSON-RPC plus screenshot path, for automated checks.
sed -i '' -E 's#<setting id="services.esenabled"[^<]*<#<setting id="services.esenabled">true<#' "$G"
sed -i '' -E 's#<setting id="debug.screenshotpath"[^>]*/>#<setting id="debug.screenshotpath">/tmp/kscape-shots/</setting>#' "$G"
# Mouse off: the host pointer hovering over Kodi would otherwise steal focus during tests.
sed -i '' -E 's#<setting id="input.enablemouse"[^<]*<#<setting id="input.enablemouse">false<#' "$G"
# Port 9091 so a real Kodi (9090) on this machine never receives test input.
cat > "$K/userdata/advancedsettings.xml" <<'XML'
<advancedsettings>
  <loglevel>2</loglevel>
  <jsonrpc><tcpport>9091</tcpport></jsonrpc>
</advancedsettings>
XML
rm -f "$H/Library/Logs/kodi.log"
cd /tmp && HOME=$H nohup /Applications/Kodi.app/Contents/MacOS/Kodi > /tmp/kscape-kodi-stdout.txt 2>&1 &
echo $! > $PIDF
sleep ${WAIT:-35}
LOG="$H/Library/Logs/kodi.log"
grep -E "load skin from|Failed to load skin|LoadFontsFromFile|Loading skin file: Home| error " "$LOG" | grep -viE 'MediaKey|CDisplaySettings|CSettings' | cut -c1-220

"""Put every hand-written KScape window's controls inside a root group that carries the display
transform (<include>KScapeDisplay</include>, Includes_Display.xml), so the CinemaScope band,
safe area and projector offsets apply to it.

Usage: python3 tools/wrap_display.py [--check]

Idempotent: a window whose controls already sit in the root group is left as it is. Generated
windows get the same root from their generators (display_root() below). Not wrapped: include,
variable, font and default files, Pointer.xml (the mouse pointer must stay where the mouse is),
video calibration (its marks are the real screen's edges) and the cover wall, which lays itself
out inside the band.
"""
import os
import re
import sys

TOOLS = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(TOOLS, '..')
FOLDERS = [os.path.join(ROOT, 'skin.kscape', '1080i'),
           os.path.join(ROOT, 'script.kscape.wall', 'resources', 'skins', 'Default', '1080i')]
SKIP = re.compile(r'^(Includes.*|Variables|Font|Defaults|Pointer|SettingsScreenCalibration|script-kscape-preview|script-kscape-wall.*|script-kscape-list.*|'
                  r'script-kscape-collections.*)\.xml$')
MARK = '<description>Display &amp; aspect ratio root (Includes_Display.xml)</description>'


def display_root(inner, ind='\t\t'):
    """Wrap a window's controls (already indented for <controls>) in the transform root."""
    body = '\n'.join(('\t' + line) if line.strip() else line for line in inner.rstrip('\n').split('\n'))
    return (f'{ind}<control type="group">\n{ind}\t{MARK}\n{ind}\t<include>KScapeDisplay</include>\n'
            f'{body}\n{ind}</control>\n')


def wrap(text):
    if MARK in text:
        return text
    start = text.find('<controls>')
    end = text.rfind('</controls>')
    if start < 0 or end < 0:
        return text
    head = text[:start + len('<controls>')]
    inner = text[start + len('<controls>'):end]
    tail = text[end:]
    nl = inner.lstrip(' \t').startswith('\n')
    inner = inner.lstrip(' \t')[1:] if nl else inner
    line_start = text.rfind('\n', 0, end) + 1
    ind = text[line_start:end] + '\t'
    return f'{head}\n{display_root(inner, ind)}{text[line_start:end]}{tail}'


def main():
    check = '--check' in sys.argv
    changed = []
    for folder in FOLDERS:
        for name in sorted(os.listdir(folder)):
            if not name.endswith('.xml') or SKIP.match(name):
                continue
            path = os.path.join(folder, name)
            text = open(path, encoding='utf-8').read()
            new = wrap(text)
            if new != text:
                changed.append(name)
                if not check:
                    open(path, 'w', encoding='utf-8').write(new)
    print(('would wrap: ' if check else 'wrapped: ') + (', '.join(changed) or 'nothing'))
    return 1 if (check and changed) else 0


if __name__ == '__main__':
    sys.exit(main())

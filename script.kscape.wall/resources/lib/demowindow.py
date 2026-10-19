"""Demo Script screen: the album / show screen (browse.py, script-kscape-browse.xml) showing one
Demo Script - cover (the first scene's artwork), how many scenes and how long, its playback
options, description - with Play / Edit… / Duplicate / Delete (Back returns), and its scenes in order.

Select on a scene plays the script from there; Play plays it from the start (or from the focused
scene). C on a scene: Preview Scene, Move up, Move down, Remove from Demo Script (the scene
itself stays), Add scenes…; C on the menu: Rename, Duplicate, Delete.

Like the other screens it reports what was chosen and the caller starts playback:
('play', index), ('preview', scene id) or None.
"""
import xbmcgui

from . import scenemodel as SM
from . import scenes as S
from .browse import CONTEXT, ENTRIES, MENU, BrowseDialog
from . import menu, modal

tr = S.tr


class DemoDialog(BrowseDialog):

    def start(self):
        self.store = self.item                      # the scenes store; the script id is `did`
        self.refresh(select_menu='play')
        self.setFocusId(MENU)

    def refresh(self, select_menu=None, select_entry=0):
        d = self.store.script(self.did)
        if d is None:
            self.finish(None)
            return
        scenes = SM.script_scenes(d, self.store.by_id())
        self.scenes = scenes
        cover = next((s.get('thumbnail') or s.get('poster', '') for s in scenes
                      if s.get('thumbnail') or s.get('poster')), '')
        facts = f'{S.count_text(len(scenes), 32213, 32212)}, {SM.clock(SM.total_duration(d, self.store.by_id()))}'
        summary = f'{facts}  ·  {S.options_text(self.store, d)}'
        self._header(d['name'], cover, 'poster', summary, d.get('description', ''), tr(32210))
        # Back returns, so the four actions fit under a poster-shaped cover.
        self._fill_menu([('play', tr(32289), ''), ('edit', tr(32292), ''), ('duplicate', tr(32290), ''),
                         ('delete', tr(32291), '')], select_menu or 'play')
        rows = []
        for i, s in enumerate(scenes):
            rows.append((f'{i + 1}.  {s["name"]}', SM.clock(SM.duration(s)), s.get('poster', ''),
                         {'detail': s.get('title', '')}))
        self._fill_entries(rows, select_entry)
        self.setProperty('empty', '' if scenes else tr(32282))

    def on_menu(self, key):
        if key == 'return':
            self.finish(None)
        elif key == 'play':
            if self.scenes:
                self.finish(('play', 0))
            else:
                S.notify(tr(32282))
        elif key == 'edit':
            if S.edit_script(self.store, self.did):
                self.refresh(select_menu='edit')
        elif key == 'duplicate':
            new = S.duplicate_script(self.store, self.did)
            if new:
                S.notify(self.store.script(new)['name'])
        elif key == 'delete':
            if S.delete_script(self.store, self.did):
                self.finish(None)

    def on_entry(self, index):
        if 0 <= index < len(self.scenes):
            self.finish(('play', index))

    def on_play(self):
        if self.scenes:
            focused = self.getFocusId() == ENTRIES
            self.finish(('play', max(0, self.entries.getSelectedPosition()) if focused else 0))

    def onAction(self, action):
        if action.getId() in CONTEXT:
            self.context()
        else:
            super().onAction(action)

    def context(self):
        if self.getFocusId() == ENTRIES and self.scenes:
            i = self.entries.getSelectedPosition()
            entries = [('preview', tr(32278)), ('up', tr(32279)), ('down', tr(32280)),
                       ('remove', tr(32251)), ('add', tr(32281))]
            choice = menu.show(None, None, entries, search=False)
            if choice == 'preview':
                self.finish(('preview', self.scenes[i]['id']))
            elif choice in ('up', 'down'):
                j = self.store.move_in_script(self.did, i, -1 if choice == 'up' else 1)
                self.refresh(select_entry=j)
                self.setFocusId(ENTRIES)
            elif choice == 'remove':
                self.store.remove_from_script(self.did, i)
                self.refresh(select_entry=i)
                if self.scenes:
                    self.setFocusId(ENTRIES)
            elif choice == 'add':
                self.add_scenes()
            return
        choice = menu.show(None, None, [('rename', tr(32258)), ('add', tr(32281)), ('duplicate', tr(32259)),
                                        ('delete', tr(32260))], search=False)
        if choice == 'rename' and S.rename_script(self.store, self.did):
            self.refresh(select_menu='edit')
        elif choice == 'add':
            self.add_scenes()
        elif choice == 'duplicate':
            self.on_menu('duplicate')
        elif choice == 'delete':
            self.on_menu('delete')

    def add_scenes(self):
        """Pick scenes (movies first, then episodes) to add at the end of the script."""
        pool = SM.by_media(self.store.scenes, 'movie') + SM.by_media(self.store.scenes, 'episode')
        if not pool:
            S.notify(tr(32283))
            return
        chosen = xbmcgui.Dialog().multiselect(
            tr(32281), [f'{s["name"]}  ·  {s.get("title", "")}  ({SM.clock(SM.duration(s))})' for s in pool])
        for i in chosen or []:
            self.store.add_to_script(self.did, pool[i]['id'])
        if chosen:
            self.refresh(select_entry=len(self.scenes))


def show_script(st, did, favs=None):
    """Open a Demo Script's screen. Returns ('play', index), ('preview', scene id) or None."""
    menu.wait_for_dialogs()
    dialog = DemoDialog('script-kscape-browse.xml', S.ADDON.getAddonInfo('path'), 'Default', '1080i',
                        item=st, favs=None)
    dialog.did = did
    modal.run(dialog)
    choice = dialog.choice
    del dialog
    return choice

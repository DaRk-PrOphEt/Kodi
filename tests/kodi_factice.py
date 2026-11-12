# -*- coding: utf-8 -*-
"""Faux modules Kodi pour tester default.py sans Kodi, dans un dossier temporaire.

LOT0_SOURCE (facultatif) : dossier contenant un autre default.py à tester.
"""
import os
import sys
import tempfile
import types

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SOURCE = os.environ.get('LOT0_SOURCE') or os.path.join(RACINE, 'repo', 'script.dark-prophet')
SANDBOX = tempfile.mkdtemp(prefix='kodi-tests-')
SKIN = 'skin.arctic.fuse.3'

xbmc = types.ModuleType('xbmc')
xbmc.LOGINFO = 1
xbmc.log = lambda *a, **k: None
xbmc.habillage = SKIN
xbmc.getSkinDir = lambda: xbmc.habillage
xbmc.commandes = []
xbmc.executebuiltin = lambda commande, *a: xbmc.commandes.append(commande)
xbmc.sleep = lambda ms: None
xbmcvfs = types.ModuleType('xbmcvfs')
xbmcvfs.translatePath = lambda chemin: os.path.join(SANDBOX, chemin.split('://', 1)[-1])
xbmcgui = types.ModuleType('xbmcgui')
xbmcgui.Dialog = type('Dialog', (), {})
xbmcgui.WindowDialog = type('WindowDialog', (), {})
sys.modules.update({'xbmc': xbmc, 'xbmcvfs': xbmcvfs, 'xbmcgui': xbmcgui, 'xbmcaddon': types.ModuleType('xbmcaddon')})
sys.path.insert(0, SOURCE)
import default   # noqa: E402,F401

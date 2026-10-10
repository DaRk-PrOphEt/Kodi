# -*- coding: utf-8 -*-
# Lancé par Kodi à l'ouverture d'un profil : rend profiles.xml à Kodi après la
# pose des logos (voir poser_logos dans default.py) et repose nos images dans
# l'habillage si une de ses mises à jour les a remplacées, puis recharge les
# rangées de l'accueil quand un favori est ajouté.
import default

default.lever_verrou_profils()
default.poser_images_habillage(telecharger=False)
default.oublier_jeton()
default.surveiller_listes()

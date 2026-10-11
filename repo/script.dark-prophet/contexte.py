# -*- coding: utf-8 -*-
# Entrée « Chercher dans vStream » du menu d'un film ou d'une série (version Full) :
# quand alkoFlix ne trouve pas de lien, vStream cherche le même titre dans ses sources.
import sys
from urllib.parse import quote

import xbmc

RECHERCHE = ('plugin://plugin.video.vstream/?site=globalSearch&function=globalSearch'
             '&siteUrl=http%3A%2F%2Fvenom&searchtext={titre}&sCat={categorie}')


def chercher():
    element = sys.listitem
    fiche = element.getVideoInfoTag()
    if fiche.getMediaType() in ('tvshow', 'season', 'episode'):
        titre, categorie = fiche.getTVShowTitle() or fiche.getTitle(), '2'   # vStream : 2 = séries
    else:
        titre, categorie = fiche.getTitle(), '1'                             # 1 = films
    titre = (titre or element.getLabel()).strip()
    if titre:
        xbmc.executebuiltin('ActivateWindow(Videos,"%s",return)'
                            % RECHERCHE.format(titre=quote(titre), categorie=categorie))


if __name__ == '__main__':
    chercher()

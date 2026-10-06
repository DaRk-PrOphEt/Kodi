# -*- coding: utf-8 -*-
import json
import os
import shutil
import zipfile
from io import BytesIO
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

import xbmc
import xbmcgui
import xbmcvfs

TITRE = 'DaRk-PrOphEt'
SKIN = 'skin.arctic.fuse.3'
SKIN_SECOURS = 'skin.estuary'
PACK_URL = 'https://raw.githubusercontent.com/DaRk-PrOphEt/Kodi/main/packs/arctic-fuse-3.zip'
PACK_NOM = 'arctic-fuse-3.zip'

# Seuls ces dossiers de réglages voyagent dans un pack : la mise en page,
# jamais les réglages d'extensions qui contiennent des identifiants.
DOSSIERS = (SKIN, 'script.skinvariables')

ADDON_DATA = xbmcvfs.translatePath('special://profile/addon_data/')
SAUVEGARDE = os.path.join(ADDON_DATA, 'script.dark-prophet', 'sauvegarde')

dialog = xbmcgui.Dialog()


def log(msg):
    xbmc.log('[script.dark-prophet] %s' % msg, xbmc.LOGINFO)


def attendre(condition, secondes):
    """Attend qu'une condition Kodi devienne vraie. Renvoie False si le délai est dépassé."""
    moniteur = xbmc.Monitor()
    for _ in range(secondes * 2):
        if xbmc.getCondVisibility(condition):
            return True
        if moniteur.waitForAbort(0.5):
            return False
    return xbmc.getCondVisibility(condition)


def installer_habillage():
    if xbmc.getCondVisibility('System.HasAddon(%s)' % SKIN):
        return True
    dialog.ok(TITRE, "L'habillage Arctic Fuse 3 va être téléchargé.[CR]Réponds « Oui » quand Kodi te le demande.")
    # Le dépôt de l'auteur vient d'être installé avec ce script : Kodi doit
    # avoir lu son catalogue avant de pouvoir y trouver l'habillage.
    xbmc.executebuiltin('UpdateAddonRepos')
    xbmc.sleep(8000)
    xbmc.executebuiltin('InstallAddon(%s)' % SKIN)
    if attendre('System.HasAddon(%s)' % SKIN, 300):
        # Les dépendances finissent de s'installer juste après l'habillage.
        xbmc.sleep(5000)
        return True
    dialog.ok(TITRE, "L'habillage n'a pas pu être installé.[CR]Vérifie la connexion et que Kodi est en version 21 ou plus, puis relance.")
    return False


def changer_habillage(skin):
    if xbmc.getSkinDir() == skin:
        return True
    xbmc.executeJSONRPC(json.dumps({
        'jsonrpc': '2.0', 'id': 1, 'method': 'Settings.SetSettingValue',
        'params': {'setting': 'lookandfeel.skin', 'value': skin},
    }))
    # Kodi demande « Conserver ce changement ? » et annule seul au bout de
    # quelques secondes : on répond Oui à sa place.
    if attendre('Window.IsVisible(yesnodialog)', 20):
        xbmc.executebuiltin('SendClick(11)')
    moniteur = xbmc.Monitor()
    for _ in range(40):
        if xbmc.getSkinDir() == skin:
            xbmc.sleep(2000)
            return True
        if moniteur.waitForAbort(0.5):
            return False
    return False


def telecharger_pack():
    try:
        with urlopen(PACK_URL, timeout=30) as reponse:
            return zipfile.ZipFile(BytesIO(reponse.read()))
    except HTTPError as erreur:
        if erreur.code == 404:
            dialog.ok(TITRE, "La configuration n'est pas encore publiée sur le dépôt.")
        else:
            dialog.ok(TITRE, 'Téléchargement refusé (erreur %s).' % erreur.code)
    except (URLError, OSError, zipfile.BadZipFile) as erreur:
        log('telechargement : %r' % erreur)
        dialog.ok(TITRE, 'Téléchargement impossible. Vérifie la connexion puis relance.')
    return None


def membres_autorises(archive):
    """Fichiers du pack qu'on accepte d'écrire : addon_data/<dossier connu>/..."""
    for info in archive.infolist():
        morceaux = info.filename.replace('\\', '/').split('/')
        if info.is_dir() or len(morceaux) < 3 or '..' in morceaux:
            continue
        if morceaux[0] != 'addon_data' or morceaux[1] not in DOSSIERS:
            continue
        yield info, os.path.join(ADDON_DATA, *morceaux[1:])


def sauvegarder_actuel():
    shutil.rmtree(SAUVEGARDE, ignore_errors=True)
    for dossier in DOSSIERS:
        source = os.path.join(ADDON_DATA, dossier)
        if os.path.isdir(source):
            shutil.copytree(source, os.path.join(SAUVEGARDE, dossier))


def ecrire_pack(archive):
    for dossier in DOSSIERS:
        shutil.rmtree(os.path.join(ADDON_DATA, dossier), ignore_errors=True)
    nombre = 0
    for info, cible in membres_autorises(archive):
        os.makedirs(os.path.dirname(cible), exist_ok=True)
        with archive.open(info) as source, open(cible, 'wb') as sortie:
            shutil.copyfileobj(source, sortie)
        nombre += 1
    return nombre


def hors_de_l_habillage(action):
    """Kodi réécrit les réglages de l'habillage actif quand il le quitte : on
    passe donc sur l'habillage d'origine le temps de toucher aux fichiers."""
    if xbmc.getSkinDir() == SKIN and not changer_habillage(SKIN_SECOURS):
        dialog.ok(TITRE, "Impossible de quitter l'habillage pour appliquer les réglages.")
        return False
    action()
    return changer_habillage(SKIN)


def installer_config():
    if not dialog.yesno(TITRE, "Installer Arctic Fuse 3 avec la configuration de DaRk-PrOphEt ?[CR]Les réglages actuels de cet habillage seront remplacés (une copie est gardée)."):
        return
    if not installer_habillage():
        return
    archive = telecharger_pack()
    if archive is None:
        return
    if not any(membres_autorises(archive)):
        dialog.ok(TITRE, 'Le pack téléchargé ne contient aucun réglage utilisable.')
        return

    def appliquer():
        sauvegarder_actuel()
        log('%s fichiers écrits' % ecrire_pack(archive))

    if hors_de_l_habillage(appliquer):
        dialog.ok(TITRE, "C'est installé.[CR]Si des menus manquent, redémarre Kodi une fois.")
    else:
        dialog.ok(TITRE, "Réglages copiés, mais l'habillage n'a pas pu être activé.[CR]Active Arctic Fuse 3 dans Paramètres > Interface.")


def restaurer_avant():
    if not os.path.isdir(SAUVEGARDE):
        dialog.ok(TITRE, "Aucune copie des réglages d'avant sur cet appareil.")
        return
    if not dialog.yesno(TITRE, "Remettre les réglages d'avant l'installation ?"):
        return

    def remettre():
        for dossier in DOSSIERS:
            cible = os.path.join(ADDON_DATA, dossier)
            shutil.rmtree(cible, ignore_errors=True)
            source = os.path.join(SAUVEGARDE, dossier)
            if os.path.isdir(source):
                shutil.copytree(source, cible)

    hors_de_l_habillage(remettre)
    dialog.ok(TITRE, "Réglages d'avant remis en place.")


def exporter_config():
    """Fabrique le pack à partir de ce Kodi (à faire sur l'appareil déjà configuré)."""
    dossier = dialog.browse(3, 'Où enregistrer le pack ?', 'files')
    if not dossier:
        return
    tampon = BytesIO()
    nombre = 0
    with zipfile.ZipFile(tampon, 'w', zipfile.ZIP_DEFLATED) as archive:
        for nom in DOSSIERS:
            racine = os.path.join(ADDON_DATA, nom)
            for chemin, _, fichiers in os.walk(racine):
                for fichier in fichiers:
                    complet = os.path.join(chemin, fichier)
                    relatif = os.path.relpath(complet, ADDON_DATA).replace(os.sep, '/')
                    archive.write(complet, 'addon_data/' + relatif)
                    nombre += 1
    if not nombre:
        dialog.ok(TITRE, "Aucun réglage d'Arctic Fuse 3 trouvé sur cet appareil.")
        return
    # xbmcvfs sait écrire sur un partage réseau ou une clé USB, pas open().
    cible = dossier + PACK_NOM
    sortie = xbmcvfs.File(cible, 'w')
    reussi = sortie.write(bytearray(tampon.getvalue()))
    sortie.close()
    if reussi:
        dialog.ok(TITRE, 'Pack enregistré (%s fichiers) :[CR]%s' % (nombre, cible))
    else:
        dialog.ok(TITRE, "Écriture impossible dans ce dossier.")


def menu():
    choix = dialog.select(TITRE, [
        'Installer Arctic Fuse 3 configuré',
        "Remettre mes réglages d'avant",
        'Exporter la configuration de cet appareil',
    ])
    if choix == 0:
        installer_config()
    elif choix == 1:
        restaurer_avant()
    elif choix == 2:
        exporter_config()


if __name__ == '__main__':
    menu()

# -*- coding: utf-8 -*-
import base64
import glob
import html
import json
import os
import random
import re
import shutil
import sqlite3
import struct
import sys
import threading
import zlib
import zipfile
from http.server import BaseHTTPRequestHandler, HTTPServer
from io import BytesIO
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, quote
from urllib.request import Request, urlopen
from xml.etree import ElementTree

import xbmc
import xbmcaddon
import xbmcgui
import xbmcvfs

TITRE = 'DaRk-PrOphEt'
SKIN = 'skin.arctic.fuse.3'
SKIN_SECOURS = 'skin.estuary'
ALKOFLIX = 'plugin.video.alkoflix'
CATCHUP = 'plugin.video.catchuptvandmore'
LANGUE = 'resource.language.fr_fr'
SONS = 'resource.uisounds.androidtv'
# Icônes des menus d'alkoFlix : les packs de réglages s'en servent, mais
# alkoFlix ne les installe pas d'office (dépendance facultative).
ICONES = 'resource.images.alkodicons.coal'
# Suggestions du clavier : sans elle, Arctic Fuse 3 propose de l'installer à
# chaque ouverture du clavier.
SAISIE = 'plugin.program.autocompletion'
TMDBHELPER = 'plugin.video.themoviedb.helper'
LECTEUR = 'alkoflix.select.json'
NOMS = {SKIN: 'Arctic Fuse 3', ALKOFLIX: 'alkoFlix', CATCHUP: 'Catch-up TV & More',
        LANGUE: 'la langue française', SONS: 'les sons Android TV', ICONES: "les icônes d'alkoFlix",
        SAISIE: 'les suggestions du clavier'}
# Dépôt officiel de chaque extension. Le script les installe lui-même : Kodi
# refuse d'installer un dépôt en tant que dépendance d'une autre extension.
DEPOTS = {SKIN: 'repository.jurialmunkey', ALKOFLIX: 'repository.alkoflix', CATCHUP: 'catchuptvandmore.kodi.release'}
NOMS.update({'repository.jurialmunkey': "le dépôt d'Arctic Fuse 3", 'repository.alkoflix': "le dépôt d'alkoFlix",
             'catchuptvandmore.kodi.release': 'le dépôt de Catch-up TV'})
# Le confort : si l'un d'eux ne s'installe pas, la formule continue quand même.
FACULTATIFS = (LANGUE, SONS, ICONES, SAISIE)

PACKS_URL = 'https://raw.githubusercontent.com/DaRk-PrOphEt/Kodi/main/packs/'
# Publication d'un pack depuis Kodi : réservée au propriétaire du dépôt, qui
# saisit son jeton GitHub dans les paramètres de l'extension. Le jeton reste
# sur l'appareil.
API_PACKS = 'https://api.github.com/repos/DaRk-PrOphEt/Kodi/contents/packs/'
SIGNATURE = {'name': 'DaRk-PrOphEt', 'email': '67680888+DaRk-PrOphEt@users.noreply.github.com'}
PACK_ALKOFLIX = 'arctic-fuse-3.zip'
# Même interface avec moins de rangées par page, pour les boîtiers modestes.
PACK_LEGER = 'arctic-fuse-3-leger.zip'
PACK_CATCHUP = 'arctic-fuse-3-catchup.zip'

# Les deux entrées de l'écran de choix au démarrage (formule alkoFlix + Catch-up TV).
PROFIL_ALKOFLIX = 'alkoFlix'
PROFIL_CATCHUP = 'Catch-up TV'

# Seuls ces dossiers de réglages voyagent dans un pack : la mise en page,
# jamais les réglages d'extensions qui contiennent des identifiants.
DOSSIERS = (SKIN, 'script.skinvariables')

# Comptes que Catch-up TV & More sait utiliser (préfixe de ses réglages).
COMPTES = (
    ('TF1+', 'tf1plus'),
    ('M6+ (6play)', '6play'),
    ('RMC BFM Play', 'rmcbfmplay'),
    ('SFR TV', 'sfrtv'),
    ('ABweb', 'abweb'),
)

MAITRE = xbmcvfs.translatePath('special://masterprofile/')
PROFIL = xbmcvfs.translatePath('special://profile/')
ADDON_DATA = os.path.join(PROFIL, 'addon_data')
SAUVEGARDE = os.path.join(ADDON_DATA, 'script.dark-prophet', 'sauvegarde')
# Les paramètres d'une extension sont propres à chaque profil : le jeton est
# recopié ici pour servir aussi depuis le profil Catch-up TV.
FICHIER_JETON = os.path.join(MAITRE, 'addon_data', 'script.dark-prophet', 'jeton')
# Interface choisie à l'installation (« complet » ou « leger »), pour que la
# mise à jour ne repose pas la question.
FICHIER_INTERFACE = os.path.join(MAITRE, 'addon_data', 'script.dark-prophet', 'interface')

# Fonds d'écran proposés pour le profil alkoFlix (une image fixe : aucun effet sur la fluidité).
FONDS = (('Rouge', 'alkoflix-rouge.jpg'), ('Bleu', 'alkoflix-bleu.jpg'))
FICHIER_FOND = os.path.join(MAITRE, 'addon_data', 'script.dark-prophet', 'fond')
DOSSIER_FONDS = os.path.join(MAITRE, 'addon_data', 'script.dark-prophet')
FOND_HABILLAGE = 'special://skin/extras/backgrounds/blur/purple_blur.jpg'   # celui des packs
FOND_CATCHUP = 'catchup.jpg'   # l'image officielle de Catch-up TV & More, assombrie

# Image de la case « Plus… » en bout de rangée. Arctic Fuse 3 la lit dans son fichier
# groupé Textures.xbt, qui passe avant tout fichier posé dans son dossier : on fait donc
# pointer la seule ligne de l'habillage qui la cite vers notre image. Une mise à jour de
# l'habillage remet sa ligne ; service.py la repointe au démarrage suivant.
IMAGE_PLUS = 'more-items-wide.png'
DOSSIER_IMAGES = os.path.join(MAITRE, 'addon_data', 'script.dark-prophet', 'images')
PLUS_ORIGINE = '>fallback/more-items-wide.png<'
PLUS_REMPLACEE = '>special://masterprofile/addon_data/script.dark-prophet/images/more-items-wide.png<'

# Image de chaque profil sur l'écran de choix : l'icône officielle de son extension.
LOGOS = {PROFIL_ALKOFLIX: 'special://home/addons/%s/icon.png' % ALKOFLIX,
         PROFIL_CATCHUP: 'special://home/addons/%s/icon.png' % CATCHUP}
FICHIER_PROFILS = os.path.join(MAITRE, 'profiles.xml')
# Tant que ce fichier existe, profiles.xml est protégé en écriture (voir poser_logos).
VERROU_PROFILS = os.path.join(MAITRE, 'addon_data', 'script.dark-prophet', 'profils_verrouilles')
# Dossiers de profils à effacer une fois Kodi redémarré (voir reinitialiser).
PROFILS_A_EFFACER = os.path.join(MAITRE, 'addon_data', 'script.dark-prophet', 'profils_a_effacer')
# Réglages de Kodi relevés avant la première installation, pour pouvoir les remettre.
ETAT_AVANT = os.path.join(MAITRE, 'addon_data', 'script.dark-prophet', 'etat_avant.json')
REGLAGES_KODI = ('lookandfeel.skin', 'lookandfeel.soundskin', 'locale.keyboardlayouts', 'locale.country',
                 'addons.updatemode', 'locale.language')   # la langue en dernier : Kodi recharge tout

# Écran « Profils » de Kodi : identifiants fixés par Kodi, les mêmes dans tous les habillages.
LISTE_PROFILS = 2
BOUTON_ECRAN_CHOIX = 4
BOUTON_OK_DOSSIER = 413
BOUTON_OK_REGLAGES = 28
BOUTON_OUI = 11
BOUTON_NON = 10

dialog = xbmcgui.Dialog()


def log(msg):
    xbmc.log('[script.dark-prophet] %s' % msg, xbmc.LOGINFO)


def rpc(methode, params=None):
    reponse = xbmc.executeJSONRPC(json.dumps({'jsonrpc': '2.0', 'id': 1, 'method': methode, 'params': params or {}}))
    return json.loads(reponse).get('result')


def attendre(condition, secondes):
    """Attend qu'une condition Kodi devienne vraie. Renvoie False si le délai est dépassé."""
    moniteur = xbmc.Monitor()
    for _ in range(secondes * 4):
        if xbmc.getCondVisibility(condition):
            return True
        if moniteur.waitForAbort(0.25):
            return False
    return xbmc.getCondVisibility(condition)


def annoncer(texte):
    """Message de fin. Arctic Fuse 3 recharge l'habillage quand ses réglages
    changent, ce qui referme le message sans qu'on l'ait lu : on le réaffiche."""
    for _ in range(3):
        if dialog.ok(TITRE, texte):
            return
        xbmc.sleep(3000)


def installe(addon_id):
    return xbmc.getCondVisibility('System.HasAddon(%s)' % addon_id)


def dans_le_profil_principal():
    return os.path.normpath(PROFIL) == os.path.normpath(MAITRE)


# --- Installation des extensions -------------------------------------------

def rafraichir_depots():
    # Les dépôts tiers viennent d'être installés avec ce script : Kodi doit
    # avoir lu leur catalogue avant de pouvoir y trouver quoi que ce soit.
    xbmc.executebuiltin('UpdateAddonRepos')
    xbmc.sleep(8000)


def installer_extension(addon_id):
    """Lance l'installation, confirme à la place de l'utilisateur et attend qu'elle aboutisse."""
    if installe(addon_id):
        return True
    xbmc.executebuiltin('InstallAddon(%s)' % addon_id)
    if attendre('Window.IsVisible(yesnodialog)', 15):
        xbmc.executebuiltin('SendClick(%d)' % BOUTON_OUI)
    moniteur = xbmc.Monitor()
    for _ in range(600):
        if installe(addon_id):
            break
        if xbmc.getCondVisibility('Window.IsVisible(okdialog)'):
            # Kodi annonce un échec (dépendance introuvable, téléchargement coupé…).
            xbmc.executebuiltin('Dialog.Close(okdialog)')
            return False
        if moniteur.waitForAbort(0.5):
            return False
    else:
        return False
    # Les dépendances finissent de s'installer juste après.
    xbmc.sleep(5000)
    if addon_id in (SKIN, LANGUE) and attendre('Window.IsVisible(yesnodialog)', 5):
        # Kodi propose de basculer tout de suite : non, le script s'en charge au bon moment.
        xbmc.executebuiltin('SendClick(%d)' % BOUTON_NON)
        xbmc.sleep(1000)
    return True


def installer_tout(addon_ids):
    """Installe ce qui manque. Renvoie False (après l'avoir dit) au premier échec."""
    manquants = []
    for addon_id in addon_ids:
        if not installe(addon_id):
            depot = DEPOTS.get(addon_id)
            if depot and not installe(depot):
                manquants.append(depot)
            manquants.append(addon_id)
    if not manquants:
        return True
    # Arctic Fuse 3 demande des versions de ses dépendances plus récentes que
    # celles du dépôt officiel de Kodi : sans ce réglage (« Mettre à jour les
    # extensions officielles depuis : Tous les dépôts »), Kodi refuse de l'installer.
    rpc('Settings.SetSettingValue', {'setting': 'addons.updatemode', 'value': 1})
    progression = xbmcgui.DialogProgressBG()
    progression.create(TITRE, 'Lecture des dépôts…')
    try:
        rafraichir_depots()
        for numero, addon_id in enumerate(manquants):
            progression.update(int(100 * numero / len(manquants)), TITRE, 'Installation de %s…' % NOMS[addon_id])
            if numero and manquants[numero - 1] in DEPOTS.values():
                # Un dépôt vient d'arriver : Kodi doit lire son catalogue.
                rafraichir_depots()
            # Sur un Kodi tout neuf, les catalogues des dépôts arrivent parfois
            # après la première tentative : on réessaie une fois.
            if not installer_extension(addon_id) and not (rafraichir_depots() or installer_extension(addon_id)):
                if addon_id in FACULTATIFS:
                    log('%s non installé, on continue' % addon_id)
                    continue
                dialog.ok(TITRE, "%s n'a pas pu être installé.[CR]Vérifie la connexion et que Kodi est en version 21 ou plus, puis relance." % NOMS[addon_id])
                return False
    finally:
        progression.close()
    return True


def regler(reglage, valeur):
    """Change un réglage de Kodi s'il n'a pas déjà cette valeur. Renvoie True s'il a changé."""
    if (rpc('Settings.GetSettingValue', {'setting': reglage}) or {}).get('value') == valeur:
        return False
    rpc('Settings.SetSettingValue', {'setting': reglage, 'value': valeur})
    return True


def franciser():
    """Kodi en français (langue, formats de date et d'heure, clavier AZERTY) avec les sons d'Android TV."""
    if installe(LANGUE) and regler('locale.language', LANGUE):
        # Kodi recharge ses textes et l'habillage.
        xbmc.sleep(4000)
        regler('locale.country', 'France')
        xbmc.sleep(1000)
    regler('locale.keyboardlayouts', ['French AZERTY'])
    if installe(SONS):
        regler('lookandfeel.soundskin', SONS)


# --- Habillage et packs de réglages ----------------------------------------

def changer_habillage(skin):
    if xbmc.getSkinDir() == skin:
        return True
    rpc('Settings.SetSettingValue', {'setting': 'lookandfeel.skin', 'value': skin})
    # Kodi demande « Conserver ce changement ? » et annule seul au bout de
    # quelques secondes : on répond Oui à sa place.
    if attendre('Window.IsVisible(yesnodialog)', 20):
        xbmc.executebuiltin('SendClick(%d)' % BOUTON_OUI)
    moniteur = xbmc.Monitor()
    for _ in range(40):
        if xbmc.getSkinDir() == skin:
            xbmc.sleep(2000)
            return True
        if moniteur.waitForAbort(0.5):
            return False
    return False


def telecharger_pack(nom, muet=False):
    """Renvoie l'archive, ou None (pack pas encore publié, ou réseau en panne)."""
    try:
        with urlopen(PACKS_URL + nom, timeout=30) as reponse:
            archive = zipfile.ZipFile(BytesIO(reponse.read()))
        if any(membres_autorises(archive, ADDON_DATA)):
            return archive
        log('pack %s sans réglage utilisable' % nom)
    except HTTPError as erreur:
        log('pack %s : erreur %s' % (nom, erreur.code))
        if not muet and erreur.code != 404:
            dialog.ok(TITRE, 'Téléchargement refusé (erreur %s).' % erreur.code)
    except (URLError, OSError, zipfile.BadZipFile) as erreur:
        log('pack %s : %r' % (nom, erreur))
        if not muet:
            dialog.ok(TITRE, 'Téléchargement impossible. Vérifie la connexion puis relance.')
    return None


def telecharger_pack_alkoflix(redemander=True):
    """Le pack du profil alkoFlix. Si une interface allégée est publiée, on
    demande laquelle installer ; sinon la question n'est pas posée. Le choix
    est retenu : avec redemander=False (mise à jour), on le reprend."""
    leger = telecharger_pack(PACK_LEGER, muet=True)
    if leger is None:
        return telecharger_pack(PACK_ALKOFLIX)
    choix = ''
    if not redemander and os.path.isfile(FICHIER_INTERFACE):
        choix = open(FICHIER_INTERFACE).read().strip()
    if choix not in ('complet', 'leger'):
        numero = dialog.select('Quel appareil ?', ['Appareil récent : interface complète',
                                                   'Boîtier modeste : interface allégée'])
        choix = 'leger' if numero == 1 else 'complet'
        os.makedirs(os.path.dirname(FICHIER_INTERFACE), exist_ok=True)
        with open(FICHIER_INTERFACE, 'w') as sortie:
            sortie.write(choix)
    return leger if choix == 'leger' else telecharger_pack(PACK_ALKOFLIX)


def membres_autorises(archive, racine):
    """Fichiers du pack qu'on accepte d'écrire : addon_data/<dossier connu>/..."""
    for info in archive.infolist():
        morceaux = info.filename.replace('\\', '/').split('/')
        if info.is_dir() or len(morceaux) < 3 or '..' in morceaux:
            continue
        if morceaux[0] != 'addon_data' or morceaux[1] not in DOSSIERS:
            continue
        yield info, os.path.join(racine, *morceaux[1:])


def ecrire_pack(archive, racine):
    for dossier in DOSSIERS:
        shutil.rmtree(os.path.join(racine, dossier), ignore_errors=True)
    nombre = 0
    for info, cible in membres_autorises(archive, racine):
        os.makedirs(os.path.dirname(cible), exist_ok=True)
        with archive.open(info) as source, open(cible, 'wb') as sortie:
            shutil.copyfileobj(source, sortie)
        nombre += 1
    return nombre


def sauvegarder_actuel():
    """Copie des réglages d'habillage d'AVANT la première installation : c'est
    elle que « Réinitialiser les réglages » remet. On ne la remplace donc pas
    aux installations et mises à jour suivantes."""
    if os.path.isdir(SAUVEGARDE):
        return
    os.makedirs(SAUVEGARDE)
    for dossier in DOSSIERS:
        source = os.path.join(ADDON_DATA, dossier)
        if os.path.isdir(source):
            shutil.copytree(source, os.path.join(SAUVEGARDE, dossier))


def hors_de_l_habillage(action):
    """Kodi réécrit les réglages de l'habillage actif quand il le quitte : on
    passe donc sur l'habillage d'origine le temps de toucher aux fichiers."""
    if xbmc.getSkinDir() == SKIN and not changer_habillage(SKIN_SECOURS):
        dialog.ok(TITRE, "Impossible de quitter l'habillage pour appliquer les réglages.")
        return False
    action()
    return changer_habillage(SKIN)


def appliquer_ici(archive, fond=None, bouton_catchup=None):
    """Applique un pack au profil ouvert et active l'habillage.
    bouton_catchup : True ou False pour ajuster le menu Options (profil alkoFlix seulement)."""
    if archive is None:
        return changer_habillage(SKIN)

    def appliquer():
        sauvegarder_actuel()
        log('%s fichiers écrits' % ecrire_pack(archive, ADDON_DATA))
        if fond:
            poser_fond(fond)
        if bouton_catchup is not None:
            ajuster_menu_options(bouton_catchup)

    return hors_de_l_habillage(appliquer)


def ajuster_menu_options(avec_catchup):
    """Menu Options d'Arctic Fuse 3 (profil alkoFlix) : un bouton pour passer au
    profil Catch-up TV, seulement s'il existe. Le pack Catch-up TV porte déjà
    le bouton du retour vers alkoFlix."""
    fichier = os.path.join(ADDON_DATA, 'script.skinvariables', 'nodes', SKIN, 'skinvariables-shortcut-powermenu.json')
    try:
        with open(fichier, encoding='utf-8') as source:
            entrees = [e for e in json.load(source) if not str(e.get('path', '')).startswith('LoadProfile(')]
        if avec_catchup:
            # Juste avant « Quitter », qui reste en dernier.
            entrees.insert(max(len(entrees) - 1, 0), {
                'icon': 'special://skin/extras/icons/livetv.png', 'label': PROFIL_CATCHUP,
                'path': 'LoadProfile(%s)' % PROFIL_CATCHUP, 'target': '', 'guid': 'guid-dpcatchup'})
        with open(fichier, 'w', encoding='utf-8') as sortie:
            json.dump(entrees, sortie, indent=4, ensure_ascii=False)
    except (OSError, ValueError) as erreur:
        log('menu Options : %r' % erreur)


def relier_alkoflix():
    """Les fiches et la recherche d'Arctic Fuse 3 passent par TMDb Helper : sans
    les lecteurs d'alkoFlix, un film choisi là ne propose que « Lire avec UPnP ».
    On installe ces lecteurs (fournis par alkoFlix) et on prend celui qui
    affiche la liste des liens comme lecteur par défaut."""
    source = xbmcvfs.translatePath('special://home/addons/%s/resources/players/json/' % ALKOFLIX)
    cible = os.path.join(ADDON_DATA, TMDBHELPER, 'players')
    try:
        lecteurs = [f for f in os.listdir(source) if f.endswith('.json')]
        os.makedirs(cible, exist_ok=True)
        for lecteur in lecteurs:
            shutil.copy(os.path.join(source, lecteur), cible)
        if LECTEUR in lecteurs:
            reglages = xbmcaddon.Addon(TMDBHELPER)
            reglages.setSetting('default_player_movies', LECTEUR + ' play_movie')
            reglages.setSetting('default_player_episodes', LECTEUR + ' play_episode')
    except (OSError, RuntimeError) as erreur:
        log('lecteurs alkoFlix : %r' % erreur)


def telecharger_fond(fichier):
    """Télécharge un fond d'écran du dépôt. Renvoie son chemin, ou None s'il est introuvable."""
    cible = os.path.join(DOSSIER_FONDS, fichier)
    try:
        os.makedirs(DOSSIER_FONDS, exist_ok=True)
        with urlopen(PACKS_URL + 'fonds/' + fichier, timeout=30) as reponse, open(cible, 'wb') as sortie:
            shutil.copyfileobj(reponse, sortie)
    except (URLError, OSError) as erreur:
        log('fond %s : %r' % (fichier, erreur))
        return cible if os.path.isfile(cible) else None
    return cible


def choisir_fond(redemander=True):
    """Fond d'écran du profil alkoFlix : chemin de l'image téléchargée, ou None
    pour garder celui du pack. Le choix est retenu pour les mises à jour."""
    choix = open(FICHIER_FOND).read().strip() if os.path.isfile(FICHIER_FOND) else ''
    fichiers = [fichier for _, fichier in FONDS]
    if redemander or (choix not in fichiers and choix != 'aucun'):
        numero = dialog.select("Quel fond d'écran ?", [nom for nom, _ in FONDS] + ["Celui d'Arctic Fuse 3"])
        choix = fichiers[numero] if 0 <= numero < len(fichiers) else 'aucun'
        os.makedirs(DOSSIER_FONDS, exist_ok=True)
        with open(FICHIER_FOND, 'w') as sortie:
            sortie.write(choix)
    return None if choix == 'aucun' else telecharger_fond(choix)


def changer_fond():
    """Change le fond d'écran du profil alkoFlix à tout moment, sans rien réinstaller."""
    numero = dialog.select("Quel fond d'écran ?", [nom for nom, _ in FONDS] + ["Celui d'Arctic Fuse 3"])
    if numero < 0:
        return
    choix = FONDS[numero][1] if numero < len(FONDS) else 'aucun'
    image = FOND_HABILLAGE if choix == 'aucun' else telecharger_fond(choix)
    if image is None:
        dialog.ok(TITRE, 'Téléchargement impossible. Vérifie la connexion puis relance.')
        return
    os.makedirs(DOSSIER_FONDS, exist_ok=True)
    with open(FICHIER_FOND, 'w') as sortie:
        sortie.write(choix)
    xbmc.executebuiltin('Skin.SetString(Background.Image,%s)' % image)


def poser_fond(image, racine=None):
    """Inscrit le fond dans les réglages de l'habillage d'un profil, pendant qu'il n'y est pas actif."""
    fichier = os.path.join(racine or ADDON_DATA, SKIN, 'settings.xml')
    if not os.path.isfile(fichier):
        return
    with open(fichier, encoding='utf-8') as source:
        xml = source.read()
    ligne = '<setting id="background.image" type="string">%s</setting>' % image.replace('&', '&amp;')
    motif = re.compile(r'<setting id="background\.image" type="string">.*?</setting>|<setting id="background\.image" type="string" */>', re.I | re.S)
    xml = motif.sub(lambda m: ligne, xml, count=1) if motif.search(xml) else xml.replace('</settings>', '    %s\n</settings>' % ligne)
    with open(fichier, 'w', encoding='utf-8') as sortie:
        sortie.write(xml)


def poser_images_habillage(telecharger=True):
    """Fait afficher notre image sur la case « Plus… » d'Arctic Fuse 3. Avec
    telecharger=False (au démarrage de Kodi), on se contente de repointer la
    ligne si une mise à jour de l'habillage l'a remise. Prend effet au
    prochain chargement de l'habillage."""
    copie = os.path.join(DOSSIER_IMAGES, IMAGE_PLUS)
    try:
        if telecharger:
            os.makedirs(DOSSIER_IMAGES, exist_ok=True)
            with urlopen(PACKS_URL + 'images/' + IMAGE_PLUS, timeout=30) as reponse, open(copie, 'wb') as sortie:
                shutil.copyfileobj(reponse, sortie)
        if os.path.isfile(copie):
            remplacer_dans_habillage(PLUS_ORIGINE, PLUS_REMPLACEE)
    except (URLError, OSError) as erreur:
        log('image « Plus » : %r' % erreur)


def remplacer_dans_habillage(avant, apres):
    fichier = xbmcvfs.translatePath('special://home/addons/%s/1080i/Includes_Objects.xml' % SKIN)
    if not os.path.isfile(fichier):
        return
    with open(fichier, encoding='utf-8') as source:
        xml = source.read()
    if avant in xml:
        with open(fichier, 'w', encoding='utf-8') as sortie:
            sortie.write(xml.replace(avant, apres))


def fermer_fenetres():
    """Ferme ce qu'un pilotage interrompu aurait laissé ouvert (clavier, fenêtre de profil)."""
    for _ in range(4):
        if not xbmc.getCondVisibility('System.HasActiveModalDialog'):
            break
        xbmc.executebuiltin('Action(Back)')
        xbmc.sleep(500)


def attendre_le_calme(maximum=60):
    """À sa première activation, Arctic Fuse 3 fabrique ses menus puis se
    recharge : tout pilotage lancé pendant ce temps est perdu. On attend
    quelques secondes sans fenêtre de travail."""
    moniteur = xbmc.Monitor()
    calme = 0
    for _ in range(maximum * 2):
        occupe = xbmc.getCondVisibility(
            'Window.IsVisible(progressdialog) | Window.IsVisible(busydialog) | '
            'Window.IsVisible(busydialognocancel) | Window.IsActive(startup)')
        calme = 0 if occupe else calme + 1
        if calme >= 12 or moniteur.waitForAbort(0.5):
            return


def insister(action, *arguments):
    """Rejoue un pilotage d'écran qui a échoué, après avoir remis Kodi au propre."""
    for _ in range(3):
        if action(*arguments):
            return True
        fermer_fenetres()
        attendre_le_calme()
    return False


def retour_accueil():
    # Un changement de fenêtre ferme les messages ouverts : on attend qu'il
    # soit fini avant d'en afficher un.
    fermer_fenetres()
    xbmc.executebuiltin('ActivateWindow(home)')
    attendre('Window.IsActive(home)', 10)
    xbmc.sleep(700)


# --- Profils ----------------------------------------------------------------

def profils():
    return [p['label'] for p in (rpc('Profiles.GetProfiles') or {}).get('profiles', [])]


def dossier_du_profil(nom):
    """Dossier que Kodi a donné au profil, lu dans son fichier des profils."""
    for profil in ElementTree.parse(os.path.join(MAITRE, 'profiles.xml')).getroot().iter('profile'):
        if profil.findtext('name') == nom:
            return os.path.join(MAITRE, *profil.findtext('directory').strip('/').split('/'))
    return None


def ouvrir_ecran_profils():
    # Juste après son activation, Arctic Fuse 3 se recharge une fois et
    # annule l'ouverture en cours : on insiste.
    for _ in range(5):
        xbmc.executebuiltin('ActivateWindow(profiles)')
        if attendre('Window.IsActive(profiles)', 6):
            xbmc.sleep(1500)
            if xbmc.getCondVisibility('Window.IsActive(profiles)'):
                return True
    return False


def ouvrir_liste_des_profils(position):
    """Ouvre l'écran Profils de Kodi et se place sur une case de la liste."""
    if not ouvrir_ecran_profils():
        return False
    # Selon l'habillage, la liste n'apparaît qu'une fois son onglet choisi.
    for touche in ('Down', 'Down', 'Right', 'Up', 'Left', 'Down'):
        if xbmc.getCondVisibility('Control.IsVisible(%d)' % LISTE_PROFILS):
            break
        xbmc.executebuiltin('Action(%s)' % touche)
        xbmc.sleep(400)
    # En deux temps : certains habillages placent la sélection sans donner la main à la liste.
    xbmc.executebuiltin('SetFocus(%d)' % LISTE_PROFILS)
    xbmc.sleep(400)
    xbmc.executebuiltin('SetFocus(%d,%d,absolute)' % (LISTE_PROFILS, position))
    xbmc.sleep(500)
    return (xbmc.getCondVisibility('Control.HasFocus(%d)' % LISTE_PROFILS)
            and xbmc.getInfoLabel('Container(%d).CurrentItem' % LISTE_PROFILS) == str(position + 1))


def attendre_fenetre(nom, secondes):
    """Attend une fenêtre de Kodi en répondant Non aux questions qui
    s'intercalent (Arctic Fuse 3 propose par exemple d'installer une
    extension de saisie automatique dès qu'un clavier s'ouvre)."""
    moniteur = xbmc.Monitor()
    for _ in range(secondes * 4):
        if xbmc.getCondVisibility('Window.IsVisible(%s)' % nom):
            return True
        refuser_question()
        if moniteur.waitForAbort(0.25):
            return False
    return False


def refuser_question():
    if xbmc.getCondVisibility('Window.IsVisible(yesnodialog)'):
        xbmc.executebuiltin('SendClick(%d)' % BOUTON_NON)
        xbmc.sleep(600)


def saisir(texte):
    """Remplit et valide le clavier de Kodi."""
    if not attendre_fenetre('virtualkeyboard', 10):
        log('clavier : pas ouvert')
        return False
    for _ in range(3):
        # Le clavier n'accepte le texte qu'une fois son animation d'ouverture finie.
        xbmc.sleep(1000)
        refuser_question()
        rpc('Input.SendText', {'text': texte, 'done': True})
        xbmc.sleep(700)
        refuser_question()
        if not xbmc.getCondVisibility('Window.IsVisible(virtualkeyboard)'):
            return True
    log('clavier : texte refusé')
    return False


def creer_profil(nom):
    """Pilote l'écran « Ajouter un profil » de Kodi : il n'existe pas de
    commande pour créer un profil, et Kodi réécrit profiles.xml en se fermant."""
    if nom in profils():
        return True
    if not ouvrir_liste_des_profils(len(profils())):
        log('profil : liste des profils inaccessible')
        return False
    xbmc.executebuiltin('Action(Select)')
    if not saisir(nom):
        return False
    if attendre_fenetre('filebrowser', 10):
        xbmc.sleep(500)
        xbmc.executebuiltin('SendClick(%d)' % BOUTON_OK_DOSSIER)
    if not attendre_fenetre('profilesettings', 10):
        log('profil : fenêtre de réglages pas ouverte')
        return False
    xbmc.sleep(500)
    xbmc.executebuiltin('SendClick(%d)' % BOUTON_OK_REGLAGES)
    # « Copier les réglages / les sources du profil principal ? » : oui aux deux.
    for _ in range(3):
        if not attendre('Window.IsVisible(yesnodialog)', 4):
            break
        xbmc.sleep(400)
        xbmc.executebuiltin('SendClick(%d)' % BOUTON_OUI)
        xbmc.sleep(800)
    return nom in profils()


def renommer_profil_principal(nom):
    if profils()[:1] == [nom]:
        return True
    if not ouvrir_liste_des_profils(0):
        return False
    xbmc.executebuiltin('Action(Select)')
    if not attendre_fenetre('profilesettings', 10):
        return False
    xbmc.sleep(500)
    # Le nom est la première ligne, déjà sélectionnée à l'ouverture.
    xbmc.executebuiltin('Action(Select)')
    saisi = saisir(nom)
    xbmc.executebuiltin('SendClick(%d)' % BOUTON_OK_REGLAGES)
    xbmc.sleep(800)
    return saisi and profils()[:1] == [nom]


def activer_ecran_de_choix():
    if xbmc.getCondVisibility('System.HasLoginScreen'):
        return True
    if not ouvrir_ecran_profils():
        return False
    xbmc.executebuiltin('SendClick(%d)' % BOUTON_ECRAN_CHOIX)
    xbmc.sleep(800)
    return xbmc.getCondVisibility('System.HasLoginScreen')


def poser_logos():
    """Donne à chaque profil le logo de son extension sur l'écran de choix, et
    son nom au profil principal.
    Kodi n'a aucune commande pour l'image d'un profil et réécrit profiles.xml
    en se fermant : on inscrit donc les logos dans le fichier, puis on le
    protège en écriture. Au démarrage suivant Kodi le relit, et service.py
    lève la protection. Renvoie True si un logo a été posé."""
    try:
        arbre = ElementTree.parse(FICHIER_PROFILS)
        change = False
        profils_connus = list(arbre.getroot().iter('profile'))
        avec_catchup = any(profil.findtext('name') == PROFIL_CATCHUP for profil in profils_connus)
        for profil in profils_connus:
            principal = profil.findtext('id') == '0'
            nom = profil.find('name')
            # Le profil principal prend son nom ici aussi : le renommage par l'écran des profils
            # échoue sur certains appareils, et ce fichier est de toute façon relu au redémarrage.
            if principal and avec_catchup and nom is not None and nom.text != PROFIL_ALKOFLIX:
                nom.text = PROFIL_ALKOFLIX
                change = True
            logo = LOGOS[PROFIL_ALKOFLIX] if principal and avec_catchup else LOGOS.get(profil.findtext('name'))
            vignette = profil.find('thumbnail')
            # On ne remplace pas une image que quelqu'un a choisie.
            if logo and vignette is not None and not (vignette.text or '').strip():
                vignette.text = logo
                change = True
        if not change:
            return False
        os.chmod(FICHIER_PROFILS, 0o644)
        arbre.write(FICHIER_PROFILS, encoding='utf-8')
        os.chmod(FICHIER_PROFILS, 0o444)
        os.makedirs(os.path.dirname(VERROU_PROFILS), exist_ok=True)
        with open(VERROU_PROFILS, 'w') as sortie:
            sortie.write(str(os.getpid()))
        return True
    except (OSError, ElementTree.ParseError) as erreur:
        log('logos : %r' % erreur)
        return False


def lever_verrou_profils():
    """Rend profiles.xml à Kodi une fois qu'il l'a relu, c'est-à-dire après un
    redémarrage : le numéro de processus n'est plus celui noté par poser_logos."""
    if not os.path.isfile(VERROU_PROFILS):
        return
    try:
        if open(VERROU_PROFILS).read().strip() == str(os.getpid()):
            return
        os.chmod(FICHIER_PROFILS, 0o644)
        os.remove(VERROU_PROFILS)
        if os.path.isfile(PROFILS_A_EFFACER):
            # Kodi ne connaît plus ces profils : leurs dossiers (réglages, identifiants) peuvent partir.
            racine = os.path.join(MAITRE, 'profiles')
            for nom in open(PROFILS_A_EFFACER, encoding='utf-8').read().splitlines():
                dossier = os.path.normpath(os.path.join(MAITRE, nom))
                if nom and dossier.startswith(racine + os.sep):
                    shutil.rmtree(dossier, ignore_errors=True)
            os.remove(PROFILS_A_EFFACER)
    except OSError as erreur:
        log('verrou des profils : %r' % erreur)


def copier_extensions_actives(dossier):
    """Un profil neuf démarre avec toutes les extensions désactivées : on lui
    donne la liste du profil principal (habillage, Catch-up TV, ce script…)."""
    cible = os.path.join(dossier, 'Database')
    os.makedirs(cible, exist_ok=True)
    for base in glob.glob(os.path.join(MAITRE, 'Database', 'Addons*.db')):
        copie = os.path.join(cible, os.path.basename(base))
        if os.path.exists(copie):
            os.remove(copie)
        source, sortie = sqlite3.connect(base), sqlite3.connect(copie)
        try:
            with sortie:
                source.backup(sortie)
        finally:
            source.close()
            sortie.close()


def choisir_habillage_du_profil(dossier):
    """Le profil reprend les réglages généraux du principal ; on s'assure
    seulement que son habillage est bien Arctic Fuse 3."""
    fichier = os.path.join(dossier, 'guisettings.xml')
    if not os.path.isfile(fichier):
        shutil.copy(os.path.join(MAITRE, 'guisettings.xml'), fichier)
    arbre = ElementTree.parse(fichier)
    for reglage in arbre.getroot().iter('setting'):
        if reglage.get('id') == 'lookandfeel.skin':
            reglage.text = SKIN
            reglage.attrib.pop('default', None)
            break
    else:
        ElementTree.SubElement(arbre.getroot(), 'setting', id='lookandfeel.skin').text = SKIN
    arbre.write(fichier, encoding='utf-8')


GUIDE_PROFIL = (
    "Kodi n'a pas pu créer le profil tout seul. À faire à la main :[CR]"
    "1. Paramètres > Profils > Profils > Ajouter un profil[CR]"
    "2. Nom : %s, puis OK deux fois[CR]"
    "3. Réponds « Copier » aux deux questions[CR]"
    "4. Relance ensuite cette formule." % PROFIL_CATCHUP
)


# --- Les deux formules ------------------------------------------------------

def formule_alkoflix():
    if not dialog.yesno(TITRE, "Installer Arctic Fuse 3 et alkoFlix avec la configuration de DaRk-PrOphEt ?[CR]Kodi passera en français. Les réglages actuels de cet habillage seront remplacés (« Réinitialiser les réglages » les remet)."):
        return
    noter_etat_avant()
    if not installer_tout((LANGUE, SONS, SAISIE, SKIN, ALKOFLIX, ICONES)):
        return
    franciser()
    relier_alkoflix()
    poser_images_habillage()
    archive = telecharger_pack_alkoflix()
    if not appliquer_ici(archive, choisir_fond(), PROFIL_CATCHUP in profils()):
        dialog.ok(TITRE, "Réglages copiés, mais l'habillage n'a pas pu être activé.[CR]Active Arctic Fuse 3 dans Paramètres > Interface.")
    elif archive is None:
        annoncer("Arctic Fuse 3 et alkoFlix sont installés.[CR]La configuration n'est pas encore publiée : l'habillage garde ses réglages.")
    else:
        annoncer("C'est installé.[CR]Si des menus manquent, redémarre Kodi une fois.")


def formule_catchup():
    if not dialog.yesno(TITRE, "Installer Arctic Fuse 3, alkoFlix et Catch-up TV ?[CR]Au démarrage, Kodi proposera deux entrées : « %s » et « %s ».[CR]Kodi passera en français. Les réglages actuels de l'habillage seront remplacés (« Réinitialiser les réglages » les remet)." % (PROFIL_ALKOFLIX, PROFIL_CATCHUP)):
        return
    noter_etat_avant()
    if not installer_tout((LANGUE, SONS, SAISIE, SKIN, ALKOFLIX, ICONES, CATCHUP)):
        return
    franciser()
    pack_alkoflix = telecharger_pack_alkoflix()
    pack_catchup = telecharger_pack(PACK_CATCHUP, muet=True) or pack_alkoflix
    relier_alkoflix()
    poser_images_habillage()
    if not appliquer_ici(pack_alkoflix, choisir_fond(), True):
        dialog.ok(TITRE, "L'habillage n'a pas pu être activé.[CR]Active Arctic Fuse 3 dans Paramètres > Interface, puis relance.")
        return
    preparer_profil_catchup(pack_catchup)


def mettre_a_jour():
    """Pour qui a déjà tout installé : repose la dernière interface publiée
    sur chaque profil et installe ce que les versions récentes ont ajouté
    (icônes, suggestions du clavier, clavier français)."""
    if not dialog.yesno(TITRE, "Mettre l'interface à jour ?[CR]Les réglages actuels de l'habillage seront remplacés par la dernière version (« Réinitialiser les réglages » les remet)."):
        return
    installer_tout((LANGUE, SONS, SAISIE, ICONES))
    franciser()
    archive = telecharger_pack_alkoflix(redemander=False)
    if archive is None:
        return
    logos = False
    if PROFIL_CATCHUP in profils():
        dossier = dossier_du_profil(PROFIL_CATCHUP)
        copier_extensions_actives(dossier)
        ecrire_pack(telecharger_pack(PACK_CATCHUP, muet=True) or archive, os.path.join(dossier, 'addon_data'))
        fond = telecharger_fond(FOND_CATCHUP)
        if fond:
            poser_fond(fond, os.path.join(dossier, 'addon_data'))
        logos = poser_logos()
    relier_alkoflix()
    poser_images_habillage()
    if appliquer_ici(archive, choisir_fond(redemander=False), PROFIL_CATCHUP in profils()):
        if logos:
            annoncer("L'interface est à jour.[CR]Redémarre Kodi : les profils auront leur logo sur l'écran de choix.")
        else:
            annoncer("L'interface est à jour.[CR]Si des menus manquent, redémarre Kodi une fois.")
    else:
        dialog.ok(TITRE, "Réglages copiés, mais l'habillage n'a pas pu être activé.[CR]Active Arctic Fuse 3 dans Paramètres > Interface.")


def ajouter_catchup():
    """Pour qui a pris la formule alkoFlix et change d'avis : ajoute Catch-up TV
    et son profil sans toucher aux réglages du profil ouvert."""
    if not dialog.yesno(TITRE, "Ajouter Catch-up TV ?[CR]Au démarrage, Kodi proposera deux entrées : « %s » et « %s ».[CR]Tes réglages actuels ne sont pas modifiés." % (PROFIL_ALKOFLIX, PROFIL_CATCHUP)):
        return
    if not installer_tout((CATCHUP,)):
        return
    hors_de_l_habillage(lambda: ajuster_menu_options(True))
    preparer_profil_catchup(telecharger_pack(PACK_CATCHUP, muet=True) or telecharger_pack(PACK_ALKOFLIX, muet=True))


def preparer_profil_catchup(pack):
    """Crée le profil Catch-up TV avec son pack, renomme le profil principal et
    active l'écran de choix. Tant que la configuration Catch-up TV n'est pas
    publiée, `pack` est celle d'alkoFlix : même allure, à alléger ensuite."""
    attendre_le_calme()
    if not insister(creer_profil, PROFIL_CATCHUP):
        retour_accueil()
        dialog.ok(TITRE, GUIDE_PROFIL)
        xbmc.executebuiltin('ActivateWindow(profiles)')
        return
    dossier = dossier_du_profil(PROFIL_CATCHUP)
    copier_extensions_actives(dossier)
    choisir_habillage_du_profil(dossier)
    if pack is not None:
        ecrire_pack(pack, os.path.join(dossier, 'addon_data'))
        fond = telecharger_fond(FOND_CATCHUP)
        if fond:
            poser_fond(fond, os.path.join(dossier, 'addon_data'))

    renomme = insister(renommer_profil_principal, PROFIL_ALKOFLIX)
    ecran = insister(activer_ecran_de_choix)
    retour_accueil()
    poser_logos()   # en dernier : ensuite Kodi ne peut plus enregistrer ses profils jusqu'au redémarrage
    restes = []
    if not renomme:
        restes.append("renommer le profil principal en « %s »" % PROFIL_ALKOFLIX)
    if not ecran:
        restes.append("activer « Afficher l'écran de connexion au démarrage »")
    if restes:
        annoncer("C'est installé. Reste à faire à la main dans Paramètres > Profils :[CR]- " + "[CR]- ".join(restes))
    else:
        annoncer("C'est installé.[CR]Redémarre Kodi : tu choisiras entre « %s » et « %s »." % (PROFIL_ALKOFLIX, PROFIL_CATCHUP))


def reappliquer_catchup():
    if not dialog.yesno(TITRE, "Remettre la configuration Catch-up TV de DaRk-PrOphEt sur ce profil ?[CR]Les réglages actuels de l'habillage seront remplacés (« Réinitialiser les réglages » les remet)."):
        return
    archive = telecharger_pack(PACK_CATCHUP)
    if archive is None:
        dialog.ok(TITRE, "La configuration Catch-up TV n'est pas encore publiée.")
    elif appliquer_ici(archive, telecharger_fond(FOND_CATCHUP)):
        annoncer("C'est appliqué.[CR]Si des menus manquent, redémarre Kodi une fois.")
    else:
        dialog.ok(TITRE, "Réglages copiés, mais l'habillage n'a pas pu être activé.[CR]Active Arctic Fuse 3 dans Paramètres > Interface.")


# --- Identifiants Catch-up TV -----------------------------------------------

def identifiants_catchup():
    """Les comptes restent dans les réglages de Catch-up TV de CE profil :
    ils ne partent ni dans un pack ni sur le dépôt."""
    if not installe(CATCHUP):
        dialog.ok(TITRE, "Catch-up TV n'est pas installé. Lance d'abord la formule « alkoFlix + Catch-up TV ».")
        return
    if dans_le_profil_principal() and PROFIL_CATCHUP in profils():
        if not dialog.yesno(TITRE, "Les identifiants sont propres à chaque profil.[CR]Ceux saisis ici ne serviront pas dans le profil « %s » : ouvre-le et relance ce menu.[CR]Les saisir quand même ici ?" % PROFIL_CATCHUP):
            return
    catchup = xbmcaddon.Addon(CATCHUP)
    while True:
        lignes = []
        for nom, cle in COMPTES:
            compte = catchup.getSetting(cle + '.login')
            lignes.append('%s : %s' % (nom, compte or 'non renseigné'))
        lignes.append('Saisir depuis mon téléphone…')
        lignes.append('Tous les réglages de Catch-up TV…')
        choix = dialog.select('Mes identifiants Catch-up TV', lignes)
        if choix < 0:
            return
        if choix == len(COMPTES):
            identifiants_par_telephone()
            continue
        if choix == len(COMPTES) + 1:
            catchup.openSettings()
            return
        nom, cle = COMPTES[choix]
        compte = dialog.input('%s : adresse ou identifiant' % nom, catchup.getSetting(cle + '.login'))
        if not compte:
            if catchup.getSetting(cle + '.login') and dialog.yesno(TITRE, 'Effacer le compte %s de cet appareil ?' % nom):
                catchup.setSetting(cle + '.login', '')
                catchup.setSetting(cle + '.password', '')
            continue
        mot_de_passe = dialog.input('%s : mot de passe' % nom, option=xbmcgui.ALPHANUM_HIDE_INPUT)
        if mot_de_passe:
            catchup.setSetting(cle + '.login', compte)
            catchup.setSetting(cle + '.password', mot_de_passe)


# --- Identifiants depuis le téléphone ----------------------------------------

def png(lignes):
    """Image PNG en niveaux de gris à partir de lignes d'octets (0 = noir, 255 = blanc)."""
    def bloc(genre, contenu):
        return struct.pack('>I', len(contenu)) + genre + contenu + struct.pack('>I', zlib.crc32(genre + contenu) & 0xffffffff)
    brut = b''.join(b'\x00' + bytes(ligne) for ligne in lignes)
    return (b'\x89PNG\r\n\x1a\n' + bloc(b'IHDR', struct.pack('>IIBBBBB', len(lignes[0]), len(lignes), 8, 0, 0, 0, 0))
            + bloc(b'IDAT', zlib.compress(brut, 9)) + bloc(b'IEND', b''))


def image_qr(texte, fichier):
    """Écrit le QR code de `texte`. Renvoie False si le module de QR codes manque."""
    try:
        import qrcode
        code = qrcode.QRCode(border=3, error_correction=qrcode.constants.ERROR_CORRECT_M)
        code.add_data(texte)
        code.make(fit=True)
        grille = code.get_matrix()
    except Exception as erreur:   # module absent ou incomplet sur cet appareil : on affichera l'adresse seule
        log('QR code : %r' % erreur)
        return False
    pas = 8
    lignes = []
    for rangee in grille:
        ligne = b''.join((b'\x00' if case else b'\xff') * pas for case in rangee)
        lignes.extend([ligne] * pas)
    with open(fichier, 'wb') as sortie:
        sortie.write(png(lignes))
    return True


PAGE_TELEPHONE = """<!doctype html><html lang="fr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Identifiants Catch-up TV</title>
<style>body{font:17px/1.4 system-ui,sans-serif;margin:0;padding:20px;background:#14131c;color:#f0eef8}
h1{font-size:22px;margin:0 0 6px}p{color:#aaa6bd;margin:0 0 18px}fieldset{border:1px solid #33304a;border-radius:10px;margin:0 0 14px;padding:12px}
legend{font-weight:700;padding:0 6px}label{display:block;font-size:14px;color:#aaa6bd;margin-top:8px}
input{width:100%%;box-sizing:border-box;font:inherit;padding:10px;border-radius:8px;border:1px solid #4a4666;background:#1d1b29;color:inherit}
button{width:100%%;font:inherit;font-weight:700;padding:14px;border:0;border-radius:10px;background:#7b5cf0;color:#fff}
.ok{background:#17402a;border-radius:10px;padding:14px;margin-bottom:18px}</style></head><body>
<h1>Identifiants Catch-up TV</h1><p>Ils sont enregistrés sur ton appareil Kodi, nulle part ailleurs. Laisse un mot de passe vide pour garder celui déjà enregistré.</p>
%(message)s<form method="post">%(champs)s<button type="submit">Enregistrer</button></form></body></html>"""


def identifiants_par_telephone():
    """Affiche une adresse (et son QR code) à ouvrir sur un téléphone du même
    réseau : une page y demande les identifiants et les enregistre dans les
    réglages de Catch-up TV du profil ouvert. Le serveur ne vit que le temps
    de la fenêtre, et son adresse contient un code tiré au hasard."""
    catchup = xbmcaddon.Addon(CATCHUP)
    jeton = '%06d' % random.randrange(10 ** 6)

    class Page(BaseHTTPRequestHandler):
        def log_message(self, *arguments):
            pass

        def repondre(self, message=''):
            champs = ''
            for nom, cle in COMPTES:
                champs += ('<fieldset><legend>%s</legend><label>Adresse ou identifiant</label>'
                           '<input name="%s.login" value="%s" autocapitalize="none" autocomplete="off">'
                           '<label>Mot de passe</label><input name="%s.password" type="password" autocomplete="off"></fieldset>'
                           % (html.escape(nom), cle, html.escape(catchup.getSetting(cle + '.login'), quote=True), cle))
            corps = (PAGE_TELEPHONE % {'message': message, 'champs': champs}).encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Length', str(len(corps)))
            self.end_headers()
            self.wfile.write(corps)

        def autorise(self):
            if self.path.strip('/') == jeton:
                return True
            self.send_error(404)
            return False

        def do_GET(self):
            if self.autorise():
                self.repondre()

        def do_POST(self):
            if not self.autorise():
                return
            saisie = parse_qs(self.rfile.read(int(self.headers.get('Content-Length') or 0)).decode('utf-8'), keep_blank_values=True)
            for _, cle in COMPTES:
                compte = (saisie.get(cle + '.login') or [''])[0].strip()
                mot_de_passe = (saisie.get(cle + '.password') or [''])[0]
                if compte != catchup.getSetting(cle + '.login'):
                    catchup.setSetting(cle + '.login', compte)
                    if not compte:
                        catchup.setSetting(cle + '.password', '')
                if mot_de_passe:
                    catchup.setSetting(cle + '.password', mot_de_passe)
            self.repondre('<div class="ok">Enregistré. Tu peux fermer cette page et appuyer sur Retour sur Kodi.</div>')

    serveur = None
    for port in range(8765, 8771):
        try:
            serveur = HTTPServer(('', port), Page)
            break
        except OSError:
            continue
    if serveur is None:
        dialog.ok(TITRE, "Impossible d'ouvrir la page de saisie sur cet appareil.")
        return
    adresse = 'http://%s:%s/%s' % (xbmc.getIPAddress(), serveur.server_address[1], jeton)
    threading.Thread(target=serveur.serve_forever, daemon=True).start()
    try:
        dossier = os.path.join(ADDON_DATA, 'script.dark-prophet')
        os.makedirs(dossier, exist_ok=True)
        fond, qr = os.path.join(dossier, 'fond-saisie.png'), os.path.join(dossier, 'qr.png')
        with open(fond, 'wb') as sortie:
            sortie.write(png([b'\x12' * 4] * 4))

        class Fenetre(xbmcgui.WindowDialog):
            def onAction(self, action):
                self.close()

        fenetre = Fenetre()
        fenetre.addControl(xbmcgui.ControlImage(0, 0, 1280, 720, fond))
        fenetre.addControl(xbmcgui.ControlLabel(90, 150, 600, 50, 'Identifiants Catch-up TV', textColor='0xFFFFFFFF'))
        zone = xbmcgui.ControlTextBox(90, 220, 600, 320, textColor='0xFFDDDDDD')
        fenetre.addControl(zone)
        zone.setText("Sur un téléphone connecté au même Wi-Fi, ouvre cette adresse%s :[CR][CR][B]%s[/B][CR][CR]"
                     "Saisis tes identifiants, valide, puis appuie sur Retour ici."
                     % (' ou scanne le code' if image_qr(adresse, qr) else '', adresse))
        if os.path.isfile(qr):
            fenetre.addControl(xbmcgui.ControlImage(780, 160, 400, 400, qr))
        fenetre.doModal()
        del fenetre
    finally:
        serveur.shutdown()
        serveur.server_close()
        for fichier in ('qr.png',):
            try:
                os.remove(os.path.join(ADDON_DATA, 'script.dark-prophet', fichier))
            except OSError:
                pass


# --- Réinitialisation et fabrication des packs -------------------------------

def noter_etat_avant():
    """Relève, une seule fois, les réglages de Kodi que les formules vont changer."""
    if os.path.isfile(ETAT_AVANT):
        return
    etat = {cle: (rpc('Settings.GetSettingValue', {'setting': cle}) or {}).get('value') for cle in REGLAGES_KODI}
    etat['profil'] = (profils() or ['Master user'])[0]
    os.makedirs(os.path.dirname(ETAT_AVANT), exist_ok=True)
    with open(ETAT_AVANT, 'w', encoding='utf-8') as sortie:
        json.dump(etat, sortie)


def reinitialiser():
    """Défait ce que les formules ont mis en place : habillage et réglages
    d'avant, plus de profil Catch-up TV ni d'écran de choix. Les extensions
    restent installées (Kodi n'a pas de commande pour les désinstaller)."""
    avec_catchup = PROFIL_CATCHUP in profils()
    if not dialog.yesno(TITRE, "Revenir à Kodi comme avant l'installation ?[CR]L'habillage et les réglages d'avant sont remis%s.[CR]Les extensions restent installées."
                        % (", le profil « %s » est supprimé avec ses identifiants" % PROFIL_CATCHUP if avec_catchup else '')):
        return
    etat = {}
    if os.path.isfile(ETAT_AVANT):
        try:
            with open(ETAT_AVANT, encoding='utf-8') as source:
                etat = json.load(source)
        except (OSError, ValueError) as erreur:
            log('état d\'avant : %r' % erreur)
    avant = etat.get('lookandfeel.skin') or SKIN_SECOURS
    if avant == SKIN and not os.path.isdir(SAUVEGARDE):
        avant = SKIN_SECOURS
    # 1. On quitte Arctic Fuse 3 (Kodi réécrit les réglages de l'habillage actif en le quittant),
    #    on remet ses réglages d'avant, puis on revient à l'habillage d'avant.
    if xbmc.getSkinDir() == SKIN and not changer_habillage(SKIN_SECOURS):
        dialog.ok(TITRE, "Impossible de quitter l'habillage. Change-le dans Paramètres > Interface, puis relance.")
        return
    for dossier in DOSSIERS:
        cible = os.path.join(ADDON_DATA, dossier)
        shutil.rmtree(cible, ignore_errors=True)
        source = os.path.join(SAUVEGARDE, dossier)
        if os.path.isdir(source):
            shutil.copytree(source, cible)
    changer_habillage(avant)
    # 2. Les réglages de Kodi relevés avant la première installation (absents si elle date d'une ancienne version).
    for cle in REGLAGES_KODI[1:]:
        if cle in etat and etat[cle] is not None:
            if regler(cle, etat[cle]) and cle == 'locale.language':
                xbmc.sleep(4000)
    # 3. Les profils : un seul, sans écran de choix. Même méthode que pour les logos.
    redemarrer = remettre_profil_unique(etat.get('profil') or 'Master user')
    # 4. Ce que le script avait noté pour lui-même.
    shutil.rmtree(SAUVEGARDE, ignore_errors=True)
    try:
        remplacer_dans_habillage(PLUS_REMPLACEE, PLUS_ORIGINE)
    except OSError as erreur:
        log('image « Plus » : %r' % erreur)
    shutil.rmtree(DOSSIER_IMAGES, ignore_errors=True)
    images = [os.path.join(DOSSIER_FONDS, fichier) for fichier in [f for _, f in FONDS] + [FOND_CATCHUP, 'fond-saisie.png']]
    for fichier in [ETAT_AVANT, FICHIER_INTERFACE, FICHIER_FOND] + images:
        try:
            os.remove(fichier)
        except OSError:
            pass
    annoncer("C'est réinitialisé.%s" % ("[CR]Redémarre Kodi pour retirer l'écran de choix et le profil « %s »." % PROFIL_CATCHUP if redemarrer else ''))


def remettre_profil_unique(nom):
    """Ne garde que le profil principal, sous son nom d'avant, sans écran de
    choix ni logo. Renvoie True si profiles.xml a changé (redémarrage nécessaire)."""
    try:
        arbre = ElementTree.parse(FICHIER_PROFILS)
        racine = arbre.getroot()
        a_effacer, change = [], False
        for profil in list(racine.iter('profile')):
            if profil.findtext('id') != '0':
                a_effacer.append((profil.findtext('directory') or '').strip('/'))
                racine.remove(profil)
                change = True
                continue
            for balise, valeur in (('name', nom), ('thumbnail', '')):
                element = profil.find(balise)
                if element is not None and (element.text or '') != valeur and (balise != 'thumbnail' or (element.text or '') in LOGOS.values()):
                    element.text = valeur
                    change = True
        for balise, valeur in (('useloginscreen', 'false'), ('lastloaded', '0'), ('autologin', '-1')):
            element = racine.find(balise)
            if element is not None and element.text != valeur:
                element.text = valeur
                change = True
        if not change:
            return False
        os.chmod(FICHIER_PROFILS, 0o644)
        arbre.write(FICHIER_PROFILS, encoding='utf-8')
        os.chmod(FICHIER_PROFILS, 0o444)
        os.makedirs(os.path.dirname(VERROU_PROFILS), exist_ok=True)
        with open(PROFILS_A_EFFACER, 'w', encoding='utf-8') as sortie:
            sortie.write('\n'.join(a_effacer))
        with open(VERROU_PROFILS, 'w') as sortie:
            sortie.write(str(os.getpid()))
        return True
    except (OSError, ElementTree.ParseError) as erreur:
        log('profils : %r' % erreur)
        return False


def fabriquer_pack():
    """Zippe les réglages d'habillage du profil ouvert. Renvoie (octets, nombre de fichiers)."""
    tampon = BytesIO()
    nombre = 0
    with zipfile.ZipFile(tampon, 'w', zipfile.ZIP_DEFLATED) as archive:
        for nom in DOSSIERS:
            racine = os.path.join(ADDON_DATA, nom)
            for chemin, _, fichiers in os.walk(racine):
                for fichier in fichiers:
                    complet = os.path.join(chemin, fichier)
                    relatif = os.path.relpath(complet, ADDON_DATA).replace(os.sep, '/')
                    if fichier == 'skinusers.json':
                        archive.writestr('addon_data/' + relatif, sans_codes(complet))
                    else:
                        archive.write(complet, 'addon_data/' + relatif)
                    nombre += 1
    return tampon.getvalue(), nombre


def sans_codes(fichier):
    """Profils internes d'Arctic Fuse 3 (Principal, Enfants…) sans leur code
    secret : le pack part sur un dépôt public."""
    with open(fichier, encoding='utf-8') as source:
        profils_internes = json.load(source)
    for profil in profils_internes:
        profil['code'] = None
    return json.dumps(profils_internes, indent=4, ensure_ascii=False)


def pack_du_profil_ouvert():
    """Nom du pack que le profil ouvert alimente, ou None si on annule."""
    if not dans_le_profil_principal():
        return PACK_CATCHUP
    choix = dialog.select('Quelle interface as-tu réglée ?', ['Interface complète', 'Interface allégée (boîtiers modestes)'])
    return (PACK_ALKOFLIX, PACK_LEGER)[choix] if choix >= 0 else None


# --- Publication sur le dépôt (propriétaire seulement) -----------------------

def jeton_de_publication():
    jeton = xbmcaddon.Addon().getSetting('jeton').strip()
    if jeton:
        if not os.path.isfile(FICHIER_JETON) or open(FICHIER_JETON).read() != jeton:
            os.makedirs(os.path.dirname(FICHIER_JETON), exist_ok=True)
            with open(FICHIER_JETON, 'w') as sortie:
                sortie.write(jeton)
        return jeton
    if os.path.isfile(FICHIER_JETON):
        return open(FICHIER_JETON).read().strip()
    return ''


def github(methode, nom_pack, jeton, corps=None):
    """Appelle l'API GitHub sur un pack. Renvoie (code HTTP, réponse décodée)."""
    requete = Request(API_PACKS + nom_pack, method=methode,
                      data=json.dumps(corps).encode('utf-8') if corps else None,
                      headers={'Authorization': 'Bearer ' + jeton,
                               'Accept': 'application/vnd.github+json',
                               'User-Agent': 'script.dark-prophet'})
    try:
        with urlopen(requete, timeout=30) as reponse:
            return reponse.status, json.loads(reponse.read() or b'{}')
    except HTTPError as erreur:
        return erreur.code, {}
    except (URLError, OSError) as erreur:
        log('github : %r' % erreur)
        return 0, {}


def publier_config():
    """Envoie le pack du profil ouvert dans packs/ sur le dépôt, à la place de celui en ligne."""
    jeton = jeton_de_publication()
    nom_pack = pack_du_profil_ouvert()
    if not nom_pack:
        return
    contenu, nombre = fabriquer_pack()
    if not nombre:
        dialog.ok(TITRE, "Aucun réglage d'Arctic Fuse 3 trouvé sur ce profil.")
        return
    if not dialog.yesno(TITRE, "Publier la configuration de ce profil sur le dépôt ?[CR]%s (%s fichiers) remplacera celui en ligne pour tout le monde." % (nom_pack, nombre)):
        return
    code, existant = github('GET', nom_pack, jeton)
    if code not in (200, 404):
        dialog.ok(TITRE, ERREURS_GITHUB.get(code, 'GitHub a répondu une erreur %s.' % code))
        return
    corps = {'message': 'Pack %s publié depuis Kodi' % nom_pack,
             'content': base64.b64encode(contenu).decode('ascii'),
             'committer': SIGNATURE, 'author': SIGNATURE}
    if code == 200:
        corps['sha'] = existant.get('sha')
    code, _ = github('PUT', nom_pack, jeton, corps)
    if code in (200, 201):
        dialog.ok(TITRE, "%s est publié.[CR]Les nouvelles installations le recevront d'ici 5 minutes environ." % nom_pack)
    else:
        dialog.ok(TITRE, ERREURS_GITHUB.get(code, 'GitHub a répondu une erreur %s.' % code))


ERREURS_GITHUB = {
    0: 'GitHub est injoignable. Vérifie la connexion puis relance.',
    401: "GitHub refuse le jeton : il est mal saisi ou expiré.[CR]Corrige-le dans les paramètres de l'extension.",
    403: "Ce jeton n'a pas le droit d'écrire dans le dépôt (permission « Contents : Read and write »).",
    404: "Ce jeton ne donne pas accès au dépôt Kodi.",
    409: "Le pack en ligne a changé pendant l'envoi. Relance la publication.",
}


def rechercher(genre='', sections=''):
    """Recherche par titre limitée au catalogue d'alkoFlix : on ne propose que
    ce qui a des liens. Lancée par les rubriques « Rechercher » des pages :
    RunScript(script.dark-prophet,recherche,<movie|tv>,<sections du catalogue>).
    La recherche par titre d'alkoFlix interroge tout TMDb ; seules ses listes
    « Découvrir » respectent le catalogue, on leur passe donc une recherche
    TMDb. Le filtre par section est celui de « Parce que vous avez regardé »."""
    titres = {'movie': 'Rechercher un film', 'tv': 'Rechercher une série'}
    mot = dialog.input(titres.get(genre, 'Rechercher dans alkoFlix')).strip()
    if not mot:
        return
    cle = xbmcaddon.Addon(ALKOFLIX).getSetting('tmdb_api')
    tmdb = 'https://api.themoviedb.org/3/search/%s?api_key=' + cle + '&language=fr-FR&page=%%s&query=' + quote(mot)
    nom = quote('Recherche : ' + mot)
    if genre in titres:
        mode, action = (('build_movie_list', 'tmdb_movies_discover') if genre == 'movie'
                        else ('build_tvshow_list', 'tmdb_tv_discover'))
        chemin = 'plugin://%s/?mode=%s&action=%s&catalogue_only=true&name=%s' % (ALKOFLIX, mode, action, nom)
        if sections:
            chemin += '&because_you_watched=true&recommendation_group=all&recommendation_catalogue_section=' + quote(sections)
        chemin += '&query=' + quote(tmdb % genre, safe='')
    else:
        chemin = ('plugin://%s/?mode=discover.combined_results&movie_query=%s&tv_query=%s&name=%s&catalogue_only=true'
                  % (ALKOFLIX, quote(tmdb % 'movie', safe=''), quote(tmdb % 'tv', safe=''), nom))
    xbmc.executebuiltin('ActivateWindow(Videos,"%s",return)' % chemin)


def menu():
    lever_verrou_profils()
    if dans_le_profil_principal():
        entrees = [
            ('Formule alkoFlix', formule_alkoflix),
            ('Formule alkoFlix + Catch-up TV', formule_catchup),
        ]
        if xbmc.getSkinDir() == SKIN and installe(ALKOFLIX):
            # Une formule est déjà en place : on propose d'abord la mise à jour et le complément.
            if PROFIL_CATCHUP not in profils():
                entrees.insert(0, ('Ajouter Catch-up TV à mon installation', ajouter_catchup))
            entrees.insert(0, ("Mettre l'interface à jour", mettre_a_jour))
            entrees.append(("Changer le fond d'écran", changer_fond))
        entrees += [
            ('Mes identifiants Catch-up TV', identifiants_catchup),
            ('Réinitialiser les réglages', reinitialiser),
        ]
    else:
        # La réinitialisation supprime ce profil : elle se lance depuis le profil principal.
        entrees = [
            ('Mes identifiants Catch-up TV', identifiants_catchup),
            ('Remettre la configuration Catch-up TV', reappliquer_catchup),
        ]
    if jeton_de_publication():
        entrees.append(('Publier la configuration de ce profil sur le dépôt', publier_config))
    choix = dialog.select(TITRE, [libelle for libelle, _ in entrees])
    if choix >= 0:
        entrees[choix][1]()


if __name__ == '__main__':
    if sys.argv[1:2] == ['recherche']:
        rechercher(*sys.argv[2:4])
    else:
        menu()

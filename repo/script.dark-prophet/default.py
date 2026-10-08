# -*- coding: utf-8 -*-
import base64
import glob
import json
import os
import shutil
import sqlite3
import zipfile
from io import BytesIO
from urllib.error import HTTPError, URLError
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


def telecharger_pack_alkoflix():
    """Le pack du profil alkoFlix. Si une interface allégée est publiée, on
    demande laquelle installer ; sinon la question n'est pas posée."""
    leger = telecharger_pack(PACK_LEGER, muet=True)
    if leger is not None:
        choix = dialog.select('Quel appareil ?', ['Appareil récent : interface complète',
                                                  'Boîtier modeste : interface allégée'])
        if choix == 1:
            return leger
    return telecharger_pack(PACK_ALKOFLIX)


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
    shutil.rmtree(SAUVEGARDE, ignore_errors=True)
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


def appliquer_ici(archive):
    """Applique un pack au profil ouvert et active l'habillage."""
    if archive is None:
        return changer_habillage(SKIN)

    def appliquer():
        sauvegarder_actuel()
        log('%s fichiers écrits' % ecrire_pack(archive, ADDON_DATA))

    return hors_de_l_habillage(appliquer)


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
    if not dialog.yesno(TITRE, "Installer Arctic Fuse 3 et alkoFlix avec la configuration de DaRk-PrOphEt ?[CR]Kodi passera en français. Les réglages actuels de cet habillage seront remplacés (une copie est gardée)."):
        return
    if not installer_tout((LANGUE, SONS, SAISIE, SKIN, ALKOFLIX, ICONES)):
        return
    franciser()
    archive = telecharger_pack_alkoflix()
    if not appliquer_ici(archive):
        dialog.ok(TITRE, "Réglages copiés, mais l'habillage n'a pas pu être activé.[CR]Active Arctic Fuse 3 dans Paramètres > Interface.")
    elif archive is None:
        annoncer("Arctic Fuse 3 et alkoFlix sont installés.[CR]La configuration n'est pas encore publiée : l'habillage garde ses réglages.")
    else:
        annoncer("C'est installé.[CR]Si des menus manquent, redémarre Kodi une fois.")


def formule_catchup():
    if not dialog.yesno(TITRE, "Installer Arctic Fuse 3, alkoFlix et Catch-up TV ?[CR]Au démarrage, Kodi proposera deux entrées : « %s » et « %s ».[CR]Kodi passera en français. Les réglages actuels de l'habillage seront remplacés (une copie est gardée)." % (PROFIL_ALKOFLIX, PROFIL_CATCHUP)):
        return
    if not installer_tout((LANGUE, SONS, SAISIE, SKIN, ALKOFLIX, ICONES, CATCHUP)):
        return
    franciser()
    pack_alkoflix = telecharger_pack_alkoflix()
    pack_catchup = telecharger_pack(PACK_CATCHUP, muet=True) or pack_alkoflix
    if not appliquer_ici(pack_alkoflix):
        dialog.ok(TITRE, "L'habillage n'a pas pu être activé.[CR]Active Arctic Fuse 3 dans Paramètres > Interface, puis relance.")
        return
    preparer_profil_catchup(pack_catchup)


def ajouter_catchup():
    """Pour qui a pris la formule alkoFlix et change d'avis : ajoute Catch-up TV
    et son profil sans toucher aux réglages du profil ouvert."""
    if not dialog.yesno(TITRE, "Ajouter Catch-up TV ?[CR]Au démarrage, Kodi proposera deux entrées : « %s » et « %s ».[CR]Tes réglages actuels ne sont pas modifiés." % (PROFIL_ALKOFLIX, PROFIL_CATCHUP)):
        return
    if not installer_tout((CATCHUP,)):
        return
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

    renomme = insister(renommer_profil_principal, PROFIL_ALKOFLIX)
    ecran = insister(activer_ecran_de_choix)
    retour_accueil()
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
    if not dialog.yesno(TITRE, "Remettre la configuration Catch-up TV de DaRk-PrOphEt sur ce profil ?[CR]Les réglages actuels de l'habillage seront remplacés (une copie est gardée)."):
        return
    archive = telecharger_pack(PACK_CATCHUP)
    if archive is None:
        dialog.ok(TITRE, "La configuration Catch-up TV n'est pas encore publiée.")
    elif appliquer_ici(archive):
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
        lignes.append('Tous les réglages de Catch-up TV…')
        choix = dialog.select('Mes identifiants Catch-up TV', lignes)
        if choix < 0:
            return
        if choix == len(COMPTES):
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


# --- Sauvegarde et export ---------------------------------------------------

def restaurer_avant():
    if not os.path.isdir(SAUVEGARDE):
        dialog.ok(TITRE, "Aucune copie des réglages d'avant sur ce profil.")
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
    annoncer("Réglages d'avant remis en place.")


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


def exporter_config():
    """Enregistre le pack du profil ouvert dans un dossier (à faire sur l'appareil déjà configuré)."""
    nom_pack = pack_du_profil_ouvert()
    if not nom_pack:
        return
    dossier = dialog.browse(3, 'Où enregistrer %s ?' % nom_pack, 'files')
    if not dossier:
        return
    contenu, nombre = fabriquer_pack()
    if not nombre:
        dialog.ok(TITRE, "Aucun réglage d'Arctic Fuse 3 trouvé sur ce profil.")
        return
    # xbmcvfs sait écrire sur un partage réseau ou une clé USB, pas open().
    cible = dossier + nom_pack
    sortie = xbmcvfs.File(cible, 'w')
    reussi = sortie.write(bytearray(contenu))
    sortie.close()
    if reussi:
        dialog.ok(TITRE, 'Pack enregistré (%s fichiers) :[CR]%s' % (nombre, cible))
    else:
        dialog.ok(TITRE, "Écriture impossible dans ce dossier.")


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


def menu():
    if dans_le_profil_principal():
        entrees = [
            ('Formule alkoFlix', formule_alkoflix),
            ('Formule alkoFlix + Catch-up TV', formule_catchup),
        ]
        if xbmc.getSkinDir() == SKIN and installe(ALKOFLIX) and PROFIL_CATCHUP not in profils():
            # La formule alkoFlix est déjà en place : on propose d'abord le complément.
            entrees.insert(0, ('Ajouter Catch-up TV à mon installation', ajouter_catchup))
        entrees += [
            ('Mes identifiants Catch-up TV', identifiants_catchup),
            ("Remettre mes réglages d'avant", restaurer_avant),
            ('Exporter la configuration alkoFlix de cet appareil', exporter_config),
        ]
    else:
        entrees = [
            ('Mes identifiants Catch-up TV', identifiants_catchup),
            ('Remettre la configuration Catch-up TV', reappliquer_catchup),
            ("Remettre mes réglages d'avant", restaurer_avant),
            ('Exporter la configuration Catch-up TV de ce profil', exporter_config),
        ]
    if jeton_de_publication():
        entrees.append(('Publier la configuration de ce profil sur le dépôt', publier_config))
    choix = dialog.select(TITRE, [libelle for libelle, _ in entrees])
    if choix >= 0:
        entrees[choix][1]()


if __name__ == '__main__':
    menu()

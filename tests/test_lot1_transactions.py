# -*- coding: utf-8 -*-
"""Tests du Lot 1 : sauvegarde, application des packs et restauration sans perte,
y compris après une coupure à n'importe quelle étape. Sans Kodi :

    python3 -I tests/test_lot1_transactions.py

Une « coupure » est simulée par une exception que le code ne peut pas intercepter
(comme un arrêt brutal) au N-ième appel système de fichiers ; on relance ensuite la
reprise, comme le ferait Kodi au démarrage suivant.
"""
import errno
import io
import os
import shutil
import sys
import tempfile
import types
import unittest
import zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from kodi_factice import SANDBOX, SKIN, default as d, xbmc   # noqa: E402

VARIABLES = 'script.skinvariables'
ANCIEN = {SKIN + '/settings.xml': b'<settings>ANCIEN</settings>', SKIN + '/extra.xml': b'<a/>',
          VARIABLES + '/a.json': b'{"ancien": 1}'}
NOUVEAU = {SKIN + '/settings.xml': b'<settings>NOUVEAU</settings>', VARIABLES + '/b.json': b'{"nouveau": 1}',
           VARIABLES + '/nodes/c.json': b'[]'}


def pack(contenu=NOUVEAU):
    tampon = io.BytesIO()
    with zipfile.ZipFile(tampon, 'w', zipfile.ZIP_DEFLATED) as z:
        for nom, donnees in contenu.items():
            z.writestr('addon_data/' + nom, donnees)
    return zipfile.ZipFile(io.BytesIO(tampon.getvalue()))


def poser(racine, contenu):
    for nom, donnees in contenu.items():
        chemin = os.path.join(racine, *nom.split('/'))
        os.makedirs(os.path.dirname(chemin), exist_ok=True)
        with open(chemin, 'wb') as sortie:
            sortie.write(donnees)


def etat(racine):
    """Contenu des dossiers d'habillage du profil (le reste n'est pas concerné)."""
    contenu = {}
    for dossier in d.DOSSIERS:
        for chemin, _, fichiers in os.walk(os.path.join(racine, dossier)):
            for fichier in fichiers:
                complet = os.path.join(chemin, fichier)
                with open(complet, 'rb') as source:
                    contenu[os.path.relpath(complet, racine).replace(os.sep, '/')] = source.read()
    return contenu


class Coupure(BaseException):
    """Arrêt brutal : aucun except du code ne l'attrape."""


class Panne:
    """Fait échouer le N-ième appel aux fonctions de fichiers utilisées par les transactions.
    mode 'coupure' : arrêt brutal ; 'erreur' : OSError une fois ; 'persistante' : OSError
    sur ce renommage et tous les suivants (droits refusés, stockage retiré…)."""
    CIBLES = ((os, 'replace'), (os, 'makedirs'), (os, 'fsync'), (shutil, 'rmtree'), (shutil, 'copyfileobj'),
              (shutil, 'copytree'))

    def __init__(self, numero=None, mode='coupure', erreur=errno.EIO):
        self.numero, self.mode, self.erreur, self.appels, self.vrais = numero, mode, erreur, 0, {}

    def __enter__(self):
        for module, nom in self.CIBLES:
            vraie = getattr(module, nom)
            self.vrais[(module, nom)] = vraie
            setattr(module, nom, self.envelopper(nom, vraie))
        return self

    def __exit__(self, *a):
        for (module, nom), vraie in self.vrais.items():
            setattr(module, nom, vraie)

    def envelopper(self, nom, vraie):
        def appel(*args, **kwargs):
            self.appels += 1
            touche = self.numero is not None and (self.appels == self.numero or
                                                  (self.mode == 'persistante' and self.appels > self.numero and nom == 'replace'))
            if touche:
                if self.mode == 'coupure':
                    raise Coupure('%s n°%d' % (nom, self.appels))
                if nom == 'rmtree' and kwargs.get('ignore_errors'):
                    return None
                raise OSError(self.erreur, os.strerror(self.erreur))
            return vraie(*args, **kwargs)
        return appel


class Base(unittest.TestCase):
    def setUp(self):
        self.racine = tempfile.mkdtemp(dir=SANDBOX)
        d.ADDON_DATA = self.racine
        d.SAUVEGARDE = os.path.join(self.racine, 'script.dark-prophet', 'sauvegarde')
        poser(self.racine, ANCIEN)
        self.messages = []
        d.dialog = types.SimpleNamespace(ok=lambda *a: self.messages.append(a[-1]), yesno=lambda *a: True)
        self.vrai_place = d.place_libre
        xbmc.habillage = SKIN
        xbmc.commandes[:] = []

    def tearDown(self):
        d.place_libre = self.vrai_place

    def sans_residu(self, racine=None):
        t = d.dossier_transaction(racine or self.racine)
        self.assertFalse(os.path.exists(t) or os.path.exists(t + '.fin'), 'transaction restée')
        self.assertFalse(os.path.exists(d.SAUVEGARDE + '.tmp'), 'sauvegarde provisoire restée')


class Sauvegarde(Base):
    def test_premiere_sauvegarde(self):
        d.sauvegarder_actuel()
        self.assertEqual(etat(d.SAUVEGARDE), ANCIEN)
        self.sans_residu()

    def test_existante_jamais_ecrasee(self):
        d.sauvegarder_actuel()
        poser(self.racine, {SKIN + '/settings.xml': b'MODIFIE'})
        d.sauvegarder_actuel()
        self.assertEqual(etat(d.SAUVEGARDE), ANCIEN)

    def test_ancienne_sauvegarde_sans_controle_gardee_telle_quelle(self):
        """Une sauvegarde d'avant le Lot 1 ne peut pas être vérifiée : elle reste la référence
        (la refaire maintenant copierait la configuration installée, pas celle d'origine)."""
        poser(d.SAUVEGARDE, {SKIN + '/settings.xml': b'ORIGINE PARTIELLE'})
        d.sauvegarder_actuel()
        self.assertEqual(etat(d.SAUVEGARDE), {SKIN + '/settings.xml': b'ORIGINE PARTIELLE'})

    def test_interrompue_puis_refaite(self):
        for numero in range(1, 30):
            with self.subTest(coupure=numero):
                shutil.rmtree(os.path.dirname(d.SAUVEGARDE), ignore_errors=True)
                try:
                    with Panne(numero):
                        d.sauvegarder_actuel()
                except Coupure:
                    pass
                # Jamais une sauvegarde partielle sous son vrai nom :
                if os.path.isdir(d.SAUVEGARDE):
                    self.assertEqual(etat(d.SAUVEGARDE), ANCIEN)
                self.assertEqual(etat(self.racine), ANCIEN)
                d.sauvegarder_actuel()   # tentative suivante
                self.assertEqual(etat(d.SAUVEGARDE), ANCIEN)
                self.sans_residu()

    def test_dossier_provisoire_deja_la(self):
        poser(d.SAUVEGARDE + '.tmp', {'debris': b'x', SKIN + '/settings.xml': b'PARTIEL'})
        d.sauvegarder_actuel()
        self.assertEqual(etat(d.SAUVEGARDE), ANCIEN)
        self.sans_residu()

    def test_stockage_plein(self):
        with Panne(3, mode='erreur', erreur=errno.ENOSPC):
            with self.assertRaises(d.PackNonApplique) as refus:
                d.sauvegarder_actuel()
        self.assertIn('stockage plein', str(refus.exception))
        self.assertFalse(os.path.exists(d.SAUVEGARDE))
        self.sans_residu()
        d.sauvegarder_actuel()   # deuxième exécution après l'échec
        self.assertEqual(etat(d.SAUVEGARDE), ANCIEN)

    def test_place_insuffisante_annoncee_avant_tout(self):
        d.place_libre = lambda chemin: 1000
        with self.assertRaises(d.PackNonApplique):
            d.sauvegarder_actuel()
        self.assertFalse(os.path.exists(d.SAUVEGARDE))

    def test_echec_de_sauvegarde_bloque_l_application(self):
        d.changer_habillage = lambda skin: True
        d.ajuster_menu_options = lambda *a, **k: None
        with Panne(3, mode='erreur', erreur=errno.ENOSPC):
            with self.assertRaises(d.PackNonApplique):
                d.appliquer_ici(pack())
        self.assertEqual(etat(self.racine), ANCIEN)
        self.sans_residu()


class Application(Base):
    def test_pack_valide(self):
        self.assertEqual(d.ecrire_pack(pack(), self.racine), 3)
        self.assertEqual(etat(self.racine), NOUVEAU)
        self.sans_residu()

    def test_reinstallation_du_meme_pack(self):
        for _ in range(3):
            d.ecrire_pack(pack(), self.racine)
        self.assertEqual(etat(self.racine), NOUVEAU)
        self.sans_residu()

    def test_pack_corrompu_ou_incomplet(self):
        brut = bytearray(b'')
        tampon = io.BytesIO()
        with zipfile.ZipFile(tampon, 'w', zipfile.ZIP_STORED) as z:
            z.writestr('addon_data/%s/settings.xml' % SKIN, '<settings>' + 'A' * 300 + '</settings>')
        brut = bytearray(tampon.getvalue())
        brut[brut.index(b'AAAA') + 10] ^= 0xFF
        for archive in (zipfile.ZipFile(io.BytesIO(bytes(brut))), pack({VARIABLES + '/b.json': b'{}'})):
            with self.assertRaises(d.PackNonApplique):
                d.ecrire_pack(archive, self.racine)
            self.assertEqual(etat(self.racine), ANCIEN)
            self.sans_residu()

    def test_premiere_installation_sans_dossiers(self):
        vide = tempfile.mkdtemp(dir=SANDBOX)
        d.ecrire_pack(pack(), vide)
        self.assertEqual(etat(vide), NOUVEAU)

    def test_place_insuffisante_ou_inconnue(self):
        d.place_libre = lambda chemin: 10
        with self.assertRaises(d.PackNonApplique) as refus:
            d.ecrire_pack(pack(), self.racine)
        self.assertIn('Pas assez de place', str(refus.exception))
        self.assertEqual(etat(self.racine), ANCIEN)
        self.sans_residu()
        d.place_libre = lambda chemin: None   # l'appareil ne dit rien : on continue, prudemment
        d.ecrire_pack(pack(), self.racine)
        self.assertEqual(etat(self.racine), NOUVEAU)

    def test_stockage_plein_pendant_la_copie(self):
        with Panne(9, mode='erreur', erreur=errno.ENOSPC) as panne:
            with self.assertRaises(d.PackNonApplique) as refus:
                d.ecrire_pack(pack(), self.racine)
        self.assertIn('stockage plein', str(refus.exception))
        self.assertEqual(etat(self.racine), ANCIEN)
        self.sans_residu()

    def compter(self, operation):
        with Panne() as panne:
            operation()
        return panne.appels

    def test_erreur_a_chaque_etape(self):
        """Une erreur (pas une coupure) à n'importe quel appel : jamais un mélange, jamais d'autre exception."""
        total = self.compter(lambda: d.ecrire_pack(pack(), tempfile.mkdtemp(dir=SANDBOX)))
        self.assertGreater(total, 20)
        for mode in ('erreur', 'persistante'):
            for numero in range(1, total + 1):
                with self.subTest(mode=mode, appel=numero):
                    racine = tempfile.mkdtemp(dir=SANDBOX)
                    poser(racine, ANCIEN)
                    message = ''
                    with Panne(numero, mode=mode):
                        try:
                            d.ecrire_pack(pack(), racine)
                        except d.PackNonApplique as refus:
                            message = str(refus)
                    if "n'ont pas été modifiés" in message or 'ont été remis' in message:
                        self.assertEqual(etat(racine), ANCIEN)
                    elif not message:
                        self.assertEqual(etat(racine), NOUVEAU)
                    d.reprendre(racine)   # lancement suivant
                    if 'seront remis' in message:      # annulation engagée : on la termine
                        self.assertEqual(etat(racine), ANCIEN)
                    elif 'sera terminée' in message:   # bascule engagée : on la termine
                        self.assertEqual(etat(racine), NOUVEAU)
                    self.assertIn(etat(racine), (ANCIEN, NOUVEAU))
                    self.sans_residu(racine)

    def test_coupure_a_chaque_etape_puis_reprise(self):
        """Coupure à chaque appel, puis coupure pendant la reprise, puis reprise complète."""
        total = self.compter(lambda: d.ecrire_pack(pack(), tempfile.mkdtemp(dir=SANDBOX)))
        for numero in range(1, total + 1):
            for seconde in (None, 1, 2, 3, 4, 5, 6):
                with self.subTest(coupure=numero, pendant_la_reprise=seconde):
                    racine = tempfile.mkdtemp(dir=SANDBOX)
                    poser(racine, ANCIEN)
                    try:
                        with Panne(numero):
                            d.ecrire_pack(pack(), racine)
                    except Coupure:
                        pass
                    bascule = d.lire_etape(d.dossier_transaction(racine)) == 'bascule'
                    if seconde:
                        try:
                            with Panne(seconde):
                                d.reprendre(racine)
                        except Coupure:
                            pass
                    d.reprendre(racine)
                    # Tout l'un ou tout l'autre, jamais un mélange des deux versions :
                    self.assertIn(etat(racine), (ANCIEN, NOUVEAU))
                    if bascule:
                        self.assertEqual(etat(racine), NOUVEAU)
                    self.sans_residu(racine)

    def coupure_sur(self, condition):
        vrai = os.replace

        def remplacer(source, cible):
            if condition(source, cible):
                raise Coupure(source)
            return vrai(source, cible)
        os.replace = remplacer
        try:
            d.ecrire_pack(pack(), self.racine)
        except Coupure:
            pass
        finally:
            os.replace = vrai

    def test_coupure_avant_activation(self):
        def vers_bascule(source, cible):
            if not cible.endswith('etape'):
                return False
            with open(source) as etape:
                return etape.read() == 'bascule'
        self.coupure_sur(vers_bascule)
        self.assertEqual(etat(self.racine), ANCIEN)
        self.assertEqual(d.reprendre(self.racine), 'abandonnee')
        self.assertEqual(etat(self.racine), ANCIEN)
        self.sans_residu()

    def test_coupure_apres_deplacement_de_l_ancien(self):
        self.coupure_sur(lambda s, c: s.endswith(os.path.join('nouveau', SKIN)))
        self.assertFalse(os.path.exists(os.path.join(self.racine, SKIN)))
        self.assertEqual(d.reprendre(self.racine), 'terminee')
        self.assertEqual(etat(self.racine), NOUVEAU)
        self.sans_residu()

    def test_coupure_puis_kodi_recree_le_dossier_par_defaut(self):
        self.coupure_sur(lambda s, c: s.endswith(os.path.join('nouveau', SKIN)))
        poser(self.racine, {SKIN + '/settings.xml': b'<settings>DEFAUT KODI</settings>'})
        d.reprendre(self.racine)
        self.assertEqual(etat(self.racine), NOUVEAU)
        self.sans_residu()

    def test_coupure_apres_activation(self):
        self.coupure_sur(lambda s, c: c.endswith('transaction.fin'))
        self.assertEqual(etat(self.racine), NOUVEAU)
        d.reprendre(self.racine)
        self.assertEqual(etat(self.racine), NOUVEAU)
        self.sans_residu()

    def test_fichiers_en_lecture_seule(self):
        chemin = os.path.join(self.racine, SKIN, 'extra.xml')
        os.chmod(chemin, 0o444)
        d.ecrire_pack(pack(), self.racine)
        self.assertEqual(etat(self.racine), NOUVEAU)
        self.sans_residu()


class PlusieursProfils(Base):
    def setUp(self):
        super().setUp()
        self.catchup = os.path.join(self.racine, 'profiles', 'Catch-up TV', 'addon_data')
        poser(self.catchup, ANCIEN)

    def test_echec_sur_un_profil_n_affecte_pas_l_autre(self):
        d.ecrire_pack(pack(), self.catchup)
        with Panne(12, mode='erreur', erreur=errno.ENOSPC):
            with self.assertRaises(d.PackNonApplique):
                d.ecrire_pack(pack(), self.racine)
        self.assertEqual(etat(self.catchup), NOUVEAU)
        self.assertEqual(etat(self.racine), ANCIEN)
        d.ecrire_pack(pack(), self.racine)   # nouvelle tentative
        self.assertEqual(etat(self.racine), NOUVEAU)

    def test_transaction_d_un_profil_isolee(self):
        try:
            with Panne(self.trouver_bascule(), mode='coupure'):
                d.ecrire_pack(pack(), self.catchup)
        except Coupure:
            pass
        self.assertTrue(d.transaction_en_attente(self.catchup))
        d.ecrire_pack(pack(), self.racine)
        self.assertTrue(d.transaction_en_attente(self.catchup))   # pas touchée depuis l'autre profil
        d.ecrire_pack(pack(), self.catchup)                        # reprise, puis nouvelle application
        self.assertEqual(etat(self.catchup), NOUVEAU)
        self.sans_residu(self.catchup)

    def trouver_bascule(self):
        """Numéro d'appel qui tombe juste après l'activation du premier dossier."""
        racine = tempfile.mkdtemp(dir=SANDBOX)
        poser(racine, ANCIEN)
        with Panne() as panne:
            d.ecrire_pack(pack(), racine)
        for numero in range(1, panne.appels):
            essai = tempfile.mkdtemp(dir=SANDBOX)
            poser(essai, ANCIEN)
            try:
                with Panne(numero):
                    d.ecrire_pack(pack(), essai)
            except Coupure:
                if d.lire_etape(d.dossier_transaction(essai)) == 'bascule' and \
                        os.path.isdir(os.path.join(d.dossier_transaction(essai), 'ancien')):
                    return numero
        self.fail('étape de bascule introuvable')


class Restauration(Base):
    def setUp(self):
        super().setUp()
        d.sauvegarder_actuel()
        d.ecrire_pack(pack(), self.racine)   # installation : la configuration du pack est en place

    def test_sauvegarde_valide(self):
        d.remettre_sauvegarde()
        self.assertEqual(etat(self.racine), ANCIEN)
        self.assertEqual(etat(d.SAUVEGARDE), ANCIEN)
        self.sans_residu()

    def test_sauvegarde_partielle_remise_telle_quelle(self):
        shutil.rmtree(os.path.join(d.SAUVEGARDE, VARIABLES))
        d.remettre_sauvegarde()
        self.assertEqual(etat(self.racine), {k: v for k, v in ANCIEN.items() if k.startswith(SKIN)})

    def test_echec_de_copie_puis_nouvelle_tentative(self):
        with Panne(8, mode='erreur', erreur=errno.ENOSPC):
            with self.assertRaises(d.PackNonApplique):
                d.remettre_sauvegarde()
        self.assertEqual(etat(self.racine), NOUVEAU)
        self.assertEqual(etat(d.SAUVEGARDE), ANCIEN)
        self.sans_residu()
        d.remettre_sauvegarde()
        self.assertEqual(etat(self.racine), ANCIEN)

    def test_echec_ou_coupure_a_chaque_etape(self):
        with Panne() as panne:
            d.remettre_sauvegarde()
        total = panne.appels
        d.ecrire_pack(pack(), self.racine)
        for mode in ('erreur', 'persistante', 'coupure'):
            for numero in range(1, total + 1):
                with self.subTest(mode=mode, appel=numero):
                    try:
                        with Panne(numero, mode=mode):
                            d.remettre_sauvegarde()
                    except (d.PackNonApplique, Coupure):
                        pass
                    self.assertEqual(etat(d.SAUVEGARDE), ANCIEN)   # la source n'est jamais touchée
                    d.reprendre(self.racine)
                    self.assertIn(etat(self.racine), (ANCIEN, NOUVEAU))
                    self.sans_residu()
                    d.ecrire_pack(pack(), self.racine)

    def test_reinitialiser_s_arrete_sans_rien_effacer(self):
        d.profils = lambda: []
        changements = []
        d.changer_habillage = lambda skin: changements.append(skin) or True
        poser(os.path.dirname(d.ETAT_AVANT), {'etat_avant.json': b'{}'})
        d.ETAT_AVANT = os.path.join(os.path.dirname(d.ETAT_AVANT), 'etat_avant.json')
        vrai = d.remettre_sauvegarde
        d.remettre_sauvegarde = lambda: (_ for _ in ()).throw(d.PackNonApplique('Remise impossible.'))
        try:
            d.reinitialiser()
        finally:
            d.remettre_sauvegarde = vrai
        self.assertEqual(changements, [d.SKIN_SECOURS, SKIN])   # on revient où l'on était
        self.assertTrue(os.path.isdir(d.SAUVEGARDE))
        self.assertTrue(os.path.isfile(d.ETAT_AVANT))
        self.assertIn('Remise impossible.', self.messages[-1])

    def test_reinitialiser_complet(self):
        d.profils = lambda: []
        d.changer_habillage = lambda skin: True
        d.rpc = lambda *a, **k: {}
        d.reinitialiser()
        self.assertEqual(etat(self.racine), ANCIEN)
        self.assertFalse(os.path.exists(d.SAUVEGARDE))   # effacée seulement après réussite
        self.sans_residu()


class Reprise(Base):
    def interrompre(self):
        vrai = os.replace

        def remplacer(source, cible):
            if source.endswith(os.path.join('nouveau', SKIN)):
                raise Coupure(source)
            return vrai(source, cible)
        os.replace = remplacer
        try:
            d.ecrire_pack(pack(), self.racine)
        except Coupure:
            pass
        finally:
            os.replace = vrai

    def test_service_ne_touche_pas_l_habillage_charge(self):
        self.interrompre()
        d.reprendre_au_demarrage()
        self.assertTrue(d.transaction_en_attente(self.racine))
        self.assertTrue(any(c.startswith('Notification(') for c in xbmc.commandes))

    def test_service_termine_si_l_habillage_n_est_pas_charge(self):
        self.interrompre()
        xbmc.habillage = 'skin.estuary'
        d.reprendre_au_demarrage()
        self.assertEqual(etat(self.racine), NOUVEAU)
        self.sans_residu()

    def test_assistant_quitte_l_habillage_puis_termine(self):
        self.interrompre()
        changements = []
        d.changer_habillage = lambda skin: changements.append(skin) or True
        d.reprendre_au_lancement()
        self.assertEqual(changements, [d.SKIN_SECOURS, SKIN])
        self.assertEqual(etat(self.racine), NOUVEAU)
        self.assertEqual(len(self.messages), 1)
        self.sans_residu()

    def test_habillage_remis_meme_si_l_application_echoue(self):
        changements = []
        d.changer_habillage = lambda skin: changements.append(skin) or True

        def echoue():
            raise d.PackNonApplique('non')
        with self.assertRaises(d.PackNonApplique):
            d.hors_de_l_habillage(echoue)
        self.assertEqual(changements, [d.SKIN_SECOURS, SKIN])


class AnnulationInterrompue(Base):
    """B1 : une annulation engagée est terminée à la reprise, jamais transformée en installation."""

    def echec_puis_coupure_pendant_l_annulation(self, racine, numero_coupure):
        """Erreur sur le 2e renommage de dossier vers sa place, puis coupure au N-ième appel de l'annulation."""
        vrai = os.replace
        etat_panne = {'erreur': False, 'appels': 0}

        def remplacer(source, cible):
            if not etat_panne['erreur'] and source.endswith(os.path.join('nouveau', VARIABLES)):
                etat_panne['erreur'] = True
                raise OSError(errno.EIO, 'panne')
            if etat_panne['erreur']:
                etat_panne['appels'] += 1
                if etat_panne['appels'] == numero_coupure:
                    raise Coupure(source)
            return vrai(source, cible)
        os.replace = remplacer
        try:
            d.ecrire_pack(pack(), racine)
        except (Coupure, d.PackNonApplique):
            pass
        finally:
            os.replace = vrai
        return etat_panne['appels'] >= numero_coupure

    def test_annulation_interrompue_a_chaque_pas(self):
        for numero in range(1, 8):
            for seconde in (None, 1, 2, 3):
                with self.subTest(coupure=numero, pendant_la_reprise=seconde):
                    racine = tempfile.mkdtemp(dir=SANDBOX)
                    poser(racine, ANCIEN)
                    self.echec_puis_coupure_pendant_l_annulation(racine, numero)
                    # Coupure avant que la décision d'annuler soit écrite : la bascule (complète,
                    # vérifiée) est terminée. Une fois « annulation » notée : retour à l'ancien.
                    attendu = NOUVEAU if d.lire_etape(d.dossier_transaction(racine)) == 'bascule' else ANCIEN
                    if seconde:
                        try:
                            with Panne(seconde):
                                d.reprendre(racine)
                        except Coupure:
                            pass
                    d.reprendre(racine)
                    self.assertEqual(etat(racine), attendu)
                    self.sans_residu(racine)

    def test_annulation_interrompue_ancien_dossier_absent(self):
        racine = tempfile.mkdtemp(dir=SANDBOX)
        poser(racine, {k: v for k, v in ANCIEN.items() if k.startswith(SKIN)})   # pas de dossier Skin Variables
        avant = etat(racine)
        for numero in range(2, 6):   # coupure une fois l'annulation notée
            with self.subTest(coupure=numero):
                racine = tempfile.mkdtemp(dir=SANDBOX)
                poser(racine, {k: v for k, v in ANCIEN.items() if k.startswith(SKIN)})
                self.echec_puis_coupure_pendant_l_annulation(racine, numero)
                self.assertIn(d.lire_etape(d.dossier_transaction(racine)), ('annulation', 'annulee'))
                d.reprendre(racine)
                self.assertEqual(etat(racine), avant)   # Skin Variables : toujours sans fichier
                self.sans_residu(racine)

    def test_annulation_interrompue_et_dossier_recree_par_kodi(self):
        racine = tempfile.mkdtemp(dir=SANDBOX)
        poser(racine, ANCIEN)
        self.echec_puis_coupure_pendant_l_annulation(racine, 2)   # l'actuel est parti dans « nouveau »
        poser(racine, {SKIN + '/settings.xml': b'<settings>DEFAUT KODI</settings>'})
        self.assertEqual(d.reprendre(racine), 'annulee')
        self.assertEqual(etat(racine), ANCIEN)
        self.sans_residu(racine)


class Concurrence(Base):
    """B2 : un seul lancement à la fois par profil ; renommages sur un même stockage."""

    def test_profil_occupe_par_ce_kodi(self):
        d.ecrire_pack(pack(), self.racine)
        verrou = os.path.join(self.racine, 'script.dark-prophet', 'verrou')
        with open(verrou, 'w') as sortie:
            sortie.write(str(os.getpid()))
        with self.assertRaises(d.PackNonApplique) as refus:
            d.ecrire_pack(pack(ANCIEN), self.racine)
        self.assertIn('autre opération', str(refus.exception))
        self.assertEqual(etat(self.racine), NOUVEAU)
        self.assertTrue(os.path.isfile(verrou))   # celui de l'autre lancement n'est pas retiré
        os.remove(verrou)

    def test_verrou_laisse_par_un_kodi_arrete(self):
        verrou = os.path.join(self.racine, 'script.dark-prophet', 'verrou')
        poser(self.racine, {'script.dark-prophet/verrou': b'999999999'})
        d.ecrire_pack(pack(), self.racine)
        self.assertEqual(etat(self.racine), NOUVEAU)
        self.assertFalse(os.path.exists(verrou))

    def test_deuxieme_lancement_pendant_la_bascule_refuse(self):
        vrai = os.replace
        resultats = []

        def remplacer(source, cible):
            if source.endswith(os.path.join('nouveau', SKIN)) and not resultats:
                try:
                    d.ecrire_pack(pack(ANCIEN), self.racine)
                    resultats.append('acceptée')
                except d.PackNonApplique:
                    resultats.append('refusée')
            return vrai(source, cible)
        os.replace = remplacer
        try:
            d.ecrire_pack(pack(), self.racine)
        finally:
            os.replace = vrai
        self.assertEqual(resultats, ['refusée'])
        self.assertEqual(etat(self.racine), NOUVEAU)
        self.sans_residu()

    def test_service_reporte_si_occupe(self):
        try:
            with Panne(self.premiere_bascule()):
                d.ecrire_pack(pack(), self.racine)
        except Coupure:
            pass
        poser(self.racine, {'script.dark-prophet/verrou': str(os.getpid()).encode()})
        xbmc.habillage = 'skin.estuary'
        d.reprendre_au_demarrage()   # ne lève rien, ne touche à rien
        self.assertTrue(d.transaction_en_attente(self.racine))
        os.remove(os.path.join(self.racine, 'script.dark-prophet', 'verrou'))
        d.reprendre_au_demarrage()
        self.assertEqual(etat(self.racine), NOUVEAU)
        self.sans_residu()

    def premiere_bascule(self):
        with Panne() as panne:
            d.ecrire_pack(pack(), tempfile.mkdtemp(dir=SANDBOX))
        for numero in range(1, panne.appels):
            essai = tempfile.mkdtemp(dir=SANDBOX)
            poser(essai, ANCIEN)
            try:
                with Panne(numero):
                    d.ecrire_pack(pack(), essai)
            except Coupure:
                if d.lire_etape(d.dossier_transaction(essai)) == 'bascule':
                    return numero + 1
        self.fail('bascule introuvable')

    def test_stockages_differents_refuses_avant_tout(self):
        vrai = os.stat

        def faux_stat(chemin, *a, **k):
            resultat = vrai(chemin, *a, **k)
            if str(chemin).endswith(os.path.join('transaction', 'nouveau')):
                valeurs = list(resultat)
                valeurs[2] += 1   # st_dev différent
                return os.stat_result(valeurs)
            return resultat
        os.stat = faux_stat
        try:
            with self.assertRaises(d.PackNonApplique) as refus:
                d.ecrire_pack(pack(), self.racine)
        finally:
            os.stat = vrai
        self.assertIn('stockages différents', str(refus.exception))
        self.assertEqual(etat(self.racine), ANCIEN)
        self.sans_residu()


class AnciennesSauvegardes(Base):
    """B4 : sauvegardes d'avant la 1.17.7 et réinitialisation qui échoue en route."""

    def setUp(self):
        super().setUp()
        poser(d.SAUVEGARDE, ANCIEN)   # sauvegarde « ancienne » : faite sans contrôle
        d.ecrire_pack(pack(), self.racine)

    def test_ancienne_sauvegarde_conservee_et_remise(self):
        d.sauvegarder_actuel()
        self.assertEqual(etat(d.SAUVEGARDE), ANCIEN)
        d.remettre_sauvegarde()
        self.assertEqual(etat(self.racine), ANCIEN)

    def test_ancienne_sauvegarde_illisible_ne_detruit_rien(self):
        poser(d.SAUVEGARDE, {SKIN + '/settings.xml': b'<settings><setting id="a">1</sett'})
        with self.assertRaises(d.PackNonApplique) as refus:
            d.remettre_sauvegarde()
        self.assertIn('illisible', str(refus.exception))
        self.assertEqual(etat(self.racine), NOUVEAU)
        self.assertTrue(os.path.isfile(os.path.join(d.SAUVEGARDE, SKIN, 'settings.xml')))
        self.sans_residu()

    def test_ancienne_sauvegarde_sans_droit_de_lecture(self):
        dossier = os.path.join(d.SAUVEGARDE, VARIABLES)
        os.chmod(dossier, 0o000)
        try:
            with self.assertRaises(d.PackNonApplique):
                d.remettre_sauvegarde()
        finally:
            os.chmod(dossier, 0o755)
        self.assertEqual(etat(self.racine), NOUVEAU)
        self.sans_residu()

    def test_reinitialisation_profils_en_echec_n_efface_rien(self):
        d.profils = lambda: []
        d.changer_habillage = lambda skin: True
        d.rpc = lambda *a, **k: {}
        poser(os.path.dirname(d.ETAT_AVANT), {'etat_avant.json': b'{"profil": "Mon profil"}'})
        d.ETAT_AVANT = os.path.join(os.path.dirname(d.ETAT_AVANT), 'etat_avant.json')
        vrai = d.remettre_profil_unique
        d.remettre_profil_unique = lambda nom: None
        try:
            d.reinitialiser()
        finally:
            d.remettre_profil_unique = vrai
        self.assertEqual(etat(self.racine), ANCIEN)          # réglages remis
        self.assertTrue(os.path.isdir(d.SAUVEGARDE))          # sauvegarde gardée
        self.assertTrue(os.path.isfile(d.ETAT_AVANT))         # état d'avant gardé (nom du profil compris)
        self.assertIn('Relance', self.messages[-1])

    def test_remettre_profil_unique_signale_l_echec(self):
        vrai = d.FICHIER_PROFILS
        d.FICHIER_PROFILS = os.path.join(self.racine, 'profiles.xml')
        try:
            self.assertFalse(d.remettre_profil_unique('X'))   # absent : un seul profil, rien à faire
            poser(self.racine, {'profiles.xml': b'<profiles><profile>'})
            self.assertIsNone(d.remettre_profil_unique('X'))  # illisible : échec signalé
        finally:
            d.FICHIER_PROFILS = vrai


if __name__ == '__main__':
    try:
        unittest.main(verbosity=1)
    finally:
        shutil.rmtree(SANDBOX, ignore_errors=True)

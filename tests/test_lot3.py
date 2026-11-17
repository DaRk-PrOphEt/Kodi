# -*- coding: utf-8 -*-
"""Tests de la préparation 1.17.7 : derniers scénarios du verrou (plusieurs processus, arrêts
simulés à chaque étape) et contrôle de la place avant une installation volumineuse. Sans Kodi :

    python3 -I tests/test_lot3.py
"""
import json
import os
import shutil
import signal
import subprocess
import sys
import time
import types
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from kodi_factice import SANDBOX, SKIN, default as d   # noqa: E402
from test_lot1_transactions import ANCIEN, NOUVEAU, Base, Panne, etat, pack, poser   # noqa: E402
import errno   # noqa: E402
from test_lot2 import REPRENEUR, pid_disparu   # noqa: E402

ICI = os.path.dirname(os.path.abspath(__file__))

# Processus qui s'arrête net à l'étape demandée (il annonce « bloque » puis attend qu'on le tue,
# ou qu'on lui dise de continuer par une ligne sur son entrée).
#   vide        : verrou créé, contenu pas encore écrit
#   marque      : marque de reprise créée, rien d'autre
#   lecture     : verrou relu sous la marque, pas encore remplacé
#   remplacement: juste avant de remplacer le verrou abandonné
#   bascule     : application d'un pack, juste avant la bascule (sans /proc : le battement décide)
CROCHET = r'''
import os, shutil, sys, time
sys.path.insert(0, sys.argv[1])
from kodi_factice import SANDBOX, default as d
racine, etape = sys.argv[2], sys.argv[3]
d.BATTEMENT = 0.05

def arret():
    print('bloque', flush=True)
    sys.stdin.readline()

if etape == 'vide':
    vrai = d.ecrire_verrou
    def ecrire(fichier, contenu, _fait=[]):
        if not _fait and fichier.endswith('verrou'):
            _fait.append(1); arret()
        return vrai(fichier, contenu)
    d.ecrire_verrou = ecrire
elif etape == 'marque':
    vrai_open = os.open
    def ouvrir(chemin, *a, _fait=[]):
        fd = vrai_open(chemin, *a)
        if '.reprise.' in str(chemin) and not _fait:
            _fait.append(1); arret()
        return fd
    os.open = ouvrir
elif etape == 'lecture':
    vrai_etat = d.etat_verrou
    def lire(chemin, *a, _vu=[]):
        r = vrai_etat(chemin, *a)
        if chemin.endswith('verrou'):
            _vu.append(1)
            if len(_vu) == 2:
                arret()
        return r
    d.etat_verrou = lire
elif etape == 'remplacement':
    vrai = d.ecrire_verrou
    def ecrire(fichier, contenu, _fait=[]):
        if not _fait:
            _fait.append(1); arret()
        return vrai(fichier, contenu)
    d.ecrire_verrou = ecrire
elif etape == 'bascule':
    d.empreinte_processus = lambda pid: None
    d.horloge_demarrage = lambda: ('', time.time())
    vraie = d.noter_etape
    def noter(transaction, quoi):
        if quoi == 'bascule':
            arret()
        return vraie(transaction, quoi)
    d.noter_etape = noter
    import zipfile, io
    tampon = io.BytesIO()
    with zipfile.ZipFile(tampon, 'w') as z:
        z.writestr('addon_data/skin.arctic.fuse.3/settings.xml', b'<settings>ENFANT</settings>')
    try:
        d.ecrire_pack(zipfile.ZipFile(io.BytesIO(tampon.getvalue())), racine)
        print('ECRIT', flush=True)
    except d.PackNonApplique as e:
        print('refus', flush=True)
    shutil.rmtree(SANDBOX, ignore_errors=True)
    sys.exit(0)
try:
    with d.verrou(racine):
        print('tenu', flush=True)
        sys.stdin.readline()
        print('proprietaire', d.proprietaire_du_verrou(os.path.join(racine, 'script.dark-prophet', 'verrou')), flush=True)
except d.PackNonApplique:
    print('refuse', flush=True)
shutil.rmtree(SANDBOX, ignore_errors=True)
'''


class Enfant:
    def __init__(self, racine, etape):
        self.p = subprocess.Popen([sys.executable, '-I', '-c', CROCHET, ICI, racine, etape],
                                  stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)

    def ligne(self):
        return self.p.stdout.readline().strip()

    def continuer(self):
        self.p.stdin.write('\n')
        self.p.stdin.flush()

    def fin(self):
        self.p.kill()
        self.p.wait()
        self.p.stdin.close()
        self.p.stdout.close()


class Verrou(Base):
    def setUp(self):
        super().setUp()
        self.anciens = d.BATTEMENT, d.ABANDON, d.ABANDON_VIDE
        d.BATTEMENT, d.ABANDON, d.ABANDON_VIDE = 0.05, 0.5, 0.5
        self.dossier = os.path.join(self.racine, 'script.dark-prophet')
        self.fichier = os.path.join(self.dossier, 'verrou')
        os.makedirs(self.dossier, exist_ok=True)

    def tearDown(self):
        d.BATTEMENT, d.ABANDON, d.ABANDON_VIDE = self.anciens
        super().tearDown()

    def restes(self):
        return sorted(f for f in os.listdir(self.dossier) if f.startswith('verrou'))

    # A1 : verrou créé mais encore vide, son créateur suspendu bien au-delà du délai.
    def test_verrou_vide_createur_suspendu(self):
        enfant = Enfant(self.racine, 'vide')
        try:
            self.assertEqual(enfant.ligne(), 'bloque')
            enfant.p.send_signal(signal.SIGSTOP)
            time.sleep(4 * d.ABANDON_VIDE)
            with self.assertRaises(d.PackNonApplique):
                with d.verrou(self.racine):
                    pass
            enfant.p.send_signal(signal.SIGCONT)
            enfant.continuer()
            self.assertEqual(enfant.ligne(), 'tenu')
            enfant.continuer()
            self.assertTrue(enfant.ligne().startswith('proprietaire '))
            enfant.p.wait(10)                           # libère son verrou en sortant
        finally:
            enfant.fin()
        self.assertEqual(self.restes(), [])

    def test_verrou_vide_createur_mort_repris(self):
        enfant = Enfant(self.racine, 'vide')
        self.assertEqual(enfant.ligne(), 'bloque')
        enfant.fin()                                    # tué entre la création et l'écriture
        d.ecrire_pack(pack(), self.racine)              # repris aussitôt : son créateur n'existe plus
        self.assertEqual(etat(self.racine), NOUVEAU)
        self.assertEqual(self.restes(), [])

    # A2 : un repreneur tué à chaque étape de sa reprise, les autres continuent.
    def repreneur_tue_puis_concurrents(self, etape, tours=4, nombre=6):
        demarrage, battement = d.horloge_demarrage()
        for tour in range(tours):
            poser(self.racine, {'script.dark-prophet/verrou': json.dumps(
                {'id': 'mort', 'pid': pid_disparu(), 'processus': '1', 'demarrage': demarrage, 'battement': battement}).encode()})
            premier = Enfant(self.racine, etape)
            self.assertEqual(premier.ligne(), 'bloque', etape)
            premier.fin()
            depart = time.time() + 1.0
            autres = [subprocess.Popen([sys.executable, '-I', '-c', REPRENEUR, ICI, self.racine, str(depart)],
                                       stdout=subprocess.PIPE, text=True) for _ in range(nombre)]
            sorties = [a.communicate(timeout=60)[0].strip() for a in autres]
            self.assertNotIn('DOUBLE', sorties, '%s tour %d' % (etape, tour))
            self.assertIn('tenu', sorties, '%s tour %d : %s' % (etape, tour, sorties))
            self.assertEqual(self.restes(), [], '%s tour %d' % (etape, tour))

    def test_repreneur_tue_apres_la_marque(self):
        self.repreneur_tue_puis_concurrents('marque')

    def test_repreneur_tue_apres_la_lecture(self):
        self.repreneur_tue_puis_concurrents('lecture')

    def test_repreneur_tue_avant_le_remplacement(self):
        self.repreneur_tue_puis_concurrents('remplacement')

    # A3 : sans /proc, une opération figée peut perdre son verrou ; en reprenant, elle ne doit
    # plus rien modifier.
    def test_operation_depossedee_ne_bascule_pas(self):
        vraies = d.empreinte_processus, d.horloge_demarrage
        d.empreinte_processus = lambda pid: None
        d.horloge_demarrage = lambda: ('', time.time())
        enfant = Enfant(self.racine, 'bascule')
        try:
            self.assertEqual(enfant.ligne(), 'bloque')
            enfant.p.send_signal(signal.SIGSTOP)
            time.sleep(4 * d.ABANDON)
            with d.verrou(self.racine):                  # battement absent : repris (seul critère sans /proc)
                enfant.p.send_signal(signal.SIGCONT)
                enfant.continuer()
                self.assertEqual(enfant.ligne(), 'refus')
                self.assertEqual(etat(self.racine), ANCIEN)   # rien basculé pendant qu'on tient le verrou
                self.assertEqual(json.load(open(self.fichier))['pid'], os.getpid())
        finally:
            d.empreinte_processus, d.horloge_demarrage = vraies
            enfant.fin()
        self.assertEqual(self.restes(), [])


class StockagePlein(Base):
    """Phase B2 : stockage plein à chaque écriture de l'application d'un pack (sauvegarde comprise)."""

    def test_plein_a_chaque_etape(self):
        etapes = 0
        for numero in range(1, 80):
            shutil.rmtree(self.racine)
            poser(self.racine, ANCIEN)
            d.ADDON_DATA = self.racine
            d.SAUVEGARDE = os.path.join(self.racine, 'script.dark-prophet', 'sauvegarde')
            with Panne(numero, mode='erreur', erreur=errno.ENOSPC) as panne:
                try:
                    d.sauvegarder_actuel()
                    d.ecrire_pack(pack(), self.racine)
                    reussi = True
                except d.PackNonApplique:
                    reussi = False
            if panne.appels < numero:
                break   # plus aucun appel à faire échouer : tout a été balayé
            etapes += 1
            self.assertIn(etat(self.racine), (ANCIEN, NOUVEAU), 'appel %d' % numero)
            if reussi:
                self.assertEqual(etat(self.racine), NOUVEAU)
            d.reprendre(self.racine)   # le lancement suivant : rien à moitié écrit ne reste
            self.assertIn(etat(self.racine), (ANCIEN, NOUVEAU), 'appel %d' % numero)
            self.sans_residu(self.racine)
        self.assertGreater(etapes, 10)


class PlaceAvantInstallation(unittest.TestCase):
    """Phase B : avant d'installer Arctic Fuse 3, on vérifie la place quand on peut la mesurer."""

    def setUp(self):
        self.vrais = {n: getattr(d, n) for n in ('choisir_version', 'noter_etat_avant', 'installer_tout', 'installe',
                                                 'formule_extra', 'dialog', 'place_libre', 'formule_catchup')}
        self.questions, self.messages, self.appels, self.reponses = [], [], [], []
        d.dialog = types.SimpleNamespace(ok=lambda *a: self.messages.append(a[-1]), yesno=self.repondre)
        d.choisir_version = lambda *a, **k: 'base'
        d.noter_etat_avant = lambda: None
        d.formule_extra = lambda: self.appels.append('extra')
        d.installer_tout = lambda ids: self.appels.append('installer') or False
        d.installe = lambda a: False

    def tearDown(self):
        for nom, valeur in self.vrais.items():
            setattr(d, nom, valeur)

    def repondre(self, *a):
        self.questions.append(a[-1])
        return self.reponses.pop(0)

    def test_place_insuffisante_rien_n_est_installe_extra_proposee(self):
        d.place_libre = lambda chemin: 300 * 1024 * 1024
        self.reponses = [True, True]
        d.formule_alkoflix()
        self.assertEqual(self.appels, ['extra'])
        self.assertIn('Mo', self.questions[-1])
        self.assertIn('Extra-Light', self.questions[-1])

    def test_place_insuffisante_refus(self):
        d.place_libre = lambda chemin: 300 * 1024 * 1024
        self.reponses = [True, False]
        d.formule_alkoflix()
        self.assertEqual(self.appels, [])

    def test_place_suffisante_installation_normale(self):
        d.place_libre = lambda chemin: 5 * 1024 ** 3
        self.reponses = [True, False]
        d.formule_alkoflix()
        self.assertEqual(self.appels[0], 'installer')

    def test_place_inconnue_installation_normale(self):
        d.place_libre = lambda chemin: None
        self.reponses = [True, False]
        d.formule_alkoflix()
        self.assertEqual(self.appels[0], 'installer')

    def test_habillage_deja_installe_pas_de_controle(self):
        d.installe = lambda a: a == SKIN
        d.place_libre = lambda chemin: 1
        self.reponses = [True]
        d.formule_alkoflix()
        self.assertEqual(self.appels[0], 'installer')

    def test_catch_up_place_insuffisante_refus_clair(self):
        d.place_libre = lambda chemin: 300 * 1024 * 1024
        self.reponses = [True]
        d.formule_catchup()
        self.assertNotIn('installer', self.appels)
        self.assertIn('Mo', self.messages[-1])


if __name__ == '__main__':
    try:
        unittest.main(verbosity=1)
    finally:
        shutil.rmtree(SANDBOX, ignore_errors=True)

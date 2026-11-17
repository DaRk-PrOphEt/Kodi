# -*- coding: utf-8 -*-
"""Tests du Lot 2 : derniers contrôles du verrou (plusieurs processus, interruptions simulées)
et repli explicite vers l'Extra-Light quand Arctic Fuse 3 ne s'installe pas. Sans Kodi :

    python3 -I tests/test_lot2.py
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
from kodi_factice import SANDBOX, SKIN, default as d, xbmcgui   # noqa: E402
from test_lot1_transactions import ANCIEN, NOUVEAU, Base, etat, pack, poser   # noqa: E402

ICI = os.path.dirname(os.path.abspath(__file__))

# Opération qui tient le verrou jusqu'à ce qu'on lui dise de finir (une ligne sur son entrée),
# puis écrit un témoin : elle a continué après avoir été figée.
FIGEE = '''
import os, shutil, sys
sys.path.insert(0, sys.argv[1])
from kodi_factice import SANDBOX, default as d
d.BATTEMENT = 0.05
with d.verrou(sys.argv[2]):
    print('tenu', flush=True)
    sys.stdin.readline()
    open(os.path.join(sys.argv[2], 'temoin'), 'w').close()
print('libere', flush=True)
shutil.rmtree(SANDBOX, ignore_errors=True)
'''

# Repreneur lancé en même temps que d'autres sur un verrou abandonné. Un fichier « dedans »
# créé en exclusif pendant qu'il tient le verrou trahit deux détenteurs simultanés.
REPRENEUR = '''
import os, shutil, sys, time
sys.path.insert(0, sys.argv[1])
from kodi_factice import SANDBOX, default as d
racine = sys.argv[2]
time.sleep(max(0, float(sys.argv[3]) - time.time()))
try:
    with d.verrou(racine):
        fd = os.open(os.path.join(racine, 'dedans'), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        time.sleep(0.2)
        os.close(fd)
        os.remove(os.path.join(racine, 'dedans'))
    print('tenu')
except d.PackNonApplique:
    print('refuse')
except FileExistsError:
    print('DOUBLE')
shutil.rmtree(SANDBOX, ignore_errors=True)
'''


def pid_disparu():
    p = subprocess.Popen(['true'])
    p.wait()
    return p.pid


class Verrou(Base):
    def setUp(self):
        super().setUp()
        self.anciens = d.BATTEMENT, d.ABANDON, d.ABANDON_VIDE
        d.BATTEMENT, d.ABANDON = 0.05, 0.5
        self.fichier = os.path.join(self.racine, 'script.dark-prophet', 'verrou')

    def tearDown(self):
        d.BATTEMENT, d.ABANDON, d.ABANDON_VIDE = self.anciens
        super().tearDown()

    def poser_verrou(self, **valeurs):
        demarrage, battement = d.horloge_demarrage()
        contenu = dict({'id': 'autre', 'pid': os.getpid(), 'processus': d.empreinte_processus(os.getpid()),
                        'demarrage': demarrage, 'battement': battement}, **valeurs)
        poser(self.racine, {'script.dark-prophet/verrou': json.dumps(contenu).encode()})

    def restes(self):
        return sorted(f for f in os.listdir(os.path.dirname(self.fichier)) if f.startswith('verrou'))

    # Risque 2 : une opération vivante perd son battement plus longtemps que le délai d'abandon.
    def test_operation_figee_jamais_volee(self):
        enfant = subprocess.Popen([sys.executable, '-I', '-c', FIGEE, ICI, self.racine],
                                  stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
        try:
            self.assertEqual(enfant.stdout.readline().strip(), 'tenu')
            time.sleep(0.3)
            enfant.send_signal(signal.SIGSTOP)        # veille de l'appareil, stockage figé…
            time.sleep(4 * d.ABANDON)                 # battement absent bien au-delà du délai
            with self.assertRaises(d.PackNonApplique):
                d.ecrire_pack(pack(), self.racine)
            self.assertEqual(etat(self.racine), ANCIEN)
            enfant.send_signal(signal.SIGCONT)
            enfant.stdin.write('\n')
            enfant.stdin.flush()
            self.assertEqual(enfant.stdout.readline().strip(), 'libere')
            self.assertTrue(os.path.exists(os.path.join(self.racine, 'temoin')))
        finally:
            enfant.kill()
            enfant.wait()
            enfant.stdin.close()
            enfant.stdout.close()
        self.assertEqual(self.restes(), [])
        d.ecrire_pack(pack(), self.racine)            # libéré normalement : repris aussitôt
        self.assertEqual(etat(self.racine), NOUVEAU)

    def test_meme_processus_battement_ancien_jamais_vole(self):
        _, battement = d.horloge_demarrage()
        self.poser_verrou(battement=battement - 1000)   # ce Kodi tourne toujours : pas une preuve d'arrêt
        with self.assertRaises(d.PackNonApplique) as refus:
            d.ecrire_pack(pack(), self.racine)
        self.assertIn('redémarre Kodi', str(refus.exception))
        self.assertEqual(etat(self.racine), ANCIEN)

    def test_processus_disparu_repris_sans_attendre(self):
        self.poser_verrou(pid=pid_disparu())          # battement tout frais, mais le processus n'existe plus
        d.ecrire_pack(pack(), self.racine)
        self.assertEqual(etat(self.racine), NOUVEAU)
        self.assertEqual(self.restes(), [])

    def test_numero_reutilise_par_un_autre_processus(self):
        dormeur = subprocess.Popen(['sleep', '30'])
        try:
            self.poser_verrou(pid=dormeur.pid)        # même numéro, autre processus (heure de départ différente)
            d.ecrire_pack(pack(), self.racine)
            self.assertEqual(etat(self.racine), NOUVEAU)
        finally:
            dormeur.kill()
            dormeur.wait()

    def test_sans_proc_le_battement_decide_encore(self):
        """Systèmes sans /proc (Windows, macOS) : seul le battement reste (voir le rapport)."""
        vraies = d.empreinte_processus, d.horloge_demarrage
        d.empreinte_processus = lambda pid: None
        d.horloge_demarrage = lambda: ('', time.time())
        try:
            self.poser_verrou(processus=None, demarrage='', battement=time.time())
            with self.assertRaises(d.PackNonApplique):
                d.ecrire_pack(pack(), self.racine)
            self.poser_verrou(processus=None, demarrage='', battement=time.time() - 10)
            d.ecrire_pack(pack(), self.racine)
            self.assertEqual(etat(self.racine), NOUVEAU)
        finally:
            d.empreinte_processus, d.horloge_demarrage = vraies

    # Risque 1 : plusieurs repreneurs en même temps sur un verrou abandonné.
    def repreneurs(self, contenu, nombre=8):
        poser(self.racine, {'script.dark-prophet/verrou': json.dumps(contenu).encode()})
        depart = time.time() + 1.0
        enfants = [subprocess.Popen([sys.executable, '-I', '-c', REPRENEUR, ICI, self.racine, str(depart)],
                                    stdout=subprocess.PIPE, text=True) for _ in range(nombre)]
        sorties = []
        for e in enfants:
            sorties.append(e.communicate(timeout=60)[0].strip())
        return sorties

    def test_repreneurs_simultanes(self):
        demarrage, battement = d.horloge_demarrage()
        for tour in range(12):
            if tour % 2:
                # ancien format, sans empreinte : abandonné par le battement (délai réel de l'enfant : 120 s)
                contenu = {'id': 'mort', 'pid': pid_disparu(), 'demarrage': demarrage, 'battement': battement - 1000}
            else:
                contenu = {'id': 'mort', 'pid': pid_disparu(), 'processus': '1', 'demarrage': demarrage, 'battement': battement}
            sorties = self.repreneurs(contenu)
            self.assertNotIn('DOUBLE', sorties, 'tour %d' % tour)
            self.assertIn('tenu', sorties, 'tour %d' % tour)
            self.assertEqual(sorted(set(sorties) - {'tenu', 'refuse'}), [], sorties)
            self.assertEqual(self.restes(), [], 'tour %d' % tour)


class RepliExtraLight(unittest.TestCase):
    """Phase B : si Arctic Fuse 3 ne s'installe pas, on le dit et on PROPOSE l'Extra-Light."""

    def setUp(self):
        self.vrais = {n: getattr(d, n) for n in ('choisir_version', 'noter_etat_avant', 'installer_tout', 'installe',
                                                 'formule_extra', 'dialog', 'rpc', 'rafraichir_depots', 'installer_extension')}
        self.questions, self.messages, self.appels, self.reponses = [], [], [], []
        d.dialog = types.SimpleNamespace(ok=lambda *a: self.messages.append(a[-1]), yesno=self.repondre)
        d.choisir_version = lambda *a, **k: 'base'
        d.noter_etat_avant = lambda: None
        d.formule_extra = lambda: self.appels.append('extra')

    def tearDown(self):
        for nom, valeur in self.vrais.items():
            setattr(d, nom, valeur)

    def repondre(self, *a):
        self.questions.append(a[-1])
        return self.reponses.pop(0)

    def test_skin_introuvable_propose_extra(self):
        d.installer_tout = lambda ids: False
        d.installe = lambda a: a != SKIN
        self.reponses = [True, True]
        d.formule_alkoflix()
        self.assertEqual(self.appels, ['extra'])
        self.assertIn('Extra-Light', self.questions[-1])

    def test_refus_rien_ne_change(self):
        d.installer_tout = lambda ids: False
        d.installe = lambda a: a != SKIN
        self.reponses = [True, False]
        d.formule_alkoflix()
        self.assertEqual(self.appels, [])   # jamais de bascule silencieuse

    def test_autre_echec_pas_de_proposition(self):
        d.installer_tout = lambda ids: False
        d.installe = lambda a: True          # Arctic Fuse 3 est là : l'échec vient d'ailleurs
        self.reponses = [True]
        d.formule_alkoflix()
        self.assertEqual((self.appels, len(self.questions)), ([], 1))

    def test_message_clair_quand_le_skin_manque(self):
        xbmcgui.DialogProgressBG = type('P', (), {'create': lambda *a: None, 'update': lambda *a: None,
                                                  'close': lambda *a: None})
        d.rpc = lambda *a, **k: {}
        d.rafraichir_depots = lambda: None
        d.installe = lambda a: False
        d.installer_extension = lambda a: a != SKIN
        self.assertFalse(d.installer_tout((SKIN,)))
        self.assertIn('Kodi 21', self.messages[-1])
        self.assertIn('Arctic Fuse 3', self.messages[-1])


if __name__ == '__main__':
    try:
        unittest.main(verbosity=1)
    finally:
        shutil.rmtree(SANDBOX, ignore_errors=True)

# -*- coding: utf-8 -*-
"""Tests du Lot 0 : téléchargements et validation des packs, sans Kodi.

    python3 -I tests/test_lot0_telechargements.py

Les modules Kodi sont remplacés par de faux modules ; un petit serveur local
joue le rôle de GitHub (404, 500, coupure, lenteur). Variable facultative
LOT0_SOURCE : dossier contenant un autre default.py (pour rejouer les tests
sur une ancienne version).
"""
import io
import os
import shutil
import socket
import sys
import tempfile
import threading
import types
import unittest
import urllib.request
import zipfile
from http.server import BaseHTTPRequestHandler, HTTPServer

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from kodi_factice import RACINE, SANDBOX, default as d   # noqa: E402

SKIN = 'skin.arctic.fuse.3'
SETTINGS = 'addon_data/%s/settings.xml' % SKIN


def faire_zip(entrees, methode=zipfile.ZIP_DEFLATED):
    tampon = io.BytesIO()
    with zipfile.ZipFile(tampon, 'w', methode) as z:
        for nom, contenu in entrees.items():
            z.writestr(nom, contenu)
    return tampon.getvalue()


BON = {SETTINGS: '<settings version="2"><setting id="a">1</setting></settings>',
       'addon_data/script.skinvariables/x.json': '{"ok": 1}'}


class Faux(BaseHTTPRequestHandler):
    reponses = {}   # chemin -> octets du zip, ou fonction(handler)

    def log_message(self, *a):
        pass

    def do_GET(self):
        r = self.reponses.get(self.path)
        if r is None:
            self.send_error(404)
        elif callable(r):
            r(self)
        else:
            self.send_response(200)
            self.send_header('Content-Length', str(len(r)))
            self.end_headers()
            self.wfile.write(r)


def coupure(h):   # annonce 100 000 octets, en envoie 20, ferme
    h.send_response(200)
    h.send_header('Content-Length', '100000')
    h.end_headers()
    h.wfile.write(b'PK\x03\x04' + b'x' * 16)
    h.wfile.flush()
    h.close_connection = True
    h.connection.shutdown(socket.SHUT_RDWR)


def lent(h):
    import time
    time.sleep(2)


def erreur500(h):
    h.send_error(500)


class Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.serveur = HTTPServer(('127.0.0.1', 0), Faux)
        cls.serveur.handle_error = lambda *a: None   # client parti avant la fin : voulu dans certains tests
        threading.Thread(target=cls.serveur.serve_forever, daemon=True).start()
        d.PACKS_URL = 'http://127.0.0.1:%d/' % cls.serveur.server_address[1]
        vrai = urllib.request.urlopen
        d.urlopen = lambda url, timeout=30: vrai(url, timeout=0.5)   # « timeout réseau » court pour les tests

    @classmethod
    def tearDownClass(cls):
        cls.serveur.shutdown()
        cls.serveur.server_close()

    def setUp(self):
        self.messages = []
        d.dialog = types.SimpleNamespace(ok=lambda *a: self.messages.append(a[-1]))
        Faux.reponses = {}
        self.racine = tempfile.mkdtemp(dir=SANDBOX)
        d.ADDON_DATA = self.racine

    def servir(self, contenu, nom='p.zip'):
        Faux.reponses['/' + nom] = contenu
        return d.telecharger_pack(nom)


class Reseau(Base):
    def test_telechargement_interrompu(self):
        Faux.reponses['/p.zip'] = coupure
        self.assertIsNone(d.telecharger_pack('p.zip'))
        self.assertEqual(self.messages, ['Téléchargement impossible. Vérifie la connexion puis relance.'])

    def test_coupure_sur_fond_et_image_sans_exception_ni_image_tronquee(self):
        d.DOSSIER_FONDS = os.path.join(self.racine, 'fonds')
        d.DOSSIER_IMAGES = os.path.join(self.racine, 'images')
        os.makedirs(d.DOSSIER_FONDS)
        ancien = os.path.join(d.DOSSIER_FONDS, 'a.jpg')
        with open(ancien, 'wb') as sortie:
            sortie.write(b'IMAGE COMPLETE')
        Faux.reponses['/fonds/a.jpg'] = coupure
        Faux.reponses['/images/' + d.IMAGE_PLUS] = coupure
        self.assertEqual(d.telecharger_fond('a.jpg'), ancien)
        with open(ancien, 'rb') as source:
            self.assertEqual(source.read(), b'IMAGE COMPLETE')
        d.poser_images_habillage()   # ne doit pas lever
        self.assertFalse(os.path.isfile(os.path.join(d.DOSSIER_IMAGES, d.IMAGE_PLUS)))

    def test_timeout(self):
        Faux.reponses['/p.zip'] = lent
        self.assertIsNone(d.telecharger_pack('p.zip'))
        self.assertEqual(len(self.messages), 1)

    def test_404_silencieux_et_500_annonce(self):
        self.assertIsNone(d.telecharger_pack('absent.zip'))
        self.assertEqual(self.messages, [])
        Faux.reponses['/p.zip'] = erreur500
        self.assertIsNone(d.telecharger_pack('p.zip'))
        self.assertEqual(self.messages, ['Téléchargement refusé (erreur 500).'])

    def test_muet_ne_dit_rien(self):
        Faux.reponses['/p.zip'] = coupure
        self.assertIsNone(d.telecharger_pack('p.zip', muet=True))
        self.assertEqual(self.messages, [])

    def test_lecture_reseau_bornee(self):
        """A1 : on ne lit jamais plus que la limite + 1 octet, même si le serveur envoie plus."""
        lus = []
        vrai = d.urlopen

        class Espion:
            def __init__(self, reponse):
                self.reponse = reponse

            def __enter__(self):
                return self

            def __exit__(self, *a):
                self.reponse.close()

            def read(self, *taille):
                donnees = self.reponse.read(*taille)
                lus.append((taille, len(donnees)))
                return donnees

        ancien = d.PACK_MAX_TELECHARGE
        d.PACK_MAX_TELECHARGE = 1000
        d.urlopen = lambda url, timeout=30: Espion(vrai(url, timeout=timeout))
        try:
            self.assertIsNone(self.servir(b'PK' + b'x' * 3000000))
        finally:
            d.PACK_MAX_TELECHARGE = ancien
            d.urlopen = vrai
        self.assertEqual(lus, [((1001,), 1001)])

    def test_telechargement_trop_gros(self):
        ancien = d.PACK_MAX_TELECHARGE
        d.PACK_MAX_TELECHARGE = 100
        try:
            self.assertIsNone(self.servir(faire_zip(BON)))
        finally:
            d.PACK_MAX_TELECHARGE = ancien


class Validation(Base):
    def refuse(self, contenu):
        self.assertIsNone(self.servir(contenu))

    def test_zip_a_crc_invalide(self):
        brut = bytearray(faire_zip({SETTINGS: '<settings>' + 'A' * 500 + '</settings>',
                                    'addon_data/script.skinvariables/x.json': '{"ok": 1}' * 50},
                                   zipfile.ZIP_STORED))
        brut[brut.index(b'{"ok": 1}') + 12] ^= 0xFF
        self.refuse(bytes(brut))
        self.assertEqual(self.messages, ['Téléchargement impossible. Vérifie la connexion puis relance.'])

    def test_zip_vide(self):
        self.refuse(faire_zip({}))

    def test_pas_un_zip(self):
        self.refuse(b'<html>404 de proxy</html>')

    def test_pack_incomplet_sans_settings(self):
        self.refuse(faire_zip({'addon_data/script.skinvariables/x.json': '{}'}))

    def test_pack_sans_aucun_fichier_autorise(self):
        self.refuse(faire_zip({'readme.txt': 'x', 'autre/dossier/f.xml': '<a/>'}))

    def test_chemins_dangereux(self):
        for nom in ('addon_data/%s/../../evil.txt' % SKIN, '/etc/evil', '\\evil', 'C:/evil',
                    'addon_data\\..\\..\\evil'):
            with self.subTest(nom=nom):
                self.refuse(faire_zip(dict(BON, **{nom: 'x'})))

    def test_chemins_impossibles_sur_windows_ou_fat(self):
        for nom in ('addon_data/%s/a:b.xml' % SKIN, 'addon_data/%s/CON.json' % SKIN, 'addon_data/%s/nul' % SKIN,
                    'addon_data/%s/fin.' % SKIN, 'addon_data/%s/fin ' % SKIN, 'addon_data/%s/a?.xml' % SKIN,
                    'addon_data/%s/a\x01b' % SKIN, 'addon_data//%s/x' % SKIN, 'addon_data/./%s/x' % SKIN):
            with self.subTest(nom=nom):
                self.refuse(faire_zip(dict(BON, **{nom: 'x'})))

    def test_entrees_en_double_meme_a_la_casse_pres(self):
        tampon = io.BytesIO()
        with zipfile.ZipFile(tampon, 'w') as z:
            for nom, contenu in BON.items():
                z.writestr(nom, contenu)
            z.writestr(SETTINGS.replace('settings', 'Settings'), '<settings/>')
        self.refuse(tampon.getvalue())

    def test_lien_symbolique(self):
        tampon = io.BytesIO()
        with zipfile.ZipFile(tampon, 'w') as z:
            for nom, contenu in BON.items():
                z.writestr(nom, contenu)
            lien = zipfile.ZipInfo('addon_data/script.skinvariables/lien')
            lien.external_attr = (0o120777 << 16)
            z.writestr(lien, '/etc/passwd')
        self.refuse(tampon.getvalue())

    def test_fichier_et_dossier_au_meme_nom(self):
        self.refuse(faire_zip(dict(BON, **{'addon_data/script.skinvariables/a': 'x',
                                           'addon_data/script.skinvariables/a/b.json': '{}'})))

    def test_separateurs_windows_acceptes_et_bien_places(self):
        archive = self.servir(faire_zip({SETTINGS.replace('/', '\\'): BON[SETTINGS]}))
        self.assertIsNotNone(archive)
        cible = tempfile.mkdtemp(dir=SANDBOX)
        self.assertEqual(d.ecrire_pack(archive, cible), 1)
        self.assertTrue(os.path.isfile(os.path.join(cible, SKIN, 'settings.xml')))

    def test_dossiers_inattendus_jamais_ecrits(self):
        archive = self.servir(faire_zip(dict(BON, **{'addon_data/plugin.video.alkoflix/settings.xml': '<x/>',
                                                     'userdata/guisettings.xml': '<x/>', 'autre.txt': 'x'})))
        self.assertIsNotNone(archive)
        cible = tempfile.mkdtemp(dir=SANDBOX)
        d.ecrire_pack(archive, cible)
        ecrits = {os.path.relpath(os.path.join(c, f), cible) for c, _, fs in os.walk(cible) for f in fs}
        self.assertEqual(ecrits, {os.path.join(SKIN, 'settings.xml'), os.path.join('script.skinvariables', 'x.json')})

    def test_fichier_trop_gros(self):
        self.refuse(faire_zip(dict(BON, **{'addon_data/script.skinvariables/gros.json': ' ' * (d.PACK_MAX_ENTREE + 1)})))

    def test_total_trop_gros(self):
        ancien = d.PACK_MAX_TOTAL
        d.PACK_MAX_TOTAL = 50
        try:
            self.refuse(faire_zip(BON))
        finally:
            d.PACK_MAX_TOTAL = ancien

    def test_trop_de_fichiers(self):
        ancien = d.PACK_MAX_ENTREES
        d.PACK_MAX_ENTREES = 1
        try:
            self.refuse(faire_zip(BON))
        finally:
            d.PACK_MAX_ENTREES = ancien

    def test_xml_ou_json_illisible(self):
        self.refuse(faire_zip(dict(BON, **{SETTINGS: '<settings><setting>'})))
        self.refuse(faire_zip(dict(BON, **{SETTINGS: '<autre/>'})))
        self.refuse(faire_zip(dict(BON, **{'addon_data/script.skinvariables/x.json': '{pas du json'})))

    def test_valide_minimal_accepte(self):
        archive = self.servir(faire_zip(BON))
        self.assertIsNotNone(archive)
        self.assertEqual(self.messages, [])

    def test_packs_reellement_distribues_acceptes_et_ecrits(self):
        for nom in sorted(os.listdir(os.path.join(RACINE, 'packs'))):
            if not nom.endswith('.zip'):
                continue
            with self.subTest(pack=nom):
                with open(os.path.join(RACINE, 'packs', nom), 'rb') as source:
                    Faux.reponses['/' + nom] = source.read()
                archive = d.telecharger_pack(nom)
                self.assertIsNotNone(archive)
                cible = tempfile.mkdtemp(dir=SANDBOX)
                self.assertEqual(d.ecrire_pack(archive, cible), 14)
                ecrits = {}
                for chemin, _, fichiers in os.walk(cible):
                    for fichier in fichiers:
                        with open(os.path.join(chemin, fichier), 'rb') as source:
                            ecrits['addon_data/' + os.path.relpath(os.path.join(chemin, fichier), cible).replace(os.sep, '/')] = source.read()
                for dossier in list(ecrits):
                    if dossier.startswith('addon_data/script.dark-prophet/'):
                        self.fail('reste de transaction : %s' % dossier)
                self.assertEqual(ecrits, {i.filename: archive.read(i) for i in archive.infolist() if not i.is_dir()})
        self.assertEqual(self.messages, [])


class ReglagesPreserves(Base):
    """Un pack refusé ne doit toucher à rien : le flux réel est télécharger puis appliquer."""

    def test_pack_invalide_laisse_les_reglages(self):
        dossier = os.path.join(self.racine, SKIN)
        os.makedirs(dossier)
        fichier = os.path.join(dossier, 'settings.xml')
        with open(fichier, 'w') as sortie:
            sortie.write('REGLAGES ACTUELS')
        d.changer_habillage = lambda skin: True
        invalides = [b'', b'pas un zip', faire_zip({}), faire_zip({'addon_data/x/../../e': 'x'}),
                     faire_zip({'addon_data/script.skinvariables/x.json': '{}'})]
        for contenu in invalides:
            archive = self.servir(contenu)
            self.assertIsNone(archive)
            self.assertTrue(d.appliquer_ici(archive))   # parcours réel : sans pack, on se contente de l'habillage
            with open(fichier) as source:
                self.assertEqual(source.read(), 'REGLAGES ACTUELS')
        archive = self.servir(faire_zip(BON))   # un pack valide, lui, remplace bien
        d.ecrire_pack(archive, self.racine)
        with open(fichier) as source:
            self.assertNotEqual(source.read(), 'REGLAGES ACTUELS')


if __name__ == '__main__':
    try:
        unittest.main(verbosity=2)
    finally:
        shutil.rmtree(SANDBOX, ignore_errors=True)

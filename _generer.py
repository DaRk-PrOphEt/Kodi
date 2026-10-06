#!/usr/bin/env python3
"""Fabrique le catalogue du dépôt Kodi.

À lancer depuis la racine après chaque changement dans repo/<extension>/ :
    python3 _generer.py
Il zippe chaque extension dans repo/zips/, réécrit addons.xml et sa somme md5,
met à jour le zip du dépôt à la racine et la page index.html lue par Kodi.
"""
import hashlib
import os
import shutil
import zipfile
from xml.etree import ElementTree

RACINE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.join(RACINE, 'repo')
ZIPS = os.path.join(REPO, 'zips')
DEPOT_ID = 'repository.dark-prophet'
IGNORES = {'.git', '.DS_Store', 'thumbs.db', '__pycache__'}


def zipper(dossier, addon_id, cible):
    # Dates figées : un zip inchangé reste identique d'une génération à l'autre.
    with zipfile.ZipFile(cible, 'w', zipfile.ZIP_DEFLATED) as archive:
        for chemin, sous_dossiers, fichiers in os.walk(dossier):
            sous_dossiers[:] = sorted(d for d in sous_dossiers if d not in IGNORES)
            for fichier in sorted(fichiers):
                if fichier in IGNORES or fichier.endswith('.pyc'):
                    continue
                complet = os.path.join(chemin, fichier)
                relatif = os.path.relpath(complet, dossier).replace(os.sep, '/')
                info = zipfile.ZipInfo(addon_id + '/' + relatif, (2020, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o644 << 16
                with open(complet, 'rb') as source:
                    archive.writestr(info, source.read())


def main():
    shutil.rmtree(ZIPS, ignore_errors=True)
    os.makedirs(ZIPS)
    catalogue = ElementTree.Element('addons')
    depot_zip = None

    for nom in sorted(os.listdir(REPO)):
        dossier = os.path.join(REPO, nom)
        fiche = os.path.join(dossier, 'addon.xml')
        if nom == 'zips' or not os.path.isfile(fiche):
            continue
        addon = ElementTree.parse(fiche).getroot()
        addon_id, version = addon.get('id'), addon.get('version')
        if addon_id != nom:
            raise SystemExit('Le dossier %s ne porte pas le nom de son extension (%s)' % (nom, addon_id))
        catalogue.append(addon)

        sortie = os.path.join(ZIPS, addon_id)
        os.makedirs(sortie)
        cible = os.path.join(sortie, '%s-%s.zip' % (addon_id, version))
        zipper(dossier, addon_id, cible)
        for image in ('icon.png', 'fanart.jpg'):
            if os.path.isfile(os.path.join(dossier, image)):
                shutil.copy(os.path.join(dossier, image), sortie)
        if addon_id == DEPOT_ID:
            depot_zip = cible
        print('%-28s %s' % (addon_id, version))

    ElementTree.indent(catalogue)
    xml = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n' + ElementTree.tostring(catalogue, encoding='unicode') + '\n'
    with open(os.path.join(ZIPS, 'addons.xml'), 'w', encoding='utf-8') as sortie:
        sortie.write(xml)
    with open(os.path.join(ZIPS, 'addons.xml.md5'), 'w') as sortie:
        sortie.write(hashlib.md5(xml.encode('utf-8')).hexdigest())

    # Le zip du dépôt à la racine : c'est lui qu'on installe depuis Kodi.
    for ancien in os.listdir(RACINE):
        if ancien.startswith(DEPOT_ID) and ancien.endswith('.zip'):
            os.remove(os.path.join(RACINE, ancien))
    nom_zip = os.path.basename(depot_zip)
    shutil.copy(depot_zip, os.path.join(RACINE, nom_zip))
    with open(os.path.join(RACINE, 'index.html'), 'w', encoding='utf-8') as sortie:
        sortie.write('<!DOCTYPE html>\n<a href="%s">%s</a><br>\n' % (nom_zip, nom_zip))


if __name__ == '__main__':
    main()

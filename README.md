# Dépôt Kodi Pr0phEt

Adresse à ajouter comme source dans le gestionnaire de fichiers de Kodi :

    https://dark-prophet.github.io/Kodi/

Puis : Extensions > Installer depuis un fichier zip > `repository.pr0phet-x.y.z.zip`,
et enfin Installer depuis un dépôt > Pr0phEt Repo > Extensions programmes > Pr0phEt.

Le script installe l'habillage Arctic Fuse 3 (dépôt officiel de jurialmunkey) et
applique la configuration publiée dans `packs/`. Kodi 21 ou plus récent.

## Mettre à jour

Après tout changement dans `repo/<extension>/` (penser à monter le numéro de
version dans son `addon.xml`) :

    python3 _generer.py

# Dépôt Kodi DaRk-PrOphEt

Adresse à ajouter comme source dans le gestionnaire de fichiers de Kodi :

    https://dark-prophet.github.io/Kodi/

Puis : Extensions > Installer depuis un fichier zip > `repository.dark-prophet-x.y.z.zip`,
et enfin Installer depuis un dépôt > DaRk-PrOphEt Repo > Extensions programmes > DaRk-PrOphEt.

Le script propose deux formules (Kodi 21 ou plus récent) :

- **alkoFlix** : installe l'habillage Arctic Fuse 3 (dépôt officiel de jurialmunkey)
  et alkoFlix, puis applique la configuration `packs/arctic-fuse-3.zip`.
- **alkoFlix + Catch-up TV** : ajoute Catch-up TV & More dans un second profil Kodi
  nommé « Catch-up TV » (configuration `packs/arctic-fuse-3-catchup.zip`), renomme le
  profil principal en « alkoFlix » et active l'écran de choix au démarrage.

Les deux formules passent Kodi en français et installent les sons d'Android TV.
Qui a pris la formule alkoFlix peut ajouter Catch-up TV plus tard depuis le menu,
sans que ses réglages soient modifiés.

Une fois une formule installée, « Mettre l'interface à jour » repose la dernière
interface publiée sur chaque profil, sans rien réinstaller.

Les formules relient aussi alkoFlix à TMDb Helper (lecteurs fournis par alkoFlix, pris par
défaut), pour que la recherche et les fiches d'Arctic Fuse 3 lancent bien alkoFlix. Elles
proposent un fond d'écran (`packs/fonds/`), donnent à chaque profil le logo de son
extension sur l'écran de choix, et ajoutent au menu Options un bouton pour passer d'un
profil à l'autre.

Les identifiants de replay (TF1+, M6+…) se saisissent depuis le menu du script, dans
le profil Catch-up TV, à la télécommande ou depuis un téléphone du même réseau (le
script affiche une adresse et son QR code). Ils restent sur l'appareil.

Le script installe lui-même les dépôts officiels dont il a besoin (Kodi refuse de les
installer comme dépendances).

Chaque formule demande la version à installer sur le profil alkoFlix :

- **Allégée** (`packs/arctic-fuse-3-leger.zip`) : une rangée par page, pour les boîtiers modestes ;
- **Base** (`packs/arctic-fuse-3.zip`) : l'interface complète ;
- **Full** : la Base, plus vStream (dépôt officiel) en rubrique sur l'accueil et en second
  lecteur de TMDb Helper (fichier `vstream.json` des alKODIques).

« Réinitialiser les réglages » défait l'installation : habillage et réglages d'avant,
plus de profil Catch-up TV ni d'écran de choix. Les extensions restent installées.

Les packs de `packs/` sont fabriqués hors de Kodi ; le script ne propose plus de les
exporter. « Publier la configuration de ce profil » reste disponible pour qui a saisi un
jeton GitHub dans les paramètres de l'extension, et remplace alors le pack en ligne.

## Mettre à jour

Après tout changement dans `repo/<extension>/` (penser à monter le numéro de
version dans son `addon.xml`) :

    python3 _generer.py

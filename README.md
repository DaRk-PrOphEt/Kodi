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

Les identifiants de replay (TF1+, M6+…) se saisissent depuis le menu du script, dans
le profil Catch-up TV. Ils restent sur l'appareil.

Le script installe lui-même les dépôts officiels dont il a besoin (Kodi refuse de les
installer comme dépendances).

Si `packs/arctic-fuse-3-leger.zip` existe (même interface, moins de rangées par page),
les formules demandent « Quel appareil ? » et l'appliquent aux boîtiers modestes.
Depuis le profil alkoFlix, l'export et la publication demandent quelle interface
(complète ou allégée) on vient de régler.

Pour publier un pack : régler l'habillage dans le profil voulu, puis lancer le script
depuis ce profil.

- « Publier la configuration de ce profil sur le dépôt » l'envoie directement dans
  `packs/`. L'entrée n'apparaît que si un jeton GitHub est saisi dans les paramètres
  de l'extension (jeton limité à ce dépôt, permission « Contents : Read and write »).
- Sinon « Exporter » fabrique le zip, à déposer à la main dans `packs/`.

## Mettre à jour

Après tout changement dans `repo/<extension>/` (penser à monter le numéro de
version dans son `addon.xml`) :

    python3 _generer.py

# Welcome Broadcast Bot

Bot Telegram d'accueil avec:

- verification humaine au `/start`
- petite presentation avant validation
- approbation manuelle par admin
- carte d'accueil apres validation avec image + texte + boutons
- panel admin pour envoyer des annonces aux inscrits
- panel admin pour modifier l'accueil approuve et les liens
- commandes slash visibles, dont `/admin`, `/ban` et `/unban`

## Ce que le bot verifie

Le bot peut:

- bloquer les utilisateurs non approuves
- exiger un username si tu actives `REQUIRE_USERNAME=true`
- demander une presentation courte
- remonter quelques signaux simples aux admins, par exemple absence de username

Le bot ne peut pas:

- connaitre l'age reel d'un compte Telegram
- savoir de facon fiable si un compte est "recent"

Pour les faux comptes, le meilleur filtre reste donc:

- captcha
- presentation courte
- approbation manuelle

## Configuration

1. Copie `.env.example` vers ton fichier d'environnement habituel.
2. Renseigne `BOT_TOKEN`.
3. Renseigne `ADMIN_ID_1` et/ou `ADMIN_ID_2`.
4. Adapte `MENU_BUTTONS_JSON` avec tes vrais liens.
5. Optionnel: renseigne `APPROVED_POST_TEXT` et `APPROVED_PHOTO_FILE_ID`.

## Lancement

```powershell
pip install -r requirements.txt
$env:BOT_TOKEN="ton_token"
$env:ADMIN_ID_1="ton_premier_id"
$env:ADMIN_ID_2="8567294409"
python bot.py
```

## Railway

Le dossier contient deja une config Railway prete:

- [railway.json](/C:/Users/Shadow/Desktop/bot test/welcome_broadcast_bot/railway.json)
- [.gitignore](/C:/Users/Shadow/Desktop/bot test/welcome_broadcast_bot/.gitignore)

Configuration conseillee sur Railway:

1. Cree un service a partir de ce dossier ou du repo.
2. Renseigne les variables `BOT_TOKEN`, `ADMIN_ID_1` et `ADMIN_ID_2` dans Railway.
3. Ajoute un volume Railway pour garder `welcome_bot_data.json` apres restart et redeploy.
4. Monte ce volume sur `/data` ou un autre chemin absolu.

Tu peux repartir du fichier:

- [RAILWAY_VARIABLES.example](/C:/Users/Shadow/Desktop/bot test/welcome_broadcast_bot/RAILWAY_VARIABLES.example)

Le bot detecte automatiquement `RAILWAY_VOLUME_MOUNT_PATH` si un volume Railway est attache.
Au premier demarrage, si le volume est vide mais que `welcome_bot_data.json` est present dans le code source, le bot s'en sert comme seed puis continue ensuite sur le volume.

Si tu preferes forcer le chemin du fichier de sauvegarde, utilise:

- `WELCOME_BOT_DATA_FILE=/data/welcome_bot_data.json`

## Commandes

- `/start` : inscription ou ouverture du menu
- `/stop` : desinscription des annonces
- `/admin` : ouvre le panel admin
- `/ban <id>` : retire l'acces a un utilisateur
- `/unban <id>` : redonne l'acces a un utilisateur

## Stockage

Les utilisateurs sont gardes dans `welcome_bot_data.json` dans le meme dossier que le bot.

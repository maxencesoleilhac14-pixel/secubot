# Pack GitHub

Ce dossier peut etre envoye sur GitHub sans le fichier `.env`.

## Important

- Ne pousse pas `.env` sur GitHub.
- Regenerate ton token Telegram avant la mise en ligne, car il a deja ete expose.
- Le fichier `welcome_bot_data.json` est inclus dans le pack actuel pour garder ta configuration du bot.
- Si ton repo doit etre public, pense a retirer `welcome_bot_data.json` avant upload.

## Methode la plus simple sans Git

1. Va sur GitHub.
2. Cree un nouveau repository vide.
3. Ouvre le dossier `github_upload_pack`.
4. Glisse-depose tous les fichiers du dossier dans l'interface web GitHub.
5. Valide le commit.

## Methode avec GitHub Desktop

1. Installe GitHub Desktop.
2. Choisis `Add an Existing Repository from your Hard Drive` si tu initialises un repo local.
3. Sinon cree un nouveau repo a partir du contenu de `github_upload_pack`.
4. Publie sur GitHub.

## Fichiers inclus dans le pack

- `bot.py`
- `requirements.txt`
- `README.md`
- `.gitignore`
- `.env.example`
- `railway.json`
- `RAILWAY_VARIABLES.example`
- `welcome_bot_data.json`
- `GITHUB_UPLOAD.md`

## Railway apres GitHub

1. Connecte le repo a Railway.
2. Ajoute les variables:
   - `BOT_TOKEN`
   - `ADMIN_ID_1`
   - `ADMIN_ID_2`
   - `WELCOME_BOT_DATA_FILE=/data/welcome_bot_data.json`
3. Ajoute un volume Railway monte sur `/data`.
4. Deploy.

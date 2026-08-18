# Ma Bibliothèque

Application locale de gestion de collection de bandes dessinées et de livres — sans compte, sans authentification, pensée pour un usage personnel mono-utilisateur.

Développée selon le cahier des charges convenu : Flask + SQLite, HTMX + Alpine.js pour les interactions dynamiques, TailwindCSS pour le style, le tout packagé en Docker.

## Fonctionnalités

- Collection consultable en grille (couvertures), en liste (tableau), ou en **étagères** (regroupée par série, triée par tome — avec une page dédiée par série affichant les tomes manquants si le nombre total de tomes est renseigné)
- Recherche instantanée (titre, auteur, éditeur, série, ISBN) + filtres combinables (type, série, éditeur, tag, emplacement, état) + tri
- Ajout manuel d'un ouvrage avec tags, emplacement, auteurs, autocomplétion sur les référentiels existants. La série et l'éditeur se choisissent obligatoirement parmi ceux existants (liste déroulante, avec création rapide via un bouton "+" sans quitter la page) pour éviter les doublons dus à une faute de frappe. Le numéro de tome se règle via un curseur incrémentiel (+/-) en plus de la saisie directe.
- Ajout par scan de code-barre (caméra du smartphone) ou saisie manuelle de l'ISBN (PC/tablette), avec récupération automatique des métadonnées via Open Library (repli sur Google Books)
- Récupération automatique de la couverture, ou prise de photo / upload manuel
- Page d'administration en un seul endroit (onglets, sans rechargement de page) : paramètres généraux, gestion des référentiels (types, états, éditeurs, séries, tags, emplacements — avec fusion des doublons), export / import JSON de toute la collection
- **Détection des doublons**, appliquée uniformément partout (ajout manuel, scan, import) : par ISBN en priorité, avec repli sur titre + tome si l'ISBN est absent. Avertissement en direct pendant la saisie, blocage à l'enregistrement avec possibilité de confirmer volontairement, doublons automatiquement ignorés lors d'un import. Politique réglable (voire désactivable) depuis Administration > Paramètres.
- **Statut de lecture** : lu / à lire, bouton de bascule sur la fiche détail, filtre dédié sur la page Collection, conservé à l'export/import JSON
- Mode sombre / clair, disponible dès le premier lancement

## Démarrage rapide (Docker)

```bash
cp .env.example .env
docker compose up -d --build
```

L'application est alors accessible sur `https://localhost:8000` depuis le PC qui héberge le conteneur, et sur `https://<ip-de-la-machine>:8000` depuis un autre appareil du réseau local (notamment votre smartphone).

Les données (base SQLite et couvertures) sont conservées dans `./data/`, en dehors du conteneur : elles survivent aux mises à jour et reconstructions de l'image.

Pour arrêter l'application :

```bash
docker compose down
```

### Activer le scan caméra depuis un smartphone

Les navigateurs (Chrome, Safari...) n'autorisent l'accès à la caméra que sur une connexion **HTTPS** (ou `localhost`). Comme l'application est consultée depuis le réseau local en `http://` par défaut, le scan caméra serait bloqué silencieusement par le téléphone. Pour éviter ça, le conteneur génère automatiquement un **certificat HTTPS auto-signé** au premier lancement et sert l'application en HTTPS.

Pour que ce certificat soit valide pour l'adresse IP de votre machine (et pas seulement `localhost`) :

1. Trouvez l'adresse IP locale de la machine qui héberge Docker (ex. `192.168.1.20`) — `ip a` sous Linux, `ipconfig` sous Windows.
2. Renseignez-la dans `.env` : `HOST_IP=192.168.1.20`
3. Relancez : `docker compose up -d --build`
4. Depuis le smartphone, ouvrez `https://192.168.1.20:8000`

Le certificat étant auto-signé, le navigateur affichera un avertissement de sécurité ("Connexion non privée" ou équivalent) : c'est normal pour une application auto-hébergée sans nom de domaine public. Choisissez "Avancé" puis "Continuer vers le site" — cet avertissement n'apparaîtra qu'une fois par appareil. Une fois la page acceptée, l'accès caméra fonctionne normalement.

Le certificat est stocké dans `./data/certs` et n'est régénéré qu'une seule fois (sauf suppression manuelle de ce dossier ou changement de `HOST_IP`).

Si le message *"Accès caméra impossible"* s'affiche malgré tout sur la page Scanner, vérifiez que l'URL commence bien par `https://` et non `http://`.

### Utilisation derrière un reverse proxy

Si TLS est terminé en amont par un reverse proxy, mettez `HTTPS_AUTOSIGNE=false` dans `.env` : le conteneur ne génère plus de certificat et sert l'application en HTTP simple sur le port 8000.


## Développement local (sans Docker)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
flask init-db
flask run --debug --port 8000
```

## Arborescence du projet

```
biblio-app/
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── run.py
├── app/
│   ├── config.py            # configuration (chemins, clés API...)
│   ├── extensions.py         # SQLAlchemy, Migrate
│   ├── models/                # Ouvrage, Auteur, Editeur, Serie, Tag, Emplacement, Parametre
│   ├── services/               # logique métier (recherche, ISBN, images, ouvrages, paramètres)
│   ├── routes/                  # Blueprints Flask (main, ouvrages, scan, admin)
│   ├── templates/                 # Jinja2 (layout, pages, fragments HTMX, admin)
│   └── static/                      # JS (htmx/alpine/scanner) et couvertures stockées
└── data/                     # créé au premier lancement Docker (base + couvertures), non versionné
```

## Ajouter une nouvelle fonctionnalité

L'architecture est volontairement en couches pour rester simple à faire évoluer :

1. **Modèle** (`app/models/`) si une nouvelle donnée doit être stockée.
2. **Service** (`app/services/`) pour la logique métier — jamais de logique dans les routes.
3. **Route** (`app/routes/`) pour exposer la fonctionnalité, dans le blueprint concerné (ou un nouveau blueprint si le domaine est distinct).
4. **Template** (`app/templates/`) pour l'affichage ; réutilisez les fragments HTMX existants comme modèle pour toute nouvelle vue dynamique.

## Évolution du schéma de données (migrations)

Le tout premier lancement crée les tables directement (`flask init-db`, déjà intégré à l'image Docker). Si vous modifiez les modèles par la suite et souhaitez un suivi de version du schéma via Alembic :

```bash
docker compose exec biblio-app flask db init
docker compose exec biblio-app flask db migrate -m "description du changement"
docker compose exec biblio-app flask db upgrade
```

## Sources de métadonnées ISBN

- [Open Library Books API](https://openlibrary.org/dev/docs/api/books) — gratuite, sans clé
- [Google Books API](https://developers.google.com/books) — gratuite, clé optionnelle (`GOOGLE_BOOKS_API_KEY` dans `.env`) pour des quotas plus élevés

La source prioritaire se configure depuis la page Administration > Paramètres.

Chaque appel envoie un en-tête `User-Agent` identifiant l'application. Open Library recommande d'y inclure un contact (email ou téléphone) : en échange, la limite de débit passe d'1 à 3 requêtes par seconde, et ils peuvent vous prévenir en cas de volume anormal plutôt que de bloquer silencieusement. Renseignez `CONTACT_INFO` dans `.env` pour en bénéficier (facultatif, mais recommandé si vous scannez beaucoup d'ouvrages d'affilée).

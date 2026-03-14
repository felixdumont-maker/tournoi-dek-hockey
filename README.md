# Tournoi Dek Hockey — Plateforme complète

Plateforme de gestion de tournois de dek hockey avec brackets éliminatoires, inscriptions par code d'accès, scores en temps réel via WebSocket, et envoi de courriels automatisés.

## Architecture

```
tournoi.cocktailmedia.ca/          → Page publique (horaire + résultats en direct)
tournoi.cocktailmedia.ca/admin     → Administration (protégé par mot de passe)
tournoi.cocktailmedia.ca/inscription?code=XXX → Inscription des joueurs (protégé par code)
```

## Stack technique

- **Backend** : Python FastAPI + SQLAlchemy + MariaDB
- **WebSocket** : Scores en temps réel sans refresh
- **Frontend** : HTML/CSS/JS vanilla (3 pages)
- **Infra** : Docker Compose + Nginx reverse proxy
- **Email** : SMTP via aiosmtplib

## Installation

### 1. Prérequis

- Docker + Docker Compose
- MariaDB existant en Docker
- Domaine `tournoi.cocktailmedia.ca` pointant vers le serveur

### 2. Configuration

```bash
cp .env.example .env
nano .env  # Remplir les variables
```

Variables importantes :
- `DB_HOST` : nom du container MariaDB existant
- `ADMIN_PASSWORD` : mot de passe pour /admin
- `SECRET_KEY` : chaîne aléatoire de 64 caractères
- `SMTP_*` : configuration email

### 3. Réseau Docker

Le container API doit être sur le même réseau Docker que MariaDB :

```bash
# Vérifie le nom du réseau de ton MariaDB
docker network ls

# Ajuste `mariadb-net` dans docker-compose.yml
```

### 4. Créer la base de données

```bash
docker exec -it mariadb mysql -u root -p
CREATE DATABASE tournoi CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'tournoi'@'%' IDENTIFIED BY 'TON_MOT_DE_PASSE';
GRANT ALL PRIVILEGES ON tournoi.* TO 'tournoi'@'%';
FLUSH PRIVILEGES;
```

### 5. Lancer

```bash
docker-compose up -d
```

Les tables sont créées automatiquement au premier démarrage.

### 6. Nginx principal (sur ton host)

Ajouter dans ta config Nginx principale :

```nginx
server {
    listen 443 ssl;
    server_name tournoi.cocktailmedia.ca;

    ssl_certificate /path/to/cert;
    ssl_certificate_key /path/to/key;

    location / {
        proxy_pass http://localhost:8090;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /ws/ {
        proxy_pass http://localhost:8090;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_read_timeout 86400;
    }
}
```

## Utilisation

### Flow complet

1. **Admin** : Créer un tournoi, ajouter divisions + équipes
2. **Admin** : Générer les codes d'inscription
3. **Admin** : Entrer les emails des capitaines et envoyer les codes
4. **Capitaines** : Inscrire les joueurs via le lien reçu
5. **Admin** : Générer les brackets, configurer l'horaire
6. **Admin** : Passer le tournoi en statut "Actif"
7. **Jour du tournoi** : Entrer les scores dans l'admin → mise à jour en direct pour les spectateurs

### API Documentation

FastAPI génère automatiquement la doc : `tournoi.cocktailmedia.ca/api/docs`

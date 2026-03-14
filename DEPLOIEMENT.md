# Déploiement — Tournoi Dek Hockey
## Commandes exactes pour CocktailOS

Tu es connecté en SSH sur `felix-1234@cocktail:~$`. Voici chaque commande dans l'ordre.

---

## 0. Avant de commencer — Reboot le serveur

Ton serveur affiche "Le système doit être redémarré" et "2 zombie processes". Fais un reboot propre avant tout :

```bash
sudo reboot
```

Attends 1-2 minutes, puis reconnecte-toi en SSH.

---

## 1. Transférer l'archive sur le serveur

Depuis TON POSTE LOCAL (pas le serveur), ouvre un terminal et tape :

```bash
scp tournoi-dekhockey.tar.gz felix-1234@10.0.0.249:~/
```

Si tu accèdes via WireGuard depuis l'extérieur, utilise l'IP VPN à la place.

---

## 2. Extraire et placer les fichiers

De retour dans le SSH du serveur :

```bash
cd ~
tar -xzf tournoi-dekhockey.tar.gz
sudo mv tournoi /opt/tournoi
cd /opt/tournoi
ls -la
```

Tu devrais voir :

```
docker-compose.yml
.env.example
api/
frontend/
nginx/
README.md
DEPLOIEMENT.md
```

---

## 3. Trouver le réseau Docker de ton MariaDB

```bash
docker ps --format "table {{.Names}}\t{{.Image}}\t{{.Status}}" | grep -i maria
```

Note le NOM du container (première colonne). Ensuite :

```bash
docker inspect TON_CONTAINER_MARIADB --format='{{range $key, $val := .NetworkSettings.Networks}}{{$key}} {{end}}'
```

Ça va te donner un nom comme `cocktailos_default` ou `mariadb_network` — note-le.

---

## 4. Configurer docker-compose.yml

```bash
nano /opt/tournoi/docker-compose.yml
```

Change ces deux endroits :

1. Dans le service `api` → `networks`, remplace `mariadb-net` par le vrai nom trouvé à l'étape 3
2. En bas du fichier dans `networks`, même chose :

```yaml
networks:
  tournoi-net:
    driver: bridge
  LE_VRAI_NOM_ICI:
    external: true
```

Sauvegarde : `Ctrl+O`, `Enter`, `Ctrl+X`

---

## 5. Créer le fichier .env

Génère d'abord un secret key :

```bash
openssl rand -hex 32
```

Copie le résultat. Ensuite :

```bash
cp /opt/tournoi/.env.example /opt/tournoi/.env
nano /opt/tournoi/.env
```

Remplis chaque variable :

```
DB_HOST=NOM_DE_TON_CONTAINER_MARIADB
DB_PORT=3306
DB_USER=tournoi
DB_PASSWORD=choisis_un_mot_de_passe
DB_NAME=tournoi

ADMIN_PASSWORD=ton_mot_de_passe_admin

SECRET_KEY=le_resultat_de_openssl_rand

SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=info@cocktailmedia.ca
SMTP_PASSWORD=ton_app_password
SMTP_FROM_NAME=Cocktail Media
SMTP_FROM_EMAIL=info@cocktailmedia.ca

REDIS_URL=redis://redis:6379

BASE_URL=https://tournoi.cocktailmedia.ca
```

Tu peux laisser les SMTP vides pour l'instant si tu veux tester sans email.

Sauvegarde : `Ctrl+O`, `Enter`, `Ctrl+X`

---

## 6. Créer la base de données dans MariaDB

```bash
docker exec -it NOM_DE_TON_CONTAINER_MARIADB mysql -u root -p
```

Entre ton mot de passe root MariaDB, puis :

```sql
CREATE DATABASE tournoi CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'tournoi'@'%' IDENTIFIED BY 'le_meme_mot_de_passe_que_dans_env';
GRANT ALL PRIVILEGES ON tournoi.* TO 'tournoi'@'%';
FLUSH PRIVILEGES;
EXIT;
```

---

## 7. Lancer les containers

```bash
cd /opt/tournoi
docker-compose up -d --build
```

La première fois, ça va prendre 1-2 minutes pour builder l'image Python.

Vérifie que tout roule :

```bash
docker-compose ps
```

Les 3 services doivent être "Up" :

```
tournoi-api     Up
tournoi-redis   Up
tournoi-nginx   Up
```

Si un service est "Restarting" ou "Exit", check les logs :

```bash
docker-compose logs api --tail 30
```

Teste que l'API répond :

```bash
curl http://localhost:8090/api/health
```

Tu devrais avoir : `{"status":"ok","timestamp":"..."}`

---

## 8. Configurer le DNS chez ton registraire

Va dans le panneau de ton registraire de domaine (là où tu gères cocktailmedia.ca) et ajoute :

```
Type:   A
Nom:    tournoi
Valeur: TON_IP_PUBLIQUE
TTL:    300
```

Pour trouver ton IP publique :

```bash
curl -4 ifconfig.me
```

---

## 9. Configurer Nginx sur le host

```bash
sudo nano /etc/nginx/sites-available/tournoi.cocktailmedia.ca
```

Colle ce contenu :

```nginx
server {
    listen 80;
    server_name tournoi.cocktailmedia.ca;

    location / {
        proxy_pass http://127.0.0.1:8090;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /ws/ {
        proxy_pass http://127.0.0.1:8090;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_read_timeout 86400;
    }
}
```

Sauvegarde : `Ctrl+O`, `Enter`, `Ctrl+X`

Active le site :

```bash
sudo ln -s /etc/nginx/sites-available/tournoi.cocktailmedia.ca /etc/nginx/sites-enabled/
```

Teste la config :

```bash
sudo nginx -t
```

Si "syntax is ok" :

```bash
sudo systemctl reload nginx
```

---

## 10. Obtenir le certificat SSL

Si tu n'as pas certbot :

```bash
sudo apt install certbot python3-certbot-nginx -y
```

Puis :

```bash
sudo certbot --nginx -d tournoi.cocktailmedia.ca
```

Suis les instructions. Certbot va automatiquement modifier la config Nginx pour ajouter le HTTPS et la redirection.

---

## 11. Tester

Ouvre dans ton navigateur :

```
https://tournoi.cocktailmedia.ca                → Page publique
https://tournoi.cocktailmedia.ca/admin           → Login admin
https://tournoi.cocktailmedia.ca/api/docs        → Doc API auto-générée
```

---

## Aide-mémoire (commandes du quotidien)

```bash
# Démarrer
cd /opt/tournoi && docker-compose up -d

# Arrêter
cd /opt/tournoi && docker-compose down

# Voir les logs en temps réel
cd /opt/tournoi && docker-compose logs -f

# Logs d'un service spécifique
cd /opt/tournoi && docker-compose logs api --tail 50

# Rebuild après changement de code
cd /opt/tournoi && docker-compose up -d --build api

# Redémarrer un service
cd /opt/tournoi && docker-compose restart api

# Backup de la DB
docker exec NOM_MARIADB mysqldump -u tournoi -p tournoi > ~/backup_tournoi_$(date +%Y%m%d).sql
```

---

## Dépannage

**curl localhost:8090 → "Connection refused"**
→ `docker-compose ps` pour voir si les containers tournent
→ `docker-compose logs api --tail 30` pour voir l'erreur
→ Cause #1 : mauvais DB_HOST dans .env
→ Cause #2 : mot de passe MariaDB incorrect

**Navigateur → "502 Bad Gateway"**
→ Le Nginx du host ne rejoint pas le container
→ Vérifie que le port 8090 dans docker-compose.yml correspond au proxy_pass

**Navigateur → "DNS_PROBE_FINISHED_NXDOMAIN"**
→ Le DNS n'a pas encore propagé, attends 5-15 minutes
→ Vérifie ton enregistrement A chez ton registraire

**Les scores ne se mettent pas à jour en direct (WebSocket)**
→ Vérifie que le bloc `location /ws/` est bien dans ta config Nginx
→ Si derrière Cloudflare, active WebSocket dans les settings du domaine

**Emails ne s'envoient pas**
→ Vérifie SMTP dans .env
→ Gmail nécessite un "App Password" (Google Account → Security → 2FA → App passwords)
→ Teste sans email d'abord, les codes se copient aussi manuellement dans l'admin

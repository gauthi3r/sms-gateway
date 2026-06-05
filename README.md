# 📡 SMS Gateway — Guide d'installation

Interface web Flask pour envoyer et recevoir des SMS via un routeur **4G/5G** (Huawei, Netgear…). Rate limiting, logging sécurisé (mot de passe masqué), validation des numéros FR.

## 🖼️ Aperçu

| Simple | Expert | Fichier groupé |
|--------|--------|----------------|
| ![Mode simple](docs/simple.png) | ![Mode expert](docs/expert.png) | ![Envoi fichier](docs/file.png) |

| Boîte de réception | Boîte d'envoi |
|--------------------|---------------|
| ![Inbox](docs/inbox.png) | ![Outbox](docs/outbox.png) |

| Configuration routeur |
|-----------------------|
| ![Config](docs/config.png) |

---

## 🔌 Configuration multi-routeurs

L'onglet **⚙️ Config** permet de connecter n'importe quel routeur 4G/5G supporté, directement depuis l'interface web — sans toucher aux fichiers de configuration.

| Marque | Bibliothèque | Inbox | Outbox |
|--------|-------------|-------|--------|
| Huawei (B525, B535, B818…) | `huawei-lte-api` | ✅ | ✅ |
| Netgear (LB1120, LB2120, MR1100…) | `eternalegypt` | ✅ | ❌ |

**Champs de connexion :**
- **Adresse IP** du routeur sur le réseau local
- **Utilisateur** (non requis pour Netgear)
- **Mot de passe**

Le bouton **Tester** vérifie la connexion sans sauvegarder. Le bouton **Sauvegarder** applique la configuration immédiatement, sans redémarrage du service.

> La configuration est stockée dans `router_config.json` (non versionné). Le mot de passe n'apparaît jamais dans les logs.

---

## ✅ Prérequis

| Composant      | Détail                                      |
|---------------|---------------------------------------------|
| OS            | Debian 11+, Raspbian (aarch64)               |
| Python        | 3.9+                                        |
| Routeur       | Huawei LTE (B525, B535, B818…) sur réseau local |
| Accès internet | Pour apt + pip (installation uniquement)    |

---

## 🚀 Installation rapide

```bash
git clone https://github.com/Wr1ghtShade/SMS-Gateway.git
cd SMS-Gateway
chmod +x install.sh
sudo ./install.sh
```

Puis **renseigner les identifiants du routeur** :

```bash
nano /var/www/sms-gateway/.env
```

```env
HUAWEI_USER=admin
HUAWEI_PASS=votre_mot_de_passe
HUAWEI_IP=192.168.16.1
```

Puis démarrer :

```bash
sudo systemctl start gateway-sms
```

---

## 📁 Structure déployée

```
/var/www/sms-gateway/
├── gateway-sms-webui.py   # Backend Flask (port 5000)
├── templates/index.html   # Frontend HTML/CSS/JS
├── static/favicon.svg
├── requirements.txt
├── .env                   # Credentials routeur (ne pas versionner)
├── .env.example           # Template vide
├── fix-perms.sh           # Remet les permissions après édition root
├── gateway-sms.service    # Définition systemd
└── venv/                  # Environnement Python
```

---

## 🛠️ Commandes quotidiennes

```bash
# Statut
systemctl is-active gateway-sms
journalctl -u gateway-sms -n 30 --no-pager

# Redémarrer
sudo systemctl restart gateway-sms

# Permissions après édition root
sudo bash /var/www/sms-gateway/fix-perms.sh

# Test rapide
curl -s http://127.0.0.1:5000/health
curl -s http://127.0.0.1:5000/router/status
```

---

## 🔌 Routes API

| Méthode   | Route                  | Description                        |
|-----------|------------------------|------------------------------------|
| GET/POST  | `/send`                | Envoyer un SMS                     |
| POST      | `/send_bulk`           | Envoi groupé en arrière-plan       |
| GET       | `/send_bulk/status`    | Statut de l'envoi groupé           |
| POST      | `/send_bulk/stop`      | Annuler l'envoi groupé             |
| GET       | `/inbox`               | SMS reçus                          |
| GET       | `/outbox`              | SMS envoyés                        |
| POST      | `/delete`              | Supprimer un SMS                   |
| POST      | `/delete_all_sent`     | Supprimer tout l'outbox            |
| GET       | `/health`              | Santé du service et du routeur     |
| GET       | `/router/status`       | Signal, opérateur, type réseau     |

---

## 💬 Envoyer un SMS de test

```bash
curl -s -X POST http://127.0.0.1:5000/send \
  -H "Content-Type: application/json" \
  -d '{"number": "0600000000", "message": "Test 🎉"}'
```

---

## 🔗 Intégration avec des scripts externes

L'endpoint `/send` accepte les requêtes GET avec paramètres URL, ce qui permet de l'appeler depuis n'importe quel script shell, cron ou outil tiers :

```bash
curl -s "http://127.0.0.1:5000/send" \
  --data-urlencode "number=06XXXXXXXX" \
  --data-urlencode "message=Alerte : événement détecté"
```

Exemples d'usage : alertes onduleur (NUT), supervision système, notifications cron, scripts de monitoring.

---

## 🗑️ Désinstallation

```bash
sudo systemctl stop gateway-sms
sudo systemctl disable gateway-sms
sudo rm /etc/systemd/system/gateway-sms.service
sudo systemctl daemon-reload
sudo rm -rf /var/www/sms-gateway
```

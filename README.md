# SMS Gateway — Guide d'installation

Interface web Flask pour envoyer et recevoir des SMS via un routeur **Huawei LTE** (testé sur B525s-23a). Rate limiting, logging sécurisé (mot de passe masqué), validation des numéros FR.

![SMS Gateway](docs/sms-gateway-screen.png)

---

## Prérequis

| Composant      | Détail                                      |
|---------------|---------------------------------------------|
| OS            | Debian 11+, Raspbian (aarch64)               |
| Python        | 3.9+                                        |
| Routeur       | Huawei LTE (B525, B535, B818…) sur réseau local |
| Accès internet | Pour apt + pip (installation uniquement)    |

---

## Installation rapide

```bash
git clone https://github.com/gauthi3r/SMS-Gateway.git
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

## Structure déployée

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

## Commandes quotidiennes

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

## Routes API

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

## Envoyer un SMS de test

```bash
curl -s -X POST http://127.0.0.1:5000/send \
  -H "Content-Type: application/json" \
  -d '{"number": "0600000000", "message": "Test 🎉"}'
```

---

## Intégration NUT (onduleur)

Le script `/etc/nut/notify.sh` appelle `/send` en GET pour alerter par SMS lors de coupures secteur.

---

## Désinstallation

```bash
sudo systemctl stop gateway-sms
sudo systemctl disable gateway-sms
sudo rm /etc/systemd/system/gateway-sms.service
sudo systemctl daemon-reload
sudo rm -rf /var/www/sms-gateway
```

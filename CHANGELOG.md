# Changelog — SMS Gateway

---

## [1.00.16] — 2026-06-04
### UX
- Suppression du `padding-right` sur le `h1` qui décentrait le titre "SMS Hub"

---

## [1.00.15] — 2026-06-04
### UX
- Boutons de thème remis en `position: absolute` en haut à droite (24px, plus petits)
- Padding réservé sur le `h1` pour éviter le chevauchement sur mobile

---

## [1.00.14] — 2026-06-04
### UX
- Boutons de thème réduits (26px) et repositionnés en ligne centrée pour corriger le chevauchement mobile

---

## [1.00.13] — 2026-06-04
### Nouveautés
- Widget statut routeur : signal (barres), opérateur, type réseau (4G LTE, etc.), rafraîchi toutes les 30s
- Compteur de caractères SMS sous chaque textarea : détection GSM-7 vs Unicode, nombre de SMS calculé
- Endpoint `GET /health` : répond 200 si le routeur est joignable, 503 sinon
- Endpoint `GET /router/status` : retourne signal, opérateur, type réseau, solde
- Script `fix-perms.sh` : remet les bonnes permissions après édition (gauthi3r:www-data)

---

## [1.00.12] — 2026-06-04
### Corrections de bugs
- Validation des numéros ajoutée dans `perform_bulk_send` (les numéros invalides passaient silencieusement en "ok")
- Validation upfront dans `/send_bulk` : la route rejette toute la liste si un numéro est invalide
- Projet déplacé de `/root/sms-gateway` vers `/var/www/sms-gateway`
- Service systemd migré de `root:root` vers `www-data:www-data`
- Permissions : `gauthi3r` propriétaire (écriture), `www-data` groupe (lecture/exécution)

---

## [1.00.11] — 2026-06-04
### UX
- Suppression de la confirmation d'envoi (dialog inutile avant chaque envoi)

---

## [1.00.10] — 2026-06-04
### Sécurité
- Credentials (HUAWEI_USER, HUAWEI_PASS, HUAWEI_IP) sortis du code source
- Chargement via `python-dotenv` depuis un fichier `.env`
- Ajout d'un `.env.example` comme template versionnable
- Démarrage bloqué avec message clair si HUAWEI_PASS manquant

---

## [1.00.09] — 2026-06-04
### Refacto
- HTML (~400 lignes) extrait du fichier Python vers `templates/index.html`
- `render_template_string(HTML_PAGE)` remplacé par `render_template('index.html')`
- `sms-ups-alert-flask.py` supprimé (fonctionnellement remplacé par le projet principal)

---

## [1.00.08] — 2026-06-04
### UX
- Ajout d'un bouton ⏹ Stop visible pendant un envoi groupé
- Appel à `POST /send_bulk/stop` pour interrompre le thread d'envoi entre deux SMS
- Message de log affiché en cas d'annulation par l'utilisateur

---

## [1.00.07] — 2026-06-04
### UX
- Zone de progression (barre + logs) désormais persistante lors des changements d'onglet pendant un envoi
- Variable `isSending` côté JS pour bloquer le masquage de la zone de progression

---

## [1.00.06] — 2026-06-04
### Performance
- Envoi groupé migré en arrière-plan serveur via `POST /send_bulk`
- Réduction de N requêtes HTTP à 1 seule depuis le navigateur
- Ajout de `GET /send_bulk/status` pour le polling du statut
- Ajout de `POST /send_bulk/stop` pour l'annulation
- Page fluide pendant tout l'envoi (plus de boucle bloquante JS)

---

## [1.00.05] — 2026-06-04
### Corrections de bugs
- `if not idx` → `if idx is None` (index SMS = 0 ne déclenchait plus une erreur à tort)
- Suppression de la réinitialisation d'état redondante dans `perform_bulk_delete`
- Limite hardcodée à 15 itérations remplacée par `while True` (suppression complète quelle que soit la taille de l'outbox)

---

## [1.00.04] — 2026-06-04
### UX
- Suppression de l'alerte de succès après une suppression globale de l'outbox (doublon pénible)

---

## [1.00.03] — 2026-06-04
### Refacto
- Extraction de `parse_sms_list()` — logique de parsing SMS dédupliquée (3 occurrences → 1 fonction)
- `ROUTER_URL` définie comme constante globale — suppression des 5 reconstructions en inline
- `deleteSms(index, onSuccess)` — fusion de `deleteSms` et `deleteSentSms` en une seule fonction JS avec callback

---

## [1.00.02] — 2026-06-04
### Sécurité
- Ajout de la validation des numéros de téléphone côté serveur
- Formats acceptés : `06XXXXXXXX`, `07XXXXXXXX`, `+336XXXXXXXX`, `+337XXXXXXXX`
- Espaces et tirets nettoyés avant validation
- Réponse `400` avec message explicite si numéro invalide

---

## [1.00.01] — Version initiale
- Interface web Flask pour l'envoi de SMS via routeur Huawei LTE
- Modes d'envoi : Simple, File (.txt), Expert (numéro;message)
- Lecture Inbox / Outbox
- Suppression individuelle et suppression globale de l'outbox (arrière-plan)
- 4 thèmes UI : Clair, Sombre, Cyber, Dracula
- Sanitization du mot de passe dans les messages d'erreur

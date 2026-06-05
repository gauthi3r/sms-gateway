#!/bin/bash
# Remet les bonnes permissions après une modification des fichiers
# (les edits via root réinitialisent owner:group en root:root)

PROJECT=/var/www/sms-gateway

# Détection de l'utilisateur propriétaire (celui qui a lancé sudo)
OWNER="${SUDO_USER:-$(logname 2>/dev/null || whoami)}"

echo "Application des permissions sur $PROJECT..."

chown -R "${OWNER}:www-data" "$PROJECT"
find "$PROJECT" -type d -exec chmod 750 {} \;
find "$PROJECT" -type f -exec chmod 640 {} \;
find "$PROJECT/venv/bin" -type f -exec chmod 750 {} \;
chmod 640 "$PROJECT/.env"
chmod +x "$PROJECT/fix-perms.sh"

echo "✅ Permissions OK"
echo "   Owner    : ${OWNER}:www-data"
echo "   Dossiers : 750 (rwxr-x---)"
echo "   Fichiers : 640 (rw-r-----)"
echo "   .env     : 640 (rw-r-----)"

#!/bin/bash
# ============================================================
#  SMS Gateway — Script d'installation automatisé
#  Testé : Debian 11/12, Raspbian (aarch64)
#  Prérequis : exécuter en tant que root (sudo ./install.sh)
# ============================================================
set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; BOLD='\033[1m'; NC='\033[0m'

ok()   { echo -e "  ${GREEN}✓${NC} $1"; }
warn() { echo -e "  ${YELLOW}⚠${NC} $1"; }
err()  { echo -e "  ${RED}✗ ERREUR :${NC} $1"; exit 1; }
step() { echo -e "\n${BLUE}${BOLD}[$1/$TOTAL_STEPS]${NC}${BOLD} $2${NC}"; }

TOTAL_STEPS=7

APP_NAME="gateway-sms"
APP_DIR="/var/www/sms-gateway"
INSTALL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OWNER="${SUDO_USER:-$(logname 2>/dev/null || whoami)}"

echo -e "\n${BOLD}SMS Gateway — Installation${NC}\n"

[ "$EUID" -ne 0 ] && err "Exécuter en tant que root : sudo ./install.sh"
[ -f "$INSTALL_DIR/gateway-sms-webui.py" ] || err "Source corrompue : gateway-sms-webui.py introuvable."

# ============================================================

step 1 "Mise à jour APT et installation des paquets système"

apt-get update -qq
apt-get install -y --no-install-recommends \
    python3 python3-venv python3-pip \
    > /dev/null 2>&1
ok "Python3 installé."

# ============================================================

step 2 "Création du répertoire et copie des fichiers"

if [ -d "$APP_DIR" ]; then
    BACKUP="/var/www/sms-gateway_backup_$(date +%Y%m%d_%H%M%S)"
    warn "Installation existante détectée. Sauvegarde vers $BACKUP"
    cp -r "$APP_DIR" "$BACKUP" 2>/dev/null || true
fi

mkdir -p "$APP_DIR/templates"
mkdir -p "$APP_DIR/static"

cp "$INSTALL_DIR/gateway-sms-webui.py"  "$APP_DIR/"
cp "$INSTALL_DIR/templates/index.html"  "$APP_DIR/templates/"
cp "$INSTALL_DIR/static/favicon.svg"    "$APP_DIR/static/"
cp "$INSTALL_DIR/requirements.txt"      "$APP_DIR/"
cp "$INSTALL_DIR/CHANGELOG.md"          "$APP_DIR/"
cp "$INSTALL_DIR/fix-perms.sh"          "$APP_DIR/"
cp "$INSTALL_DIR/gateway-sms.service"   "$APP_DIR/"
ok "Fichiers copiés vers $APP_DIR"

# ============================================================

step 3 "Fichier de configuration .env"

if [ ! -f "$APP_DIR/.env" ]; then
    cp "$INSTALL_DIR/.env.example" "$APP_DIR/.env"
    warn ".env créé depuis .env.example — vous devez le remplir avant de démarrer !"
    warn "Éditez : nano $APP_DIR/.env"
else
    ok ".env existant conservé."
fi

# ============================================================

step 4 "Environnement virtuel Python"

python3 -m venv "$APP_DIR/venv"
ok "venv créé."

"$APP_DIR/venv/bin/pip" install --upgrade pip --quiet
"$APP_DIR/venv/bin/pip" install -r "$APP_DIR/requirements.txt" --quiet
ok "Dépendances installées (Flask, huawei-lte-api, flask-limiter…)"

# ============================================================

step 5 "Installation du service systemd"

cp "$APP_DIR/gateway-sms.service" /etc/systemd/system/gateway-sms.service
systemctl daemon-reload
ok "Service systemd enregistré : gateway-sms.service"

# ============================================================

step 6 "Application des permissions"

chown -R "${OWNER}:www-data" "$APP_DIR"
find "$APP_DIR" -type d -exec chmod 750 {} \;
find "$APP_DIR" -type f -exec chmod 640 {} \;
find "$APP_DIR/venv/bin" -type f -exec chmod 750 {} \;
chmod 640 "$APP_DIR/.env"
chmod +x  "$APP_DIR/fix-perms.sh"
ok "Permissions appliquées (${OWNER}:www-data)."

# ============================================================

step 7 "Activation du service"

systemctl enable "$APP_NAME" > /dev/null 2>&1

# Vérifier si .env est rempli avant de démarrer
HUAWEI_PASS_VAL=$(grep -E '^HUAWEI_PASS=' "$APP_DIR/.env" | cut -d= -f2)

if [ -z "$HUAWEI_PASS_VAL" ]; then
    warn "HUAWEI_PASS vide dans .env — le service ne sera PAS démarré."
    warn "1. Remplissez le .env : nano $APP_DIR/.env"
    warn "2. Puis démarrez : sudo systemctl start gateway-sms"
else
    systemctl start "$APP_NAME"
    sleep 2
    if systemctl is-active --quiet "$APP_NAME"; then
        ok "Service '$APP_NAME' actif."
    else
        warn "Démarrage échoué. Vérifiez : journalctl -u $APP_NAME -n 20"
    fi
fi

# ============================================================

IP=$(hostname -I 2>/dev/null | awk '{print $1}' || echo "127.0.0.1")

echo ""
echo -e "${GREEN}${BOLD}══════════════════════════════════════════════════${NC}"
echo -e "${GREEN}${BOLD}  ✓  SMS Gateway installé !${NC}"
echo -e "${GREEN}${BOLD}══════════════════════════════════════════════════${NC}"
echo ""
echo -e "  ${BOLD}URL locale       :${NC} http://${IP}:5000"
echo -e "  ${BOLD}Répertoire       :${NC} ${APP_DIR}"
echo -e "  ${BOLD}Config           :${NC} nano ${APP_DIR}/.env"
echo ""
echo -e "  ${BOLD}Commandes utiles :${NC}"
echo -e "  sudo systemctl start   gateway-sms     # Démarrer"
echo -e "  sudo systemctl restart gateway-sms     # Redémarrer"
echo -e "  journalctl -u gateway-sms -f           # Logs en direct"
echo -e "  sudo bash ${APP_DIR}/fix-perms.sh      # Permissions"
echo ""

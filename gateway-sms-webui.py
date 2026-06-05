from flask import Flask, request, jsonify, render_template, Response
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from huawei_lte_api.Client import Client
from huawei_lte_api.Connection import Connection
from dataclasses import dataclass, field
from functools import wraps
from dotenv import load_dotenv
import secrets
import os
import re
import time
import threading
import logging

# --- CONFIGURATION (chargée avant le logging pour pouvoir sanitiser) ---
load_dotenv()
USER_HUAWEI = os.getenv('HUAWEI_USER', 'admin')
PASS_HUAWEI = os.getenv('HUAWEI_PASS', '')
IP_HUAWEI   = os.getenv('HUAWEI_IP', '192.168.16.1')

if not PASS_HUAWEI:
    raise RuntimeError("HUAWEI_PASS manquant dans le fichier .env")

# --- LOGGING — le mot de passe est effacé de toute sortie (message + traceback) ---
class _SanitizingFormatter(logging.Formatter):
    def format(self, record):
        msg = super().format(record)
        return msg.replace(PASS_HUAWEI, '********') if PASS_HUAWEI else msg

_handler = logging.StreamHandler()
_handler.setFormatter(_SanitizingFormatter('%(asctime)s [%(levelname)s] %(message)s'))
logging.root.setLevel(logging.INFO)
logging.root.addHandler(_handler)
logger = logging.getLogger(__name__)

# --- LIMITES ---
MAX_MESSAGE_LENGTH = 480  # ~3 SMS GSM-7
MAX_BULK_TASKS     = 200
# -------------------------------------------

# --- VALIDATION ---
PHONE_RE = re.compile(r'^(0[67][0-9]{8}|\+33[67][0-9]{8})$')

def validate_number(number):
    return bool(PHONE_RE.match(number.replace(' ', '').replace('-', '')))

def sanitize_exception(e):
    err_str = str(e)
    if PASS_HUAWEI and PASS_HUAWEI in err_str:
        err_str = err_str.replace(PASS_HUAWEI, '********')
    return err_str

# --- ÉTAT ARRIÈRE-PLAN ---
@dataclass
class BulkDeleteState:
    lock: threading.Lock = field(default_factory=threading.Lock)
    in_progress: bool = False
    deleted_count: int = 0
    error: str = None

@dataclass
class BulkSendState:
    lock: threading.Lock = field(default_factory=threading.Lock)
    in_progress: bool = False
    stop_requested: bool = False
    total: int = 0
    sent: int = 0
    errors: int = 0
    logs: list = field(default_factory=list)

delete_state = BulkDeleteState()
send_state   = BulkSendState()

# --- CACHE STATUT ROUTEUR ---
_router_status_cache: dict = {'data': None, 'ts': 0.0}
ROUTER_STATUS_TTL = 5  # secondes
# ----------------------------

app = Flask(__name__)

# --- RATE LIMITING ---
limiter = Limiter(get_remote_address, app=app, default_limits=[], storage_uri="memory://")

# --- CSRF ---
CSRF_TOKEN = secrets.token_hex(32)

def csrf_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if request.method == 'POST':
            if request.headers.get('X-CSRF-Token') != CSRF_TOKEN:
                return jsonify({'status': 'error', 'message': 'Token CSRF invalide'}), 403
        return f(*args, **kwargs)
    return decorated

# --- ASTUCE DE COMPATIBILITE (NE PAS TOUCHER) ---
# Contourne le bug de la librairie Huawei "int has no attribute value"
class BoxTypeInbox:
    value = 1

class BoxTypeSent:
    value = 2

ROUTER_URL = f'http://{USER_HUAWEI}:{PASS_HUAWEI}@{IP_HUAWEI}/'

def parse_sms_list(sms_list):
    messages = []
    if 'Messages' in sms_list and 'Message' in sms_list['Messages']:
        raw_msgs = sms_list['Messages']['Message']
        if isinstance(raw_msgs, dict):
            raw_msgs = [raw_msgs]
        for msg in raw_msgs:
            messages.append({
                'Index': msg.get('Index'),
                'Phone': msg.get('Phone'),
                'Content': msg.get('Content'),
                'Date': msg.get('Date')
            })
    return messages

# --- ROUTE PAGE D'ACCUEIL ---
@app.route('/')
def home():
    return render_template('index.html', csrf_token=CSRF_TOKEN)

# --- ROUTE API ENVOI (GET & POST) ---
@app.route('/send', methods=['GET', 'POST'])
@limiter.limit("200 per 10 minutes")
@csrf_required
def send_sms_api():
    if request.is_json:
        data = request.get_json()
        number  = data.get('number')
        message = data.get('message')
    else:
        number  = request.args.get('number')
        message = request.args.get('message')

    if not number or not message:
        return jsonify({'status': 'error', 'message': 'Données manquantes'}), 400

    if not validate_number(number):
        return jsonify({'status': 'error', 'message': f'Numéro invalide : {number}'}), 400

    if len(message) > MAX_MESSAGE_LENGTH:
        return jsonify({'status': 'error', 'message': f'Message trop long (max {MAX_MESSAGE_LENGTH} caractères)'}), 400

    try:
        logger.info("SEND > %s", number)
        with Connection(ROUTER_URL) as connection:
            client = Client(connection)
            client.sms.send_sms([number], message)
        return jsonify({'status': 'success', 'to': number}), 200
    except Exception as e:
        logger.error("ERREUR SEND", exc_info=True)
        return jsonify({'status': 'error', 'message': f'Erreur lors de l\'envoi : {sanitize_exception(e)}'}), 500

# --- ROUTE : LIRE INBOX ---
@app.route('/inbox', methods=['GET'])
def get_inbox():
    page     = max(1, request.args.get('page', 1, type=int))
    per_page = 20
    try:
        with Connection(ROUTER_URL) as connection:
            client = Client(connection)
            sms_list = client.sms.get_sms_list(page=page, box_type=BoxTypeInbox, read_count=per_page)
            messages = parse_sms_list(sms_list)
        return jsonify({'status': 'success', 'messages': messages, 'page': page, 'has_more': len(messages) == per_page}), 200
    except Exception as e:
        logger.error("ERREUR INBOX", exc_info=True)
        return jsonify({'status': 'error', 'message': f'Impossible de charger la boîte de réception : {sanitize_exception(e)}'}), 500

# --- ROUTE : SUPPRIMER SMS ---
@app.route('/delete', methods=['POST'])
@csrf_required
def delete_sms():
    data = request.get_json()
    try:
        idx = int(data.get('index'))
    except (TypeError, ValueError):
        return jsonify({'status': 'error', 'message': 'Index invalide'}), 400

    try:
        with Connection(ROUTER_URL) as connection:
            client = Client(connection)
            client.sms.delete_sms([idx])
        return jsonify({'status': 'success', 'deleted': idx}), 200
    except Exception as e:
        logger.error("ERREUR DELETE", exc_info=True)
        return jsonify({'status': 'error', 'message': f'Impossible de supprimer le SMS : {sanitize_exception(e)}'}), 500

# --- ROUTE : LIRE OUTBOX ---
@app.route('/outbox', methods=['GET'])
def get_outbox():
    page     = max(1, request.args.get('page', 1, type=int))
    per_page = 50
    try:
        with Connection(ROUTER_URL) as connection:
            client = Client(connection)
            sms_list = client.sms.get_sms_list(page=page, box_type=BoxTypeSent, read_count=per_page)
            messages = parse_sms_list(sms_list)
        return jsonify({'status': 'success', 'messages': messages, 'page': page, 'has_more': len(messages) == per_page}), 200
    except Exception as e:
        logger.error("ERREUR OUTBOX", exc_info=True)
        return jsonify({'status': 'error', 'message': f'Impossible de charger la boîte d\'envoi : {sanitize_exception(e)}'}), 500

def perform_bulk_delete():
    try:
        with Connection(ROUTER_URL) as connection:
            client = Client(connection)
            while True:
                sms_list = client.sms.get_sms_list(page=1, box_type=BoxTypeSent, read_count=50)
                indices = [m['Index'] for m in parse_sms_list(sms_list) if m.get('Index')]
                if not indices:
                    break
                client.sms.delete_sms(indices)
                with delete_state.lock:
                    delete_state.deleted_count += len(indices)
                if len(indices) < 50:
                    break
                time.sleep(0.5)
    except Exception as e:
        logger.error("ERREUR SUPPRESSION ARRIÈRE-PLAN", exc_info=True)
        with delete_state.lock:
            delete_state.error = str(e)
    finally:
        with delete_state.lock:
            delete_state.in_progress = False

# --- ROUTE : SUPPRIMER TOUT L'OUTBOX ---
@app.route('/delete_all_sent', methods=['POST'])
@csrf_required
def delete_all_sent_api():
    with delete_state.lock:
        if delete_state.in_progress:
            return jsonify({'status': 'error', 'message': 'Une suppression globale est déjà en cours.'}), 400
        delete_state.in_progress = True
        delete_state.deleted_count = 0
        delete_state.error = None
    threading.Thread(target=perform_bulk_delete, daemon=True).start()
    return jsonify({'status': 'success', 'message': 'Suppression globale démarrée en arrière-plan.'}), 202

# --- ROUTE : STATUT DE LA SUPPRESSION GLOBALE ---
@app.route('/delete_all_sent/status', methods=['GET'])
def delete_all_sent_status():
    with delete_state.lock:
        return jsonify({
            'status': 'success',
            'in_progress': delete_state.in_progress,
            'deleted_count': delete_state.deleted_count,
            'error': sanitize_exception(delete_state.error) if delete_state.error else None
        }), 200

def perform_bulk_send(tasks, delay=1.0):
    try:
        with Connection(ROUTER_URL) as connection:
            client = Client(connection)
            for task in tasks:
                with send_state.lock:
                    if send_state.stop_requested:
                        send_state.logs.append({'number': '—', 'status': 'error', 'detail': 'Envoi annulé par l\'utilisateur.'})
                        break
                number  = task.get('number', '')
                message = task.get('message', '')
                if not validate_number(number):
                    with send_state.lock:
                        send_state.errors += 1
                        send_state.logs.append({'number': number, 'status': 'error', 'detail': 'Numéro invalide'})
                    continue
                try:
                    client.sms.send_sms([number], message)
                    with send_state.lock:
                        send_state.sent += 1
                        send_state.logs.append({'number': number, 'status': 'ok'})
                except Exception as e:
                    with send_state.lock:
                        send_state.errors += 1
                        send_state.logs.append({'number': number, 'status': 'error', 'detail': sanitize_exception(e)})
                time.sleep(delay)
    except Exception as e:
        logger.error("ERREUR BULK SEND", exc_info=True)
        with send_state.lock:
            send_state.errors += 1
            send_state.logs.append({'number': '?', 'status': 'error', 'detail': f'Connexion perdue : {sanitize_exception(e)}'})
    finally:
        with send_state.lock:
            send_state.in_progress = False

@app.route('/send_bulk', methods=['POST'])
@limiter.limit("10 per 10 minutes")
@csrf_required
def send_bulk_api():
    data  = request.get_json()
    tasks = data.get('tasks', []) if data else []
    try:
        delay = float(data.get('delay', 1.0))
        delay = max(0.5, min(5.0, delay))
    except (TypeError, ValueError):
        delay = 1.0

    if not tasks:
        return jsonify({'status': 'error', 'message': 'Aucune tâche fournie.'}), 400

    if len(tasks) > MAX_BULK_TASKS:
        return jsonify({'status': 'error', 'message': f'Trop de destinataires (max {MAX_BULK_TASKS}).'}), 400

    invalid = [t.get('number') for t in tasks if not validate_number(t.get('number', ''))]
    if invalid:
        return jsonify({'status': 'error', 'message': f'Numéro(s) invalide(s) : {", ".join(invalid)}'}), 400

    with send_state.lock:
        if send_state.in_progress:
            return jsonify({'status': 'error', 'message': 'Un envoi groupé est déjà en cours.'}), 400
        send_state.in_progress    = True
        send_state.stop_requested = False
        send_state.total          = len(tasks)
        send_state.sent           = 0
        send_state.errors         = 0
        send_state.logs           = []

    threading.Thread(target=perform_bulk_send, args=(tasks, delay), daemon=True).start()
    return jsonify({'status': 'success', 'message': 'Envoi groupé démarré.', 'total': len(tasks)}), 202

@app.route('/send_bulk/stream')
def send_bulk_stream():
    import json as _json
    def generate():
        # Attend que l'envoi démarre (garde contre race condition client/serveur)
        deadline = time.time() + 2
        while not send_state.in_progress and time.time() < deadline:
            time.sleep(0.05)

        if not send_state.in_progress:
            yield f"data: {_json.dumps({'done': True, 'sent': 0, 'errors': 0, 'total': 0})}\n\n"
            return

        last = 0
        while True:
            with send_state.lock:
                logs    = list(send_state.logs)
                in_prog = send_state.in_progress
                sent    = send_state.sent
                errors  = send_state.errors
                total   = send_state.total

            for log in logs[last:]:
                yield f"data: {_json.dumps(log)}\n\n"
            last = len(logs)

            if not in_prog:
                yield f"data: {_json.dumps({'done': True, 'sent': sent, 'errors': errors, 'total': total})}\n\n"
                return

            time.sleep(0.3)

    return Response(
        generate(),
        mimetype='text/event-stream',
        headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'}
    )

@app.route('/send_bulk/stop', methods=['POST'])
@csrf_required
def send_bulk_stop():
    with send_state.lock:
        if not send_state.in_progress:
            return jsonify({'status': 'error', 'message': 'Aucun envoi en cours.'}), 400
        send_state.stop_requested = True
    return jsonify({'status': 'success', 'message': 'Arrêt demandé.'}), 200

@app.route('/send_bulk/status', methods=['GET'])
def send_bulk_status():
    with send_state.lock:
        return jsonify({
            'status': 'success',
            'in_progress': send_state.in_progress,
            'total': send_state.total,
            'sent': send_state.sent,
            'errors': send_state.errors,
            'logs': list(send_state.logs)
        }), 200

@app.route('/health', methods=['GET'])
def health():
    try:
        with Connection(ROUTER_URL) as connection:
            client = Client(connection)
            client.device.information()
        return jsonify({'status': 'ok', 'router': 'reachable'}), 200
    except Exception as e:
        return jsonify({'status': 'error', 'router': 'unreachable', 'detail': sanitize_exception(e)}), 503

def _fetch_router_status():
    with Connection(ROUTER_URL) as connection:
        client = Client(connection)
        monitoring    = client.monitoring.status()
        signal_bars   = int(monitoring.get('SignalIcon', 0))
        network_type  = monitoring.get('CurrentNetworkType', '')
        try:
            plmn     = client.net.current_plmn()
            operator = plmn.get('FullName') or plmn.get('ShortName') or '—'
        except Exception:
            operator = '—'
        network_map = {
            '0': 'GPRS', '1': 'GPRS', '2': 'EDGE',  '3': 'WCDMA',
            '4': 'HSDPA','5': 'HSUPA','6': 'HSPA',   '7': 'HSPA+',
            '8': 'TDSCDMA','9': 'HSPA+','10': 'EVDO','19': '4G LTE',
            '41': '3G+', '101': '4G+'
        }
        return {
            'status':      'ok',
            'signal_bars': signal_bars,
            'network':     network_map.get(str(network_type), f'Type {network_type}'),
            'operator':    operator,
        }

@app.route('/router/status', methods=['GET'])
def router_status():
    now = time.time()
    if _router_status_cache['data'] and now - _router_status_cache['ts'] < ROUTER_STATUS_TTL:
        return jsonify(_router_status_cache['data']), 200
    try:
        result = _fetch_router_status()
        _router_status_cache['data'] = result
        _router_status_cache['ts']   = now
        return jsonify(result), 200
    except Exception as e:
        return jsonify({'status': 'error', 'detail': sanitize_exception(e)}), 503

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)

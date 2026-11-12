from flask import Flask, render_template, request, redirect, flash, url_for, jsonify, send_from_directory
import os
from datetime import datetime
import calendar
import json
import hashlib
import hmac
import ipaddress
import secrets
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from merge_pppoe import main as merge_pppoe_automatically
from pathlib import Path
from threading import RLock, Thread
from time import monotonic, sleep
from urllib.parse import urlsplit
from uuid import uuid4

BASE_DIR = Path(__file__).resolve().parent
try:
    from dotenv import load_dotenv
    load_dotenv(BASE_DIR / ".env")
except ImportError:
    pass

try:
    from pywebpush import webpush, WebPushException
except ImportError:
    webpush = None
    WebPushException = Exception

app = Flask(__name__)
app.secret_key = "lifemedia-jaya-jaya-keren"

ROOT_DIR = Path(os.environ.get("JSS_ROOT", BASE_DIR))
DATA_DIR = ROOT_DIR / 'data'
RUNTIME_DIR = ROOT_DIR / 'runtime'

NOTIFICATIONS_FILE = DATA_DIR / 'notifications.json'
NOTIFICATIONS_BAK_FILE = f"{NOTIFICATIONS_FILE}.bak"
OUTAGES_FILE = DATA_DIR / 'outages.json'
BACKUP_DIR = RUNTIME_DIR / 'backups'
HISTORY_FILE = RUNTIME_DIR / 'history.json' 
QUEUE_FILE = DATA_DIR / 'queue_user_pppoe.json'
USER_PPPOE_FILE = DATA_DIR / 'user_pppoe.json'
USER_LOG_FILE = RUNTIME_DIR / 'user_log.json'
USER_TEMP_FILE = DATA_DIR / "user_temp.json"
USER_PPPOES_FILE = DATA_DIR / "pppoes.json"
PPPOES_TEMP_FILE = DATA_DIR / "pppoes_temp.json"
MANUAL_FILE = DATA_DIR / "user_manual.json"
PUSH_SUBSCRIPTIONS_FILE = DATA_DIR / "push_subscriptions.json"
PPPOE_STATUS_STATE_FILE = RUNTIME_DIR / "pppoe_status_state.json"
MIKROTIK_HEARTBEAT_ALERT_FILE = RUNTIME_DIR / "mikrotik_heartbeat_alerts.json"

VAPID_PUBLIC_KEY = os.environ.get("VAPID_PUBLIC_KEY", "").strip()
VAPID_SUBJECT = os.environ.get("VAPID_SUBJECT", "").strip()
VAPID_PRIVATE_KEY_FILE = os.environ.get(
    "VAPID_PRIVATE_KEY_FILE", "runtime/secrets/vapid_private.pem"
).strip()
PUSH_ENROLLMENT_TOKEN = os.environ.get("PUSH_ENROLLMENT_TOKEN", "").strip()
MIKROTIK_API_TOKEN = os.environ.get("MIKROTIK_API_TOKEN", "").strip()
PUSH_PUBLIC_BASE_URL = os.environ.get("PUBLIC_BASE_URL", "").rstrip("/")
try:
    PPPOE_STATUS_CONFIRMATIONS = max(1, int(os.environ.get("PPPOE_STATUS_CONFIRMATIONS", "2")))
except ValueError:
    PPPOE_STATUS_CONFIRMATIONS = 2
try:
    MIKROTIK_HEARTBEAT_TIMEOUT_SECONDS = max(
        60, int(os.environ.get("MIKROTIK_HEARTBEAT_TIMEOUT_SECONDS", "180"))
    )
except ValueError:
    MIKROTIK_HEARTBEAT_TIMEOUT_SECONDS = 180
MIKROTIK_HEARTBEAT_CHECK_INTERVAL_SECONDS = 15

router_state_cache = {}
global_history_buffer = None
PUSH_LOCK = RLock()
STATUS_LOCK = RLock()
DATA_LOCK = RLock()
PUSH_TOKEN_FAILURE_LOCK = RLock()
PUSH_TOKEN_FAILURES = {}
PUSH_TOKEN_MAX_FAILURES = 10
PUSH_TOKEN_FAILURE_WINDOW = 300
PUSH_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="web-push")
MIKROTIK_HEARTBEAT_LOCK = RLock()


def _resolve_vapid_private_key():
    path = Path(VAPID_PRIVATE_KEY_FILE)
    return path if path.is_absolute() else BASE_DIR / path


def _valid_push_enrollment_token(value):
    return (
        isinstance(value, str)
        and 5 <= len(value) <= 8
        and value.isascii()
        and value.isalnum()
    )


def _push_is_configured():
    return bool(
        webpush
        and VAPID_PUBLIC_KEY
        and VAPID_SUBJECT
        and _valid_push_enrollment_token(PUSH_ENROLLMENT_TOKEN)
        and _resolve_vapid_private_key().is_file()
    )


def _push_token_authorized():
    supplied = request.headers.get("Authorization", "")
    if supplied.lower().startswith("bearer "):
        supplied = supplied[7:].strip()
    if not _valid_push_enrollment_token(PUSH_ENROLLMENT_TOKEN):
        return False

    client = request.remote_addr or "unknown"
    now = monotonic()
    with PUSH_TOKEN_FAILURE_LOCK:
        failures = [
            failed_at
            for failed_at in PUSH_TOKEN_FAILURES.get(client, [])
            if now - failed_at < PUSH_TOKEN_FAILURE_WINDOW
        ]
        if len(failures) >= PUSH_TOKEN_MAX_FAILURES:
            PUSH_TOKEN_FAILURES[client] = failures
            return False

        authorized = hmac.compare_digest(
            supplied.encode("utf-8"), PUSH_ENROLLMENT_TOKEN.encode("utf-8")
        )
        if authorized:
            PUSH_TOKEN_FAILURES.pop(client, None)
            return True

        failures.append(now)
        PUSH_TOKEN_FAILURES[client] = failures
        for address, timestamps in list(PUSH_TOKEN_FAILURES.items()):
            fresh_timestamps = [
                failed_at
                for failed_at in timestamps
                if now - failed_at < PUSH_TOKEN_FAILURE_WINDOW
            ]
            if fresh_timestamps:
                PUSH_TOKEN_FAILURES[address] = fresh_timestamps
            else:
                PUSH_TOKEN_FAILURES.pop(address, None)
        return False


def _mikrotik_api_authorized():
    if not MIKROTIK_API_TOKEN:
        return True
    supplied = request.headers.get("X-API-Token", "")
    return hmac.compare_digest(supplied.encode("utf-8"), MIKROTIK_API_TOKEN.encode("utf-8"))


def _push_origin_authorized():
    origin = request.headers.get("Origin", "").rstrip("/")
    if not origin:
        return False
    expected = PUSH_PUBLIC_BASE_URL or request.host_url.rstrip("/")
    try:
        origin_parts = urlsplit(origin)
        expected_parts = urlsplit(expected)
    except ValueError:
        return False
    return (
        origin_parts.scheme in {"http", "https"}
        and origin_parts.scheme == expected_parts.scheme
        and origin_parts.netloc.casefold() == expected_parts.netloc.casefold()
    )


def _read_json_file(file_path, default):
    try:
        with open(file_path, "r", encoding="utf-8") as file:
            return json.load(file)
    except (OSError, json.JSONDecodeError):
        return default


def _read_push_subscriptions():
    value = _read_json_file(PUSH_SUBSCRIPTIONS_FILE, [])
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _write_push_subscriptions(subscriptions):
    PUSH_SUBSCRIPTIONS_FILE.parent.mkdir(parents=True, exist_ok=True)
    temp_path = PUSH_SUBSCRIPTIONS_FILE.with_name(f".{PUSH_SUBSCRIPTIONS_FILE.name}.tmp")
    temp_path.write_text(json.dumps(subscriptions, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temp_path, PUSH_SUBSCRIPTIONS_FILE)


def _owner_token_hash(token):
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _valid_push_subscription(value):
    if not isinstance(value, dict):
        return False
    endpoint = value.get("endpoint")
    keys = value.get("keys")
    if not isinstance(endpoint, str) or len(endpoint) > 4096:
        return False
    try:
        endpoint_parts = urlsplit(endpoint)
        hostname = endpoint_parts.hostname or ""
        try:
            host_is_public_ip = ipaddress.ip_address(hostname).is_global
        except ValueError:
            host_is_public_ip = True
    except ValueError:
        return False
    return bool(
        endpoint_parts.scheme == "https"
        and endpoint_parts.netloc
        and hostname
        and not endpoint_parts.username
        and not endpoint_parts.password
        and not hostname.casefold().endswith((".localhost", ".local", ".internal"))
        and hostname.casefold() != "localhost"
        and host_is_public_ip
        and isinstance(keys, dict)
        and isinstance(keys.get("p256dh"), str)
        and 16 <= len(keys["p256dh"]) <= 512
        and isinstance(keys.get("auth"), str)
        and 8 <= len(keys["auth"]) <= 256
    )


def _register_push_subscription(subscription, device_name, existing_owner_token=""):
    endpoint = subscription["endpoint"]
    with PUSH_LOCK:
        subscriptions = _read_push_subscriptions()
        current = next((item for item in subscriptions if item.get("endpoint") == endpoint), None)
        if current:
            expected_hash = current.get("owner_token_hash", "")
            if not isinstance(expected_hash, str) or not expected_hash or not existing_owner_token or not hmac.compare_digest(
                expected_hash, _owner_token_hash(existing_owner_token)
            ):
                return None, "Perangkat ini sudah terdaftar. Hapus langganan lama dari browser lalu daftar ulang."
            current["subscription"] = subscription
            current["device_name"] = device_name
            current["updated_at"] = datetime.now().isoformat()
            _write_push_subscriptions(subscriptions)
            return existing_owner_token, None

        owner_token = secrets.token_urlsafe(32)
        subscriptions.append({
            "id": str(uuid4()),
            "endpoint": endpoint,
            "subscription": subscription,
            "device_name": device_name,
            "owner_token_hash": _owner_token_hash(owner_token),
            "created_at": datetime.now().isoformat(),
        })
        _write_push_subscriptions(subscriptions)
        return owner_token, None


def _remove_push_subscription(endpoint, owner_token):
    if not isinstance(endpoint, str) or not owner_token:
        return False
    supplied_hash = _owner_token_hash(owner_token)
    with PUSH_LOCK:
        subscriptions = _read_push_subscriptions()
        kept = []
        removed = False
        for item in subscriptions:
            stored_hash = item.get("owner_token_hash", "")
            if (
                item.get("endpoint") == endpoint
                and isinstance(stored_hash, str)
                and hmac.compare_digest(stored_hash, supplied_hash)
            ):
                removed = True
            else:
                kept.append(item)
        if removed:
            _write_push_subscriptions(kept)
        return removed


def _push_subscription_owned(endpoint, owner_token):
    if not endpoint or not owner_token:
        return False
    supplied_hash = _owner_token_hash(owner_token)
    with PUSH_LOCK:
        return any(
            item.get("endpoint") == endpoint
            and isinstance(item.get("owner_token_hash"), str)
            and hmac.compare_digest(item["owner_token_hash"], supplied_hash)
            for item in _read_push_subscriptions()
        )


def _remove_expired_push_endpoint(endpoint):
    with PUSH_LOCK:
        subscriptions = _read_push_subscriptions()
        kept = [item for item in subscriptions if item.get("endpoint") != endpoint]
        if len(kept) != len(subscriptions):
            _write_push_subscriptions(kept)


def _send_push_notification(payload, endpoint=None):
    if not _push_is_configured():
        return
    with PUSH_LOCK:
        subscriptions = list(_read_push_subscriptions())
    for item in subscriptions:
        if endpoint and item.get("endpoint") != endpoint:
            continue
        try:
            webpush(
                subscription_info=item["subscription"],
                data=json.dumps(payload, ensure_ascii=False),
                vapid_private_key=str(_resolve_vapid_private_key()),
                vapid_claims={"sub": VAPID_SUBJECT},
                ttl=3600,
                timeout=10,
            )
        except WebPushException as error:
            response = getattr(error, "response", None)
            if response is not None and response.status_code in {404, 410}:
                _remove_expired_push_endpoint(item.get("endpoint", ""))
            else:
                print(f"[WEB PUSH] Gagal mengirim notifikasi: {error}")
        except Exception as error:
            print(f"[WEB PUSH] Gagal mengirim notifikasi: {error}")


def _queue_push_notification(payload, endpoint=None):
    if _push_is_configured():
        PUSH_EXECUTOR.submit(_send_push_notification, payload, endpoint)


def _check_mikrotik_heartbeats():
    """Notify once when a router stops reporting; re-arm after its next report."""
    now = datetime.now().astimezone()
    with DATA_LOCK:
        router_states = _read_json_file(USER_TEMP_FILE, {})
    if not isinstance(router_states, dict):
        return

    MIKROTIK_HEARTBEAT_ALERT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with MIKROTIK_HEARTBEAT_LOCK:
        alerted_routers = _read_json_file(MIKROTIK_HEARTBEAT_ALERT_FILE, {})
        if not isinstance(alerted_routers, dict):
            alerted_routers = {}

        changed = False
        pending_alerts = []
        for router_name, state in router_states.items():
            if not isinstance(state, dict):
                continue
            last_seen_value = state.get("last_seen")
            if not last_seen_value:
                continue
            try:
                last_seen = datetime.fromisoformat(str(last_seen_value).replace("Z", "+00:00"))
                if last_seen.tzinfo is None:
                    last_seen = last_seen.astimezone()
                if (now - last_seen).total_seconds() > MIKROTIK_HEARTBEAT_TIMEOUT_SECONDS:
                    if router_name not in alerted_routers:
                        pending_alerts.append((str(router_name), str(last_seen_value)))
                elif router_name in alerted_routers:
                    alerted_routers.pop(router_name, None)
                    changed = True
            except (TypeError, ValueError):
                continue

        for router_name, last_seen_value in pending_alerts:
            timeout = MIKROTIK_HEARTBEAT_TIMEOUT_SECONDS
            timeout_text = f"{timeout // 60} menit" if timeout % 60 == 0 else f"{timeout} detik"
            message = (
                f"Gangguan komunikasi pada MikroTik {router_name}: "
                f"data monitoring tidak diterima selama lebih dari {timeout_text}. "
                "Teknisi perlu melakukan pengecekan."
            )
            add_notification(message, "error", ont_name=router_name)
            router_tag = hashlib.sha256(router_name.encode("utf-8")).hexdigest()[:16]
            _queue_push_notification({
                "title": "Gangguan MikroTik",
                "body": message,
                "url": "/notifications",
                "tag": f"mikrotik-heartbeat-{router_tag}",
            })
            alerted_routers[router_name] = {
                "last_seen": last_seen_value,
                "alerted_at": now.isoformat(),
            }
            changed = True

        if changed:
            _atomic_write_json(MIKROTIK_HEARTBEAT_ALERT_FILE, alerted_routers)


def _mikrotik_heartbeat_watchdog():
    while True:
        try:
            _check_mikrotik_heartbeats()
        except Exception as error:
            print(f"[MIKROTIK HEARTBEAT] Gagal memeriksa laporan router: {error}")
        sleep(MIKROTIK_HEARTBEAT_CHECK_INTERVAL_SECONDS)


def _start_mikrotik_heartbeat_watchdog():
    Thread(
        target=_mikrotik_heartbeat_watchdog,
        name="mikrotik-heartbeat-watchdog",
        daemon=True,
    ).start()


def _record_username(record):
    if not isinstance(record, dict):
        return ""
    return str(record.get("user") or record.get("username_pppoe") or record.get("name") or "").strip()


def _normalize_reported_status(value):
    normalized = str(value or "").strip().upper()
    if normalized in {"ONLINE", "ON", "ACTIVE", "UP", "TRUE", "1"}:
        return "ONLINE"
    if normalized in {"OFFLINE", "OFF", "INACTIVE", "DOWN", "FALSE", "0"}:
        return "OFFLINE"
    return None


def _as_records(value):
    if isinstance(value, dict):
        value = value.get("pppoe", [])
    return value if isinstance(value, list) else []


def _record_pppoe_status_snapshot(router, incoming_users, known_users, baseline_users, snapshot_complete=False):
    """Persist reported status and return transitions stable across multiple snapshots."""
    router_key = str(router or "Unknown_Router").strip().casefold()
    with STATUS_LOCK:
        state = _read_json_file(PPPOE_STATUS_STATE_FILE, {})
        if not isinstance(state, dict):
            state = {}
        router_state = state.setdefault(router_key, {"router": str(router), "initialized": False, "users": {}})
        users_state = router_state.get("users")
        if not isinstance(users_state, dict):
            users_state = {}
            router_state["users"] = users_state

        if not router_state.get("initialized"):
            for record in baseline_users:
                username = _record_username(record)
                record_router = str(record.get("router") or "").strip().casefold() if isinstance(record, dict) else ""
                status = _normalize_reported_status(record.get("status")) if isinstance(record, dict) else None
                if username and record_router == router_key and status:
                    users_state[username.casefold()] = {
                        "username": username,
                        "status": status,
                        "candidate": None,
                        "candidate_count": 0,
                    }
            router_state["initialized"] = True

        known_names = set()
        for record in known_users:
            username = _record_username(record)
            record_router = str(record.get("router") or "").strip().casefold() if isinstance(record, dict) else ""
            if username and record_router == router_key:
                known_names.add(username.casefold())
        known_names.update(users_state.keys())

        observed = {}
        for record in incoming_users:
            username = _record_username(record)
            status = _normalize_reported_status(record.get("status")) if isinstance(record, dict) else None
            if username and status:
                observed[username.casefold()] = {"username": username, "status": status}

        if snapshot_complete:
            for username_key in known_names:
                if username_key not in observed:
                    previous = users_state.get(username_key, {})
                    observed[username_key] = {
                        "username": previous.get("username", username_key),
                        "status": "OFFLINE",
                    }

        transitions = []
        for username_key, item in observed.items():
            current = users_state.get(username_key)
            if not isinstance(current, dict) or current.get("status") not in {"ONLINE", "OFFLINE"}:
                users_state[username_key] = {
                    "username": item["username"],
                    "status": item["status"],
                    "candidate": None,
                    "candidate_count": 0,
                }
                continue

            current["username"] = item["username"]
            if current["status"] == item["status"]:
                current["candidate"] = None
                current["candidate_count"] = 0
                continue
            if current.get("candidate") == item["status"]:
                current["candidate_count"] = int(current.get("candidate_count", 0)) + 1
            else:
                current["candidate"] = item["status"]
                current["candidate_count"] = 1
            if current["candidate_count"] >= PPPOE_STATUS_CONFIRMATIONS:
                previous_status = current["status"]
                current["status"] = item["status"]
                current["candidate"] = None
                current["candidate_count"] = 0
                transitions.append({"username": item["username"], "from": previous_status, "to": item["status"]})

        router_state["router"] = str(router)
        PPPOE_STATUS_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        temp_path = PPPOE_STATUS_STATE_FILE.with_name(f".{PPPOE_STATUS_STATE_FILE.name}.tmp")
        temp_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temp_path, PPPOE_STATUS_STATE_FILE)
        return transitions

def load_data():
    try:
        if USER_PPPOES_FILE.exists():
            with open(USER_PPPOES_FILE, 'r') as f:
                return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []

def load_notifications():
    """Load notifications from primary file; fall back to backup on decode error."""
    try:
        with open(NOTIFICATIONS_FILE, 'r') as f:
            notifications = json.load(f)
        if not isinstance(notifications, list):
            raise ValueError("Notifications file does not contain a list")
        for notif in notifications:
            if not isinstance(notif, dict):
                raise ValueError("Invalid notification format")
            if 'id' not in notif or 'message' not in notif or 'timestamp' not in notif:
                raise ValueError("Notification missing required fields")
        return notifications
    except FileNotFoundError:
        print("Notifications file not found, trying to recover from backup...")
        return _recover_notifications_from_backup()
    except (json.JSONDecodeError, ValueError) as e:
        print(f"Notifications file corrupted: {e}, trying to recover from backup...")
        return _recover_notifications_from_backup()

def _recover_notifications_from_backup():
    """Mencoba memulihkan notifikasi dari backup terbaru"""
    try:
        import glob
        backup_pattern = f'{BACKUP_DIR}/notifications-*.json'
        backup_files = glob.glob(backup_pattern)
        if not backup_files:
            print("No notification backups found, starting fresh")
            return []
        backup_files.sort(key=os.path.getmtime, reverse=True)
        latest_backup = backup_files[0]
        print(f"Recovering notifications from: {latest_backup}")
        with open(latest_backup, 'r') as f:
            notifications = json.load(f)
        save_notifications(notifications)
        print(f"Successfully recovered {len(notifications)} notifications")
        return notifications
    except Exception as e:
        print(f"Failed to recover notifications from backup: {e}")
        return []

def _atomic_write_json(file_path, data):
    dir_name = os.path.dirname(file_path) or '.'
    temp_path = os.path.join(dir_name, f".tmp-{os.path.basename(file_path)}")
    with open(temp_path, 'w') as tf:
        json.dump(data, tf, indent=2)
        tf.flush()
        try:
            os.fsync(tf.fileno())
        except Exception:
            pass
    try:
        with open(f"{file_path}.bak", 'w') as bf:
            json.dump(data, bf, indent=2)
    except Exception:
        pass
    os.replace(temp_path, file_path)

def save_notifications(notifications):
    _atomic_write_json(NOTIFICATIONS_FILE, notifications)

def add_notification(message, notification_type="info", ont_id=None, ont_name=None, timestamp=None):
    notifications = load_notifications()
    next_id = (max((n.get('id', 0) for n in notifications), default=0) + 1)
    new_notification = {
        "id": next_id, "message": message, "type": notification_type,
        "timestamp": (timestamp or datetime.now().isoformat()),
        "ont_id": ont_id, "ont_name": ont_name, "read": False
    }
    notifications.append(new_notification)
    _backup_notifications(notifications)
    save_notifications(notifications)
    return new_notification

def _backup_notifications(notifications):
    try:
        timestamp = datetime.now().strftime('%Y%m%d-%H%M%S')
        backup_path = f'{BACKUP_DIR}/notifications-{timestamp}.json'
        os.makedirs(BACKUP_DIR, exist_ok=True)
        with open(backup_path, 'w') as f:
            json.dump(notifications, f, indent=2)
        _cleanup_old_backups('notifications-*.json', 10)
    except Exception as e:
        print(f"Warning: Failed to backup notifications: {e}")

def _cleanup_old_backups(pattern, keep_count):
    try:
        import glob
        backup_files = glob.glob(f'{BACKUP_DIR}/{pattern}')
        backup_files.sort(key=os.path.getmtime, reverse=True)
        for old_file in backup_files[keep_count:]:
            try:
                os.remove(old_file)
            except:
                pass
    except Exception as e:
        print(f"Warning: Failed to cleanup old backups: {e}")

def save_and_backup(onts):
    with open(USER_PPPOES_FILE, 'w') as f:
        json.dump(onts, f, indent=2)
    with open(PPPOES_TEMP_FILE, 'w') as f:
        json.dump(onts, f, indent=2)

@app.route('/')
def map_view():
    return render_template('map.html')

@app.route('/dashboard')
def dashboard():
    return render_template('dashboard.html')

@app.route('/analytics')
def analytics_page():
    """Menampilkan halaman analitik baru."""
    return render_template('analytics.html')

@app.route('/healthz')
def healthz():
    """Endpoint sederhana untuk cek kesehatan service."""
    return jsonify({"status": "ok"})

@app.route('/admin')
def admin():
    pppoes = load_data()
    return render_template('list.html', pppoes=pppoes)

@app.route('/notifications')
def notifications():
    notifications_list = load_notifications()
    notifications_list.sort(key=lambda x: x['timestamp'], reverse=True)
    return render_template('notifications.html', notifications=notifications_list)


@app.route('/service-worker.js')
def service_worker():
    response = send_from_directory(app.static_folder, 'service-worker.js', mimetype='application/javascript')
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response.headers['Service-Worker-Allowed'] = '/'
    return response


@app.route('/api/push/config')
def push_config():
    configured = _push_is_configured()
    return jsonify({
        "configured": configured,
        "public_key": VAPID_PUBLIC_KEY if configured else "",
    })


def _push_api_error(message, status):
    return jsonify({"success": False, "message": message}), status


def _authorize_push_request():
    if not _push_origin_authorized():
        return _push_api_error("Asal permintaan tidak cocok dengan alamat aplikasi.", 403)
    if not _push_token_authorized():
        return _push_api_error("Token pendaftaran notifikasi tidak valid.", 401)
    if not _push_is_configured():
        return _push_api_error("Konfigurasi VAPID belum lengkap di server.", 503)
    return None


@app.route('/api/push/subscribe', methods=['POST'])
def push_subscribe():
    error = _authorize_push_request()
    if error:
        return error
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return _push_api_error("Format permintaan tidak valid.", 400)
    subscription = payload.get("subscription")
    if not _valid_push_subscription(subscription):
        return _push_api_error("Data subscription browser tidak valid.", 400)
    device_name = str(payload.get("device_name") or "Perangkat teknisi").strip()[:80]
    owner_token, message = _register_push_subscription(
        subscription,
        device_name or "Perangkat teknisi",
        str(payload.get("owner_token") or ""),
    )
    if message:
        return _push_api_error(message, 409)
    return jsonify({"success": True, "owner_token": owner_token})


@app.route('/api/push/unsubscribe', methods=['POST'])
def push_unsubscribe():
    error = _authorize_push_request()
    if error:
        return error
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return _push_api_error("Format permintaan tidak valid.", 400)
    subscription = payload.get("subscription") or {}
    endpoint = subscription.get("endpoint") if isinstance(subscription, dict) else ""
    owner_token = str(payload.get("owner_token") or "")
    if not _remove_push_subscription(endpoint, owner_token):
        return _push_api_error("Subscription tidak ditemukan atau token perangkat tidak cocok.", 404)
    return jsonify({"success": True})


@app.route('/api/push/test', methods=['POST'])
def push_test():
    error = _authorize_push_request()
    if error:
        return error
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return _push_api_error("Format permintaan tidak valid.", 400)
    subscription = payload.get("subscription") or {}
    endpoint = subscription.get("endpoint") if isinstance(subscription, dict) else ""
    owner_token = str(payload.get("owner_token") or "")
    if not _push_subscription_owned(endpoint, owner_token):
        return _push_api_error("Perangkat ini belum terdaftar atau token pemilik tidak cocok.", 404)
    _queue_push_notification({
        "title": "PPPoE Monitoring",
        "body": "Notifikasi perangkat berhasil diaktifkan.",
        "url": "/notifications",
        "tag": "pppoe-push-test",
    }, endpoint=endpoint)
    return jsonify({"success": True, "message": "Notifikasi uji dikirim."}), 202

@app.route('/api/notifications', methods=['GET', 'POST'])
def api_notifications():
    if request.method == 'POST':
        data = request.get_json()
        add_notification(data.get('message', ''), data.get('type', 'info'), None, None, timestamp=data.get('timestamp'))
        return jsonify({"success": True})
    notifications_list = load_notifications()
    notifications_list.sort(key=lambda x: x['timestamp'], reverse=True)
    return jsonify(notifications_list)

@app.route('/api/notifications/mark-read/<int:notification_id>', methods=['POST'])
def mark_notification_read(notification_id):
    notifications_list = load_notifications()
    for notification in notifications_list:
        if notification['id'] == notification_id:
            notification['read'] = True
            break
    save_notifications(notifications_list)
    return jsonify({"success": True})

@app.route('/api/notifications/clear-all', methods=['POST'])
def clear_all_notifications():
    try:
        current_notifications = load_notifications()
        if current_notifications:
            _backup_notifications(current_notifications)
        save_notifications([])
        return jsonify({"success": True, "message": "Semua notifikasi berhasil dihapus."})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

@app.route('/api/notifications/restore-backup', methods=['POST'])
def restore_notifications_from_backup():
    try:
        current_notifications = load_notifications()
        if current_notifications:
            _backup_notifications(current_notifications)
        restored_notifications = _recover_notifications_from_backup()
        if restored_notifications:
            return jsonify({"success": True, "message": f"Berhasil memulihkan {len(restored_notifications)} notifikasi dari backup", "count": len(restored_notifications)})
        else:
            return jsonify({"success": False, "message": "Tidak ada backup yang tersedia untuk dipulihkan"})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

@app.route('/edit/<id>', methods=['GET', 'POST'])    
def edit_pppoe(id):
    # 1. BACA DATABASE MASTER SECARA AMAN
    data_master = load_data()
    
    if isinstance(data_master, dict):
        pppoe_list = data_master.get("pppoe", [])
    elif isinstance(data_master, list):
        pppoe_list = data_master
    else:
        pppoe_list = []
        
    # Mencari user berdasarkan ID int
    pppoe_user = next((p for p in pppoe_list if str(p.get('user')) == id or str(p.get('name')) == id or str(p.get('id')) == id), None)
    
    if not pppoe_user:
        return "User PPPoE tidak ditemukan", 404
        
    if request.method == 'POST':
        # Tangkap data baru dari form edit (Sesuai dengan tag name="" di HTML terbaru)
        target_router = request.form.get('router_name', pppoe_user.get('router', ''))
        username_pppoe = request.form.get('username_pppoe') # Ini Primary Key (Readonly dari HTML)
        
        new_id_pelanggan = request.form.get('id_pelanggan', '')
        new_nama = request.form.get('nama', '')
        new_lokasi = request.form.get('lokasi', '')
        new_ip = request.form.get('ip', '')
        new_latitude = request.form.get('latitude', '')
        new_longitude = request.form.get('longitude', '')
        new_password = request.form.get('password', '')
        new_profile = request.form.get('profile', '')

        # ---------------------------------------------------------
        # A. LOGIKA BARU: MASUKKAN INSTRUKSI EDIT KE ANTREAN (QUEUE)
        # ---------------------------------------------------------
        queue_data = []
        if os.path.exists(QUEUE_FILE):
            try:
                with open(QUEUE_FILE, 'r') as qf:
                    queue_data = json.load(qf)
                    if not isinstance(queue_data, list):
                        queue_data = []
            except (json.JSONDecodeError, FileNotFoundError):
                queue_data = []

        # Susun instruksi edit
        queue_item = {
            "id": new_id_pelanggan,
            "icon": 119,
            "action": "edit",
            "lokasi": new_lokasi,
            "latitude": new_latitude,
            "longitude": new_longitude,
            "mac": pppoe_user.get('mac', ''),
            "router": target_router,
            "username_pppoe": username_pppoe, # MikroTik akan mencari akun berdasarkan nama ini
            "password": new_password,
            "profile": new_profile,
            "ip": new_ip,
            "timestamp": datetime.now().isoformat()
        }

        queue_data = [q for q in queue_data if q.get("username_pppoe") != username_pppoe]
        queue_data.append(queue_item)

        try:
            with open(QUEUE_FILE, 'w') as qf:
                json.dump(queue_data, qf, indent=4)
            print(f"--- [QUEUE EDIT SUCCESS] Perintah 'edit' {username_pppoe} disimpan ke antrean ---")
        except Exception as e:
            print(f"[QUEUE ERROR] Gagal menulis file antrean: {e}")

        # ---------------------------------------------------------
        # B. UPDATE DATA KE DATABASE LOKAL WEB
        # ---------------------------------------------------------
        pppoe_user['id'] = new_id_pelanggan
        pppoe_user['nama_asli'] = new_nama
        pppoe_user['lokasi'] = new_lokasi
        pppoe_user['ip'] = new_ip
        pppoe_user['latitude'] = new_latitude
        pppoe_user['longitude'] = new_longitude
        pppoe_user['password'] = new_password
        pppoe_user['profile'] = new_profile
            
        # Bungkus kembali ke bentuk dict sebelum disimpan
        save_and_backup(pppoe_list)

        # ---------------------------------------------------------
        # C. LOGIKA BARU: KUNCI DATA MANUAl/KOORDINAT ABADI
        # ---------------------------------------------------------
        manual_entry = {
            "router": target_router,
            "icon": 119,
            "id": new_id_pelanggan,
            "user": username_pppoe,              
            "lokasi": new_lokasi,              
            "latitude": float(new_latitude) if new_latitude and new_latitude != "-" else "-",
            "longitude": float(new_longitude) if new_longitude and new_longitude != "-" else "-",
            "mac": pppoe_user.get('mac', '-'),
            "ip": new_ip,
            "uptime": pppoe_user.get('uptime', '-'),
            "status": pppoe_user.get('status', 'OFFLINE')
        }

        try:
            if os.path.exists(MANUAL_FILE):
                with open(MANUAL_FILE, 'r') as mf:
                    try:
                        manual_data = json.load(mf)
                        if not isinstance(manual_data, list): 
                            manual_data = []
                    except:
                        manual_data = []
            else:
                manual_data = []

            # Hapus data lama agar tidak menumpuk duplikat
            manual_data = [m for m in manual_data if m.get("user") != username_pppoe]
            manual_data.append(manual_entry)

            # Simpan secara permanen ke dalam database server lokal
            with open(MANUAL_FILE, 'w') as mf:
                json.dump(manual_data, mf, indent=4)
            print(f"--- [MANUAL SECURE SUCCESS] Koordinat & ID {username_pppoe} berhasil dikunci abadi ---")
        except Exception as e:
            print(f"[MANUAL ERROR] Gagal mengunci koordinat manual: {e}")
        
        add_notification(
            f"User PPPoE diperbarui mohon tunggu 5 menit untuk perubahan di mikrotik: {username_pppoe}", 
            "info", 
            pppoe_user.get('id', 'N/A'), 
            username_pppoe
        )   
        
        flash(f"User {username_pppoe} berhasil diperbarui! Perubahan akan disinkronkan ke MikroTik dalam waktu 5 menit!", "success")
        return redirect(url_for('admin')) 
        
    return render_template('form.html', pppoe=pppoe_user)
        
@app.route('/api/clear-queue', methods=['GET'])
def queue_done():
    # 1. Ambil ID antrean yang dikirim oleh MikroTik via parameter URL
    queue_id = request.args.get('id')
    
    if not queue_id:
        return jsonify({"status": "error", "message": "ID tidak ditemukan"}), 400
    
    try:
        # 2. Baca file antrean yang ada
        if not os.path.exists(QUEUE_FILE):
            return jsonify({"status": "error", "message": "File antrean tidak ada"}), 404
            
        with open(QUEUE_FILE, 'r') as f:
            queue_data = json.load(f)
        
        updated_queue = [q for q in queue_data if str(q.get('id')) != str(queue_id)]
        
        with open(QUEUE_FILE, 'w') as f:
            json.dump(updated_queue, f, indent=4)
            
        print(f"[SUCCESS] Antrean #{queue_id} berhasil dihapus dari daftar.")
        return jsonify({"status": "success", "message": "Antrean dihapus"}), 200
        
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/get-queue', methods=['GET'])
def get_queue():
    try:
        if not os.path.exists(QUEUE_FILE):
            return "", 200, {'Content-Type': 'text/plain'}

        with open(QUEUE_FILE, 'r') as f:
            try:
                queue_data = json.load(f)
                if not isinstance(queue_data, list):
                    queue_data = []
            except json.JSONDecodeError:
                queue_data = []

        rsc_commands = []
        
        for item in queue_data:
            username = item.get('username_pppoe')
            password = item.get('password', '')
            profile = item.get('profile', '')
            remote_ip = item.get('ip', '-')
            id_antrean = item.get('id', '-')
            router_target = item.get('router', '')

            if not username:
                continue

            if remote_ip == "-":
                cmd = f'/ppp secret set [find name="{username}"] password="{password}" profile="{profile}";'
            else:
                cmd = f'/ppp secret set [find name="{username}"] password="{password}" profile="{profile}" remote-address="{remote_ip}";'
            
            rsc_commands.append(cmd)
            rsc_commands.append(':delay 1s; /system script run update-user-pppoe;')

            if id_antrean != "-":
                clear_url = f"http://202.169.232.239:8078/api/clear-queue?id={id_antrean}"
                rsc_commands.append(f'/tool fetch mode=http url="{clear_url}" keep-result=no')

        final_rsc = "\n".join(rsc_commands)
        return final_rsc, 200, {'Content-Type': 'text/plain'}

    except Exception as e:
        print(f"[GET QUEUE ERROR] Gagal menyusun script rsc: {e}")
        return f"# Error: {str(e)}", 500, {'Content-Type': 'text/plain'}

def simpan_ke_file(data_baru, target_file):
    """Fungsi dinamis untuk membaca file lama, menambah data baru, lalu menyimpannya kembali"""
    folder_target = os.path.dirname(target_file)
    if folder_target and not os.path.exists(folder_target):
        os.makedirs(folder_target, exist_ok=True)
        
    riwayat = []
    
    if os.path.exists(target_file):
        try:
            with open(target_file, "r") as file:
                riwayat = json.load(file)
                if not isinstance(riwayat, list):
                    riwayat = []
        except Exception:
            riwayat = []
            
    riwayat.append(data_baru)
    
    if len(riwayat) > 500:
        riwayat.pop(0)
        
    with open(target_file, "w") as file:
        json.dump(riwayat, file, indent=4)
        
    return riwayat

def baca_dari_file(target_file):
    """PERBAIKAN: Fungsi dinamis untuk membaca data dari file JSON apa saja"""
    if os.path.exists(target_file):
        try:
            with open(target_file, "r") as file:
                return json.load(file)
        except Exception:
            return []
    return []


def init_history_buffer():
    """Fungsi pembantu untuk memuat data dari file ke array HANYA 1x saat server nyala."""
    global global_history_buffer
    if global_history_buffer is None:
        try:
            with open(HISTORY_FILE, 'r') as file:
                global_history_buffer = json.load(file)
                if not isinstance(global_history_buffer, list):
                    global_history_buffer = []
        except (FileNotFoundError, json.JSONDecodeError):
            global_history_buffer = []

@app.route('/api/update-pppoe', methods=['POST'])
def update_pppoe():
    global global_history_buffer
    if not _mikrotik_api_authorized():
        return jsonify({"status": "error", "message": "Token API tidak valid."}), 401
    push_payload = None
    DATA_LOCK.acquire()
    try:
        data_terurai = None
        try:
            if request.is_json:
                data_terurai = request.get_json(silent=True)
            if not data_terurai:
                raw_body = request.get_data(as_text=True).strip()
                if raw_body.startswith('{'):
                    data_terurai = json.loads(raw_body)
                elif request.form and 'data_json' in request.form:
                    data_terurai = json.loads(request.form.get('data_json'))
        except Exception as e:
            print(f"[ERROR] Gagal membaca stream HTTP: {e}")

        if not isinstance(data_terurai, dict):
            return jsonify({"status": "failed", "message": "Format JSON rusak/kosong."}), 400
            
        raw_user_list = data_terurai.get("pppoe", [])
        if not isinstance(raw_user_list, list):
            return jsonify({"status": "failed", "message": "Field pppoe harus berupa array."}), 400
        baseline_status_rows = _as_records(load_data())
        waktu_sekarang = datetime.now().isoformat()
        
        BLACKLIST_PREFIX = ('cleon', 'vpn', 'test', 'ppp', 'event', 'ruko', 'tower')
        filtered_user = []
        
        for user in raw_user_list:
            if not isinstance(user, dict):
                continue
            username = str(user.get('user') or '').strip().lower()
            if not username.startswith(BLACKLIST_PREFIX):
                filtered_user.append(user)
        # Ekstraksi Nama Router
        nama_router = "Unknown_Router"
        if data_terurai.get("router"):
            nama_router = str(data_terurai.get("router")).strip() or "Unknown_Router"
        elif filtered_user:
            nama_router = str(filtered_user[0].get("router") or "Unknown_Router").strip()
            
        total_on = len([u for u in filtered_user if _normalize_reported_status(u.get('status')) == "ONLINE"])
        total_global = len(filtered_user)

        # =================================================================
        # PERSIAPAN: Map Ulang List User
        # =================================================================
        mapped_user_list = []
        for user in filtered_user:
            mapped_user_list.append({
                "router": nama_router,
                "user": user.get("user", "-"),
                "ip": user.get("ip", "-"),
                "mac": user.get("mac", "-"),
                "uptime": user.get("uptime", "-"),
                "status": _normalize_reported_status(user.get("status")) or "OFFLINE"
            })

        # =================================================================
        # 2. SHARED MEMORY STATE
        # =================================================================
        try:
            with open(USER_TEMP_FILE, 'r') as f:
                state_terkini = json.load(f)
        except:
            state_terkini = {}

        state_terkini[nama_router] = {
            "on": total_on,
            "total": total_global,
            "last_seen": waktu_sekarang
        }
        with open(USER_TEMP_FILE, 'w') as f:
            json.dump(state_terkini, f, indent=4)

        sum_on = sum(r["on"] for r in state_terkini.values())
        sum_total = sum(r["total"] for r in state_terkini.values())
        sum_off = max(0, sum_total - sum_on)

        # =================================================================
        # 3. LAYER HISTORY_FILE
        # =================================================================
        init_history_buffer()
        melebur = False
        if global_history_buffer:
            last_entry = global_history_buffer[-1]
            try:
                last_ts = datetime.fromisoformat(last_entry.get("timestamp"))
                now_ts = datetime.fromisoformat(waktu_sekarang)
                if abs((now_ts - last_ts).total_seconds()) < 300:
                    melebur = True
                    last_entry.update({"pppoe_users": sum_on, "pppoe_offlines": sum_off, "total_pppoe": sum_total, "timestamp": waktu_sekarang})
            except: pass

        if not melebur:
            global_history_buffer.append({"pppoe_users": sum_on, "pppoe_offlines": sum_off, "total_pppoe": sum_total, "timestamp": waktu_sekarang})

        with open(HISTORY_FILE, 'w') as file:
            json.dump(global_history_buffer, file, indent=4)

        # =================================================================
        # 4. LAYER USER_LOG_FILE
        # =================================================================
        try:
            with open(USER_LOG_FILE, 'r') as file:
                user_log_data = json.load(file)
                if not isinstance(user_log_data, list): user_log_data = []
        except: user_log_data = []

        user_log_data.append({"timestamp": waktu_sekarang, "router": nama_router, "pppoe": mapped_user_list}) 
        with open(USER_LOG_FILE, "w") as file:
            json.dump(user_log_data, file, indent=4)

        # =================================================================
        # 5. LAYER USER_PPPOES_FILE (Penyimpanan Master Semua User)
        # =================================================================
        try:
            if os.path.exists(PPPOES_TEMP_FILE):
                with open(PPPOES_TEMP_FILE, 'r') as file:
                    existing_data = json.load(file)
                    master_list = existing_data if isinstance(existing_data, list) else []
            else:
                master_list = []
        except Exception as e:
            print(f"[WARN] Gagal membaca data lama PPPOES_TEMP_FILE: {e}")
            master_list = []

        master_list = [u for u in master_list if u.get("router") != nama_router]
        master_list.extend(mapped_user_list)
            
        with open(PPPOES_TEMP_FILE, "w") as file:
            json.dump(master_list, file, indent=4)

        try:
            merge_pppoe_automatically()
            print(f"[AUTO MERGE BERHASIL] Berhasil menjalankan merge otomatis!")
        except Exception as e:
            print(f"[AUTO MERGE ERROR] Gagal menjalankan merge otomatis: {e}")

        manual_rows = _read_json_file(MANUAL_FILE, [])
        if not isinstance(manual_rows, list):
            manual_rows = []
        known_status_rows = _as_records(load_data()) + manual_rows
        snapshot_complete = data_terurai.get("snapshot_complete") is True
        if not snapshot_complete:
            snapshot_complete = data_terurai.get("complete_snapshot") is True
        transitions = _record_pppoe_status_snapshot(
            nama_router,
            filtered_user,
            known_status_rows,
            baseline_status_rows,
            snapshot_complete=snapshot_complete,
        )
        if transitions:
            offline_count = sum(1 for item in transitions if item["to"] == "OFFLINE")
            online_count = sum(1 for item in transitions if item["to"] == "ONLINE")
            summary_parts = []
            if offline_count:
                summary_parts.append(f"{offline_count} akun offline")
            if online_count:
                summary_parts.append(f"{online_count} akun online")
            message = f"Perubahan status PPPoE di {nama_router}: " + ", ".join(summary_parts) + "."
            add_notification(message, "warning" if offline_count else "success", ont_name=nama_router)
            push_payload = {
                "title": "Gangguan PPPoE" if offline_count else "Koneksi PPPoE pulih",
                "body": message,
                "url": "/admin",
                "tag": f"pppoe-status-{nama_router}-{int(datetime.now().timestamp() // 60)}",
            }
            
        print(f"[SUCCESS] {nama_router} Masuk. Total Akumulasi Semua Router: {sum_on} User")
        return jsonify({"status": "success"}), 200
        
    except Exception as e:
        print(f"[ERROR] API Crash: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        DATA_LOCK.release()
        if push_payload:
            _queue_push_notification(push_payload)

@app.route('/api/history', methods=['GET'])
def get_history():
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r") as file:
                return jsonify(json.load(file)), 200
        except Exception:
            return jsonify([]), 500
    return jsonify([]), 200

@app.route('/api/pppoes', methods=['GET'])
def get_user_actives():
    if os.path.exists(USER_PPPOES_FILE):
        try:
            with open(USER_PPPOES_FILE, "r") as file:
                return jsonify(json.load(file)), 200
        except Exception:
            return jsonify([]), 500
    
    return jsonify([]), 200
    
@app.route('/api/analytics-data', methods=['GET'])
def get_analytics_data():
    """Membaca history.json untuk grafik, dan user_log.json untuk tabel raw log."""
    month_filter = request.args.get('month', '').strip()
    
    try:
        with open(HISTORY_FILE, 'r') as f:
            history_data = json.load(f)
            if not isinstance(history_data, list):
                history_data = []
    except (FileNotFoundError, json.JSONDecodeError):
        history_data = []

    try:
        with open(USER_LOG_FILE, 'r') as f:
            user_log_data = json.load(f)
            if not isinstance(user_log_data, list):
                user_log_data = []
    except (FileNotFoundError, json.JSONDecodeError):
        user_log_data = []

    daily_data = {}
    monthly_data = {}
    pppoe_counts = []

    # 1. Ekstraksi Data dari Log Historis (Amankan parsing Timestamp)
    for entry in history_data:
        if not isinstance(entry, dict):
            continue
            
        try:
            ts_string = entry.get('timestamp', '').strip()
            if not ts_string:
                continue
                
            if "T" in ts_string:
                ts_string = ts_string.replace("T", " ")
            
            if "." in ts_string:
                dt = datetime.strptime(ts_string.split(".")[0], '%Y-%m-%d %H:%M:%S')
            else:
                dt = datetime.strptime(ts_string, '%Y-%m-%d %H:%M:%S')
                
        except Exception as e:
            print(f"[DEBUG LOG] Gagal parsing waktu pada baris data: {e}")
            continue

        day = dt.strftime('%Y-%m-%d')
        month = dt.strftime('%Y-%m')

        p_count = int(entry.get('pppoe_users', 0))
        pppoe_counts.append(p_count)

        daily_data.setdefault(day, []).append(p_count)
        monthly_data.setdefault(month, []).append(p_count)

    # 2. Pembuatan Ringkasan Harian
    daily_summary_all = []
    for day, counts_list in daily_data.items():
        if counts_list:
            daily_summary_all.append({
                "date": day,
                "pppoe_peak": max(counts_list),
                "pppoe_avg": round(sum(counts_list) / len(counts_list)),
                "peak": max(counts_list),
                "trough": min(counts_list),
                "average": round(sum(counts_list) / len(counts_list))
            })
    daily_summary_all.sort(key=lambda x: x['date'])

    # 3. Pembuatan Ringkasan Bulanan
    monthly_summary = []
    for month, counts_list in monthly_data.items():
        if counts_list:
            monthly_summary.append({
                "month": month,
                "pppoe_peak": max(counts_list),
                "pppoe_avg": round(sum(counts_list) / len(counts_list)),
                "peak": max(counts_list),
                "trough": min(counts_list),
                "average": round(sum(counts_list) / len(counts_list))
            })

    current_year = datetime.now().year
    existing_months = {m['month'] for m in monthly_summary}
    for m in range(1, 13):
        key = f"{current_year}-{m:02d}"
        if key not in existing_months:
            monthly_summary.append({
                "month": key, "pppoe_peak": 0, "pppoe_avg": 0,
                "peak": 0, "trough": 0, "average": 0
            })
    monthly_summary.sort(key=lambda x: x['month'])

    # 4. Filter Berdasarkan Kalender Bulanan
    normalized_filter = ""
    no_data_for_month = False
    if month_filter:
        if len(month_filter) == 2 and month_filter.isdigit():
            normalized_filter = f"{current_year}-{month_filter}"
        elif len(month_filter) == 7 and '-' in month_filter:
            normalized_filter = month_filter
        else:
            return jsonify({"error": "Format filter bulan tidak valid."}), 400
    
    daily_summary = daily_summary_all
    if normalized_filter:
        daily_summary = [rec for rec in daily_summary_all if rec['date'].startswith(normalized_filter)]
        try:
            y, m = normalized_filter.split('-')
            y, m = int(y), int(m)
            # Pastikan "import calendar" ada di baris paling atas app.py
            _, days_in_month = calendar.monthrange(y, m)
            existing_map = {rec['date']: rec for rec in daily_summary}
            completed = []
            for d in range(1, days_in_month + 1):
                date_str = f"{y}-{m:02d}-{d:02d}"
                if date_str in existing_map:
                    completed.append(existing_map[date_str])
                else:
                    completed.append({
                        "date": date_str, "pppoe_peak": 0, "pppoe_avg": 0,
                        "peak": 0, "trough": 0, "average": 0
                    })
            completed.sort(key=lambda x: x['date'])
            daily_summary = completed
            no_data_for_month = False
        except Exception:
            no_data_for_month = len(daily_summary) == 0

    # 5. Petakan struktur data realtime dari baris terakhir log
    realtime = {'timestamp': None, 'online': 0, 'offline': 0, 'total': 0}
    if history_data:
        last = history_data[-1]
        realtime = {
            'timestamp': last.get('timestamp'),
            'online': int(last.get('pppoe_users', 0)),
            'offline': int(last.get('pppoe_offlines', 0)),
            'total': int(last.get('total_pppoe', 0))
        }

    # Ambil 100 baris terakhir saja dari arsip agar browser tidak lag
    active_users_list = user_log_data[-100:] if user_log_data else []

    analytics_payload = {
        "summary": {
            "peak_users": max(pppoe_counts) if pppoe_counts else 0,
            "trough_users": min(pppoe_counts) if pppoe_counts else 0,
            "average_users": round(sum(pppoe_counts) / len(pppoe_counts), 2) if pppoe_counts else 0,
            "unique_devices": realtime['online']  
        },
        "daily_summary": daily_summary,
        "monthly_summary": monthly_summary,
        "realtime": realtime,
        "raw_logs": active_users_list,
        "month_filter": normalized_filter,
        "no_data_for_month": no_data_for_month
    }

    return jsonify(analytics_payload)

if __name__ == '__main__':
    _start_mikrotik_heartbeat_watchdog()
    app.run(host="0.0.0.0", debug=True, use_reloader=False)

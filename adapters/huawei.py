"""Huawei LTE router adapter using huawei-lte-api."""
import time
from huawei_lte_api.Client import Client
from huawei_lte_api.Connection import Connection
from .base import RouterAdapter


# Workaround for a huawei-lte-api bug: "int has no attribute value"
class _BoxTypeInbox:
    value = 1


class _BoxTypeSent:
    value = 2


class HuaweiAdapter(RouterAdapter):
    """Adapter for Huawei LTE routers (B525, B535, B818…)."""

    brand = "huawei"
    supports_inbox = True
    supports_outbox = True

    NETWORK_MAP = {
        '0': 'GPRS', '1': 'GPRS', '2': 'EDGE', '3': 'WCDMA',
        '4': 'HSDPA', '5': 'HSUPA', '6': 'HSPA', '7': 'HSPA+',
        '8': 'TDSCDMA', '9': 'HSPA+', '10': 'EVDO', '19': '4G LTE',
        '41': '3G+', '101': '4G+',
    }

    def __init__(self, ip: str, user: str, password: str):
        self._url = f'http://{user}:{password}@{ip}/'

    # --- Private helpers ---

    def _parse_sms_list(self, raw) -> list:
        messages = []
        if 'Messages' in raw and 'Message' in raw['Messages']:
            items = raw['Messages']['Message']
            if isinstance(items, dict):
                items = [items]
            for msg in items:
                messages.append({
                    'Index': msg.get('Index'),
                    'Phone': msg.get('Phone'),
                    'Content': msg.get('Content'),
                    'Date': msg.get('Date'),
                })
        return messages

    # --- RouterAdapter interface ---

    def send_sms(self, numbers: list, message: str) -> None:
        with Connection(self._url) as conn:
            Client(conn).sms.send_sms(numbers, message)

    def get_inbox(self, page: int = 1, per_page: int = 20) -> dict:
        with Connection(self._url) as conn:
            raw = Client(conn).sms.get_sms_list(
                page=page, box_type=_BoxTypeInbox, read_count=per_page
            )
        messages = self._parse_sms_list(raw)
        return {'messages': messages, 'page': page, 'has_more': len(messages) == per_page}

    def get_outbox(self, page: int = 1, per_page: int = 50) -> dict:
        with Connection(self._url) as conn:
            raw = Client(conn).sms.get_sms_list(
                page=page, box_type=_BoxTypeSent, read_count=per_page
            )
        messages = self._parse_sms_list(raw)
        return {'messages': messages, 'page': page, 'has_more': len(messages) == per_page}

    def delete_sms(self, index) -> None:
        with Connection(self._url) as conn:
            Client(conn).sms.delete_sms([int(index)])

    def delete_sms_batch(self, indices: list) -> int:
        """Efficient batch delete using Huawei's native multi-index call."""
        with Connection(self._url) as conn:
            Client(conn).sms.delete_sms([int(i) for i in indices])
        return len(indices)

    def delete_outbox_all(self, on_progress=None) -> int:
        """Efficient outbox purge reusing a single connection."""
        deleted = 0
        with Connection(self._url) as conn:
            client = Client(conn)
            while True:
                raw = client.sms.get_sms_list(
                    page=1, box_type=_BoxTypeSent, read_count=50
                )
                indices = [m['Index'] for m in self._parse_sms_list(raw) if m.get('Index')]
                if not indices:
                    break
                client.sms.delete_sms(indices)
                deleted += len(indices)
                if on_progress:
                    on_progress(deleted)
                if len(indices) < 50:
                    break
                time.sleep(0.5)
        return deleted

    def get_status(self) -> dict:
        with Connection(self._url) as conn:
            client = Client(conn)
            monitoring = client.monitoring.status()
            signal_bars = int(monitoring.get('SignalIcon', 0))
            network_type = monitoring.get('CurrentNetworkType', '')
            try:
                plmn = client.net.current_plmn()
                operator = plmn.get('FullName') or plmn.get('ShortName') or '—'
            except Exception:
                operator = '—'
        return {
            'status': 'ok',
            'signal_bars': signal_bars,
            'network': self.NETWORK_MAP.get(str(network_type), f'Type {network_type}'),
            'operator': operator,
        }

    def check_health(self) -> dict:
        with Connection(self._url) as conn:
            Client(conn).device.information()
        return {'status': 'ok', 'router': 'reachable'}

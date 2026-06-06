"""TP-Link MR series adapter using tplinkrouterc6u.

Supported models (non-exhaustive): MR6400, MR600, MR500, MR200, Archer MR550,
MR400, MR450, MR100 — any TP-Link 4G/LTE router with the MR firmware web UI.

Two firmware variants are handled automatically:
  - TPLinkMRClient    : standard RSA+AES firmware (most devices)
  - TPLinkMRClientGCM : AES-GCM firmware (newer devices / recent firmware updates)

The adapter tries the standard variant first; if it raises a *crypto/auth*
error (not a network error) it retries with the GCM variant. Network errors
(timeout, unreachable host) are surfaced immediately without retrying — the
firmware variant has no bearing on reachability.

The chosen variant is cached for the lifetime of the adapter instance.

Username is always 'admin' (TP-Link MR web UI has no configurable username).
"""
import logging
import socket
from datetime import datetime
from requests.exceptions import ConnectionError as ReqConnectionError, Timeout as ReqTimeout
from .base import RouterAdapter

log = logging.getLogger(__name__)


# Errors that mean "couldn't reach the router" — no point retrying with a
# different firmware variant.
_NETWORK_EXCS = (ReqConnectionError, ReqTimeout, socket.timeout, socket.gaierror, OSError)


class TplinkAdapter(RouterAdapter):
    brand = "tplink"
    supports_inbox = True
    supports_outbox = False   # MR firmware doesn't expose a sent-SMS API

    def __init__(self, ip: str, password: str, user: str = 'admin'):
        self._ip = ip
        self._password = password
        self._username = user or 'admin'
        self._client_cls = None   # resolved on first use (standard or GCM)

    # ── Private helpers ──────────────────────────────────────────────────────

    def _get_client(self):
        """Return an authorised client, auto-detecting firmware variant.

        - If the router is unreachable (network error), bail out immediately
          with a clear ConnectionError — trying the other variant won't help.
        - Otherwise, try the standard client first; on auth/crypto failure,
          fall back to the GCM client. The successful class is cached.
        """
        from tplinkrouterc6u import TPLinkMRClient, TPLinkMRClientGCM
        from tplinkrouterc6u.common.exception import ClientException, ClientError

        candidates = (
            [self._client_cls]
            if self._client_cls is not None
            else [TPLinkMRClient, TPLinkMRClientGCM]
        )

        auth_errors = []
        for cls in candidates:
            try:
                client = cls(
                    host=self._ip,
                    password=self._password,
                    username=self._username,
                    verify_ssl=False,
                    timeout=15,
                )
                client.authorize()
                if self._client_cls is None:
                    self._client_cls = cls
                    log.info("TP-Link firmware variant détectée : %s", cls.__name__)
                return client
            except _NETWORK_EXCS as e:
                # Router unreachable — no point trying the other variant
                raise ConnectionError(
                    f"Routeur TP-Link injoignable ({self._ip}) : {e}"
                ) from e
            except (ClientException, ClientError) as e:
                # Auth/crypto error — try the next variant
                auth_errors.append(f"{cls.__name__}: {e}")
                continue
            except Exception as e:
                # Unknown error — also try the next variant but record it
                auth_errors.append(f"{cls.__name__} (inattendu): {e}")
                continue

        raise ConnectionError(
            f"Authentification TP-Link impossible ({self._ip}) — "
            f"variantes essayées : {' | '.join(auth_errors)}"
        )

    @staticmethod
    def _make_sms_obj(index):
        """Build a minimal SMS object for delete operations (only .id is used)."""
        from tplinkrouterc6u.common.dataclass import SMS
        return SMS(
            id=int(index),
            sender='',
            content='',
            received_at=datetime.now(),
            unread=False,
        )

    # ── RouterAdapter interface ───────────────────────────────────────────────

    def send_sms(self, numbers: list, message: str) -> None:
        client = self._get_client()
        try:
            for number in numbers:
                client.send_sms(phone_number=number, message=message)
        finally:
            try:
                client.logout()
            except Exception:
                pass

    def get_inbox(self, page: int = 1, per_page: int = 20) -> dict:
        client = self._get_client()
        try:
            raw = client.get_sms()
        finally:
            try:
                client.logout()
            except Exception:
                pass

        # Normalise to our standard dict format, newest first
        all_sms = [
            {
                'Index': str(sms.id),
                'Phone': sms.sender or '—',
                'Content': sms.content or '',
                'Date': sms.received_at.strftime('%Y-%m-%d %H:%M:%S')
                        if isinstance(sms.received_at, datetime) else str(sms.received_at),
            }
            for sms in reversed(raw)   # API returns oldest first
        ]

        start = (page - 1) * per_page
        end = start + per_page
        return {
            'messages': all_sms[start:end],
            'page': page,
            'has_more': len(all_sms) > end,
        }

    def get_outbox(self, page: int = 1, per_page: int = 50) -> dict:
        raise NotSupportedError(
            "TP-Link MR n'expose pas la boîte d'envoi via son API."
        )

    def delete_sms(self, index) -> None:
        client = self._get_client()
        try:
            client.delete_sms(self._make_sms_obj(index))
        finally:
            try:
                client.logout()
            except Exception:
                pass

    def delete_sms_batch(self, indices: list) -> int:
        """Single login/logout for the whole batch."""
        client = self._get_client()
        try:
            for idx in indices:
                client.delete_sms(self._make_sms_obj(idx))
        finally:
            try:
                client.logout()
            except Exception:
                pass
        return len(indices)

    def get_status(self) -> dict:
        client = self._get_client()
        try:
            lte = client.get_lte_status()
        finally:
            try:
                client.logout()
            except Exception:
                pass

        return {
            'status':      'ok',
            'signal_bars': lte.sig_level if lte.sig_level is not None else 0,
            'network':     lte.network_type_info if lte.network_type is not None else '—',
            'operator':    lte.isp_name or '—',
        }

    def check_health(self) -> dict:
        client = self._get_client()
        try:
            client.logout()
        except Exception:
            pass
        return {'status': 'ok', 'router': 'reachable'}

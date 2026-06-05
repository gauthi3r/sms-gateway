"""Netgear LTE router adapter using eternalegypt (async wrapped for Flask)."""
import asyncio
import aiohttp
import eternalegypt
from .base import RouterAdapter, NotSupportedError


class NetgearAdapter(RouterAdapter):
    """Adapter for Netgear LTE modems (LB1120, LB2120, MR1100…).

    eternalegypt is fully async (asyncio + aiohttp). This adapter wraps
    every call with asyncio.run() so it stays sync-compatible with Flask.
    """

    brand = "netgear"
    supports_inbox = True
    supports_outbox = False   # Netgear API exposes inbox only

    def __init__(self, ip: str, password: str):
        self._ip = ip
        self._password = password

    # --- Async helpers ---

    @staticmethod
    def _run(coro):
        """Run an async coroutine synchronously."""
        return asyncio.run(coro)

    async def _with_modem(self, fn):
        """Open a session, login, execute fn(modem), logout."""
        jar = aiohttp.CookieJar(unsafe=True)
        async with aiohttp.ClientSession(cookie_jar=jar) as session:
            modem = eternalegypt.Modem(hostname=self._ip, websession=session)
            await modem.login(password=self._password)
            try:
                return await fn(modem)
            finally:
                await modem.logout()

    # --- RouterAdapter interface ---

    def send_sms(self, numbers: list, message: str) -> None:
        async def _send(modem):
            for number in numbers:
                await modem.sms(phone=number, message=message)

        self._run(self._with_modem(_send))

    def get_inbox(self, page: int = 1, per_page: int = 20) -> dict:
        async def _fetch(modem):
            info = await modem.information()
            return info.sms

        all_sms = self._run(self._with_modem(_fetch))

        # Sort newest first
        all_sms = sorted(all_sms, key=lambda s: s.id, reverse=True)

        # Paginate in memory (Netgear returns all at once)
        start = (page - 1) * per_page
        end = start + per_page
        page_sms = all_sms[start:end]

        messages = [
            {
                'Index': str(sms.id),
                'Phone': sms.sender or '—',
                'Content': sms.message or '',
                'Date': (
                    sms.timestamp.strftime('%Y-%m-%d %H:%M:%S')
                    if sms.timestamp else '—'
                ),
            }
            for sms in page_sms
        ]

        return {
            'messages': messages,
            'page': page,
            'has_more': len(all_sms) > end,
        }

    def get_outbox(self, page: int = 1, per_page: int = 50) -> dict:
        raise NotSupportedError(
            "Les routeurs Netgear n'exposent pas la boîte d'envoi via leur API."
        )

    def delete_sms(self, index) -> None:
        async def _delete(modem):
            await modem.delete_sms(int(index))

        self._run(self._with_modem(_delete))

    def delete_sms_batch(self, indices: list) -> int:
        """Delete multiple messages, one per session (Netgear has no batch delete)."""
        async def _delete_all(modem):
            for idx in indices:
                await modem.delete_sms(int(idx))

        self._run(self._with_modem(_delete_all))
        return len(indices)

    def get_status(self) -> dict:
        async def _fetch(modem):
            return await modem.information()

        info = self._run(self._with_modem(_fetch))

        # radio_quality is 0-100 → map to 0-5 bars
        quality = info.radio_quality or 0
        signal_bars = min(round(quality / 20), 5)

        # Pick the most informative network label available
        network = (
            info.connection_type
            or info.current_nw_service_type
            or info.current_ps_service_type
            or '—'
        )
        operator = info.register_network_display or '—'

        return {
            'status': 'ok',
            'signal_bars': signal_bars,
            'network': network,
            'operator': operator,
        }

    def check_health(self) -> dict:
        async def _ping(modem):
            await modem.information()

        self._run(self._with_modem(_ping))
        return {'status': 'ok', 'router': 'reachable'}

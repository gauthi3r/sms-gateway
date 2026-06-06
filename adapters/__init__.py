"""Router adapter factory."""
from .base import RouterAdapter, NotSupportedError
from .huawei import HuaweiAdapter
from .netgear import NetgearAdapter
from .glinet import GlinetAdapter
from .tplink import TplinkAdapter

# Registry: brand slug → adapter class
ADAPTERS: dict = {
    'huawei':  HuaweiAdapter,
    'netgear': NetgearAdapter,
    'glinet':  GlinetAdapter,
    'tplink':  TplinkAdapter,
}

# Human-readable labels and field requirements for the config UI
ADAPTER_META: dict = {
    'huawei': {
        'label': 'Huawei LTE (B525, B535, B818…)',
        'needs_user': True,
        'supports_outbox': True,
    },
    'netgear': {
        'label': 'Netgear LTE (LB1120, LB2120, MR1100…)',
        'needs_user': False,
        'supports_outbox': False,
    },
    'glinet': {
        'label': 'GL.iNet LTE/5G (X3000, XE3000, X750, E750…)',
        'needs_user': True,
        'supports_outbox': False,
    },
    'tplink': {
        'label': 'TP-Link MR (MR6400, MR600, MR200, MR500…)',
        'needs_user': False,
        'supports_outbox': False,
    },
}


def get_adapter(config: dict) -> RouterAdapter:
    """Instantiate the right adapter from a config dict.

    Expected keys: brand, ip, pass, (user — optional for some brands)
    """
    brand = config.get('brand', 'huawei').lower()
    cls = ADAPTERS.get(brand)
    if cls is None:
        raise ValueError(f"Marque inconnue : {brand!r}. Valeurs acceptées : {list(ADAPTERS)}")

    ip       = config['ip']
    password = config['pass']
    user     = config.get('user', '')

    if brand == 'huawei':
        return HuaweiAdapter(ip=ip, user=user, password=password)
    if brand == 'netgear':
        return NetgearAdapter(ip=ip, password=password)
    if brand == 'glinet':
        return GlinetAdapter(ip=ip, password=password, user=user)
    if brand == 'tplink':
        return TplinkAdapter(ip=ip, password=password)

    raise ValueError(f"Marque non implémentée : {brand!r}")

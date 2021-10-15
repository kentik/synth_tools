import logging
from typing import Optional

from kentik_api import KentikAPI
from kentik_api.utils import get_credentials

from kentik_synth_client import KentikSynthClient

log = logging.getLogger("apis")


class APIs:
    def __init__(self, mgmt_profile: str, syn_profile: str, proxy: Optional[str] = None) -> None:
        self.mgmt = KentikAPI(*get_credentials(mgmt_profile), proxy=proxy)
        self.syn = KentikSynthClient(get_credentials(syn_profile), proxy=proxy)
        log.debug("API: mgmt: %s", self.mgmt)
        log.debug("API: syn: %s", self.syn)

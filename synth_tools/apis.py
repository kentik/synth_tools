import os
from typing import Callable, Optional
from urllib.parse import urlparse

from kentik_api import KentikAPI
from kentik_api.utils import get_credentials
from kentik_api.utils.auth import load_credential_profile

from kentik_synth_client import KentikSynthClient
from synth_tools import log


def _fail(msg: str) -> None:
    raise RuntimeError(msg)


class APIs:
    def __init__(
        self,
        mgmt_profile: str,
        syn_profile: str,
        proxy: Optional[str] = None,
        api_url: Optional[str] = None,
        fail: Callable[[str], None] = _fail,
    ) -> None:
        self.mgmt_profile = mgmt_profile
        self.syn_profile = syn_profile
        self.proxy = proxy
        self.api_url = api_url
        self._fail = fail
        self._mgmt_api = None
        self._syn_api = None
        log.debug("API: mgmt profile: %s", self.mgmt_profile)
        log.debug("API: syn profile: %s", self.syn_profile)
        log.debug("API: proxy: %s", self.proxy)

    def _load_profile(self, profile: str) -> dict:
        home = os.environ.get("KTAPI_HOME", os.environ.get("HOME", "."))
        cfg_file = os.environ.get("KTAPI_CFG_FILE", os.path.join(home, ".kentik", profile))
        cfg = load_credential_profile(cfg_file)
        if cfg is None:
            self._fail(f"Failed to load profile file '{cfg_file}'")
        return cfg

    def _get_url(self, profile: str) -> Optional[str]:
        return os.environ.get("KTAPI_URL", self._load_profile(profile).get("url"))

    def _get_proxy(self, profile: str) -> Optional[str]:
        return os.environ.get("KTAPI_PROXY", self._load_profile(profile).get("proxy"))

    @property
    def mgmt(self):
        if not self._mgmt_api:
            if not self.mgmt_profile:
                self._fail("No authentication profile specified to target account")
            if self.proxy:
                proxy = self.proxy
            else:
                proxy = self._get_proxy(self.mgmt_profile)
            if not self.api_url:
                url = self._get_url(self.mgmt_profile)
            else:
                url = self.api_url
            # KentikAPI expects URL to include path, e.g. https://api.ou1.kentik.com/api/v5
            if url:
                u = urlparse(url)
                if u.path == "":
                    url = u._replace(path="/api/v5").geturl()
            else:
                url = KentikAPI.API_URL_US
            log.debug("API: mgmt URL: %s", url)
            log.debug("API: mgmt proxy: %s", proxy)
            self._mgmt_api = KentikAPI(*get_credentials(self.mgmt_profile), api_url=url, proxy=proxy)
            log.debug("API: mgmt_api: %s", self._mgmt_api)
        return self._mgmt_api

    @property
    def syn(self):
        if not self._syn_api:
            if not self.syn_profile:
                self._fail("No authentication profile specified (---profile option is required)")
            if self.proxy:
                proxy = self.proxy
            else:
                proxy = self._get_proxy(self.syn_profile)
            if not self.api_url:
                url = self._get_url(self.syn_profile)
            else:
                url = self.api_url
            log.debug("API: syn_api URL: %s", url)
            log.debug("API: syn_api proxy: %s", proxy)
            self._syn_api = KentikSynthClient(get_credentials(self.syn_profile), url=url, proxy=proxy)
            log.debug("API: syn_api: %s", self._syn_api)
        return self._syn_api

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
        mgmt_profile: Optional[str] = None,
        syn_profile: Optional[str] = None,
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
        if not profile:
            log.debug("No profile provided, expecting credentials in environment variables")
            missing = [v for v in ("KTAPI_AUTH_EMAIL", "KTAPI_AUTH_TOKEN") if not os.environ.get(v)]
            if missing:
                log.error("No credential profile specified and no %s in environment", " ".join(missing))
                self._fail("Missing authentication credentials ({})".format(" ".join(missing)))
            return {}
        home = os.environ.get("KTAPI_HOME", os.environ.get("HOME", "."))
        cfg_file = os.environ.get("KTAPI_CFG_FILE", os.path.join(home, ".kentik", profile))
        cfg = load_credential_profile(cfg_file)
        if cfg is None:
            self._fail(f"Failed to load profile file '{cfg_file}'")
        return cfg

    def _get_url(self, profile: str) -> Optional[str]:
        if self.api_url:
            return self.api_url
        else:
            cfg = self._load_profile(profile)
            if cfg:
                return cfg.get("url")
            else:
                return os.environ.get("KTAPI_URL")

    def _get_api_host(self, profile: str) -> Optional[str]:
        url = self._get_url(profile)
        if url:
            return urlparse(url).netloc
        else:
            return KentikAPI.API_HOST_US

    def _get_proxy(self, profile: str) -> Optional[str]:
        if self.proxy:
            return self.proxy
        else:
            cfg = self._load_profile(profile)
            if cfg:
                return cfg.get("proxy")
            else:
                return os.environ.get("KTAPI_PROXY")

    @property
    def mgmt(self):
        if not self._mgmt_api:
            proxy = self._get_proxy(self.mgmt_profile)
            api_host = self._get_api_host(self.mgmt_profile)
            log.debug("API: mgmt API host: %s", api_host)
            log.debug("API: mgmt proxy: %s", proxy)
            self._mgmt_api = KentikAPI(*get_credentials(self.mgmt_profile), api_host=api_host, proxy=proxy)
            log.debug("API: mgmt_api: %s", self._mgmt_api)
        return self._mgmt_api

    @property
    def syn(self):
        if not self._syn_api:
            proxy = self._get_proxy(self.syn_profile)
            url = self._get_url(self.syn_profile)
            log.debug("API: syn_api API url: %s", url)
            log.debug("API: syn_api proxy: %s", proxy)
            self._syn_api = KentikSynthClient(get_credentials(self.syn_profile), url=url, proxy=proxy)
            log.debug("API: syn_api: %s", self._syn_api)
        return self._syn_api

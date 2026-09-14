"""Client HTTP « poli » : robots.txt, throttling, User-Agent explicite, cache.

- Respecte robots.txt (par domaine, mis en cache).
- 1 requête / delai_min par domaine (défaut 2 s).
- Refuse net les domaines de la blocklist (agrégateurs interdits).
- Cache disque optionnel : permet de rejouer une collecte / figer des fixtures
  sans re-solliciter les serveurs.
"""

from __future__ import annotations

import hashlib
import time
from pathlib import Path
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import requests


class BlockedDomainError(RuntimeError):
    """Levée si on tente de collecter un domaine interdit (agrégateur)."""


class RobotsDisallowedError(RuntimeError):
    """Levée si robots.txt interdit l'URL demandée."""


class PoliteClient:
    def __init__(
        self,
        user_agent: str,
        *,
        min_delay: float = 2.0,
        blocked_domains: tuple[str, ...] = (),
        cache_dir: Path | str | None = None,
        respect_robots: bool = True,
        timeout: float = 30.0,
    ) -> None:
        self.user_agent = user_agent
        self.min_delay = min_delay
        self.blocked = {d.lower().removeprefix("www.") for d in blocked_domains}
        self.respect_robots = respect_robots
        self.timeout = timeout
        self.cache_dir = Path(cache_dir) if cache_dir else None
        if self.cache_dir:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._last_request: dict[str, float] = {}
        self._robots: dict[str, RobotFileParser | None] = {}
        self._session = requests.Session()
        self._session.headers["User-Agent"] = user_agent

    # -- Politique ------------------------------------------------------------
    def _domain(self, url: str) -> str:
        return urlparse(url).netloc.lower().removeprefix("www.")

    def _ensure_allowed(self, url: str) -> None:
        domain = self._domain(url)
        if domain in self.blocked:
            raise BlockedDomainError(f"Domaine interdit (blocklist) : {domain}")
        if not self.respect_robots:
            return
        rp = self._robots_for(url)
        if rp is not None and not rp.can_fetch(self.user_agent, url):
            raise RobotsDisallowedError(f"robots.txt interdit : {url}")

    def _robots_for(self, url: str) -> RobotFileParser | None:
        parsed = urlparse(url)
        key = f"{parsed.scheme}://{parsed.netloc}"
        if key in self._robots:
            return self._robots[key]
        parser = RobotFileParser()
        parser.set_url(f"{key}/robots.txt")
        rp: RobotFileParser | None
        try:
            self._throttle(self._domain(url))
            resp = self._session.get(f"{key}/robots.txt", timeout=self.timeout)
            if resp.status_code >= 400:
                rp = None  # pas de robots.txt exploitable -> on n'interdit pas
            else:
                parser.parse(resp.text.splitlines())
                rp = parser
        except requests.RequestException:
            rp = None
        self._robots[key] = rp
        return rp

    def _throttle(self, domain: str) -> None:
        last = self._last_request.get(domain)
        if last is not None:
            wait = self.min_delay - (time.monotonic() - last)
            if wait > 0:
                time.sleep(wait)
        self._last_request[domain] = time.monotonic()

    # -- Cache ----------------------------------------------------------------
    def _cache_path(self, url: str) -> Path | None:
        if not self.cache_dir:
            return None
        digest = hashlib.sha256(url.encode()).hexdigest()[:24]
        return self.cache_dir / digest

    # -- Récupération ---------------------------------------------------------
    def get_bytes(self, url: str, *, use_cache: bool = True) -> bytes:
        cache = self._cache_path(url) if use_cache else None
        if cache and cache.exists():
            return cache.read_bytes()
        self._ensure_allowed(url)
        self._throttle(self._domain(url))
        resp = self._session.get(url, timeout=self.timeout)
        resp.raise_for_status()
        data = resp.content
        if cache:
            cache.write_bytes(data)
        return data

    def get_text(self, url: str, *, use_cache: bool = True) -> str:
        return self.get_bytes(url, use_cache=use_cache).decode("utf-8", errors="replace")

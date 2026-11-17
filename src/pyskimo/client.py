"""
HTTP client with caching, retries, and rate limiting for Skimo data sources.

This module provides a configured HTTP client that:
- Caches responses locally to reduce server load
- Implements polite rate limiting with configurable delays
- Handles retries with exponential backoff
- Uses a descriptive User-Agent header
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any

import httpx
import requests_cache

logger = logging.getLogger(__name__)

USER_AGENT = "pyskimo/0.1.0 (https://github.com/pyskimo/pyskimo; Ski Mountaineering Data)"

DEFAULT_CACHE_PATH = Path.home() / ".cache" / "pyskimo"
DEFAULT_CACHE_TTL = 3600 * 24  # 24 hours
DEFAULT_RATE_LIMIT_DELAY = 1.0  # seconds between requests
DEFAULT_TIMEOUT = 30.0  # seconds
DEFAULT_MAX_RETRIES = 3


class SkimoClient:
    """
    HTTP client for fetching Skimo race data with caching and rate limiting.

    This client implements best practices for web scraping:
    - Local disk caching to minimize requests
    - Configurable rate limiting to be polite to servers
    - Exponential backoff for failed requests
    - Clear User-Agent identification

    Example:
        >>> client = SkimoClient()
        >>> html = client.get_html("https://ismf-ski.com/results/...")
        >>> client.close()

        # Or use as context manager:
        >>> with SkimoClient() as client:
        ...     html = client.get_html(url)
    """

    def __init__(
        self,
        cache_path: Path | str | None = None,
        cache_ttl: int = DEFAULT_CACHE_TTL,
        use_cache: bool = True,
        rate_limit_delay: float = DEFAULT_RATE_LIMIT_DELAY,
        timeout: float = DEFAULT_TIMEOUT,
        max_retries: int = DEFAULT_MAX_RETRIES,
    ) -> None:
        """
        Initialize the Skimo HTTP client.

        Args:
            cache_path: Path for cache storage. Defaults to ~/.cache/pyskimo
            cache_ttl: Cache time-to-live in seconds. Default 24 hours.
            use_cache: Whether to use caching. Set False to bypass cache.
            rate_limit_delay: Minimum seconds between requests. Default 1.0.
            timeout: Request timeout in seconds. Default 30.
            max_retries: Maximum retry attempts for failed requests. Default 3.
        """
        self.use_cache = use_cache
        self.rate_limit_delay = rate_limit_delay
        self.timeout = timeout
        self.max_retries = max_retries
        self._last_request_time: float = 0.0

        if cache_path is None:
            cache_path = DEFAULT_CACHE_PATH
        self.cache_path = Path(cache_path)
        self.cache_path.mkdir(parents=True, exist_ok=True)

        self._cached_session: requests_cache.CachedSession | None = None
        if use_cache:
            self._cached_session = requests_cache.CachedSession(
                cache_name=str(self.cache_path / "http_cache"),
                backend="sqlite",
                expire_after=cache_ttl,
                allowable_codes=[200],
                stale_if_error=True,
            )
            self._cached_session.headers["User-Agent"] = USER_AGENT

        self._httpx_client = httpx.Client(
            timeout=timeout,
            headers={"User-Agent": USER_AGENT},
            follow_redirects=True,
        )

    def _wait_for_rate_limit(self) -> None:
        """Wait if necessary to respect rate limiting."""
        if self.rate_limit_delay <= 0:
            return

        elapsed = time.monotonic() - self._last_request_time
        if elapsed < self.rate_limit_delay:
            sleep_time = self.rate_limit_delay - elapsed
            logger.debug(f"Rate limiting: sleeping {sleep_time:.2f}s")
            time.sleep(sleep_time)

    def _update_request_time(self) -> None:
        """Update the last request timestamp."""
        self._last_request_time = time.monotonic()

    def get(
        self,
        url: str,
        params: dict[str, Any] | None = None,
        bypass_cache: bool = False,
    ) -> httpx.Response:
        """
        Make a GET request with caching and rate limiting.

        Args:
            url: URL to fetch
            params: Optional query parameters
            bypass_cache: If True, skip cache for this request

        Returns:
            httpx.Response object

        Raises:
            httpx.HTTPError: If request fails after all retries
        """
        self._wait_for_rate_limit()

        if self.use_cache and not bypass_cache and self._cached_session is not None:
            response = self._get_with_cache(url, params)
        else:
            response = self._get_with_retries(url, params)

        self._update_request_time()
        return response

    def _get_with_cache(
        self,
        url: str,
        params: dict[str, Any] | None = None,
    ) -> httpx.Response:
        """Make a cached request using requests-cache."""
        if self._cached_session is None:
            return self._get_with_retries(url, params)

        try:
            response = self._cached_session.get(url, params=params, timeout=self.timeout)
            response.raise_for_status()

            httpx_response = httpx.Response(
                status_code=response.status_code,
                headers=dict(response.headers),
                content=response.content,
                request=httpx.Request("GET", url),
            )

            if hasattr(response, "from_cache") and response.from_cache:
                logger.debug(f"Cache hit: {url}")
            else:
                logger.debug(f"Cache miss: {url}")

            return httpx_response

        except Exception as e:
            logger.warning(f"Cache request failed, falling back to direct request: {e}")
            return self._get_with_retries(url, params)

    def _get_with_retries(
        self,
        url: str,
        params: dict[str, Any] | None = None,
    ) -> httpx.Response:
        """Make a request with exponential backoff retries."""
        last_error: Exception | None = None

        for attempt in range(self.max_retries):
            try:
                response = self._httpx_client.get(url, params=params)
                response.raise_for_status()
                return response

            except httpx.HTTPStatusError as e:
                if e.response.status_code in (429, 500, 502, 503, 504):
                    last_error = e
                    wait_time = (2**attempt) * 1.0
                    logger.warning(
                        f"Request failed with {e.response.status_code}, "
                        f"retrying in {wait_time}s (attempt {attempt + 1}/{self.max_retries})"
                    )
                    time.sleep(wait_time)
                else:
                    raise

            except httpx.RequestError as e:
                last_error = e
                wait_time = (2**attempt) * 1.0
                logger.warning(
                    f"Request error: {e}, "
                    f"retrying in {wait_time}s (attempt {attempt + 1}/{self.max_retries})"
                )
                time.sleep(wait_time)

        raise last_error or httpx.RequestError(
            f"Failed to fetch {url} after {self.max_retries} retries"
        )

    def get_html(
        self,
        url: str,
        params: dict[str, Any] | None = None,
        bypass_cache: bool = False,
    ) -> str:
        """
        Fetch a URL and return the HTML content as string.

        Args:
            url: URL to fetch
            params: Optional query parameters
            bypass_cache: If True, skip cache for this request

        Returns:
            HTML content as string
        """
        response = self.get(url, params=params, bypass_cache=bypass_cache)
        return response.text

    def get_bytes(
        self,
        url: str,
        params: dict[str, Any] | None = None,
        bypass_cache: bool = False,
    ) -> bytes:
        """
        Fetch a URL and return raw bytes (useful for PDFs).

        Args:
            url: URL to fetch
            params: Optional query parameters
            bypass_cache: If True, skip cache for this request

        Returns:
            Response content as bytes
        """
        response = self.get(url, params=params, bypass_cache=bypass_cache)
        return response.content

    def clear_cache(self) -> None:
        """Clear all cached responses."""
        if self._cached_session is not None:
            self._cached_session.cache.clear()  # type: ignore[no-untyped-call]
            logger.info("Cache cleared")

    def close(self) -> None:
        """Close the client and release resources."""
        self._httpx_client.close()
        if self._cached_session is not None:
            self._cached_session.close()  # type: ignore[no-untyped-call]

    def __enter__(self) -> SkimoClient:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()


_default_client: SkimoClient | None = None


def get_default_client() -> SkimoClient:
    """
    Get the default shared client instance.

    Creates a new client with default settings if one doesn't exist.
    """
    global _default_client
    if _default_client is None:
        _default_client = SkimoClient()
    return _default_client


def set_default_client(client: SkimoClient | None) -> None:
    """
    Set the default shared client instance.

    Pass None to clear the default client.
    """
    global _default_client
    _default_client = client

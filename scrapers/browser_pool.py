"""
Shared Browser Pool

Singleton that maintains one Playwright instance + one Chromium browser.
Scrapers get isolated BrowserContexts from the shared browser instead of
launching their own processes.

Usage (FastAPI lifespan):
    await browser_pool.start()
    ...
    await browser_pool.stop()

Usage (scrapers):
    async with browser_pool.get_context() as ctx:
        page = await ctx.new_page()
        ...
"""

import asyncio
import time
from contextlib import asynccontextmanager
from typing import Optional

from playwright.async_api import async_playwright, Playwright, Browser, BrowserContext

import sys
sys.path.insert(0, str(__file__).rsplit("/", 2)[0])

from config import config
from utils.logging import get_logger

logger = get_logger(__name__)

# Chromium args optimized for Docker / low-resource containers
_CHROMIUM_ARGS = [
    "--disable-dev-shm-usage",
    "--no-sandbox",
    "--disable-gpu",
    "--disable-extensions",
]


class BrowserPool:
    """Singleton browser pool that shares one Chromium instance."""

    def __init__(self) -> None:
        self._playwright: Optional[Playwright] = None
        self._browser: Optional[Browser] = None
        self._started = False
        self._semaphore: Optional[asyncio.Semaphore] = None
        self._lock = asyncio.Lock()
        self._waiting: int = 0

    async def start(self) -> None:
        """Launch Playwright and Chromium. Call once at app startup."""
        if self._started:
            return
        logger.info("BrowserPool: Starting Playwright + Chromium")
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            headless=config.HEADLESS,
            args=_CHROMIUM_ARGS,
        )
        self._semaphore = asyncio.Semaphore(config.MAX_BROWSER_PAGES)
        self._started = True
        logger.info("BrowserPool: Ready (max %d concurrent pages)", config.MAX_BROWSER_PAGES)

    async def stop(self) -> None:
        """Shut down browser and Playwright. Call once at app shutdown."""
        if not self._started:
            return
        logger.info("BrowserPool: Shutting down")
        self._started = False
        if self._browser:
            try:
                await self._browser.close()
            except Exception:
                pass
            self._browser = None
        if self._playwright:
            try:
                await self._playwright.stop()
            except Exception:
                pass
            self._playwright = None

    async def _ensure_browser(self) -> Browser:
        """Check browser health; restart if it crashed."""
        async with self._lock:
            if self._browser and self._browser.is_connected():
                return self._browser
            # Browser died — restart
            logger.warning("BrowserPool: Browser disconnected, restarting")
            # Clean up old browser
            if self._browser:
                try:
                    await self._browser.close()
                except Exception:
                    pass
            if not self._playwright:
                self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.launch(
                headless=config.HEADLESS,
                args=_CHROMIUM_ARGS,
            )
            logger.info("BrowserPool: Browser restarted")
            return self._browser

    @asynccontextmanager
    async def get_context(self, timeout: float = None, **kwargs):
        """
        Acquire a semaphore slot and yield an isolated BrowserContext.

        The context is automatically closed when the caller exits the block.
        Pass extra kwargs (e.g. user_agent) to browser.new_context().

        Args:
            timeout: Max seconds to wait for a pool slot. Defaults to
                     config.BROWSER_POOL_TIMEOUT. Raises RuntimeError
                     if no slot is available within the timeout.
        """
        if not self._started:
            raise RuntimeError("BrowserPool not started. Call start() first.")

        if timeout is None:
            timeout = float(config.BROWSER_POOL_TIMEOUT)

        self._waiting += 1
        logger.info(
            "BrowserPool: requesting slot (waiting=%d, timeout=%.0fs)",
            self._waiting, timeout,
        )
        acquire_start = time.monotonic()
        try:
            await asyncio.wait_for(self._semaphore.acquire(), timeout=timeout)
        except asyncio.TimeoutError:
            self._waiting -= 1
            raise RuntimeError(
                "Browser pool busy: no slot available within %.0fs "
                "(max_pages=%d, waiting=%d)" % (timeout, config.MAX_BROWSER_PAGES, self._waiting)
            )
        self._waiting -= 1
        acquire_time = time.monotonic() - acquire_start
        if acquire_time > 1.0:
            logger.info("BrowserPool: slot acquired in %.1fs", acquire_time)
        ctx: Optional[BrowserContext] = None
        try:
            browser = await self._ensure_browser()
            kwargs.setdefault("user_agent", config.USER_AGENT)
            ctx = await browser.new_context(**kwargs)
            yield ctx
        finally:
            if ctx:
                try:
                    await ctx.close()
                except Exception:
                    pass
            self._semaphore.release()


# Module-level singleton
browser_pool = BrowserPool()

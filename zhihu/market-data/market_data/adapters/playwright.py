from __future__ import annotations

from market_data.adapters.html import HtmlAdapter
from market_data.errors import AdapterTransportError
from market_data.schemas import AdapterResult, SourceDefinition, SourceSnapshot


class PlaywrightAdapter(HtmlAdapter):
    adapter_type = "playwright"

    def parse(self, source: SourceDefinition, snapshot: SourceSnapshot) -> AdapterResult:
        result = super().parse(source, snapshot)
        return result.model_copy(update={"adapter_type": "playwright", "adapter_version": self.version})

    def fetch(self, source: SourceDefinition) -> SourceSnapshot:
        self.assert_live_collection_allowed(source)
        self.throttle(source)
        try:
            from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise AdapterTransportError(
                "Playwright extra is not installed; install requirements-playwright.txt"
            ) from exc

        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                page = browser.new_page(user_agent="CareerGuardianMarketBot/0.1")
                response = page.goto(
                    str(source.base_url),
                    wait_until=source.config.get("wait_until", "networkidle"),
                    timeout=source.timeout_seconds * 1000,
                )
                selector = source.config.get("ready_selector")
                if selector:
                    page.wait_for_selector(selector, timeout=source.timeout_seconds * 1000)
                content = page.content()
                final_url = page.url
                status = response.status if response else None
                browser.close()
            return SourceSnapshot(
                source_url=final_url,
                content_type="text/html",
                content=content,
                http_status=status,
                transport_metadata={"attempt": 1, "mode": "live", "rendered": True},
            )
        except PlaywrightTimeoutError as exc:
            raise AdapterTransportError(f"Playwright timed out: {exc}") from exc
        except Exception as exc:
            raise AdapterTransportError(f"Playwright failed: {exc}") from exc

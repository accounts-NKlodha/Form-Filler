"""Load the real unpacked extension in Playwright's Chromium and press Alt+Shift+D on the
mock form served under an mca.gov.in URL. Every mca.gov.in request is answered locally by
route interception, so nothing ever reaches the real portal. Needs the local server running.
"""
import sys
import tempfile
from pathlib import Path

from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent
EXT = str(HERE.parent / "extension")
URL = "https://www.mca.gov.in/content/mca/global/en/mca/e-filing/annual-filings/form-mocktest.html"


def main():
    html = (HERE / "form-mocktest.html").read_text(encoding="utf-8")
    with sync_playwright() as p, tempfile.TemporaryDirectory() as prof:
        ctx = p.chromium.launch_persistent_context(prof, headless=False, args=[
            "--headless=new", f"--disable-extensions-except={EXT}", f"--load-extension={EXT}"])

        def handle(route):
            u = route.request.url
            if u.startswith("https://www.mca.gov.in/"):
                return route.fulfill(status=200, content_type="text/html", body=html if u == URL else "")
            if u.startswith("http://127.0.0.1:8742/"):
                return route.continue_()
            return route.abort()

        ctx.route("**/*", handle)
        page = ctx.new_page()
        page.goto(URL)
        page.wait_for_timeout(1500)
        page.keyboard.press("Alt+Shift+KeyD")
        page.wait_for_timeout(3000)
        box = page.evaluate("[...document.querySelectorAll('div')].map(d => d.innerText).find(t => t.startsWith('MCA filler')) || ''")
        print("BOX:", box.replace("\n", " | "))
        ctx.close()
        return "Saved MOCKTEST structure" in box


if __name__ == "__main__":
    sys.exit(0 if main() else 1)

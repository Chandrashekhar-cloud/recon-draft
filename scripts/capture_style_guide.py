"""Capture high-resolution screenshots of the Recon Draft style guide in light and dark mode."""

from pathlib import Path
from playwright.sync_api import sync_playwright

ARTIFACT_DIR = Path(r"C:\Users\chand\.gemini\antigravity-ide\brain\544eafd9-57f9-46a4-8f9c-6de9fb5078ca")
DOCS_DIR = Path(__file__).resolve().parent.parent / "docs"
DOCS_DIR.mkdir(parents=True, exist_ok=True)

def main():
    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(channel="msedge", headless=True)
        except Exception:
            browser = p.chromium.launch(headless=True)

        # 1. Capture Light Mode
        page = browser.new_page(viewport={"width": 1400, "height": 1800}, device_scale_factor=2)
        page.goto("http://127.0.0.1:5000/style-guide")
        page.wait_for_timeout(800)

        light_docs = DOCS_DIR / "style_guide_light.png"
        page.screenshot(path=str(light_docs), full_page=True)
        if ARTIFACT_DIR.is_dir():
            light_art = ARTIFACT_DIR / "style_guide_light.png"
            page.screenshot(path=str(light_art), full_page=True)

        print(f"Captured light mode screenshot to {light_docs}")

        # 2. Toggle to Dark Mode and Capture
        page.evaluate("window.ReconApp.toggleTheme()")
        page.wait_for_timeout(500)

        dark_docs = DOCS_DIR / "style_guide_dark.png"
        page.screenshot(path=str(dark_docs), full_page=True)
        if ARTIFACT_DIR.is_dir():
            dark_art = ARTIFACT_DIR / "style_guide_dark.png"
            page.screenshot(path=str(dark_art), full_page=True)

        print(f"Captured dark mode screenshot to {dark_docs}")

        browser.close()

if __name__ == "__main__":
    main()

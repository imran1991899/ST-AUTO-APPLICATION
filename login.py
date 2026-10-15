import os
from playwright.sync_api import sync_playwright

def login_oas():
    email = os.environ.get("OAS_EMAIL")
    password = os.environ.get("OAS_PASSWORD")

    if not email or not password:
        raise ValueError("OAS_EMAIL and OAS_PASSWORD environment variables must be set.")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()

        print("Navigating to OAS login page...")
        page.goto("https://oas.st.gov.my/en/home", timeout=60000)

        # 1. Time buffer for the popup message to fully load
        print("Waiting for popup to appear...")
        page.wait_for_timeout(3000)

        # 2. Close the popup
        try:
            print("Attempting to close popup...")
            close_btn = page.locator("button.close, .close, [aria-label='Close'], button:has-text('x'), .ui-dialog-titlebar-close, .aui-button-icon-close")
            if close_btn.is_visible(timeout=3000):
                close_btn.first.click()
                print("Popup closed successfully.")
                page.wait_for_timeout(1000)
        except Exception as e:
            print(f"No popup found or already closed: {e}")

        # 3. Fill Email Address and Password
        print("Filling credentials...")
        page.get_by_text("Email Address", exact=False).locator("..").locator("input").fill(email)
        page.get_by_text("Password", exact=True).locator("..").locator("input").fill(password)
        
        # 4. Locate and screenshot the CAPTCHA image
        try:
            print("Capturing CAPTCHA image...")
            # Look for the CAPTCHA image element on the form
            captcha_img = page.locator("img[src*='captcha'], img[id*='captcha'], .captcha img")
            if captcha_img.count() > 0:
                captcha_img.first.screenshot(path="captcha.png")
                print("Saved captcha.png successfully.")
            else:
                # Fallback: take a screenshot of the login form area
                page.screenshot(path="captcha.png")
                print("CAPTCHA specific tag not found, saved general view to captcha.png")
        except Exception as e:
            print(f"Could not save CAPTCHA image: {e}")

        # 5. Fill Text Verification box (If you have a static value or a way to supply it)
        # Note: If running locally, you can prompt input(). In GitHub Actions, it requires an automated solver or static bypass.
        captcha_text = os.environ.get("CAPTCHA_TEXT", "")
        if captcha_text:
            print("Filling Text Verification...")
            page.locator("input[name*='captcha'], input[id*='captcha'], input[placeholder*='Verification']").fill(captcha_text)
        
        # 6. Click the Sign In button
        print("Submitting login form...")
        submit_button = page.locator("input[type='submit'], button[type='submit']")
        submit_button.click(force=True)
        
        page.wait_for_load_state("networkidle")
        browser.close()

if __name__ == "__main__":
    login_oas()

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

        # 1. Close the popup announcement dialog if it appears
        try:
            print("Checking for popup announcement...")
            # Look for the close button indicated by the red circle in the screenshot
            close_btn = page.locator("button.close, .close, [aria-label='Close'], button:has-text('x'), .ui-dialog-titlebar-close")
            if close_btn.is_visible(timeout=5000):
                close_btn.first.click()
                print("Popup closed successfully.")
        except Exception as e:
            print(f"No popup found or already closed: {e}")

        # 2. Fill Email Address and Password fields using the form labels
        print("Filling credentials...")
        page.get_by_text("Email Address", exact=False).locator("..").locator("input").fill(email)
        page.get_by_text("Password", exact=True).locator("..").locator("input").fill(password)
        
        # 3. Click the Sign In button
        print("Submitting login form...")
        submit_button = page.locator("input[type='submit'], button[type='submit']")
        submit_button.click(force=True)
        
        # 4. Wait for page load after submit
        page.wait_for_load_state("networkidle")

        # --- VERIFICATION ---
        current_url = page.url
        print(f"Current page URL after submission: {current_url}")

        logged_in_indicator = page.locator("a:has-text('Logout'), a:has-text('Log Keluar'), .user-avatar, .dashboard")
        
        if logged_in_indicator.count() > 0 or "home" not in current_url:
            print("VERIFICATION SUCCESSFUL: Login was completed successfully!")
        else:
            print("VERIFICATION WARNING: Could not explicitly confirm login element, please check screenshot.")

        page.screenshot(path="login_result.png", full_page=True)
        print("Saved result screenshot to login_result.png")

        browser.close()

if __name__ == "__main__":
    login_oas()

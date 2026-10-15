import os
from playwright.sync_api import sync_playwright

def verify_session():
    # Check if session file exists
    if not os.path.exists("auth_state.json"):
        raise FileNotFoundError("auth_state.json not found! Please generate it locally first.")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        
        # Load the saved session cookies/state
        context = browser.new_context(storage_state="auth_state.json")
        page = context.new_page()

        print("Navigating to OAS home page using saved session...")
        page.goto("https://oas.st.gov.my/en/home", timeout=60000)
        
        page.wait_for_load_state("networkidle")

        current_url = page.url
        print(f"Current page URL: {current_url}")

        # Check if we are successfully logged in using indicators
        logged_in_indicator = page.locator("a:has-text('Logout'), a:has-text('Log Keluar'), .user-avatar, .dashboard")
        
        if logged_in_indicator.count() > 0 or "home" not in current_url:
            print("SUCCESS: Session cookie is active and you are logged in!")
        else:
            print("WARNING: Session may have expired. You will need to re-generate auth_state.json locally.")

        browser.close()

if __name__ == "__main__":
    verify_session()

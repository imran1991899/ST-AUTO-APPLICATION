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

        # 1. Fill credentials and click sign in
        page.fill("input[type='text'], input[name*='login'], input[id*='login']", email)
        page.fill("input[type='password'], input[name*='password'], input[id*='password']", password)
        
        print("Submitting login form...")
        page.click("button[type='submit'], input[type='submit'], button:has-text('Sign In'), button:has-text('Log Masuk')")
        
        # 2. Wait for page load after submit
        page.wait_for_load_state("networkidle")

        # --- VERIFICATION STEP 1: Check Current URL ---
        current_url = page.url
        print(f"Current page URL after submission: {current_url}")

        # --- VERIFICATION STEP 2: Check for Post-Login UI Elements ---
        # Checks if 'Logout', 'Sign Out', or dashboard indicators exist
        logged_in_indicator = page.locator("a:has-text('Logout'), a:has-text('Log Keluar'), .user-avatar, .dashboard")
        
        if logged_in_indicator.count() > 0 or "home" not in current_url:
            print("VERIFICATION SUCCESSFUL: Login was completed successfully!")
        else:
            print("VERIFICATION WARNING: Could not explicitly confirm login element, please check screenshot.")

        # --- VERIFICATION STEP 3: Take Screenshot ---
        page.screenshot(path="login_result.png", full_page=True)
        print("Saved result screenshot to login_result.png")

        browser.close()

if __name__ == "__main__":
    login_oas()

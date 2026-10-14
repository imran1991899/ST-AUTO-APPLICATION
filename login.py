import os
from playwright.sync_api import sync_playwright

def login_oas():
    # Retrieve secrets from environment variables
    email = os.environ.get("OAS_EMAIL")
    password = os.environ.get("OAS_PASSWORD")

    if not email or not password:
        raise ValueError("OAS_EMAIL and OAS_PASSWORD environment variables must be set.")

    with sync_playwright() as p:
        # Launch browser (headless mode set to False if you want to watch it run locally)
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()

        print("Navigating to OAS login page...")
        page.goto("https://oas.st.gov.my/en/home", timeout=60000)

        # Click or navigate to the login section if required, or go straight to the login portal URL
        # Adjust selectors based on exact form IDs/names on the page
        try:
            # Look for typical Liferay / portal login fields
            page.fill("input[type='text'], input[name*='login'], input[id*='login']", email)
            page.fill("input[type='password'], input[name*='password'], input[id*='password']", password)
            
            # Click the sign-in / submit button
            page.click("button[type='submit'], input[type='submit'], button:has-text('Sign In'), button:has-text('Log Masuk')")
            
            # Wait for dashboard or navigation to confirm login success
            page.wait_for_url("**/dashboard**", timeout=15000)
            print("Successfully logged into OAS!")
            
        except Exception as e:
            print(f"An error occurred during login interaction: {e}")
            page.screenshot(path="login_error.png")
            raise e
        finally:
            browser.close()

if __name__ == "__main__":
    login_oas()

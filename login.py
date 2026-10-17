import os
import time
import requests
from PIL import Image
from playwright.sync_api import sync_playwright

def ask_ollama_to_solve_captcha(image_path):
    print("Sending CAPTCHA image to lightweight Ollama vision model (moondream)...")
    url = "http://localhost:11434/api/generate"
    
    payload = {
        "model": "moondream",
        "prompt": "Read the numbers in this image. Output only the digits, with no extra text or spaces.",
        "images": [get_base64_image(image_path)],
        "stream": False,
        "options": {
            "temperature": 0.0,
            "num_predict": 10
        }
    }

    try:
        response = requests.post(url, json=payload, timeout=60)
        if response.status_code == 200:
            result = response.json().get("response", "").strip()
            clean_text = "".join(c for c in result if c.isalnum())
            print(f"Ollama successfully read CAPTCHA: '{clean_text}'")
            return clean_text
        else:
            print(f"Ollama API error: {response.text}")
            return ""
    except Exception as e:
        print(f"Failed to connect to local Ollama: {e}")
        return ""

def get_base64_image(image_path):
    import base64
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')

def navigate_to_e_application(page):
    """Adds a buffer, searches for e-Application in the top navigation bar, clicks it, and takes a screenshot."""
    print("Searching for e-Application...")
    try:
        # Buffer time to ensure the top menu is fully interactive after login redirect
        page.wait_for_timeout(4000)
        
        # Explicitly target the top menu navigation link for e-Application
        e_app_element = page.locator("a:has-text('e-Application')").first
        
        if e_app_element.count() > 0 and e_app_element.is_visible():
            e_app_element.click(force=True)
            print("Clicked e-Application successfully.")
        else:
            print("e-Application link not immediately visible. Waiting for selector...")
            page.wait_for_selector("a:has-text('e-Application')", timeout=10000)
            page.locator("a:has-text('e-Application')").first.click(force=True)
            print("Clicked e-Application after waiting for selector.")

        # Wait for the target page or content to load
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(3000)

        # Take screenshot for e-Application verification
        page.screenshot(path="e-application.png")
        print("Saved e-application.png successfully.")

    except Exception as e:
        print(f"Error navigating to e-Application: {e}")
        page.screenshot(path="e-application.png")

def navigate_to_evcs_application(page):
    """Searches for and clicks the 'LE2EVCS - Lesen Awam Pengagihan EV Charging Station' link and takes a screenshot."""
    print("Searching for LE2EVCS - Lesen Awam Pengagihan EV Charging Station link...")
    link_text = "LE2EVCS - Lesen Awam Pengagihan EV Charging Station"
    screenshot_name = f"Click_{link_text}.png"

    try:
        page.wait_for_timeout(3000)
        
        # Locate and click the blue link
        evcs_link = page.locator(f"a:has-text('{link_text}')").first
        
        if evcs_link.count() > 0 and evcs_link.is_visible():
            evcs_link.click(force=True)
            print(f"Clicked '{link_text}' successfully.")
        else:
            print(f"Link not immediately visible. Waiting for selector: {link_text}...")
            page.wait_for_selector(f"a:has-text('{link_text}')", timeout=10000)
            page.locator(f"a:has-text('{link_text}')").first.click(force=True)
            print(f"Clicked '{link_text}' after waiting.")

        # Wait for the page/form to load
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(3000)

        # Take screenshot after link click
        page.screenshot(path=screenshot_name)
        print(f"Saved '{screenshot_name}' successfully.")

    except Exception as e:
        print(f"Error clicking LE2EVCS link: {e}")
        page.screenshot(path=screenshot_name)

def upload_files(page):
    """Add your file upload automation logic here after navigating to e-Application."""
    print("Ready to upload files...")
    # Example:
    # page.goto("https://oas.st.gov.my/en/your-upload-page-url")
    # page.set_input_files("input[type='file']", "path/to/your/file.pdf")
    # page.click("button:has-text('Upload')")
    # page.wait_for_timeout(5000)

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

        # 1. Buffer time for the popup notification to render
        print("Buffer: Waiting for popup notification to appear...")
        page.wait_for_timeout(4000)

        # 2. Instantly remove/delete the popup element using the updated XPath
        try:
            print("Removing popup notification element via JavaScript...")
            xpath_popup = "/html/body/div[2]/div"
            page.evaluate(f"""
                const element = document.evaluate("{xpath_popup}", document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue;
                if (element) {{
                    element.remove();
                    console.log("Popup element successfully removed.");
                }} else {{
                    console.log("Popup element not found by XPath.");
                }}
            """)
            page.wait_for_timeout(1000)
        except Exception as e:
            print(f"Error removing popup element: {e}")

        # 3. Fill credentials
        print("Filling Email Address and Password...")
        page.get_by_text("Email Address", exact=False).locator("..").locator("input").fill(email)
        page.get_by_text("Password", exact=True).locator("..").locator("input").fill(password)
        
        # 4. Locate and screenshot the CAPTCHA image
        captcha_code = ""
        try:
            print("Capturing CAPTCHA image...")
            captcha_img = page.locator("form img, fieldset img, img[src*='captcha'], img[src*='Captcha'], img[src*='servlet']").first
            
            if captcha_img.count() > 0 and captcha_img.is_visible():
                captcha_img.screenshot(path="captcha.png")
                print("Saved captcha.png successfully from element.")
            else:
                print("Element locator failed. Saving full page snapshot as captcha.png fallback...")
                page.screenshot(path="captcha.png")

            if os.path.exists("captcha.png"):
                captcha_code = ask_ollama_to_solve_captcha("captcha.png")
            else:
                print("Error: captcha.png could not be written to disk.")

        except Exception as e:
            print(f"Error handling CAPTCHA screenshot: {e}")
            page.screenshot(path="captcha.png")

        # 5. Paste the number into the verification box
        if captcha_code:
            print(f"Pasting CAPTCHA text into verification box: {captcha_code}")
            verification_input = page.locator("input[name*='captcha'], input[id*='captcha'], input[placeholder*='Verification'], tr:has-text('Text Verification') input")
            verification_input.fill(captcha_code)
        else:
            print("Warning: Ollama could not extract a code.")

        # 6. Click Sign In
        print("Clicking Sign In...")
        submit_button = page.locator("input[type='submit'], button[type='submit']")
        submit_button.click(force=True)
        
        page.wait_for_load_state("networkidle")

        # Buffer delay for slower network conditions after submit
        print("Buffer: Waiting for post-login page to fully load...")
        page.wait_for_timeout(5000)

        current_url = page.url
        print(f"Current page URL after submission: {current_url}")

        # Take screenshot for login verification
        page.screenshot(path="success_login.png")
        print("success login...")

        logged_in_indicator = page.locator("a:has-text('Logout'), a:has-text('Log Keluar'), .user-avatar, .dashboard")
        if logged_in_indicator.count() > 0 or "home" not in current_url:
            print("VERIFICATION SUCCESSFUL: Login was completed successfully!")
            
            # --- NAVIGATE TO E-APPLICATION AND TAKE SCREENSHOT ---
            navigate_to_e_application(page)

            # --- NAVIGATE TO EVCS APPLICATION AND TAKE SCREENSHOT ---
            navigate_to_evcs_application(page)

            # --- CALL UPLOAD FUNCTION HERE INSTEAD OF CLOSING ---
            upload_files(page)
            
        else:
            print("VERIFICATION WARNING: Could not explicitly confirm login element.")

        browser.close()

if __name__ == "__main__":
    login_oas()

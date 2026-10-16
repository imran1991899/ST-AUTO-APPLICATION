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
        "stream": False
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

        # 2. Instantly remove/delete the popup element using your exact XPath
        try:
            print("Removing popup notification element via JavaScript...")
            xpath_popup = "/html/body/div[2]/div/div[2]"
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

        current_url = page.url
        print(f"Current page URL after submission: {current_url}")

        logged_in_indicator = page.locator("a:has-text('Logout'), a:has-text('Log Keluar'), .user-avatar, .dashboard")
        if logged_in_indicator.count() > 0 or "home" not in current_url:
            print("VERIFICATION SUCCESSFUL: Login was completed successfully!")
        else:
            print("VERIFICATION WARNING: Could not explicitly confirm login element.")

        browser.close()

if __name__ == "__main__":
    login_oas()

import os
import time
import requests
from PIL import Image
from playwright.sync_api import sync_playwright

def ask_ollama_to_solve_captcha(image_path):
    """Sends the captcha image to the local Ollama instance to read the text."""
    print("Sending CAPTCHA image to local Ollama vision model...")
    url = "http://localhost:11434/api/generate"
    
    # Using 'minicpm-v' or 'llava' (we will pull minicpm-v in the workflow as it's lightweight and fast for text/numbers)
    payload = {
        "model": "minicpm-v",
        "prompt": "Look at this image. Extract only the exact digits or characters shown inside the grey box. Output strictly the text/numbers with no extra words, spaces, or punctuation.",
        "images": [get_base64_image(image_path)],
        "stream": False
    }

    try:
        response = requests.post(url, json=payload, timeout=60)
        if response.status_code == 200:
            result = response.json().get("response", "").strip()
            # Clean up the output to keep only alphanumeric characters
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

        # 1. Time buffer for the popup message to fully load
        print("Buffer: Waiting for popup to appear...")
        page.wait_for_timeout(3000)

        # 2. Close the popup notification
        try:
            print("Attempting to close popup notification...")
            close_btn = page.locator("button.close, .close, [aria-label='Close'], button:has-text('x'), .ui-dialog-titlebar-close, .aui-button-icon-close")
            if close_btn.is_visible(timeout=3000):
                close_btn.first.click()
                print("Popup closed successfully.")
                page.wait_for_timeout(1000)
        except Exception as e:
            print(f"No popup found or already closed: {e}")

        # 3. Fill Email Address and Password
        print("Filling Email Address and Password...")
        page.get_by_text("Email Address", exact=False).locator("..").locator("input").fill(email)
        page.get_by_text("Password", exact=True).locator("..").locator("input").fill(password)
        
        # 4. Locate and screenshot the CAPTCHA image using exact XPath
        captcha_code = ""
        try:
            print("Capturing CAPTCHA image...")
            xpath_selector = "xpath=/html/body/div[1]/div/div/div[1]/div/div[2]/div/div[2]/div/div[2]/div/div[1]/section/div/div/div/form/fieldset/div/div/img"
            captcha_img = page.locator(xpath_selector)
            
            if captcha_img.count() > 0:
                captcha_img.first.screenshot(path="captcha.png")
                print("Saved captcha.png successfully.")
                
                # 5. Integrate with Ollama to read the CAPTCHA
                captcha_code = ask_ollama_to_solve_captcha("captcha.png")
            else:
                print("XPath captcha image not found.")
        except Exception as e:
            print(f"Error handling CAPTCHA screenshot: {e}")

        # 6. Paste/fill the number into the text verification box
        if captcha_code:
            print(f"Pasting CAPTCHA text into verification box: {captcha_code}")
            verification_input = page.locator("input[name*='captcha'], input[id*='captcha'], input[placeholder*='Verification'], tr:has-text('Text Verification') input")
            verification_input.fill(captcha_code)
        else:
            print("Warning: Ollama could not extract a code.")

        # 7. Click Sign In
        print("Clicking Sign In...")
        submit_button = page.locator("input[type='submit'], button[type='submit']")
        submit_button.click(force=True)
        
        page.wait_for_load_state("networkidle")

        # --- VERIFICATION ---
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

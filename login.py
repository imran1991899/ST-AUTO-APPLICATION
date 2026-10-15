import os
import pytesseract
from PIL import Image, ImageOps
from playwright.sync_api import sync_playwright

def solve_captcha_image(image_path):
    try:
        img = Image.open(image_path).convert('L')
        img = ImageOps.autocontrast(img, cutoff=2)
        config = '--oem 1 -c tessedit_char_whitelist=0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz'
        text = pytesseract.image_to_string(img, config=config)
        clean_text = text.strip().replace(" ", "").replace("\n", "")
        print(f"OCR Extracted CAPTCHA Text: '{clean_text}'")
        return clean_text
    except Exception as e:
        print(f"OCR Processing failed: {e}")
        return ""

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

        # 1. Time buffer for the popup message
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
        
        # 4. Locate, capture, and extract the CAPTCHA using your exact XPath
        captcha_code = ""
        try:
            print("Capturing CAPTCHA element using exact XPath...")
            xpath_selector = "xpath=/html/body/div[1]/div/div/div[1]/div/div[2]/div/div[2]/div/div[2]/div/div[1]/section/div/div/div/form/fieldset/div/div/img"
            captcha_img = page.locator(xpath_selector)
            
            if captcha_img.count() > 0:
                captcha_img.first.screenshot(path="captcha.png")
                print("Saved captcha.png successfully via XPath.")
                captcha_code = solve_captcha_image("captcha.png")
            else:
                print("XPath selector did not find the image, falling back to general locator...")
                fallback_img = page.locator("img[src*='captcha'], img[id*='captcha']").first
                if fallback_img.count() > 0:
                    fallback_img.screenshot(path="captcha.png")
                    captcha_code = solve_captcha_image("captcha.png")
        except Exception as e:
            print(f"Error handling CAPTCHA image via XPath: {e}")

        # 5. Fill Text Verification box
        if captcha_code:
            print(f"Filling Text Verification box with: {captcha_code}")
            page.locator("input[name*='captcha'], input[id*='captcha'], input[placeholder*='Verification'], tr:has-text('Text Verification') input").fill(captcha_code)
        else:
            print("Warning: No CAPTCHA code was extracted.")

        # 6. Click the Sign In button
        print("Submitting login form...")
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

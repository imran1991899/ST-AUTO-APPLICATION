import os
import time
import requests
from PIL import Image
from playwright.sync_api import sync_playwright

def resize_screenshot_to_limit(image_path, max_size_kb=600):
    """Resizes and compresses an image until it is under max_size_kb (600KB)."""
    if not os.path.exists(image_path):
        return
    
    max_bytes = max_size_kb * 1024
    if os.path.getsize(image_path) <= max_bytes:
        return

    print(f"Compressing {image_path} to be under {max_size_kb}KB...")
    try:
        with Image.open(image_path) as img:
            # Convert RGBA to RGB if saving as JPEG
            if img.mode in ("RGBA", "P"):
                img = img.convert("RGB")
            
            quality = 95
            img.save(image_path, "JPEG", quality=quality)
            
            while os.path.getsize(image_path) > max_bytes and quality > 10:
                quality -= 10
                img.save(image_path, "JPEG", quality=quality)
            
            # If still too large, downscale dimensions
            scale = 0.9
            while os.path.getsize(image_path) > max_bytes and scale > 0.1:
                new_width = int(img.width * scale)
                new_height = int(img.height * scale)
                resized_img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
                resized_img.save(image_path, "JPEG", quality=quality)
                scale -= 0.1

        print(f"Successfully compressed {image_path} to {os.path.getsize(image_path) / 1024:.2f}KB")
    except Exception as e:
        print(f"Error compressing screenshot {image_path}: {e}")

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
    """Searches for e-Application in the top navigation bar, clicks it, and takes a screenshot."""
    print("Searching for e-Application...")
    try:
        # Dynamically wait for the top navigation menu link to appear
        e_app_element = page.locator("a:has-text('e-Application')").first
        e_app_element.wait_for(state="visible", timeout=10000)
        e_app_element.click(force=True)
        print("Clicked e-Application successfully.")

        # Wait for content load dynamically
        page.wait_for_load_state("domcontentloaded")

        # Take screenshot for e-Application verification
        page.screenshot(path="e-application.png")
        resize_screenshot_to_limit("e-application.png", 600)
        print("Saved e-application.png successfully.")

    except Exception as e:
        print(f"Error navigating to e-Application: {e}")
        page.screenshot(path="e-application.png")
        resize_screenshot_to_limit("e-application.png", 600)

def navigate_to_evcs_application(page):
    """Searches for and clicks the 'LE2EVCS - Lesen Awam Pengagihan EV Charging Station' link and takes a screenshot."""
    print("Searching for LE2EVCS - Lesen Awam Pengagihan EV Charging Station link...")
    link_text = "LE2EVCS - Lesen Awam Pengagihan EV Charging Station"
    screenshot_name = f"Click_{link_text}.png"

    try:
        # Dynamically wait for the specific link to appear
        evcs_link = page.locator(f"a:has-text('{link_text}')").first
        evcs_link.wait_for(state="visible", timeout=10000)
        evcs_link.click(force=True)
        print(f"Clicked '{link_text}' successfully.")

        # Wait for load state
        page.wait_for_load_state("domcontentloaded")

        # Take screenshot after link click
        page.screenshot(path=screenshot_name)
        resize_screenshot_to_limit(screenshot_name, 600)
        print(f"Saved '{screenshot_name}' successfully.")

    except Exception as e:
        print(f"Error clicking LE2EVCS link: {e}")
        page.screenshot(path=screenshot_name)
        resize_screenshot_to_limit(screenshot_name, 600)

def search_after_hantar(page):
    """Searches for the button/element containing 'Hantar', clicks it, takes a screenshot, and saves another screenshot afterwards."""
    print("Searching for 'Hantar' button/element to click...")
    try:
        hantar_element = page.locator("button:has-text('Hantar'), input[type='submit'][value*='Hantar'], a:has-text('Hantar')").first
        hantar_element.wait_for(state="visible", timeout=10000)
        
        # Take screenshot before or right as we locate/interact with Hantar
        page.screenshot(path="before_hantar.png")
        resize_screenshot_to_limit("before_hantar.png", 600)
        print("Saved before_hantar.png successfully.")

        hantar_element.click(force=True)
        print("Clicked 'Hantar' successfully.")

        page.wait_for_load_state("domcontentloaded")
        
        # Take screenshot after Hantar click
        page.screenshot(path="after_hantar.png")
        resize_screenshot_to_limit("after_hantar.png", 600)
        print("Saved after_hantar.png successfully.")

    except Exception as e:
        print(f"Error clicking 'Hantar': {e}")
        page.screenshot(path="after_hantar.png")
        resize_screenshot_to_limit("after_hantar.png", 600)

def process_bahagian_sections(page):
    """Iterates through Bahagian A to Bahagian G, adding buffer, text fill/document uploads, and screenshots."""
    sections = ['Bahagian A', 'Bahagian B', 'Bahagian C', 'Bahagian D', 'Bahagian E', 'Bahagian F', 'Bahagian G']
    
    for section in sections:
        print(f"Processing {section}...")
        try:
            # Click the tab for the current Bahagian
            tab_element = page.locator(f"a:has-text('{section}'), button:has-text('{section}'), td:has-text('{section}')").first
            if tab_element.count() > 0 and tab_element.is_visible():
                tab_element.click(force=True)
                print(f"Clicked tab for {section}.")
            else:
                print(f"Tab for {section} not directly clickable by text, trying generic locator...")
            
            page.wait_for_load_state("domcontentloaded")
            
            # --- BUFFER TIME & PLACEHOLDER: ADD FUNCTION ADD TEXT AND DOCUMENT UPLOAD ---
            print(f"Buffer active for {section}: waiting for manual/automated information filling...")
            time.sleep(3) # Buffer time for section load and user information input preparation
            
            # TODO: add function add text and document upload
            # Example text fill / document upload placeholder logic:
            # page.fill("input[name='example']", "sample text")
            # page.set_input_files("input[type='file']", "path/to/document.pdf")
            
            # Take screenshot for the current Bahagian
            safe_name = section.replace(" ", "_").lower()
            screenshot_filename = f"{safe_name}.png"
            page.screenshot(path=screenshot_filename)
            resize_screenshot_to_limit(screenshot_filename, 600)
            print(f"Saved {screenshot_filename} successfully.")

            # Special check for Bahagian G to search and click "Simpan Draf"
            if section == 'Bahagian G':
                print("Searching for 'Simpan Draf' in Bahagian G...")
                try:
                    simpan_draf_btn = page.locator("button:has-text('Simpan Draf'), input[type='submit'][value*='Simpan Draf'], a:has-text('Simpan Draf')").first
                    simpan_draf_btn.wait_for(state="visible", timeout=8000)
                    simpan_draf_btn.click(force=True)
                    print("Clicked 'Simpan Draf' successfully in Bahagian G.")
                    
                    page.wait_for_load_state("domcontentloaded")
                    time.sleep(4) # Buffer after saving draft
                    
                    page.screenshot(path="bahagian_g_simpan_draf.png")
                    resize_screenshot_to_limit("bahagian_g_simpan_draf.png", 600)
                    print("Saved bahagian_g_simpan_draf.png successfully.")
                except Exception as ex_draft:
                    print(f"Could not find or click 'Simpan Draf': {ex_draft}")
                    page.screenshot(path="bahagian_g_simpan_draf.png")
                    resize_screenshot_to_limit("bahagian_g_simpan_draf.png", 600)

        except Exception as e:
            print(f"Error processing {section}: {e}")
            safe_name = section.replace(" ", "_").lower()
            page.screenshot(path=f"{safe_name}.png")
            resize_screenshot_to_limit(f"{safe_name}.png", 600)

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

        # 1. Quick check for the popup notification element without a long static sleep
        try:
            print("Checking and removing popup notification element via JavaScript...")
            xpath_popup = "/html/body/div[2]/div"
            page.evaluate(f"""
                const element = document.evaluate("{xpath_popup}", document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue;
                if (element) {{
                    element.remove();
                    console.log("Popup element successfully removed.");
                }}
            """)
        except Exception as e:
            print(f"Error removing popup element: {e}")

        # 2. Fill credentials immediately
        print("Filling Email Address and Password...")
        page.get_by_text("Email Address", exact=False).locator("..").locator("input").fill(email)
        page.get_by_text("Password", exact=True).locator("..").locator("input").fill(password)
        
        # 3. Locate and screenshot the CAPTCHA image
        captcha_code = ""
        try:
            print("Capturing CAPTCHA image...")
            captcha_img = page.locator("form img, fieldset img, img[src*='captcha'], img[src*='Captcha'], img[src*='servlet']").first
            
            if captcha_img.count() > 0 and captcha_img.is_visible():
                captcha_img.screenshot(path="captcha.png")
                resize_screenshot_to_limit("captcha.png", 600)
                print("Saved captcha.png successfully from element.")
            else:
                print("Element locator failed. Saving full page snapshot as captcha.png fallback...")
                page.screenshot(path="captcha.png")
                resize_screenshot_to_limit("captcha.png", 600)

            if os.path.exists("captcha.png"):
                captcha_code = ask_ollama_to_solve_captcha("captcha.png")
            else:
                print("Error: captcha.png could not be written to disk.")

        except Exception as e:
            print(f"Error handling CAPTCHA screenshot: {e}")
            page.screenshot(path="captcha.png")
            resize_screenshot_to_limit("captcha.png", 600)

        # 4. Paste the number into the verification box
        if captcha_code:
            print(f"Pasting CAPTCHA text into verification box: {captcha_code}")
            verification_input = page.locator("input[name*='captcha'], input[id*='captcha'], input[placeholder*='Verification'], tr:has-text('Text Verification') input")
            verification_input.fill(captcha_code)
        else:
            print("Warning: Ollama could not extract a code.")

        # 5. Click Sign In
        print("Clicking Sign In...")
        submit_button = page.locator("input[type='submit'], button[type='submit']")
        submit_button.click(force=True)
        
        # Fast load state trigger instead of static sleeping
        page.wait_for_load_state("domcontentloaded")

        current_url = page.url
        print(f"Current page URL after submission: {current_url}")

        # Take screenshot for login verification
        page.screenshot(path="success_login.png")
        resize_screenshot_to_limit("success_login.png", 600)
        print("success login...")

        logged_in_indicator = page.locator("a:has-text('Logout'), a:has-text('Log Keluar'), .user-avatar, .dashboard")
        if logged_in_indicator.count() > 0 or "home" not in current_url:
            print("VERIFICATION SUCCESSFUL: Login was completed successfully!")
            
            # --- NAVIGATE TO E-APPLICATION AND TAKE SCREENSHOT ---
            navigate_to_e_application(page)

            # --- NAVIGATE TO EVCS APPLICATION AND TAKE SCREENSHOT ---
            navigate_to_evcs_application(page)

            # --- SEARCH AFTER HANTAR, TAKE SCREENSHOTS, AND CLICK IT ---
            search_after_hantar(page)

            # --- PROCESS BAHAGIAN A TO G (WITH BUFFERS, TEXT/UPLOAD REMARK, AND SIMPAN DRAF) ---
            process_bahagian_sections(page)

            # --- CALL UPLOAD FUNCTION HERE INSTEAD OF CLOSING ---
            upload_files(page)
            
        else:
            print("VERIFICATION WARNING: Could not explicitly confirm login element.")

        browser.close()

if __name__ == "__main__":
    login_oas()

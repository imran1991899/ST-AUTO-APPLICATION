import os
import time
import requests
from PIL import Image
from playwright.sync_api import sync_playwright

def resize_screenshot_to_limit(image_path, max_size_kb=600):
    if not os.path.exists(image_path):
        return
    max_bytes = max_size_kb * 1024
    if os.path.getsize(image_path) <= max_bytes:
        return
    try:
        with Image.open(image_path) as img:
            if img.mode in ("RGBA", "P"):
                img = img.convert("RGB")
            quality = 95
            img.save(image_path, "JPEG", quality=quality)
            while os.path.getsize(image_path) > max_bytes and quality > 10:
                quality -= 10
                img.save(image_path, "JPEG", quality=quality)
            scale = 0.9
            while os.path.getsize(image_path) > max_bytes and scale > 0.1:
                new_width = int(img.width * scale)
                new_height = int(img.height * scale)
                resized_img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
                resized_img.save(image_path, "JPEG", quality=quality)
                scale -= 0.1
    except Exception as e:
        print(f"Error compressing screenshot {image_path}: {e}")

def ask_ollama_to_solve_captcha(image_path):
    url = "http://localhost:11434/api/generate"
    payload = {
        "model": "moondream",
        "prompt": "Read the numbers in this image. Output only the digits, with no extra text or spaces.",
        "images": [get_base64_image(image_path)],
        "stream": False,
        "options": {"temperature": 0.0, "num_predict": 10}
    }
    try:
        response = requests.post(url, json=payload, timeout=60)
        if response.status_code == 200:
            result = response.json().get("response", "").strip()
            clean_text = "".join(c for c in result if c.isalnum())
            return clean_text
        return ""
    except Exception as e:
        print(f"Failed to connect to local Ollama: {e}")
        return ""

def get_base64_image(image_path):
    import base64
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')

def navigate_to_e_application(page):
    try:
        e_app_element = page.locator("a:has-text('e-Application')").first
        e_app_element.wait_for(state="visible", timeout=10000)
        e_app_element.click(force=True)
        page.wait_for_load_state("domcontentloaded")
        page.screenshot(path="e-application.png")
        resize_screenshot_to_limit("e-application.png", 600)
    except Exception as e:
        print(f"Error navigating to e-Application: {e}")

def navigate_to_evcs_application(page):
    link_text = "LE2EVCS - Lesen Awam Pengagihan EV Charging Station"
    screenshot_name = f"Click_{link_text}.png"
    try:
        evcs_link = page.locator(f"a:has-text('{link_text}')").first
        evcs_link.wait_for(state="visible", timeout=10000)
        evcs_link.click(force=True)
        page.wait_for_load_state("domcontentloaded")
        page.screenshot(path=screenshot_name)
        resize_screenshot_to_limit(screenshot_name, 600)
    except Exception as e:
        print(f"Error clicking LE2EVCS link: {e}")

def search_after_hantar(page):
    try:
        hantar_element = page.locator("button:has-text('Hantar'), input[type='submit'][value*='Hantar'], a:has-text('Hantar')").first
        hantar_element.wait_for(state="visible", timeout=10000)
        page.screenshot(path="before_hantar.png")
        resize_screenshot_to_limit("before_hantar.png", 600)
        hantar_element.click(force=True)
        page.wait_for_load_state("domcontentloaded")
        page.screenshot(path="after_hantar.png")
        resize_screenshot_to_limit("after_hantar.png", 600)
    except Exception as e:
        print(f"Error clicking 'Hantar': {e}")

def process_bahagian_sections(page):
    target_project = os.environ.get("TRIGGER_PROJECT_NAME", "")
    print(f"Processing automation workflow for project: {target_project}")
    sections = ['Bahagian A', 'Bahagian B', 'Bahagian C', 'Bahagian D', 'Bahagian E', 'Bahagian F', 'Bahagian G']
    for section in sections:
        try:
            tab_element = page.locator(f"a:has-text('{section}'), button:has-text('{section}'), td:has-text('{section}')").first
            if tab_element.count() > 0 and tab_element.is_visible():
                tab_element.click(force=True)
            page.wait_for_load_state("domcontentloaded")
            time.sleep(3)
            
            safe_name = section.replace(" ", "_").lower()
            screenshot_filename = f"{safe_name}.png"
            page.screenshot(path=screenshot_filename)
            resize_screenshot_to_limit(screenshot_filename, 600)

            if section == 'Bahagian G':
                time.sleep(4)
                try:
                    simpan_draf_btn = page.locator("input[value*='Simpan Draf'], button:has-text('Simpan Draf'), input[type='button'][value*='Simpan Draf'], a:has-text('Simpan Draf')").first
                    simpan_draf_btn.wait_for(state="visible", timeout=10000)
                    simpan_draf_btn.click(force=True)
                    page.wait_for_load_state("domcontentloaded")
                    time.sleep(3)
                    page.screenshot(path="bahagian_g_simpan_draf.png")
                    resize_screenshot_to_limit("bahagian_g_simpan_draf.png", 600)
                except Exception as ex_draft:
                    print(f"Could not click 'Simpan Draf': {ex_draft}")
        except Exception as e:
            print(f"Error processing {section}: {e}")

def upload_files(page):
    print("Ready to upload files...")

def login_oas():
    email = os.environ.get("OAS_EMAIL")
    password = os.environ.get("OAS_PASSWORD")
    if not email or not password:
        raise ValueError("OAS_EMAIL and OAS_PASSWORD environment variables must be set.")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()

        page.goto("https://oas.st.gov.my/en/home", timeout=60000)
        try:
            xpath_popup = "/html/body/div[2]/div"
            page.evaluate(f"""
                const element = document.evaluate("{xpath_popup}", document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue;
                if (element) {{ element.remove(); }}
            """)
        except Exception as e:
            print(f"Error removing popup: {e}")

        page.get_by_text("Email Address", exact=False).locator("..").locator("input").fill(email)
        page.get_by_text("Password", exact=True).locator("..").locator("input").fill(password)
        
        captcha_code = ""
        try:
            captcha_img = page.locator("form img, fieldset img, img[src*='captcha'], img[src*='Captcha'], img[src*='servlet']").first
            if captcha_img.count() > 0 and captcha_img.is_visible():
                captcha_img.screenshot(path="captcha.png")
                resize_screenshot_to_limit("captcha.png", 600)
            else:
                page.screenshot(path="captcha.png")
                resize_screenshot_to_limit("captcha.png", 600)

            if os.path.exists("captcha.png"):
                captcha_code = ask_ollama_to_solve_captcha("captcha.png")
        except Exception as e:
            print(f"Error handling CAPTCHA: {e}")

        if captcha_code:
            verification_input = page.locator("input[name*='captcha'], input[id*='captcha'], input[placeholder*='Verification'], tr:has-text('Text Verification') input")
            verification_input.fill(captcha_code)

        submit_button = page.locator("input[type='submit'], button[type='submit']")
        submit_button.click(force=True)
        page.wait_for_load_state("domcontentloaded")

        page.screenshot(path="success_login.png")
        resize_screenshot_to_limit("success_login.png", 600)

        logged_in_indicator = page.locator("a:has-text('Logout'), a:has-text('Log Keluar'), .user-avatar, .dashboard")
        if logged_in_indicator.count() > 0 or "home" not in page.url:
            navigate_to_e_application(page)
            navigate_to_evcs_application(page)
            search_after_hantar(page)
            process_bahagian_sections(page)
            upload_files(page)
        
        browser.close()

if __name__ == "__main__":
    login_oas()

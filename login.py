import os
import time
import json
import requests
from PIL import Image
from playwright.sync_api import sync_playwright

PAYLOAD_FILE = "draft_payload.json"

def load_payload():
    if os.path.exists(PAYLOAD_FILE):
        try:
            with open(PAYLOAD_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"Error reading payload: {e}")
    return {}

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
    except Exception as e:
        print(f"Error compressing screenshot {image_path}: {e}")

def ask_ollama_to_solve_captcha(image_path):
    url = "http://localhost:11434/api/generate"
    try:
        import base64
        with open(image_path, "rb") as img_file:
            b64_img = base64.b64encode(img_file.read()).decode('utf-8')
        
        payload = {
            "model": "moondream",
            "prompt": "Read the numbers in this image. Output only the digits, with no extra text or spaces.",
            "images": [b64_img],
            "stream": False,
            "options": {"temperature": 0.0, "num_predict": 10}
        }
        response = requests.post(url, json=payload, timeout=60)
        if response.status_code == 200:
            result = response.json().get("response", "").strip()
            return "".join(c for c in result if c.isalnum())
    except Exception as e:
        print(f"Ollama connection error: {e}")
    return ""

def fill_field_if_exists(page, selector, value):
    if not value:
        return
    try:
        element = page.locator(selector).first
        if element.count() > 0 and element.is_visible():
            element.fill(str(value))
    except Exception as e:
        print(f"Could not fill selector {selector}: {e}")

def upload_file_if_exists(page, selector, file_path):
    if not file_path or not os.path.exists(file_path):
        return
    try:
        element = page.locator(selector).first
        if element.count() > 0:
            element.set_input_files(file_path)
    except Exception as e:
        print(f"File upload error: {e}")

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
    try:
        evcs_link = page.locator(f"a:has-text('{link_text}')").first
        evcs_link.wait_for(state="visible", timeout=10000)
        evcs_link.click(force=True)
        page.wait_for_load_state("domcontentloaded")
        page.screenshot(path="Click_EVCS.png")
        resize_screenshot_to_limit("Click_EVCS.png", 600)
    except Exception as e:
        print(f"Error clicking LE2EVCS link: {e}")

def process_bahagian_sections_with_data(page, payload):
    sections = ['Bahagian A', 'Bahagian B', 'Bahagian C', 'Bahagian D', 'Bahagian E', 'Bahagian F', 'Bahagian G']
    
    for section in sections:
        print(f"Processing {section}...")
        try:
            tab_element = page.locator(f"a:has-text('{section}'), button:has-text('{section}'), td:has-text('{section}')").first
            if tab_element.count() > 0 and tab_element.is_visible():
                tab_element.click(force=True)
                page.wait_for_load_state("domcontentloaded")
            time.sleep(2)

            if section == 'Bahagian A':
                fill_field_if_exists(page, "textarea[name*='maklumat'], textarea[id*='a_info']", payload.get("bahagian_a_info"))
            elif section == 'Bahagian B':
                fill_field_if_exists(page, "input[name*='keupayaan']", payload.get("b_jumlah_keupayaan"))
                fill_field_if_exists(page, "input[name*='kehendak_maksimum']", payload.get("b_kehendak_maksimum"))
                fill_field_if_exists(page, "input[name*='incomers']", payload.get("b_bilangan_incomers"))
                fill_field_if_exists(page, "input[name*='pencawang']", payload.get("b_nama_pencawang"))
            elif section == 'Bahagian C':
                files = payload.get("uploaded_files", {})
                for key, file_path in files.items():
                    upload_file_if_exists(page, "input[type='file']", file_path)
            elif section == 'Bahagian D':
                fill_field_if_exists(page, "textarea[name*='d_info']", payload.get("bahagian_d_info"))
            elif section == 'Bahagian E':
                fill_field_if_exists(page, "input[name*='no_lot']", payload.get("e_no_lot"))
                fill_field_if_exists(page, "input[name*='mukim']", payload.get("e_mukim"))
            elif section == 'Bahagian F':
                checkboxes = page.locator("input[type='checkbox']")
                for i in range(checkboxes.count()):
                    try:
                        checkboxes.nth(i).check(force=True)
                    except Exception:
                        pass
            elif section == 'Bahagian G':
                fill_field_if_exists(page, "input[name*='nama']", payload.get("g_nama"))
                fill_field_if_exists(page, "input[name*='perakuan']", payload.get("g_no_perakuan"))
                fill_field_if_exists(page, "textarea[name*='alamat']", payload.get("g_alamat"))

                print("Clicking 'Simpan Draf' in Bahagian G on OAS portal...")
                time.sleep(3)
                simpan_draf_btn = page.locator("input[value*='Simpan Draf'], button:has-text('Simpan Draf'), input[type='button'][value*='Simpan Draf']").first
                if simpan_draf_btn.count() > 0 and simpan_draf_btn.is_visible():
                    simpan_draf_btn.click(force=True)
                    page.wait_for_load_state("domcontentloaded")
                    time.sleep(3)

            safe_name = section.replace(" ", "_").lower()
            page.screenshot(path=f"{safe_name}.png")
            resize_screenshot_to_limit(f"{safe_name}.png", 600)
        except Exception as e:
            print(f"Error in {section}: {e}")

def login_oas():
    email = os.environ.get("OAS_EMAIL")
    password = os.environ.get("OAS_PASSWORD")
    payload = load_payload()

    if not email or not password:
        raise ValueError("OAS_EMAIL and OAS_PASSWORD environment variables must be set.")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()

        print("Navigating to OAS login page...")
        page.goto("https://oas.st.gov.my/en/home", timeout=60000)

        try:
            xpath_popup = "/html/body/div[2]/div"
            page.evaluate(f"""
                const element = document.evaluate("{xpath_popup}", document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue;
                if (element) {{ element.remove(); }}
            """)
        except Exception:
            pass

        print("Filling Credentials...")
        page.get_by_text("Email Address", exact=False).locator("..").locator("input").fill(email)
        page.get_by_text("Password", exact=True).locator("..").locator("input").fill(password)
        
        captcha_code = ""
        try:
            captcha_img = page.locator("form img, fieldset img, img[src*='captcha'], img[src*='Captcha']").first
            if captcha_img.count() > 0 and captcha_img.is_visible():
                captcha_img.screenshot(path="captcha.png")
                resize_screenshot_to_limit("captcha.png", 600)
                captcha_code = ask_ollama_to_solve_captcha("captcha.png")
        except Exception as e:
            print(f"CAPTCHA error: {e}")

        if captcha_code:
            page.locator("input[name*='captcha'], input[id*='captcha']").fill(captcha_code)

        page.locator("input[type='submit'], button[type='submit']").click(force=True)
        page.wait_for_load_state("domcontentloaded")

        page.screenshot(path="success_login.png")
        resize_screenshot_to_limit("success_login.png", 600)

        logged_in_indicator = page.locator("a:has-text('Logout'), a:has-text('Log Keluar'), .user-avatar, .dashboard")
        if logged_in_indicator.count() > 0 or "home" not in page.url:
            print("Login successful! Executing automation workflow...")
            navigate_to_e_application(page)
            navigate_to_evcs_application(page)
            process_bahagian_sections_with_data(page, payload)
        else:
            print("Login indicator warning encountered.")

        browser.close()

if __name__ == "__main__":
    login_oas()

import os
import time
import json
import requests
from PIL import Image
from playwright.sync_api import sync_playwright

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

def fetch_latest_submission_from_sheets():
    """Fetches the latest application submission row from Google Sheets for background auto-fill."""
    print("Fetching latest submission from Google Sheets...")
    creds_json = os.environ.get("GOOGLE_CREDENTIALS_JSON")
    if not creds_json:
        print("GOOGLE_CREDENTIALS_JSON environment variable not set. Running with default dummy data.")
        return get_dummy_application_data()
    
    try:
        from google.oauth2 import service_account
        SCOPES = ['https://www.googleapis.com/auth/spreadsheets.readonly', 'https://www.googleapis.com/auth/drive.readonly']
        creds_dict = json.loads(creds_json)
        creds = service_account.Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
        
        drive_service = build('drive', 'v3', credentials=creds)
        sheets_service = build('sheets', 'v4', credentials=creds)
        
        FOLDER_ID = "1edCJklkyUp4UtZl3zOh-HNsYOMmw8hsc"
        query = f"'{FOLDER_ID}' in parents and name = 'general_applications' and mimeType = 'application/vnd.google-apps.spreadsheet'"
        response = drive_service.files().list(q=query, fields="files(id, name)").execute()
        files = response.get("files", [])
        
        if not files:
            print("General applications sheet not found in Drive. Using fallback dummy data.")
            return get_dummy_application_data()
            
        sheet_id = files[0]["id"]
        result = sheets_service.spreadsheets().values().get(spreadsheetId=sheet_id, range="A:AD").execute()
        rows = result.get("values", [])
        
        if len(rows) <= 1:
            print("No data rows found in spreadsheet. Using fallback dummy data.")
            return get_dummy_application_data()
            
        header = rows[0]
        latest_row = rows[-1]  # Get the most recent submission
        
        app_data = dict(zip(header, latest_row))
        print(f"Successfully loaded submission for project: {app_data.get('Project Name')}")
        return app_data
    except Exception as e:
        print(f"Error fetching from Google Sheets: {e}. Using fallback dummy data.")
        return get_dummy_application_data()

def get_dummy_application_data():
    return {
        "Project Name": "Sample EVCS Project Nilai",
        "Negeri": "Negeri Sembilan",
        "PBT": "Nilai Municipal Council",
        "Poskod": "71800",
        "Daerah": "Seremban",
        "Mukim": "Labu",
        "Kawasan": "Bandar Baru Nilai",
        "Taman / Tempat": "Taman Scientex",
        "Jalan": "Persiaran Utama",
        "No. Lot / No. Unit / Blok / PT": "Lot 1234",
        "Hak Milik Bangunan": "MILIK SENDIRI",
        "Kedudukan Premis": "LOT TEPI",
        "Brand / Model": "Guorui / GRD08-120SDE",
        "No. of Units": "2",
        "Rated Input Power (kW AC)": "133 kW AC",
        "Max. Charging Power": "120 kW / DC",
        "Mode of Charging": "Mode 4",
        "Connector Type": "CCS 2",
        "Output Cable Size": "CSS2-5M-250A",
        "No. of Charging Bays": "4",
        "GPS Latitude": "2.800693, 101.686073"
    }

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
    print("Sending CAPTCHA image to lightweight Ollama vision model (moondream)...")
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
            print(f"Ollama successfully read CAPTCHA: '{clean_text}'")
            return clean_text
    except Exception as e:
        print(f"Failed to connect to local Ollama: {e}")
    return ""

def get_base64_image(image_path):
    import base64
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')

def navigate_to_e_application(page):
    print("Searching for e-Application...")
    try:
        e_app_element = page.locator("a:has-text('e-Application')").first
        e_app_element.wait_for(state="visible", timeout=10000)
        e_app_element.click(force=True)
        page.wait_for_load_state("domcontentloaded")
        page.screenshot(path="e-application.png")
        resize_screenshot_to_limit("e-application.png", 600)
        print("Saved e-application.png successfully.")
    except Exception as e:
        print(f"Error navigating to e-Application: {e}")

def navigate_to_evcs_application(page):
    print("Searching for LE2EVCS link...")
    link_text = "LE2EVCS - Lesen Awam Pengagihan EV Charging Station"
    try:
        evcs_link = page.locator(f"a:has-text('{link_text}')").first
        evcs_link.wait_for(state="visible", timeout=10000)
        evcs_link.click(force=True)
        page.wait_for_load_state("domcontentloaded")
        page.screenshot(path=f"Click_{link_text}.png")
        resize_screenshot_to_limit(f"Click_{link_text}.png", 600)
        print("Clicked LE2EVCS link successfully.")
    except Exception as e:
        print(f"Error clicking LE2EVCS link: {e}")

def search_after_hantar(page):
    print("Searching for 'Hantar' button/element...")
    try:
        hantar_element = page.locator("button:has-text('Hantar'), input[type='submit'][value*='Hantar'], a:has-text('Hantar')").first
        hantar_element.wait_for(state="visible", timeout=10000)
        page.screenshot(path="before_hantar.png")
        resize_screenshot_to_limit("before_hantar.png", 600)
        hantar_element.click(force=True)
        page.wait_for_load_state("domcontentloaded")
        page.screenshot(path="after_hantar.png")
        resize_screenshot_to_limit("after_hantar.png", 600)
        print("Clicked 'Hantar' successfully.")
    except Exception as e:
        print(f"Error clicking 'Hantar': {e}")

def fill_field(page, selectors, value):
    """Helper function to fill text inputs safely."""
    if not value:
        return
    for selector in selectors:
        try:
            loc = page.locator(selector).first
            if loc.count() > 0 and loc.is_visible():
                loc.fill(value)
                print(f"Filled '{value}' into selector '{selector}'")
                return
        except Exception:
            continue

def select_option(page, selectors, value):
    """Helper function to select dropdown options safely."""
    if not value:
        return
    for selector in selectors:
        try:
            loc = page.locator(selector).first
            if loc.count() > 0 and loc.is_visible():
                loc.select_option(label=value)
                print(f"Selected option '{value}' in '{selector}'")
                return
        except Exception:
            continue

def process_bahagian_sections(page, app_data):
    """Fills the OAS portal fields dynamically from Bahagian A to Bahagian G using data fetched from Google Sheets."""
    sections = ['Bahagian A', 'Bahagian B', 'Bahagian C', 'Bahagian D', 'Bahagian E', 'Bahagian F', 'Bahagian G']
    
    for section in sections:
        print(f"Processing {section} and filling data...")
        try:
            tab_element = page.locator(f"a:has-text('{section}'), button:has-text('{section}'), td:has-text('{section}')").first
            if tab_element.count() > 0 and tab_element.is_visible():
                tab_element.click(force=True)
            page.wait_for_load_state("domcontentloaded")
            time.sleep(2)
            
            # --- Auto-fill logic per Bahagian ---
            if section == 'Bahagian A':
                fill_field(page, ["input[name*='nama_projek']", "input[name*='project']", "input[placeholder*='Project']"], app_data.get("Project Name"))

            elif section == 'Bahagian B':
                fill_field(page, ["input[name*='jumlah_keupayaan']", "input[name*='capacity']"], app_data.get("Rated Input Power (kW AC)"))
                fill_field(page, ["input[name*='kehendak_max']", "input[name*='max_demand']"], app_data.get("Max. Charging Power"))

            elif section == 'Bahagian C':
                print("Checking Bahagian C checklist requirements...")

            elif section == 'Bahagian E':
                fill_field(page, ["input[name*='lot']", "input[id*='lot']"], app_data.get("No. Lot / No. Unit / Blok / PT"))
                fill_field(page, ["input[name*='poskod']"], app_data.get("Poskod"))
                fill_field(page, ["input[name*='daerah']"], app_data.get("Daerah"))
                fill_field(page, ["input[name*='mukim']"], app_data.get("Mukim"))
                fill_field(page, ["input[name*='kawasan']"], app_data.get("Kawasan"))
                fill_field(page, ["input[name*='taman']"], app_data.get("Taman / Tempat"))
                fill_field(page, ["input[name*='jalan']"], app_data.get("Jalan"))
                select_option(page, ["select[name*='negeri']"], app_data.get("Negeri"))

            elif section == 'Bahagian F':
                # Accept declaration checkboxes
                checkboxes = page.locator("input[type='checkbox']")
                for idx in range(checkboxes.count()):
                    try:
                        checkboxes.nth(idx).check(force=True)
                    except Exception:
                        pass

            elif section == 'Bahagian G':
                time.sleep(2)
                try:
                    simpan_draf_btn = page.locator("input[value*='Simpan Draf'], button:has-text('Simpan Draf')").first
                    simpan_draf_btn.wait_for(state="visible", timeout=10000)
                    simpan_draf_btn.click(force=True)
                    page.wait_for_load_state("domcontentloaded")
                    print("Saved Bahagian G Simpan Draf successfully.")
                except Exception as ex_draft:
                    print(f"Simpan Draf action note: {ex_draft}")

            safe_name = section.replace(" ", "_").lower()
            screenshot_filename = f"{safe_name}.png"
            page.screenshot(path=screenshot_filename)
            resize_screenshot_to_limit(screenshot_filename, 600)
            print(f"Saved {screenshot_filename} successfully.")

        except Exception as e:
            print(f"Error processing {section}: {e}")

def upload_files(page):
    print("Ready to upload files...")

def login_oas():
    email = os.environ.get("OAS_EMAIL")
    password = os.environ.get("OAS_PASSWORD")

    if not email or not password:
        raise ValueError("OAS_EMAIL and OAS_PASSWORD environment variables must be set.")

    # Fetch latest Streamlit form submission from Google Sheets
    app_data = fetch_latest_submission_from_sheets()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
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
        except Exception as e:
            print(f"Popup removal note: {e}")

        print("Filling Email Address and Password...")
        page.get_by_text("Email Address", exact=False).locator("..").locator("input").fill(email)
        page.get_by_text("Password", exact=True).locator("..").locator("input").fill(password)
        
        captcha_code = ""
        try:
            captcha_img = page.locator("form img, fieldset img, img[src*='captcha'], img[src*='Captcha']").first
            if captcha_img.count() > 0 and captcha_img.is_visible():
                captcha_img.screenshot(path="captcha.png")
            else:
                page.screenshot(path="captcha.png")
            resize_screenshot_to_limit("captcha.png", 600)

            if os.path.exists("captcha.png"):
                captcha_code = ask_ollama_to_solve_captcha("captcha.png")
        except Exception as e:
            print(f"CAPTCHA error: {e}")

        if captcha_code:
            verification_input = page.locator("input[name*='captcha'], input[id*='captcha'], input[placeholder*='Verification']")
            verification_input.fill(captcha_code)

        print("Clicking Sign In...")
        submit_button = page.locator("input[type='submit'], button[type='submit']")
        submit_button.click(force=True)
        page.wait_for_load_state("domcontentloaded")

        page.screenshot(path="success_login.png")
        resize_screenshot_to_limit("success_login.png", 600)

        logged_in_indicator = page.locator("a:has-text('Logout'), a:has-text('Log Keluar'), .user-avatar, .dashboard")
        if logged_in_indicator.count() > 0 or "home" not in page.url:
            print("VERIFICATION SUCCESSFUL: Login completed!")
            navigate_to_e_application(page)
            navigate_to_evcs_application(page)
            search_after_hantar(page)
            process_bahagian_sections(page, app_data)
            upload_files(page)
        else:
            print("VERIFICATION WARNING: Could not explicitly confirm login element.")

        browser.close()

if __name__ == "__main__":
    login_oas()

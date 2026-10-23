import os
import time
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

        print(f"Successfully compressed {image_path} to {os.path.getsize(image_path) / 1024:.2f}KB")
    except Exception as e:
        print(f"Error compressing screenshot {image_path}: {e}")

def login_mpsepang():
    user_id = os.environ.get("MPSEPANG_USER")
    password = os.environ.get("MPSEPANG_PASSWORD")

    if not user_id or not password:
        raise ValueError("MPSEPANG_USER and MPSEPANG_PASSWORD environment variables must be set.")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()

        print("Navigating to MP Sepang login page...")
        page.goto("https://ekl.mpsepang.gov.my/sso/Default.aspx", timeout=60000)

        # 1. Fill No Kad Pengenalan / Passport and Katalaluan directly using input types
        print("Filling No Kad Pengenalan / Passport and Katalaluan...")
        page.locator("input[type='text']").first.fill(user_id)
        page.locator("input[type='password']").first.fill(password)

        # 2. Click LOG MASUK button
        print("Clicking 'LOG MASUK'...")
        login_btn = page.locator("button:has-text('LOG MASUK'), input[value*='LOG MASUK'], input[type='submit'], a:has-text('LOG MASUK')").first
        login_btn.click(force=True)

        page.wait_for_load_state("domcontentloaded")
        
        # Buffer time after login
        print("Buffer active: waiting for post-login session initialization...")
        time.sleep(3)

        # 3. Remove popup notification via full XPath /html/body/form/div[4]
        try:
            print("Removing popup notification element via XPath...")
            xpath_popup = "/html/body/form/div[4]"
            page.evaluate(f"""
                const element = document.evaluate("{xpath_popup}", document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue;
                if (element) {{
                    element.remove();
                    console.log("Popup element successfully removed.");
                }}
            """)
        except Exception as e:
            print(f"Error removing popup element: {e}")

        # Take screenshot after login verification
        page.screenshot(path="success_login.png")
        resize_screenshot_to_limit("success_login.png", 600)
        print("Saved success_login.png successfully.")

        # 4. Search and click 'eLesen Baharu'
        print("Searching for 'eLesen Baharu'...")
        try:
            elesen_link = page.locator("a:has-text('eLesen Baharu'), button:has-text('eLesen Baharu')").first
            elesen_link.wait_for(state="visible", timeout=10000)
            elesen_link.click(force=True)
            print("Clicked 'eLesen Baharu' successfully.")
            page.wait_for_load_state("domcontentloaded")
            time.sleep(2)
        except Exception as e:
            print(f"Error clicking 'eLesen Baharu': {e}")

        # 5. Search and click 'Permohonan Baru'
        print("Searching for 'Permohonan Baru'...")
        try:
            permohonan_link = page.locator("a:has-text('Permohonan Baru'), button:has-text('Permohonan Baru')").first
            permohonan_link.wait_for(state="visible", timeout=10000)
            permohonan_link.click(force=True)
            print("Clicked 'Permohonan Baru' successfully.")
            page.wait_for_load_state("domcontentloaded")
            time.sleep(2)

            page.screenshot(path="permohonan_baru.png")
            resize_screenshot_to_limit("permohonan_baru.png", 600)
            print("Saved permohonan_baru.png successfully.")
        except Exception as e:
            print(f"Error clicking 'Permohonan Baru': {e}")

        browser.close()

if __name__ == "__main__":
    login_mpsepang()

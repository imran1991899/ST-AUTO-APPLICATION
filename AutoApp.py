import streamlit as st
import pandas as pd
from datetime import datetime
from io import BytesIO
import json
import mimetypes
import time
import os
import pickle
from urllib.parse import urlencode
from PIL import Image

from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

# Malaysia timezone setup
try:
    from zoneinfo import ZoneInfo
    MALAYSIA_ZONE = ZoneInfo("Asia/Kuala_Lumpur")
except ImportError:
    import pytz
    MALAYSIA_ZONE = pytz.timezone("Asia/Kuala_Lumpur")

# --------- Page Setup ---------
st.set_page_config(page_title="Application Portal", layout="wide")

# --------- Custom CSS for Border Cards around Images & Stepper Buttons ---------
st.markdown("""
<style>
.evc-card {
    border: 2px solid #008080;
    border-radius: 10px;
    padding: 10px;
    text-align: center;
    background-color: #0e1117;
    margin-bottom: 10px;
}
[data-testid="stVerticalBlock"] [data-testid="stContainer"] {
    border: 2px solid #008080 !important;
    border-radius: 10px !important;
    background-color: #0e1117 !important;
    padding: 10px !important;
}
</style>
""", unsafe_allow_html=True)

# --------- Google Drive Folder ID ---------
FOLDER_ID = "1edCJklkyUp4UtZl3zOh-HNsYOMmw8hsc"

# --------- OAuth Setup ---------
SCOPES = [
    'https://www.googleapis.com/auth/drive.file',
    'https://www.googleapis.com/auth/spreadsheets'
]

CLIENT_SECRETS_FILE = 'client_secrets.json'
REDIRECT_URI = 'https://st-auto-application-np4xyno3ptrqqq7ebjgpjy.streamlit.app/'

def save_credentials(credentials):
    with open('token.pickle', 'wb') as token:
        pickle.dump(credentials, token)

def load_credentials():
    if os.path.exists('token.pickle'):
        with open('token.pickle', 'rb') as token:
            return pickle.load(token)
    return None

def get_authenticated_service():
    creds = load_credentials()
    
    # 1. Valid credentials exist
    if creds and creds.valid:
        return build('drive', 'v3', credentials=creds), build('sheets', 'v4', credentials=creds)

    # 2. Expired but refreshable
    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            save_credentials(creds)
            return build('drive', 'v3', credentials=creds), build('sheets', 'v4', credentials=creds)
        except Exception:
            pass

    # 3. Handle OAuth Handshake
    if os.path.exists(CLIENT_SECRETS_FILE):
        flow = Flow.from_client_secrets_file(CLIENT_SECRETS_FILE, scopes=SCOPES, redirect_uri=REDIRECT_URI)
    else:
        # Fallback to Streamlit secrets if client_secrets.json is not present locally
        client_config = {
            "installed": {
                "client_id": st.secrets["installed"]["client_id"],
                "project_id": st.secrets["installed"]["project_id"],
                "auth_uri": st.secrets["installed"]["auth_uri"],
                "token_uri": st.secrets["installed"]["token_uri"],
                "auth_provider_x509_cert_url": st.secrets["installed"]["auth_provider_x509_cert_url"],
                "client_secret": st.secrets["installed"]["client_secret"],
                "redirect_uris": [REDIRECT_URI]
            }
        }
        flow = Flow.from_client_config(client_config, scopes=SCOPES, redirect_uri=REDIRECT_URI)
    
    query_params = st.query_params

    if "code" in query_params:
        if os.path.exists("verifier.tmp"):
            with open("verifier.tmp", "r") as f:
                flow.code_verifier = f.read()
            try:
                full_url = REDIRECT_URI + "?" + urlencode(query_params)
                flow.fetch_token(authorization_response=full_url)
                save_credentials(flow.credentials)
                
                if os.path.exists("verifier.tmp"):
                    os.remove("verifier.tmp")
                
                st.query_params.clear()
                st.rerun()
            except Exception as e:
                st.error(f"Handshake failed: {e}")
                st.stop()
        else:
            st.warning("Session verifier lost. Restarting login...")
            time.sleep(2)
            st.query_params.clear()
            st.rerun()
    else:
        auth_url, _ = flow.authorization_url(prompt='consent', access_type="offline", include_granted_scopes="true")
        with open("verifier.tmp", "w") as f:
            f.write(flow.code_verifier)
        
        st.markdown(f"### Authentication Required\n[🔴 Click Here to Login with Google]({auth_url})")
        st.stop()

# --------- Google API Helper Functions ---------
drive_service, sheets_service = get_authenticated_service()

def get_or_create_project_folder(project_title, parent_folder_id):
    """Finds or creates a Google Drive subfolder named after the Project Title inside iGREEN AUTO ASSETS folder."""
    clean_title = "".join([c for c in project_title if c.isalnum() or c in (' ', '_', '-')]).strip()
    if not clean_title:
        clean_title = "Untitled_Project"
    
    query = f"'{parent_folder_id}' in parents and name = '{clean_title}' and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
    response = drive_service.files().list(
        q=query,
        fields="files(id, name)",
        includeItemsFromAllDrives=True,
        supportsAllDrives=True
    ).execute()
    
    files = response.get("files", [])
    if files:
        return files[0]["id"]
    
    folder_metadata = {
        "name": clean_title,
        "mimeType": "application/vnd.google-apps.folder",
        "parents": [parent_folder_id]
    }
    folder = drive_service.files().create(
        body=folder_metadata,
        fields="id",
        supportsAllDrives=True
    ).execute()
    return folder.get("id")

def compress_file_if_needed(file_bytes, filename, max_size_mb=2.0):
    """Automatically compresses images if file size exceeds max_size_mb (default 2MB)."""
    max_bytes = max_size_mb * 1024 * 1024
    if len(file_bytes) <= max_bytes:
        return file_bytes, filename

    ext = os.path.splitext(filename)[1].lower()
    if ext in ['.png', '.jpg', '.jpeg']:
        try:
            img = Image.open(BytesIO(file_bytes))
            if img.mode in ("RGBA", "P"):
                img = img.convert("RGB")
            
            quality = 85
            output = BytesIO()
            img.save(output, format="JPEG", quality=quality, optimize=True)
            compressed_bytes = output.getvalue()
            
            # Reduce quality further if needed
            while len(compressed_bytes) > max_bytes and quality > 20:
                quality -= 15
                output = BytesIO()
                img.save(output, format="JPEG", quality=quality, optimize=True)
                compressed_bytes = output.getvalue()
            
            # Resize image if still over limit
            if len(compressed_bytes) > max_bytes:
                img.thumbnail((img.width // 2, img.height // 2))
                output = BytesIO()
                img.save(output, format="JPEG", quality=30, optimize=True)
                compressed_bytes = output.getvalue()
                
            new_filename = os.path.splitext(filename)[0] + ".jpg"
            return compressed_bytes, new_filename
        except Exception:
            return file_bytes, filename
    return file_bytes, filename

def gdrive_upload_file(file_bytes, filename, mimetype, folder_id=None):
    file_bytes, filename = compress_file_if_needed(file_bytes, filename, max_size_mb=2.0)
    mimetype = mimetypes.guess_type(filename)[0] or 'application/octet-stream'
    
    media = MediaIoBaseUpload(BytesIO(file_bytes), mimetype)
    file_metadata = {"name": filename}
    if folder_id:
        file_metadata["parents"] = [folder_id]
    uploaded = drive_service.files().create(
        body=file_metadata,
        media_body=media,
        fields="id, webViewLink",
        supportsAllDrives=True,
    ).execute()
    return uploaded.get("webViewLink"), uploaded.get("id")

def find_or_create_gsheet(sheet_name, folder_id=None):
    if folder_id:
        query = (f"'{folder_id}' in parents and name = '{sheet_name}' and "
                 "mimeType = 'application/vnd.google-apps.spreadsheet'")
    else:
        query = (f"name = '{sheet_name}' and "
                 "mimeType = 'application/vnd.google-apps.spreadsheet'")
    response = drive_service.files().list(
        q=query,
        fields="files(id, name)",
        includeItemsFromAllDrives=True,
        supportsAllDrives=True,
    ).execute()

    files = response.get("files", [])
    if files:
        return files[0]["id"]

    file_metadata = {
        "name": sheet_name,
        "mimeType": "application/vnd.google-apps.spreadsheet",
    }
    if folder_id:
        file_metadata["parents"] = [folder_id]

    file = drive_service.files().create(
        body=file_metadata,
        fields="id",
        supportsAllDrives=True,
    ).execute()
    return file["id"]

def append_row_to_gsheet(sheet_id, values, header):
    sheet = sheets_service.spreadsheets()
    result = sheet.values().get(spreadsheetId=sheet_id, range="A1:A1").execute()
    if "values" not in result:
        sheet.values().update(
            spreadsheetId=sheet_id,
            range="A1",
            valueInputOption="RAW",
            body={"values": [header]},
        ).execute()
        row_num = 2
    else:
        row_values = sheet.values().get(spreadsheetId=sheet_id, range="A:A").execute().get("values", [])
        row_num = len(row_values) + 1

    sheet.values().append(
        spreadsheetId=sheet_id,
        range=f"A{row_num}",
        valueInputOption="RAW",
        insertDataOption="INSERT_ROWS",
        body={"values": [values]},
    ).execute()

# --------- Initialize Session State ---------
defaults = {
    "app_mode": "none",
    "project_title": "",
    "location": "",
    "total_bay": "",
    "total_evcs": "",
    "evcs_type": "AC",
    "brand_model": "",
    "no_of_units": "",
    "rated_input_power": "",
    "max_charging_power": "",
    "mode_of_charging": "",
    "connector_type": "",
    "output_cable_size": "",
    "no_of_charging_bays": "",
    "gps_lat": "",
    "gps_lon": "",
    "description": "",
    "tarikh_mulatugas_count": 1,
}

for key, default in defaults.items():
    if key not in st.session_state:
        st.session_state[key] = default

# --------- Navigation / Sidebar Setup ---------
st.sidebar.title("Navigation Menu")
nav_selection = st.sidebar.radio(
    "Go to",
    ["1. Main Page", "2. Detail Application", "3. Information"]
)

# --------- 1. MAIN PAGE ---------
if nav_selection == "1. Main Page":
    st.title("Application Portal")
    
    col1, col2 = st.columns(2)
    with col1:
        if st.button("🆕 New Application", use_container_width=True):
            st.session_state.app_mode = "new"
    with col2:
        if st.button("📂 Existing Application", use_container_width=True):
            st.session_state.app_mode = "existing"

    st.markdown("---")

    # ----- NEW APPLICATION FORM -----
    if st.session_state.app_mode == "new":
        st.subheader("📝 New Application Submission")

        project_title = st.text_input("📋 Project / Request Title", value=st.session_state.project_title)
        st.session_state.project_title = project_title

        location = st.text_input("📍 Location", value=st.session_state.location)
        st.session_state.location = location

        col_ev1, col_ev2 = st.columns(2)
        with col_ev1:
            total_bay = st.text_input("🅿️ Total Bay", value=st.session_state.total_bay)
            st.session_state.total_bay = total_bay
        with col_ev2:
            total_evcs = st.text_input("🔌 Total No. EVCS", value=st.session_state.total_evcs)
            st.session_state.total_evcs = total_evcs

        evcs_types = ["AC", "DC", "AC & DC Hybrid"]
        evcs_type = st.selectbox(
            "⚡ EVCS TYPE",
            evcs_types,
            index=evcs_types.index(st.session_state.evcs_type) if st.session_state.evcs_type in evcs_types else 0
        )
        st.session_state.evcs_type = evcs_type

        # --- Side-by-Side EVCS Technical Specifications ---
        st.markdown("---")
        st.markdown("#### ⚡ EVCS Technical Specifications")

        def select_model_120():
            st.session_state.brand_model = "Guorui / GRD08-120SDE"
            st.session_state.max_charging_power = "120 kW / DC"
            st.session_state.rated_input_power = "133 kW AC"
            st.session_state.mode_of_charging = "Mode 4"
            st.session_state.connector_type = "CCS 2"

        def select_model_240():
            st.session_state.brand_model = "Guorui / GRD08-240SDE"
            st.session_state.max_charging_power = "240 kW / DC"
            st.session_state.rated_input_power = "266 kW AC"
            st.session_state.mode_of_charging = "Mode 4"
            st.session_state.connector_type = "CCS 2"

        def select_model_add():
            st.session_state.brand_model = ""
            st.session_state.max_charging_power = ""
            st.session_state.rated_input_power = ""
            st.session_state.mode_of_charging = ""
            st.session_state.connector_type = ""

        col_img1, col_img2, col_img3 = st.columns(3)

        with col_img1:
            with st.container(border=True):
                ic1, ic2, ic3 = st.columns([1, 2, 1])
                with ic2:
                    if os.path.exists("imgEVC/DC_120.png"):
                        st.image("imgEVC/DC_120.png", width=90)
                    else:
                        st.warning("imgEVC/DC_120.png not found")
                if st.button("Guorui / GRD08-120SDE", use_container_width=True, key="btn_120"):
                    select_model_120()
                    st.rerun()

        with col_img2:
            with st.container(border=True):
                ic1, ic2, ic3 = st.columns([1, 2, 1])
                with ic2:
                    if os.path.exists("imgEVC/DC_240.png"):
                        st.image("imgEVC/DC_240.png", width=90)
                    else:
                        st.warning("imgEVC/DC_240.png not found")
                if st.button("Guorui / GRD08-240SDE", use_container_width=True, key="btn_240"):
                    select_model_240()
                    st.rerun()

        with col_img3:
            with st.container(border=True):
                ic1, ic2, ic3 = st.columns([1, 2, 1])
                with ic2:
                    if os.path.exists("imgEVC/add.png"):
                        st.image("imgEVC/add.png", width=90)
                    else:
                        st.warning("imgEVC/add.png not found")
                if st.button("+ Add Other Model", use_container_width=True, key="btn_add"):
                    select_model_add()
                    st.rerun()

        st.markdown("---")

        col_s1, col_s2 = st.columns(2)

        with col_s1:
            brand_model = st.text_input("Brand / Model", value=st.session_state.brand_model)
            st.markdown("<p style='color: gray; font-size: 0.85rem; margin-top: -15px;'>Example: Guorui / GRD08-120SDE</p>", unsafe_allow_html=True)

            # Rated Input Power with stepper buttons [-] [+]
            col_rip_in, col_rip_btn = st.columns([4, 1])
            with col_rip_in:
                rated_input_power = st.text_input("Rated Input Power (kW AC)", value=st.session_state.rated_input_power, key="input_rated_input_power")
                st.markdown("<p style='color: gray; font-size: 0.85rem; margin-top: -15px;'>Example: 133 kW AC</p>", unsafe_allow_html=True)
                st.session_state.rated_input_power = rated_input_power
            with col_rip_btn:
                st.markdown("<br>", unsafe_allow_html=True)
                b_m1, b_p1 = st.columns(2)
                with b_m1:
                    if st.button("-", key="minus_rip"):
                        import re
                        nums = re.findall(r'\d+', st.session_state.rated_input_power)
                        if nums:
                            val = max(0, int(nums[0]) - 1)
                            st.session_state.rated_input_power = st.session_state.rated_input_power.replace(nums[0], str(val), 1)
                            st.rerun()
                with b_p1:
                    if st.button("+", key="plus_rip"):
                        import re
                        nums = re.findall(r'\d+', st.session_state.rated_input_power)
                        if nums:
                            val = int(nums[0]) + 1
                            st.session_state.rated_input_power = st.session_state.rated_input_power.replace(nums[0], str(val), 1)
                        else:
                            st.session_state.rated_input_power = "1"
                        st.rerun()

            mode_of_charging = st.text_input("Mode of Charging", value=st.session_state.mode_of_charging)
            st.markdown("<p style='color: gray; font-size: 0.85rem; margin-top: -15px;'>Example: Mode 4</p>", unsafe_allow_html=True)

            output_cable_size = st.text_input("Output Cable Size / Type (Charging Cable)", value=st.session_state.output_cable_size)
            st.markdown("<p style='color: gray; font-size: 0.85rem; margin-top: -15px;'>Example: CSS2-5M-250A cable size 2 × 70 mm²+25mm²</p>", unsafe_allow_html=True)

            # GPS Coordinate Latitude & Longitude with Interactive Map Picker Dialog
            st.markdown("GPS Coordinate Latitude Longitude")
            col_gps_in, col_gps_btn = st.columns([4, 1])
            with col_gps_in:
                gps_lat = st.text_input("Latitude", value=st.session_state.gps_lat, key="input_gps_lat", placeholder="2.800693")
                st.session_state.gps_lat = gps_lat
            with col_gps_btn:
                st.markdown("<br>", unsafe_allow_html=True)
                @st.dialog("🗺️ Select Location on Map")
                def gps_map_dialog():
                    st.markdown("Click on the map to pin a location and automatically save coordinates:", unsafe_allow_html=True)
                    try:
                        import folium
                        from streamlit_folium import st_folium
                        
                        try:
                            init_lat = float(st.session_state.get("gps_lat", "2.800693") or 2.800693)
                        except:
                            init_lat = 2.800693
                        try:
                            init_lon = float(st.session_state.get("gps_lon", "101.686073") or 101.686073)
                        except:
                            init_lon = 101.686073

                        m = folium.Map(location=[init_lat, init_lon], zoom_start=13)
                        folium.Marker([init_lat, init_lon], popup="Selected Location", tooltip="Pinned Location").add_to(m)
                        m.add_child(folium.LatLngPopup())
                        
                        map_data = st_folium(m, width=500, height=350, key="map_popup_interactive")
                        
                        if map_data and map_data.get("last_clicked"):
                            clicked_lat = map_data["last_clicked"]["lat"]
                            clicked_lon = map_data["last_clicked"]["lng"]
                            st.session_state.gps_lat = str(clicked_lat)
                            st.session_state.gps_lon = str(clicked_lon)
                            st.success(f"Saved Latitude: {clicked_lat}, Longitude: {clicked_lon}")
                            time.sleep(0.5)
                            st.rerun()
                    except Exception as e:
                        st.warning(f"Interactive map requires folium and streamlit-folium. Error: {e}")
                        dlg_lat = st.text_input("Latitude", value=st.session_state.get("gps_lat", "2.800693"))
                        dlg_lon = st.text_input("Longitude", value=st.session_state.get("gps_lon", "101.686073"))
                        if st.button("✅ Save Coordinates", use_container_width=True):
                            st.session_state.gps_lat = dlg_lat
                            st.session_state.gps_lon = dlg_lon
                            st.success("Coordinates saved!")
                            time.sleep(0.5)
                            st.rerun()

                    if st.button("✅ Close / Done", use_container_width=True):
                        st.rerun()

                if st.button("🗺️ Map", key="btn_open_map"):
                    gps_map_dialog()
            st.markdown("<p style='color: gray; font-size: 0.85rem; margin-top: -15px;'>Example: 2.800693</p>", unsafe_allow_html=True)

        with col_s2:
            # No. of Units with stepper buttons [-] [+]
            col_nou_in, col_nou_btn = st.columns([4, 1])
            with col_nou_in:
                no_of_units = st.text_input("No. of Units", value=st.session_state.no_of_units, key="input_no_of_units")
                st.markdown("<p style='color: gray; font-size: 0.85rem; margin-top: -15px;'>Example: 2</p>", unsafe_allow_html=True)
                st.session_state.no_of_units = no_of_units
            with col_nou_btn:
                st.markdown("<br>", unsafe_allow_html=True)
                b_m2, b_p2 = st.columns(2)
                with b_m2:
                    if st.button("-", key="minus_nou"):
                        import re
                        nums = re.findall(r'\d+', st.session_state.no_of_units)
                        if nums:
                            val = max(0, int(nums[0]) - 1)
                            st.session_state.no_of_units = st.session_state.no_of_units.replace(nums[0], str(val), 1)
                            st.rerun()
                with b_p2:
                    if st.button("+", key="plus_nou"):
                        import re
                        nums = re.findall(r'\d+', st.session_state.no_of_units)
                        if nums:
                            val = int(nums[0]) + 1
                            st.session_state.no_of_units = st.session_state.no_of_units.replace(nums[0], str(val), 1)
                        else:
                            st.session_state.no_of_units = "1"
                        st.rerun()

            # Max. Charging / Output Power with stepper buttons [-] [+]
            col_mcp_in, col_mcp_btn = st.columns([4, 1])
            with col_mcp_in:
                max_charging_power = st.text_input("Max. Charging / Output Power (AC or DC)", value=st.session_state.max_charging_power, key="input_max_charging_power")
                st.markdown("<p style='color: gray; font-size: 0.85rem; margin-top: -15px;'>Example: 120 kW / DC</p>", unsafe_allow_html=True)
                st.session_state.max_charging_power = max_charging_power
            with col_mcp_btn:
                st.markdown("<br>", unsafe_allow_html=True)
                b_m3, b_p3 = st.columns(2)
                with b_m3:
                    if st.button("-", key="minus_mcp"):
                        import re
                        nums = re.findall(r'\d+', st.session_state.max_charging_power)
                        if nums:
                            val = max(0, int(nums[0]) - 1)
                            st.session_state.max_charging_power = st.session_state.max_charging_power.replace(nums[0], str(val), 1)
                            st.rerun()
                with b_p3:
                    if st.button("+", key="plus_mcp"):
                        import re
                        nums = re.findall(r'\d+', st.session_state.max_charging_power)
                        if nums:
                            val = int(nums[0]) + 1
                            st.session_state.max_charging_power = st.session_state.max_charging_power.replace(nums[0], str(val), 1)
                        else:
                            st.session_state.max_charging_power = "1"
                        st.rerun()

            connector_type = st.text_input("Connector Type", value=st.session_state.connector_type)
            st.markdown("<p style='color: gray; font-size: 0.85rem; margin-top: 15px;'>Example: 8 × CCS 2</p>", unsafe_allow_html=True)

            # No. of Charging Bays with stepper buttons [-] [+]
            col_nocb_in, col_nocb_btn = st.columns([4, 1])
            with col_nocb_in:
                no_of_charging_bays = st.text_input("No. of Charging Bays", value=st.session_state.no_of_charging_bays, key="input_no_of_charging_bays")
                st.markdown("<p style='color: gray; font-size: 0.85rem; margin-top: -15px;'>Example: 10</p>", unsafe_allow_html=True)
                st.session_state.no_of_charging_bays = no_of_charging_bays
            with col_nocb_btn:
                st.markdown("<br>", unsafe_allow_html=True)
                b_m4, b_p4 = st.columns(2)
                with b_m4:
                    if st.button("-", key="minus_nocb"):
                        import re
                        nums = re.findall(r'\d+', st.session_state.no_of_charging_bays)
                        if nums:
                            val = max(0, int(nums[0]) - 1)
                            st.session_state.no_of_charging_bays = st.session_state.no_of_charging_bays.replace(nums[0], str(val), 1)
                            st.rerun()
                with b_p4:
                    if st.button("+", key="plus_nocb"):
                        import re
                        nums = re.findall(r'\d+', st.session_state.no_of_charging_bays)
                        if nums:
                            val = int(nums[0]) + 1
                            st.session_state.no_of_charging_bays = st.session_state.no_of_charging_bays.replace(nums[0], str(val), 1)
                        else:
                            st.session_state.no_of_charging_bays = "1"
                        st.rerun()

            gps_lon = st.text_input("GPS Coordinate Longitude", value=st.session_state.gps_lon)
            st.markdown("<p style='color: gray; font-size: 0.85rem; margin-top: -15px;'>Example: 101.686073</p>", unsafe_allow_html=True)

        st.markdown("---")

        description = st.text_area("📄 Project Description & Objectives", value=st.session_state.description, height=150)
        st.session_state.description = description

        st.markdown("---")
        st.subheader("📋 Application Sections (Bahagian A - G)")

        tab_a, tab_b, tab_c, tab_d, tab_e, tab_f, tab_g = st.tabs([
            "Bahagian A", 
            "Bahagian B", 
            "Bahagian C", 
            "Bahagian D", 
            "Bahagian E", 
            "Bahagian F", 
            "Bahagian G"
        ])

        # BAHAGIAN A
        with tab_a:
            st.markdown("### 📌 BAHAGIAN A : MAKLUMAT PEMOHON")
            bahagian_a_info = st.text_area("Maklumat Pemohon / Catatan Bahagian A:", key="a_info")

        # BAHAGIAN B
        with tab_b:
            st.markdown("### 📌 BAHAGIAN B : AKTIVITI YANG DIJALANKAN")
            st.markdown("*Sila pilih aktiviti yang dijalankan :")
            pengagihan_check = st.checkbox("Pengagihan", value=True)

            st.markdown("---")
            st.markdown("#### 📄 Lampiran 5")
            st.markdown("### Maklumat Pepasangan Bagi Aktiviti Pengagihan")

            st.markdown("#### 1. Sistem Pengagihan")
            col_b1, col_b2 = st.columns([3, 1])
            with col_b1:
                jumlah_keupayaan = st.text_input("*Jumlah keupayaan sistem pengagihan :", key="b_jumlah_keupayaan")
            with col_b2:
                st.markdown("<br>", unsafe_allow_html=True)
                st.text("kW")

            col_b3, col_b4 = st.columns([3, 1])
            with col_b3:
                kehendak_maksimum = st.text_input("*Kehendak Maksimum :", key="b_kehendak_maksimum")
            with col_b4:
                st.markdown("<br>", unsafe_allow_html=True)
                st.text("kW")

            punca_bekalan = st.radio(
                "*Punca bekalan :",
                ["TNB", "SESB", "Penjanaan Sendiri", "Lain-lain (Sila nyatakan)"],
                key="b_punca_bekalan"
            )
            punca_bekalan_lain = ""
            if punca_bekalan == "Lain-lain (Sila nyatakan)":
                punca_bekalan_lain = st.text_input("Nyatakan punca bekalan lain:", key="b_punca_bekalan_lain")

            st.markdown("*Tarif belian daripada utiliti :")
            col_t1, col_t2 = st.columns([3, 2])
            with col_t1:
                tarif_kehendak_max = st.text_input("Caj kehendak maksimum:", key="b_tarif_kehendak_max")
            with col_t2:
                st.markdown("<br>", unsafe_allow_html=True)
                st.text("RM/kW (caj kehendak maksimum)")

            col_t3, col_t4 = st.columns([3, 2])
            with col_t3:
                tarif_puncak = st.text_input("Caj bekalan puncak/caj tenaga:", key="b_tarif_puncak")
            with col_t4:
                st.markdown("<br>", unsafe_allow_html=True)
                st.text("sen/kWj (caj bekalan puncak/caj tenaga)")

            col_t5, col_t6 = st.columns([3, 2])
            with col_t5:
                tarif_luar_puncak = st.text_input("Caj bekalan luar puncak:", key="b_tarif_luar_puncak")
            with col_t6:
                st.markdown("<br>", unsafe_allow_html=True)
                st.text("sen/kWj (caj bekalan luar puncak)")

            col_b5, col_b6 = st.columns([3, 1])
            with col_b5:
                jumlah_tenaga_sebulan = st.text_input("*Jumlah tenaga elektrik dibeli sebulan dari utiliti :", key="b_jumlah_tenaga_sebulan")
            with col_b6:
                st.markdown("<br>", unsafe_allow_html=True)
                st.text("kWj")

            bilangan_incomers = st.text_input("*Bilangan Incomers (punca bekalan TNB/SESB sahaja) :", key="b_bilangan_incomers")
            nama_pencawang = st.text_input("*Nama Pencawang (punca bekalan TNB/SESB sahaja) :", key="b_nama_pencawang")

            col_b7, col_b8 = st.columns([3, 1])
            with col_b7:
                voltan_punca_bekalan = st.text_input("*Voltan punca bekalan :", key="b_voltan_punca_bekalan")
            with col_b8:
                st.markdown("<br>", unsafe_allow_html=True)
                st.text("kV")

            col_b9, col_b10 = st.columns([3, 1])
            with col_b9:
                voltan_pengagihan = st.text_input("*Voltan pengagihan :", key="b_voltan_pengagihan")
            with col_b10:
                st.markdown("<br>", unsafe_allow_html=True)
                st.text("kV")

            st.markdown("*Sistem agihan :")
            sistem_agihan_pendawaian = st.checkbox("Pendawaian dalaman", key="b_sa_pendawaian")
            sistem_agihan_kabel = st.checkbox("Kabel bawah tanah", key="b_sa_kabel")
            sistem_agihan_talian = st.checkbox("Talian atas", key="b_sa_talian")
            sistem_agihan_lain_check = st.checkbox("Lain-lain (Sila nyatakan)", key="b_sa_lain_check")
            sistem_agihan_lain = ""
            if sistem_agihan_lain_check:
                sistem_agihan_lain = st.text_input("Nyatakan sistem agihan lain:", key="b_sa_lain_text")

            col_b11, col_b12 = st.columns([3, 1])
            with col_b11:
                loji_janakuasa = st.text_input("Loji Janakuasa Tunggusedia (jika ada) :", key="b_loji_janakuasa")
            with col_b12:
                st.markdown("<br>", unsafe_allow_html=True)
                st.text("kW")

            col_b13, col_b14 = st.columns([1, 3])
            with col_b13:
                st.text("RM")
            with col_b14:
                caj_sambungan = st.text_input("Caj sambungan yang dikenakan oleh TNB/SESB :", key="b_caj_sambungan")

            st.markdown("<br>", unsafe_allow_html=True)
            st.markdown("#### 2. Pembekalan")

            default_pembekalan_df = pd.DataFrame({
                "Butiran": [
                    "*Bilangan pengguna",
                    "*Jumlah jualan tenaga elektrik sebulan yang dijangka kepada pengguna (kWj)",
                    "*Kadar kehendak maksimum pengguna (kW)",
                    "*Kos penyelenggaraan sebulan (RM)"
                ],
                "Industri": ["", "", "", ""],
                "Komersial": ["", "", "", ""],
                "Domestik": ["", "", "", ""]
            })

            edited_pembekalan_df = st.data_editor(
                default_pembekalan_df,
                disabled=["Butiran"],
                hide_index=True,
                use_container_width=True,
                key="pembekalan_table"
            )

        # BAHAGIAN C
        with tab_c:
            st.markdown("### 📌 BAHAGIAN C : DOKUMEN SOKONGAN & SENARAI SEMAK")

            doc_c_data = {}

            def render_doc_row(no, label, has_fotokopi=True, extra_widget=None, key_prefix="c_doc"):
                c1, c2, c3, c4 = st.columns([0.5, 4.0, 3.0, 1.5])
                c1.write(f"**{no}.**")
                c2.write(label)
                if extra_widget:
                    extra_widget()
                
                with c3:
                    file_up = st.file_uploader("Muat naik (Auto max 2MB)", type=["pdf", "png", "jpg", "jpeg", "docx"], key=f"{key_prefix}_file_{no}")
                    use_cam = st.checkbox("📷 Ambil Gambar", key=f"{key_prefix}_usecam_{no}")
                    cam_img = None
                    if use_cam:
                        cam_img = st.camera_input("Tangkap Gambar", key=f"{key_prefix}_cam_{no}")
                    
                    chosen_file = cam_img if cam_img else file_up

                foto = c4.checkbox("Salinan Fotokopi", key=f"{key_prefix}_foto_{no}") if has_fotokopi else False
                return chosen_file, foto

            # 1. Dokumen berkaitan syarikat
            st.markdown("#### 🏢 Dokumen berkaitan syarikat yang memohon dan disahkan.")
            syarikat_docs = [
                ("1", "*Borang 9 (Certificate of Incorporation)", False),
                ("2", "Borang 13 (Certificate of Incorporation on change of name)", True),
                ("3", "Borang 44 (Notice of Situation of Registered Office)", True),
                ("4", "Borang 24 (Return of Allotment of Shares)", True),
                ("5", "Borang 32A (Return for the Transfer of Shares Transaction)", True),
                ("6", "Borang 49 (Return giving Particulars in Register of Directors, Managers and Secretaries and Changes of Particulars)", True),
                ("7", "Borang 55 (Form Of Annual Return)", True),
                ("8", "Memorandum and Articles of Association", True)
            ]
            for idx, label, has_foto in syarikat_docs:
                f, foto = render_doc_row(idx, label, has_foto, key_prefix="c_syrkat")
                doc_c_data[f"Syarikat_{idx}_{label}"] = {"file": f, "fotokopi": foto}

            # 2. Lokasi pepasangan & lukisan-lukisan pepasangan
            st.markdown("<br>", unsafe_allow_html=True)
            st.markdown("#### 🗺️ Lokasi pepasangan & lukisan-lukisan pepasangan bersaiz A3 atau A4.")
            lokasi_docs = [
                ("1", "*Pelan lokasi dan pelan tapak (menyatakan no. lot pepasangan dan no. lot bersebelahan)", False),
                ("2", "Geran Tanah (Borang mesti lengkap)", True),
                ("3", "Salinan perjanjian sewa bangunan/tapak (jika bukan milik pemohon)", True),
                ("4", "Lukisan Skematik Utama Voltan Tinggi", True),
                ("5", "*Lukisan Skematik Utama Voltan Rendah", False)
            ]
            for idx, label, has_foto in lokasi_docs:
                f, foto = render_doc_row(idx, label, has_foto, key_prefix="c_lokasi")
                doc_c_data[f"Lokasi_{idx}_{label}"] = {"file": f, "fotokopi": foto}

            # 3. Kelulusan Agensi Kerajaan
            st.markdown("<br>", unsafe_allow_html=True)
            st.markdown("#### 🏛️ Kelulusan Agensi Kerajaan")
            kelulusan_docs = [
                ("1", "*Salinan surat kelulusan Pihak Berkuasa Tempatan (Kebenaran Merancang)", False),
                ("2", "Salinan surat kelulusan Kerajaan Negeri", True),
                ("3", "Salinan surat kelulusan Jabatan Alam Sekitar", True),
                ("4", "Salinan surat kelulusan permohonan bekalan pukal daripada pihak Utiliti", True),
                ("5", "Surat/bil/invois caj sambungan yang dikenakan oleh pihak Utiliti", True),
                ("6", "*Salinan surat kelulusan perlaksanaan PSS/CCC/NEMAS daripada pihak Utiliti", False),
                ("7", "Salinan surat tawaran projek loji janakuasa", True),
                ("8", "Salinan Sijil Kelulusan Tarif Galakan daripada SEDA", True),
                ("9", "Perjanjian Jualan Tenaga (PPA)", True),
                ("10", "Perjanjian Jual-Beli Tenaga dengan Utiliti (REPPA)", True),
                ("11", "Perjanjian Bekalan Bahanapi (FSA)", True),
                ("12", "Salinan Sijil Kelulusan Net Energy Metering (NEM) daripada SEDA", True),
                ("13", "Lain-lain kelulusan", True)
            ]
            for idx, label, has_foto in kelulusan_docs:
                f, foto = render_doc_row(idx, label, has_foto, key_prefix="c_kelulusan")
                doc_c_data[f"Kelulusan_{idx}_{label}"] = {"file": f, "fotokopi": foto}

            # 4. Analisis Kewangan
            st.markdown("<br>", unsafe_allow_html=True)
            st.markdown("#### 💰 Analisis Kewangan")
            kewangan_docs = [
                ("1", "Letter Of Intent Daripada Pembiaya Kewangan", True),
                ("2", "Letter Of Offer Daripada Pembiaya Kewangan", True),
                ("3", "Dokumen perjanjian kewangan", True)
            ]
            for idx, label, has_foto in kewangan_docs:
                f, foto = render_doc_row(idx, label, has_foto, key_prefix="c_kewangan")
                doc_c_data[f"Kewangan_{idx}_{label}"] = {"file": f, "fotokopi": foto}

            # 4.4 & 4.5
            st.markdown("---")
            c1, c2, c3, c4 = st.columns([0.5, 4.0, 3.0, 1.5])
            c1.write("**4.**")
            with c2:
                st.write("Project Financial Run - bagi aktiviti Penjanaan :")
                act_penjanaan = st.selectbox("Aktiviti Penjanaan:", ["--- Sila pilih ---", "Solar", "Biomass", "Hydro", "Lain-lain"], key="c_act_penjanaan")
                st.caption("Arahan:\n1. Sila pilih aktiviti Penjanaan di atas.\n2. Muat turun fail excel berikut.\n3. Lengkapkan maklumat yang diperlukan dalam fail excel.\n4. Muat naik semula fail excel yang telah dilengkapkan.")
            with c3:
                f_penjanaan = st.file_uploader("Muat naik Excel Penjanaan", type=["xlsx", "xls", "pdf"], key="c_file_penjanaan")
            foto_penjanaan = c4.checkbox("Fotokopi", key="c_foto_penjanaan")
            doc_c_data["Kewangan_4_Project_Financial_Run"] = {"file": f_penjanaan, "fotokopi": foto_penjanaan, "extra": act_penjanaan}

            c1, c2, c3, c4 = st.columns([0.5, 4.0, 3.0, 1.5])
            c1.write("**5.**")
            with c2:
                st.write("Simple Financial Analysis - bagi aktiviti Pengagihan")
                st.caption("Arahan:\n1. Muat turun fail excel berikut: Simple Financial Analysis.xlsx\n2. Lengkapkan maklumat yang diperlukan dalam fail excel.\n3. Muat naik semula fail excel yang telah dilengkapkan.")
            with c3:
                f_pengagihan = st.file_uploader("Muat naik Excel Pengagihan", type=["xlsx", "xls", "pdf"], key="c_file_pengagihan")
            foto_pengagihan = c4.checkbox("Fotokopi", key="c_foto_pengagihan")
            doc_c_data["Kewangan_5_Simple_Financial_Analysis"] = {"file": f_pengagihan, "fotokopi": foto_pengagihan}

            # 5. Ringkasan Projek
            st.markdown("<br>", unsafe_allow_html=True)
            st.markdown("#### 📊 Ringkasan Projek")
            c1, c2, c3, c4 = st.columns([0.5, 4.0, 3.0, 1.5])
            c1.write("**1.**")
            c2.write("Merangkumi maklumat aktiviti yang akan dilesenkan seperti cadangan teknikal & cadangan pembiayaan projek; lokasi pepasangan, aktiviti bangunan, product catalogue, insentif yang diperoleh, status kemajuan projek dan gambar tapak, serta maklumat-maklumat lain yang berkaitan.")
            with c3:
                f_ringkasan1 = st.file_uploader("Muat naik Ringkasan Projek", type=["pdf", "png", "jpg", "jpeg", "docx"], key="c_file_ringkasan1")
            foto_ringkasan1 = c4.checkbox("Fotokopi", key="c_foto_ringkasan1")
            doc_c_data["Ringkasan_1_Maklumat_Aktiviti"] = {"file": f_ringkasan1, "fotokopi": foto_ringkasan1}

            c1, c2, c3, c4 = st.columns([0.5, 4.0, 3.0, 1.5])
            c1.write("**2.**")
            c2.write("Bagi permohonan pindaan lesen, sila nyatakan justifikasi ke atas permohonan pindaan yang dibuat.")
            with c3:
                f_ringkasan2 = st.file_uploader("Muat naik Justifikasi Pindaan", type=["pdf", "png", "jpg", "jpeg", "docx"], key="c_file_ringkasan2")
            foto_ringkasan2 = c4.checkbox("Fotokopi", key="c_foto_ringkasan2")
            doc_c_data["Ringkasan_2_Justifikasi_Pindaan"] = {"file": f_ringkasan2, "fotokopi": foto_ringkasan2}

            # 6. Salinan sijil kakitangan / Orang Kompeten yang dilantik
            st.markdown("<br>", unsafe_allow_html=True)
            st.markdown("#### 👷 *Salinan sijil kakitangan / Orang Kompeten yang dilantik")
            st.caption("**Makluman: WAJIB isi SALAH SATU daripada perkara di bawah.**")

            st.markdown("##### 1. Jurutera Elektrik Kompeten / Jurutera Perkhidmatan / Penyelia Elektrik")
            c_btn1, c_btn2 = st.columns([1, 1])
            with c_btn1:
                st.button("Cari", key="c_btn_cari1")
            with c_btn2:
                st.button("Reset", key="c_btn_reset1")

            c_j1, c_j2 = st.columns(2)
            with c_j1:
                jurutera_mykad = st.text_input("No. MyKad :", key="c_jurutera_mykad")
                jurutera_nama = st.text_input("Nama :", key="c_jurutera_nama")
                jurutera_perakuan = st.text_input("No. Perakuan :", key="c_jurutera_perakuan")
            with c_j2:
                jurutera_kategori = st.text_input("Kategori/Sekatan :", key="c_jurutera_kategori")
                jurutera_tarikh_tamat = st.date_input("Tarikh Tamat :", key="c_jurutera_tarikh_tamat")
                jurutera_alamat = st.text_area("Alamat :", key="c_jurutera_alamat")

            st.markdown("##### 2. Penjaga Jentera yang dilantik")
            c_btn3, c_btn4 = st.columns([1, 1])
            with c_btn3:
                st.button("Cari", key="c_btn_cari2")
            with c_btn4:
                st.button("Reset", key="c_btn_reset2")

            c_p1, c_p2 = st.columns(2)
            with c_p1:
                penjaga_mykad = st.text_input("No. MyKad :", key="c_penjaga_mykad")
                penjaga_nama = st.text_input("Nama :", key="c_penjaga_nama")
                penjaga_perakuan = st.text_input("No. Perakuan :", key="c_penjaga_perakuan")
            with c_p2:
                penjaga_kategori = st.text_input("Kategori/Sekatan :", key="c_penjaga_kategori")
                penjaga_tarikh_tamat = st.date_input("Tarikh Tamat :", key="c_penjaga_tarikh_tamat")
                penjaga_alamat = st.text_area("Alamat :", key="c_penjaga_alamat")

            st.markdown("##### 3. Muat naik Surat Komitmen Pelantikan Sebelum Pepasangan Mula Tugas")
            f_surat_jurutera = st.file_uploader("a. Surat Pelantikan Jurutera Elektrik Kompeten / Jurutera Perkhidmatan / Penyelia Elektrik :", type=["pdf", "png", "jpg", "jpeg", "docx"], key="c_f_surat_jurutera")
            f_surat_penjaga = st.file_uploader("b. Surat Pelantikan Penjaga Jentera :", type=["pdf", "png", "jpg", "jpeg", "docx"], key="c_f_surat_penjaga")

        # BAHAGIAN D
        with tab_d:
            st.markdown("### 📌 BAHAGIAN D")
            bahagian_d_info = st.text_area("Maklumat Bahagian D:", key="d_info")

        # BAHAGIAN E
        with tab_e:
            st.markdown("### 📌 Bahagian E : MAKLUMAT PERMOHONAN")

            st.markdown("#### 1. Butiran Tapak Pepasangan")
            st.caption("(Termasuk keseluruhan kawasan bekalan jika melibatkan aktiviti pengagihan)")

            e_no_lot = st.text_input("*No. Lot :", key="e_no_lot")
            e_lot_status = st.radio("Status Lot:", ["Tetap", "Sementara"], horizontal=True, key="e_lot_status")

            e_mukim = st.text_input("*Mukim :", key="e_mukim")
            e_daerah = st.text_input("*Daerah :", key="e_daerah")
            e_poskod = st.text_input("*Poskod :", key="e_poskod")

            negeri_list = [
                "--- Sila pilih ---", "Johor", "Kedah", "Kelantan", "Melaka", 
                "Negeri Sembilan", "Pahang", "Perak", "Perlis", "Pulau Pinang", 
                "Sabah", "Sarawak", "Selangor", "Terengganu", "W.P. Kuala Lumpur", 
                "W.P. Labuan", "W.P. Putrajaya"
            ]
            e_negeri = st.selectbox("*Negeri :", negeri_list, key="e_negeri")

            jenis_projek_list = ["--- Sila pilih ---", "Pembangunan Baru", "Peluasan / Peningkatan Kapasiti", "Pindaan Lesen", "Lain-lain"]
            e_jenis_projek = st.selectbox("Jenis Projek :", jenis_projek_list, key="e_jenis_projek")

            st.markdown("*Kategori Penggunaan :")
            e_kat_pengilangan = st.checkbox("Pengilangan / Industri", key="e_kat_pengilangan")
            e_kat_perladangan = st.checkbox("Perladangan", key="e_kat_perladangan")
            e_kat_perniagaan = st.checkbox("Perniagaan", key="e_kat_perniagaan")
            e_kat_lain_check = st.checkbox("Lain-lain (Sila nyatakan) :", key="e_kat_lain_check")
            e_kat_lain_text = ""
            if e_kat_lain_check:
                e_kat_lain_text = st.text_input("Nyatakan kategori penggunaan lain:", key="e_kat_lain_text")

            st.markdown("Bagi tujuan lesen persendirian, sila nyatakan sebab penjanaan sendiri :")
            e_sebab_sementara = st.checkbox("Bekalan sementara", key="e_sebab_sementara")
            e_sebab_ekonomi = st.checkbox("Lebih ekonomi", key="e_sebab_ekonomi")
            e_sebab_tiada_utiliti = st.checkbox("Tiada bekalan utiliti", key="e_sebab_tiada_utiliti")
            e_sebab_lain_check = st.checkbox("Lain-lain (Sila nyatakan) :", key="e_sebab_lain_check")
            e_sebab_lain_text = ""
            if e_sebab_lain_check:
                e_sebab_lain_text = st.text_input("Nyatakan sebab penjanaan sendiri lain:", key="e_sebab_lain_text")

            status_pepasangan_list = ["--- Sila pilih ---", "Dalam Perancangan", "Dalam Pembinaan", "Telah Siap", "Beroperasi"]
            e_status_pepasangan = st.selectbox("*Status pepasangan :", status_pepasangan_list, key="e_status_pepasangan")

            st.markdown("*Tempoh Lesen Diperlukan :")
            col_e_t1, col_e_t2 = st.columns([3, 1])
            with col_e_t1:
                e_tempoh_lesen = st.text_input("Tempoh :", key="e_tempoh_lesen")
            with col_e_t2:
                st.markdown("<br>", unsafe_allow_html=True)
                st.text("tahun")

            e_tarikh_mulai = st.date_input("Mulai :", key="e_tarikh_mulai")

            st.markdown("<br>", unsafe_allow_html=True)
            e_tarikh_pentauliahan = st.date_input("*Tarikh Pentauliahan Pepasangan :", key="e_tarikh_pentauliahan")

            st.markdown("<br>", unsafe_allow_html=True)
            st.markdown("*Tarikh Mulatugas :")

            e_mulatugas_list = []
            for i in range(st.session_state.tarikh_mulatugas_count):
                col_m1, col_m2, col_m3 = st.columns([1, 3, 1])
                with col_m1:
                    st.markdown(f"<br><b>{i+1}</b>", unsafe_allow_html=True)
                with col_m2:
                    t_val = st.date_input(f"Tarikh Unit {i+1}:", key=f"e_mulatugas_tarikh_{i}")
                    e_mulatugas_list.append({"unit": i+1, "tarikh": str(t_val)})
                with col_m3:
                    st.markdown("<br>", unsafe_allow_html=True)
                    if st.button("Hapus", key=f"e_hapus_mulatugas_{i}"):
                        if st.session_state.tarikh_mulatugas_count > 1:
                            st.session_state.tarikh_mulatugas_count -= 1
                            st.rerun()

            if st.button("Tambah", key="e_tambah_mulatugas"):
                st.session_state.tarikh_mulatugas_count += 1
                st.rerun()

        # BAHAGIAN F
        with tab_f:
            st.markdown("### 📌 Bahagian F : PENGAKUAN PEMOHON")

            display_applicant = project_title if project_title else "PEMOHON"

            f_check1 = st.checkbox(
                f"*Saya {display_applicant}, mengaku bahawa maklumat-maklumat yang terkandung di dalam permohonan ini adalah benar dan kenyataan-kenyataan adalah betul dan saya sedar adalah menjadi suatu kesalahan di bawah seksyen 8 Akta Bekalan Elektrik 1990 jika maklumat-maklumat yang diberikan itu adalah palsu.",
                key="f_check1"
            )

            f_check2 = st.checkbox(
                "*Saya akan melantik orang kompeten untuk menjaga, mengendalikan dan menyelia pepasangan menurut Akta Bekalan Elektrik 1990 dan Peraturan-Peraturan yang dibuat dibawahnya dan memaklumkan Suruhanjaya Tenaga berkenaan dengan perlantikan tersebut.",
                key="f_check2"
            )

            f_check3 = st.checkbox(
                "*Saya bersetuju untuk mematuhi terma-terma dan syarat-syarat lesen awam yang diberikan oleh Suruhanjaya Tenaga.",
                key="f_check3"
            )

        # BAHAGIAN G
        with tab_g:
            st.markdown("### 📌 Bahagian G : PENGESAHAN JURUTERA PROFESIONAL / ORANG KOMPETEN")

            st.markdown("*Saya mengesahkan bahawa (Tandakan aktiviti yang berkenaan) :")

            g_aktiviti_option = st.radio(
                "Aktiviti Pengesahan:",
                [
                    "Pepasangan baru ini telah direkabentuk dan diselia oleh saya mengikut kehendak perundangan yang berkaitan serta mengikut amalan kejuruteraan yang baik (good engineering practice).",
                    "Pepasangan sedia ada ini telah direkabentuk dan dipasang mengikut kehendak perundangan yang berkaitan serta mengikut amalan kejuruteraan yang baik (good engineering practice)."
                ],
                key="g_aktiviti_option"
            )

            g_nama = st.text_input("*Nama :", key="g_nama")
            g_no_perakuan = st.text_input("*No. Perakuan :", key="g_no_perakuan")
            g_alamat = st.text_area("*Alamat :", key="g_alamat")

            st.caption("Pemohon dikehendaki membayar Fi Proses secara atas talian (online) terlebih dahulu sebelum menghantar permohonan.")

            col_g1, col_g2, col_g3 = st.columns([2, 1, 1])
            with col_g1:
                st.button("Bayar Fi Proses & Hantar", key="g_btn_bayar")
            with col_g2:
                st.button("Simpan Draf", key="g_btn_draf")
            with col_g3:
                st.button("Hapus Draf", key="g_btn_hapus_draf")

        st.markdown("---")

        with st.form(key="submit_form"):
            submit = st.form_submit_button("✅ Submit Application")
            if submit:
                if not project_title.strip():
                    st.warning("❗ Please provide a project title.")
                elif not location.strip():
                    st.warning("❗ Please provide a location.")
                elif not description.strip():
                    st.warning("❗ Please provide a project description.")
                elif not (f_check1 and f_check2 and f_check3):
                    st.warning("❗ Please complete all declarations in Bahagian F before submitting.")
                else:
                    try:
                        timestamp = datetime.now(MALAYSIA_ZONE).strftime("%Y-%m-%d %H:%M:%S")

                        # Automatically create or use the dedicated project subfolder inside FOLDER_ID
                        project_folder_id = get_or_create_project_folder(project_title, FOLDER_ID)

                        # Process selected 'Sistem Agihan' options
                        sistem_agihan_selected = []
                        if sistem_agihan_pendawaian: sistem_agihan_selected.append("Pendawaian dalaman")
                        if sistem_agihan_kabel: sistem_agihan_selected.append("Kabel bawah tanah")
                        if sistem_agihan_talian: sistem_agihan_selected.append("Talian atas")
                        if sistem_agihan_lain_check and sistem_agihan_lain:
                            sistem_agihan_selected.append(f"Lain-lain: {sistem_agihan_lain}")

                        final_punca_bekalan = punca_bekalan
                        if punca_bekalan == "Lain-lain (Sila nyatakan)" and punca_bekalan_lain:
                            final_punca_bekalan = f"Lain-lain: {punca_bekalan_lain}"

                        pembekalan_json = json.dumps(edited_pembekalan_df.to_dict(orient="records"))

                        # Process Bahagian C Uploads & Checklist (stored in project folder)
                        bahagian_c_summary = {}
                        for key_doc, doc_val in doc_c_data.items():
                            file_obj = doc_val["file"]
                            uploaded_link = None
                            if file_obj:
                                content = file_obj.getvalue() if hasattr(file_obj, "getvalue") else file_obj.read()
                                orig_name = getattr(file_obj, "name", "camera_capture.jpg")
                                clean_filename = f"{timestamp}_BahagianC_{key_doc[:30]}_{os.path.splitext(orig_name)[1]}"
                                mimetype = mimetypes.guess_type(clean_filename)[0] or 'image/jpeg'
                                uploaded_link, _ = gdrive_upload_file(content, clean_filename, mimetype, project_folder_id)
                            
                            bahagian_c_summary[key_doc] = {
                                "file_link": uploaded_link if uploaded_link else "Tiada",
                                "salinan_fotokopi": doc_val.get("fotokopi", False),
                                "extra": doc_val.get("extra", "")
                            }

                        # Process competent person surat pelantikan (stored in project folder)
                        surat_jurutera_link = "Tiada"
                        if f_surat_jurutera:
                            content = f_surat_jurutera.getvalue() if hasattr(f_surat_jurutera, "getvalue") else f_surat_jurutera.read()
                            clean_filename = f"{timestamp}_BahagianC_SuratJurutera_{os.path.splitext(f_surat_jurutera.name)[1]}"
                            mimetype = mimetypes.guess_type(clean_filename)[0] or 'application/octet-stream'
                            surat_jurutera_link, _ = gdrive_upload_file(content, clean_filename, mimetype, project_folder_id)

                        surat_penjaga_link = "Tiada"
                        if f_surat_penjaga:
                            content = f_surat_penjaga.getvalue() if hasattr(f_surat_penjaga, "getvalue") else f_surat_penjaga.read()
                            clean_filename = f"{timestamp}_BahagianC_SuratPenjaga_{os.path.splitext(f_surat_penjaga.name)[1]}"
                            mimetype = mimetypes.guess_type(clean_filename)[0] or 'application/octet-stream'
                            surat_penjaga_link, _ = gdrive_upload_file(content, clean_filename, mimetype, project_folder_id)

                        bahagian_c_competent = {
                            "jurutera": {
                                "mykad": jurutera_mykad, "nama": jurutera_nama, "perakuan": jurutera_perakuan,
                                "kategori": jurutera_kategori, "tarikh_tamat": str(jurutera_tarikh_tamat), "alamat": jurutera_alamat
                            },
                            "penjaga": {
                                "mykad": penjaga_mykad, "nama": penjaga_nama, "perakuan": penjaga_perakuan,
                                "kategori": penjaga_kategori, "tarikh_tamat": str(penjaga_tarikh_tamat), "alamat": penjaga_alamat
                            },
                            "surat_jurutera": surat_jurutera_link,
                            "surat_penjaga": surat_penjaga_link
                        }

                        c_checklist_json = json.dumps(bahagian_c_summary)
                        c_competent_json = json.dumps(bahagian_c_competent)

                        # Process Bahagian E Data
                        kat_penggunaan_list = []
                        if e_kat_pengilangan: kat_penggunaan_list.append("Pengilangan / Industri")
                        if e_kat_perladangan: kat_penggunaan_list.append("Perladangan")
                        if e_kat_perniagaan: kat_penggunaan_list.append("Perniagaan")
                        if e_kat_lain_check and e_kat_lain_text:
                            kat_penggunaan_list.append(f"Lain-lain: {e_kat_lain_text}")

                        sebab_penjanaan_list = []
                        if e_sebab_sementara: sebab_penjanaan_list.append("Bekalan sementara")
                        if e_sebab_ekonomi: sebab_penjanaan_list.append("Lebih ekonomi")
                        if e_sebab_tiada_utiliti: sebab_penjanaan_list.append("Tiada bekalan utiliti")
                        if e_sebab_lain_check and e_sebab_lain_text:
                            sebab_penjanaan_list.append(f"Lain-lain: {e_sebab_lain_text}")

                        bahagian_e_data = {
                            "no_lot": e_no_lot,
                            "lot_status": e_lot_status,
                            "mukim": e_mukim,
                            "daerah": e_daerah,
                            "poskod": e_poskod,
                            "negeri": e_negeri,
                            "jenis_projek": e_jenis_projek,
                            "kategori_penggunaan": kat_penggunaan_list,
                            "sebab_penjanaan_sendiri": sebab_penjanaan_list,
                            "status_pepasangan": e_status_pepasangan,
                            "tempoh_lesen_tahun": e_tempoh_lesen,
                            "tarikh_mulai": str(e_tarikh_mulai),
                            "tarikh_pentauliahan": str(e_tarikh_pentauliahan),
                            "tarikh_mulatugas": e_mulatugas_list
                        }
                        bahagian_e_json = json.dumps(bahagian_e_data)

                        # Process Bahagian F Data
                        bahagian_f_data = {
                            "pengakuan_maklumat_benar": f_check1,
                            "pengakuan_lantik_orang_kompeten": f_check2,
                            "pengakuan_patuh_syarat_lesen": f_check3
                        }
                        bahagian_f_json = json.dumps(bahagian_f_data)

                        # Process Bahagian G Data
                        bahagian_g_data = {
                            "aktiviti_pengesahan": g_aktiviti_option,
                            "nama": g_nama,
                            "no_perakuan": g_no_perakuan,
                            "alamat": g_alamat
                        }
                        bahagian_g_json = json.dumps(bahagian_g_data)

                        row = [
                            timestamp, project_title, location, total_bay, total_evcs, evcs_type,
                            brand_model, no_of_units, rated_input_power, max_charging_power,
                            mode_of_charging, connector_type, output_cable_size, no_of_charging_bays,
                            gps_lat, gps_lon, description,
                            bahagian_a_info,
                            "Pengagihan" if pengagihan_check else "",
                            jumlah_keupayaan, kehendak_maksimum, final_punca_bekalan,
                            tarif_kehendak_max, tarif_puncak, tarif_luar_puncak,
                            jumlah_tenaga_sebulan, bilangan_incomers, nama_pencawang,
                            voltan_punca_bekalan, voltan_pengagihan,
                            ", ".join(sistem_agihan_selected), loji_janakuasa, caj_sambungan,
                            pembekalan_json,
                            c_checklist_json, c_competent_json,
                            bahagian_d_info,
                            bahagian_e_json,
                            bahagian_f_json, bahagian_g_json
                        ]

                        header = [
                            "Timestamp", "Project Title", "Location", "Total Bay", "Total EVCS", "EVCS Type",
                            "Brand / Model", "No. of Units", "Rated Input Power (kW AC)", "Max. Charging Power",
                            "Mode of Charging", "Connector Type", "Output Cable Size", "No. of Charging Bays",
                            "GPS Latitude", "GPS Longitude", "Description",
                            "Bahagian A Info",
                            "Bahagian B - Aktiviti", "Jumlah Keupayaan (kW)", "Kehendak Maksimum (kW)", "Punca Bekalan",
                            "Tarif Caj Kehendak Max (RM/kW)", "Tarif Caj Puncak (sen/kWj)", "Tarif Caj Luar Puncak (sen/kWj)",
                            "Jumlah Tenaga Sebulan (kWj)", "Bilangan Incomers", "Nama Pencawang",
                            "Voltan Punca Bekalan (kV)", "Voltan Pengagihan (kV)",
                            "Sistem Agihan", "Loji Janakuasa Tunggusedia (kW)", "Caj Sambungan TNB/SESB (RM)",
                            "Pembekalan Table Data (JSON)",
                            "Bahagian C Senarai Semak (JSON)", "Bahagian C Orang Kompeten (JSON)",
                            "Bahagian D Info",
                            "Bahagian E Maklumat Permohonan (JSON)",
                            "Bahagian F Pengakuan (JSON)", "Bahagian G Pengesahan (JSON)"
                        ]

                        gsheet_id = find_or_create_gsheet("general_applications", FOLDER_ID)
                        append_row_to_gsheet(gsheet_id, row, header)

                        st.session_state.update({
                            "project_title": "",
                            "location": "",
                            "total_bay": "",
                            "total_evcs": "",
                            "evcs_type": "AC",
                            "brand_model": "",
                            "no_of_units": "",
                            "rated_input_power": "",
                            "max_charging_power": "",
                            "mode_of_charging": "",
                            "connector_type": "",
                            "output_cable_size": "",
                            "no_of_charging_bays": "",
                            "gps_lat": "",
                            "gps_lon": "",
                            "description": "",
                            "tarikh_mulatugas_count": 1,
                        })
                        st.success("Application Submitted Successfully!")
                        time.sleep(2)
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error during submission: {e}")

    # ----- EXISTING APPLICATION SECTION -----
    elif st.session_state.app_mode == "existing":
        st.subheader("📁 Existing Applications")
        st.info("Viewing and tracking existing applications will appear here.")

# --------- 2. DETAIL APPLICATION ---------
elif nav_selection == "2. Detail Application":
    st.title("Detail Application")
    st.info("This section is reserved for future detailed application management and review tools.")

# --------- 3. INFORMATION ---------
elif nav_selection == "3. Information":
    st.title("Information")
    st.info("This section provides guidelines, instructions, and system information.")

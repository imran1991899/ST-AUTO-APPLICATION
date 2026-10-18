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

from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

# Malaysia timezone
try:
    from zoneinfo import ZoneInfo
    MALAYSIA_ZONE = ZoneInfo("Asia/Kuala_Lumpur")
except ImportError:
    import pytz
    MALAYSIA_ZONE = pytz.timezone("Asia/Kuala_Lumpur")

# --------- Page Setup ---------
st.set_page_config(page_title="Bus Stop Survey", layout="wide")
st.title("Bus Stop Assessment Survey")

# --------- Google Drive Folder ID ---------
FOLDER_ID = "1U1E45NroftvHINPziURbJDaojsX6P-AP"

# --------- OAuth Setup ---------
SCOPES = [
    'https://www.googleapis.com/auth/drive.file',
    'https://www.googleapis.com/auth/spreadsheets'
]

CLIENT_SECRETS_FILE = 'client_secrets.json'
# Ensure this matches your Streamlit Cloud URL exactly
REDIRECT_URI = 'https://bus-stop-survey-dpl6qeby3stuvpiexjhovk.streamlit.app/'

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
    flow = Flow.from_client_secrets_file(CLIENT_SECRETS_FILE, scopes=SCOPES, redirect_uri=REDIRECT_URI)
    
    query_params = st.query_params

    if "code" in query_params:
        # Check for the verifier file saved before redirect
        if os.path.exists("verifier.tmp"):
            with open("verifier.tmp", "r") as f:
                flow.code_verifier = f.read()
            try:
                # Reconstruct the response URL for the library
                full_url = REDIRECT_URI + "?" + urlencode(query_params)
                flow.fetch_token(authorization_response=full_url)
                save_credentials(flow.credentials)
                
                # Cleanup
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
        # Initial step: Generate Auth URL and save verifier to disk
        auth_url, _ = flow.authorization_url(prompt='consent', access_type="offline", include_granted_scopes="true")
        with open("verifier.tmp", "w") as f:
            f.write(flow.code_verifier)
        
        st.markdown(f"### Authentication Required\n[🔴 Click Here to Login with Google]({auth_url})")
        st.stop()

# --------- Google API Setup ---------
drive_service, sheets_service = get_authenticated_service()

def gdrive_upload_file(file_bytes, filename, mimetype, folder_id=None):
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

# --------- Load Excel Data ---------
try:
    routes_df = pd.read_excel("bus_data.xlsx", sheet_name="routes")
    stops_df = pd.read_excel("bus_data.xlsx", sheet_name="stops")
except Exception as e:
    st.error(f"❌ Failed to load bus_data.xlsx: {e}")
    st.stop()

# --------- Initialize Session State ---------
for key, default in {
    "staff_id": "",
    "selected_depot": "",
    "selected_route": "",
    "selected_stop": "",
    "condition": "1. Covered Bus Stop",
    "activity_category": "",
    "specific_conditions": set(),
    "ground_status": "",
    "other_text": "",
    "photos": [],
    "show_success": False,
    "time_of_day": None,
}.items():
    if key not in st.session_state:
        st.session_state[key] = default

def handle_ground_status_change():
    st.session_state.ground_status = st.session_state.temp_ground_status
    if st.session_state.ground_status == "Tiada Isu":
        st.session_state.specific_conditions = {"1. Tiada Isu"}
    elif st.session_state.ground_status == "Isu":
        st.session_state.specific_conditions.discard("1. Tiada Isu")

# --------- Survey Questions ---------

staff_id = st.text_input("👤 Staff ID (8 digits)", value=st.session_state.staff_id)
if staff_id and (not staff_id.isdigit() or len(staff_id) != 8):
    st.warning("⚠️ Staff ID must be exactly 8 digits.")
st.session_state.staff_id = staff_id

depots = routes_df["Depot"].dropna().unique()
selected_depot = st.selectbox("1️⃣ Select Depot", depots, 
    index=list(depots).index(st.session_state.selected_depot) if st.session_state.selected_depot in depots else 0)
st.session_state.selected_depot = selected_depot

filtered_routes = routes_df[routes_df["Depot"] == selected_depot]["Route Number"].dropna().unique()
selected_route = st.selectbox("2️⃣ Select Route Number", filtered_routes, 
    index=list(filtered_routes).index(st.session_state.selected_route) if st.session_state.selected_route in filtered_routes else 0)
st.session_state.selected_route = selected_route

filtered_stops_df = stops_df[
    (stops_df["Route Number"] == selected_route) & 
    stops_df["Stop Name"].notna() & 
    stops_df["Order"].notna() & 
    stops_df["dr"].notna()
].sort_values(by=["dr", "Order"])

filtered_stops = []
for _, row in filtered_stops_df.iterrows():
    name = str(row['Stop Name'])
    try:
        id_val = row.iloc[4]
        if pd.isna(id_val) or str(id_val).strip() == "":
            filtered_stops.append(name)
        else:
            clean_id = str(id_val).split('.')[0]
            filtered_stops.append(f"{name} (id:{clean_id})")
    except:
        filtered_stops.append(name)

if st.session_state.selected_stop not in filtered_stops:
    st.session_state.selected_stop = filtered_stops[0] if filtered_stops else ""

selected_stop = st.selectbox("3️⃣ Select Bus Stop", filtered_stops, 
    index=filtered_stops.index(st.session_state.selected_stop) if st.session_state.selected_stop in filtered_stops else 0)
st.session_state.selected_stop = selected_stop

conditions = ["1. Covered Bus Stop", "2. Pole Only", "3. Layby", "4. Non-Infrastructure"]
condition = st.selectbox("4️⃣ Bus Stop Condition", conditions, 
    index=conditions.index(st.session_state.condition) if st.session_state.condition in conditions else 0)
st.session_state.condition = condition

activity_options = ["", "1. On Board in the Bus", "2. On Ground Location"]
activity_category = st.selectbox("5️⃣ Categorizing Activities", activity_options, 
    index=activity_options.index(st.session_state.activity_category) if st.session_state.activity_category in activity_options else 0)
st.session_state.activity_category = activity_category

if activity_category == "1. On Board in the Bus":
    onboard_options = ["1. Tiada penumpang menunggu", "2. Tiada isyarat (penumpang tidak menahan bas)", "3. Tidak berhenti/memperlahankan bas", "4. Salah tempat menunggu", "5. Bas penuh", "6. Mengejar masa waybill (punctuality)", "7. Kesesakan lalu lintas", "8. Kekeliruan laluan oleh pemandu baru", "9. Terdapat laluan tutup atas sebab tertentu (baiki jalan, pokok tumbang, lawatan delegasi)", "10. Hentian terlalu hampir simpang masuk", "11. Hentian berdekatan dengan traffic light", "12. Other (Please specify below)", "13. Remarks"]
    
    st.markdown("6️⃣ Specific Situational Conditions (Select all that apply)")
    has_exclusive = any("1. Tiada penumpang menunggu" in s for s in st.session_state.specific_conditions)
    has_others = any("1. Tiada penumpang menunggu" not in s for s in st.session_state.specific_conditions)

    for opt in onboard_options:
        is_excl = "1. Tiada penumpang menunggu" in opt
        disabled = (is_excl and has_others) or (not is_excl and has_exclusive)
        checked = opt in st.session_state.specific_conditions
        if st.checkbox(opt, value=checked, key=opt, disabled=disabled):
            st.session_state.specific_conditions.add(opt)
        else:
            st.session_state.specific_conditions.discard(opt)

elif activity_category == "2. On Ground Location":
    st.markdown("6️⃣ Ground Assessment")
    ground_status_options = ["", "Tiada Isu", "Isu"]
    st.radio(
        "Is there an issue?", 
        ground_status_options, 
        index=ground_status_options.index(st.session_state.ground_status),
        key="temp_ground_status",
        on_change=handle_ground_status_change
    )

    if st.session_state.ground_status == "Tiada Isu":
        st.info("Status: No issues.")
    elif st.session_state.ground_status == "Isu":
        onground_issues = ["2. Infrastruktur sudah tiada/musnah", "3. Terlindung oleh pokok", "4. Terhalang oleh kenderaan parkir", "5. Hentian gelap dan tiada lampu jalan", "6. Perubahan Nama,Coordinate, Lokasi hentian", "7. Ada Infra, tiada bus bay ", "8. Ada Tiang, tiada bus bay ", "9. Hentian rosak & vandalism", "10. Keselamatan bas - lokasi hentian tidak sesuai ", "11. Keselamatan pax - Lokasi hentian tidak sesuai", "12. Other (Please specify below)", "13. Remarks"]
        
        st.markdown("Select all that apply:")
        for opt in onground_issues:
            checked = opt in st.session_state.specific_conditions
            if st.checkbox(opt, value=checked, key=f"ground_{opt}"):
                st.session_state.specific_conditions.add(opt)
            else:
                st.session_state.specific_conditions.discard(opt)

if any("Other" in s for s in st.session_state.specific_conditions):
    other_text = st.text_area("📝 Please describe 'Other' (min 2 words)", height=150, value=st.session_state.other_text)
    st.session_state.other_text = other_text

st.markdown("7️⃣ Add up to 5 Photos")
if len(st.session_state.photos) < 5:
    photo = st.camera_input(f"📷 Take Photo #{len(st.session_state.photos) + 1}")
    if photo:
        st.session_state.photos.append(photo)

if len(st.session_state.photos) < 5:
    upload_photo = st.file_uploader(f"📁 Upload Photo #{len(st.session_state.photos) + 1}", type=["png", "jpg", "jpeg"], key=f"uploader_{len(st.session_state.photos)}")
    if upload_photo:
        st.session_state.photos.append(upload_photo)

if st.session_state.photos:
    st.subheader("📸 Saved Photos")
    to_delete = None
    for i, p in enumerate(st.session_state.photos):
        cols = st.columns([4, 1])
        cols[0].image(p, caption=f"Photo #{i + 1}", use_container_width=True)
        if cols[1].button(f"❌ Delete #{i + 1}", key=f"del_{i}"):
            to_delete = i
    if to_delete is not None:
        st.session_state.photos.pop(to_delete)
        st.rerun()

time_options = ["", "Daytime", "Nighttime"]
current_time_val = st.session_state.time_of_day if st.session_state.time_of_day in time_options else ""
selected_time = st.selectbox("8️⃣ Daytime / Nighttime", time_options, index=time_options.index(current_time_val))
st.session_state.time_of_day = selected_time

with st.form(key="submit_form"):
    submit = st.form_submit_button("✅ Submit Survey")
    if submit:
        if not staff_id.strip() or len(staff_id) != 8:
            st.warning("❗ Staff ID must be 8 digits.")
        elif not st.session_state.photos:
            st.warning("❗ Please add at least one photo.")
        elif not st.session_state.time_of_day:
            st.warning("❗ Please select Daytime or Nighttime.")
        elif not st.session_state.specific_conditions:
            st.warning("❗ Please provide an assessment in Section 6.")
        else:
            try:
                timestamp = datetime.now(MALAYSIA_ZONE).strftime("%Y-%m-%d %H:%M:%S")
                photo_links = []
                # --- CORRECTED BLOCK ---
                photo_links = []
                for idx, img in enumerate(st.session_state.photos):
                    # These lines MUST be indented more than the 'for' above
                    content = img.getvalue() if hasattr(img, "getvalue") else img.read()
                    
                    # Sanitize the stop name (removes characters like / or : that break filenames)
                    clean_stop = "".join([c for c in selected_stop if c.isalnum() or c in (' ', '_', '-')]).strip()
                    
                    # This creates the new filename format you wanted
                    filename = f"{timestamp}_{clean_stop}_photo{idx+1}.jpg"
                    
                    link, _ = gdrive_upload_file(content, filename, "image/jpeg", FOLDER_ID)
                    photo_links.append(link)
                # --- END OF BLOCK ---
                
                cond_list = list(st.session_state.specific_conditions)
                row = [
                    timestamp, staff_id, selected_depot, selected_route, 
                    selected_stop, condition, activity_category, 
                    "; ".join(cond_list), "; ".join(photo_links),
                    "", "", "", "", st.session_state.time_of_day
                ]
                header = ["Timestamp", "Staff ID", "Depot", "Route", "Bus Stop", "Condition", "Activity", "Situational Conditions", "Photos", "Empty1", "Empty2", "Empty3", "Empty4", "Day/Night"]

                gsheet_id = find_or_create_gsheet("survey_responses", FOLDER_ID)
                append_row_to_gsheet(gsheet_id, row, header)

                st.session_state.update({"activity_category": "", "specific_conditions": set(), "ground_status": "", "other_text": "", "photos": [], "show_success": True, "time_of_day": None})
                st.success("Form Submitted Successfully!")
                time.sleep(2)
                st.rerun()
            except Exception as e:
                st.error(f"Error during submission: {e}")

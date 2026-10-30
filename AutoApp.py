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

# ReportLab imports for PDF generation
from reportlab.lib.pagesizes import letter, landscape
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Image as RLImage, Paragraph
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

# Malaysia timezone setup
try:
    from zoneinfo import ZoneInfo
    MALAYSIA_ZONE = ZoneInfo("Asia/Kuala_Lumpur")
except ImportError:
    import pytz
    MALAYSIA_ZONE = pytz.timezone("Asia/Kuala_Lumpur")

# --------- Page Setup (Neon Green & Black Theme) ---------
st.set_page_config(
    page_title="Application Portal", 
    layout="wide",
    initial_sidebar_state="collapsed"
)

# --------- Custom CSS for Neon Green & Black Theme matching the styling provided & wider layout ---------
st.markdown("""
    <style>
    /* Main Background - Very Dark Gray/Black */
    .stApp {
        background-color: #0B0E0F;
    }

    /* Make the main block container wider to fill the screen as requested */
    .block-container {
        max-width: 80% !important;
        padding-left: 2rem !important;
        padding-right: 2rem !important;
    }
    
    /* Header Style */
    .custom-header {
        background-color: #111516;
        border-bottom: 2px solid #00FF66;
        padding: 15px;
        border-radius: 8px 8px 0px 0px;
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 20px;
    }
    
    .header-title {
        color: #00FF66 !important;
        font-family: 'Courier New', Courier, monospace;
        font-size: 22px;
        font-weight: bold;
        letter-spacing: 2px;
        margin: 0;
    }

    /* Labels - Small, Gray, Uppercase */
    label, .stMarkdown p {
        color: #888888 !important;
        font-family: 'Courier New', Courier, monospace !important;
        text-transform: uppercase;
        font-size: 12px !important;
        font-weight: bold;
    }

    /* Input Fields - Dark with Neon Green Text */
    .stTextInput>div>div>input, .stSelectbox>div>div>div, .stDateInput>div>div>input, .stNumberInput>div>div>input {
        background-color: #111516 !important;
        color: #00FF66 !important;
        border: 1px solid #333333 !important;
        font-family: 'Courier New', Courier, monospace !important;
        border-radius: 4px !important;
    }
    
    /* Success/Error Messages */
    .stAlert {
        background-color: #111516 !important;
        color: #00FF66 !important;
        border: 1px solid #00FF66 !important;
    }

    /* Buttons - Neon Green Outline/Solid */
    .stButton>button {
        background-color: transparent !important;
        color: #00FF66 !important;
        border: 2px solid #00FF66 !important;
        font-family: 'Courier New', Courier, monospace !important;
        font-weight: bold !important;
        transition: 0.3s;
    }
    
    .stButton>button:hover {
        background-color: #00FF66 !important;
        color: #000000 !important;
    }

    /* Target the Download button wrapper for light blue glow */
    div.stDownloadButton > button {
        background-color: transparent !important;
        color: #00E5FF !important;
        border: 2px solid #00E5FF !important;
        box-shadow: 0 0 15px rgba(0, 229, 255, 0.6) !important;
        animation: pulseGlow 2s infinite alternate;
    }

    div.stDownloadButton > button:hover {
        background-color: #00E5FF !important;
        color: #000000 !important;
        box-shadow: 0 0 25px rgba(0, 229, 255, 0.9) !important;
    }

    @keyframes pulseGlow {
        from { box-shadow: 0 0 8px rgba(0, 229, 255, 0.4); }
        to { box-shadow: 0 0 20px rgba(0, 229, 255, 0.8); }
    }

    /* Divider color */
    hr {
        border-color: #1A1E1F !important;
    }

    /* Progress Bar */
    .stProgress > div > div > div > div {
        background-color: #00FF66 !important;
    }
    
    /* Style custom Radio button container to match theme */
    div[data-testid="stRadio"] > label {
        margin-bottom: 8px !important;
    }
    div[data-testid="stRadio"] label p {
        color: #00FF66 !important;
    }

    /* Extra container styling preservation */
    .evc-card {
        border: 2px solid #00FF66;
        border-radius: 10px;
        padding: 10px;
        text-align: center;
        background-color: #111516;
        margin-bottom: 10px;
    }
    [data-testid="stVerticalBlock"] [data-testid="stContainer"] {
        border: 2px solid #00FF66 !important;
        border-radius: 10px !important;
        background-color: #111516 !important;
        padding: 10px !important;
    }

    /* Center Streamlit Dialog / Modal */
    div[data-testid="stModal"] {
        position: fixed !important;
        top: 100% !important;
        left: 30% !important;
        transform: translate(-50%, -50%) !important;
    }
    </style>
    """, unsafe_allow_html=True)

# --- HEADER INJECTION ---
st.markdown("""
    <div class="custom-header">
        <p class="header-title">APPLICATION PORTAL</p>
        <span style="color: #FF3366; font-weight: bold; font-family: sans-serif; cursor: pointer;">✕</span>
    </div>
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
    
    if creds and creds.valid:
        return build('drive', 'v3', credentials=creds), build('sheets', 'v4', credentials=creds)

    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            save_credentials(creds)
            return build('drive', 'v3', credentials=creds), build('sheets', 'v4', credentials=creds)
        except Exception:
            pass

    if os.path.exists(CLIENT_SECRETS_FILE):
        flow = Flow.from_client_secrets_file(CLIENT_SECRETS_FILE, scopes=SCOPES, redirect_uri=REDIRECT_URI)
    else:
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
            
            while len(compressed_bytes) > max_bytes and quality > 20:
                quality -= 15
                output = BytesIO()
                img.save(output, format="JPEG", quality=quality, optimize=True)
                compressed_bytes = output.getvalue()
            
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

def update_row_in_gsheet(sheet_id, row_index, values):
    sheet = sheets_service.spreadsheets()
    sheet.values().update(
        spreadsheetId=sheet_id,
        range=f"A{row_index}",
        valueInputOption="RAW",
        body={"values": [values]}
    ).execute()

def delete_row_from_gsheet(sheet_id, row_index):
    sheet_metadata = sheets_service.spreadsheets().get(spreadsheetId=sheet_id).execute()
    sheet_id_int = sheet_metadata['sheets'][0]['properties']['sheetId']
    
    body = {
        "requests": [
            {
                "deleteDimension": {
                    "range": {
                        "sheetId": sheet_id_int,
                        "dimension": "ROWS",
                        "startIndex": row_index - 1,
                        "endIndex": row_index
                    }
                }
            }
        ]
    }
    sheets_service.spreadsheets().batchUpdate(spreadsheetId=sheet_id, body=body).execute()

def get_all_gsheet_rows(sheet_id):
    sheet = sheets_service.spreadsheets()
    result = sheet.values().get(spreadsheetId=sheet_id, range="A:AD").execute()
    return result.get("values", [])

# --------- PDF Generation Helper ---------
def generate_project_summary_pdf(evcs_models):
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(letter),
        rightMargin=20,
        leftMargin=20,
        topMargin=20,
        bottomMargin=20
    )
    styles = getSampleStyleSheet()

    header_style = ParagraphStyle(
        'HeaderStyle', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=10, alignment=1, textColor=colors.black
    )
    cell_style = ParagraphStyle(
        'CellStyle', parent=styles['Normal'], fontName='Helvetica', fontSize=9, alignment=1, textColor=colors.black
    )
    cell_bold_style = ParagraphStyle(
        'CellBoldStyle', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=9, alignment=0, textColor=colors.black
    )

    num_models = len(evcs_models)
    
    spec_labels = [
        "Brand / Model", "No. of Units", "Rated Input Power (kW AC)",
        "Max. Charging / Output Power\n(AC or DC)", "Mode of Charging", "Connector Type",
        "Output Cable Size / Type\n(Charging Cable)", "No. of Charging Bays",
        "GPS Coordinate Latitude", "GPS Coordinate Longitude"
    ]

    top_header = [Paragraph("<b>PROJECT SUMMARY TABLE (CHARGER SPECIFICATION TABLE)</b>", ParagraphStyle('TitleStyle', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=12, alignment=1))] + [""] * (num_models + 1)
    
    col_headers = [Paragraph("Specification", cell_bold_style)]
    for m in evcs_models:
        brand_name = m.get("brand_model", "").strip() or "EVCS Model"
        col_headers.append(Paragraph(f"<b>{brand_name}</b>", header_style))
    col_headers.append(Paragraph("PICTURE", header_style))

    table_data = [top_header, col_headers]

    for spec_label in spec_labels:
        row = [Paragraph(spec_label.replace('\n', '<br/>'), cell_bold_style)]
        for m in evcs_models:
            if spec_label == "Brand / Model": val = m.get("brand_model", "")
            elif spec_label == "No. of Units": val = m.get("no_of_units", "")
            elif spec_label == "Rated Input Power (kW AC)": val = m.get("rated_input_power", "")
            elif "Max. Charging" in spec_label: val = m.get("max_charging_power", "")
            elif spec_label == "Mode of Charging": val = m.get("mode_of_charging", "")
            elif spec_label == "Connector Type": val = m.get("connector_type", "")
            elif "Output Cable" in spec_label: val = m.get("output_cable_size", "")
            elif spec_label == "No. of Charging Bays": val = m.get("no_of_charging_bays", "")
            elif spec_label == "GPS Coordinate Latitude":
                raw_gps = m.get("gps_lat", "")
                val = raw_gps.split(",")[0].strip() if "," in raw_gps else raw_gps
            elif spec_label == "GPS Coordinate Longitude":
                raw_gps = m.get("gps_lat", "")
                val = raw_gps.split(",")[1].strip() if "," in raw_gps else m.get("gps_lon", "")
            else: val = ""
            row.append(Paragraph(str(val).replace('\n', '<br/>'), cell_style))
        row.append("")
        table_data.append(row)

    picture_element = ""
    for m in evcs_models:
        brand = m.get("brand_model", "")
        if "120" in brand and os.path.exists("DC_120.png"):
            picture_element = RLImage("DC_120.png", width=180, height=330)
            break
        elif "240" in brand and os.path.exists("DC_240.png"):
            picture_element = RLImage("DC_240.png", width=180, height=330)
            break
    if not picture_element and os.path.exists("DC_120.png"):
        picture_element = RLImage("DC_120.png", width=180, height=330)

    if picture_element:
        table_data[2][-1] = picture_element

    spec_col_w = 180
    pic_col_w = 200
    avail_w = 752 - spec_col_w - pic_col_w
    model_col_w = avail_w / num_models if num_models > 0 else avail_w
    col_widths = [spec_col_w] + [model_col_w] * num_models + [pic_col_w]

    t_style = [
        ('SPAN', (0, 0), (num_models + 1, 0)),
        ('BACKGROUND', (0, 0), (num_models + 1, 0), colors.white),
        ('BACKGROUND', (0, 1), (num_models + 1, 1), colors.HexColor('#E0E0E0')),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ('SPAN', (num_models + 1, 2), (num_models + 1, len(table_data) - 1)),
    ]

    t = Table(table_data, colWidths=col_widths)
    t.setStyle(TableStyle(t_style))
    doc.build([t])
    return buffer.getvalue()

# --------- Initialize Session State ---------
defaults = {
    "app_mode": "none",
    "edit_row_idx": None,
    "project_name": "",
    "negeri": "",
    "pbt": "",
    "poskod": "",
    "daerah": "",
    "mukim": "",
    "kawasan": "",
    "taman_tempat": "",
    "jalan": "",
    "no_lot": "",
    "hak_milik": "",
    "kedudukan_premis": "",
    "tarikh_mulatugas_count": 1,
    "evcs_models": [
        {
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
            "is_minimized": False
        }
    ]
}

for key, default in defaults.items():
    if key not in st.session_state:
        st.session_state[key] = default

# --------- Navigation / Sidebar Setup ---------
st.sidebar.markdown("### Navigation Menu")
st.sidebar.markdown("<p style='color: gray; font-size: 0.85rem; margin-top: -10px;'>Go to</p>", unsafe_allow_html=True)

nav_selection = st.sidebar.radio(
    "Go to",
    ["ST Application", "Business License PBT", "Information"],
    label_visibility="collapsed"
)

# --------- 1. MAIN PAGE (ST Application) ---------
if nav_selection == "ST Application":
    st.title("Application Portal")
    
    col1, col2 = st.columns(2)
    with col1:
        if st.button("🆕 New Application", use_container_width=True):
            st.session_state.app_mode = "new"
            st.session_state.edit_row_idx = None
    with col2:
        if st.button("📂 Existing Application", use_container_width=True):
            st.session_state.app_mode = "existing"

    st.markdown("---")

    # ----- NEW APPLICATION FORM -----
    if st.session_state.app_mode == "new":
        edit_mode_title = f"📝 Edit Application (Row {st.session_state.edit_row_idx})" if st.session_state.edit_row_idx else "📝 New Application Submission"
        st.subheader(edit_mode_title)
        st.markdown("#### Project Information")

        project_name = st.text_input("Project name", value=st.session_state.project_name)
        st.session_state.project_name = project_name

        col_pi1, col_pi2, col_pi3 = st.columns(3)
        with col_pi1:
            negeri_options = ["--- Sila pilih ---", "Johor", "Kedah", "Kelantan", "Melaka", "Negeri Sembilan", "Pahang", "Perak", "Perlis", "Pulau Pinang", "Sabah", "Sarawak", "Selangor", "Terengganu", "W.P. Kuala Lumpur", "W.P. Labuan", "W.P. Putrajaya"]
            negeri = st.selectbox("Negeri", negeri_options, index=negeri_options.index(st.session_state.negeri) if st.session_state.negeri in negeri_options else 0)
            st.session_state.negeri = negeri
        with col_pi2:
            pbt_options = ["--- Sila pilih ---", "DBKL", "MBPJ", "MBSA", "MPSJ", "MPKJ", "MBMB", "MBJB", "MBI", "DBKK", "MBMB"]
            pbt = st.selectbox("PBT", pbt_options, index=pbt_options.index(st.session_state.pbt) if st.session_state.pbt in pbt_options else 0)
            st.session_state.pbt = pbt
        with col_pi3:
            poskod = st.text_input("Poskod", value=st.session_state.poskod)
            st.session_state.poskod = poskod

        col_pi4, col_pi5, col_pi6 = st.columns(3)
        with col_pi4:
            daerah = st.text_input("Daerah", value=st.session_state.daerah)
            st.session_state.daerah = daerah
        with col_pi5:
            mukim = st.text_input("Mukim", value=st.session_state.mukim)
            st.session_state.mukim = mukim
        with col_pi6:
            kawasan = st.text_input("Kawasan", value=st.session_state.kawasan)
            st.session_state.kawasan = kawasan

        col_pi7, col_pi8, col_pi9 = st.columns(3)
        with col_pi7:
            taman_tempat = st.text_input("Taman / Tempat", value=st.session_state.taman_tempat)
            st.session_state.taman_tempat = taman_tempat
        with col_pi8:
            jalan = st.text_input("Jalan", value=st.session_state.jalan)
            st.session_state.jalan = jalan
        with col_pi9:
            no_lot = st.text_input("No. Lot / No. Unit / Blok / PT", value=st.session_state.no_lot)
            st.session_state.no_lot = no_lot

        col_pi10, col_pi11 = st.columns(2)
        with col_pi10:
            hak_milik_options = ["--- Sila pilih ---", "MILIK SENDIRI", "SEWA"]
            hak_milik = st.selectbox("Hak Milik Bangunan", hak_milik_options, index=hak_milik_options.index(st.session_state.hak_milik) if st.session_state.hak_milik in hak_milik_options else 0)
            st.session_state.hak_milik = hak_milik
        with col_pi11:
            kedudukan_options = ["--- Sila pilih ---", "LOT TENGAH", "LOT TEPI", "PERSENDIRIAN"]
            kedudukan_premis = st.selectbox("Kedudukan Premis", kedudukan_options, index=kedudukan_options.index(st.session_state.kedudukan_premis) if st.session_state.kedudukan_premis in kedudukan_options else 0)
            st.session_state.kedudukan_premis = kedudukan_premis

        st.markdown("---")
        st.markdown("#### ⚡ EVCS Technical Specifications")

        def select_model_preset(model_idx, preset_type):
            if preset_type == "120":
                brand_val, mcp_val, rip_val, moc_val, conn_val = "Guorui / GRD08-120SDE", "120 kW / DC", "133 kW AC", "Mode 4", "CCS 2"
            elif preset_type == "240":
                brand_val, mcp_val, rip_val, moc_val, conn_val = "Guorui / GRD08-240SDE", "240 kW / DC", "266 kW AC", "Mode 4", "CCS 2"

            st.session_state.evcs_models[model_idx]["brand_model"] = brand_val
            st.session_state.evcs_models[model_idx]["max_charging_power"] = mcp_val
            st.session_state.evcs_models[model_idx]["rated_input_power"] = rip_val
            st.session_state.evcs_models[model_idx]["mode_of_charging"] = moc_val
            st.session_state.evcs_models[model_idx]["connector_type"] = conn_val

            st.session_state[f"brand_model_{model_idx}"] = brand_val
            st.session_state[f"input_max_charging_power_{model_idx}"] = mcp_val
            st.session_state[f"input_rated_input_power_{model_idx}"] = rip_val
            st.session_state[f"mode_of_charging_{model_idx}"] = moc_val
            st.session_state[f"connector_type_{model_idx}"] = conn_val

        active_idx = len(st.session_state.evcs_models) - 1
        col_img1, col_img2, col_img3 = st.columns(3)

        with col_img1:
            with st.container(border=True):
                ic1, ic2, ic3 = st.columns([1.8, 2, 1])
                with ic2:
                    if os.path.exists("DC_120.png"): st.image("DC_120.png", width=90)
                    else: st.warning("DC_120.png not found")
                if st.button("Guorui / GRD08-120SDE", use_container_width=True, key="btn_120"):
                    select_model_preset(active_idx, "120")
                    st.rerun()

        with col_img2:
            with st.container(border=True):
                ic1, ic2, ic3 = st.columns([1.8, 2, 1])
                with ic2:
                    if os.path.exists("DC_240.png"): st.image("DC_240.png", width=90)
                    else: st.warning("DC_240.png not found")
                if st.button("Guorui / GRD08-240SDE", use_container_width=True, key="btn_240"):
                    select_model_preset(active_idx, "240")
                    st.rerun()

        with col_img3:
            with st.container(border=True):
                ic1, ic2, ic3 = st.columns([1.8, 2, 1])
                with ic2:
                    if os.path.exists("add.png"): st.image("add.png", width=90)
                    else: st.warning("add.png not found")
                if st.button("+ add more type", use_container_width=True, key="btn_add_more_type"):
                    st.session_state.evcs_models[active_idx]["is_minimized"] = True
                    st.session_state.evcs_models.append({
                        "brand_model": "", "no_of_units": "", "rated_input_power": "", "max_charging_power": "",
                        "mode_of_charging": "", "connector_type": "", "output_cable_size": "", "no_of_charging_bays": "",
                        "gps_lat": "", "gps_lon": "", "is_minimized": False
                    })
                    st.rerun()

        def remove_evcs_model(model_idx):
            if len(st.session_state.evcs_models) > 1:
                st.session_state.evcs_models.pop(model_idx)
                st.rerun()

        for idx, model in enumerate(st.session_state.evcs_models):
            exact_model_name = model['brand_model'].strip() if model['brand_model'] and model['brand_model'].strip() else f"Model Type {idx + 1} (New)"
            
            if model["is_minimized"]:
                with st.expander(f"🗄️ {exact_model_name} (Click to expand)", expanded=False):
                    c_min1, c_min2 = st.columns(2)
                    with c_min1:
                        st.write(f"**Brand / Model:** {model['brand_model'] or '-'}")
                        st.write(f"**Rated Input Power:** {model['rated_input_power'] or '-'}")
                    with c_min2:
                        st.write(f"**No. of Units:** {model['no_of_units'] or '-'}")
                        st.write(f"**Max. Charging Power:** {model['max_charging_power'] or '-'}")
                    
                    btn_col1, btn_col2 = st.columns([1, 1])
                    with btn_col1:
                        if st.button(f"✏️ Edit Model {idx + 1}", key=f"edit_model_{idx}"):
                            st.session_state.evcs_models[idx]["is_minimized"] = False
                            st.rerun()
                    with btn_col2:
                        if len(st.session_state.evcs_models) > 1:
                            if st.button(f"🗑️ Remove Model {idx + 1}", key=f"remove_min_model_{idx}"):
                                remove_evcs_model(idx)
            else:
                col_title, col_del = st.columns([4, 1])
                with col_title: st.markdown(f"#### ⚙️ Active Model: {exact_model_name}")
                with col_del:
                    if len(st.session_state.evcs_models) > 1:
                        if st.button("🗑️ Remove Model", key=f"remove_active_model_{idx}"):
                            remove_evcs_model(idx)

                col_s1, col_s2 = st.columns(2)
                with col_s1:
                    brand_model = st.text_input("Brand / Model", value=model["brand_model"], key=f"brand_model_{idx}")
                    st.session_state.evcs_models[idx]["brand_model"] = brand_model
                    rated_input_power = st.text_input("Rated Input Power (kW AC)", value=model["rated_input_power"], key=f"input_rated_input_power_{idx}")
                    st.session_state.evcs_models[idx]["rated_input_power"] = rated_input_power
                    mode_of_charging = st.text_input("Mode of Charging", value=model["mode_of_charging"], key=f"mode_of_charging_{idx}")
                    st.session_state.evcs_models[idx]["mode_of_charging"] = mode_of_charging
                    output_cable_size = st.text_input("Output Cable Size / Type (Charging Cable)", value=model["output_cable_size"], key=f"output_cable_size_{idx}")
                    st.session_state.evcs_models[idx]["output_cable_size"] = output_cable_size

                with col_s2:
                    no_of_units = st.text_input("No. of Units", value=model["no_of_units"], key=f"input_no_of_units_{idx}")
                    st.session_state.evcs_models[idx]["no_of_units"] = no_of_units
                    max_charging_power = st.text_input("Max. Charging / Output Power (AC or DC)", value=model["max_charging_power"], key=f"input_max_charging_power_{idx}")
                    st.session_state.evcs_models[idx]["max_charging_power"] = max_charging_power
                    connector_type = st.text_input("Connector Type", value=model["connector_type"], key=f"connector_type_{idx}")
                    st.session_state.evcs_models[idx]["connector_type"] = connector_type

                gps_lat = st.text_input("GPS Coordinate Latitude Longitude", value=model.get("gps_lat", ""), key=f"input_gps_lat_{idx}", placeholder="2.800693, 101.686073")
                st.session_state.evcs_models[idx]["gps_lat"] = gps_lat

        st.markdown("---")
        st.subheader("📋 Application Sections (Bahagian A - G)")

        tab_a, tab_b, tab_c, tab_d, tab_e, tab_f, tab_g = st.tabs([
            "Bahagian A", "Bahagian B", "Bahagian C", "Bahagian D", "Bahagian E", "Bahagian F", "Bahagian G"
        ])

        with tab_a:
            st.markdown("### 📌 BAHAGIAN A : MAKLUMAT PEMOHON")
            bahagian_a_info = st.text_area("Maklumat Pemohon / Catatan Bahagian A:", key="a_info")

        with tab_b:
            st.markdown("### 📌 BAHAGIAN B : AKTIVITI YANG DIJALANKAN")
            pengagihan_check = st.checkbox("Pengagihan", value=True)
            jumlah_keupayaan = st.text_input("*Jumlah keupayaan sistem pengagihan (kW) :", key="b_jumlah_keupayaan")
            kehendak_maksimum = st.text_input("*Kehendak Maksimum (kW) :", key="b_kehendak_maksimum")
            punca_bekalan = st.radio("*Punca bekalan :", ["TNB", "SESB", "Penjanaan Sendiri", "Lain-lain"], key="b_punca_bekalan")

        with tab_c:
            st.markdown("### 📌 BAHAGIAN C : DOKUMEN SOKONGAN & SENARAI SEMAK")
            doc_c_data = {}
            f_syarikat = st.file_uploader("Borang 9 / Sijil Pendaftaran Syarikat", type=["pdf", "png", "jpg", "jpeg", "docx"], key="c_file_syrkat")
            doc_c_data["Syarikat_Borang_9"] = {"file": f_syarikat}
            
            jurutera_mykad = st.text_input("No. MyKad (Jurutera/Kompeten):", key="c_jurutera_mykad")
            jurutera_nama = st.text_input("Nama (Jurutera/Kompeten):", key="c_jurutera_nama")
            jurutera_perakuan = st.text_input("No. Perakuan (Jurutera/Kompeten):", key="c_jurutera_perakuan")

        with tab_d:
            st.markdown("### 📌 BAHAGIAN D")
            bahagian_d_info = st.text_area("Maklumat Bahagian D:", key="d_info")

        with tab_e:
            st.markdown("### 📌 Bahagian E : MAKLUMAT PERMOHONAN")
            e_no_lot = st.text_input("*No. Lot :", key="e_no_lot")
            e_mukim = st.text_input("*Mukim :", key="e_mukim")
            e_daerah = st.text_input("*Daerah :", key="e_daerah")
            e_poskod = st.text_input("*Poskod :", key="e_poskod")
            e_negeri = st.selectbox("*Negeri :", negeri_options, key="e_negeri")

        with tab_f:
            st.markdown("### 📌 Bahagian F : PENGAKUAN PEMOHON")
            f_check1 = st.checkbox("Saya mengaku bahawa maklumat adalah benar di bawah Akta Bekalan Elektrik 1990", key="f_check1")
            f_check2 = st.checkbox("Saya akan melantik orang kompeten untuk menjaga pepasangan", key="f_check2")
            f_check3 = st.checkbox("Saya bersetuju mematuhi terma dan syarat lesen awam", key="f_check3")

        with tab_g:
            st.markdown("### 📌 Bahagian G : PENGESAHAN JURUTERA PROFESIONAL / ORANG KOMPETEN")
            g_aktiviti_option = st.radio("Aktiviti Pengesahan:", ["Pepasangan baru ini telah direkabentuk dan diselia oleh saya", "Pepasangan sedia ada"], key="g_aktiviti_option")
            g_nama = st.text_input("*Nama :", key="g_nama")
            g_no_perakuan = st.text_input("*No. Perakuan :", key="g_no_perakuan")
            g_alamat = st.text_area("*Alamat :", key="g_alamat")

        st.markdown("---")

        with st.form(key="submit_form"):
            col_sub1, col_sub2 = st.columns(2)
            with col_sub1: submit = st.form_submit_button("✅ Submit Application (Save New)")
            with col_sub2: overwrite = st.form_submit_button("💾 Save Overwrite") if st.session_state.edit_row_idx else None

            if submit or overwrite:
                if not project_name.strip():
                    st.warning("❗ Please provide a project name.")
                elif not (f_check1 and f_check2 and f_check3):
                    st.warning("❗ Please complete all declarations in Bahagian F before submitting.")
                else:
                    try:
                        timestamp = datetime.now(MALAYSIA_ZONE).strftime("%Y-%m-%d %H:%M:%S")
                        project_folder_id = get_or_create_project_folder(project_name, FOLDER_ID)

                        evcs_models_json = json.dumps(st.session_state.evcs_models)
                        pdf_bytes = generate_project_summary_pdf(st.session_state.evcs_models)
                        pdf_filename = f"{project_name}_PROJECT SUMMARY.pdf"
                        pdf_link, _ = gdrive_upload_file(pdf_bytes, pdf_filename, "application/pdf", project_folder_id)

                        primary_model = st.session_state.evcs_models[0] if st.session_state.evcs_models else {}

                        row = [
                            timestamp, project_name, negeri, pbt, poskod, daerah, mukim, kawasan,
                            taman_tempat, jalan, no_lot, hak_milik, kedudukan_premis,
                            primary_model.get("brand_model", ""), primary_model.get("no_of_units", ""), 
                            primary_model.get("rated_input_power", ""), primary_model.get("max_charging_power", ""),
                            primary_model.get("mode_of_charging", ""), primary_model.get("connector_type", ""), 
                            primary_model.get("output_cable_size", ""), primary_model.get("no_of_charging_bays", ""),
                            primary_model.get("gps_lat", ""), primary_model.get("gps_lon", ""),
                            evcs_models_json, pdf_link
                        ]

                        header = [
                            "Timestamp", "Project Name", "Negeri", "PBT", "Poskod", "Daerah", "Mukim", "Kawasan",
                            "Taman / Tempat", "Jalan", "No. Lot", "Hak Milik Bangunan", "Kedudukan Premis",
                            "Brand / Model", "No. of Units", "Rated Input Power", "Max. Charging Power",
                            "Mode of Charging", "Connector Type", "Output Cable Size", "No. of Charging Bays",
                            "GPS Latitude", "GPS Longitude", "EVCS All Models (JSON)", "Project Summary PDF Link"
                        ]

                        gsheet_id = find_or_create_gsheet("general_applications", FOLDER_ID)
                        
                        if overwrite and st.session_state.edit_row_idx:
                            update_row_in_gsheet(gsheet_id, st.session_state.edit_row_idx, row)
                            st.success(f"Application Overwritten Successfully (Row {st.session_state.edit_row_idx})!")
                        else:
                            append_row_to_gsheet(gsheet_id, row, header)
                            st.success("New Application Submitted Successfully!")

                        st.session_state.update({"app_mode": "existing", "edit_row_idx": None, "project_name": ""})
                        time.sleep(1.5)
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error during submission: {e}")

    elif st.session_state.app_mode == "existing":
        st.subheader("📁 Existing Applications")
        try:
            gsheet_id = find_or_create_gsheet("general_applications", FOLDER_ID)
            rows = get_all_gsheet_rows(gsheet_id)
            if not rows or len(rows) <= 1:
                st.info("No existing applications found.")
            else:
                data_rows = rows[1:]
                for idx, r in enumerate(data_rows):
                    row_num = idx + 2
                    proj_name = r[1] if len(r) > 1 and r[1] else f"Project (Row {row_num})"
                    timestamp = r[0] if len(r) > 0 and r[0] else "N/A"
                    with st.container(border=True):
                        st.markdown(f"**📂 {proj_name}** | Submitted on: {timestamp}")
        except Exception as e:
            st.error(f"Could not load existing applications: {e}")

elif nav_selection == "Business License PBT":
    st.title("Business License PBT")
    st.info("Management tools for Business License PBT.")

elif nav_selection == "Information":
    st.title("Information")
    st.info("Guidelines and system instructions.")

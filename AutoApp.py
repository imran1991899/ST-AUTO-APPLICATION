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

# Malaysia timezone setup
try:
    from zoneinfo import ZoneInfo
    MALAYSIA_ZONE = ZoneInfo("Asia/Kuala_Lumpur")
except ImportError:
    import pytz
    MALAYSIA_ZONE = pytz.timezone("Asia/Kuala_Lumpur")

# --------- Page Setup ---------
st.set_page_config(page_title="Application Portal", layout="wide")

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

# --------- Initialize Session State ---------
defaults = {
    "app_mode": "none",
    "applicant_name": "",
    "staff_id": "",
    "department": "",
    "project_title": "",
    "priority_level": "Medium",
    "description": "",
    "uploaded_files": [],
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

        applicant_name = st.text_input("👤 Applicant Full Name", value=st.session_state.applicant_name)
        st.session_state.applicant_name = applicant_name

        staff_id = st.text_input("🆔 Staff ID (8 digits)", value=st.session_state.staff_id)
        if staff_id and (not staff_id.isdigit() or len(staff_id) != 8):
            st.warning("⚠️ Staff ID must be exactly 8 digits.")
        st.session_state.staff_id = staff_id

        departments = ["", "Information Technology", "Operations", "Finance", "Human Resources", "Administration", "Marketing"]
        department = st.selectbox(
            "🏢 Department",
            departments,
            index=departments.index(st.session_state.department) if st.session_state.department in departments else 0
        )
        st.session_state.department = department

        project_title = st.text_input("📋 Project / Request Title", value=st.session_state.project_title)
        st.session_state.project_title = project_title

        priorities = ["Low", "Medium", "High", "Urgent"]
        priority_level = st.selectbox(
            "⚡ Priority Level",
            priorities,
            index=priorities.index(st.session_state.priority_level) if st.session_state.priority_level in priorities else 1
        )
        st.session_state.priority_level = priority_level

        description = st.text_area("📄 Project Description & Objectives", value=st.session_state.description, height=150)
        st.session_state.description = description

        st.markdown("**📎 Attach Supporting Documents (Up to 5 files)**")
        uploaded_file = st.file_uploader("Upload file", type=["png", "jpg", "jpeg", "pdf", "docx"], key="file_uploader")
        
        if uploaded_file:
            if uploaded_file not in st.session_state.uploaded_files and len(st.session_state.uploaded_files) < 5:
                st.session_state.uploaded_files.append(uploaded_file)

        if st.session_state.uploaded_files:
            st.subheader("📁 Uploaded Files Preview")
            to_delete = None
            for i, f in enumerate(st.session_state.uploaded_files):
                cols = st.columns([4, 1])
                cols[0].text(f"File #{i + 1}: {f.name}")
                if cols[1].button(f"❌ Remove #{i + 1}", key=f"del_file_{i}"):
                    to_delete = i
            if to_delete is not None:
                st.session_state.uploaded_files.pop(to_delete)
                st.rerun()

        with st.form(key="submit_form"):
            submit = st.form_submit_button("✅ Submit Application")
            if submit:
                if not applicant_name.strip():
                    st.warning("❗ Please enter the applicant's name.")
                elif not staff_id.strip() or len(staff_id) != 8:
                    st.warning("❗ Staff ID must be exactly 8 digits.")
                elif not department:
                    st.warning("❗ Please select a department.")
                elif not project_title.strip():
                    st.warning("❗ Please provide a project title.")
                elif not description.strip():
                    st.warning("❗ Please provide a project description.")
                else:
                    try:
                        timestamp = datetime.now(MALAYSIA_ZONE).strftime("%Y-%m-%d %H:%M:%S")
                        file_links = []
                        
                        for idx, file_obj in enumerate(st.session_state.uploaded_files):
                            content = file_obj.getvalue() if hasattr(file_obj, "getvalue") else file_obj.read()
                            clean_title = "".join([c for c in project_title if c.isalnum() or c in (' ', '_', '-')]).strip()
                            filename = f"{timestamp}_{clean_title}_file{idx+1}{os.path.splitext(file_obj.name)[1]}"
                            
                            mimetype = mimetypes.guess_type(filename)[0] or 'application/octet-stream'
                            link, _ = gdrive_upload_file(content, filename, mimetype, FOLDER_ID)
                            file_links.append(link)
                        
                        row = [
                            timestamp, applicant_name, staff_id, department, 
                            project_title, priority_level, description, "; ".join(file_links)
                        ]
                        header = ["Timestamp", "Applicant Name", "Staff ID", "Department", "Project Title", "Priority", "Description", "Attachments"]

                        gsheet_id = find_or_create_gsheet("general_applications", FOLDER_ID)
                        append_row_to_gsheet(gsheet_id, row, header)

                        st.session_state.update({
                            "applicant_name": "",
                            "staff_id": "",
                            "department": "",
                            "project_title": "",
                            "priority_level": "Medium",
                            "description": "",
                            "uploaded_files": [],
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

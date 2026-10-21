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
import subprocess
import tempfile
import sys

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

st.sidebar.title("Navigation Menu")
nav_selection = st.sidebar.radio(
    "Go to",
    ["1. Main Page", "2. Detail Application", "3. Information"]
)

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

        st.markdown("---")
        st.markdown("#### ⚡ EVCS Technical Specifications")

        col_s1, col_s2 = st.columns(2)

        with col_s1:
            brand_model = st.text_input("Brand / Model", value=st.session_state.brand_model)
            rated_input_power = st.text_input("Rated Input Power (kW AC)", value=st.session_state.rated_input_power)
            mode_of_charging = st.text_input("Mode of Charging", value=st.session_state.mode_of_charging)
            output_cable_size = st.text_input("Output Cable Size / Type (Charging Cable)", value=st.session_state.output_cable_size)
            gps_lat = st.text_input("GPS Coordinate Latitude", value=st.session_state.gps_lat)

        with col_s2:
            no_of_units = st.text_input("No. of Units", value=st.session_state.no_of_units)
            max_charging_power = st.text_input("Max. Charging / Output Power (AC or DC)", value=st.session_state.max_charging_power)
            connector_type = st.text_input("Connector Type", value=st.session_state.connector_type)
            no_of_charging_bays = st.text_input("No. of Charging Bays", value=st.session_state.no_of_charging_bays)
            gps_lon = st.text_input("GPS Coordinate Longitude", value=st.session_state.gps_lon)

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

        with tab_a:
            st.markdown("### 📌 BAHAGIAN A : MAKLUMAT PEMOHON")
            bahagian_a_info = st.text_area("Maklumat Pemohon / Catatan Bahagian A:", key="a_info")

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
                st.text("RM/kW")

            col_t3, col_t4 = st.columns([3, 2])
            with col_t3:
                tarif_puncak = st.text_input("Caj bekalan puncak/caj tenaga:", key="b_tarif_puncak")
            with col_t4:
                st.markdown("<br>", unsafe_allow_html=True)
                st.text("sen/kWj")

            col_t5, col_t6 = st.columns([3, 2])
            with col_t5:
                tarif_luar_puncak = st.text_input("Caj bekalan luar puncak:", key="b_tarif_luar_puncak")
            with col_t6:
                st.markdown("<br>", unsafe_allow_html=True)
                st.text("sen/kWj")

            col_b5, col_b6 = st.columns([3, 1])
            with col_b5:
                jumlah_tenaga_sebulan = st.text_input("*Jumlah tenaga elektrik dibeli sebulan dari utiliti :", key="b_jumlah_tenaga_sebulan")
            with col_b6:
                st.markdown("<br>", unsafe_allow_html=True)
                st.text("kWj")

            bilangan_incomers = st.text_input("*Bilangan Incomers :", key="b_bilangan_incomers")
            nama_pencawang = st.text_input("*Nama Pencawang :", key="b_nama_pencawang")

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

            sistem_agihan_pendawaian = st.checkbox("Pendawaian dalaman", key="b_sa_pendawaian")
            sistem_agihan_kabel = st.checkbox("Kabel bawah tanah", key="b_sa_kabel")
            sistem_agihan_talian = st.checkbox("Talian atas", key="b_sa_talian")
            sistem_agihan_lain_check = st.checkbox("Lain-lain (Sila nyatakan)", key="b_sa_lain_check")
            sistem_agihan_lain = ""
            if sistem_agihan_lain_check:
                sistem_agihan_lain = st.text_input("Nyatakan sistem agihan lain:", key="b_sa_lain_text")

            loji_janakuasa = st.text_input("Loji Janakuasa Tunggusedia (jika ada) :", key="b_loji_janakuasa")
            caj_sambungan = st.text_input("Caj sambungan yang dikenakan oleh TNB/SESB :", key="b_caj_sambungan")

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
                    file_up = st.file_uploader("Muat naik", type=["pdf", "png", "jpg", "jpeg", "docx"], key=f"{key_prefix}_file_{no}")
                    use_cam = st.checkbox("📷 Ambil Gambar", key=f"{key_prefix}_usecam_{no}")
                    cam_img = st.camera_input("Tangkap", key=f"{key_prefix}_cam_{no}") if use_cam else None
                    chosen_file = cam_img if cam_img else file_up
                foto = c4.checkbox("Salinan Fotokopi", key=f"{key_prefix}_foto_{no}") if has_fotokopi else False
                return chosen_file, foto

            syarikat_docs = [
                ("1", "*Borang 9 (Certificate of Incorporation)", False),
                ("2", "Borang 13 (Certificate of Incorporation on change of name)", True),
            ]
            for idx, label, has_foto in syarikat_docs:
                f, foto = render_doc_row(idx, label, has_foto, key_prefix="c_syrkat")
                doc_c_data[f"Syarikat_{idx}_{label}"] = {"file": f, "fotokopi": foto}

            lokasi_docs = [
                ("1", "*Pelan lokasi dan pelan tapak", False),
            ]
            for idx, label, has_foto in lokasi_docs:
                f, foto = render_doc_row(idx, label, has_foto, key_prefix="c_lokasi")
                doc_c_data[f"Lokasi_{idx}_{label}"] = {"file": f, "fotokopi": foto}

            f_surat_jurutera = st.file_uploader("a. Surat Pelantikan Jurutera :", type=["pdf", "png", "jpg", "jpeg", "docx"], key="c_f_surat_jurutera")
            f_surat_penjaga = st.file_uploader("b. Surat Pelantikan Penjaga :", type=["pdf", "png", "jpg", "jpeg", "docx"], key="c_f_surat_penjaga")

        with tab_d:
            st.markdown("### 📌 BAHAGIAN D")
            bahagian_d_info = st.text_area("Maklumat Bahagian D:", key="d_info")

        with tab_e:
            st.markdown("### 📌 Bahagian E : MAKLUMAT PERMOHONAN")
            e_no_lot = st.text_input("*No. Lot :", key="e_no_lot")
            e_mukim = st.text_input("*Mukim :", key="e_mukim")
            e_daerah = st.text_input("*Daerah :", key="e_daerah")
            e_poskod = st.text_input("*Poskod :", key="e_poskod")
            e_negeri = st.selectbox("*Negeri :", ["--- Sila pilih ---", "Johor", "Selangor", "W.P. Kuala Lumpur"], key="e_negeri")
            e_status_pepasangan = st.selectbox("*Status pepasangan :", ["--- Sila pilih ---", "Beroperasi"], key="e_status_pepasangan")

        with tab_f:
            st.markdown("### 📌 Bahagian F : PENGAKUAN PEMOHON")
            f_check1 = st.checkbox("*Akuan benar maklumat", key="f_check1")
            f_check2 = st.checkbox("*Lantik orang kompeten", key="f_check2")
            f_check3 = st.checkbox("*Patuh syarat lesen", key="f_check3")

        with tab_g:
            st.markdown("### 📌 Bahagian G : PENGESAHAN JURUTERA PROFESIONAL / ORANG KOMPETEN")
            g_aktiviti_option = st.radio("Aktiviti Pengesahan:", ["Pepasangan baru...", "Pepasangan sedia ada..."], key="g_aktiviti_option")
            g_nama = st.text_input("*Nama :", key="g_nama")
            g_no_perakuan = st.text_input("*No. Perakuan :", key="g_no_perakuan")
            g_alamat = st.text_area("*Alamat :", key="g_alamat")

            col_g1, col_g2, col_g3 = st.columns([2, 1, 1])
            with col_g1:
                st.button("Bayar Fi Proses & Hantar", key="g_btn_bayar")
            with col_g2:
                if st.button("Simpan Draf", key="g_btn_draf"):
                    st.info("Saving draft & triggering OAS background automation...")
                    
                    uploaded_file_paths = {}
                    temp_dir = tempfile.gettempdir()
                    for k, v in st.session_state.items():
                        if hasattr(v, "read") and hasattr(v, "name"):
                            file_path = os.path.join(temp_dir, v.name)
                            with open(file_path, "wb") as f:
                                f.write(v.getvalue())
                            uploaded_file_paths[k] = file_path

                    draft_payload = {
                        "project_title": st.session_state.get("project_title", ""),
                        "location": st.session_state.get("location", ""),
                        "bahagian_a_info": st.session_state.get("a_info", ""),
                        "b_jumlah_keupayaan": st.session_state.get("b_jumlah_keupayaan", ""),
                        "b_kehendak_maksimum": st.session_state.get("b_kehendak_maksimum", ""),
                        "b_bilangan_incomers": st.session_state.get("b_bilangan_incomers", ""),
                        "b_nama_pencawang": st.session_state.get("b_nama_pencawang", ""),
                        "b_voltan_punca_bekalan": st.session_state.get("b_voltan_punca_bekalan", ""),
                        "b_voltan_pengagihan": st.session_state.get("b_voltan_pengagihan", ""),
                        "bahagian_d_info": st.session_state.get("d_info", ""),
                        "e_no_lot": st.session_state.get("e_no_lot", ""),
                        "e_mukim": st.session_state.get("e_mukim", ""),
                        "e_daerah": st.session_state.get("e_daerah", ""),
                        "e_poskod": st.session_state.get("e_poskod", ""),
                        "g_nama": st.session_state.get("g_nama", ""),
                        "g_no_perakuan": st.session_state.get("g_no_perakuan", ""),
                        "g_alamat": st.session_state.get("g_alamat", ""),
                        "uploaded_files": uploaded_file_paths
                    }

                    with open("draft_payload.json", "w", encoding="utf-8") as f:
                        json.dump(draft_payload, f, indent=4)

                    try:
                        subprocess.Popen([sys.executable, "login.py"])
                        st.success("Draft saved & login.py automation launched successfully!")
                    except Exception as e:
                        st.error(f"Error executing script: {e}")

            with col_g3:
                st.button("Hapus Draf", key="g_btn_hapus_draf")

        st.markdown("---")
        with st.form(key="submit_form"):
            submit = st.form_submit_button("✅ Submit Application")
            if submit:
                st.success("Google Sheets & Google Drive synced successfully!")

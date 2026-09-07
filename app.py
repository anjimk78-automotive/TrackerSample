import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from streamlit_js_eval import get_geolocation
from datetime import datetime, date

# ----------------------------------------------------------------------
# CONFIG
# ----------------------------------------------------------------------
st.set_page_config(page_title="Location Tracker", page_icon="📍", layout="centered")

SHEET_NAME = st.secrets.get("SHEET_NAME", "LocationTracker")   # name of the Google Sheet
WORKSHEET_NAME = st.secrets.get("WORKSHEET_NAME", "Sheet1")    # tab name inside the sheet
COLUMNS = ["Date", "Location Name", "Latitude", "Longitude", "Saved Time"]

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]


# ----------------------------------------------------------------------
# GOOGLE SHEETS CONNECTION
# ----------------------------------------------------------------------
@st.cache_resource(show_spinner=False)
def get_worksheet():
    creds_dict = dict(st.secrets["gcp_service_account"])
    creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
    client = gspread.authorize(creds)

    try:
        sheet = client.open(SHEET_NAME)
    except gspread.SpreadsheetNotFound:
        sheet = client.create(SHEET_NAME)

    try:
        worksheet = sheet.worksheet(WORKSHEET_NAME)
    except gspread.WorksheetNotFound:
        worksheet = sheet.add_worksheet(title=WORKSHEET_NAME, rows=1000, cols=len(COLUMNS))
        worksheet.append_row(COLUMNS)

    # Make sure header row exists
    if worksheet.row_values(1) != COLUMNS:
        worksheet.clear()
        worksheet.append_row(COLUMNS)

    return worksheet


def load_data() -> pd.DataFrame:
    worksheet = get_worksheet()
    records = worksheet.get_all_records()
    if not records:
        return pd.DataFrame(columns=COLUMNS)
    return pd.DataFrame(records)


def save_row(row_date: date, location_name: str, lat: float, lon: float):
    worksheet = get_worksheet()
    saved_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    worksheet.append_row(
        [row_date.strftime("%Y-%m-%d"), location_name, lat, lon, saved_time]
    )


# ----------------------------------------------------------------------
# UI
# ----------------------------------------------------------------------
st.title("📍 Location Tracker")
st.caption("Capture your live GPS location on mobile and save it to Google Sheets.")

# Always call get_geolocation() at the top level, outside any if/else branch —
# the component is known to misbehave when called from inside a conditional block.
_location = get_geolocation()
if _location and _location.get("coords"):
    st.session_state["captured_location"] = {
        "latitude": _location["coords"]["latitude"],
        "longitude": _location["coords"]["longitude"],
    }
elif _location and "error" in _location:
    st.session_state["location_error"] = _location["error"]

section = st.radio(
    "Choose section",
    ["1️⃣ Save a location", "2️⃣ View a saved location"],
    horizontal=True,
)

st.divider()

# ------------------------------------------------------------------
# SECTION 1 — SAVE LOCATION
# ------------------------------------------------------------------
if section.startswith("1"):
    st.subheader("Save New Location")

    captured = st.session_state.get("captured_location")
    loc_error = st.session_state.get("location_error")

    if not captured:
        # Location not granted/captured yet — ask for it first and don't show
        # the form until we actually have it.
        if loc_error and loc_error.get("code") == 1:
            st.error("Location permission was denied. Please turn on location access for this "
                      "site in your phone's browser settings, then reload the page.")
        elif loc_error:
            st.warning(f"Couldn't get your location: {loc_error.get('message', 'unknown error')}")
        else:
            st.info("📡 Please turn on Location on your phone and allow access when your "
                     "browser asks — the form will appear once your location is detected.")
    else:
        # Location already captured in the background — show the form.
        col1, col2 = st.columns(2)
        with col1:
            selected_date = st.date_input("Select Date", value=date.today())
        with col2:
            location_name = st.text_input("Location Name", placeholder="e.g. Home, Office, Site A")

        save_clicked = st.button("💾 Save to Google Sheet", type="primary", use_container_width=True)

        if save_clicked:
            if not location_name.strip():
                st.error("Please enter a location name.")
            else:
                try:
                    save_row(selected_date, location_name.strip(), captured["latitude"], captured["longitude"])
                    st.success("✅ Saved to Google Sheet!")
                    del st.session_state["captured_location"]
                    st.rerun()
                except Exception as e:
                    st.error(f"Failed to save: {e}")

# ------------------------------------------------------------------
# SECTION 2 — VIEW LOCATION BY TIME
# ------------------------------------------------------------------
else:
    st.subheader("View Saved Location")

    try:
        df = load_data()
    except Exception as e:
        st.error(f"Failed to load data from Google Sheet: {e}")
        df = pd.DataFrame(columns=COLUMNS)

    if df.empty:
        st.info("No saved locations yet. Add one in section 1 first.")
    else:
        # Optional filter by date first
        available_dates = sorted(df["Date"].unique(), reverse=True)
        pick_date = st.selectbox("Filter by date (optional)", ["All dates"] + available_dates)

        filtered = df if pick_date == "All dates" else df[df["Date"] == pick_date]

        # Build a friendly label for each saved entry
        filtered = filtered.copy()
        filtered["label"] = (
            filtered["Saved Time"] + "  |  " + filtered["Location Name"] + "  (" + filtered["Date"] + ")"
        )

        selected_label = st.selectbox("Select saved time", filtered["label"].tolist())

        row = filtered[filtered["label"] == selected_label].iloc[0]

        lat = float(row["Latitude"])
        lon = float(row["Longitude"])

        st.write(f"**Location Name:** {row['Location Name']}")
        st.write(f"**Date:** {row['Date']}")
        st.write(f"**Saved Time:** {row['Saved Time']}")
        st.write(f"**Coordinates:** {lat:.6f}, {lon:.6f}")

        st.map(pd.DataFrame([{"lat": lat, "lon": lon}]))

        st.link_button(
            "Open in Google Maps",
            f"https://www.google.com/maps?q={lat},{lon}",
            use_container_width=True,
        )

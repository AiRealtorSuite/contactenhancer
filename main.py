import os
import io
import logging
import requests
import pandas as pd
from fastapi import FastAPI, UploadFile, File
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from tempfile import NamedTemporaryFile

# ===== Config / Keys =====
RAPIDAPI_KEY = os.getenv("RAPIDAPI_KEY", "")
APOLLO_API_KEY = os.getenv("APOLLO_API_KEY", "")

MLS_COL = "MLS Number"
FIRST_COL = "First Name"
LAST_COL  = "Last Name"

# ===== App =====
app = FastAPI(title="AI Contact Enricher")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("contact_enricher")

@app.get("/")
def home():
    return {"message": "AI Contact Enricher API is running"}

@app.post("/upload_csv")
async def upload_csv(file: UploadFile = File(...)):
    try:
        raw = await file.read()
        # Try UTF-8 then Latin-1 for weird CSVs
        try:
            df = pd.read_csv(io.BytesIO(raw))
        except UnicodeDecodeError:
            df = pd.read_csv(io.BytesIO(raw), encoding="latin-1")

        # Validate columns
        missing = [c for c in [MLS_COL, FIRST_COL, LAST_COL] if c not in df.columns]
        if missing:
            return JSONResponse(
                status_code=422,
                content={"error": f"CSV missing required columns: {', '.join(missing)}"}
            )

        enriched_rows = []
        for idx, row in df.iterrows():
            result = {"Email": None, "Phone": None, "Source": None, "LookupStatus": "unattempted"}
            try:
                mls_id = str(row[MLS_COL]).strip() if pd.notna(row[MLS_COL]) else ""
                first  = str(row[FIRST_COL]).strip() if pd.notna(row[FIRST_COL]) else ""
                last   = str(row[LAST_COL]).strip() if pd.notna(row[LAST_COL]) else ""
                full_name = (first + " " + last).strip()

                # 1) Try MLS by MLS Number
                if mls_id:
                    mls_data = fetch_from_mls_api(mls_id)
                    if mls_data:
                        result.update(mls_data)
                        result["Source"] = "MLS"
                        result["LookupStatus"] = "ok"

                # 2) Fallback to Apollo by full name (if not found yet)
                if not result.get("Email") and full_name:
                    apollo_data = fetch_from_apollo_by_name(full_name)
                    if apollo_data:
                        result.update(apollo_data)
                        result["Source"] = "Apollo"
                        result["LookupStatus"] = "ok"

                # If still empty, mark no_data
                if not result.get("Email") and not result.get("Phone"):
                    result["LookupStatus"] = "no_data"

            except Exception as e:
                log.exception(f"Row {idx} error")
                result["LookupStatus"] = f"error: {e}"

            merged = row.to_dict()
            merged.update(result)
            enriched_rows.append(merged)

        out_df = pd.DataFrame(enriched_rows)
        tmp = NamedTemporaryFile(delete=False, suffix=".csv")
        out_df.to_csv(tmp.name, index=False)
        return FileResponse(tmp.name, filename="enriched_contacts.csv", media_type="text/csv")

    except Exception as e:
        log.exception("Upload handler failed")
        return JSONResponse(status_code=500, content={"error": str(e)})

def fetch_from_mls_api(mls_id: str):
    """
    RapidAPI: US Real Estate Listings (Agent lookup by MLS ID).
    Returns dict like {"Email": "...", "Phone": "..."} or None.
    """
    if not RAPIDAPI_KEY:
        return None
    try:
        url = "https://us-real-estate-listings.p.rapidapi.com/agent"
        headers = {
            "x-rapidapi-key": RAPIDAPI_KEY,
            "x-rapidapi-host": "us-real-estate-listings.p.rapidapi.com"
        }
        params = {"mls_id": mls_id}
        r = requests.get(url, headers=headers, params=params, timeout=15)
        if r.status_code == 200:
            data = r.json() or {}
            email = data.get("email") or data.get("agent_email")
            phone = data.get("phone") or data.get("agent_phone")
            if email or phone:
                return {"Email": email, "Phone": phone}
        else:
            log.warning(f"MLS API {r.status_code} for {mls_id}: {r.text[:200]}")
    except Exception as e:
        log.warning(f"MLS API error for {mls_id}: {e}")
    return None

def fetch_from_apollo_by_name(full_name: str):
    """
    Apollo fallback by person name. Returns {"Email": "...", "Phone": "..."} or None.
    """
    if not APOLLO_API_KEY or not full_name:
        return None
    try:
        url = "https://api.apollo.io/v1/mixed_people/search"
        payload = {
            "api_key": APOLLO_API_KEY,
            "person_name": full_name,
            "page": 1,
            "per_page": 1
        }
        r = requests.post(url, json=payload, timeout=20)
        if r.status_code == 200:
            data = r.json() or {}
            people = data.get("people") or []
            if people:
                p = people[0]
                email = p.get("email")
                phone = (p.get("phone_numbers") or [{}])[0].get("number")
                if email or phone:
                    return {"Email": email, "Phone": phone}
        else:
            log.warning(f"Apollo {r.status_code} for {full_name}: {r.text[:200]}")
    except Exception as e:
        log.warning(f"Apollo error for {full_name}: {e}")
    return None

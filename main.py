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

@app.get("/diag")
def diag():
    # helpful quick check without leaking secrets
    status = {
        "has_RAPIDAPI_KEY": bool(RAPIDAPI_KEY),
        "has_APOLLO_API_KEY": bool(APOLLO_API_KEY),
    }
    return status

@app.post("/upload_csv")
@app.post("/upload/")
async def upload_csv(file: UploadFile = File(...)):
    try:
        raw = await file.read()
        try:
            df = pd.read_csv(io.BytesIO(raw))
        except UnicodeDecodeError:
            df = pd.read_csv(io.BytesIO(raw), encoding="latin-1")

        missing = [c for c in [MLS_COL, FIRST_COL, LAST_COL] if c not in df.columns]
        if missing:
            return JSONResponse(status_code=422, content={"error": f"CSV missing required columns: {', '.join(missing)}"})

        enriched_rows = []
        for idx, row in df.iterrows():
            mls_status = "skipped"
            apollo_status = "skipped"
            result = {"Email": None, "Phone": None, "Source": None, "LookupStatus": "unattempted"}

            try:
                mls_id = str(row[MLS_COL]).strip() if pd.notna(row[MLS_COL]) else ""
                first  = str(row[FIRST_COL]).strip() if pd.notna(row[FIRST_COL]) else ""
                last   = str(row[LAST_COL]).strip() if pd.notna(row[LAST_COL]) else ""
                full_name = (first + " " + last).strip()

                # 1) MLS by MLS Number
                if mls_id:
                    data, mls_status = fetch_from_mls_api(mls_id)
                    if data:
                        result.update(data)
                        result["Source"] = "MLS"
                        result["LookupStatus"] = "ok"

                # 2) Apollo by full name (only if still missing)
                if not result.get("Email") and not result.get("Phone") and full_name:
                    data, apollo_status = fetch_from_apollo_by_name(full_name)
                    if data:
                        result.update(data)
                        result["Source"] = "Apollo"
                        result["LookupStatus"] = "ok"

                if not result.get("Email") and not result.get("Phone"):
                    result["LookupStatus"] = "no_data"

            except Exception as e:
                log.exception(f"Row {idx} processing error")
                result["LookupStatus"] = f"error: {e}"

            merged = row.to_dict()
            merged["MLS_Status"] = mls_status
            merged["Apollo_Status"] = apollo_status
            merged.update(result)
            enriched_rows.append(merged)

        out_df = pd.DataFrame(enriched_rows)
        tmp = NamedTemporaryFile(delete=False, suffix=".csv")
        out_df.to_csv(tmp.name, index=False)
        return FileResponse(tmp.name, filename="enriched_contacts.csv", media_type="text/csv")

    except Exception as e:
        log.exception("Upload handler failed")
        return JSONResponse(status_code=500, content={"error": str(e)})

def _extract_email_phone(obj):
    """Best-effort extraction from varied shapes."""
    if not obj: 
        return None
    email = None
    phone = None

    # Direct keys common cases
    for k in ["email", "agent_email", "primary_email"]:
        if isinstance(obj, dict) and obj.get(k):
            email = obj.get(k); break

    # Try phone arrays or strings
    if isinstance(obj, dict):
        if obj.get("phone"): phone = obj.get("phone")
        elif obj.get("agent_phone"): phone = obj.get("agent_phone")
        elif obj.get("primary_phone"): phone = obj.get("primary_phone")
        elif obj.get("phone_numbers"):
            arr = obj.get("phone_numbers") or []
            if arr and isinstance(arr, list):
                phone = (arr[0] or {}).get("number")

    if email or phone:
        return {"Email": email, "Phone": phone}
    return None

def fetch_from_mls_api(mls_id: str):
    """RapidAPI agent lookup by MLS ID -> ({'Email','Phone'}, 'status')."""
    if not RAPIDAPI_KEY:
        return None, "no_key"
    try:
        url = "https://us-real-estate-listings.p.rapidapi.com/agent"
        headers = {
            "x-rapidapi-key": RAPIDAPI_KEY,
            "x-rapidapi-host": "us-real-estate-listings.p.rapidapi.com"
        }
        params = {"mls_id": mls_id}
        r = requests.get(url, headers=headers, params=params, timeout=20)
        if r.status_code == 200:
            data = r.json() or {}
            # Handle nested responses
            # Try direct
            hit = _extract_email_phone(data)
            if not hit:
                # Try 'data' wrapper
                hit = _extract_email_phone(data.get("data")) if isinstance(data, dict) else None
            if not hit:
                # Try list
                if isinstance(data, list) and data:
                    hit = _extract_email_phone(data[0])
                elif isinstance(data, dict):
                    # common list containers
                    for key in ["agents", "results", "items"]:
                        if isinstance(data.get(key), list) and data[key]:
                            hit = _extract_email_phone(data[key][0]); break
            return (hit, "ok" if hit else "no_match")
        else:
            return (None, f"HTTP_{r.status_code}")
    except Exception as e:
        log.warning(f"MLS API error for {mls_id}: {e}")
        return None, f"error:{e}"

def fetch_from_apollo_by_name(full_name: str):
    """
    Apollo fallback by name. Try multiple payload shapes to avoid 422s:
      1) person_name
      2) q_person_name
      3) q_keywords
    """
    if not APOLLO_API_KEY:
        return None, "no_key"

    url = "https://api.apollo.io/v1/mixed_people/search"
    attempts = [
        {"person_name": full_name, "page": 1, "per_page": 1},
        {"q_person_name": full_name, "page": 1, "per_page": 1},
        {"q_keywords": full_name, "page": 1, "per_page": 1},
    ]

    for i, payload in enumerate(attempts, start=1):
        body = {"api_key": APOLLO_API_KEY, **payload}
        try:
            r = requests.post(url, json=body, timeout=30)
            if r.status_code == 200:
                data = r.json() or {}
                people = data.get("people") or []
                if people:
                    p = people[0]
                    email = p.get("email")
                    phone = (p.get("phone_numbers") or [{}])[0].get("number")
                    if email or phone:
                        return {"Email": email, "Phone": phone}, f"ok_variant_{i}"
                # 200 but no people
                # keep trying other variants
            else:
                # record the first failing code for visibility
                code = r.status_code
                try_text = r.text[:200]
                log.warning(f"Apollo {code} on variant {i} for {full_name}: {try_text}")
        except Exception as e:
            log.warning(f"Apollo error on variant {i} for {full_name}: {e}")

    return None, "no_match"

import os
import io
import logging
import requests
import pandas as pd
from fastapi import FastAPI, UploadFile, File
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from tempfile import NamedTemporaryFile

# =======================
# Config / Env
# =======================
APOLLO_API_KEY = os.getenv("APOLLO_API_KEY", "")
# Optional: restrict search by org domain, e.g. "realtor.com"
APOLLO_ORG_DOMAIN = os.getenv("APOLLO_ORG_DOMAIN", "").strip() or None

# Your CSV column names
MLS_COL   = "MLS Number"
FIRST_COL = "First Name"
LAST_COL  = "Last Name"

# =======================
# App + CORS
# =======================
app = FastAPI(title="AI Contact Enricher (Apollo-only)")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("contact_enricher")

# =======================
# Routes
# =======================
@app.get("/")
def home():
    return {"message": "AI Contact Enricher API is running"}

@app.get("/diag")
def diag():
    return {
        "has_APOLLO_API_KEY": bool(APOLLO_API_KEY),
        "apollo_org_domain": APOLLO_ORG_DOMAIN or "(none)"
    }

# Accept both paths so your frontend can use either
@app.post("/upload_csv")
@app.post("/upload/")
async def upload_csv(file: UploadFile = File(...)):
    if not APOLLO_API_KEY:
        return JSONResponse(status_code=500, content={"error": "APOLLO_API_KEY not set on server"})

    try:
        raw = await file.read()
        # Try utf-8, then latin-1
        try:
            df = pd.read_csv(io.BytesIO(raw))
        except UnicodeDecodeError:
            df = pd.read_csv(io.BytesIO(raw), encoding="latin-1")

        missing = [c for c in [MLS_COL, FIRST_COL, LAST_COL] if c not in df.columns]
        if missing:
            return JSONResponse(
                status_code=422,
                content={"error": f"CSV missing required columns: {', '.join(missing)}"}
            )

        enriched_rows = []
        for idx, row in df.iterrows():
            first = str(row[FIRST_COL]).strip() if pd.notna(row[FIRST_COL]) else ""
            last  = str(row[LAST_COL]).strip() if pd.notna(row[LAST_COL]) else ""
            full_name = (first + " " + last).strip()

            result = {
                "Email": None,
                "Phone": None,
                "Source": None,
                "LookupStatus": "unattempted",
                "Apollo_Status": "skipped" if not full_name else "attempted"
            }

            try:
                if full_name:
                    hit, status = apollo_lookup_name(full_name, APOLLO_ORG_DOMAIN)
                    result["Apollo_Status"] = status
                    if hit:
                        result.update(hit)
                        result["Source"] = "Apollo"
                        result["LookupStatus"] = "ok"
                    else:
                        result["LookupStatus"] = "no_data"
                else:
                    result["LookupStatus"] = "no_name"
                    result["Apollo_Status"] = "no_name"

            except Exception as e:
                log.exception(f"Row {idx} Apollo error")
                result["LookupStatus"] = f"error: {e}"
                result["Apollo_Status"] = f"error: {e}"

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

# =======================
# Apollo helper
# =======================
def apollo_lookup_name(full_name: str, org_domain: str | None = None):
    """
    Apollo 'mixed_people/search' with X-Api-Key header (required).
    Tries a few payload shapes to maximize matches.
    Returns ( {'Email','Phone'}, 'status_str' ) or (None, 'no_match')
    """
    url = "https://api.apollo.io/v1/mixed_people/search"
    headers = {"X-Api-Key": APOLLO_API_KEY}  # <-- REQUIRED NOW

    # Build optional org filter (must be in JSON, not querystring)
    org_filter = {"q_organization_domains": [org_domain]} if org_domain else {}

    attempts = [
        {"person_name": full_name, "page": 1, "per_page": 1, **org_filter},
        {"q_person_name": full_name, "page": 1, "per_page": 1, **org_filter},
        {"q_keywords": full_name, "page": 1, "per_page": 1, **org_filter},
    ]

    for i, payload in enumerate(attempts, start=1):
        try:
            r = requests.post(url, json=payload, headers=headers, timeout=30)
            if r.status_code == 200:
                data = r.json() or {}
                people = data.get("people") or []
                if people:
                    p = people[0]
                    email = p.get("email")
                    phone = (p.get("phone_numbers") or [{}])[0].get("number")
                    if email or phone:
                        return {"Email": email, "Phone": phone}, f"ok_variant_{i}"
                # 200 but no results — try next variant
            else:
                # Log first ~300 chars for debug, keep going
                log.warning(f"Apollo {r.status_code} on variant {i} for {full_name}: {r.text[:300]}")
        except Exception as e:
            log.warning(f"Apollo exception on variant {i} for {full_name}: {e}")

    return None, "no_match"

from fastapi import FastAPI, UploadFile, File
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from starlette.requests import Request

import pandas as pd
import os
import shutil
import uuid
import requests
import json
import time

app = FastAPI()

templates = Jinja2Templates(directory="templates")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

APOLLO_API_KEY = "xIx_O2UpDUlm8QxWMlWCMA"

@app.get("/", response_class=HTMLResponse)
async def form_get(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

def apollo_lookup(first_name, last_name):
    url = "https://api.apollo.io/v1/mixed_people/search"
    headers = {
        "Cache-Control": "no-cache",
        "Content-Type": "application/json",
        "X-Api-Key": APOLLO_API_KEY
    }

    payload = {
        "q_organization_domains": [],
        "page": 1,
        "person_titles": ["Realtor"],
        "display_mode": "enriched",
        "person_first_name": first_name.strip(),
        "person_last_name": last_name.strip()
    }

    try:
        response = requests.post(url, headers=headers, data=json.dumps(payload), timeout=10)
        if response.status_code == 200:
            results = response.json().get("people", [])
            if results:
                person = results[0]
                email = person.get("email", "")
                phone = person.get("phone_number", "")
                print(f"✅ Found: {first_name} {last_name} | 📞 {phone} | 📧 {email}")
                return phone or "", email or ""
            else:
                print(f"⚠️ No match found for {first_name} {last_name}")
        else:
            print(f"❌ Apollo error for {first_name} {last_name}: {response.status_code} {response.text}")
    except Exception as e:
        print(f"❌ Exception for {first_name} {last_name}: {e}")
    return "", ""

@app.post("/", response_class=HTMLResponse)
async def handle_upload(request: Request, file: UploadFile = File(...)):
    temp_file = f"/tmp/temp_{uuid.uuid4().hex}.csv"
    with open(temp_file, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    df = pd.read_csv(temp_file)

    df["Enriched Agent Phone"] = ""
    df["Enriched Agent Email"] = ""

    for i, row in df.iterrows():
        first_name = str(row.get("First Name", "")).strip()
        last_name = str(row.get("Last Name", "")).strip()
        print(f"🔍 Searching for {first_name} {last_name} in ...")
        phone, email = apollo_lookup(first_name, last_name)
        df.at[i, "Enriched Agent Phone"] = phone
        df.at[i, "Enriched Agent Email"] = email
        time.sleep(1.5)  # stay under rate limit

    enriched_file = f"/tmp/enriched_{uuid.uuid4().hex}.csv"
    df.to_csv(enriched_file, index=False)
    print(f"✅ File saved: {enriched_file}")

    os.remove(temp_file)

    return HTMLResponse(
        content=f"""
        <html><body style='text-align:center; font-family:sans-serif;'>
            <h2>✅ Enrichment Complete</h2>
            <a href='/download/{os.path.basename(enriched_file)}' download>Download Enriched CSV</a>
        </body></html>
        """,
        status_code=200
    )

@app.get("/download/{filename}")
async def download_file(filename: str):
    filepath = f"/tmp/{filename}"
    if not os.path.exists(filepath):
        return JSONResponse(status_code=404, content={"error": "File not found"})
    print(f"⬇️ Serving file: {filepath}")
    response = FileResponse(path=filepath, filename=filename, media_type="text/csv")
    @response.call_on_close
    def cleanup():
        try:
            os.remove(filepath)
            print(f"🧹 Deleted file after download: {filepath}")
        except Exception as e:
            print(f"⚠️ Failed to delete file: {e}")
    return response

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
import time

# 🔑 Your Apollo API Key (replace if needed)
APOLLO_API_KEY = "xIx_O2UpDUlm8QxWMlWCMA"

app = FastAPI()
templates = Jinja2Templates(directory="templates")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/", response_class=HTMLResponse)
async def form_get(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


def enrich_with_apollo(first_name, last_name, location=None):
    headers = {
        "Cache-Control": "no-cache",
        "Content-Type": "application/json",
        "x-api-key": APOLLO_API_KEY,
    }

    params = {
        "q_organization_domains": [],
        "person_name": f"{first_name} {last_name}".strip(),
        "per_page": 1,
    }

    if location:
        params["person_locations"] = [location]

    try:
        response = requests.post(
            "https://api.apollo.io/api/v1/mixed_people/search",
            json=params,
            headers=headers,
            timeout=10
        )
        response.raise_for_status()
        data = response.json()

        if data.get("people"):
            person = data["people"][0]
            phone = person.get("phone_number")
            email = person.get("email")
            print(f"✅ Found: {first_name} {last_name} | 📞 {phone} | 📧 {email}")
            return phone or "", email or ""
        else:
            print(f"⚠️ No match found for {first_name} {last_name}")
            return "", ""
    except Exception as e:
        print(f"❌ Apollo error for {first_name} {last_name}: {e}")
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
        location = str(row.get("Property Address", "")).strip()
        print(f"🔍 Searching for {first_name} {last_name} in {location}...")

        phone, email = enrich_with_apollo(first_name, last_name, location)
        df.at[i, "Enriched Agent Phone"] = phone
        df.at[i, "Enriched Agent Email"] = email

        time.sleep(1)  # throttle just to be safe

    enriched_file = f"/tmp/enriched_{uuid.uuid4().hex}.csv"
    df.to_csv(enriched_file, index=False)

    print(f"✅ File saved as: {enriched_file}")

    return HTMLResponse(
        content=f"""
        <html>
        <body style='text-align:center; font-family:sans-serif;'>
            <h2>✅ Enrichment Complete</h2>
            <a href='/download/{os.path.basename(enriched_file)}' download>Download Enriched CSV</a>
        </body>
        </html>
        """,
        status_code=200,
    )


@app.get("/download/{filename}")
async def download_file(filename: str):
    file_path = f"/tmp/{filename}"
    if not os.path.exists(file_path):
        return JSONResponse(status_code=404, content={"error": f"File '{filename}' not found."})

    print(f"⬇️ Serving file: {file_path}")
    response = FileResponse(path=file_path, filename=filename, media_type="text/csv")
    
    @response.call_on_close
    def cleanup():
        try:
            os.remove(file_path)
            print(f"🧹 Deleted file after download: {file_path}")
        except Exception as e:
            print(f"⚠️ Error deleting file: {e}")
    
    return response

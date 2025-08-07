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

def search_apollo(name):
    url = "https://api.apollo.io/api/v1/mixed_people/search"
    headers = {
        "Cache-Control": "no-cache",
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Api-Key": APOLLO_API_KEY
    }

    payload = {
        "person_name": name,
        "contact_info_required": True,  # 💥 Unlock contact info
        "page": 1,
        "per_page": 1
    }

    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=15)
        data = resp.json()

        if not data.get("people"):
            print(f"⚠️ No match found for {name}")
            return "", ""

        person = data["people"][0]
        email = person.get("email") or ""
        phone = person.get("phone_number") or ""

        print(f"✅ Found: {name} | 📞 {phone or 'None'} | 📧 {email or 'None'}")
        return phone, email

    except Exception as e:
        print(f"❌ Apollo API error for {name}: {e}")
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
        first = str(row.get("Agent First Name", "")).strip()
        last = str(row.get("Agent Last Name", "")).strip()
        full_name = f"{first} {last}".strip()

        print(f"🔍 Searching for {full_name} in ...")
        phone, email = search_apollo(full_name)
        df.at[i, "Enriched Agent Phone"] = phone
        df.at[i, "Enriched Agent Email"] = email
        time.sleep(1)

    enriched_file = f"/tmp/enriched_{uuid.uuid4().hex}.csv"
    df.to_csv(enriched_file, index=False)
    print(f"✅ File saved: {enriched_file}")

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

    # Schedule file deletion after response
    @response.call_on_close
    def cleanup():
        os.remove(file_path)
        print(f"🧹 Deleted file after download: {file_path}")

    return response

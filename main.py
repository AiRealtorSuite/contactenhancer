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
APOLLO_URL = "https://api.apollo.io/api/v1/mixed_people/search"

def query_apollo(name):
    print(f"🔍 Searching for {name} in Apollo...")

    headers = {
        "Cache-Control": "no-cache",
        "Content-Type": "application/json",
        "X-Api-Key": APOLLO_API_KEY,
    }

    payload = {
        "person_name": name,
        "contact_info_required": True
    }

    try:
        res = requests.post(APOLLO_URL, headers=headers, json=payload, timeout=15)
        data = res.json()

        if data.get("people"):
            person = data["people"][0]
            email = person.get("email", "")
            phone = person.get("phone", "")
            print(f"✅ Found: {person.get('full_name')} | 📞 {phone or 'None'} | 📧 {email or 'None'}")
            return phone or "", email or ""
        else:
            print(f"❌ No Apollo match for {name}")
    except Exception as e:
        print(f"❌ Apollo error for {name}: {e}")
    return "", ""

@app.get("/", response_class=HTMLResponse)
async def form_get(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

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
        phone, email = query_apollo(full_name)
        df.at[i, "Enriched Agent Phone"] = phone
        df.at[i, "Enriched Agent Email"] = email
        time.sleep(1.2)

    enriched_file = f"/tmp/enriched_{uuid.uuid4().hex}.csv"
    df.to_csv(enriched_file, index=False)
    print(f"✅ Enriched CSV saved: {enriched_file}")

    os.remove(temp_file)

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
    print(f"📁 Checking for file at: {file_path}")

    if not os.path.exists(file_path):
        return JSONResponse(status_code=404, content={"error": f"File '{filename}' not found."})

    print(f"⬇️ Serving file: {file_path}")
    response = FileResponse(path=file_path, filename=filename, media_type="text/csv")

    @response.call_on_close
    def cleanup():
        os.remove(file_path)
        print(f"🧹 Deleted file after download: {file_path}")

    return response

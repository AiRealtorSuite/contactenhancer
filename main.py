from fastapi import FastAPI, UploadFile, File
from fastapi.responses import FileResponse, HTMLResponse
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


def search_apollo_contact(first_name, last_name):
    try:
        url = "https://api.apollo.io/v1/mixed_people/search"
        headers = {
            "Cache-Control": "no-cache",
            "Content-Type": "application/json",
        }
        payload = {
            "api_key": APOLLO_API_KEY,
            "q_keywords": f"{first_name} {last_name}",
            "contact_info_required": True
        }

        response = requests.post(url, json=payload, headers=headers)
        response.raise_for_status()
        data = response.json()

        if data.get("people"):
            person = data["people"][0]
            email = person.get("email", "")
            phone = person.get("direct_phone", "") or person.get("mobile_phone", "") or ""
            print(f"✅ Found: {first_name} {last_name} | \U0001F4DE {phone} | \U0001F4E7 {email}")
            return phone, email
        else:
            print(f"⚠️ No match found for {first_name} {last_name}")
    except Exception as e:
        print(f"❌ Apollo error for {first_name} {last_name}: {e}")
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
        first_name = str(row.get("First Name", "")).strip()
        last_name = str(row.get("Last Name", "")).strip()
        if not first_name or not last_name:
            print(f"⚠️ Missing name at row {i}")
            continue

        print(f"🔍 Searching for {first_name} {last_name} in ...")
        phone, email = search_apollo_contact(first_name, last_name)
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
        return HTMLResponse(content="<h3>❌ File not found.</h3>", status_code=404)

    print(f"⬇️ Serving file: {file_path}")
    response = FileResponse(path=file_path, filename=filename, media_type="text/csv")
    return response

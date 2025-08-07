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

# Apollo API Key
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


def query_apollo(first_name, last_name, city_state):
    url = "https://api.apollo.io/v1/mixed_people/search"
    headers = {
        "Cache-Control": "no-cache",
        "Content-Type": "application/json",
        "X-Api-Key": APOLLO_API_KEY
    }
    payload = {
        "person_first_name": first_name,
        "person_last_name": last_name,
        "person_city": city_state.split(",")[0] if "," in city_state else city_state,
        "person_titles": ["Realtor", "Real Estate Agent", "Broker"],
        "page": 1
    }

    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=10)
        data = resp.json()
        people = data.get("people", [])
        if people:
            person = people[0]
            email = person.get("email")
            phone = person.get("direct_phone") or person.get("mobile_phone")
            print(f"✅ Apollo Match for {first_name} {last_name}: {email}, {phone}")
            return phone or "", email or ""
        else:
            print(f"❌ No Apollo match for {first_name} {last_name}")
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
        first = str(row.get("First Name", "")).strip()
        last = str(row.get("Last Name", "")).strip()
        address = str(row.get("Property Address", "")).strip()

        if not first or not last:
            print(f"⚠️ Missing name for row {i}. Skipping.")
            continue

        print(f"🔍 Searching for {first} {last} in {address}...")
        phone, email = query_apollo(first, last, address)
        df.at[i, "Enriched Agent Phone"] = phone
        df.at[i, "Enriched Agent Email"] = email
        time.sleep(1)

    enriched_file = f"/tmp/enriched_{uuid.uuid4().hex}.csv"
    df.to_csv(enriched_file, index=False)

    print(f"✅ File saved as: {enriched_file}")

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
    if not os.path.exists(file_path):
        return JSONResponse(status_code=404, content={"error": f"File '{filename}' not found."})
    print(f"⬇️ Serving file: {file_path}")
    response = FileResponse(path=file_path, filename=filename, media_type="text/csv")

    @response.call_on_close
    def cleanup():
        print(f"🧹 Deleted file after download: {file_path}")
        try:
            os.remove(file_path)
        except Exception as e:
            print(f"Failed to delete file: {e}")

    return response

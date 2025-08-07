from fastapi import FastAPI, UploadFile, File
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.background import BackgroundTask

import pandas as pd
import os
import shutil
import uuid
import requests
from bs4 import BeautifulSoup
import time
import asyncio

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


def scrape_contact_info(agent_name, city_state):
    # Prepare slug for Realtor.com profile URL
    city_slug = city_state.lower().replace(",", "").replace(" ", "-")
    name_slug = agent_name.lower().replace(",", "").replace(".", "").replace(" ", "-")
    profile_url = f"https://www.realtor.com/realestateagents/{city_slug}/{name_slug}"

    headers = {"User-Agent": "Mozilla/5.0"}
    print(f"🌐 Checking Realtor.com profile: {profile_url}")

    try:
        resp = requests.get(profile_url, headers=headers, timeout=10)
        soup = BeautifulSoup(resp.text, "html.parser")

        email = None
        phone = None

        for tag in soup.find_all(text=True):
            if "@" in tag and ".com" in tag:
                email = tag.strip()
            if any(x in tag for x in ["(", ")", "-", "."]):
                digits = ''.join(c for c in tag if c.isdigit())
                if len(digits) >= 10:
                    phone = tag.strip()
            if email and phone:
                break

        print(f"📞 Phone: {phone or 'None'}, 📧 Email: {email or 'None'}")
        return phone or "", email or ""
    except Exception as e:
        print(f"❌ Error accessing profile: {e}")
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
        agent_name = str(row.get("Agent Name", "")).strip() or f"{first} {last}".strip()
        address = str(row.get("Property Address", "")).strip()

        print(f"🔍 Searching for {agent_name} in {address}...")
        phone, email = scrape_contact_info(agent_name, address)
        df.at[i, "Enriched Agent Phone"] = phone
        df.at[i, "Enriched Agent Email"] = email
        time.sleep(2)

    enriched_basename = f"enriched_{uuid.uuid4().hex}.csv"
    enriched_path = f"/tmp/{enriched_basename}"
    df.to_csv(enriched_path, index=False)

    print(f"✅ File saved as: {enriched_path}")
    os.remove(temp_file)

    return HTMLResponse(
        content=f"""
        <html>
        <body style='text-align:center; font-family:sans-serif;'>
            <h2>✅ Enrichment Complete</h2>
            <a href='/download/{enriched_basename}' download>Download Enriched CSV</a>
        </body>
        </html>
        """,
        status_code=200,
    )


# 🧹 Delayed deletion for safe streaming
async def delayed_remove(file_path):
    await asyncio.sleep(1)
    try:
        os.remove(file_path)
        print(f"🧹 Deleted file after download: {file_path}")
    except Exception as e:
        print(f"⚠️ Could not delete file: {file_path} - {e}")


@app.get("/download/{filename}")
async def download_file(filename: str):
    file_path = f"/tmp/{filename}"
    if not os.path.exists(file_path):
        print(f"🚫 File not found: {file_path}")
        return JSONResponse(status_code=404, content={"error": f"File '{filename}' not found."})

    print(f"⬇️ Serving file: {file_path}")
    return FileResponse(
        path=file_path,
        filename="enriched_contacts.csv",
        media_type="text/csv",
        background=BackgroundTask(delayed_remove, file_path)
    )

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
from bs4 import BeautifulSoup
import time

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
    query = f"{agent_name} realtor {city_state} site:realtor.com"
    headers = {"User-Agent": "Mozilla/5.0"}
    url = f"https://www.google.com/search?q={requests.utils.quote(query)}"

    try:
        resp = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(resp.text, "html.parser")
        links = [a['href'] for a in soup.select('a[href^="http"]') if 'realtor.com' in a['href']]
        if links:
            profile_url = links[0]
            profile_resp = requests.get(profile_url, headers=headers, timeout=10)
            profile_soup = BeautifulSoup(profile_resp.text, "html.parser")

            email = None
            phone = None
            for tag in profile_soup.find_all(text=True):
                if "@" in tag and ".com" in tag:
                    email = tag.strip()
                if any(x in tag for x in ["(", ")", "- ", "-", "."]):
                    digits = ''.join(c for c in tag if c.isdigit())
                    if len(digits) >= 10:
                        phone = tag.strip()
                if email and phone:
                    break
            return phone or "", email or ""
    except Exception as e:
        print(f"Error: {e}")
    return "", ""


@app.post("/", response_class=HTMLResponse)
async def handle_upload(request: Request, file: UploadFile = File(...)):
    temp_file = f"temp_{uuid.uuid4().hex}.csv"
    with open(temp_file, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    df = pd.read_csv(temp_file)

    df["Enriched Agent Phone"] = ""
    df["Enriched Agent Email"] = ""

    for i, row in df.iterrows():
        agent_name = str(row.get("Agent Name", ""))
        address = str(row.get("Property Address", ""))
        print(f"🔍 Searching for {agent_name} in {address}...")
        phone, email = scrape_contact_info(agent_name, address)
        df.at[i, "Enriched Agent Phone"] = phone
        df.at[i, "Enriched Agent Email"] = email
        time.sleep(2)

    enriched_file = f"enriched_{uuid.uuid4().hex}.csv"
    df.to_csv(enriched_file, index=False)

    print(f"✅ File saved as: {enriched_file}")

    os.remove(temp_file)

    return HTMLResponse(
        content=f"""
        <html>
        <body style='text-align:center; font-family:sans-serif;'>
            <h2>✅ Enrichment Complete</h2>
            <a href='/download/{enriched_file}' download>Download Enriched CSV</a>
        </body>
        </html>
        """,
        status_code=200,
    )


@app.get("/download/{filename}")
async def download_file(filename: str):
    if not os.path.exists(filename):
        return JSONResponse(status_code=404, content={"error": f"File '{filename}' not found."})
    print(f"⬇️ Serving file: {filename}")
    return FileResponse(
        path=filename,
        filename="enriched_contacts.csv",  # Consistent name for download
        media_type="text/csv"
    )

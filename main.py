from fastapi import FastAPI, UploadFile, File, Request
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.templating import Jinja2Templates
from dotenv import load_dotenv
import os
import pandas as pd
import requests
from datetime import datetime
from typing import List
import io

load_dotenv()

app = FastAPI()

# Removed: static directory mounting
# app.mount("/static", StaticFiles(directory="static"), name="static")

templates = Jinja2Templates(directory="templates")

APOLLO_API_KEY = os.getenv("APOLLO_API_KEY")

def enrich_contact(first_name, last_name):
    print(f"🔍 Searching Apollo for: {first_name} {last_name}")
    url = "https://api.apollo.io/v1/mixed_people/search"
    headers = {"Cache-Control": "no-cache", "Content-Type": "application/json"}
    payload = {
        "api_key": APOLLO_API_KEY,
        "q_organization_domains": [],
        "page": 1,
        "person_titles": [],
        "prospect_person_name": f"{first_name} {last_name}"
    }
    try:
        response = requests.post(url, json=payload, headers=headers)
        response.raise_for_status()
        data = response.json()
        people = data.get("people", [])
        if people:
            person = people[0]
            email = person.get("email")
            phone = person.get("direct_phone")
            return email, phone
    except Exception as e:
        print(f"❌ Apollo API error for {first_name} {last_name}: {e}")
    return None, None

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.post("/enrich")
async def enrich(file: UploadFile = File(...)):
    df = pd.read_csv(file.file)
    enriched_rows = []
    for _, row in df.iterrows():
        first_name = str(row.get("First Name", "")).strip()
        last_name = str(row.get("Last Name", "")).strip()
        if not first_name or not last_name:
            enriched_rows.append({**row, "Email": "", "Phone": ""})
            continue
        email, phone = enrich_contact(first_name, last_name)
        enriched_row = {**row, "Email": email or "", "Phone": phone or ""}
        enriched_rows.append(enriched_row)

    enriched_df = pd.DataFrame(enriched_rows)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_filename = f"enriched_{timestamp}.csv"
    output_path = f"/tmp/{output_filename}"
    enriched_df.to_csv(output_path, index=False)
    return FileResponse(output_path, media_type='text/csv', filename=output_filename)

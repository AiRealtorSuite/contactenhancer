import os
import csv
import time
import requests
from fastapi import FastAPI, File, UploadFile, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from starlette.responses import FileResponse
import pandas as pd

app = FastAPI()
templates = Jinja2Templates(directory="templates")

APOLLO_API_KEY = os.getenv("APOLLO_API_KEY", "tSJVEfGeRu_7Wyjgl2Laxg")

def search_apollo(full_name):
    url = "https://api.apollo.io/v1/mixed_people/search"
    headers = {"Cache-Control": "no-cache", "Content-Type": "application/json"}
    params = {
        "api_key": APOLLO_API_KEY,
        "q_organization_domains": "",
        "person_name": full_name,
        "page": 1
    }

    try:
        response = requests.post(url, json=params, headers=headers)
        response.raise_for_status()
        data = response.json()
        if data.get("people"):
            person = data["people"][0]
            return {
                "email": person.get("email"),
                "phone": person.get("phone"),
                "title": person.get("title"),
                "company": person.get("organization", {}).get("name")
            }
    except Exception as e:
        print(f"❌ Apollo API error for {full_name}: {e}")
    return {}

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.post("/")
async def enrich_file(file: UploadFile = File(...)):
    contents = await file.read()
    df = pd.read_csv(pd.io.common.BytesIO(contents))

    enriched_data = []
    for _, row in df.iterrows():
        full_name = str(row.get("Name", "")).strip()
        print(f"🔍 Searching Apollo for: {full_name}")
        if not full_name:
            continue

        enriched = search_apollo(full_name)
        enriched_row = row.to_dict()
        enriched_row.update(enriched)
        enriched_data.append(enriched_row)
        time.sleep(1.2)  # Respect rate limits

    enriched_df = pd.DataFrame(enriched_data)
    output_path = "/mnt/data/enriched_contacts_apollo.csv"
    enriched_df.to_csv(output_path, index=False)
    print(f"✅ Enriched file saved: {output_path}")
    return FileResponse(output_path, filename="enriched_contacts_apollo.csv")


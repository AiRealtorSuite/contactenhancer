import os
import csv
import requests
from fastapi import FastAPI, Request, UploadFile, Form
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
import pandas as pd
from dotenv import load_dotenv

load_dotenv()

app = FastAPI()
templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")

APOLLO_API_KEY = os.getenv("APOLLO_API_KEY")

@app.get("/", response_class=HTMLResponse)
async def read_index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.post("/")
async def enrich_file(file: UploadFile):
    df = pd.read_csv(file.file)

    enriched_data = []
    for _, row in df.iterrows():
        first_name = row.get("First Name", "").strip()
        last_name = row.get("Last Name", "").strip()
        mls_number = row.get("MLS Number", "")
        address = row.get("Address (full)", "")

        if not first_name or not last_name:
            print(f"⏭️ Skipping row with missing name: MLS {mls_number}")
            enriched_data.append(row)
            continue

        print(f"🔍 Searching Apollo for: {first_name} {last_name}")
        try:
            response = requests.post(
                "https://api.apollo.io/v1/mixed_people/search",
                headers={"Cache-Control": "no-cache"},
                json={
                    "api_key": APOLLO_API_KEY,
                    "q_organization_domains": [],
                    "person_titles": [],
                    "page": 1,
                    "per_page": 1,
                    "first_name": first_name,
                    "last_name": last_name
                }
            )
            response.raise_for_status()
            results = response.json().get("people", [])

            if results:
                person = results[0]
                row["Apollo Name"] = f"{person.get('first_name')} {person.get('last_name')}"
                row["Apollo Email"] = person.get("email", "")
                row["Apollo Title"] = person.get("title", "")
                row["Apollo Org"] = person.get("organization", {}).get("name", "")
                row["Apollo Phone"] = person.get("phone_numbers", [{}])[0].get("raw_number", "")
                print(f"✅ Found: {row['Apollo Name']}")
            else:
                print(f"❌ No results for {first_name} {last_name}")
        except Exception as e:
            print(f"❌ Apollo error for {first_name} {last_name}: {e}")
        
        enriched_data.append(row)

    enriched_df = pd.DataFrame(enriched_data)
    output_path = "/tmp/enriched_output.csv"
    enriched_df.to_csv(output_path, index=False)
    print(f"✅ Enriched file saved: {output_path}")

    return FileResponse(output_path, filename="enriched_contacts.csv", media_type="text/csv")

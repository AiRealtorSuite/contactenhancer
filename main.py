import os
import csv
import io
import requests
import pandas as pd
from fastapi import FastAPI, UploadFile, File
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from tempfile import NamedTemporaryFile

# API Keys
RAPIDAPI_KEY = os.getenv("RAPIDAPI_KEY")
APOLLO_API_KEY = os.getenv("APOLLO_API_KEY")

app = FastAPI()

# Allow all origins (adjust if needed)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def home():
    return {"message": "AI Contact Enricher API is running"}

@app.post("/upload_csv")
async def upload_csv(file: UploadFile = File(...)):
    try:
        contents = await file.read()
        df = pd.read_csv(io.BytesIO(contents))

        if "MLS_ID" not in df.columns:
            return {"error": "CSV must contain 'MLS_ID' column"}

        enriched_data = []

        for _, row in df.iterrows():
            mls_id = str(row["MLS_ID"]).strip()
            contact_info = await get_contact_info(mls_id)
            enriched_row = row.to_dict()
            enriched_row.update(contact_info)
            enriched_data.append(enriched_row)

        enriched_df = pd.DataFrame(enriched_data)
        output_file = NamedTemporaryFile(delete=False, suffix=".csv")
        enriched_df.to_csv(output_file.name, index=False)

        return FileResponse(output_file.name, filename="enriched_contacts.csv", media_type="text/csv")

    except Exception as e:
        return {"error": str(e)}

async def get_contact_info(mls_id):
    """Try MLS API first, then Apollo as fallback."""
    mls_data = fetch_from_mls_api(mls_id)
    if mls_data:
        return mls_data
    apollo_data = fetch_from_apollo(mls_id)
    return apollo_data or {}

def fetch_from_mls_api(mls_id):
    try:
        url = "https://us-real-estate-listings.p.rapidapi.com/agent"
        headers = {
            "x-rapidapi-key": RAPIDAPI_KEY,
            "x-rapidapi-host": "us-real-estate-listings.p.rapidapi.com"
        }
        params = {"mls_id": mls_id}
        response = requests.get(url, headers=headers, params=params, timeout=10)
        if response.status_code == 200:
            data = response.json()
            if data and "email" in data and "phone" in data:
                return {"Email": data.get("email"), "Phone": data.get("phone")}
    except Exception as e:
        print(f"MLS API error for {mls_id}: {e}")
    return None

def fetch_from_apollo(name_or_email):
    try:
        url = "https://api.apollo.io/v1/mixed_people/search"
        headers = {"Cache-Control": "no-cache"}
        payload = {
            "api_key": APOLLO_API_KEY,
            "q_keywords": name_or_email,
            "page": 1,
            "per_page": 1
        }
        response = requests.post(url, json=payload, headers=headers, timeout=10)
        if response.status_code == 200:
            data = response.json()
            if "people" in data and data["people"]:
                person = data["people"][0]
                return {
                    "Email": person.get("email"),
                    "Phone": person.get("phone_numbers", [{}])[0].get("number")
                }
    except Exception as e:
        print(f"Apollo API error for {name_or_email}: {e}")
    return None

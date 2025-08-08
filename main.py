import os
import csv
import requests
import pandas as pd
from fastapi import FastAPI, UploadFile, Form
from fastapi.responses import FileResponse
from tempfile import TemporaryDirectory

app = FastAPI()

APOLLO_API_KEY = "tSJVEfGeRu_7Wyjgl2Laxg"
APOLLO_URL = "https://api.apollo.io/v1/mixed_people/search"

def search_apollo_contact(full_name):
    headers = {
        "Cache-Control": "no-cache",
        "Content-Type": "application/json",
        "Accept": "application/json"
    }

    payload = {
        "api_key": APOLLO_API_KEY,
        "q_organization_domains": [],
        "person_name": full_name,
        "page": 1
    }

    try:
        response = requests.post(APOLLO_URL, json=payload, headers=headers)
        response.raise_for_status()
        results = response.json()

        if results.get("people"):
            person = results["people"][0]
            return {
                "email": person.get("email", ""),
                "phone": person.get("phone", "")
            }
        else:
            return {"email": "", "phone": ""}
    except Exception as e:
        print(f"❌ Apollo API error for {full_name}: {e}")
        return {"email": "", "phone": ""}

@app.post("/")
async def enrich_contacts(file: UploadFile, tag: str = Form(...)):
    with TemporaryDirectory() as tmpdir:
        input_path = os.path.join(tmpdir, file.filename)
        output_path = os.path.join(tmpdir, f"enriched_{file.filename}")

        # Save uploaded CSV
        with open(input_path, "wb") as f:
            f.write(await file.read())

        df = pd.read_csv(input_path)

        # Add columns for enrichment
        df["Email"] = ""
        df["Phone"] = ""

        for index, row in df.iterrows():
            full_name = f"{row['First Name']} {row['Last Name']}"
            print(f"🔍 Searching Apollo for: {full_name}")
            result = search_apollo_contact(full_name)
            df.at[index, "Email"] = result["email"]
            df.at[index, "Phone"] = result["phone"]

        df.to_csv(output_path, index=False)
        print(f"✅ Enriched file saved: {output_path}")
        return FileResponse(output_path, filename=os.path.basename(output_path))


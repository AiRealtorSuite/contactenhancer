import os
import csv
import time
import tempfile
import requests
from fastapi import FastAPI, File, UploadFile
from fastapi.responses import FileResponse, HTMLResponse
from starlette.middleware.cors import CORSMiddleware

RAPIDAPI_KEY = "f1a850ecbemsh11bb6e2b91515c0p19d12ejsnf375208d92a7"

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
async def main():
    with open("templates/index.html") as f:
        return HTMLResponse(f.read())

@app.post("/")
async def enrich_contacts(file: UploadFile = File(...)):
    temp_dir = tempfile.mkdtemp()
    input_path = os.path.join(temp_dir, file.filename)
    output_path = os.path.join(temp_dir, f"enriched_{file.filename}")

    with open(input_path, "wb") as f:
        f.write(await file.read())

    enriched_rows = []
    with open(input_path, newline="", encoding="utf-8-sig") as csvfile:
        reader = csv.DictReader(csvfile)
        fieldnames = reader.fieldnames + ["Agent Name", "Agent Phone", "Agent Email"]

        for row in reader:
            mls_number = row.get("MLS Number", "").strip()
            nrds_id = row.get("Agent ID", "").strip()

            if not mls_number or not nrds_id:
                print(f"⚠️ Missing MLS Number or NRDS ID, skipping row: {row}")
                row["Agent Name"] = ""
                row["Agent Phone"] = ""
                row["Agent Email"] = ""
                enriched_rows.append(row)
                continue

            print(f"🔍 Searching listing: MLS {mls_number} | NRDS {nrds_id}")
            time.sleep(0.1)  # Safe throttle for Pro plan

            # Step 1: Search for listing using MLS number
            advertiser_id = ""
            try:
                search_resp = requests.get(
                    "https://us-real-estate-listings.p.rapidapi.com/properties/search",
                    headers={
                        "X-RapidAPI-Key": RAPIDAPI_KEY,
                        "X-RapidAPI-Host": "us-real-estate-listings.p.rapidapi.com"
                    },
                    params={"query": mls_number}
                )
                search_resp.raise_for_status()
                listings = search_resp.json().get("data", {}).get("home_search", {}).get("results", [])
                if listings:
                    advertisers = listings[0].get("advertisers", [])
                    if advertisers:
                        advertiser_id = advertisers[0].get("advertiser_id", "")
            except Exception as e:
                print(f"❌ Error during listing search: {e}")

            # Step 2: Query agent profile with advertiser_id and NRDS ID
            if advertiser_id and nrds_id:
                try:
                    profile_resp = requests.get(
                        "https://us-real-estate-listings.p.rapidapi.com/agent/profile",
                        headers={
                            "X-RapidAPI-Key": RAPIDAPI_KEY,
                            "X-RapidAPI-Host": "us-real-estate-listings.p.rapidapi.com"
                        },
                        params={
                            "advertiser_id": advertiser_id,
                            "nrds_id": nrds_id
                        }
                    )
                    profile_resp.raise_for_status()
                    profile = profile_resp.json().get("data", {})
                    row["Agent Name"] = profile.get("name", "")
                    row["Agent Phone"] = profile.get("phone", "")
                    row["Agent Email"] = profile.get("email", "")
                    print(f"✅ Found: {row['Agent Name']} | 📞 {row['Agent Phone']} | 📧 {row['Agent Email']}")
                except Exception as e:
                    print(f"❌ Error retrieving agent profile: {e}")
                    row["Agent Name"] = ""
                    row["Agent Phone"] = ""
                    row["Agent Email"] = ""
            else:
                print(f"❌ No advertiser_id found for MLS {mls_number}")
                row["Agent Name"] = ""
                row["Agent Phone"] = ""
                row["Agent Email"] = ""

            enriched_rows.append(row)

    with open(output_path, "w", newline="", encoding="utf-8") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(enriched_rows)

    print(f"✅ Enriched file saved: {output_path}")
    return FileResponse(output_path, filename=os.path.basename(output_path))

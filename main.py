import os
import csv
import tempfile
import time
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
            mls_id = row.get("MLS Number", "").strip()

            if not mls_id:
                print(f"⚠️ Missing MLS Number, skipping row: {row}")
                row["Agent Name"] = ""
                row["Agent Phone"] = ""
                row["Agent Email"] = ""
                enriched_rows.append(row)
                continue

            print(f"🔍 Searching property ID: {mls_id}")

            # Add light throttle
            time.sleep(0.1)

            for attempt in range(3):
                try:
                    response = requests.get(
                        "https://us-real-estate-listings.p.rapidapi.com/properties/detail",
                        headers={
                            "X-RapidAPI-Key": RAPIDAPI_KEY,
                            "X-RapidAPI-Host": "us-real-estate-listings.p.rapidapi.com"
                        },
                        params={"property_id": mls_id}
                    )

                    if response.status_code == 429:
                        print(f"⏳ Rate limit hit for {mls_id}, retrying in 2s... (Attempt {attempt + 1})")
                        time.sleep(2)
                        continue  # Retry

                    response.raise_for_status()
                    data = response.json()
                    agent = data.get("data", {}).get("advertisers", [{}])[0]

                    row["Agent Name"] = agent.get("name", "")
                    row["Agent Phone"] = agent.get("phone", "")
                    row["Agent Email"] = agent.get("email", "")

                    print(f"✅ Found: {row['Agent Name']} | 📞 {row['Agent Phone']} | 📧 {row['Agent Email']}")
                    break  # Success, break retry loop

                except requests.exceptions.RequestException as e:
                    if attempt == 2:
                        print(f"❌ Failed after retries for MLS {mls_id}: {e}")
                        row["Agent Name"] = ""
                        row["Agent Phone"] = ""
                        row["Agent Email"] = ""
                    else:
                        time.sleep(1)

            enriched_rows.append(row)

    with open(output_path, "w", newline="", encoding="utf-8") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(enriched_rows)

    print(f"✅ Enriched file saved: {output_path}")
    return FileResponse(output_path, filename=os.path.basename(output_path))

import os
import csv
import shutil
import tempfile
import requests
from fastapi import FastAPI, File, UploadFile, Form
from fastapi.responses import FileResponse, HTMLResponse
from starlette.middleware.cors import CORSMiddleware

APOLLO_API_KEY = os.getenv("APOLLO_API_KEY")

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
    with open("index.html") as f:
        return HTMLResponse(f.read())

@app.post("/")
async def enrich_contacts(file: UploadFile = File(...)):
    temp_dir = tempfile.mkdtemp()
    input_path = os.path.join(temp_dir, file.filename)
    output_path = os.path.join(temp_dir, f"enriched_{os.path.splitext(file.filename)[0]}.csv")

    with open(input_path, "wb") as f:
        f.write(await file.read())

    enriched_rows = []
    with open(input_path, newline="", encoding="utf-8-sig") as csvfile:
        reader = csv.DictReader(csvfile)
        fieldnames = reader.fieldnames + ["Agent Phone", "Agent Email"]
        for row in reader:
            first_name = row.get("First Name", "").strip()
            last_name = row.get("Last Name", "").strip()

            if not first_name or not last_name:
                print(f"⚠️ Missing name data, skipping row: {row}")
                row["Agent Phone"] = ""
                row["Agent Email"] = ""
                enriched_rows.append(row)
                continue

            full_name = f"{first_name} {last_name}"
            print(f"🔍 Searching for {full_name} in Apollo...")

            try:
                response = requests.post(
                    "https://api.apollo.io/v1/mixed_people/search",
                    headers={
                        "Cache-Control": "no-cache",
                        "Content-Type": "application/json",
                        "X-Api-Key": APOLLO_API_KEY
                    },
                    json={
                        "q_person_name": full_name,
                        "person_titles": ["Realtor"],
                        "page": 1
                    }
                )
                response.raise_for_status()
                data = response.json()

                if data.get("people"):
                    person = data["people"][0]
                    phone = person.get("phone_number") or "None"
                    email = person.get("email") or "None"
                    print(f"✅ Found: {full_name} | 📞 {phone} | 📧 {email}")
                    row["Agent Phone"] = phone
                    row["Agent Email"] = email
                else:
                    print(f"⚠️ No match found for {full_name}")
                    row["Agent Phone"] = ""
                    row["Agent Email"] = ""

            except requests.exceptions.RequestException as e:
                print(f"❌ Apollo error for {full_name}: {e}")
                row["Agent Phone"] = ""
                row["Agent Email"] = ""

            enriched_rows.append(row)

    with open(output_path, "w", newline="", encoding="utf-8") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(enriched_rows)

    print(f"✅ File saved: {output_path}")
    return FileResponse(output_path, filename=os.path.basename(output_path))

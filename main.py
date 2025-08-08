import os
import csv
import uuid
import shutil
import httpx
import tempfile
from fastapi import FastAPI, File, UploadFile, Request
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")

APOLLO_API_KEY = os.getenv("APOLLO_API_KEY")

HTML_FORM = """
<!DOCTYPE html>
<html>
<head>
    <title>AI Contact Enricher</title>
    <link href="/static/style.css" rel="stylesheet" />
</head>
<body>
    <div class="container">
        <h1>🧠 AI Contact Enricher</h1>
        <form action="/" method="post" enctype="multipart/form-data">
            <input type="file" name="file" accept=".csv" required>
            <button type="submit">Enrich Contacts</button>
        </form>
    </div>
</body>
</html>
"""

@app.get("/", response_class=HTMLResponse)
async def form():
    return HTML_FORM

@app.post("/")
async def enrich_contacts(file: UploadFile = File(...)):
    temp_dir = tempfile.mkdtemp()
    input_path = os.path.join(temp_dir, file.filename)

    with open(input_path, "wb") as f:
        f.write(await file.read())

    output_filename = f"enriched_{uuid.uuid4().hex}.csv"
    output_path = os.path.join(temp_dir, output_filename)

    with open(input_path, newline='') as infile, open(output_path, mode='w', newline='') as outfile:
        reader = csv.DictReader(infile)
        fieldnames = reader.fieldnames + ["Agent Phone", "Agent Email"]
        writer = csv.DictWriter(outfile, fieldnames=fieldnames)
        writer.writeheader()

        for row in reader:
            first = row.get("First Name", "").strip()
            last = row.get("Last Name", "").strip()
            full_name = f"{first} {last}".strip()

            if not full_name:
                print("⚠️ Skipping empty name")
                writer.writerow(row)
                continue

            print(f"🔍 Searching for {full_name} in Apollo...")

            query = {
                "api_key": APOLLO_API_KEY,
                "q_person_name": full_name,
                "person_titles": ["Realtor"]
            }

            try:
                response = httpx.post(
                    "https://api.apollo.io/v1/mixed_people/search",
                    json=query,
                    timeout=30
                )
                response.raise_for_status()
                data = response.json()

                matches = data.get("people", [])
                if matches:
                    person = matches[0]
                    phone = person.get("phone_numbers", [None])[0]
                    email = person.get("email")
                    print(f"✅ Found: {full_name} | 📞 {phone} | 📧 {email}")
                    row["Agent Phone"] = phone or ""
                    row["Agent Email"] = email or ""
                else:
                    print(f"⚠️ No match found for {full_name}")
                    row["Agent Phone"] = ""
                    row["Agent Email"] = ""
            except Exception as e:
                print(f"❌ Apollo error for {full_name}: {e}")
                row["Agent Phone"] = ""
                row["Agent Email"] = ""

            writer.writerow(row)

    return FileResponse(output_path, filename=output_filename, media_type='text/csv', background=lambda: shutil.rmtree(temp_dir))

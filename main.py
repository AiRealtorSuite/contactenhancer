import os
import uuid
import csv
import shutil
import aiofiles
from fastapi import FastAPI, File, UploadFile, Form
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
import pandas as pd
import requests

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

UPLOAD_DIR = "/tmp"
APOLLO_API_KEY = os.getenv("APOLLO_API_KEY", "xIx_O2UpDUlm8QxWMlWCMA")

@app.get("/")
async def main():
    content = """
    <html>
        <head>
            <title>Upload CSV File</title>
        </head>
        <body>
            <h1>Upload CSV File</h1>
            <form action="/" enctype="multipart/form-data" method="post">
            <input name="file" type="file">
            <input type="submit">
            </form>
        </body>
    </html>
    """
    return HTMLResponse(content=content)


def search_apollo_person(first_name, last_name):
    full_name = f"{first_name.strip()} {last_name.strip()}"
    headers = {"Cache-Control": "no-cache"}
    payload = {
        "api_key": APOLLO_API_KEY,
        "q_person_name": full_name,
        "title": "Realtor",
        "contact_info_required": True
    }
    try:
        response = requests.post("https://api.apollo.io/v1/mixed_people/search", json=payload, headers=headers)
        response.raise_for_status()
        data = response.json()
        if data.get("people"):
            person = data["people"][0]
            email = person.get("email", "")
            phone = person.get("phone", "")
            print(f"✅ Found: {full_name} | 📞 {phone} | 📧 {email}")
            return phone, email
        else:
            print(f"⚠️ No match found for {full_name}")
            return "", ""
    except requests.exceptions.HTTPError as err:
        print(f"❌ Apollo error for {full_name}: {err}")
        try:
            print("📨 Apollo response:", response.json())
        except:
            pass
        return "", ""


@app.post("/")
async def enrich_contacts(file: UploadFile = File(...)):
    contents = await file.read()
    temp_filename = os.path.join(UPLOAD_DIR, file.filename)
    async with aiofiles.open(temp_filename, 'wb') as out_file:
        await out_file.write(contents)

    df = pd.read_csv(temp_filename)
    if "First Name" not in df.columns or "Last Name" not in df.columns:
        return {"error": "CSV must contain 'First Name' and 'Last Name' columns."}

    phones = []
    emails = []

    for index, row in df.iterrows():
        first_name = row["First Name"]
        last_name = row["Last Name"]
        if pd.isna(first_name) or pd.isna(last_name):
            phones.append("")
            emails.append("")
            continue
        phone, email = search_apollo_person(str(first_name), str(last_name))
        phones.append(phone)
        emails.append(email)

    df["Agent Phone"] = phones
    df["Agent Email"] = emails

    output_filename = f"enriched_{uuid.uuid4().hex}.csv"
    output_path = os.path.join(UPLOAD_DIR, output_filename)
    df.to_csv(output_path, index=False)

    print(f"✅ File saved: {output_path}")
    return FileResponse(path=output_path, filename=output_filename, media_type='text/csv')

from fastapi import FastAPI, UploadFile, File
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from starlette.requests import Request

import pandas as pd
import os
import shutil
import uuid
import requests
import time

app = FastAPI()

templates = Jinja2Templates(directory="templates")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

APOLLO_API_KEY = "xIx_O2UpDUlm8QxWMlWCMA"

def search_apollo(name: str):
    url = "https://api.apollo.io/api/v1/mixed_people/search"
    headers = {"Cache-Control": "no-cache", "Content-Type": "application/json"}
    payload = {
        "api_key": APOLLO_API_KEY,
        "person_name": name,
        "page": 1
    }

    try:
        response = requests.post(url, json=payload, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()
        people = data.get("people", [])

        if not people:
            print(f"❌ No Apollo match for {name}")
            return "", ""

        top_person = people[0]
        phone = top_person.get("phone_number") or ""
        email = top_person.get("email") or ""

        print(f"✅ Match for {name} | Title: {top_person.get('title', '')}, Company: {top_person.get('organization', {}).get('name', '')}")
        print(f"   📞 Phone: {phone}, 📧 Email: {email}")

        return phone, email
    except Exception as e:
        print(f"⚠️ Error with Apollo API for {name}: {e}")
        return "", ""

@app.get("/", response_class=HTMLResponse)
async def form_get(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.post("/", response_class=HTMLResponse)
async def handle_upload(request: Request, file: UploadFile = File(...)):
    temp_file = f"/tmp/temp_{uuid.uuid4().hex}.csv"
    with open(temp_file, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    df = pd.read_csv(temp_file)

    df["Enriched Agent Phone"] = ""
    df["Enriched Agent Email"] = ""

    for i, row in df.iterrows():
        first_name = str(row.get("First Name", "")).strip()
        last_name = str(row.get("Last Name", "")).strip()
        full_name = f"{first_name} {last_name}".strip()

        print(f"🔍 Searching for {full_name} in Apollo...")
        phone, email = search_apollo(full_name)
        df.at[i, "Enriched Agent Phone"] = phone
        df.at[i, "Enriched Agent Email"] = email
        time.sleep(1)

    enriched_file = f"/tmp/enriched_{uuid.uuid4().hex}.csv"
    df.to_csv(enriched_file, index=False)

    print(f"✅ File saved as: {enriched_file}")

    return HTMLResponse(
        content=f"""
        <html>
        <body style='text-align:center; font-family:sans-serif;'>
            <h2>✅ Enrichment Complete</h2>
            <a href='/download/{os.path.basename(enriched_file)}' download>Download Enriched CSV</a>
        </body>
        </html>
        """,
        status_code=200,
    )


@app.get("/download/{filename}")
async def download_file(filename: str):
    file_path = f"/tmp/{filename}"
    if not os.path.exists(file_path):
        return JSONResponse(status_code=404, content={"error": f"File '{filename}' not found."})

    print(f"⬇️ Serving file: {file_path}")
    response = FileResponse(
        path=file_path,
        filename=filename,
        media_type="text/csv"
    )

    @response.call_on_close
    def cleanup():
        try:
            os.remove(file_path)
            print(f"🧹 Deleted file after download: {file_path}")
        except Exception as e:
            print(f"⚠️ Failed to delete file: {e}")

    return response

from fastapi import FastAPI, UploadFile, Request, Form
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
import os
import pandas as pd
import requests
from io import StringIO
import tempfile

app = FastAPI()

templates = Jinja2Templates(directory="templates")

# Serve index.html from templates folder
@app.get("/", response_class=HTMLResponse)
async def read_index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

# Apollo API Key from environment variable
APOLLO_API_KEY = os.getenv("APOLLO_API_KEY")

# Apollo enrichment function
def search_apollo(full_name):
    url = "https://api.apollo.io/v1/mixed_people/search"
    headers = {
        "Content-Type": "application/json",
    }
    payload = {
        "api_key": APOLLO_API_KEY,
        "person_name": full_name,
        "page": 1
    }
    try:
        response = requests.post(url, headers=headers, json=payload)
        response.raise_for_status()
        data = response.json()
        if data.get("people"):
            person = data["people"][0]
            return person.get("email"), person.get("phone_number")
    except Exception as e:
        print(f"❌ Apollo API error for {full_name}: {e}")
    return None, None

# File upload and enrichment endpoint
@app.post("/")
async def enrich_file(file: UploadFile):
    contents = await file.read()
    df = pd.read_csv(StringIO(contents.decode("utf-8")))

    enriched_data = []
    for _, row in df.iterrows():
        name = f"{row.get('first_name', '')} {row.get('last_name', '')}".strip()
        print(f"🔍 Searching Apollo for: {name}")
        email, phone = search_apollo(name)
        enriched_row = row.to_dict()
        enriched_row["Email"] = email or ""
        enriched_row["Phone"] = phone or ""
        enriched_data.append(enriched_row)

    enriched_df = pd.DataFrame(enriched_data)
    output_dir = tempfile.mkdtemp(prefix="enriched_")
    output_path = os.path.join(output_dir, file.filename)
    enriched_df.to_csv(output_path, index=False)
    print(f"✅ Enriched file saved: {output_path}")
    return {"status": "success", "file_path": output_path}

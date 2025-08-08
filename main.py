import csv
import requests
import time
from fastapi import FastAPI, File, UploadFile, Form, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
import pandas as pd
import io

app = FastAPI()
templates = Jinja2Templates(directory="templates")

APOLLO_API_KEY = "tSJVEfGeRu_7Wyjgl2Laxg"  # Update if needed

def query_apollo(first_name, last_name):
    url = "https://api.apollo.io/v1/mixed_people/search"
    headers = {"Cache-Control": "no-cache"}
    params = {
        "api_key": APOLLO_API_KEY,
        "q_organization_domains": "realtor.com",
        "person_name": f"{first_name} {last_name}"
    }

    try:
        response = requests.get(url, headers=headers, params=params)
        response.raise_for_status()
        results = response.json()
        people = results.get("people", [])

        if people:
            top = people[0]
            return {
                "email": top.get("email"),
                "phone": top.get("phone_number"),
                "title": top.get("title"),
                "linkedin": top.get("linkedin_url")
            }
        else:
            return {"error": "No match"}
    except Exception as e:
        return {"error": str(e)}

@app.get("/", response_class=HTMLResponse)
async def form_post(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.post("/upload/")
async def handle_upload(request: Request, file: UploadFile = File(...)):
    contents = await file.read()
    df = pd.read_csv(io.StringIO(contents.decode("utf-8")))

    results = []

    for _, row in df.iterrows():
        first_name = row["First Name"]
        last_name = row["Last Name"]
        mls = row.get("MLS Number", "")
        agent_id = row.get("Agent ID", "")

        print(f"🔍 Searching Apollo for: {first_name} {last_name}")
        apollo_data = query_apollo(first_name, last_name)
        if "error" in apollo_data:
            print(f"❌ Apollo API error for {first_name} {last_name}: {apollo_data['error']}")
        time.sleep(1.2)  # Respect rate limits

        row_data = {
            "First Name": first_name,
            "Last Name": last_name,
            "MLS Number": mls,
            "Agent ID": agent_id,
            "Email": apollo_data.get("email"),
            "Phone": apollo_data.get("phone"),
            "Title": apollo_data.get("title"),
            "LinkedIn": apollo_data.get("linkedin"),
            "Error": apollo_data.get("error")
        }
        results.append(row_data)

    output_df = pd.DataFrame(results)
    output_filename = "enriched_output.csv"
    output_df.to_csv(output_filename, index=False)

    return templates.TemplateResponse("results.html", {
        "request": request,
        "data": results,
        "filename": output_filename
    })

from fastapi import FastAPI, UploadFile, File, Form
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.templating import Jinja2Templates
from starlette.requests import Request

import pandas as pd
import os
import shutil
import uuid

app = FastAPI()

# Set up templates and static files
templates = Jinja2Templates(directory="templates")
# app.mount("/static", StaticFiles(directory="static"), name="static")

# Allow CORS for testing/local dev
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/", response_class=HTMLResponse)
async def form_post(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.post("/", response_class=HTMLResponse)
async def handle_upload(request: Request, file: UploadFile = File(...)):
    temp_file = f"temp_{uuid.uuid4().hex}.csv"
    with open(temp_file, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    # Load and enrich the file
    df = pd.read_csv(temp_file)

    # Add dummy enrichment columns for now
    df["Enriched Agent Phone"] = "555-123-4567"
    df["Enriched Agent Email"] = "agent@example.com"

    enriched_file = f"enriched_{uuid.uuid4().hex}.csv"
    df.to_csv(enriched_file, index=False)

    os.remove(temp_file)

    return HTMLResponse(
        content=f"""
        <html>
        <body style="text-align:center;font-family:sans-serif;">
            <h2>✅ Enrichment Complete</h2>
            <a href="/download/{enriched_file}" download>Download Enriched File</a>
        </body>
        </html>
        """,
        status_code=200,
    )

@app.get("/download/{filename}", response_class=FileResponse)
async def download_file(filename: str):
    return FileResponse(path=filename, filename=filename, media_type="text/csv")

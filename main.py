from fastapi import FastAPI, UploadFile, File
from fastapi.responses import HTMLResponse
from google import genai
from pypdf import PdfReader
import json
import re
import hashlib
import os
import io

app = FastAPI()

# Gemini client
client = genai.Client(api_key="AIzaSyCSMaFZhTQPI7E04IlC5TUq_cRNhyw_Qdk")

CACHE_DIR = "cache"

if not os.path.exists(CACHE_DIR):
    os.makedirs(CACHE_DIR)


# -------------------------
# SAFE GEMINI CALL
# -------------------------

def ask_gemini(prompt):

    try:
        r = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt
        )
        return r.text
    except Exception as e:
        return f"Gemini Error: {str(e)}"


# -------------------------
# SAFE JSON PARSER
# -------------------------

def safe_json(text, default):

    try:
        match = re.search(r"\{[\s\S]*\}", text)

        if match:
            return json.loads(match.group())

        return default

    except Exception:
        return default


# -------------------------
# HASH
# -------------------------

def file_hash(file_bytes):

    sha = hashlib.sha256()
    sha.update(file_bytes)

    return sha.hexdigest()


# -------------------------
# HOME
# -------------------------

@app.get("/", response_class=HTMLResponse)
def home():

    return """

<html>
<head>

<title>PharmaLens AI</title>

<style>

body{
font-family:Segoe UI;
background:#eef2f7;
padding:40px;
}

.card{
background:white;
padding:30px;
border-radius:10px;
margin-bottom:20px;
box-shadow:0 8px 20px rgba(0,0,0,0.1);
}

button{
padding:10px 20px;
background:#1a73e8;
color:white;
border:none;
border-radius:6px;
}

</style>

</head>

<body>

<div class="card">

<h1>PharmaLens AI</h1>

<form action="/ask">

<input name="question" style="width:300px;padding:8px">

<button type="submit">Ask</button>

</form>

</div>

<div class="card">

<h3>Analyze Pharmacopoeia</h3>

<form action="/analyze-pdf" method="post" enctype="multipart/form-data">

<input type="file" name="file">

<br><br>

<button type="submit">Analyze</button>

</form>

</div>

<div class="card">

<h3>Analyze COA</h3>

<form action="/analyze-coa" method="post" enctype="multipart/form-data">

<input type="file" name="file">

<br><br>

<button type="submit">Analyze COA</button>

</form>

</div>

</body>
</html>

"""


# -------------------------
# ASK
# -------------------------

@app.get("/ask")
def ask(question: str):

    answer = ask_gemini(question)

    return HTMLResponse(f"""

<html>
<body style="font-family:Arial;padding:40px">

<h2>AI Answer</h2>

<pre style="white-space:pre-wrap">
{answer}
</pre>

</body>
</html>

""")


# -------------------------
# ANALYZE PDF
# -------------------------

@app.post("/analyze-pdf")
async def analyze_pdf(file: UploadFile = File(...)):

    file_bytes = await file.read()

    hash_id = file_hash(file_bytes)

    cache_file = f"{CACHE_DIR}/{hash_id}.json"

    if os.path.exists(cache_file):

        with open(cache_file) as f:
            data = json.load(f)

    else:

        reader = PdfReader(io.BytesIO(file_bytes))

        text = ""

        for page in reader.pages:

            t = page.extract_text()

            if t:
                text += t


        prompt = f"""

Extract pharmaceutical QC tests from this pharmacopoeia text.

Return JSON:

{{
"tests":[
{{"name":"","limit":"","details":""}}
]
}}

{text}

"""

        response_text = ask_gemini(prompt)

        data = safe_json(
            response_text,
            {"tests":[{"name":"Analysis","limit":"","details":response_text}]}
        )

        with open(cache_file,"w") as f:
            json.dump(data,f)


    rows = ""

    for t in data["tests"]:

        rows += f"""
<tr>
<td>{t.get("name","")}</td>
<td>{t.get("limit","")}</td>
</tr>
"""


    return HTMLResponse(f"""

<html>

<body style="font-family:Segoe UI;padding:40px">

<h2>QC Tests</h2>

<table border="1" cellpadding="10">

<tr>
<th>Test</th>
<th>Limit</th>
</tr>

{rows}

</table>

</body>

</html>

""")


# -------------------------
# ANALYZE COA
# -------------------------

@app.post("/analyze-coa")
async def analyze_coa(file: UploadFile = File(...)):

    file_bytes = await file.read()

    reader = PdfReader(io.BytesIO(file_bytes))

    text = ""

    for page in reader.pages:

        t = page.extract_text()

        if t:
            text += t


    prompt = f"""

Analyze this Certificate of Analysis.

Return JSON:

{{
"coa":[
{{"test":"","result":"","spec":"","status":""}}
]
}}

{text}

"""

    response_text = ask_gemini(prompt)

    data = safe_json(
        response_text,
        {"coa":[{"test":"analysis","result":"","spec":"","status":""}]}
    )


    rows = ""

    for t in data["coa"]:

        status = t.get("status","")

        color = "green"

        if "fail" in status.lower():
            color = "red"


        rows += f"""
<tr>
<td>{t.get("test","")}</td>
<td>{t.get("result","")}</td>
<td>{t.get("spec","")}</td>
<td style="color:{color};font-weight:bold">{status}</td>
</tr>
"""


    return HTMLResponse(f"""

<html>

<body style="font-family:Segoe UI;padding:40px">

<h2>COA Analysis</h2>

<table border="1" cellpadding="10">

<tr>
<th>Test</th>
<th>Result</th>
<th>Spec</th>
<th>Status</th>
</tr>

{rows}

</table>

</body>

</html>

""")
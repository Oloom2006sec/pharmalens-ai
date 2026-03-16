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

client = genai.Client(api_key="AIzaSyCSMaFZhTQPI7E04IlC5TUq_cRNhyw_Qdk")

CACHE_DIR = "cache"

if not os.path.exists(CACHE_DIR):
    os.makedirs(CACHE_DIR)

# -----------------------------
# HASH
# -----------------------------

def file_hash(file_bytes):

    sha = hashlib.sha256()
    sha.update(file_bytes)

    return sha.hexdigest()


# -----------------------------
# HPLC PARAMETER EXTRACTION
# -----------------------------

def extract_hplc_params(text):

    params = {}

    col = re.search(r'column.*?\((.*?)\)', text, re.I)
    if col:
        params["column"] = col.group()

    flow = re.search(r'flow rate.*?([\d\.]+\s?mL/?min)', text, re.I)
    if flow:
        params["flow"] = flow.group(1)

    wave = re.search(r'wavelength.*?([\d]+\s?nm)', text, re.I)
    if wave:
        params["wavelength"] = wave.group(1)

    inj = re.search(r'inject.*?([\d]+\s?µ?L)', text, re.I)
    if inj:
        params["inj"] = inj.group(1)

    mobile = re.search(r'mobile phase[:\-]?(.*?)(flow rate|column|detection)', text, re.I | re.S)
    if mobile:
        params["mobile"] = mobile.group(1)

    return params


# -----------------------------
# HOME PAGE
# -----------------------------

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

<h3>Analyze Certificate of Analysis</h3>

<form action="/analyze-coa" method="post" enctype="multipart/form-data">

<input type="file" name="file">

<br><br>

<button type="submit">Analyze COA</button>

</form>

</div>

</body>

</html>

"""


# -----------------------------
# ASK AI
# -----------------------------

@app.get("/ask")
def ask(question:str):

    r = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=question
    )

    return HTMLResponse(f"""

<html>

<body style="font-family:Arial;padding:40px">

<h2>AI Answer</h2>

<pre style="white-space:pre-wrap">
{r.text}
</pre>

</body>

</html>

""")


# -----------------------------
# ANALYZE PHARMACOPOEIA
# -----------------------------

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

        text=""

        for page in reader.pages:

            t=page.extract_text()

            if t:
                text+=t


        response = client.models.generate_content(

            model="gemini-2.5-flash",

            contents=f"""

You are pharmaceutical QC expert.

Extract QC tests.

Return JSON.

{{
"tests":[
{{"name":"","limit":"","details":""}}
]
}}

Document:

{text}

"""
        )

        match=re.search(r"\{[\s\S]*\}",response.text)

        if match:
            data=json.loads(match.group())
        else:
            data={"tests":[{"name":"analysis","details":response.text}]}

        with open(cache_file,"w") as f:
            json.dump(data,f)


    tests=data.get("tests",[])

    tabs=""
    sections=""
    rows=""
    sop_all=""

    for i,t in enumerate(tests):

        name=t.get("name","")
        limit=t.get("limit","")
        details=t.get("details","")

        technique=""

        text_all=(name+details).lower()

        if "chromatograph" in text_all:
            technique="HPLC"

        elif "titration" in text_all:
            technique="Titration"

        elif "uv" in text_all:
            technique="UV"

        elif "infrared" in text_all:
            technique="IR"

        elif "melting" in text_all:
            technique="Melting Point"

        elif "drying" in text_all:
            technique="Gravimetric"


        params_html=""

        if technique=="HPLC":

            p=extract_hplc_params(details)

            if p:

                params_html+="<b>Chromatographic Conditions</b><br>"

                if "column" in p:
                    params_html+=f"Column: {p['column']}<br>"

                if "mobile" in p:
                    params_html+=f"Mobile phase: {p['mobile']}<br>"

                if "flow" in p:
                    params_html+=f"Flow rate: {p['flow']}<br>"

                if "wavelength" in p:
                    params_html+=f"Wavelength: {p['wavelength']}<br>"

                if "inj" in p:
                    params_html+=f"Injection volume: {p['inj']}<br>"

                params_html+="<br>"


        tab=f"tab{i}"
        active="active" if i==0 else ""

        tabs+=f'<div class="tab {active}" id="btn_{tab}" onclick="openTab(\'{tab}\')">{name}</div>'


        sections+=f"""

<div class="section {active}" id="{tab}">

<h3>{name}</h3>

<b>Technique:</b> {technique}<br>
<b>Limit:</b> {limit}<br><br>

{params_html}

<h4>Description</h4>

<pre style="white-space:pre-wrap">{details}</pre>

</div>

"""


        rows+=f"""
<tr>
<td>{name}</td>
<td>{technique}</td>
<td>{limit}</td>
</tr>
"""


        sop_all+=f"""

<h3>{name}</h3>

Technique: {technique}

Limit: {limit}

{details}

<hr>

"""


    tabs+=f'<div class="tab" id="btn_sop" onclick="openTab(\'sop\')">SOP</div>'

    sections+=f"""

<div class="section" id="sop">

<h2>QC Laboratory SOP</h2>

{sop_all}

</div>

"""


    html=f"""

<html>

<head>

<style>

body{{font-family:Segoe UI;background:#eef2f7;padding:40px}}

table{{width:100%;border-collapse:collapse;background:white}}

th,td{{padding:10px;border:1px solid #ddd}}

th{{background:#1a73e8;color:white}}

.tabs{{display:flex;gap:10px;margin-top:20px;flex-wrap:wrap}}

.tab{{background:white;padding:8px 16px;border-radius:6px;cursor:pointer}}

.tab.active{{background:#1a73e8;color:white}}

.section{{display:none;background:white;padding:20px;border-radius:10px;margin-top:10px}}

.section.active{{display:block}}

</style>

<script>

function openTab(id){{
document.querySelectorAll('.section').forEach(x=>x.classList.remove('active'))
document.querySelectorAll('.tab').forEach(x=>x.classList.remove('active'))

document.getElementById(id).classList.add('active')
document.getElementById('btn_'+id).classList.add('active')
}}

</script>

</head>

<body>

<h1>PharmaLens AI QC Dashboard</h1>

<h2>QC Summary</h2>

<table>

<tr>
<th>Test</th>
<th>Technique</th>
<th>Limit</th>
</tr>

{rows}

</table>

<div class="tabs">

{tabs}

</div>

{sections}

</body>

</html>

"""

    return HTMLResponse(html)


# -----------------------------
# COA ANALYZER
# -----------------------------

@app.post("/analyze-coa")
async def analyze_coa(file: UploadFile = File(...)):

    file_bytes = await file.read()

    reader = PdfReader(io.BytesIO(file_bytes))

    text=""

    for page in reader.pages:

        t=page.extract_text()

        if t:
            text+=t


    response = client.models.generate_content(

        model="gemini-2.5-flash",

        contents=f"""

You are pharmaceutical QC expert.

Analyze Certificate of Analysis.

Extract:

Test
Result
Specification
Status (Pass or Fail)

Return JSON:

{{
"coa":[
{{"test":"","result":"","spec":"","status":""}}
]
}}

{text}

"""
    )

    match=re.search(r"\{[\s\S]*\}",response.text)

    if match:
        data=json.loads(match.group())
    else:
        return HTMLResponse("<h2>Parsing Error</h2>")


    rows=""

    for t in data["coa"]:

        test=t.get("test","")
        result=t.get("result","")
        spec=t.get("spec","")
        status=t.get("status","")

        color="green"

        if "fail" in status.lower():
            color="red"

        rows+=f"""
<tr>
<td>{test}</td>
<td>{result}</td>
<td>{spec}</td>
<td style="color:{color};font-weight:bold">{status}</td>
</tr>
"""


    html=f"""

<html>

<head>

<style>

body{{font-family:Segoe UI;background:#eef2f7;padding:40px}}

table{{width:100%;border-collapse:collapse;background:white}}

th,td{{padding:10px;border:1px solid #ddd}}

th{{background:#1a73e8;color:white}}

</style>

</head>

<body>

<h1>PharmaLens COA Analyzer</h1>

<table>

<tr>
<th>Test</th>
<th>Result</th>
<th>Specification</th>
<th>Status</th>
</tr>

{rows}

</table>

</body>

</html>

"""

    return HTMLResponse(html)
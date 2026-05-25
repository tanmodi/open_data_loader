import json
import os
import re
import tempfile
from html import escape
from io import BytesIO
from pathlib import Path

import opendataloader_pdf
import pdfplumber
import requests
from django.http import HttpResponse, HttpResponseBadRequest, JsonResponse
from django.views.decorators.csrf import csrf_exempt


OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen3.5:latest")
OLLAMA_TIMEOUT = int(os.environ.get("OLLAMA_TIMEOUT", "300"))
OLLAMA_NUM_CTX = int(os.environ.get("OLLAMA_NUM_CTX", "8192"))
OLLAMA_NUM_THREAD = int(os.environ.get("OLLAMA_NUM_THREAD", "16"))


def home(_request):
    return render_upload_ui()


@csrf_exempt
def upload(request):
    return handle_pdf_upload(request, extract_pdf)


@csrf_exempt
def upload2(request):
    return handle_pdf_upload(request, extract_pdf_with_opendataloader)


@csrf_exempt
def ai_pdf_extract_v1(request):
    if request.method == "GET":
        return render_upload_ui(active_path=request.path)

    if request.method != "POST":
        return HttpResponseBadRequest("Use GET or POST with a PDF file in the 'file' form field.\n")

    uploaded_file = request.FILES.get("file")
    if uploaded_file is None:
        return HttpResponseBadRequest("Missing PDF file in 'file' form field.\n")

    if not uploaded_file.name.lower().endswith(".pdf"):
        return HttpResponseBadRequest("Only PDF uploads are supported.\n")

    try:
        extracted_text = extract_pdf_with_opendataloader(uploaded_file.read(), uploaded_file.name)
        llm_text = run_bill_extraction_llm(extracted_text)
        bill_json = parse_json_object(llm_text)
    except ValueError as exc:
        if request.POST.get("ui") == "1":
            return render_upload_ui(active_path=request.path, ai_error=str(exc), status=502)
        return JsonResponse({"error": str(exc)}, status=502)
    except requests.RequestException as exc:
        error = f"Ollama request failed: {exc}"
        if request.POST.get("ui") == "1":
            return render_upload_ui(active_path=request.path, ai_error=error, status=502)
        return JsonResponse({"error": error}, status=502)
    except Exception as exc:
        if request.POST.get("ui") == "1":
            return render_upload_ui(active_path=request.path, ai_error=f"Could not extract PDF: {exc}", status=400)
        return HttpResponseBadRequest(f"Could not extract PDF: {exc}\n")

    response_data = {
        "model": OLLAMA_MODEL,
        "source": "upload2_text_extraction",
        "data": bill_json,
    }
    if request.POST.get("ui") == "1":
        return render_upload_ui(active_path=request.path, ai_json=response_data)

    return JsonResponse(
        response_data,
        json_dumps_params={"ensure_ascii": False, "indent": 2},
    )


def handle_pdf_upload(request, extractor):
    if request.method == "GET":
        return render_upload_ui(active_path=request.path)

    if request.method != "POST":
        return HttpResponseBadRequest("Use GET or POST with a PDF file in the 'file' form field.\n")

    uploaded_file = request.FILES.get("file")
    if uploaded_file is None:
        return HttpResponseBadRequest("Missing PDF file in 'file' form field.\n")

    if not uploaded_file.name.lower().endswith(".pdf"):
        return HttpResponseBadRequest("Only PDF uploads are supported.\n")

    try:
        result = extractor(uploaded_file.read(), uploaded_file.name)
    except Exception as exc:
        return HttpResponseBadRequest(f"Could not extract PDF: {exc}\n")

    response = HttpResponse(result, content_type="text/plain; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="extracted.txt"'
    return response


def render_upload_ui(active_path="/upload", ai_json=None, ai_error=None, status=200):
    active_path = active_path if active_path in {"/upload", "/upload2", "/ai/pdf_extract/v1"} else "/upload"
    html = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Open Data Loader</title>
  <style>
    :root {{
      color-scheme: light;
      --bg: #f6f7f9;
      --panel: #ffffff;
      --text: #18202a;
      --muted: #647184;
      --border: #d7dde6;
      --accent: #0f766e;
      --accent-dark: #115e59;
      --shadow: 0 16px 40px rgba(24, 32, 42, 0.08);
    }}

    * {{
      box-sizing: border-box;
    }}

    body {{
      margin: 0;
      min-height: 100vh;
      font-family: Arial, Helvetica, sans-serif;
      color: var(--text);
      background: var(--bg);
    }}

    .shell {{
      width: min(940px, calc(100% - 32px));
      margin: 0 auto;
      padding: 40px 0;
    }}

    header {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
      margin-bottom: 28px;
    }}

    h1 {{
      margin: 0;
      font-size: 28px;
      line-height: 1.2;
    }}

    .status {{
      padding: 8px 12px;
      border: 1px solid #b7e0d9;
      border-radius: 999px;
      color: #075047;
      background: #e6f6f3;
      font-size: 14px;
      white-space: nowrap;
    }}

    .layout {{
      display: grid;
      grid-template-columns: 220px minmax(0, 1fr);
      gap: 20px;
      align-items: start;
    }}

    nav {{
      display: grid;
      gap: 10px;
    }}

    nav a {{
      display: block;
      padding: 12px 14px;
      border: 1px solid var(--border);
      border-radius: 8px;
      color: var(--text);
      text-decoration: none;
      background: var(--panel);
    }}

    nav a.active {{
      border-color: var(--accent);
      color: var(--accent-dark);
      font-weight: 700;
    }}

    main {{
      border: 1px solid var(--border);
      border-radius: 8px;
      background: var(--panel);
      box-shadow: var(--shadow);
      padding: 28px;
    }}

    h2 {{
      margin: 0 0 8px;
      font-size: 22px;
      line-height: 1.25;
    }}

    p {{
      margin: 0 0 22px;
      color: var(--muted);
      line-height: 1.5;
    }}

    form {{
      display: grid;
      gap: 16px;
    }}

    .file-box {{
      display: grid;
      gap: 10px;
      padding: 22px;
      border: 1px dashed #9aa8ba;
      border-radius: 8px;
      background: #fbfcfd;
    }}

    label {{
      font-weight: 700;
    }}

    input[type="file"] {{
      width: 100%;
      padding: 12px;
      border: 1px solid var(--border);
      border-radius: 8px;
      background: #ffffff;
      color: var(--text);
    }}

    button {{
      justify-self: start;
      min-height: 44px;
      padding: 0 18px;
      border: 0;
      border-radius: 8px;
      color: #ffffff;
      background: var(--accent);
      font-weight: 700;
      cursor: pointer;
    }}

    button:hover {{
      background: var(--accent-dark);
    }}

    .actions {{
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      align-items: center;
    }}

    .secondary-button {{
      display: inline-flex;
      align-items: center;
      justify-content: center;
      min-height: 40px;
      padding: 0 14px;
      border: 1px solid var(--border);
      border-radius: 8px;
      color: var(--text);
      background: #ffffff;
      font-weight: 700;
      text-decoration: none;
      cursor: pointer;
    }}

    .secondary-button:hover {{
      border-color: var(--accent);
      color: var(--accent-dark);
      background: #ffffff;
    }}

    .json-result {{
      display: grid;
      gap: 12px;
      margin-top: 22px;
      padding-top: 22px;
      border-top: 1px solid var(--border);
    }}

    .json-header {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      flex-wrap: wrap;
    }}

    h3 {{
      margin: 0;
      font-size: 18px;
      line-height: 1.3;
    }}

    pre {{
      width: 100%;
      max-height: 560px;
      margin: 0;
      overflow: auto;
      padding: 16px;
      border: 1px solid var(--border);
      border-radius: 8px;
      color: #172033;
      background: #f8fafc;
      font-family: Consolas, Monaco, monospace;
      font-size: 13px;
      line-height: 1.55;
      white-space: pre-wrap;
      word-break: break-word;
    }}

    .error-box {{
      margin-top: 22px;
      padding: 14px 16px;
      border: 1px solid #fecaca;
      border-radius: 8px;
      color: #7f1d1d;
      background: #fef2f2;
      line-height: 1.45;
    }}

    .note {{
      margin-top: 18px;
      padding-top: 18px;
      border-top: 1px solid var(--border);
      font-size: 14px;
      color: var(--muted);
    }}

    code {{
      font-family: Consolas, Monaco, monospace;
      font-size: 0.95em;
      color: #273244;
    }}

    @media (max-width: 720px) {{
      header {{
        align-items: flex-start;
        flex-direction: column;
      }}

      .layout {{
        grid-template-columns: 1fr;
      }}

      main {{
        padding: 22px;
      }}
    }}
  </style>
</head>
<body>
  <div class="shell">
    <header>
      <h1>Open Data Loader</h1>
      <div class="status">server working</div>
    </header>
    <div class="layout">
      <nav aria-label="Extractor">
        {nav_link("/upload", "PDF Plumber", active_path)}
        {nav_link("/upload2", "OpenDataLoader PDF", active_path)}
        {nav_link("/ai/pdf_extract/v1", "AI JSON Extract", active_path)}
      </nav>
      {upload_panel(active_path, ai_json, ai_error)}
    </div>
  </div>
{ui_script(active_path)}
</body>
</html>
"""
    return HttpResponse(html, content_type="text/html; charset=utf-8", status=status)


def nav_link(path, label, active_path):
    active_class = ' class="active"' if path == active_path else ""
    return f'<a href="{path}"{active_class}>{escape(label)}</a>'


def upload_panel(action, ai_json=None, ai_error=None):
    if action == "/upload":
        title = "PDF Plumber extraction"
        detail = "Extract plain text, JSON tables, and table text with pdfplumber."
        button_text = "Download TXT"
    elif action == "/upload2":
        title = "OpenDataLoader PDF extraction"
        detail = "Extract plain text, JSON tables, and table text with OpenDataLoader PDF."
        button_text = "Download TXT"
    else:
        title = "AI electricity bill extraction"
        detail = "Extract Indian electricity bill values as JSON with local Gemma through Ollama."
        button_text = "Extract JSON"

    hidden_fields = '<input type="hidden" name="ui" value="1">' if action == "/ai/pdf_extract/v1" else ""

    return f"""<main>
        <h2>{escape(title)}</h2>
        <p>{escape(detail)}</p>
        <form method="post" action="{escape(action)}" enctype="multipart/form-data">
          {hidden_fields}
          <div class="file-box">
            <label for="file">PDF file</label>
            <input id="file" type="file" name="file" accept="application/pdf,.pdf" required>
          </div>
          <button type="submit">{escape(button_text)}</button>
        </form>
        <div class="note">
          {upload_note(action)}
        </div>
        {ai_result_panel(action, ai_json, ai_error)}
      </main>"""


def upload_note(action):
    if action == "/ai/pdf_extract/v1":
        return f"Returns <code>application/json</code> from local <code>{escape(OLLAMA_MODEL)}</code>."
    return "The downloaded TXT includes <code>###PLAIN_START###</code>, <code>###TABLE_START###</code>, and <code>###BEXT_TABLE_START###</code> sections."


def ai_result_panel(action, ai_json, ai_error):
    if action != "/ai/pdf_extract/v1":
        return ""
    if ai_error:
        return f'<div class="error-box">{escape(ai_error)}</div>'
    if ai_json is None:
        return ""

    json_text = json.dumps(ai_json, ensure_ascii=False, indent=2)
    return f"""<section class="json-result" aria-label="AI JSON result">
          <div class="json-header">
            <h3>Extracted JSON</h3>
            <div class="actions">
              <button class="secondary-button" type="button" data-copy-json>Copy</button>
              <button class="secondary-button" type="button" data-download-json>Download</button>
            </div>
          </div>
          <pre id="json-output">{escape(json_text)}</pre>
        </section>"""


def ui_script(active_path):
    if active_path != "/ai/pdf_extract/v1":
        return ""
    return """<script>
  (() => {
    const output = document.getElementById("json-output");
    if (!output) {
      return;
    }

    const copyButton = document.querySelector("[data-copy-json]");
    const downloadButton = document.querySelector("[data-download-json]");

    copyButton?.addEventListener("click", async () => {
      await navigator.clipboard.writeText(output.textContent);
      copyButton.textContent = "Copied";
      window.setTimeout(() => {
        copyButton.textContent = "Copy";
      }, 1400);
    });

    downloadButton?.addEventListener("click", () => {
      const blob = new Blob([output.textContent], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = "electricity-bill-extraction.json";
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
    });
  })();
</script>"""


def run_bill_extraction_llm(extracted_text):
    prompt = build_bill_extraction_prompt(extracted_text)
    response = requests.post(
        f"{OLLAMA_BASE_URL}/api/generate",
        json={
            "model": OLLAMA_MODEL,
            "prompt": prompt,
            "stream": False,
            "format": "json",
            "options": {
                "temperature": 0,
                "num_ctx": OLLAMA_NUM_CTX,
                "num_thread": OLLAMA_NUM_THREAD,
            },
        },
        timeout=OLLAMA_TIMEOUT,
    )
    response.raise_for_status()

    payload = response.json()
    generated_text = payload.get("response", "")
    if not generated_text.strip():
        raise ValueError("Ollama returned an empty response")
    return generated_text


def build_bill_extraction_prompt(extracted_text):
    return f"""Extract all values from this Indian electricity bill PDF extraction.

Return only one valid JSON object. Do not include markdown or explanation.
Use null when a value is not present. Preserve exact values, units, dates,
currency symbols, account numbers, meter numbers, tariff names, and labels
as they appear in the bill.

Expected JSON shape:
{{
  "document_type": "electricity_bill",
  "country": "India",
  "provider": null,
  "consumer": {{
    "name": null,
    "consumer_number": null,
    "account_number": null,
    "address": null,
    "mobile": null,
    "email": null
  }},
  "bill": {{
    "bill_number": null,
    "bill_date": null,
    "due_date": null,
    "billing_period": null,
    "amount_due": null,
    "amount_after_due_date": null,
    "previous_balance": null,
    "payments_received": null,
    "total_charges": null
  }},
  "meter": {{
    "meter_number": null,
    "phase": null,
    "tariff": null,
    "sanctioned_load": null,
    "connected_load": null
  }},
  "readings": [],
  "charges": [],
  "taxes": [],
  "all_extracted_values": [
    {{
      "label": null,
      "value": null,
      "unit": null,
      "category": null,
      "source_text": null
    }}
  ],
  "confidence": null
}}

PDF extraction:
{extracted_text}
"""


def parse_json_object(text):
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    decoder = json.JSONDecoder()
    for match in re.finditer(r"{", text):
        try:
            value, _end = decoder.raw_decode(text[match.start() :])
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value

    raise ValueError("Gemma did not return valid JSON")


def extract_pdf(pdf_bytes, _filename="uploaded.pdf"):
    plain_pages = []
    table_pages = []
    best_table_pages = []

    with pdfplumber.open(BytesIO(pdf_bytes)) as pdf:
        for page_number, page in enumerate(pdf.pages, start=1):
            plain_pages.append(page.extract_text(x_tolerance=1, y_tolerance=3) or "")

            tables = page.extract_tables() or []
            normalized_tables = [normalize_table(table) for table in tables]
            table_pages.append(
                {
                    "page": page_number,
                    "tables": normalized_tables,
                }
            )

            best_table_pages.extend(
                table_to_text(page_number, index, table)
                for index, table in enumerate(normalized_tables, start=1)
            )

    return format_extraction_output(
        "\n\n".join(plain_pages),
        table_pages,
        "\n\n".join(best_table_pages),
    )


def extract_pdf_with_opendataloader(pdf_bytes, filename="uploaded.pdf"):
    safe_name = Path(filename).name or "uploaded.pdf"
    if not safe_name.lower().endswith(".pdf"):
        safe_name = f"{safe_name}.pdf"

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        input_path = temp_path / safe_name
        output_dir = temp_path / "output"
        input_path.write_bytes(pdf_bytes)
        output_dir.mkdir()

        opendataloader_pdf.convert(
            input_path=[str(input_path)],
            output_dir=str(output_dir),
            format="text,json",
            keep_line_breaks=True,
            image_output="off",
            quiet=True,
        )

        plain_text = read_first_output(output_dir, [".txt", ".text"])
        document_json = json.loads(read_first_output(output_dir, [".json"]))
        table_pages = extract_opendataloader_tables(document_json)
        best_table_text = "\n\n".join(
            table_to_text(table["page"], index, table["rows"])
            for index, table in enumerate(table_pages, start=1)
        )

    return format_extraction_output(plain_text, table_pages, best_table_text)


def format_extraction_output(plain_text, table_data, best_table_text):
    table_json = json.dumps(table_data, ensure_ascii=False, indent=2)
    return "\n".join(
        [
            "###PLAIN_START###",
            plain_text.strip(),
            "###PLAIN_END###",
            "",
            "###TABLE_START###",
            table_json,
            "###TABLE_END###",
            "",
            "###BEXT_TABLE_START###",
            best_table_text.strip(),
            "###BEXT_TABLE_END###",
            "",
        ]
    )


def read_first_output(output_dir, suffixes):
    for suffix in suffixes:
        matches = sorted(output_dir.glob(f"*{suffix}"))
        if matches:
            return matches[0].read_text(encoding="utf-8")
    expected = ", ".join(suffixes)
    raise ValueError(f"OpenDataLoader did not create an output file with {expected}")


def extract_opendataloader_tables(document_json):
    tables = []
    for node in walk_nodes(document_json):
        if node.get("type") == "table":
            rows = opendataloader_table_rows(node)
            if rows:
                tables.append(
                    {
                        "page": node.get("page number"),
                        "rows": rows,
                        "number_of_rows": node.get("number of rows"),
                        "number_of_columns": node.get("number of columns"),
                    }
                )
    return tables


def walk_nodes(node):
    if isinstance(node, dict):
        yield node
        for value in node.values():
            yield from walk_nodes(value)
    elif isinstance(node, list):
        for item in node:
            yield from walk_nodes(item)


def opendataloader_table_rows(table):
    rows = []
    for row in table.get("rows", []):
        cells = sorted(
            row.get("cells", []),
            key=lambda cell: cell.get("column number", 0),
        )
        rows.append([extract_node_text(cell) for cell in cells])
    return [row for row in rows if any(row)]


def extract_node_text(node):
    parts = []
    for child in walk_nodes(node):
        content = child.get("content")
        if content:
            parts.append(clean_cell(content))
    return " ".join(parts)


def normalize_table(table):
    return [
        [clean_cell(cell) for cell in row]
        for row in table
        if row and any(clean_cell(cell) for cell in row)
    ]


def clean_cell(value):
    if value is None:
        return ""
    return " ".join(str(value).split())


def table_to_text(page_number, table_number, table):
    rows = ["\t".join(row) for row in table]
    return "\n".join([f"Page {page_number} Table {table_number}", *rows])

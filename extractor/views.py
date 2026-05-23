import json
import tempfile
from html import escape
from io import BytesIO
from pathlib import Path

import opendataloader_pdf
import pdfplumber
from django.http import HttpResponse, HttpResponseBadRequest
from django.views.decorators.csrf import csrf_exempt


def home(_request):
    return render_upload_ui()


@csrf_exempt
def upload(request):
    return handle_pdf_upload(request, extract_pdf)


@csrf_exempt
def upload2(request):
    return handle_pdf_upload(request, extract_pdf_with_opendataloader)


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


def render_upload_ui(active_path="/upload"):
    active_path = active_path if active_path in {"/upload", "/upload2"} else "/upload"
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
      </nav>
      {upload_panel(active_path)}
    </div>
  </div>
</body>
</html>
"""
    return HttpResponse(html, content_type="text/html; charset=utf-8")


def nav_link(path, label, active_path):
    active_class = ' class="active"' if path == active_path else ""
    return f'<a href="{path}"{active_class}>{escape(label)}</a>'


def upload_panel(action):
    title = "PDF Plumber extraction" if action == "/upload" else "OpenDataLoader PDF extraction"
    detail = (
        "Extract plain text, JSON tables, and table text with pdfplumber."
        if action == "/upload"
        else "Extract plain text, JSON tables, and table text with OpenDataLoader PDF."
    )
    return f"""<main>
        <h2>{escape(title)}</h2>
        <p>{escape(detail)}</p>
        <form method="post" action="{escape(action)}" enctype="multipart/form-data">
          <div class="file-box">
            <label for="file">PDF file</label>
            <input id="file" type="file" name="file" accept="application/pdf,.pdf" required>
          </div>
          <button type="submit">Download TXT</button>
        </form>
        <div class="note">
          The downloaded TXT includes <code>###PLAIN_START###</code>, <code>###TABLE_START###</code>, and <code>###BEXT_TABLE_START###</code> sections.
        </div>
      </main>"""


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

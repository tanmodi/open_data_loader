import json
import tempfile
from io import BytesIO
from pathlib import Path

import opendataloader_pdf
import pdfplumber
from django.http import HttpResponse, HttpResponseBadRequest
from django.views.decorators.csrf import csrf_exempt


def home(_request):
    return HttpResponse("server working\n", content_type="text/plain")


@csrf_exempt
def upload(request):
    return handle_pdf_upload(request, extract_pdf)


@csrf_exempt
def upload2(request):
    return handle_pdf_upload(request, extract_pdf_with_opendataloader)


def handle_pdf_upload(request, extractor):
    if request.method == "GET":
        return upload_form(request.path)

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


def upload_form(action):
    html = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Upload PDF</title>
</head>
<body>
  <form method="post" action="{action}" enctype="multipart/form-data">
    <input type="file" name="file" accept="application/pdf" required>
    <button type="submit">Upload</button>
  </form>
</body>
</html>
"""
    return HttpResponse(html, content_type="text/html; charset=utf-8")


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

import json
from io import BytesIO

import pdfplumber
from django.http import HttpResponse, HttpResponseBadRequest
from django.views.decorators.csrf import csrf_exempt


def home(_request):
    return HttpResponse("server working\n", content_type="text/plain")


@csrf_exempt
def upload(request):
    if request.method != "POST":
        return HttpResponseBadRequest("POST a PDF file using the 'file' form field.\n")

    uploaded_file = request.FILES.get("file")
    if uploaded_file is None:
        return HttpResponseBadRequest("Missing PDF file in 'file' form field.\n")

    if not uploaded_file.name.lower().endswith(".pdf"):
        return HttpResponseBadRequest("Only PDF uploads are supported.\n")

    try:
        result = extract_pdf(uploaded_file.read())
    except Exception as exc:
        return HttpResponseBadRequest(f"Could not extract PDF: {exc}\n")

    response = HttpResponse(result, content_type="text/plain; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="extracted.txt"'
    return response


def extract_pdf(pdf_bytes):
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

    table_json = json.dumps(table_pages, ensure_ascii=False, indent=2)
    best_table_text = "\n\n".join(best_table_pages)

    return "\n".join(
        [
            "###PLAIN_START###",
            "\n\n".join(plain_pages).strip(),
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

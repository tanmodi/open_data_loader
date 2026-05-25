from django.urls import path

from extractor.views import ai_pdf_extract_v1, ai_pdf_extract_v1_stream, home, upload, upload2

urlpatterns = [
    path("", home, name="home"),
    path("upload", upload, name="upload"),
    path("upload2", upload2, name="upload2"),
    path("ai/pdf_extract/v1", ai_pdf_extract_v1, name="ai_pdf_extract_v1"),
    path("ai/pdf_extract/v1/stream", ai_pdf_extract_v1_stream, name="ai_pdf_extract_v1_stream"),
]

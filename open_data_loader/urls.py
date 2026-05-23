from django.urls import path

from extractor.views import home, upload, upload2

urlpatterns = [
    path("", home, name="home"),
    path("upload", upload, name="upload"),
    path("upload2", upload2, name="upload2"),
]

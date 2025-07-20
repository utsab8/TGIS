from django.urls import path
from . import views

app_name = 'land_parser'

urlpatterns = [
    path('', views.upload_view, name='upload'),
    path('preview/', views.preview_view, name='preview'),
    path('download-csv/', views.download_csv_view, name='download-csv'),
    path('save-to-db/', views.save_to_db_view, name='save-to-db'),
    path('clear-session/', views.clear_session_view, name='clear-session'),
    path('help/', views.help_view, name='help'),
] 
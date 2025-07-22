from django.urls import path
from .views import (
    csv_upload_view, csv_export_view, attachment_upload_view, 
    attachment_delete_view, dashboard_analytics_api, 
    boundary_completeness_report, area_coverage_report, export_excel_report, 
    user_activity_api, coverage_map_data, advanced_search_api, 
    SurveyRecordViewSet, CSVUploadAPIView, export_kml_api, 
    spatial_query_api, google_earth_link_api, 
    kml_export_google_earth_api, dashboard_stats_api, dashboard_coverage_api, 
    survey_list_view, survey_add_view, map_view, survey_edit_view, 
    survey_delete_view, download_generated_kml, 
    download_all_surveys_kml, dashboard_view, download_error_report, 
    help_view, advanced_csv_upload, boundaries_geojson_api, 
    excel_export_view, kml_export_view, pdf_export_view
)
from rest_framework.routers import DefaultRouter

router = DefaultRouter()
router.register(r'api/v1/surveys', SurveyRecordViewSet, basename='surveyrecord')

urlpatterns = [
    path('', survey_list_view, name='survey_list'),
    path('dashboard/', dashboard_view, name='dashboard'),
    path('upload-csv/', csv_upload_view, name='csv_upload'),
    path('export-csv/', csv_export_view, name='csv_export'),
    path('upload-attachment/', attachment_upload_view, name='attachment_upload'),
    path('delete-attachment/<int:pk>/', attachment_delete_view, name='attachment_delete'),
    path('map-view/', map_view, name='map_view'),
]

urlpatterns += [
    path('api/dashboard-analytics/', dashboard_analytics_api, name='dashboard_analytics_api'),
]

urlpatterns += [
    path('api/boundary-completeness/', boundary_completeness_report, name='boundary_completeness_report'),
    path('api/area-coverage/', area_coverage_report, name='area_coverage_report'),
    path('export-excel/', export_excel_report, name='export_excel_report'),
    path('api/user-activity/', user_activity_api, name='user_activity_api'),
    path('api/coverage-map/', coverage_map_data, name='coverage_map_data'),
]

urlpatterns += [
    path('api/v1/surveys/upload-csv/', CSVUploadAPIView.as_view(), name='api_upload_csv'),
    path('api/v1/surveys/export-kml/', export_kml_api, name='api_export_kml'),

    # Search API
    path('api/v1/surveys/spatial-query/', spatial_query_api, name='api_spatial_query'),

    # Google Earth Integration
    path('api/v1/surveys/google-earth/<int:pk>/', google_earth_link_api, name='api_google_earth_link'),
    path('api/v1/surveys/kml-export/', kml_export_google_earth_api, name='api_kml_export_google_earth'),

    # Dashboard API
    path('api/v1/dashboard/stats/', dashboard_stats_api, name='api_dashboard_stats'),
    path('api/v1/dashboard/coverage/', dashboard_coverage_api, name='api_dashboard_coverage'),
]

urlpatterns += [
    path('api/v1/boundaries/', boundaries_geojson_api, name='api_boundaries_geojson'),
    path('api/v1/boundaries/<int:pk>/', boundaries_geojson_api, name='api_boundaries_geojson_detail'),
]

urlpatterns += [
    path('list/', survey_list_view, name='survey_list'),
    path('add/', survey_add_view, name='survey_add'),
    path('map/', map_view, name='map_view'),
]

urlpatterns += [
    path('edit/<int:pk>/', survey_edit_view, name='survey_edit'),
    path('delete/<int:pk>/', survey_delete_view, name='survey_delete'),
]

urlpatterns += [
    path('download-generated-kml/', download_generated_kml, name='download_generated_kml'),
]

urlpatterns += [
    path('download-all-surveys-kml/', download_all_surveys_kml, name='download_all_surveys_kml'),
]

urlpatterns += [
    path('download-error-report/', download_error_report, name='download_error_report'),
]

urlpatterns += [
    path('help/', help_view, name='help'),
]

urlpatterns += [
    path('advanced-csv-upload/', advanced_csv_upload, name='advanced_csv_upload'),
    path('dashboard/', dashboard_view, name='dashboard'),
]

urlpatterns += [
    path('export-excel/', excel_export_view, name='excel_export'),
    path('export-kml/', kml_export_view, name='kml_export'),
    path('export-pdf/', pdf_export_view, name='pdf_export'),
]

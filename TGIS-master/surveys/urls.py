from django.urls import path
from .views import csv_upload_view, csv_export_view, attachment_upload_view, attachment_delete_view, survey_search_view, dashboard_analytics_api, boundary_completeness_report, area_coverage_report, export_excel_report, user_activity_api, coverage_map_data, advanced_search_api, pdf_report_view, SurveyRecordViewSet, CSVUploadAPIView, export_kml_api, survey_search_api, boundary_search_api, spatial_query_api, google_earth_link_api, kml_export_google_earth_api, dashboard_stats_api, dashboard_coverage_api, survey_list_view, survey_add_view, map_view, survey_edit_view, survey_delete_view, csv_to_kml_view, download_generated_kml, download_all_surveys_kml, dashboard_view, csv_to_kml_from_mapping, download_error_report, help_view
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
    path('search/', survey_search_view, name='survey_search'),
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
    path('api/advanced-search/', advanced_search_api, name='advanced_search_api'),
]

urlpatterns += [
    path('pdf-report/', pdf_report_view, name='pdf_report_batch'),
    path('pdf-report/<int:survey_id>/', pdf_report_view, name='pdf_report'),
]

urlpatterns += router.urls

urlpatterns += [
    # File Upload API
    path('api/v1/surveys/upload-csv/', CSVUploadAPIView.as_view(), name='api_upload_csv'),
    path('api/v1/surveys/export-kml/', export_kml_api, name='api_export_kml'),

    # Search API
    path('api/v1/surveys/search/', survey_search_api, name='api_survey_search'),
    path('api/v1/surveys/boundary-search/', boundary_search_api, name='api_boundary_search'),
    path('api/v1/surveys/spatial-query/', spatial_query_api, name='api_spatial_query'),

    # Google Earth Integration
    path('api/v1/surveys/google-earth/<int:pk>/', google_earth_link_api, name='api_google_earth_link'),
    path('api/v1/surveys/kml-export/', kml_export_google_earth_api, name='api_kml_export_google_earth'),

    # Dashboard API
    path('api/v1/dashboard/stats/', dashboard_stats_api, name='api_dashboard_stats'),
    path('api/v1/dashboard/coverage/', dashboard_coverage_api, name='api_dashboard_coverage'),
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
    path('csv-to-kml/', csv_to_kml_view, name='csv_to_kml'),
    path('download-generated-kml/', download_generated_kml, name='download_generated_kml'),
]

urlpatterns += [
    path('download-all-surveys-kml/', download_all_surveys_kml, name='download_all_surveys_kml'),
]

urlpatterns += [
    path('csv-to-kml-from-mapping/', csv_to_kml_from_mapping, name='csv_to_kml_from_mapping'),
]

urlpatterns += [
    path('download-error-report/', download_error_report, name='download_error_report'),
]

urlpatterns += [
    path('help/', help_view, name='help'),
]

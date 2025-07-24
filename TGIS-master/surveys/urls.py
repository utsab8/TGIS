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
    excel_export_view, kml_export_view, pdf_export_view, upload_history_view,
    custom_login_view, admin_dashboard_view, user_list_view, user_add_view, user_edit_view, user_delete_view,
    custom_logout_view, user_dashboard_view, export_users_csv, export_logs_csv, delete_old_logs, admin_logs_api,
    activity_view, settings_view
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
    path('login/', custom_login_view, name='login'),
    path('logout/', custom_logout_view, name='logout'),
    path('admin-dashboard/', admin_dashboard_view, name='admin_dashboard'),
    path('user-dashboard/', user_dashboard_view, name='user_dashboard'),
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

urlpatterns += [
    path('upload-history/', upload_history_view, name='upload_history'),
]

urlpatterns += [
    path('user-management/', user_list_view, name='user_list'),
    path('user-management/add/', user_add_view, name='user_add'),
    path('user-management/<int:user_id>/edit/', user_edit_view, name='user_edit'),
    path('user-management/<int:user_id>/delete/', user_delete_view, name='user_delete'),
]

urlpatterns += [
    path('admin/export-users-csv/', export_users_csv, name='export_users_csv'),
]

urlpatterns += [
    path('admin/export-logs-csv/', export_logs_csv, name='export_logs_csv'),
]

urlpatterns += [
    path('admin/delete-old-logs/', delete_old_logs, name='delete_old_logs'),
]

urlpatterns += [
    path('admin/api/logs/', admin_logs_api, name='admin_logs_api'),
]

urlpatterns += [
    path('activity/', activity_view, name='activity'),
    path('help/', help_view, name='help'),
    path('settings/', settings_view, name='settings'),
]

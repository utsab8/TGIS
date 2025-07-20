from django.contrib import admin
from .models import SurveyRecord, KMLFile, KMLBoundary, FileAttachment

@admin.register(SurveyRecord)
class SurveyRecordAdmin(admin.ModelAdmin):
    list_display = ('kitta_number', 'owner_name', 'created_at', 'uploaded_by')
    search_fields = ('kitta_number', 'owner_name', 'land_type')
    list_filter = ('created_at', 'uploaded_by', 'data_source')

@admin.register(KMLFile)
class KMLFileAdmin(admin.ModelAdmin):
    list_display = ('file_name', 'uploaded_at', 'uploaded_by', 'file_size', 'processed', 'total_features')
    search_fields = ('file_name',)
    list_filter = ('uploaded_at', 'processed')

@admin.register(KMLBoundary)
class KMLBoundaryAdmin(admin.ModelAdmin):
    list_display = ('kitta_number', 'kml_file', 'area_sqm', 'perimeter_m', 'created_at')
    search_fields = ('kitta_number',)
    list_filter = ('kml_file',)

@admin.register(FileAttachment)
class FileAttachmentAdmin(admin.ModelAdmin):
    list_display = ('survey_record', 'file_path', 'file_type', 'uploaded_at', 'file_size')
    list_filter = ('uploaded_at',)

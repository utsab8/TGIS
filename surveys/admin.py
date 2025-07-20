from django.contrib import admin
from .models import SurveyRecord, FileAttachment

@admin.register(SurveyRecord)
class SurveyRecordAdmin(admin.ModelAdmin):
    list_display = ('kitta_number', 'owner_name', 'created_at', 'uploaded_by')
    search_fields = ('kitta_number', 'owner_name', 'land_type')
    list_filter = ('created_at', 'uploaded_by', 'data_source')

@admin.register(FileAttachment)
class FileAttachmentAdmin(admin.ModelAdmin):
    list_display = ('survey_record', 'file_path', 'file_type', 'uploaded_at', 'file_size')
    list_filter = ('uploaded_at',)

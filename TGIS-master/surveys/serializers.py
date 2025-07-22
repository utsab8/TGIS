from rest_framework import serializers
from .models import SurveyRecord, FileAttachment, Boundary

class SurveyRecordSerializer(serializers.ModelSerializer):
    class Meta:
        model = SurveyRecord
        fields = '__all__'

class FileAttachmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = FileAttachment
        fields = '__all__'

class BoundarySerializer(serializers.ModelSerializer):
    class Meta:
        model = Boundary
        fields = ['id', 'survey_record', 'geojson', 'created_at', 'updated_at']

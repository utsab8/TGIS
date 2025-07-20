from rest_framework import serializers
from .models import SurveyRecord, KMLFile, KMLBoundary, FileAttachment

class SurveyRecordSerializer(serializers.ModelSerializer):
    class Meta:
        model = SurveyRecord
        fields = '__all__'

class KMLFileSerializer(serializers.ModelSerializer):
    class Meta:
        model = KMLFile
        fields = '__all__'

class KMLBoundarySerializer(serializers.ModelSerializer):
    class Meta:
        model = KMLBoundary
        fields = '__all__'

class FileAttachmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = FileAttachment
        fields = '__all__'

from rest_framework import serializers
from .models import SurveyRecord, FileAttachment

class SurveyRecordSerializer(serializers.ModelSerializer):
    class Meta:
        model = SurveyRecord
        fields = '__all__'

class FileAttachmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = FileAttachment
        fields = '__all__'

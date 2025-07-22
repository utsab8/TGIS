from django.db import models
from django.conf import settings

# Create your models here.

class SurveyRecord(models.Model):
    kitta_number = models.CharField(max_length=100, unique=True, null=True, blank=True)
    owner_name = models.CharField(max_length=255, null=True, blank=True)
    lat = models.DecimalField(max_digits=10, decimal_places=7, null=True, blank=True)
    lon = models.DecimalField(max_digits=10, decimal_places=7, null=True, blank=True)
    land_type = models.CharField(max_length=100, blank=True, null=True)
    area_size = models.DecimalField(max_digits=20, decimal_places=2, blank=True, null=True)
    has_boundary = models.BooleanField(default=False)
    data_source = models.CharField(max_length=20, choices=[('CSV','CSV'),('Manual','Manual')], default='Manual')
    created_at = models.DateTimeField(auto_now_add=True, null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True, null=True, blank=True)
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)

    def __str__(self):
        return f"{self.kitta_number} - {self.owner_name}"

class FileAttachment(models.Model):
    survey_record = models.ForeignKey(SurveyRecord, on_delete=models.CASCADE, related_name='attachments')
    file_path = models.FileField(upload_to='attachments/', null=True, blank=True)
    file_type = models.CharField(max_length=50, null=True, blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True, null=True, blank=True)
    file_size = models.PositiveIntegerField(null=True, blank=True)

    def __str__(self):
        return f"Attachment for {self.survey_record.kitta_number}"

class UploadHistory(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    filename = models.CharField(max_length=255)
    upload_time = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=20, choices=[('Success', 'Success'), ('Failed', 'Failed')], default='Success')
    error_message = models.TextField(blank=True, null=True)

    def __str__(self):
        return f"{self.filename} uploaded by {self.user} at {self.upload_time} - {self.status}"

class Boundary(models.Model):
    survey_record = models.ForeignKey(SurveyRecord, on_delete=models.CASCADE, related_name='boundaries')
    geojson = models.JSONField()  # Store polygon as GeoJSON
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Boundary for {self.survey_record.kitta_number}"

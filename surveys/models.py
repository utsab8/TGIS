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
    data_source = models.CharField(max_length=20, choices=[('CSV','CSV'),('KML','KML'),('Manual','Manual')], default='Manual')
    created_at = models.DateTimeField(auto_now_add=True, null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True, null=True, blank=True)
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)

    def __str__(self):
        return f"{self.kitta_number} - {self.owner_name}"

class KMLFile(models.Model):
    file_name = models.CharField(max_length=255, null=True, blank=True)
    file_path = models.FileField(upload_to='uploads/kml/', null=True, blank=True)
    file_size = models.PositiveIntegerField(null=True, blank=True)
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True, null=True, blank=True)
    processed = models.BooleanField(default=False)
    total_features = models.PositiveIntegerField(default=0, null=True, blank=True)

    def __str__(self):
        return self.file_name or str(self.id)

class KMLBoundary(models.Model):
    survey_record = models.ForeignKey(SurveyRecord, on_delete=models.SET_NULL, null=True, blank=True, related_name='boundaries')
    kml_file = models.ForeignKey(KMLFile, on_delete=models.CASCADE, related_name='boundaries')
    kitta_number = models.CharField(max_length=100, blank=True, null=True)
    polygon_data = models.TextField(null=True, blank=True)  # GeoJSON format
    area_sqm = models.DecimalField(max_digits=20, decimal_places=2, blank=True, null=True)
    perimeter_m = models.DecimalField(max_digits=20, decimal_places=2, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True, null=True, blank=True)

    def __str__(self):
        return f"Boundary: {self.kitta_number or self.id} in {self.kml_file.file_name}"

class FileAttachment(models.Model):
    survey_record = models.ForeignKey(SurveyRecord, on_delete=models.CASCADE, related_name='attachments')
    file_path = models.FileField(upload_to='attachments/', null=True, blank=True)
    file_type = models.CharField(max_length=50, null=True, blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True, null=True, blank=True)
    file_size = models.PositiveIntegerField(null=True, blank=True)

    def __str__(self):
        return f"Attachment for {self.survey_record.kitta_number}"

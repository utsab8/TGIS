from django.db import models
from django.core.validators import MinValueValidator
from decimal import Decimal


class LandParcel(models.Model):
    """
    Model to store land parcel information extracted from KML files
    """
    kitta_number = models.CharField(
        max_length=50, 
        unique=True,
        help_text="Unique identifier for the land parcel"
    )
    owner_name = models.CharField(
        max_length=200,
        help_text="Name of the land owner"
    )
    area = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))],
        help_text="Area of the land parcel in square meters"
    )
    coordinates = models.TextField(
        help_text="Geographic coordinates in KML format"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = "Land Parcel"
        verbose_name_plural = "Land Parcels"
    
    def __str__(self):
        return f"Kitta: {self.kitta_number} - Owner: {self.owner_name}"
    
    def get_area_hectares(self):
        """Convert area from square meters to hectares"""
        return self.area / 10000
    
    def get_coordinates_list(self):
        """Parse coordinates string into list of coordinate pairs"""
        if not self.coordinates:
            return []
        
        coords = []
        lines = self.coordinates.strip().split('\n')
        for line in lines:
            line = line.strip()
            if line:
                parts = line.split(',')
                if len(parts) >= 2:
                    try:
                        lon = float(parts[0])
                        lat = float(parts[1])
                        coords.append((lon, lat))
                    except ValueError:
                        continue
        return coords

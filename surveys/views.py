from django.shortcuts import render, redirect
from django.contrib import messages
from django import forms
from .models import SurveyRecord, KMLFile, KMLBoundary, FileAttachment
import csv
from django.http import HttpResponse
from fastkml import kml
from django.conf import settings
import os
from django.core.paginator import Paginator
from django.db.models import Q
import simplekml
from django.urls import reverse
from django.views.decorators.cache import cache_page
from django.http import JsonResponse
from django.views.decorators.http import require_GET

import math
import io
import xlsxwriter
from django.contrib.auth import get_user_model
from django.views.decorators.csrf import csrf_exempt
from django.db.models import F
from math import radians, cos, sin, asin, sqrt
import qrcode
import base64
from io import BytesIO
from django.template.loader import render_to_string
from weasyprint import HTML
from django.core.cache import cache
from django.views.decorators.cache import cache_page
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect
from django.core.exceptions import SuspiciousFileOperation
import logging
from django_ratelimit.decorators import ratelimit

from rest_framework import viewsets, status
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.permissions import IsAuthenticatedOrReadOnly, AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.parsers import MultiPartParser, FormParser
from .serializers import SurveyRecordSerializer, KMLFileSerializer, KMLBoundarySerializer, FileAttachmentSerializer
from django.shortcuts import get_object_or_404
from django.contrib.auth.decorators import login_required

logger = logging.getLogger(__name__)

def calculate_polygon_area(coords):
    # Simple area calculation for lat/lon polygon (approximate, not for production GIS)
    # Uses Shoelace formula, assumes coords is [(lat, lon), ...]
    if len(coords) < 3:
        return 0
    area = 0
    for i in range(len(coords)):
        lat1, lon1 = coords[i]
        lat2, lon2 = coords[(i + 1) % len(coords)]
        area += math.radians(lon1) * math.sin(math.radians(lat2)) - math.radians(lon2) * math.sin(math.radians(lat1))
    return abs(area * 6378137 * 6378137 / 2)  # Earth radius in meters

def haversine(lat1, lon1, lat2, lon2):
    # Calculate the great circle distance between two points on the earth (specified in decimal degrees)
    # Returns distance in meters
    lon1, lat1, lon2, lat2 = map(radians, [lon1, lat1, lon2, lat2])
    dlon = lon2 - lon1
    dlat = lat2 - lat1
    a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
    c = 2 * asin(sqrt(a))
    r = 6371000  # Radius of earth in meters
    return c * r

@cache_page(60 * 5)
def dashboard_analytics_api(request):
    total_points = SurveyRecord.objects.count()
    total_boundaries = KMLBoundary.objects.count()
    total_area = 0
    for boundary in KMLBoundary.objects.all():
        try:
            coords = eval(boundary.coordinates)
            total_area += calculate_polygon_area(coords)
        except Exception:
            continue
    data = {
        'total_points': total_points,
        'total_boundaries': total_boundaries,
        'total_area_m2': round(total_area, 2),
    }
    return JsonResponse(data)

@csrf_exempt
def advanced_search_api(request):
    import json
    params = request.GET if request.method == 'GET' else json.loads(request.body)
    kitta = params.get('kitta', '')
    owner = params.get('owner', '')
    lat = params.get('lat', '')
    lon = params.get('lon', '')
    radius = float(params.get('radius', 0))
    boundary_id = params.get('boundary_id', None)
    highlight_ids = []
    results = SurveyRecord.objects.all()
    if kitta:
        results = results.filter(kitta_number__icontains=kitta)
    if owner:
        from django.db.models import Q
        results = results.filter(Q(owner_name__icontains=owner) | Q(owner_name__unaccent__icontains=owner))
    if lat and lon and radius > 0:
        lat, lon = float(lat), float(lon)
        filtered = []
        for rec in results:
            if hasattr(rec, 'lat') and hasattr(rec, 'lon') and rec.lat and rec.lon:
                d = haversine(lat, lon, float(rec.lat), float(rec.lon))
                if d <= radius:
                    filtered.append(rec.id)
        results = results.filter(id__in=filtered)
    if boundary_id:
        # Find plots within a given boundary (simple bounding box, not true polygon test)
        try:
            boundary = KMLBoundary.objects.get(id=boundary_id)
            coords = eval(boundary.coordinates)
            lats = [lat for lat, lon in coords]
            lons = [lon for lat, lon in coords]
            min_lat, max_lat = min(lats), max(lats)
            min_lon, max_lon = min(lons), max(lons)
            results = results.filter(lat__gte=min_lat, lat__lte=max_lat, lon__gte=min_lon, lon__lte=max_lon)
        except Exception:
            pass
    highlight_ids = list(results.values_list('id', flat=True))
    # Return results and highlight IDs for map
    return JsonResponse({'results': list(results.values()), 'highlight_ids': highlight_ids})

# Create your views here.

class CSVUploadForm(forms.Form):
    file = forms.FileField(label='Select CSV file')


def csv_upload_view(request):
    if request.method == 'POST':
        form = CSVUploadForm(request.POST, request.FILES)
        if form.is_valid():
            csv_file = form.cleaned_data['file']
            if not csv_file.name.endswith('.csv'):
                messages.error(request, 'File is not CSV type')
                return redirect('csv_upload')
            try:
                decoded_file = csv_file.read().decode('utf-8').splitlines()
                reader = csv.DictReader(decoded_file)
                required_fields = {'Kitta Number', 'Latitude', 'Longitude'}
                updated_count = 0
                created_count = 0
                for i, row in enumerate(reader, 1):
                    if not required_fields.issubset(row):
                        messages.error(request, f'Missing required fields in row {i}')
                        continue
                    try:
                        lat = float(row['Latitude'])
                        lon = float(row['Longitude'])
                    except ValueError:
                        messages.error(request, f'Invalid lat/lon in row {i}')
                        continue
                    obj, created = SurveyRecord.objects.update_or_create(
                        kitta_number=row['Kitta Number'],
                        defaults={
                            'owner_name': row.get('Owner Name', ''),
                            'land_type': row.get('Land Type', ''),
                            'area_size': row.get('Area Size (sq m)', 0),
                            'lat': lat,
                            'lon': lon,
                            'data_source': 'CSV',
                        }
                    )
                    if created:
                        created_count += 1
                    else:
                        updated_count += 1
                messages.success(request, f'CSV upload completed! {created_count} created, {updated_count} updated.')
                return redirect('csv_upload')
            except Exception as e:
                messages.error(request, f'Error processing file: {e}')
    else:
        form = CSVUploadForm()
    return render(request, 'surveys/upload_csv.html', {'form': form})

# Download all survey records as KML
import simplekml
from django.http import HttpResponse

def download_all_surveys_kml(request):
    kml = simplekml.Kml()
    all_coords = []  # Collect all coordinates for camera positioning
    
    # Add polygons/lines from KMLBoundary
    for boundary in KMLBoundary.objects.all():
        name = boundary.kitta_number or ''
        description = f"Area: {boundary.area_sqm or ''} sq m"
        coords = []
        if boundary.polygon_data:
            try:
                coords = eval(boundary.polygon_data)
            except Exception:
                coords = []
        if coords:
            # Only use the first two values (lat, lon) for each coordinate
            safe_coords = []
            for coord in coords:
                if len(coord) >= 2:
                    lat, lon = coord[:2]
                    safe_coords.append((lon, lat))
                    all_coords.append((lon, lat))
            if len(safe_coords) > 2:
                pol = kml.newpolygon(name=name, outerboundaryis=safe_coords)
                pol.description = description
            elif len(safe_coords) == 2:
                line = kml.newlinestring(name=name, coords=safe_coords)
                line.description = description
    # Add points from SurveyRecord
    for record in SurveyRecord.objects.all():
        if record.lat and record.lon:
            desc = f"Owner: {record.owner_name or ''}\nLand Type: {record.land_type or ''}\nArea: {record.area_size or ''} sq m"
            pnt = kml.newpoint(name=record.kitta_number or '', description=desc, coords=[(float(record.lon), float(record.lat))])
            pnt.extendeddata.newdata(name='Kitta Number', value=record.kitta_number or '')
            pnt.extendeddata.newdata(name='Owner Name', value=record.owner_name or '')
            pnt.extendeddata.newdata(name='Land Type', value=record.land_type or '')
            pnt.extendeddata.newdata(name='Area Size (sq m)', value=str(record.area_size or ''))
            pnt.extendeddata.newdata(name='Latitude', value=str(record.lat or ''))
            pnt.extendeddata.newdata(name='Longitude', value=str(record.lon or ''))
            all_coords.append((float(record.lon), float(record.lat)))
    
    # Add camera positioning if we have coordinates
    if all_coords:
        lons = [coord[0] for coord in all_coords]
        lats = [coord[1] for coord in all_coords]
        center_lon = sum(lons) / len(lons)
        center_lat = sum(lats) / len(lats)
        
        # Calculate appropriate altitude based on data spread
        lon_range = max(lons) - min(lons)
        lat_range = max(lats) - min(lats)
        max_range = max(lon_range, lat_range)
        
        # Set altitude based on the spread of data
        if max_range > 1:  # Large area
            altitude = 1000000  # 1000 km
        elif max_range > 0.1:  # Medium area
            altitude = 100000   # 100 km
        elif max_range > 0.01:  # Small area
            altitude = 10000    # 10 km
        else:  # Very small area
            altitude = 1000     # 1 km
        
        # Set camera to look at the center of all data
        kml.camera.longitude = center_lon
        kml.camera.latitude = center_lat
        kml.camera.altitude = altitude
        kml.camera.tilt = 0
        kml.camera.heading = 0
        kml.camera.altitudemode = simplekml.AltitudeMode.relativetoground
    
    kml_data = kml.kml()
    response = HttpResponse(kml_data, content_type='application/vnd.google-earth.kml+xml')
    response['Content-Disposition'] = 'attachment; filename="all_survey_records.kml"'
    return response


def csv_export_view(request):
    records = SurveyRecord.objects.all()
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="survey_records.csv"'
    writer = csv.writer(response)
    writer.writerow(['Kitta Number', 'Owner Name', 'Land Type', 'Area Size (sq m)', 'Latitude', 'Longitude', 'Data Source', 'Created At', 'Updated At'])
    for record in records:
        writer.writerow([
            record.kitta_number or '',
            record.owner_name or '',
            record.land_type or '',
            record.area_size or '',
            record.lat or '',
            record.lon or '',
            record.data_source or '',
            record.created_at.strftime('%Y-%m-%d %H:%M:%S') if record.created_at else '',
            record.updated_at.strftime('%Y-%m-%d %H:%M:%S') if record.updated_at else '',
        ])
    return response


class KMLUploadForm(forms.Form):
    file = forms.FileField(label='Select KML file')


@csrf_protect
@ratelimit(key='ip', rate='5/m', block=True)
def kml_upload_view(request):
    if request.method == 'POST':
        form = KMLUploadForm(request.POST, request.FILES)
        if form.is_valid():
            kml_file = form.cleaned_data['file']
            # Security: Validate file extension and content
            if not kml_file.name.endswith('.kml') or kml_file.content_type not in ['application/vnd.google-earth.kml+xml', 'application/xml', 'text/xml']:
                messages.error(request, 'Invalid KML file type.')
                logger.warning(f'Blocked KML upload: {kml_file.name}')
                return redirect('kml_upload')
            try:
                kml_bytes = kml_file.read()
                kml_content = kml_bytes.decode('utf-8')
                if '<kml' not in kml_content:
                    raise SuspiciousFileOperation('Not a valid KML file')
                # Caching: avoid reprocessing same file
                cache_key = f'kml_{hash(kml_content)}'
                if cache.get(cache_key):
                    messages.info(request, 'This KML file was already processed.')
                    return redirect('kml_upload')
                
                # Debug: Log the first 500 characters of KML content
                logger.info(f'KML content preview: {kml_content[:500]}...')
                
                # Basic KML validation
                if '<kml' not in kml_content.lower():
                    messages.error(request, 'Invalid KML file: Missing KML root element.')
                    return redirect('kml_upload')
                
                if '<placemark' not in kml_content.lower() and '<polygon' not in kml_content.lower() and '<point' not in kml_content.lower():
                    messages.warning(request, 'KML file does not contain Placemarks, Polygons, or Points. Please check your KML file structure.')
                
                # Use comprehensive KML validation
                validation_result = kml_validator.validate_kml_geometry(kml_content)
                
                # Log validation results
                logger.info(f'KML Validation Results:')
                logger.info(f'  Features found: {validation_result["features_found"]}')
                logger.info(f'  Geometries found: {validation_result["geometries_found"]}')
                logger.info(f'  Coordinates found: {validation_result["coordinates_found"]}')
                logger.info(f'  Is valid: {validation_result["is_valid"]}')
                
                if validation_result['errors']:
                    logger.error(f'KML Validation Errors: {validation_result["errors"]}')
                
                if validation_result['warnings']:
                    logger.warning(f'KML Validation Warnings: {validation_result["warnings"]}')
                
                # Check if KML is valid
                if not validation_result['is_valid']:
                    error_message = "KML validation failed:\n"
                    if validation_result['errors']:
                        error_message += "\n".join([f"• {error}" for error in validation_result['errors']])
                    if validation_result['warnings']:
                        error_message += "\n\nWarnings:\n" + "\n".join([f"• {warning}" for warning in validation_result['warnings']])
                    if validation_result['suggestions']:
                        error_message += "\n\nSuggestions:\n" + "\n".join([f"• {suggestion}" for suggestion in validation_result['suggestions']])
                    
                    messages.error(request, error_message)
                    return redirect('kml_upload')
                
                # Extract features from validation result
                all_features = []
                for feature_info in validation_result['parsed_features']:
                    if feature_info['has_geometry'] and feature_info['parsed_coordinates']:
                        # Create a simple feature object
                        class ValidatedFeature:
                            def __init__(self, name, geometry_type, coordinates, description=""):
                                self.name = name
                                self.geometry_type = geometry_type
                                self.coordinates = coordinates
                                self.description = description
                            
                            def __getattr__(self, name):
                                if name == 'geometry':
                                    return self
                                return None
                        
                        feature = ValidatedFeature(
                            name=feature_info['name'] or f'Feature_{feature_info["index"]}',
                            geometry_type=feature_info['geometry_type'],
                            coordinates=feature_info['parsed_coordinates'],
                            description=feature_info['description']
                        )
                        all_features.append(feature)
                
                # All features are now extracted from the validation result above
                
                logger.info(f'Total validated features found: {len(all_features)}')
                
                # Debug: Log each feature found
                for i, feat in enumerate(all_features):
                    logger.info(f'Feature {i}: Type={type(feat)}, Name={getattr(feat, "name", "Unnamed")}')
                    logger.info(f'Feature {i}: Geometry type={getattr(feat, "geometry_type", "Unknown")}')
                    logger.info(f'Feature {i}: Coordinates count={len(getattr(feat, "coordinates", []))}')
                
                if not all_features:
                    messages.error(request, 'No valid features found in KML. Please check if the KML file contains valid placemarks with proper geometry and coordinates.')
                    return redirect('kml_upload')
                
                try:
                    boundaries_created = 0
                    kml_db = KMLFile.objects.create(file_name=kml_file.name, file_path=kml_file)
                    csv_rows = []
                    
                    def process_feature_safe(feat):
                        """Safely process a KML feature"""
                        nonlocal boundaries_created
                        try:
                            logger.info(f'Processing feature: {type(feat)} - {getattr(feat, "name", "Unnamed")}')
                            logger.info(f'Feature attributes: {dir(feat)}')
                            logger.info(f'Has geometry: {hasattr(feat, "geometry")}')
                            if hasattr(feat, 'geometry'):
                                logger.info(f'Geometry type: {type(feat.geometry)}')
                                logger.info(f'Geometry is None: {feat.geometry is None}')
                            
                            # If it's a container (Document/Folder), recurse
                            if hasattr(feat, 'features'):
                                try:
                                    sub_features = feat.features()
                                    if sub_features:
                                        if isinstance(sub_features, list):
                                            logger.info(f'Container has {len(sub_features)} sub-features')
                                            for subfeat in sub_features:
                                                process_feature_safe(subfeat)
                                        elif hasattr(sub_features, '__iter__'):
                                            sub_list = list(sub_features)
                                            logger.info(f'Container has {len(sub_list)} sub-features')
                                            for subfeat in sub_list:
                                                process_feature_safe(subfeat)
                                        else:
                                            logger.info('Container has 1 sub-feature')
                                            process_feature_safe(sub_features)
                                except Exception as e:
                                    logger.error(f'Error processing sub-features: {e}')
                            
                            # Process validated features
                            if hasattr(feat, 'coordinates') and feat.coordinates:
                                try:
                                    # Use validated coordinates directly
                                    coords = feat.coordinates
                                    
                                    if coords:
                                        # Validate coordinate ranges
                                        valid_coords = []
                                        for coord_pair in coords:
                                            if len(coord_pair) >= 2:
                                                lon, lat = coord_pair[0], coord_pair[1]
                                                if isinstance(lon, (int, float)) and isinstance(lat, (int, float)):
                                                    if -90 <= lat <= 90 and -180 <= lon <= 180:
                                                        valid_coords.append([lon, lat])
                                                    else:
                                                        logger.warning(f'Invalid coordinate range: {lat}, {lon}')
                                                else:
                                                    logger.warning(f'Non-numeric coordinate: {coord_pair}')
                                        
                                        if valid_coords:
                                            # Create KML boundary
                                            KMLBoundary.objects.create(
                                                kml_file=kml_db,
                                                kitta_number=getattr(feat, 'name', 'Unnamed'),
                                                polygon_data=str(valid_coords)
                                            )
                                            boundaries_created += 1
                                            
                                            # Add to CSV rows
                                            for coord in valid_coords:
                                                lon, lat = coord[:2]
                                                csv_rows.append({
                                                    'Kitta Number': getattr(feat, 'name', 'Unnamed'),
                                                    'Owner Name': '',
                                                    'Land Type': 'other',
                                                    'Area Size (sq m)': 0,
                                                    'Latitude': lat,
                                                    'Longitude': lon,
                                                    'Address': '',
                                                    'Remarks': getattr(feat, 'description', ''),
                                                    'Created At': '',
                                                    'Updated At': ''
                                                })
                                        else:
                                            logger.error(f'No valid coordinates found for feature: {getattr(feat, "name", "Unnamed")}')
                                except Exception as e:
                                    logger.error(f'Error processing validated feature: {e}')
                                try:
                                    # Use coordinates directly from simple feature
                                    coords = feat.coordinates
                                    
                                    if coords:
                                        # Validate and store coordinates
                                        valid_coords = validate_coordinates(coords)
                                        
                                        if valid_coords:
                                            # Create KML boundary
                                            KMLBoundary.objects.create(
                                                kml_file=kml_db,
                                                kitta_number=getattr(feat, 'name', 'Unnamed'),
                                                polygon_data=str(valid_coords)
                                            )
                                            boundaries_created += 1
                                            
                                            # Add to CSV rows
                                            for coord in valid_coords:
                                                lon, lat = coord[:2]
                                                csv_rows.append({
                                                    'Kitta Number': getattr(feat, 'name', 'Unnamed'),
                                                    'Owner Name': '',
                                                    'Land Type': 'other',
                                                    'Area Size (sq m)': 0,
                                                    'Latitude': lat,
                                                    'Longitude': lon,
                                                    'Address': '',
                                                    'Remarks': getattr(feat, 'description', ''),
                                                    'Created At': '',
                                                    'Updated At': ''
                                                })
                                except Exception as e:
                                    logger.error(f'Error processing simple feature: {e}')
                        except Exception as e:
                            logger.error(f'Error processing feature: {e}')
                    
                    # Coordinate validation is now handled by the KML validator
                    
                    # Process all features
                    for feat in all_features:
                        process_feature_safe(feat)
                        
                except Exception as e:
                    logger.error(f'Error in KML parsing: {e}')
                    messages.error(request, f'KML parsing error: {e}')
                    return redirect('kml_upload')
                cache.set(cache_key, True, 60*60)  # Cache for 1 hour
                # Generate CSV with all KML details
                csv_data = extract_kml_to_csv(kml_bytes)
                request.session['kml_csv_data'] = csv_data
                if boundaries_created == 0:
                    messages.warning(request, 'No valid polygons/points found in KML. This might be due to the KML structure or coordinate format.')
                    # Create a test KML file for debugging
                    try:
                        test_kml = simplekml.Kml()
                        pnt = test_kml.newpoint(name='Test Point')
                        pnt.coords = [(85.3, 27.7)]  # Kathmandu coordinates
                        test_kml_path = os.path.join(settings.MEDIA_ROOT, 'test_kml.kml')
                        test_kml.save(test_kml_path)
                        logger.info(f'Created test KML file at: {test_kml_path}')
                    except Exception as e:
                        logger.error(f'Error creating test KML: {e}')
                else:
                    messages.success(request, f'KML upload successful! {boundaries_created} boundaries/points extracted.')
                return redirect('kml_upload')
            except Exception as e:
                logger.error(f'KML parsing error: {e}')
                messages.error(request, f'KML parsing error: {e}')
                return redirect('kml_upload')
    else:
        form = KMLUploadForm()
    # Check if CSV is available in session for download link
    csv_available = 'kml_csv_data' in request.session
    return render(request, 'surveys/upload_kml.html', {'form': form, 'csv_available': csv_available})

def extract_kml_to_csv(kml_bytes):
    import io
    import csv

    try:
        # Convert bytes to string for validation
        kml_content = kml_bytes.decode('utf-8')
        
        # Use the comprehensive KML validator
        validation_result = kml_validator.validate_kml_geometry(kml_content)
        
        if not validation_result['is_valid']:
            logger.error(f'KML validation failed in CSV extraction: {validation_result["errors"]}')
            return ""
        
        # Extract features from validation result
        all_features = []
        for feature_info in validation_result['parsed_features']:
            if feature_info['has_geometry'] and feature_info['parsed_coordinates']:
                # Create a simple feature object for CSV extraction
                class CSVFeature:
                    def __init__(self, name, coordinates, description=""):
                        self.name = name
                        self.coordinates = coordinates
                        self.description = description
                    
                    def __getattr__(self, name):
                        if name == 'geometry':
                            return self
                        return None
                
                feature = CSVFeature(
                    name=feature_info['name'] or f'Feature_{feature_info["index"]}',
                    coordinates=feature_info['parsed_coordinates'],
                    description=feature_info['description']
                )
                all_features.append(feature)
        
        placemark_rows = []

        def process_feature_safe(feat):
            """Safely process a KML feature for CSV extraction"""
            try:
                # Process validated features directly
                if hasattr(feat, 'coordinates') and feat.coordinates:
                    # Map KML fields to the desired CSV columns
                    base_data = {
                        'Kitta Number': getattr(feat, 'name', ''),
                        'Owner Name': '',
                        'Land Type': 'other',
                        'Area Size (sq m)': 0,
                        'Address': '',
                        'Remarks': getattr(feat, 'description', ''),
                        'Created At': '',
                        'Updated At': ''
                    }
                    
                    # Try to extract Owner Name, Address, etc. from ExtendedData if present
                    try:
                        if hasattr(feat, 'etree_element'):
                            elem = feat.etree_element()
                            ext_data = elem.find('.//{http://www.opengis.net/kml/2.2}ExtendedData')
                            if ext_data is not None:
                                for data_elem in ext_data.findall('.//{http://www.opengis.net/kml/2.2}Data'):
                                    key = data_elem.get('name')
                                    value_elem = data_elem.find('{http://www.opengis.net/kml/2.2}value')
                                    value = value_elem.text if value_elem is not None else ''
                                    if key:
                                        if key.lower() in ['owner', 'owner_name', 'ownername']:
                                            base_data['Owner Name'] = value
                                        elif key.lower() in ['address']:
                                            base_data['Address'] = value
                                        elif key.lower() in ['remarks', 'remark']:
                                            base_data['Remarks'] = value
                                        elif key.lower() in ['created_at', 'createdat']:
                                            base_data['Created At'] = value
                                        elif key.lower() in ['updated_at', 'updatedat']:
                                            base_data['Updated At'] = value
                                        elif key.lower() in ['land_type', 'landtype']:
                                            base_data['Land Type'] = value
                                        elif key.lower() in ['area', 'area_size', 'area_size_sq_m', 'area size (sq m)']:
                                            base_data['Area Size (sq m)'] = value
                    except Exception as e:
                        logger.error(f'Error extracting extended data: {e}')
                    
                    # Extract coordinates from validated feature
                    try:
                        coords = feat.coordinates
                        
                        if coords:
                            for coord in coords:
                                row = base_data.copy()
                                if isinstance(coord, (list, tuple)) and len(coord) >= 2:
                                    if isinstance(coord[0], (int, float)) and isinstance(coord[1], (int, float)):
                                        row['Longitude'] = coord[0]
                                        row['Latitude'] = coord[1]
                                    else:
                                        row['Longitude'] = ''
                                        row['Latitude'] = ''
                                else:
                                    row['Longitude'] = ''
                                    row['Latitude'] = ''
                                placemark_rows.append(row)
                        else:
                            # No coordinates, just output the base data
                            row = base_data.copy()
                            row['Longitude'] = ''
                            row['Latitude'] = ''
                            placemark_rows.append(row)
                    except Exception as e:
                        logger.error(f'Error processing coordinates in CSV: {e}')
                        # Add a basic row even if geometry fails
                        row = base_data.copy()
                        row['Longitude'] = ''
                        row['Latitude'] = ''
                        placemark_rows.append(row)
            except Exception as e:
                logger.error(f'Error processing feature in CSV: {e}')

        # No longer needed - coordinates are already validated and extracted

        for feat in all_features:
            process_feature_safe(feat)
    except Exception as e:
        logger.error(f'Error in CSV extraction: {e}')
        placemark_rows = []

    fieldnames = [
        'Kitta Number', 'Owner Name', 'Land Type', 'Area Size (sq m)', 'Latitude', 'Longitude',
        'Address', 'Remarks', 'Created At', 'Updated At'
    ]

    csv_buffer = io.StringIO()
    writer = csv.DictWriter(csv_buffer, fieldnames=fieldnames)
    writer.writeheader()
    for pm in placemark_rows:
        row = {col: pm.get(col, '') for col in fieldnames}
        writer.writerow(row)
    return csv_buffer.getvalue()

# New view to download the generated CSV after KML upload
from django.http import HttpResponse

def download_kml_csv(request):
    csv_data = request.session.get('kml_csv_data')
    if not csv_data:
        messages.error(request, 'No CSV data available. Please upload a KML file first.')
        return redirect('kml_upload')
    response = HttpResponse(csv_data, content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="kml_extracted_data.csv"'
    return response


class AttachmentUploadForm(forms.Form):
    file = forms.FileField(label='Select file')
    survey_record = forms.ModelChoiceField(queryset=SurveyRecord.objects.all())

    def clean_file(self):
        f = self.cleaned_data['file']
        # Validate file size (max 5MB)
        if f.size > 5 * 1024 * 1024:
            raise forms.ValidationError('File too large (max 5MB).')
        # Validate file type
        allowed_types = ['application/pdf', 'image/jpeg', 'image/png', 'application/zip']
        if f.content_type not in allowed_types:
            raise forms.ValidationError('Unsupported file type.')
        return f

def attachment_upload_view(request):
    if request.method == 'POST':
        form = AttachmentUploadForm(request.POST, request.FILES)
        if form.is_valid():
            file = form.cleaned_data['file']
            survey_record = form.cleaned_data['survey_record']
            FileAttachment.objects.create(survey_record=survey_record, file=file)
            messages.success(request, 'Attachment uploaded!')
            return redirect('attachment_upload')
    else:
        form = AttachmentUploadForm()
    return render(request, 'surveys/upload_attachment.html', {'form': form})

def attachment_delete_view(request, pk):
    attachment = FileAttachment.objects.get(pk=pk)
    # Security: Only allow deletion by owner or admin
    if request.user.is_superuser or (attachment.survey_record.user == request.user):
        if os.path.isfile(attachment.file.path):
            os.remove(attachment.file.path)
        attachment.delete()
        messages.success(request, 'Attachment deleted!')
    else:
        messages.error(request, 'Permission denied.')
    return redirect('attachment_upload')

# Link KML boundaries to survey records (example usage in a view)
def link_kml_boundary_to_survey(request, boundary_id, survey_id):
    boundary = KMLBoundary.objects.get(pk=boundary_id)
    survey = SurveyRecord.objects.get(pk=survey_id)
    # Example: add a ForeignKey from KMLBoundary to SurveyRecord if needed
    # boundary.survey_record = survey
    # boundary.save()
    messages.success(request, f'Linked boundary {boundary.name} to survey {survey.title}')
    return redirect('dashboard')

# Example: Add fields to SurveyRecord for kitta_number, owner_name, land_type, data_source, lat, lon if not present
# For demonstration, search/filter logic is provided assuming these fields exist.

def survey_search_view(request):
    query = request.GET.get('q', '')
    kitta_number = request.GET.get('kitta_number', '')
    owner_name = request.GET.get('owner_name', '')
    lat = request.GET.get('lat', '')
    lon = request.GET.get('lon', '')
    land_type = request.GET.get('land_type', '')
    data_source = request.GET.get('data_source', '')
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')

    records = SurveyRecord.objects.all()
    if query:
        records = records.filter(Q(title__icontains=query) | Q(description__icontains=query))
    if kitta_number:
        records = records.filter(kitta_number__icontains=kitta_number)
    if owner_name:
        records = records.filter(owner_name__icontains=owner_name)
    if lat and lon:
        try:
            lat = float(lat)
            lon = float(lon)
            records = records.filter(lat=lat, lon=lon)
        except ValueError:
            pass
    if land_type:
        records = records.filter(land_type__iexact=land_type)
    if data_source:
        records = records.filter(data_source__iexact=data_source)
    if date_from:
        records = records.filter(created_at__gte=date_from)
    if date_to:
        records = records.filter(created_at__lte=date_to)

    paginator = Paginator(records, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    return render(request, 'surveys/search.html', {'page_obj': page_obj, 'query': query})

# KML boundary search and spatial search (simple example)
def kml_boundary_search_view(request):
    name = request.GET.get('name', '')
    coord = request.GET.get('coord', '')
    boundaries = KMLBoundary.objects.all()
    if name:
        boundaries = boundaries.filter(name__icontains=name)
    if coord:
        try:
            lat, lon = map(float, coord.split(','))
            # Simple spatial search: check if coord string is in coordinates field
            boundaries = boundaries.filter(coordinates__icontains=str(lat))
        except Exception:
            pass
    paginator = Paginator(boundaries, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    return render(request, 'surveys/kml_search.html', {'page_obj': page_obj, 'name': name})

def kml_export_view(request, survey_id=None):
    kml_obj = simplekml.Kml()
    point_style = simplekml.Style()
    point_style.iconstyle.icon.href = 'http://maps.google.com/mapfiles/kml/paddle/red-circle.png'
    point_style.labelstyle.scale = 1.2
    poly_style = simplekml.Style()
    poly_style.polystyle.color = simplekml.Color.changealphaint(150, simplekml.Color.red)
    poly_style.linestyle.width = 2
    kitta_number = request.GET.get('kitta_number')
    if survey_id:
        records = SurveyRecord.objects.filter(id=survey_id)
    elif kitta_number:
        records = SurveyRecord.objects.filter(kitta_number__icontains=kitta_number)
    else:
        records = SurveyRecord.objects.all()
    for record in records:
        if hasattr(record, 'lat') and hasattr(record, 'lon') and record.lat and record.lon:
            p = kml_obj.newpoint(name=record.kitta_number or record.owner_name, coords=[(float(record.lon), float(record.lat))])
            p.style = point_style
            p.description = f"Owner: {getattr(record, 'owner_name', '')}<br>Kitta: {getattr(record, 'kitta_number', '')}"
        for boundary in getattr(record, 'boundaries', []).all():
            try:
                coords = eval(boundary.polygon_data) if boundary.polygon_data else None
                if coords:
                    poly = kml_obj.newpolygon(name=boundary.kitta_number or boundary.id, outerboundaryis=[(lon, lat) for lat, lon in coords])
                    poly.style = poly_style
                    poly.description = f"Kitta: {boundary.kitta_number or ''}" \
                        + (f"<br>Area: {boundary.area_sqm} sqm" if boundary.area_sqm else '')
            except Exception:
                continue
    response = HttpResponse(kml_obj.kml(), content_type='application/vnd.google-earth.kml+xml')
    filename = 'survey.kml' if survey_id or kitta_number else 'surveys_batch.kml'
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response

# Add a view to render a button for Google Earth Pro
# In your template, use: <a href="{% url 'kml_export' survey_id=record.id %}" target="_blank">View in Google Earth Pro</a>

def boundary_completeness_report(request):
    total = KMLBoundary.objects.count()
    linked = KMLBoundary.objects.filter(survey_record__isnull=False).count()
    percent = (linked / total * 100) if total else 0
    return JsonResponse({'total': total, 'linked': linked, 'percent': round(percent, 2)})

def area_coverage_report(request):
    total_area = 0
    for boundary in KMLBoundary.objects.all():
        try:
            coords = eval(boundary.coordinates)
            total_area += calculate_polygon_area(coords)
        except Exception:
            continue
    return JsonResponse({'total_area_m2': round(total_area, 2)})

def export_excel_report(request):
    output = io.BytesIO()
    workbook = xlsxwriter.Workbook(output, {'in_memory': True})
    worksheet = workbook.add_worksheet()
    worksheet.write_row(0, 0, ['Title', 'Owner', 'Kitta', 'Lat', 'Lon'])
    for i, record in enumerate(SurveyRecord.objects.all(), 1):
        worksheet.write_row(i, 0, [getattr(record, 'title', ''), getattr(record, 'owner_name', ''), getattr(record, 'kitta_number', ''), getattr(record, 'lat', ''), getattr(record, 'lon', '')])
    workbook.close()
    output.seek(0)
    response = HttpResponse(output.read(), content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = 'attachment; filename=survey_report.xlsx'
    return response

def user_activity_api(request):
    User = get_user_model()
    # Example: Replace with real activity log
    users = User.objects.all().values('username', 'last_login', 'date_joined')
    return JsonResponse(list(users), safe=False)

def coverage_map_data(request):
    # Return GeoJSON-like data for coverage map
    features = []
    for boundary in KMLBoundary.objects.all():
        try:
            coords = eval(boundary.coordinates)
            features.append({
                'type': 'Feature',
                'geometry': {'type': 'Polygon', 'coordinates': [[ [lon, lat] for lat, lon in coords ]]},
                'properties': {'name': boundary.name}
            })
        except Exception:
            continue
    return JsonResponse({'type': 'FeatureCollection', 'features': features})

@require_GET
def kml_network_link(request):
    # Returns a KML with a network link to the batch KML export endpoint
    kml_str = f'''
    <kml xmlns="http://www.opengis.net/kml/2.2">
      <NetworkLink>
        <name>GeoSurveyPro Live Data</name>
        <Link>
          <href>{request.build_absolute_uri(reverse('kml_export_batch'))}</href>
          <refreshMode>onInterval</refreshMode>
          <refreshInterval>30</refreshInterval>
        </Link>
      </NetworkLink>
    </kml>
    '''
    return HttpResponse(kml_str, content_type='application/vnd.google-earth.kml+xml')

@require_GET
def kml_tour(request):
    # Example: Create a simple KML tour (fly to each point)
    kml_obj = simplekml.Kml()
    tour = kml_obj.newgxtour(name="GeoSurveyPro Tour")
    playlist = tour.newgxtplaylist()
    for record in SurveyRecord.objects.all():
        if hasattr(record, 'lat') and hasattr(record, 'lon') and record.lat and record.lon:
            flyto = playlist.newgxflyto(gxduration=2)
            flyto.camera = simplekml.Camera(latitude=float(record.lat), longitude=float(record.lon), altitude=1000)
    response = HttpResponse(kml_obj.kml(), content_type='application/vnd.google-earth.kml+xml')
    response['Content-Disposition'] = 'attachment; filename="geosurveypro_tour.kml"'
    return response

def generate_qr_code(url):
    qr = qrcode.QRCode(box_size=2, border=2)
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buffer = BytesIO()
    img.save(buffer, format="PNG")
    img_str = base64.b64encode(buffer.getvalue()).decode()
    return f"data:image/png;base64,{img_str}"

def pdf_report_view(request, survey_id=None):
    if survey_id:
        records = SurveyRecord.objects.filter(id=survey_id)
    else:
        records = SurveyRecord.objects.all()
    pdfs = []
    for record in records:
        boundaries = getattr(record, 'boundaries', []).all()
        kml_url = request.build_absolute_uri(reverse('kml_export', kwargs={'survey_id': record.id}))
        qr_code = generate_qr_code(kml_url)
        html_string = render_to_string('surveys/pdf_report.html', {
            'record': record,
            'boundaries': boundaries,
            'qr_code': qr_code,
            'kml_url': kml_url,
            # 'map_img': ... # Optionally add map snapshot as base64
        })
        pdf = HTML(string=html_string).write_pdf()
        pdfs.append(pdf)
    if len(pdfs) == 1:
        response = HttpResponse(pdfs[0], content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename=survey_{records[0].id}.pdf'
        return response
    else:
        # Batch: merge PDFs (simple concatenation, not true PDF merge)
        response = HttpResponse(b''.join(pdfs), content_type='application/pdf')
        response['Content-Disposition'] = 'attachment; filename=survey_batch.pdf'
        return response

# --- Core Survey API ---
class SurveyRecordViewSet(viewsets.ModelViewSet):
    queryset = SurveyRecord.objects.all()
    serializer_class = SurveyRecordSerializer
    permission_classes = [IsAuthenticatedOrReadOnly]

# --- File Upload API ---
class CSVUploadAPIView(APIView):
    parser_classes = [MultiPartParser, FormParser]
    def post(self, request):
        # Reuse csv_upload_view logic
        return csv_upload_view(request)

class KMLUploadAPIView(APIView):
    parser_classes = [MultiPartParser, FormParser]
    def post(self, request):
        return kml_upload_view(request)

@api_view(['GET'])
def export_kml_api(request):
    return kml_export_view(request)

# --- Search API ---
@api_view(['GET'])
def survey_search_api(request):
    return survey_search_view(request)

@api_view(['GET'])
def boundary_search_api(request):
    return kml_boundary_search_view(request)

@api_view(['POST'])
def spatial_query_api(request):
    return advanced_search_api(request)

# --- Google Earth Integration ---
@api_view(['GET'])
def google_earth_link_api(request, pk):
    survey = get_object_or_404(SurveyRecord, pk=pk)
    url = request.build_absolute_uri(reverse('kml_export', kwargs={'survey_id': survey.id}))
    return Response({'google_earth_url': url})

@api_view(['GET'])
def kml_export_google_earth_api(request):
    return kml_export_view(request)

# --- Dashboard API ---
@api_view(['GET'])
def dashboard_stats_api(request):
    return dashboard_analytics_api(request)

@api_view(['GET'])
def dashboard_coverage_api(request):
    return area_coverage_report(request)

def survey_list_view(request):
    records = SurveyRecord.objects.all()
    return render(request, 'surveys/survey_list.html', {'records': records})

class SurveyAddForm(forms.ModelForm):
    class Meta:
        model = SurveyRecord
        fields = ['kitta_number', 'owner_name', 'lat', 'lon', 'land_type', 'area_size', 'data_source']

def survey_add_view(request):
    if request.method == 'POST':
        form = SurveyAddForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Survey added successfully!')
            return redirect(reverse('survey_list'))
    else:
        form = SurveyAddForm()
    return render(request, 'surveys/survey_add.html', {'form': form})

def survey_edit_view(request, pk):
    survey = get_object_or_404(SurveyRecord, pk=pk)
    if request.method == 'POST':
        form = SurveyAddForm(request.POST, instance=survey)
        if form.is_valid():
            form.save()
            messages.success(request, 'Survey updated successfully!')
            return redirect(reverse('survey_list'))
    else:
        form = SurveyAddForm(instance=survey)
    return render(request, 'surveys/survey_add.html', {'form': form, 'edit': True, 'survey': survey})

def survey_delete_view(request, pk):
    survey = get_object_or_404(SurveyRecord, pk=pk)
    if request.method == 'POST':
        survey.delete()
        messages.success(request, 'Survey deleted successfully!')
        return redirect(reverse('survey_list'))
    return render(request, 'surveys/survey_delete_confirm.html', {'survey': survey})

def map_view(request):
    return render(request, 'surveys/map_view.html')

@require_GET
def kmlboundary_geojson(request):
    kitta_number = request.GET.get('kitta_number')
    boundaries = KMLBoundary.objects.all()
    if kitta_number:
        boundaries = boundaries.filter(kitta_number__icontains=kitta_number)
    features = []
    for boundary in boundaries:
        try:
            coords = eval(boundary.polygon_data) if boundary.polygon_data else None
            if coords:
                features.append({
                    'type': 'Feature',
                    'geometry': {'type': 'Polygon', 'coordinates': [[ [lon, lat] for lat, lon in coords ]]},
                    'properties': {'id': boundary.id, 'kitta_number': boundary.kitta_number}
                })
        except Exception:
            continue
    return JsonResponse({'type': 'FeatureCollection', 'features': features})

# Apply login_required to all main views
csv_upload_view = login_required(csv_upload_view)
csv_export_view = login_required(csv_export_view)
kml_upload_view = login_required(kml_upload_view)
download_kml_csv = login_required(download_kml_csv)
attachment_upload_view = login_required(attachment_upload_view)
attachment_delete_view = login_required(attachment_delete_view)
link_kml_boundary_to_survey = login_required(link_kml_boundary_to_survey)
survey_search_view = login_required(survey_search_view)
kml_boundary_search_view = login_required(kml_boundary_search_view)
kml_export_view = login_required(kml_export_view)
export_excel_report = login_required(export_excel_report)
pdf_report_view = login_required(pdf_report_view)
survey_list_view = login_required(survey_list_view)
survey_add_view = login_required(survey_add_view)
survey_edit_view = login_required(survey_edit_view)
survey_delete_view = login_required(survey_delete_view)
map_view = login_required(map_view)

class CSVToKMLForm(forms.Form):
    file = forms.FileField(label='Select CSV file')

def csv_to_kml_view(request):
    kml_data = None
    if request.method == 'POST':
        form = CSVToKMLForm(request.POST, request.FILES)
        if form.is_valid():
            csv_file = form.cleaned_data['file']
            decoded_file = csv_file.read().decode('utf-8').splitlines()
            import csv
            reader = csv.DictReader(decoded_file)
            kml = simplekml.Kml()
            rows = list(reader)
            from collections import defaultdict
            grouped = defaultdict(list)
            all_coords = []  # Collect all coordinates for camera positioning
            
            for row in rows:
                kitta = row.get('Kitta Number', '')
                grouped[kitta].append(row)
                
            for kitta, group in grouped.items():
                coords = []
                for row in group:
                    lat = row.get('Latitude')
                    lon = row.get('Longitude')
                    if lat and lon:
                        coords.append((float(lon), float(lat)))
                        all_coords.append((float(lon), float(lat)))
                        
                def build_description(row):
                    return '\n'.join(f"{key}: {value}" for key, value in row.items() if value)
                meta = group[0]
                name = meta.get('Kitta Number', '')
                description = build_description(meta)
                # MultiGeometry support: allow for future extension
                if len(coords) > 2:
                    mg = kml.newmultigeometry(name=name, description=description)
                    pol = mg.newpolygon(outerboundaryis=coords)
                    for key, value in meta.items():
                        pol.extendeddata.newdata(name=key, value=value)
                elif len(coords) == 2:
                    mg = kml.newmultigeometry(name=name, description=description)
                    line = mg.newlinestring(coords=coords)
                    for key, value in meta.items():
                        line.extendeddata.newdata(name=key, value=value)
                elif len(coords) == 1:
                    mg = kml.newmultigeometry(name=name, description=description)
                    pnt = mg.newpoint(coords=coords)
                    for key, value in meta.items():
                        pnt.extendeddata.newdata(name=key, value=value)
            
            # Add camera positioning if we have coordinates
            if all_coords:
                lons = [coord[0] for coord in all_coords]
                lats = [coord[1] for coord in all_coords]
                center_lon = sum(lons) / len(lons)
                center_lat = sum(lats) / len(lats)
                
                # Calculate appropriate altitude based on data spread
                lon_range = max(lons) - min(lons)
                lat_range = max(lats) - min(lats)
                max_range = max(lon_range, lat_range)
                
                # Set altitude based on the spread of data
                if max_range > 1:  # Large area
                    altitude = 1000000  # 1000 km
                elif max_range > 0.1:  # Medium area
                    altitude = 100000   # 100 km
                elif max_range > 0.01:  # Small area
                    altitude = 10000    # 10 km
                else:  # Very small area
                    altitude = 1000     # 1 km
                
                # Set camera to look at the center of all data
                kml.camera.longitude = center_lon
                kml.camera.latitude = center_lat
                kml.camera.altitude = altitude
                kml.camera.tilt = 0
                kml.camera.heading = 0
                kml.camera.altitudemode = simplekml.AltitudeMode.relativetoground
                
            kml_data = kml.kml()
            request.session['generated_kml'] = kml_data
    else:
        form = CSVToKMLForm()
    return render(request, 'surveys/csv_to_kml.html', {'form': form, 'kml_available': bool(kml_data or request.session.get('generated_kml'))})

def download_generated_kml(request):
    kml_data = request.session.get('generated_kml')
    if not kml_data:
        return HttpResponse('No KML generated yet.', status=404)
    response = HttpResponse(kml_data, content_type='application/vnd.google-earth.kml+xml')
    response['Content-Disposition'] = 'attachment; filename="converted_from_csv.kml"'
    return response

def dashboard_view(request):
    """Beautiful animated dashboard with statistics and map data"""
    # Get statistics
    total_surveys = SurveyRecord.objects.count()
    total_boundaries = KMLBoundary.objects.count()
    
    # Calculate total area
    total_area = 0
    for boundary in KMLBoundary.objects.all():
        try:
            coords = eval(boundary.coordinates) if boundary.coordinates else []
            if coords:
                total_area += calculate_polygon_area(coords)
        except Exception:
            continue
    
    # Get recent surveys
    recent_surveys = SurveyRecord.objects.order_by('-created_at')[:5]
    
    # Get survey data for map
    survey_points = []
    for record in SurveyRecord.objects.all():
        if record.lat and record.lon:
            survey_points.append({
                'id': record.id,
                'kitta_number': record.kitta_number or '',
                'owner_name': record.owner_name or '',
                'land_type': record.land_type or '',
                'area_size': record.area_size or 0,
                'lat': float(record.lat),
                'lon': float(record.lon),
                'created_at': record.created_at.strftime('%Y-%m-%d') if record.created_at else ''
            })
    
    # Get boundary data for map
    boundary_data = []
    for boundary in KMLBoundary.objects.all():
        try:
            coords = eval(boundary.polygon_data) if boundary.polygon_data else []
            if coords:
                boundary_data.append({
                    'id': boundary.id,
                    'kitta_number': boundary.kitta_number or '',
                    'area_sqm': boundary.area_sqm or 0,
                    'coordinates': coords
                })
        except Exception:
            continue
    
    # Calculate area coverage by land type
    land_type_stats = {}
    for record in SurveyRecord.objects.all():
        land_type = record.land_type or 'Unknown'
        area = record.area_size or 0
        if land_type in land_type_stats:
            land_type_stats[land_type]['count'] += 1
            land_type_stats[land_type]['area'] += area
        else:
            land_type_stats[land_type] = {'count': 1, 'area': area}
    
    # Calculate progress percentages for progress bars
    surveys_progress = min((total_surveys + 1) * 10, 100)
    boundaries_progress = min((total_boundaries + 1) * 10, 100)
    area_progress = min((total_area + 1000) * 0.01, 100)
    land_types_progress = min((len(land_type_stats) + 1) * 20, 100)
    
    context = {
        'total_surveys': total_surveys,
        'total_boundaries': total_boundaries,
        'total_area': round(total_area, 2),
        'recent_surveys': recent_surveys,
        'survey_points': survey_points,
        'boundary_data': boundary_data,
        'land_type_stats': land_type_stats,
        'surveys_progress': surveys_progress,
        'boundaries_progress': boundaries_progress,
        'area_progress': area_progress,
        'land_types_progress': land_types_progress,
    }
    
    return render(request, 'surveys/dashboard.html', context)

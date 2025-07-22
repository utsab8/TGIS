from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django import forms
from .models import SurveyRecord, FileAttachment
import csv
from django.http import HttpResponse
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
from django.contrib.auth import get_user_model
from django.views.decorators.csrf import csrf_exempt
from django.db.models import F
from math import radians, cos, sin, asin, sqrt
import qrcode
import base64
from io import BytesIO
from django.template.loader import render_to_string
from django.core.cache import cache
from django.views.decorators.cache import cache_page
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect
from django.core.exceptions import SuspiciousFileOperation
import logging
from django.utils.encoding import smart_str
import pandas as pd
from django import template
register = template.Library()
from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticatedOrReadOnly, AllowAny
from .serializers import SurveyRecordSerializer, FileAttachmentSerializer
import tempfile
from decimal import Decimal
import json
from datetime import datetime
import uuid

@register.filter
def get_item(dictionary, key):
    return dictionary.get(key, '')

logger = logging.getLogger(__name__)

def haversine(lat1, lon1, lat2, lon2):
    lon1, lat1, lon2, lat2 = map(radians, [lon1, lat1, lon2, lat2])
    dlon = lon2 - lon1
    dlat = lat2 - lat1
    a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
    c = 2 * asin(sqrt(a))
    r = 6371000
    return c * r

@cache_page(60 * 5)
def dashboard_analytics_api(request):
    total_points = SurveyRecord.objects.count()
    data = {
        'total_points': total_points,
        'total_boundaries': 0,
        'total_area_m2': 0,
    }
    return JsonResponse(data)

@csrf_exempt
def advanced_search_api(request):
    pass  # Removed

# Create your views here.

class CSVUploadForm(forms.Form):
    file = forms.FileField(label='Select CSV file')

def csv_upload_view(request):
    import pandas as pd
    from .models import UploadHistory

    user = request.user if request.user.is_authenticated else None
    
    def record_failure(filename, msg):
        UploadHistory.objects.create(user=user, filename=filename, status='Failed', error_message=msg)
        messages.error(request, msg)

    if request.method == 'POST':
        # This block handles all actions after the user has mapped the fields.
        if 'map_kitta_number' in request.POST:
            temp_file_path = request.session.get('temp_csv_path')
            csv_filename = request.session.get('csv_filename', 'uploaded.csv')
            action = request.POST.get('action')

            if not temp_file_path or not os.path.exists(temp_file_path):
                record_failure(csv_filename, 'Session expired or temporary file not found. Please upload again.')
                return redirect('csv_upload')
            
            field_map = {
                'kitta_number': request.POST.get('map_kitta_number'),
                'lat': request.POST.get('map_lat'),
                'lon': request.POST.get('map_lon'),
                'owner_name': request.POST.get('map_owner_name'),
                'geometry': request.POST.get('map_geometry'),
            }

            try:
                df = pd.read_csv(temp_file_path)

                # --- ACTION: Download as KML ---
                if action == 'download_kml':
                    kml = simplekml.Kml()
                    for i, row in df.iterrows():
                        try:
                            lat = float(row.get(field_map['lat']))
                            lon = float(row.get(field_map['lon']))
                            name = str(row.get(field_map['kitta_number'], ''))
                            pnt = kml.newpoint(name=name, coords=[(lon, lat)])
                            desc = []
                            for col, val in row.items():
                                desc.append(f"<b>{col}:</b> {val}")
                            pnt.description = "<br>".join(desc)
                        except (ValueError, TypeError):
                            continue # Skip rows with invalid coordinates
                    
                    response = HttpResponse(kml.kml(), content_type='application/vnd.google-earth.kml+xml')
                    response['Content-Disposition'] = f'attachment; filename="kml_export_{csv_filename}.kml"'
                    return response

                # --- ACTION: Confirm Mapping & Continue (Import to DB) ---
                elif action == 'confirm':
                    created_count, updated_count, error_count = 0, 0, 0
                    for i, row_data in enumerate(df.to_dict('records')):
                        try:
                            kitta = row_data.get(field_map['kitta_number'])
                            if not kitta or pd.isna(kitta):
                                error_count += 1
                                continue
                            
                            defaults = {'data_source': 'CSV'}
                            if field_map.get('lat') and field_map.get('lon') and not pd.isna(row_data.get(field_map['lat'])) and not pd.isna(row_data.get(field_map['lon'])):
                                defaults['lat'] = float(row_data[field_map['lat']])
                                defaults['lon'] = float(row_data[field_map['lon']])
                            if field_map.get('owner_name') and not pd.isna(row_data.get(field_map['owner_name'])):
                                defaults['owner_name'] = str(row_data[field_map['owner_name']])

                            obj, created = SurveyRecord.objects.update_or_create(kitta_number=str(kitta), defaults=defaults)
                            if created: created_count += 1
                            else: updated_count += 1
                        except Exception:
                            error_count += 1
                    
                    status = 'Failed' if error_count > 0 else 'Success'
                    message = f'Processed {len(df)} rows with {error_count} errors.' if error_count > 0 else f'Successfully processed {len(df)} rows.'
                    UploadHistory.objects.create(user=user, filename=csv_filename, status=status, error_message=message)
                    
                    messages.success(request, f'Import complete: {created_count} created, {updated_count} updated, {error_count} failed.')
                    os.remove(temp_file_path) # Clean up temp file
                    return redirect('dashboard')
            
            except Exception as e:
                record_failure(csv_filename, f"An error occurred during final processing: {e}")
                if os.path.exists(temp_file_path): os.remove(temp_file_path)
                return redirect('csv_upload')

        # --- Initial File Upload Logic (mostly unchanged) ---
        form = CSVUploadForm(request.POST, request.FILES)
        if form.is_valid():
            csv_file = form.cleaned_data['file']
            
            # --- Temporary file storage ---
            temp_dir = os.path.join(settings.MEDIA_ROOT, 'temp_csv')
            os.makedirs(temp_dir, exist_ok=True)
            temp_filename = f"{uuid.uuid4()}.csv"
            temp_file_path = os.path.join(temp_dir, temp_filename)
            
            with open(temp_file_path, 'wb+') as destination:
                for chunk in csv_file.chunks():
                    destination.write(chunk)
            
            request.session['temp_csv_path'] = temp_file_path
            request.session['csv_filename'] = csv_file.name
            
            try:
                df = pd.read_csv(temp_file_path)
                # ... (rest of the initial parsing and rendering logic is mostly the same)
                field_map = {}
                candidates = {'kitta_number': ['kitta_number', 'kitta', 'plot number'], 'lat': ['lat', 'latitude'], 'lon': ['lon', 'longitude'], 'owner_name': ['owner_name', 'owner'], 'geometry': ['wkt', 'geom', 'geometry']}
                for key, options in candidates.items():
                    for col in df.columns:
                        if col.strip().lower() in options:
                            field_map[key] = col
                            break
                
                request.session['csv_preview'] = df.head(10).to_dict('records')
                request.session['csv_columns'] = list(df.columns)
                request.session['csv_field_map'] = field_map
                
                field_labels = {'kitta_number': 'Kitta Number', 'lat': 'Latitude', 'lon': 'Longitude', 'owner_name': 'Owner Name', 'geometry': 'Geometry (WKT/GeoJSON)'}
                
                return render(request, 'surveys/csv_field_mapping.html', {'columns': list(df.columns), 'field_map': field_map, 'preview_rows': request.session['csv_preview'], 'form': form, 'field_labels': field_labels})

            except Exception as e:
                record_failure(csv_file.name, f"Failed to parse CSV: {e}")
                os.remove(temp_file_path) # Clean up failed upload
                return redirect('csv_upload')
    else:
        form = CSVUploadForm()
    
    return render(request, 'surveys/upload_csv.html', {'form': form})

# Download all survey records as KML
def download_all_surveys_kml(request):
    kml = simplekml.Kml()
    all_coords = []  # Collect all coordinates for camera positioning
    
    # Add survey records as points
    for record in SurveyRecord.objects.all():
        if record.lat and record.lon:
            pnt = kml.newpoint(name=record.kitta_number or 'Unknown')
            pnt.coords = [(record.lon, record.lat)]
            pnt.description = f"Owner: {record.owner_name or 'Unknown'}<br>Land Type: {record.land_type or 'Unknown'}<br>Area: {record.area_size or 0} sq m"
            all_coords.append((record.lon, record.lat))
    
    # Set camera position to center of all points
    if all_coords:
        avg_lon = sum(lon for lon, lat in all_coords) / len(all_coords)
        avg_lat = sum(lat for lon, lat in all_coords) / len(all_coords)
        kml.document.camera.longitude = avg_lon
        kml.document.camera.latitude = avg_lat
        kml.document.camera.altitude = 10000
    
    response = HttpResponse(kml.kml(), content_type='application/vnd.google-earth.kml+xml')
    response['Content-Disposition'] = 'attachment; filename="all_surveys.kml"'
    return response

def csv_export_view(request):
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="survey_records.csv"'
    
    writer = csv.writer(response)
    writer.writerow(['Kitta Number', 'Owner Name', 'Latitude', 'Longitude', 'Land Type', 'Area Size (sq m)', 'Data Source', 'Created At'])
    
    records = SurveyRecord.objects.all()
    for record in records:
        writer.writerow([
            record.kitta_number or '',
            record.owner_name or '',
            record.lat or '',
            record.lon or '',
            record.land_type or '',
            record.area_size or '',
            record.data_source or '',
            record.created_at or ''
        ])
    
    return response

class AttachmentUploadForm(forms.Form):
    file = forms.FileField(label='Select file')
    survey_record = forms.ModelChoiceField(queryset=SurveyRecord.objects.all())
    
    def clean_file(self):
        file = self.cleaned_data['file']
        if file.size > 10 * 1024 * 1024:  # 10MB limit
            raise forms.ValidationError('File size must be under 10MB')
        return file

def attachment_upload_view(request):
    if request.method == 'POST':
        form = AttachmentUploadForm(request.POST, request.FILES)
        if form.is_valid():
            attachment = form.save(commit=False)
            attachment.save()
            messages.success(request, 'Attachment uploaded successfully!')
            return redirect('attachment_upload')
    else:
        form = AttachmentUploadForm()
    return render(request, 'surveys/upload_attachment.html', {'form': form})

def attachment_delete_view(request, pk):
    attachment = get_object_or_404(FileAttachment, pk=pk)
    attachment.delete()
    messages.success(request, 'Attachment deleted successfully!')
    return redirect('attachment_upload')

def boundary_completeness_report(request):
    total_records = SurveyRecord.objects.count()
    records_with_boundaries = SurveyRecord.objects.filter(has_boundary=True).count()
    completeness = (records_with_boundaries / total_records * 100) if total_records > 0 else 0
    
    return JsonResponse({
        'total_records': total_records,
        'records_with_boundaries': records_with_boundaries,
        'completeness_percentage': round(completeness, 2)
    })

def area_coverage_report(request):
    total_area = SurveyRecord.objects.aggregate(total=F('area_size'))['total'] or 0
    avg_area = SurveyRecord.objects.aggregate(avg=F('area_size'))['avg'] or 0
    
    return JsonResponse({
        'total_area_sqm': float(total_area),
        'average_area_sqm': float(avg_area),
        'total_parcels': SurveyRecord.objects.count()
    })

def export_excel_report(request):
    # Excel export temporarily disabled - xlsxwriter dependency removed
    messages.warning(request, 'Excel export feature is temporarily disabled.')
    return redirect('dashboard')

def user_activity_api(request):
    return JsonResponse({'message': 'User activity tracking not implemented'})

def coverage_map_data(request):
    # Return GeoJSON-like data for coverage map
    records = SurveyRecord.objects.filter(lat__isnull=False, lon__isnull=False)[:100]
    features = []
    for record in records:
        features.append({
            'type': 'Feature',
            'geometry': {
                'type': 'Point',
                'coordinates': [float(record.lon), float(record.lat)]
            },
            'properties': {
                'kitta_number': record.kitta_number,
                'owner_name': record.owner_name,
                'area_size': float(record.area_size) if record.area_size else 0
            }
        })
    
    return JsonResponse({
        'type': 'FeatureCollection',
        'features': features
    })

def generate_qr_code(url):
    qr = qrcode.QRCode(version=1, box_size=10, border=5)
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buffer = BytesIO()
    img.save(buffer, format='PNG')
    return base64.b64encode(buffer.getvalue()).decode()

def pdf_report_view(request, survey_id=None):
    pass  # Removed

class SurveyRecordViewSet(viewsets.ModelViewSet):
    queryset = SurveyRecord.objects.all()
    serializer_class = SurveyRecordSerializer
    permission_classes = [IsAuthenticatedOrReadOnly]

class CSVUploadAPIView(APIView):
    parser_classes = [MultiPartParser, FormParser]
    
    def post(self, request):
        # Reuse csv_upload_view logic
        return Response({'message': 'CSV upload API endpoint'})

@api_view(['GET'])
def export_kml_api(request):
    return Response({'message': 'KML export API endpoint'})

@api_view(['GET'])
def survey_search_api(request):
    return Response({'message': 'Survey search API endpoint'})

@api_view(['GET'])
def boundary_search_api(request):
    return Response({'message': 'Boundary search API endpoint'})

@api_view(['POST'])
def spatial_query_api(request):
    return Response({'message': 'Spatial query API endpoint'})

@api_view(['GET'])
def google_earth_link_api(request, pk):
    record = get_object_or_404(SurveyRecord, pk=pk)
    kml_url = request.build_absolute_uri(reverse('download_all_surveys_kml'))
    return Response({
        'kml_url': kml_url,
        'record': SurveyRecordSerializer(record).data
    })

@api_view(['GET'])
def kml_export_google_earth_api(request):
    return Response({'message': 'KML export for Google Earth API endpoint'})

@api_view(['GET'])
def dashboard_stats_api(request):
    return Response({'message': 'Dashboard stats API endpoint'})

@api_view(['GET'])
def dashboard_coverage_api(request):
    return Response({'message': 'Dashboard coverage API endpoint'})

def survey_list_view(request):
    records = SurveyRecord.objects.all().order_by('-created_at')
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
            messages.success(request, 'Survey record added successfully!')
            return redirect('survey_list')
    else:
        form = SurveyAddForm()
    return render(request, 'surveys/survey_add.html', {'form': form})

def survey_edit_view(request, pk):
    record = get_object_or_404(SurveyRecord, pk=pk)
    if request.method == 'POST':
        form = SurveyAddForm(request.POST, instance=record)
        if form.is_valid():
            form.save()
            messages.success(request, 'Survey record updated successfully!')
            return redirect('survey_list')
    else:
        form = SurveyAddForm(instance=record)
    return render(request, 'surveys/survey_edit.html', {'form': form, 'record': record})

def survey_delete_view(request, pk):
    record = get_object_or_404(SurveyRecord, pk=pk)
    record.delete()
    messages.success(request, 'Survey record deleted successfully!')
    return redirect('survey_list')

def map_view(request):
    records = SurveyRecord.objects.filter(lat__isnull=False, lon__isnull=False)
    return render(request, 'surveys/map.html', {'records': records})

def download_generated_kml(request):
    kml_content = request.session.get('generated_kml')
    if not kml_content:
        messages.error(request, 'No KML file found. Please generate one first.')
        return redirect('csv_to_kml')
    
    response = HttpResponse(kml_content, content_type='application/vnd.google-earth.kml+xml')
    response['Content-Disposition'] = 'attachment; filename="generated.kml"'
    return response

def safe_json(val):
    if isinstance(val, Decimal):
        return float(val)
    if isinstance(val, datetime):
        return val.isoformat()
    if val is None:
        return None
    return val

def dashboard_view(request):
    from .models import UploadHistory
    from django.db.models import Count, Sum
    # Summary stats
    total_surveys = SurveyRecord.objects.count()
    total_boundaries = SurveyRecord.objects.filter(has_boundary=True).count()
    total_area = SurveyRecord.objects.aggregate(total=Sum('area_size'))['total'] or 0
    land_type_stats_qs = SurveyRecord.objects.values('land_type').annotate(count=Count('id')).order_by('-count')
    land_type_stats = {lt['land_type'] or 'Unknown': {'count': lt['count']} for lt in land_type_stats_qs}
    # Inject dummy data if empty
    if not land_type_stats:
        land_type_stats = {
            "Agriculture": {"count": 10},
            "Residential": {"count": 5},
            "Commercial": {"count": 3}
        }
    # Convert any Decimal in land_type_stats to float
    for k, v in land_type_stats.items():
        if isinstance(v.get('count'), Decimal):
            v['count'] = float(v['count'])
    # Progress (example: percent of records with boundaries, area, etc.)
    surveys_progress = 100
    boundaries_progress = int((total_boundaries / total_surveys) * 100) if total_surveys else 0
    area_progress = min(int(total_area / 10000), 100)  # Example scaling
    land_types_progress = min(len(land_type_stats) * 20, 100)
    # Recent surveys
    recent_surveys = SurveyRecord.objects.order_by('-created_at')[:5]
    # Upload history (only successful uploads)
    upload_history = UploadHistory.objects.filter(user=request.user, status='Success').order_by('-upload_time')[:10] if request.user.is_authenticated else []
    # Survey points for map (convert Decimal, datetime, and None)
    survey_points = [
        {k: safe_json(v) for k, v in point.items()}
        for point in SurveyRecord.objects.exclude(lat__isnull=True).exclude(lon__isnull=True).values('kitta_number', 'owner_name', 'lat', 'lon', 'land_type', 'area_size', 'created_at')
    ]
    # Boundary data for map (dummy, extend as needed)
    boundary_data = []  # Add logic if you have boundary polygons
    # Serialize for JS
    survey_points_json = json.dumps(survey_points)
    boundary_data_json = json.dumps(boundary_data)
    land_type_stats_json = json.dumps(land_type_stats)
    context = {
        'total_surveys': total_surveys,
        'total_boundaries': total_boundaries,
        'total_area': total_area,
        'land_type_stats': land_type_stats,
        'land_type_stats_json': land_type_stats_json,
        'surveys_progress': surveys_progress,
        'boundaries_progress': boundaries_progress,
        'area_progress': area_progress,
        'land_types_progress': land_types_progress,
        'recent_surveys': recent_surveys,
        'upload_history': upload_history,
        'survey_points': survey_points,
        'survey_points_json': survey_points_json,
        'boundary_data': boundary_data,
        'boundary_data_json': boundary_data_json,
    }
    return render(request, 'surveys/dashboard.html', context)

def download_error_report(request):
    error_rows = request.session.get('csv_error_rows', [])
    if not error_rows:
        messages.error(request, 'No error report available.')
        return redirect('csv_upload')
    import csv
    from io import StringIO
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename=error_report.csv'
    output = StringIO()
    writer = csv.writer(output)
    # Write header
    if error_rows and isinstance(error_rows[0], dict):
        writer.writerow(list(error_rows[0].keys()))
        for row in error_rows:
            writer.writerow([smart_str(row.get(col, '')) for col in row.keys()])
    else:
        writer.writerow(['Row', 'Error'])
        for row in error_rows:
            writer.writerow(row)
    response.write(output.getvalue())
    return response

def help_view(request):
    return render(request, 'surveys/help.html')

def advanced_csv_upload(request):
    return render(request, 'surveys/advanced_csv_upload.html')

def decimal_to_float(val):
    if isinstance(val, Decimal):
        return float(val)
    return val

def none_to_null(val):
    if val is None:
        return None
    return val

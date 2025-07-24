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
from rest_framework import viewsets, status, filters
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticatedOrReadOnly, AllowAny
from .serializers import SurveyRecordSerializer, FileAttachmentSerializer, BoundarySerializer
import tempfile
from decimal import Decimal
import json
import urllib.parse
try:
    from shapely import wkt as shapely_wkt
    from shapely.geometry import mapping as shapely_mapping
except ImportError:
    shapely_wkt = None
    shapely_mapping = None
from datetime import datetime
import uuid
from django_filters.rest_framework import DjangoFilterBackend
import requests
import folium
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from PIL import Image
import time
from staticmap import StaticMap, CircleMarker
from django.contrib.auth.decorators import login_required
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import user_passes_test
from .models import LogEntry
from django.utils import timezone
from datetime import timedelta
from django.contrib.auth import get_user_model
User = get_user_model()

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
                df = robust_read_csv(temp_file_path)

                # --- ACTION: Download as KML ---
                if action == 'download_kml':
                    kml = simplekml.Kml()
                    def parse_wkt_polygon(wkt):
                        # Expects WKT like: POLYGON((lng lat, lng lat, ...))
                        if not isinstance(wkt, str) or not wkt.upper().startswith('POLYGON'):
                            return None
                        coords_str = wkt[wkt.find("((")+2:wkt.find("))")]
                        coords = []
                        for pair in coords_str.split(','):
                            parts = pair.strip().split()
                            if len(parts) == 2:
                                lng, lat = map(float, parts)
                                coords.append((lng, lat))
                        return coords if coords else None
                    def land_type_color(land_type):
                        if not land_type:
                            return '7dff0000'  # blue
                        lt = str(land_type).strip().lower()
                        if lt == 'government':
                            return '7d0000ff'  # red
                        elif lt == 'private':
                            return '7d00ff00'  # green
                        else:
                            return '7dff0000'  # blue
                    for i, row in df.iterrows():
                        try:
                            geometry_col = field_map.get('geometry')
                            geometry_val = row.get(geometry_col) if geometry_col else None
                            land_type_val = row.get('land_type') or row.get(field_map.get('land_type', 'land_type'))
                            if geometry_val:
                                coords = parse_wkt_polygon(geometry_val)
                                if coords:
                                    pol = kml.newpolygon(name=str(row.get(field_map['kitta_number'], '')),
                                                         outerboundaryis=coords)
                                    desc = []
                                    for col, val in row.items():
                                        desc.append(f"<b>{col}:</b> {val}")
                                    pol.description = "<br>".join(desc)
                                    pol.style.polystyle.color = land_type_color(land_type_val)
                                    pol.style.linestyle.color = 'ff000000'
                                    pol.style.linestyle.width = 2
                                    continue  # Skip to next row after polygon
                            # Otherwise, fallback to point
                            lat = float(row.get(field_map['lat']))
                            lon = float(row.get(field_map['lon']))
                            name = str(row.get(field_map['kitta_number'], ''))
                            pnt = kml.newpoint(name=name, coords=[(lon, lat)])
                            desc = []
                            for col, val in row.items():
                                desc.append(f"<b>{col}:</b> {val}")
                            pnt.description = "<br>".join(desc)
                        except (ValueError, TypeError):
                            continue # Skip rows with invalid geometry or coordinates
                    response = HttpResponse(kml.kml(), content_type='application/vnd.google-earth.kml+xml')
                    response['Content-Disposition'] = f'attachment; filename="kml_export_{csv_filename}.kml"'
                    return response

                # --- ACTION: Confirm Mapping & Continue (Import to DB) ---
                elif action == 'confirm':
                    created_count, updated_count, error_count = 0, 0, 0
                    # Create UploadHistory for this import
                    upload_history = UploadHistory.objects.create(user=user, filename=csv_filename, status='Success', error_message='')
                    for i, row_data in enumerate(df.to_dict('records')):
                        try:
                            kitta = row_data.get(field_map['kitta_number'])
                            if not kitta or pd.isna(kitta):
                                error_count += 1
                                continue
                            defaults = {'data_source': 'CSV', 'upload_history': upload_history}
                            if field_map.get('lat') and field_map.get('lon') and not pd.isna(row_data.get(field_map['lat'])) and not pd.isna(row_data.get(field_map['lon'])):
                                defaults['lat'] = float(row_data[field_map['lat']])
                                defaults['lon'] = float(row_data[field_map['lon']])
                            if field_map.get('owner_name') and not pd.isna(row_data.get(field_map['owner_name'])):
                                defaults['owner_name'] = str(row_data[field_map['owner_name']])
                            obj, created = SurveyRecord.objects.update_or_create(kitta_number=str(kitta), defaults=defaults)
                            if created: created_count += 1
                            else: updated_count += 1
                            # Always link to this upload_history
                            obj.upload_history = upload_history
                            obj.save()
                        except Exception:
                            error_count += 1
                    status = 'Failed' if error_count > 0 else 'Success'
                    message = f'Processed {len(df)} rows with {error_count} errors.' if error_count > 0 else f'Successfully processed {len(df)} rows.'
                    upload_history.status = status
                    upload_history.error_message = message
                    upload_history.save()
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
            # Clear any previous preview/session data
            for key in ['temp_csv_path', 'csv_filename', 'csv_preview', 'csv_columns', 'csv_field_map']:
                if key in request.session:
                    del request.session[key]
            request.session['temp_csv_path'] = temp_file_path
            request.session['csv_filename'] = csv_file.name
            try:
                # Initial parsing and rendering logic
                df = robust_read_csv(temp_file_path)
            except Exception as e:
                record_failure(csv_file.name, f"Failed to parse CSV: {e}")
                os.remove(temp_file_path) # Clean up failed upload
                return redirect('csv_upload')

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

def get_filtered_records(request):
    records = SurveyRecord.objects.all().order_by('-created_at')
    kitta_number = request.GET.get('kitta_number', '').strip()
    owner_name = request.GET.get('owner_name', '').strip()
    area_min = request.GET.get('area_min', '').strip()
    area_max = request.GET.get('area_max', '').strip()
    search = request.GET.get('search', '').strip()
    selected_ids = request.GET.get('selected_ids', '').strip()
    if selected_ids:
        id_list = [int(pk) for pk in selected_ids.split(',') if pk.isdigit()]
        records = records.filter(pk__in=id_list)
        return records
    if kitta_number:
        records = records.filter(kitta_number__icontains=kitta_number)
    if owner_name:
        records = records.filter(owner_name__icontains=owner_name)
    if area_min:
        try:
            records = records.filter(area_size__gte=float(area_min))
        except ValueError:
            pass
    if area_max:
        try:
            records = records.filter(area_size__lte=float(area_max))
        except ValueError:
            pass
    if search:
        records = records.filter(
            Q(kitta_number__icontains=search) |
            Q(owner_name__icontains=search) |
            Q(land_type__icontains=search)
        )
    return records

def csv_export_view(request):
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="survey_records.csv"'
    writer = csv.writer(response)
    writer.writerow(['Kitta Number', 'Owner Name', 'Latitude', 'Longitude', 'Land Type', 'Area Size (sq m)', 'Data Source', 'Created At'])
    records = get_filtered_records(request)
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

def excel_export_view(request):
    import pandas as pd
    records = get_filtered_records(request)
    data = [
        {
            'Kitta Number': r.kitta_number,
            'Owner Name': r.owner_name,
            'Latitude': r.lat,
            'Longitude': r.lon,
            'Land Type': r.land_type,
            'Area Size (sq m)': r.area_size,
            'Data Source': r.data_source,
            'Created At': r.created_at,
        }
        for r in records
    ]
    df = pd.DataFrame(data)
    response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = 'attachment; filename="survey_records.xlsx"'
    with pd.ExcelWriter(response, engine='openpyxl') as writer:
        df.to_excel(writer, index=False)
    return response

def kml_export_view(request):
    import simplekml
    records = get_filtered_records(request)
    kml = simplekml.Kml()
    def land_type_color(land_type):
        if not land_type:
            return '7dff0000'  # blue
        lt = str(land_type).strip().lower()
        if lt == 'government':
            return '7d0000ff'  # red
        elif lt == 'private':
            return '7d00ff00'  # green
        else:
            return '7dff0000'  # blue
    for record in records:
        if record.lat and record.lon:
            pnt = kml.newpoint(name=record.kitta_number or 'Unknown')
            pnt.coords = [(record.lon, record.lat)]
            pnt.description = f"Owner: {record.owner_name or 'Unknown'}<br>Land Type: {record.land_type or 'Unknown'}<br>Area: {record.area_size or 0} sq m"
        # If you have polygons, add them here with color
        if hasattr(record, 'geometry') and record.geometry:
            try:
                from shapely import wkt as shapely_wkt
                shape = shapely_wkt.loads(record.geometry)
                if shape.geom_type == 'Polygon':
                    coords = list(shape.exterior.coords)
                    pol = kml.newpolygon(name=record.kitta_number or 'Unknown', outerboundaryis=coords)
                    pol.description = f"Owner: {record.owner_name or 'Unknown'}<br>Land Type: {record.land_type or 'Unknown'}<br>Area: {record.area_size or 0} sq m"
                    pol.style.polystyle.color = land_type_color(record.land_type)
                    pol.style.linestyle.color = 'ff000000'
                    pol.style.linestyle.width = 2
            except Exception:
                pass
    response = HttpResponse(kml.kml(), content_type='application/vnd.google-earth.kml+xml')
    response['Content-Disposition'] = 'attachment; filename="survey_records.kml"'
    return response

def generate_folium_map_image(records, width=600, height=400):
    # Center on the first record or a default location
    center = [float(records[0].lat), float(records[0].lon)] if records and records[0].lat and records[0].lon else [27.6712, 85.3240]
    m = folium.Map(location=center, zoom_start=16, width=width, height=height)
    for r in records:
        if r.lat and r.lon:
            popup = f'Kitta: {r.kitta_number}<br>Owner: {r.owner_name}'
            folium.Marker([float(r.lat), float(r.lon)], popup=popup).add_to(m)
    # Save to HTML
    tmp_html = tempfile.NamedTemporaryFile(delete=False, suffix='.html')
    m.save(tmp_html.name)
    tmp_html.close()  # Ensure file is closed before Selenium uses it
    # Use Selenium to screenshot the map
    chrome_options = Options()
    chrome_options.add_argument('--headless')
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.add_argument(f'--window-size={width},{height}')
    driver = webdriver.Chrome(options=chrome_options)
    driver.get('file://' + tmp_html.name)
    time.sleep(2)  # Wait for map to render
    tmp_png = tempfile.NamedTemporaryFile(delete=False, suffix='.png')
    driver.save_screenshot(tmp_png.name)
    driver.quit()
    # Wait for Chrome to fully release the file lock and process the image
    for _ in range(20):
        try:
            img = Image.open(tmp_png.name)
            buffered = tempfile.NamedTemporaryFile(delete=False, suffix='.png')
            img.save(buffered.name, format='PNG')
            img.close()
            with open(buffered.name, 'rb') as f:
                encoded = base64.b64encode(f.read()).decode('utf-8')
            os.unlink(buffered.name)
            break
        except PermissionError:
            time.sleep(0.2)
    else:
        raise PermissionError(f"Could not process image file: {tmp_png.name}")
    # Clean up temp files
    os.unlink(tmp_html.name)
    os.unlink(tmp_png.name)
    return f'data:image/png;base64,{encoded}'

def generate_static_map_image(records, width=600, height=400):
    m = StaticMap(width, height)
    for r in records:
        if r.lat and r.lon:
            marker = CircleMarker((float(r.lon), float(r.lat)), 'red', 12)
            m.add_marker(marker)
    image = m.render()
    tmp_png = tempfile.NamedTemporaryFile(delete=False, suffix='.png')
    image.save(tmp_png.name, format='PNG')
    tmp_png.close()  # Ensure file is closed before reading/deleting
    with open(tmp_png.name, 'rb') as f:
        encoded = base64.b64encode(f.read()).decode('utf-8')
    # Robustly delete the file (retry if needed)
    import time
    for _ in range(10):
        try:
            os.unlink(tmp_png.name)
            break
        except PermissionError:
            time.sleep(0.1)
    return f'data:image/png;base64,{encoded}'

def pdf_export_view(request):
    from django.template.loader import render_to_string
    from xhtml2pdf import pisa
    records = get_filtered_records(request)
    map_img_data = generate_static_map_image(records)
    # Build absolute path to logo
    logo_path = os.path.join(settings.BASE_DIR, 'static', 'logo.png')
    print('Looking for logo at:', logo_path)
    print('File exists?', os.path.exists(logo_path))
    print('Files in static dir:', os.listdir(os.path.join(settings.BASE_DIR, 'static')))
    with open(logo_path, 'rb') as f:
        logo_base64 = base64.b64encode(f.read()).decode('utf-8')
    logo_data = f'data:image/png;base64,{logo_base64}'
    total_area = sum(float(r.area_size) for r in records if r.area_size not in (None, '', 'None'))
    unique_owners = len(set(r.owner_name for r in records if r.owner_name))
    areas = [float(r.area_size) for r in records if r.area_size not in (None, '', 'None')]
    area_min = min(areas) if areas else 'N/A'
    area_max = max(areas) if areas else 'N/A'
    html = render_to_string('surveys/pdf_report.html', {
        'records': records,
        'map_img_data': map_img_data,
        'total_area': total_area,
        'logo_data': logo_data,
        'unique_owners': unique_owners,
        'area_min': area_min,
        'area_max': area_max,
    })
    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = 'attachment; filename="survey_records.pdf"'
    pisa.CreatePDF(html, dest=response)
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
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = {
        'owner_name': ['icontains', 'exact'],
        'kitta_number': ['icontains', 'exact'],
        'area_size': ['gte', 'lte', 'exact'],
    }
    search_fields = ['owner_name', 'kitta_number', 'land_type']

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

@api_view(['GET', 'POST', 'DELETE', 'PUT'])
def boundaries_geojson_api(request, pk=None):
    from .models import Boundary, SurveyRecord
    if request.method == 'POST':
        data = request.data
        survey_id = data.get('survey_record')
        geojson = data.get('geojson')
        if not survey_id or not geojson:
            return Response({'error': 'survey_record and geojson required'}, status=400)
        try:
            survey = SurveyRecord.objects.get(id=survey_id)
            boundary = Boundary.objects.create(survey_record=survey, geojson=geojson)
            return Response({'id': boundary.id}, status=201)
        except SurveyRecord.DoesNotExist:
            return Response({'error': 'SurveyRecord not found'}, status=404)
    if request.method == 'DELETE' and pk:
        try:
            boundary = Boundary.objects.get(id=pk)
            boundary.delete()
            return Response({'status': 'deleted'})
        except Boundary.DoesNotExist:
            return Response({'error': 'Boundary not found'}, status=404)
    if request.method == 'PUT' and pk:
        data = request.data
        geojson = data.get('geojson')
        if not geojson:
            return Response({'error': 'geojson required'}, status=400)
        try:
            boundary = Boundary.objects.get(id=pk)
            boundary.geojson = geojson
            boundary.save()
            return Response({'status': 'updated'})
        except Boundary.DoesNotExist:
            return Response({'error': 'Boundary not found'}, status=404)
    # GET: return all boundaries as GeoJSON
    boundaries = Boundary.objects.all()
    features = []
    for b in boundaries:
        features.append({
            'type': 'Feature',
            'geometry': b.geojson,
            'properties': {
                'id': b.id,
                'survey_record': b.survey_record_id,
                'created_at': b.created_at.isoformat(),
            }
        })
    return Response({'type': 'FeatureCollection', 'features': features})

def survey_list_view(request):
    from .models import UploadHistory
    # Only show records from the latest successful upload
    latest_upload = UploadHistory.objects.filter(status='Success').order_by('-upload_time').first()
    if latest_upload:
        records = SurveyRecord.objects.filter(upload_history=latest_upload).order_by('-created_at')
    else:
        records = SurveyRecord.objects.none()
    # Filtering
    kitta_number = request.GET.get('kitta_number', '').strip()
    owner_name = request.GET.get('owner_name', '').strip()
    area_min = request.GET.get('area_min', '').strip()
    area_max = request.GET.get('area_max', '').strip()
    search = request.GET.get('search', '').strip()
    if kitta_number:
        records = records.filter(kitta_number__icontains=kitta_number)
    if owner_name:
        records = records.filter(owner_name__icontains=owner_name)
    if area_min:
        try:
            records = records.filter(area_size__gte=float(area_min))
        except ValueError:
            pass
    if area_max:
        try:
            records = records.filter(area_size__lte=float(area_max))
        except ValueError:
            pass
    if search:
        records = records.filter(
            Q(kitta_number__icontains=search) |
            Q(owner_name__icontains=search) |
            Q(land_type__icontains=search)
        )
    context = {
        'records': records,
        'filters': {
            'kitta_number': kitta_number,
            'owner_name': owner_name,
            'area_min': area_min,
            'area_max': area_max,
            'search': search,
        }
    }
    return render(request, 'surveys/survey_list.html', context)

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
    from .models import UploadHistory, Boundary
    # Only show records from the latest successful upload
    latest_upload = UploadHistory.objects.filter(status='Success').order_by('-upload_time').first()
    if latest_upload:
        records = SurveyRecord.objects.filter(upload_history=latest_upload, lat__isnull=False, lon__isnull=False)
    else:
        records = SurveyRecord.objects.none()
    # Prepare survey points for JS
    survey_points = [
        {
            'lat': float(r.lat),
            'lon': float(r.lon),
            'title': r.kitta_number or '',
            'owner': r.owner_name or '',
            'kitta': r.kitta_number or '',
            'id': r.pk,
            'land_type': r.land_type or '',
            'area_size': r.area_size or '',
        }
        for r in records
    ]
    # Prepare boundary polygons for JS
    boundaries = Boundary.objects.all()
    boundary_features = []
    for b in boundaries:
        feature = {
            'type': 'Feature',
            'geometry': b.geojson,
            'properties': {
                'id': b.id,
                'survey_record': b.survey_record_id,
                'created_at': b.created_at.isoformat(),
            }
        }
        boundary_features.append(feature)
    import json
    return render(request, 'surveys/map_view.html', {
        'survey_points_json': json.dumps(survey_points),
        'boundary_data_json': json.dumps(boundary_features),
    })

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
    from .models import UploadHistory, SurveyRecord
    from django.db.models import Count, Sum
    # Find latest successful upload
    latest_upload = UploadHistory.objects.filter(status='Success').order_by('-upload_time').first()
    if latest_upload:
        records_qs = SurveyRecord.objects.filter(upload_history=latest_upload)
    else:
        records_qs = SurveyRecord.objects.none()
    # Summary stats
    total_surveys = records_qs.count()
    total_boundaries = records_qs.filter(has_boundary=True).count()
    total_area = records_qs.aggregate(total=Sum('area_size'))['total'] or 0
    land_type_stats_qs = records_qs.values('land_type').annotate(count=Count('id')).order_by('-count')
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
    recent_surveys = records_qs.order_by('-created_at')[:5]
    # Upload history (only successful uploads)
    upload_history = UploadHistory.objects.filter(user=request.user, status='Success').order_by('-upload_time')[:10] if request.user.is_authenticated else []
    # Survey points for map (convert Decimal, datetime, and None)
    survey_points = [
        {k: safe_json(v) for k, v in point.items()}
        for point in records_qs.exclude(lat__isnull=True).exclude(lon__isnull=True).values('kitta_number', 'owner_name', 'lat', 'lon', 'land_type', 'area_size', 'created_at')
    ]
    boundary_data = []  # Add logic if you have boundary polygons
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

def robust_read_csv(path):
    import pandas as pd
    try:
        try:
            return pd.read_csv(path, encoding='utf-8')
        except UnicodeDecodeError:
            return pd.read_csv(path, encoding='latin1')
        except Exception:
            try:
                return pd.read_csv(path, encoding='utf-8', sep='\t')
            except UnicodeDecodeError:
                return pd.read_csv(path, encoding='latin1', sep='\t')
            except Exception:
                try:
                    return pd.read_csv(path, encoding='utf-8', sep=';')
                except UnicodeDecodeError:
                    return pd.read_csv(path, encoding='latin1', sep=';')
                except Exception:
                    try:
                        return pd.read_csv(path, encoding='utf-8', on_bad_lines='skip')
                    except UnicodeDecodeError:
                        return pd.read_csv(path, encoding='latin1', on_bad_lines='skip')
    except Exception as e:
        raise e

def get_mapbox_static_url(records, width=600, height=400):
    access_token = 'YOUR_MAPBOX_ACCESS_TOKEN'  # <-- Replace with your token!
    features = []
    for r in records:
        # Add point marker
        if r.lat and r.lon:
            features.append({
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [float(r.lon), float(r.lat)]},
                "properties": {}
            })
        # Add polygon if available (auto-detect WKT or GeoJSON)
        geometry = getattr(r, 'geometry', None)
        if geometry:
            try:
                # Try GeoJSON first
                geom = json.loads(geometry)
                features.append({
                    "type": "Feature",
                    "geometry": geom,
                    "properties": {}
                })
            except Exception:
                # Try WKT if shapely is available
                if shapely_wkt and shapely_mapping:
                    try:
                        shape = shapely_wkt.loads(geometry)
                        geojson_geom = shapely_mapping(shape)
                        features.append({
                            "type": "Feature",
                            "geometry": geojson_geom,
                            "properties": {}
                        })
                    except Exception:
                        pass
    geojson = {"type": "FeatureCollection", "features": features}
    geojson_str = urllib.parse.quote(json.dumps(geojson))
    overlay = f'geojson({geojson_str})'
    center = f"{records[0].lon},{records[0].lat}" if records and records[0].lat and records[0].lon else "85.3240,27.6712"
    url = (
        f"https://api.mapbox.com/styles/v1/mapbox/streets-v11/static/"
        f"{overlay}/{center},12/{width}x{height}@2x"
        f"?access_token={access_token}"
    )
    return url

def get_mapbox_static_image_base64(records, width=600, height=400):
    url = get_mapbox_static_url(records, width, height)
    response = requests.get(url)
    if response.status_code == 200:
        encoded = base64.b64encode(response.content).decode('utf-8')
        return f"data:image/png;base64,{encoded}"
    return None

@login_required
def upload_history_view(request):
    from .models import UploadHistory
    uploads = UploadHistory.objects.filter(user=request.user).order_by('-upload_time')
    return render(request, 'surveys/upload_history.html', {'uploads': uploads})

# Custom login view
from django.views.decorators.csrf import csrf_protect
@csrf_protect
def custom_login_view(request):
    error = None
    if request.method == 'POST':
        email = request.POST.get('email')
        password = request.POST.get('password')
        ADMIN_EMAIL = 'acharyautsab390@gmail.com'
        user = authenticate(request, username=email, password=password)
        if user is not None:
            login(request, user)
            if email == ADMIN_EMAIL:
                request.session['is_admin'] = True
                request.session['user_email'] = email
                LogEntry.objects.create(user=user, action='Admin Login', details=f'Admin {email} logged in', level='INFO')
                return redirect('admin_dashboard')
            else:
                request.session['is_admin'] = False
                request.session['user_email'] = email
                return redirect('user_dashboard')
        else:
            error = 'Invalid credentials.'
    return render(request, 'accounts/login.html', {'error': error})

# Logout view
def custom_logout_view(request):
    logout(request)
    request.session.flush()
    return redirect('login')

# Admin dashboard view
@login_required
def admin_dashboard_view(request):
    if not request.session.get('is_admin'):
        return redirect('user_dashboard')
    from .models import UploadHistory, SurveyRecord, LogEntry
    from django.db.models import Count, Sum, Q
    from django.contrib.auth import get_user_model
    User = get_user_model()
    # Log filters
    user_id = request.GET.get('log_user', '')
    level = request.GET.get('log_level', '')
    start_date = request.GET.get('log_start', '')
    end_date = request.GET.get('log_end', '')
    keyword = request.GET.get('log_keyword', '')
    log_page = int(request.GET.get('log_page', 1))
    logs_qs = LogEntry.objects.select_related('user').all()
    if user_id:
        logs_qs = logs_qs.filter(user_id=user_id)
    if level:
        logs_qs = logs_qs.filter(level=level)
    if start_date:
        logs_qs = logs_qs.filter(timestamp__gte=start_date)
    if end_date:
        logs_qs = logs_qs.filter(timestamp__lte=end_date)
    if keyword:
        logs_qs = logs_qs.filter(Q(action__icontains=keyword) | Q(details__icontains=keyword))
    logs_qs = logs_qs.order_by('-timestamp')
    paginator = Paginator(logs_qs, 20)
    logs = paginator.get_page(log_page)
    users = User.objects.all()
    latest_upload = UploadHistory.objects.filter(status='Success').order_by('-upload_time').first()
    if latest_upload:
        records_qs = SurveyRecord.objects.filter(upload_history=latest_upload)
    else:
        records_qs = SurveyRecord.objects.none()
    total_surveys = records_qs.count()
    total_boundaries = records_qs.filter(has_boundary=True).count()
    total_area = records_qs.aggregate(total=Sum('area_size'))['total'] or 0
    land_type_stats_qs = records_qs.values('land_type').annotate(count=Count('id')).order_by('-count')
    land_type_stats = {lt['land_type'] or 'Unknown': {'count': lt['count']} for lt in land_type_stats_qs}
    if not land_type_stats:
        land_type_stats = {
            "Agriculture": {"count": 10},
            "Residential": {"count": 5},
            "Commercial": {"count": 3}
        }
    for k, v in land_type_stats.items():
        if isinstance(v.get('count'), Decimal):
            v['count'] = float(v['count'])
    surveys_progress = 100
    boundaries_progress = int((total_boundaries / total_surveys) * 100) if total_surveys else 0
    area_progress = min(int(total_area / 10000), 100)
    land_types_progress = min(len(land_type_stats) * 20, 100)
    recent_surveys = records_qs.order_by('-created_at')[:5]
    upload_history = UploadHistory.objects.filter(user=request.user, status='Success').order_by('-upload_time')[:10] if request.user.is_authenticated else []
    survey_points = [
        {k: safe_json(v) for k, v in point.items()}
        for point in records_qs.exclude(lat__isnull=True).exclude(lon__isnull=True).values('kitta_number', 'owner_name', 'lat', 'lon', 'land_type', 'area_size', 'created_at')
    ]
    boundary_data = []
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
        'is_admin': True,
        'logs': logs,
        'log_users': users,
        'log_user_selected': user_id,
        'log_level_selected': level,
        'log_start_selected': start_date,
        'log_end_selected': end_date,
        'log_keyword': keyword,
        'log_paginator': paginator,
    }
    return render(request, 'surveys/dashboard.html', context)

# User dashboard view
@login_required
def user_dashboard_view(request):
    if request.session.get('is_admin'):
        return redirect('admin_dashboard')
    # Use dashboard_view logic
    from .models import UploadHistory, SurveyRecord
    from django.db.models import Count, Sum
    latest_upload = UploadHistory.objects.filter(status='Success').order_by('-upload_time').first()
    if latest_upload:
        records_qs = SurveyRecord.objects.filter(upload_history=latest_upload)
    else:
        records_qs = SurveyRecord.objects.none()
    total_surveys = records_qs.count()
    total_boundaries = records_qs.filter(has_boundary=True).count()
    total_area = records_qs.aggregate(total=Sum('area_size'))['total'] or 0
    land_type_stats_qs = records_qs.values('land_type').annotate(count=Count('id')).order_by('-count')
    land_type_stats = {lt['land_type'] or 'Unknown': {'count': lt['count']} for lt in land_type_stats_qs}
    if not land_type_stats:
        land_type_stats = {
            "Agriculture": {"count": 10},
            "Residential": {"count": 5},
            "Commercial": {"count": 3}
        }
    for k, v in land_type_stats.items():
        if isinstance(v.get('count'), Decimal):
            v['count'] = float(v['count'])
    surveys_progress = 100
    boundaries_progress = int((total_boundaries / total_surveys) * 100) if total_surveys else 0
    area_progress = min(int(total_area / 10000), 100)
    land_types_progress = min(len(land_type_stats) * 20, 100)
    recent_surveys = records_qs.order_by('-created_at')[:5]
    upload_history = UploadHistory.objects.filter(user=request.user, status='Success').order_by('-upload_time')[:10] if request.user.is_authenticated else []
    survey_points = [
        {k: safe_json(v) for k, v in point.items()}
        for point in records_qs.exclude(lat__isnull=True).exclude(lon__isnull=True).values('kitta_number', 'owner_name', 'lat', 'lon', 'land_type', 'area_size', 'created_at')
    ]
    boundary_data = []
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
        'is_admin': False,
    }
    return render(request, 'surveys/dashboard.html', context)

# User management views (admin only)
@user_passes_test(lambda u: u.is_staff or u.username == 'utsab')
def user_list_view(request):
    users = User.objects.all().order_by('-is_staff', 'username')
    return render(request, 'user_management/user_list.html', {'users': users})

@user_passes_test(lambda u: u.is_staff or u.username == 'utsab')
def user_add_view(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        email = request.POST.get('email')
        password = request.POST.get('password')
        is_staff = bool(request.POST.get('is_staff'))
        if username and password:
            user = User.objects.create_user(username=username, email=email, password=password)
            user.is_staff = is_staff
            user.save()
            LogEntry.objects.create(user=request.user, action='Add User', details=f'Added user {username}', level='ACTION')
            messages.success(request, 'User added successfully!')
            return redirect('user_list')
        else:
            messages.error(request, 'Username and password are required.')
    return render(request, 'user_management/user_add.html')

@user_passes_test(lambda u: u.is_staff or u.username == 'utsab')
def user_edit_view(request, user_id):
    user = get_object_or_404(User, pk=user_id)
    if request.method == 'POST':
        user.email = request.POST.get('email')
        user.is_staff = bool(request.POST.get('is_staff'))
        password = request.POST.get('password')
        if password:
            user.set_password(password)
        user.save()
        LogEntry.objects.create(user=request.user, action='Edit User', details=f'Edited user {user.username}', level='ACTION')
        messages.success(request, 'User updated successfully!')
        return redirect('user_list')
    return render(request, 'user_management/user_edit.html', {'user': user})

@user_passes_test(lambda u: u.is_staff or u.username == 'utsab')
def user_delete_view(request, user_id):
    user = get_object_or_404(User, pk=user_id)
    if request.method == 'POST':
        user.delete()
        LogEntry.objects.create(user=request.user, action='Delete User', details=f'Deleted user {user.username}', level='ACTION')
        messages.success(request, 'User deleted successfully!')
        return redirect('user_list')
    return render(request, 'user_management/user_delete_confirm.html', {'user': user})

@login_required
def export_users_csv(request):
    if not request.session.get('is_admin'):
        return HttpResponse('Unauthorized', status=403)
    # Log export
    LogEntry.objects.create(user=request.user, action='Export Users', details='Exported all users as CSV', level='ACTION')
    import csv
    from django.contrib.auth import get_user_model
    User = get_user_model()
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="users.csv"'
    writer = csv.writer(response)
    writer.writerow(['Username', 'Email', 'Is Staff', 'Date Joined'])
    for user in User.objects.all():
        writer.writerow([user.username, user.email, user.is_staff, user.date_joined])
    return response

@login_required
def export_logs_csv(request):
    if not request.session.get('is_admin'):
        return HttpResponse('Unauthorized', status=403)
    from .models import LogEntry
    from django.contrib.auth import get_user_model
    import csv
    from django.db.models import Q
    User = get_user_model()
    # Use same filters as dashboard
    user_id = request.GET.get('log_user', '')
    level = request.GET.get('log_level', '')
    start_date = request.GET.get('log_start', '')
    end_date = request.GET.get('log_end', '')
    keyword = request.GET.get('log_keyword', '')
    logs_qs = LogEntry.objects.select_related('user').all()
    if user_id:
        logs_qs = logs_qs.filter(user_id=user_id)
    if level:
        logs_qs = logs_qs.filter(level=level)
    if start_date:
        logs_qs = logs_qs.filter(timestamp__gte=start_date)
    if end_date:
        logs_qs = logs_qs.filter(timestamp__lte=end_date)
    if keyword:
        logs_qs = logs_qs.filter(Q(action__icontains=keyword) | Q(details__icontains=keyword))
    logs = logs_qs.order_by('-timestamp')
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="logs.csv"'
    writer = csv.writer(response)
    writer.writerow(['Timestamp', 'Level', 'User', 'Action', 'Details'])
    for log in logs:
        writer.writerow([
            log.timestamp.strftime('%Y-%m-%d %H:%M'),
            log.level,
            log.user.username if log.user else '-',
            log.action,
            log.details
        ])
    return response

@login_required
def delete_old_logs(request):
    if not request.session.get('is_admin') or request.method != 'POST':
        return HttpResponse('Unauthorized', status=403)
    from .models import LogEntry
    cutoff = timezone.now() - timedelta(days=90)
    count = LogEntry.objects.filter(timestamp__lt=cutoff).count()
    LogEntry.objects.filter(timestamp__lt=cutoff).delete()
    LogEntry.objects.create(user=request.user, action='Delete Old Logs', details=f'Deleted {count} logs older than 90 days', level='ACTION')
    return redirect('admin_dashboard')

@login_required
def admin_logs_api(request):
    if not request.session.get('is_admin'):
        return JsonResponse({'error': 'Unauthorized'}, status=403)
    from .models import LogEntry
    from django.contrib.auth import get_user_model
    from django.db.models import Q
    User = get_user_model()
    user_id = request.GET.get('log_user', '')
    level = request.GET.get('log_level', '')
    start_date = request.GET.get('log_start', '')
    end_date = request.GET.get('log_end', '')
    keyword = request.GET.get('log_keyword', '')
    log_page = int(request.GET.get('log_page', 1))
    from django.core.paginator import Paginator
    logs_qs = LogEntry.objects.select_related('user').all()
    if user_id:
        logs_qs = logs_qs.filter(user_id=user_id)
    if level:
        logs_qs = logs_qs.filter(level=level)
    if start_date:
        logs_qs = logs_qs.filter(timestamp__gte=start_date)
    if end_date:
        logs_qs = logs_qs.filter(timestamp__lte=end_date)
    if keyword:
        logs_qs = logs_qs.filter(Q(action__icontains=keyword) | Q(details__icontains=keyword))
    logs_qs = logs_qs.order_by('-timestamp')
    paginator = Paginator(logs_qs, 20)
    logs = paginator.get_page(log_page)
    data = {
        'logs': [
            {
                'id': log.id,
                'timestamp': log.timestamp.strftime('%Y-%m-%d %H:%M'),
                'level': log.level,
                'user': log.user.username if log.user else '-',
                'action': log.action,
                'details': log.details,
            } for log in logs
        ],
        'page': logs.number,
        'num_pages': logs.paginator.num_pages,
        'has_next': logs.has_next(),
        'has_previous': logs.has_previous(),
    }
    return JsonResponse(data)

@login_required
def activity_view(request):
    return render(request, 'activity.html')

@login_required
def settings_view(request):
    return render(request, 'settings.html')

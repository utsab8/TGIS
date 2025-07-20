from django.shortcuts import render, redirect
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

from rest_framework import viewsets, status
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.permissions import IsAuthenticatedOrReadOnly, AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.parsers import MultiPartParser, FormParser
from .serializers import SurveyRecordSerializer, FileAttachmentSerializer
from django.shortcuts import get_object_or_404
from django.contrib.auth.decorators import login_required

logger = logging.getLogger(__name__)

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
    data = {
        'total_points': total_points,
        'total_boundaries': 0,
        'total_area_m2': 0,
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

def survey_search_view(request):
    query = request.GET.get('q', '')
    results = []
    if query:
        results = SurveyRecord.objects.filter(
            Q(kitta_number__icontains=query) |
            Q(owner_name__icontains=query) |
            Q(land_type__icontains=query)
        )[:50]
    
    context = {
        'query': query,
        'results': results,
        'total_results': len(results)
    }
    return render(request, 'surveys/search.html', context)

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
    # PDF report temporarily disabled - weasyprint dependency removed
    messages.warning(request, 'PDF report feature is temporarily disabled.')
    return redirect('dashboard')

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

class CSVToKMLForm(forms.Form):
    file = forms.FileField(label='Select CSV file')

def csv_to_kml_view(request):
    if request.method == 'POST':
        form = CSVToKMLForm(request.POST, request.FILES)
        if form.is_valid():
            csv_file = form.cleaned_data['file']
            if not csv_file.name.endswith('.csv'):
                messages.error(request, 'File is not CSV type')
                return redirect('csv_to_kml')
            
            try:
                decoded_file = csv_file.read().decode('utf-8').splitlines()
                reader = csv.DictReader(decoded_file)
                
                kml = simplekml.Kml()
                
                for row in reader:
                    try:
                        lat = float(row.get('Latitude', 0))
                        lon = float(row.get('Longitude', 0))
                        if lat != 0 and lon != 0:
                            pnt = kml.newpoint(name=row.get('Kitta Number', 'Unknown'))
                            pnt.coords = [(lon, lat)]
                            
                            def build_description(row):
                                desc = []
                                if row.get('Owner Name'):
                                    desc.append(f"Owner: {row['Owner Name']}")
                                if row.get('Land Type'):
                                    desc.append(f"Land Type: {row['Land Type']}")
                                if row.get('Area Size (sq m)'):
                                    desc.append(f"Area: {row['Area Size (sq m)']} sq m")
                                if row.get('Address'):
                                    desc.append(f"Address: {row['Address']}")
                                if row.get('Remarks'):
                                    desc.append(f"Remarks: {row['Remarks']}")
                                return '<br>'.join(desc)
                            
                            pnt.description = build_description(row)
                    except (ValueError, KeyError):
                        continue
                
                # Save KML to session for download
                request.session['generated_kml'] = kml.kml()
                messages.success(request, 'KML file generated successfully!')
                return redirect('download_generated_kml')
                
            except Exception as e:
                messages.error(request, f'Error processing CSV file: {e}')
    else:
        form = CSVToKMLForm()
    
    return render(request, 'surveys/csv_to_kml.html', {'form': form})

def download_generated_kml(request):
    kml_content = request.session.get('generated_kml')
    if not kml_content:
        messages.error(request, 'No KML file found. Please generate one first.')
        return redirect('csv_to_kml')
    
    response = HttpResponse(kml_content, content_type='application/vnd.google-earth.kml+xml')
    response['Content-Disposition'] = 'attachment; filename="generated.kml"'
    return response

def dashboard_view(request):
    total_records = SurveyRecord.objects.count()
    recent_records = SurveyRecord.objects.order_by('-created_at')[:10]
    
    context = {
        'total_records': total_records,
        'recent_records': recent_records,
    }
    return render(request, 'surveys/dashboard.html', context)

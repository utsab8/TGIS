from django.shortcuts import render, redirect
from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from .forms import KMLUploadForm
from .utils.kml_parser import kml_parser
import json
import csv
from django.http import StreamingHttpResponse
from django.db import transaction
from surveys.models import SurveyRecord
from django.utils import timezone


def pad_coords_to_3d(coords):
    """Pad all coordinates to 3D (lon, lat, alt=0 if missing) recursively for polygons/lines/points."""
    if isinstance(coords, list):
        if coords and isinstance(coords[0], list):
            # List of coordinates (Polygon, LineString)
            return [pad_coords_to_3d(c) for c in coords]
        elif len(coords) == 2:
            return [coords[0], coords[1], 0]
        elif len(coords) == 3:
            return coords
    return coords


@login_required
def upload_view(request):
    """
    Main upload view for KML files with validation and session storage
    """
    if request.method == 'POST':
        form = KMLUploadForm(request.POST, request.FILES)
        if form.is_valid():
            try:
                # Save file to session
                if form.save_to_session(request):
                    messages.success(request, f'File "{form.cleaned_data["kml_file"].name}" uploaded successfully!')
                    return redirect('land_parser:preview')
                else:
                    messages.error(request, 'Failed to process the uploaded file.')
            except Exception as e:
                messages.error(request, f'Error processing file: {str(e)}')
        else:
            # Display form errors
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f'{field}: {error}')
    else:
        form = KMLUploadForm()
    
    context = {
        'form': form,
        'title': 'Upload KML File',
        'active_page': 'upload'
    }
    return render(request, 'land_parser/upload.html', context)


@login_required
def preview_view(request):
    """
    Preview parsed land parcel data from session with pagination
    """
    # Check if KML data exists in session
    kml_data = request.session.get('uploaded_kml')
    if not kml_data:
        messages.warning(request, 'No KML file found. Please upload a file first.')
        return redirect('land_parser:upload')
    
    try:
        # Parse KML data using our parser
        parsed_result = kml_parser.parse_kml(kml_data)
        
        # Get pagination parameters
        page = request.GET.get('page', 1)
        per_page = 20  # Show 20 parcels per page
        
        # Calculate pagination
        parcels = parsed_result.get('parcels', [])
        total_parcels = len(parcels)
        total_pages = (total_parcels + per_page - 1) // per_page
        
        # Slice parcels for current page
        start_idx = (int(page) - 1) * per_page
        end_idx = start_idx + per_page
        current_parcels = parcels[start_idx:end_idx]
        
        # --- GeoJSON conversion for current page ---
        def parcel_to_feature(parcel, idx):
            geometry_type = parcel.get('geometry_type', 'Polygon')
            coords = parcel.get('coordinates', [])
            # --- Robust GeoJSON geometry handling ---
            if geometry_type == 'Polygon':
                # Ensure coordinates are [[...]] (list of rings)
                if coords and isinstance(coords[0][0], (float, int)):
                    geometry = {
                        'type': 'Polygon',
                        'coordinates': [coords]
                    }
                else:
                    geometry = {
                        'type': 'Polygon',
                        'coordinates': coords if coords else []
                    }
            elif geometry_type == 'LineString':
                geometry = {
                    'type': 'LineString',
                    'coordinates': coords
                }
            elif geometry_type == 'Point':
                geometry = {
                    'type': 'Point',
                    'coordinates': coords[0] if coords else [0, 0, 0]
                }
            else:
                geometry = {
                    'type': geometry_type,
                    'coordinates': coords
                }
            return {
                'type': 'Feature',
                'geometry': geometry,
                'properties': {
                    'kitta_number': parcel.get('kitta_number', ''),
                    'owner_name': parcel.get('owner_name', ''),
                    'area': parcel.get('area', 0),
                    'area_hectares': parcel.get('area_hectares', 0),
                    'center_point': parcel.get('center_point', []),
                    'geometry_type': geometry_type,
                    'featureId': idx
                }
            }
        geojson = {
            'type': 'FeatureCollection',
            'features': [parcel_to_feature(p, i) for i, p in enumerate(current_parcels)]
        }
        geojson_data = json.dumps(geojson)
        # --- End GeoJSON conversion ---
        
        # Calculate summary statistics
        total_area = parsed_result.get('total_area', 0)
        total_area_hectares = total_area / 10000 if total_area else 0
        
        # Calculate area statistics
        areas = [p.get('area', 0) for p in parcels if p.get('area', 0) > 0]
        avg_area = sum(areas) / len(areas) if areas else 0
        min_area = min(areas) if areas else 0
        max_area = max(areas) if areas else 0
        
        preview_data = {
            'filename': request.session.get('kml_filename', 'Unknown'),
            'file_size': request.session.get('kml_size', 0),
            'parcels': current_parcels,
            'total_count': total_parcels,
            'total_area': total_area,
            'total_area_hectares': total_area_hectares,
            'avg_area': avg_area,
            'min_area': min_area,
            'max_area': max_area,
            'kml_content': kml_data[:500] + '...' if len(kml_data) > 500 else kml_data,
            'statistics': parsed_result.get('statistics', {}),
            'errors': parsed_result.get('errors', []),
            'warnings': parsed_result.get('warnings', []),
            'pagination': {
                'current_page': int(page),
                'total_pages': total_pages,
                'per_page': per_page,
                'start_idx': start_idx + 1,
                'end_idx': min(end_idx, total_parcels),
                'has_previous': int(page) > 1,
                'has_next': int(page) < total_pages,
                'previous_page': int(page) - 1,
                'next_page': int(page) + 1
            }
        }
        
        context = {
            'preview_data': preview_data,
            'geojson_data': geojson_data,
            'title': 'Preview KML Data',
            'active_page': 'preview'
        }
        return render(request, 'land_parser/preview.html', context)
        
    except Exception as e:
        messages.error(request, f'Error previewing data: {str(e)}')
        return redirect('land_parser:upload')


@login_required
def download_csv_view(request):
    """
    Download parsed data as CSV (robust, streaming, proper formatting)
    """
    if request.method == 'POST':
        kml_data = request.session.get('uploaded_kml')
        if not kml_data:
            return JsonResponse({'error': 'No KML data found'}, status=400)
        try:
            parsed_result = kml_parser.parse_kml(kml_data)
            parcels = parsed_result.get('parcels', [])
            # CSV header
            header = [
                'Kitta Number', 'Owner Name', 'Area (sq m)', 'Area (hectares)', 'Geometry Type', 'Coordinates'
            ]
            # Generator for streaming rows
            def row_iter():
                yield header
                for parcel in parcels:
                    coords = parcel.get('coordinates', [])
                    coords_str = ";".join([
                        f"{c[0]},{c[1]}" if isinstance(c, (list, tuple)) and len(c) >= 2 else str(c) for c in coords
                    ])
                    yield [
                        parcel.get('kitta_number', ''),
                        parcel.get('owner_name', ''),
                        f"{parcel.get('area', 0):.2f}",
                        f"{parcel.get('area_hectares', 0):.4f}",
                        parcel.get('geometry_type', ''),
                        coords_str
                    ]
            class Echo:
                def write(self, value):
                    return value
            pseudo_buffer = Echo()
            writer = csv.writer(pseudo_buffer)
            response = StreamingHttpResponse(
                (writer.writerow(row) for row in row_iter()),
                content_type='text/csv'
            )
            response['Content-Disposition'] = 'attachment; filename="land_parcels.csv"'
            return response
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)
    return JsonResponse({'error': 'POST method required'}, status=405)


@login_required
def save_to_db_view(request):
    """
    Save parsed data to database with bulk operations and duplicate handling
    """
    if request.method == 'POST':
        kml_data = request.session.get('uploaded_kml')
        if not kml_data:
            return JsonResponse({'error': 'No KML data found'}, status=400)
        
        try:
            # Parse KML data
            parsed_result = kml_parser.parse_kml(kml_data)
            parcels = parsed_result.get('parcels', [])
            
            if not parcels:
                return JsonResponse({
                    'status': 'error', 
                    'message': 'No valid land parcels found in KML file'
                }, status=400)
            
            # Prepare bulk operations
            new_records = []
            updated_records = []
            skipped_records = []
            
            with transaction.atomic():
                for parcel in parcels:
                    kitta_number = parcel.get('kitta_number', '').strip()
                    owner_name = parcel.get('owner_name', '').strip()
                    area = parcel.get('area', 0)
                    coordinates = parcel.get('coordinates', [])
                    
                    # Skip if no kitta number
                    if not kitta_number:
                        skipped_records.append(f"Parcel {len(new_records + updated_records) + 1}: No kitta number")
                        continue
                    
                    # Check for existing record
                    try:
                        existing_record = SurveyRecord.objects.get(kitta_number=kitta_number)
                        
                        # Update existing record
                        existing_record.owner_name = owner_name
                        existing_record.area_size = area
                        existing_record.data_source = 'KML'
                        existing_record.updated_at = timezone.now()
                        
                        # Update coordinates if available
                        if coordinates and len(coordinates) > 0:
                            # Use center point or first coordinate
                            center_coord = coordinates[0] if isinstance(coordinates[0], (list, tuple)) else coordinates
                            if len(center_coord) >= 2:
                                existing_record.lat = center_coord[1]  # Latitude
                                existing_record.lon = center_coord[0]  # Longitude
                        
                        updated_records.append(existing_record)
                        
                    except SurveyRecord.DoesNotExist:
                        # Create new record
                        center_coord = coordinates[0] if coordinates and len(coordinates) > 0 else [0, 0]
                        if isinstance(center_coord, (list, tuple)) and len(center_coord) >= 2:
                            lat, lon = center_coord[1], center_coord[0]
                        else:
                            lat, lon = 0, 0
                        
                        new_record = SurveyRecord(
                            kitta_number=kitta_number,
                            owner_name=owner_name,
                            lat=lat,
                            lon=lon,
                            area_size=area,
                            data_source='KML',
                            uploaded_by=request.user
                        )
                        new_records.append(new_record)
                
                # Bulk create new records
                if new_records:
                    SurveyRecord.objects.bulk_create(new_records, batch_size=100)
                
                # Bulk update existing records
                if updated_records:
                    SurveyRecord.objects.bulk_update(
                        updated_records, 
                        ['owner_name', 'area_size', 'data_source', 'updated_at', 'lat', 'lon'],
                        batch_size=100
                    )
            
            # Prepare response
            total_processed = len(new_records) + len(updated_records)
            total_area = sum(r.area_size or 0 for r in new_records + updated_records)
            
            response_data = {
                'status': 'success',
                'message': f'Successfully processed {total_processed} land parcels',
                'details': {
                    'new_records': len(new_records),
                    'updated_records': len(updated_records),
                    'skipped_records': len(skipped_records),
                    'total_area': float(total_area),
                    'total_area_hectares': float(total_area / 10000) if total_area else 0
                }
            }
            
            if skipped_records:
                response_data['warnings'] = skipped_records[:5]  # Show first 5 warnings
            
            return JsonResponse(response_data)
            
        except Exception as e:
            return JsonResponse({
                'status': 'error', 
                'message': f'Database save failed: {str(e)}'
            }, status=500)
    
    return JsonResponse({'error': 'POST method required'}, status=405)


@login_required
def clear_session_view(request):
    """
    Clear session data (uploaded KML file)
    """
    if request.method == 'POST':
        try:
            # Clear session data
            session_keys = ['uploaded_kml', 'kml_filename', 'kml_size']
            for key in session_keys:
                if key in request.session:
                    del request.session[key]
            return JsonResponse({'success': True, 'message': 'Session cleared successfully'})
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})
    return JsonResponse({'success': False, 'error': 'Invalid request method'})


@login_required
def help_view(request):
    """
    Display help and documentation for the Land Parser
    """
    return render(request, 'land_parser/help.html', {
        'active_page': 'help'
    })

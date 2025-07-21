from .models import SurveyRecord, UploadHistory
from django.views.decorators.csrf import csrf_exempt
import csv, io, json
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.shortcuts import render

@csrf_exempt
@login_required
def advanced_csv_upload(request):
    if request.method == 'POST':
        if request.content_type == 'application/json':
            data = json.loads(request.body)
            if data.get('action') == 'save':
                mapping = data['mapping']
                rows = data['rows']
                errors = []
                created_count = 0
                updated_count = 0
                for row in rows[1:]:
                    obj_data = {}
                    for idx, field in mapping.items():
                        obj_data[field] = row[int(idx)]
                    # Validation
                    if not obj_data.get('kitta_number') or not obj_data.get('lat') or not obj_data.get('lon'):
                        errors.append(f"Missing required fields in row: {row}")
                        continue
                    try:
                        lat = float(obj_data['lat'])
                        lon = float(obj_data['lon'])
                    except ValueError:
                        errors.append(f"Invalid lat/lon in row: {row}")
                        continue
                    try:
                        obj, created = SurveyRecord.objects.update_or_create(
                            kitta_number=obj_data['kitta_number'],
                            defaults={
                                'owner_name': obj_data.get('owner_name', ''),
                                'land_type': obj_data.get('land_type', ''),
                                'area_size': obj_data.get('area_size') or None,
                                'lat': lat,
                                'lon': lon,
                                'data_source': 'CSV',
                                'uploaded_by': request.user,
                            }
                        )
                        if created:
                            created_count += 1
                        else:
                            updated_count += 1
                    except Exception as e:
                        errors.append(str(e))
                UploadHistory.objects.create(
                    user=request.user,
                    filename='uploaded.csv',
                    status='Success' if not errors else 'Failed',
                    error_message='\n'.join(errors)
                )
                if errors:
                    return JsonResponse({'success': False, 'error': '\n'.join(errors)})
                return JsonResponse({'success': True, 'created': created_count, 'updated': updated_count})
        elif request.FILES.get('csv_file'):
            csv_file = request.FILES['csv_file']
            decoded_file = csv_file.read().decode('utf-8')
            reader = csv.reader(io.StringIO(decoded_file))
            rows = list(reader)
            return JsonResponse({'rows': rows})
    elif request.method == 'GET' and request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        history = UploadHistory.objects.filter(user=request.user).order_by('-upload_time')[:10]
        data = [
            {
                'filename': h.filename,
                'upload_time': h.upload_time.strftime('%Y-%m-%d %H:%M'),
                'status': h.status,
                'error_message': h.error_message
            } for h in history
        ]
        return JsonResponse({'history': data})
    return render(request, 'surveys/advanced_csv_upload.html') 
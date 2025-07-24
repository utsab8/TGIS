from django.contrib import admin
from .models import SurveyRecord, FileAttachment, UploadHistory, Boundary
from django.utils.html import format_html
from django.urls import path
from django.template.response import TemplateResponse
import json
from django.http import HttpResponse
import csv
import pandas as pd
import simplekml

class AreaSizeRangeFilter(admin.SimpleListFilter):
    title = 'Area Size Range'
    parameter_name = 'area_size_range'
    def lookups(self, request, model_admin):
        return [
            ('0-100', '0-100'),
            ('100-500', '100-500'),
            ('500-1000', '500-1000'),
            ('1000+', '1000+')
        ]
    def queryset(self, request, queryset):
        val = self.value()
        if val == '0-100':
            return queryset.filter(area_size__gte=0, area_size__lt=100)
        if val == '100-500':
            return queryset.filter(area_size__gte=100, area_size__lt=500)
        if val == '500-1000':
            return queryset.filter(area_size__gte=500, area_size__lt=1000)
        if val == '1000+':
            return queryset.filter(area_size__gte=1000)
        return queryset

def export_as_csv(modeladmin, request, queryset):
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename=survey_records.csv'
    writer = csv.writer(response)
    writer.writerow(['Kitta Number', 'Owner Name', 'Lat', 'Lon', 'Land Type', 'Area Size', 'Has Boundary', 'Data Source', 'Created At'])
    for r in queryset:
        writer.writerow([r.kitta_number, r.owner_name, r.lat, r.lon, r.land_type, r.area_size, r.has_boundary, r.data_source, r.created_at])
    return response
export_as_csv.short_description = "Export selected as CSV"

def export_as_excel(modeladmin, request, queryset):
    response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = 'attachment; filename=survey_records.xlsx'
    df = pd.DataFrame(list(queryset.values('kitta_number','owner_name','lat','lon','land_type','area_size','has_boundary','data_source','created_at')))
    with pd.ExcelWriter(response, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False)
    return response
export_as_excel.short_description = "Export selected as Excel"

def export_as_kml(modeladmin, request, queryset):
    kml = simplekml.Kml()
    for r in queryset:
        if r.lat and r.lon:
            kml.newpoint(name=str(r.kitta_number), coords=[(float(r.lon), float(r.lat))], description=f"Owner: {r.owner_name}\nArea: {r.area_size}")
    response = HttpResponse(kml.kml(), content_type='application/vnd.google-earth.kml+xml')
    response['Content-Disposition'] = 'attachment; filename=survey_records.kml'
    return response
export_as_kml.short_description = "Export selected as KML"

@admin.register(SurveyRecord)
class SurveyRecordAdmin(admin.ModelAdmin):
    list_display = ('kitta_number', 'owner_name', 'lat', 'lon', 'land_type', 'area_size', 'has_boundary', 'data_source', 'created_at')
    search_fields = ('kitta_number', 'owner_name', 'land_type')
    list_filter = ('land_type', 'has_boundary', 'data_source', 'created_at', AreaSizeRangeFilter)
    fieldsets = (
        (None, {
            'fields': ('kitta_number', 'owner_name', 'lat', 'lon', 'land_type', 'area_size', 'has_boundary', 'data_source', 'uploaded_by')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    readonly_fields = ('created_at', 'updated_at')
    change_list_template = "admin/surveys/surveyrecord_change_list.html"
    actions = [export_as_csv, export_as_excel, export_as_kml]

    def changelist_view(self, request, extra_context=None):
        # Aggregate summary stats
        from django.db.models import Count, Sum, Avg, Min, Max
        from django.db.models.functions import TruncMonth
        total = SurveyRecord.objects.count()
        total_area = SurveyRecord.objects.aggregate(Sum('area_size'))['area_size__sum'] or 0
        unique_owners = SurveyRecord.objects.values('owner_name').distinct().count()
        with_boundaries = SurveyRecord.objects.filter(has_boundary=True).count()
        land_type_stats = SurveyRecord.objects.values('land_type').annotate(count=Count('id')).order_by('-count')
        land_type_labels = [lt['land_type'] or 'Unknown' for lt in land_type_stats]
        land_type_counts = [lt['count'] for lt in land_type_stats]
        # Data source pie
        data_source_stats = SurveyRecord.objects.values('data_source').annotate(count=Count('id'))
        data_source_labels = [ds['data_source'] or 'Unknown' for ds in data_source_stats]
        data_source_counts = [ds['count'] for ds in data_source_stats]
        # Created per month line
        created_stats = SurveyRecord.objects.annotate(month=TruncMonth('created_at')).values('month').annotate(count=Count('id')).order_by('month')
        created_labels = [c['month'].strftime('%Y-%m') if c['month'] else 'Unknown' for c in created_stats]
        created_counts = [c['count'] for c in created_stats]
        # Top 5 owners
        top_owners_qs = SurveyRecord.objects.values('owner_name').annotate(count=Count('id')).order_by('-count')[:5]
        top_owners_labels = [o['owner_name'] or 'Unknown' for o in top_owners_qs]
        top_owners_counts = [o['count'] for o in top_owners_qs]
        # Area distribution histogram (10 bins)
        import numpy as np
        area_values = list(SurveyRecord.objects.exclude(area_size=None).values_list('area_size', flat=True))
        if area_values:
            hist_counts, bin_edges = np.histogram(area_values, bins=10)
            area_hist_counts = hist_counts.tolist()
            area_hist_labels = [f"{int(bin_edges[i])}-{int(bin_edges[i+1])}" for i in range(len(bin_edges)-1)]
        else:
            area_hist_counts = []
            area_hist_labels = []
        # Recent uploads (last 5)
        recent_uploads = SurveyRecord.objects.order_by('-created_at')[:5]
        extra_context = extra_context or {}
        extra_context['total'] = total
        extra_context['total_area'] = total_area
        extra_context['unique_owners'] = unique_owners
        extra_context['with_boundaries'] = with_boundaries
        extra_context['land_type_labels'] = json.dumps(land_type_labels)
        extra_context['land_type_counts'] = json.dumps(land_type_counts)
        extra_context['data_source_labels'] = json.dumps(data_source_labels)
        extra_context['data_source_counts'] = json.dumps(data_source_counts)
        extra_context['created_labels'] = json.dumps(created_labels)
        extra_context['created_counts'] = json.dumps(created_counts)
        extra_context['top_owners_labels'] = json.dumps(top_owners_labels)
        extra_context['top_owners_counts'] = json.dumps(top_owners_counts)
        extra_context['area_hist_labels'] = json.dumps(area_hist_labels)
        extra_context['area_hist_counts'] = json.dumps(area_hist_counts)
        extra_context['recent_uploads'] = recent_uploads
        avg_area = SurveyRecord.objects.aggregate(Avg('area_size'))['area_size__avg']
        min_area = SurveyRecord.objects.aggregate(Min('area_size'))['area_size__min']
        max_area = SurveyRecord.objects.aggregate(Max('area_size'))['area_size__max']
        extra_context['avg_area'] = round(avg_area, 2) if avg_area is not None else None
        extra_context['min_area'] = round(min_area, 2) if min_area is not None else None
        extra_context['max_area'] = round(max_area, 2) if max_area is not None else None
        return super().changelist_view(request, extra_context=extra_context)

@admin.register(Boundary)
class BoundaryAdmin(admin.ModelAdmin):
    list_display = ('id', 'survey_record', 'created_at', 'updated_at')
    search_fields = ('survey_record__kitta_number',)
    list_filter = ('created_at',)
    readonly_fields = ('created_at', 'updated_at')

admin.site.register(FileAttachment)
admin.site.register(UploadHistory)

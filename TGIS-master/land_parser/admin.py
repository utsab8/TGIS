from django.contrib import admin
from .models import LandParcel


@admin.register(LandParcel)
class LandParcelAdmin(admin.ModelAdmin):
    list_display = ('kitta_number', 'owner_name', 'area', 'get_area_hectares', 'created_at')
    list_filter = ('created_at', 'updated_at')
    search_fields = ('kitta_number', 'owner_name')
    readonly_fields = ('created_at', 'updated_at')
    ordering = ('-created_at',)
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('kitta_number', 'owner_name', 'area')
        }),
        ('Geographic Data', {
            'fields': ('coordinates',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def get_area_hectares(self, obj):
        return f"{obj.get_area_hectares():.2f} ha"
    get_area_hectares.short_description = 'Area (hectares)'

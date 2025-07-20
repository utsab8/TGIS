from django import template
from django.template.defaultfilters import floatformat

register = template.Library()

@register.filter
def format_area(value):
    """Format area values with appropriate units"""
    if value is None or value == 0:
        return "N/A"
    
    if value >= 10000:  # 1 hectare
        return f"{value/10000:.2f} ha"
    elif value >= 1:
        return f"{value:.2f} m²"
    else:
        return f"{value:.4f} m²"

@register.filter
def format_coordinates(value):
    """Format coordinate values for display"""
    if not value:
        return "N/A"
    
    if isinstance(value, (list, tuple)) and len(value) >= 2:
        return f"{value[0]:.6f}, {value[1]:.6f}"
    
    return str(value)

@register.filter
def truncate_coordinates(value, length=50):
    """Truncate coordinate strings for display"""
    if not value:
        return "N/A"
    
    if isinstance(value, (list, tuple)):
        # Convert coordinates to string
        coord_str = "; ".join([f"{coord[0]:.6f},{coord[1]:.6f}" for coord in value[:3]])
        if len(value) > 3:
            coord_str += f" ... (+{len(value)-3} more)"
        return coord_str
    
    return str(value)[:length] + "..." if len(str(value)) > length else str(value)

@register.filter
def format_file_size(value):
    """Format file size in human readable format"""
    if value is None:
        return "Unknown"
    
    for unit in ['B', 'KB', 'MB', 'GB']:
        if value < 1024.0:
            return f"{value:.1f} {unit}"
        value /= 1024.0
    
    return f"{value:.1f} TB"

@register.filter
def get_geometry_color(geometry_type):
    """Get color class for geometry type badges"""
    colors = {
        'Polygon': 'bg-success',
        'Point': 'bg-primary',
        'LineString': 'bg-warning',
        'MultiGeometry': 'bg-info'
    }
    return colors.get(geometry_type, 'bg-secondary') 
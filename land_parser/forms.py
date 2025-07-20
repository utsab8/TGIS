from django import forms
from django.core.exceptions import ValidationError
import os


class KMLUploadForm(forms.Form):
    """
    Form for uploading KML files with validation
    """
    kml_file = forms.FileField(
        label='Select KML File',
        help_text='Upload a KML file containing land parcel data (max 5MB)',
        widget=forms.FileInput(attrs={
            'class': 'form-control',
            'accept': '.kml',
            'id': 'kml_file'
        })
    )
    
    def clean_kml_file(self):
        """
        Validate the uploaded KML file
        """
        file = self.cleaned_data.get('kml_file')
        
        if not file:
            raise ValidationError('Please select a file to upload.')
        
        # Check file extension
        file_name = file.name
        if not file_name.lower().endswith('.kml'):
            raise ValidationError('Only KML files are allowed. Please upload a .kml file.')
        
        # Check file size (5MB = 5 * 1024 * 1024 bytes)
        max_size = 5 * 1024 * 1024  # 5MB in bytes
        if file.size > max_size:
            raise ValidationError(f'File size must be under 5MB. Current size: {file.size / (1024*1024):.2f}MB')
        
        # Check if file is empty
        if file.size == 0:
            raise ValidationError('The uploaded file is empty.')
        
        return file
    
    def save_to_session(self, request):
        """
        Save file content to session for processing
        """
        file = self.cleaned_data.get('kml_file')
        if file:
            # Read file content
            file_content = file.read().decode('utf-8')
            
            # Store in session
            request.session['uploaded_kml'] = file_content
            request.session['kml_filename'] = file.name
            request.session['kml_size'] = file.size
            
            return True
        return False 
# Geo Survey Pro

A comprehensive Django-based geographic survey application for managing and analyzing geographic data, KML files, and survey records.

## Features

- **KML File Processing**: Upload, validate, and process KML files
- **CSV to KML Conversion**: Convert CSV data to KML format
- **Google Earth Integration**: View geographic data in Google Earth
- **Survey Management**: Create and manage survey records
- **User Authentication**: Secure user registration and login system
- **Data Export**: Export data in various formats (PDF, Excel)
- **QR Code Generation**: Generate QR codes for survey records
- **Geographic Analysis**: Advanced geographic data analysis tools

## Technology Stack

- **Backend**: Django 5.2.4
- **Database**: SQLite (development), PostgreSQL (production ready)
- **Frontend**: HTML, CSS, JavaScript, Bootstrap
- **Geographic Libraries**: 
  - simplekml
  - fastkml
  - geopy
  - pygeoif
- **Additional Libraries**:
  - WeasyPrint (PDF generation)
  - XlsxWriter (Excel export)
  - QR Code generation
  - Django REST Framework

## Installation

### Prerequisites

- Python 3.8 or higher
- pip (Python package installer)

### Setup Instructions

1. **Clone the repository**
   ```bash
   git clone https://github.com/utsab8/TGIS.git
   cd TGIS
   ```

2. **Create a virtual environment**
   ```bash
   python -m venv venv
   ```

3. **Activate the virtual environment**
   
   **Windows:**
   ```bash
   venv\Scripts\activate
   ```
   
   **macOS/Linux:**
   ```bash
   source venv/bin/activate
   ```

4. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

5. **Run database migrations**
   ```bash
   python manage.py migrate
   ```

6. **Create a superuser (optional)**
   ```bash
   python manage.py createsuperuser
   ```

7. **Run the development server**
   ```bash
   python manage.py runserver
   ```

8. **Access the application**
   
   Open your browser and navigate to `http://127.0.0.1:8000/`

## Project Structure

```
Geo survey pro/
├── accounts/              # User authentication app
├── surveys/              # Main survey management app
├── geosurveypro/         # Django project settings
├── templates/            # HTML templates
├── static/              # Static files (CSS, JS, images)
├── media/               # User uploaded files
├── uploads/             # File uploads directory
├── requirements.txt     # Python dependencies
├── manage.py           # Django management script
└── README.md           # This file
```

## Usage

### KML File Processing

1. Navigate to the KML upload section
2. Upload your KML file
3. The system will validate and process the file
4. View the processed data in various formats

### CSV to KML Conversion

1. Upload a CSV file with geographic coordinates
2. Configure the conversion settings
3. Download the generated KML file

### Survey Management

1. Create new survey records
2. Add geographic boundaries using KML files
3. Generate QR codes for easy access
4. Export data in PDF or Excel format

## API Endpoints

The application includes REST API endpoints for:

- Survey records management
- KML file processing
- User authentication
- Data export

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add some amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Support

For support and questions, please open an issue on the GitHub repository.

## Acknowledgments

- Django community for the excellent web framework
- Open source geographic libraries contributors
- All contributors to this project 

## PDF Export with Map Snapshot

The PDF export feature includes a map snapshot generated with Folium. Each selected survey record is shown as a marker with Kitta Number and Owner Name. The map is embedded in the PDF as an image.

### Requirements
- folium
- selenium
- pillow
- ChromeDriver (for Selenium, must be installed and in your system PATH)

### Setup
1. Install dependencies:
   ```bash
   pip install folium selenium pillow
   ```
2. Download ChromeDriver from https://sites.google.com/chromium.org/driver/ and place it in your system PATH.
   - The ChromeDriver version must match your installed version of Google Chrome.
3. The PDF export will now generate a map image for your selected survey records.

### Customization
- The map shows all selected records as markers.
- Each marker popup displays the Kitta Number and Owner Name.
- The map is centered on your data.
- For further customization (polygons, custom marker styles, etc.), edit the `generate_folium_map_image` function in `surveys/views.py`. 
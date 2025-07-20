from django.test import TestCase, Client
from django.urls import reverse
from django.core.files.uploadedfile import SimpleUploadedFile
from .models import KMLFile, KMLBoundary, SurveyRecord

# Create your tests here.

class KMLProcessingTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.kml_content = '''<?xml version="1.0" encoding="UTF-8"?>
        <kml xmlns="http://www.opengis.net/kml/2.2">
          <Document>
            <Placemark>
              <name>Test Polygon</name>
              <Polygon>
                <outerBoundaryIs>
                  <LinearRing>
                    <coordinates>85.3,27.7,0 85.31,27.71,0 85.32,27.7,0 85.3,27.7,0</coordinates>
                  </LinearRing>
                </outerBoundaryIs>
              </Polygon>
            </Placemark>
          </Document>
        </kml>'''.encode('utf-8')

    def test_kml_upload_and_processing(self):
        kml_file = SimpleUploadedFile('test.kml', self.kml_content, content_type='application/vnd.google-earth.kml+xml')
        response = self.client.post(reverse('kml_upload'), {'file': kml_file})
        self.assertEqual(response.status_code, 302)
        self.assertTrue(KMLFile.objects.filter(name='test.kml').exists())
        self.assertTrue(KMLBoundary.objects.filter(name='Test Polygon').exists())

class CSVUploadTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.csv_content = b'title,description,lat,lon\nPlot1,Desc,27.7,85.3\nPlot2,Desc,27.8,85.32\n'

    def test_csv_upload(self):
        csv_file = SimpleUploadedFile('test.csv', self.csv_content, content_type='text/csv')
        response = self.client.post(reverse('csv_upload'), {'file': csv_file})
        self.assertEqual(response.status_code, 302)
        self.assertTrue(SurveyRecord.objects.filter(title='Plot1').exists())
        self.assertTrue(SurveyRecord.objects.filter(title='Plot2').exists())

class GoogleEarthProTests(TestCase):
    def setUp(self):
        self.client = Client()
        SurveyRecord.objects.create(title='Plot1', lat=27.7, lon=85.3)

    def test_kml_export_compatibility(self):
        response = self.client.get(reverse('kml_export_batch'))
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'<kml', response.content)
        self.assertIn(b'<Placemark', response.content)

# Integration and performance tests for map and large KML files would be added with Selenium or pytest-django plugins.

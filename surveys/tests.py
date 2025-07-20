from django.test import TestCase, Client
from django.urls import reverse
from django.core.files.uploadedfile import SimpleUploadedFile
from .models import SurveyRecord

# Create your tests here.

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

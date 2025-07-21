from .views import advanced_csv_upload

urlpatterns += [
    path('advanced-csv-upload/', advanced_csv_upload, name='advanced_csv_upload'),
] 
from django.views.generic import TemplateView

urlpatterns += [
    path('upload/', TemplateView.as_view(template_name='upload.html'), name='upload'),
] 
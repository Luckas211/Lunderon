# gerador_videos/urls.py

from django.contrib import admin
from django.urls import path, include
# Importe as duas linhas abaixo
from django.conf import settings
from django.conf.urls.static import static


urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('core.urls')),
]

# Adicione esta linha no final do arquivo
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
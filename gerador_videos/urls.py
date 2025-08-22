from django.contrib import admin  # Adição: Import para o admin
from django.urls import path, include  # Include se você tiver apps como core
from django.conf import settings
from django.conf.urls.static import static  # Para servir media/static em dev

urlpatterns = [
    path('admin/', admin.site.urls),  # Adição: URL para o Django Admin padrão
    path('', include('core.urls')),  # Assumindo que core.urls tem as rotas do app
    # Adicione outras includes aqui se houver mais apps
]

# Adição: Servir arquivos estáticos e media em modo DEBUG (para desenvolvimento)
if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
from django.contrib import admin
# APAGUE 'TelaFinal' DESTA LINHA
from .models import CategoriaVideo, CategoriaMusica, VideoBase, MusicaBase, VideoGerado

admin.site.register(CategoriaVideo)
admin.site.register(CategoriaMusica)
admin.site.register(VideoBase)
admin.site.register(MusicaBase)
admin.site.register(VideoGerado)
# A LINHA 'admin.site.register(TelaFinal)' TAMBÉM DEVE SER REMOVIDA, SE EXISTIR.
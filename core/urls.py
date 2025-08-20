from django.urls import path
from . import views

# importações no topo do arquivo...

urlpatterns = [
    # A página inicial (/) agora aponta corretamente para a view 'index' (home.html)
    path('', views.index, name='index'),

    # A página do gerador de vídeos agora tem sua própria URL: /gerador/
    path('gerador/', views.pagina_gerador, name='pagina_gerador'),

    path('meus-videos/', views.meus_videos, name='meus_videos'),

    # URL para a página "Como Funciona"
    path('como-funciona/', views.como_funciona, name='como_funciona'),

    # URL para a página "Planos"
    path('planos/', views.planos, name='planos'),

    # URL para a nova página "Cadastre-se"
    path('cadastre-se/', views.cadastre_se, name='cadastre_se'),

    path('login/', views.login_view, name='login'),
    path('suporte/', views.suporte, name='suporte'),
    
    # URL para o preview da voz (está correta)
    path('preview-voz/<str:nome_da_voz>/', views.preview_voz, name='preview_voz'),
]

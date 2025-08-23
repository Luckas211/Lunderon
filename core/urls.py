from django.urls import path
from . import views
from django.contrib import admin



urlpatterns = [
    # Páginas públicas
    path('', views.index, name='index'),
    path('gerador/', views.pagina_gerador, name='pagina_gerador'),
    path('meus-videos/', views.meus_videos, name='meus_videos'),
    path('como-funciona/', views.como_funciona, name='como_funciona'),
    path('planos/', views.planos, name='planos'),
    path('cadastre-se/', views.cadastre_se, name='cadastre_se'),
    path('login/', views.login_view, name='login'),
    path('suporte/', views.suporte, name='suporte'),
    path('admin/', admin.site.urls),
    path('stripe-webhook/', views.stripe_webhook, name='stripe-webhook'), 
    # ----------------------------
    # Painel administrativo
    # ----------------------------
    # Assinaturas
    path('painel/assinaturas/', views.admin_assinaturas, name='admin_assinaturas'),
    path('painel/assinaturas/ativar/<int:id>/', views.ativar_assinatura, name='ativar_assinatura'),
    path('painel/assinaturas/cancelar/<int:id>/', views.cancelar_assinatura, name='cancelar_assinatura'),
    path('painel/assinaturas/editar/<int:id>/', views.editar_assinatura, name='editar_assinatura'),
    path('painel/assinaturas/excluir/<int:id>/', views.excluir_assinatura, name='excluir_assinatura'),

    # Painel de Configurações
    path('painel/configuracoes/', views.admin_configuracoes, name='admin_configuracoes'),
    path('painel/editar_configuracao/<int:id>/', views.editar_configuracao, name='editar_configuracao'),
    path('painel/deletar_configuracao/<int:id>/', views.deletar_configuracao, name='deletar_configuracao'),

    #Painel de pagamentos
    # Painel de pagamentos
    path('painel/pagamentos/', views.admin_pagamentos, name='admin_pagamentos'),
    path('painel/aprovar_pagamento/<int:id>/', views.aprovar_pagamento, name='aprovar_pagamento'),
    path('painel/recusar_pagamento/<int:id>/', views.recusar_pagamento, name='recusar_pagamento'),
    path('painel/deletar_pagamento/<int:id>/', views.deletar_pagamento, name='deletar_pagamento'),
    path('painel/configuracoes/adicionar/', views.adicionar_configuracao, name='adicionar_configuracao'),
    path('painel/configuracoes/editar/<int:id>/', views.editar_configuracao, name='editar_configuracao'),
    path('stripe-webhook/', views.stripe_webhook, name='stripe-webhook'),

    # Painel administrativo - relatórios
    path('painel/relatorios/', views.admin_relatorios, name='admin_relatorios'),
    


    # Usuários
    path('painel/usuarios/', views.admin_usuarios, name='admin_usuarios'),
    path('painel/usuarios/editar/<int:user_id>/', views.editar_usuario, name='editar_usuario'),
    path('painel/usuarios/deletar/<int:user_id>/', views.deletar_usuario, name='deletar_usuario'),
    path('perfil/', views.meu_perfil, name='meu_perfil'),
    path('perfil/', views.meu_perfil, name='sua_pagina_de_perfil'),
    path('perfil/editar/', views.editar_perfil, name='editar_perfil'),
    path('assinatura/gerenciar/', views.gerenciar_assinatura_redirect, name='gerenciar_assinatura'), 
    path('criar-checkout/', views.criar_checkout_session, name='criar_checkout'),
     path('pagamento/sucesso/', views.pagamento_sucesso, name='pagamento_sucesso'),



      # URL DE AUTENTICAÇÃO E PERFIL
    path('logout/', views.logout_view, name='logout'),
    path('perfil/', views.meu_perfil, name='meu_perfil'), # <--- CORRIGIDO



    

    # URL para o preview da voz
    path('preview-voz/<str:nome_da_voz>/', views.preview_voz, name='preview_voz'),
]
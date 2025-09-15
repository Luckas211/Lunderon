# core/urls.py

from django.urls import path
from . import views
from django.contrib.auth import views as auth_views

urlpatterns = [
    # ========================================
    # PÁGINAS PÚBLICAS E DE AUTENTICAÇÃO
    # ========================================
    path('', views.index, name='index'),
    path('como-funciona/', views.como_funciona, name='como_funciona'),
    path('planos/', views.planos, name='planos'),
    path('suporte/', views.suporte, name='suporte'),
    path('termos-de-servico/', views.termos_de_servico, name='termos_de_servico'),
    path('politica-de-privacidade/', views.politica_de_privacidade, name='politica_de_privacidade'),
    path('cadastre-se/', views.cadastre_se, name='cadastre_se'),
    path('verificar-email/<str:token>/', views.verificar_email, name='verify_email'),
    path('verificar-email/<str:token>/', views.verificar_email, name='verify_email'),
    path('reenviar-verificacao/<int:user_id>/', views.reenviar_verificacao_email, name='reenviar_verificacao'),

    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('validate-otp/', views.validate_otp_view, name='validate_otp'),

    # ========================================
    # PÁGINAS DO USUÁRIO LOGADO
    # ========================================
    path('gerador/', views.pagina_gerador, name='pagina_gerador'),
    path('meus-videos/', views.meus_videos, name='meus_videos'),
    path('perfil/', views.meu_perfil, name='meu_perfil'),
    path('perfil/editar/', views.editar_perfil, name='editar_perfil'),
    
    # ========================================
    # FLUXO DE DOWNLOAD E DELEÇÃO DE VÍDEO (CORRIGIDO)
    # ========================================
    path('download-video/<int:video_id>/', views.download_video_direto, name='download_video_direto'),
    #path('delete-video-file/<int:video_id>/', views.delete_video_file, name='delete_video_file'),

    # ========================================
    # PROCESSAMENTO DE PAGAMENTOS (STRIPE)
    # ========================================
    path('criar-checkout/', views.criar_checkout_session, name='criar_checkout'),
    path('pagamento/sucesso/', views.pagamento_sucesso, name='pagamento_sucesso'),
    path('pagamento/falha/', views.pagamento_falho, name='pagamento_falho'),
    path('stripe-webhook/', views.stripe_webhook, name='stripe-webhook'),
    path('assinatura/gerenciar/', views.gerenciar_assinatura_redirect, name='gerenciar_assinatura'),

    # ========================================
    # PAINEL DE ADMIN CUSTOMIZADO (/painel/)
    # ========================================
    path('painel/usuarios/', views.admin_usuarios, name='admin_usuarios'),
    path('painel/usuarios/editar/<int:user_id>/', views.editar_usuario, name='editar_usuario'),
    path('painel/usuarios/deletar/<int:user_id>/', views.deletar_usuario, name='deletar_usuario'),
    path('painel/assinaturas/', views.admin_assinaturas, name='admin_assinaturas'),
    path('painel/assinaturas/ativar/<int:id>/', views.ativar_assinatura, name='ativar_assinatura'),
    path('painel/assinaturas/cancelar/<int:id>/', views.cancelar_assinatura, name='cancelar_assinatura'),
    path('painel/assinaturas/editar/<int:id>/', views.editar_assinatura, name='editar_assinatura'),
    path('painel/assinaturas/excluir/<int:id>/', views.excluir_assinatura, name='excluir_assinatura'),
    path('painel/assinatura/<int:assinatura_id>/pendente/', views.deixar_assinatura_pendente, name='deixar_assinatura_pendente'),
    path('painel/assinatura/<int:assinatura_id>/cancelar/', views.cancelar_assinatura_admin, name='cancelar_assinatura_admin'),
    path('painel/pagamentos/', views.admin_pagamentos, name='admin_pagamentos'),
    path('painel/aprovar_pagamento/<int:id>/', views.aprovar_pagamento, name='aprovar_pagamento'),
    path('painel/recusar_pagamento/<int:id>/', views.recusar_pagamento, name='recusar_pagamento'),
    path('painel/deletar_pagamento/<int:id>/', views.deletar_pagamento, name='deletar_pagamento'),
    path('painel/configuracoes/', views.admin_configuracoes, name='admin_configuracoes'),
    path('painel/configuracoes/adicionar/', views.adicionar_configuracao, name='adicionar_configuracao'),
    path('painel/configuracoes/editar/<int:id>/', views.editar_configuracao, name='editar_configuracao'),
    path('painel/deletar_configuracao/<int:id>/', views.deletar_configuracao, name='deletar_configuracao'),
    path('painel/relatorios/', views.admin_relatorios, name='admin_relatorios'),

    # ========================================
    # OUTRAS FUNCIONALIDADES (API/HELPERS)
    # ========================================
    path('preview-voz/<str:nome_da_voz>/', views.preview_voz, name='preview_voz'),
    path('estimativa-narracao/', views.estimativa_narracao, name='estimativa_narracao'),

    # ========================================
    # URLS PARA RESET DE SENHA
    # ========================================
    path('reset_password/', 
         auth_views.PasswordResetView.as_view(template_name="core/password_reset/password_reset_form.html"), 
         name="password_reset"),
    path('reset_password_sent/', 
         auth_views.PasswordResetDoneView.as_view(template_name="core/password_reset/password_reset_done.html"), 
         name="password_reset_done"),
    path('reset/<uidb64>/<token>/', 
         auth_views.PasswordResetConfirmView.as_view(template_name="core/password_reset/password_reset_confirm.html"), 
         name="password_reset_confirm"),
    path('reset_password_complete/', 
         auth_views.PasswordResetCompleteView.as_view(template_name="core/password_reset/password_reset_complete.html"), 
         name="password_reset_complete"),
]
# Em core/middleware.py

from django.shortcuts import redirect
from django.urls import reverse
from django.contrib import messages

class EmailVerificationMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Deixa passar se o usuário não estiver logado
        if not request.user.is_authenticated:
            return self.get_response(request)

        # Deixa passar se o e-mail já foi verificado ou se o usuário é um admin
        if request.user.email_verificado or request.user.is_staff:
            return self.get_response(request)

        # Lista de URLs que um usuário não verificado PODE acessar (para evitar loops)
        # O replace() é um truque para pegar o início da URL de verificação sem o token
        allowed_urls = [reverse('logout'), reverse('login'), reverse('verify_email', args=['token_placeholder']).replace('token_placeholder', '')]

        # Deixa passar se o usuário estiver tentando acessar uma das URLs permitidas
        if any(request.path.startswith(url) for url in allowed_urls):
            return self.get_response(request)

        # Se chegou até aqui, o usuário está logado, não é verificado e está tentando
        # acessar uma página protegida. Então, ele é bloqueado.
        messages.warning(request, 'Você precisa verificar seu e-mail para acessar esta página.')
        return redirect('login')
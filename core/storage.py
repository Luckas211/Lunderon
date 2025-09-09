from storages.backends.s3boto3 import S3Boto3Storage
from django.conf import settings


class MediaStorage(S3Boto3Storage):
    location = "media"
    file_overwrite = False
    custom_domain = settings.CLOUDFLARE_R2_PUBLIC_URL

    def url(self, name):
        # Retorna a URL pública sem assinatura
        url = super().url(name)
        # Remove parâmetros de assinatura se existirem
        if "?" in url:
            url = url.split("?")[0]
        return url

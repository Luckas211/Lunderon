from storages.backends.s3boto3 import S3Boto3Storage
from django.conf import settings

<<<<<<< HEAD

class MediaStorage(S3Boto3Storage):
    location = "media"
    file_overwrite = False
    custom_domain = settings.CLOUDFLARE_R2_PUBLIC_URL

=======
class MediaStorage(S3Boto3Storage):
    location = 'media'
    file_overwrite = False
    custom_domain = settings.CLOUDFLARE_R2_PUBLIC_URL
    
>>>>>>> ec41c5cc912ccc6d5f292e30b1908063fa6f6c96
    def url(self, name):
        # Retorna a URL pública sem assinatura
        url = super().url(name)
        # Remove parâmetros de assinatura se existirem
<<<<<<< HEAD
        if "?" in url:
            url = url.split("?")[0]
        return url
=======
        if '?' in url:
            url = url.split('?')[0]
        return url
>>>>>>> ec41c5cc912ccc6d5f292e30b1908063fa6f6c96

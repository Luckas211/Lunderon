from django.http import JsonResponse
from django.db import connection
from django.conf import settings
import boto3
from botocore.exceptions import ClientError


def health_check(request):
    """
    Health check endpoint for Cloud Run
    """
    health_status = {"status": "healthy", "checks": {}}

    # Check database connection
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        health_status["checks"]["database"] = "ok"
    except Exception as e:
        health_status["checks"]["database"] = f"error: {str(e)}"
        health_status["status"] = "unhealthy"

    # Check Cloudflare R2 connection
    try:
        if settings.AWS_ACCESS_KEY_ID and settings.AWS_SECRET_ACCESS_KEY:
            s3_client = boto3.client(
                "s3",
                endpoint_url=settings.AWS_S3_ENDPOINT_URL,
                aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
                aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
                region_name=settings.AWS_S3_REGION_NAME,
            )
            s3_client.head_bucket(Bucket=settings.AWS_STORAGE_BUCKET_NAME)
            health_status["checks"]["cloudflare_r2"] = "ok"
        else:
            health_status["checks"]["cloudflare_r2"] = "not_configured"
    except ClientError as e:
        health_status["checks"]["cloudflare_r2"] = f"error: {str(e)}"
        health_status["status"] = "unhealthy"
    except Exception as e:
        health_status["checks"]["cloudflare_r2"] = f"error: {str(e)}"
        health_status["status"] = "unhealthy"

    status_code = 200 if health_status["status"] == "healthy" else 503
    return JsonResponse(health_status, status=status_code)

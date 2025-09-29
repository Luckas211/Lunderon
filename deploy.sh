#!/bin/bash

# Deploy script for Google Cloud Run
set -e

# Configuration
PROJECT_ID="your-project-id"
SERVICE_NAME="gerador-videos"
REGION="us-central1"
IMAGE_NAME="gcr.io/${PROJECT_ID}/${SERVICE_NAME}"

echo "🚀 Starting deployment to Google Cloud Run..."

# Check if gcloud is installed
if ! command -v gcloud &> /dev/null; then
    echo "❌ gcloud CLI is not installed. Please install it first."
    exit 1
fi

# Set project
echo "📋 Setting project to ${PROJECT_ID}..."
gcloud config set project ${PROJECT_ID}

# Enable required APIs
echo "🔧 Enabling required APIs..."
gcloud services enable run.googleapis.com
gcloud services enable cloudbuild.googleapis.com
gcloud services enable secretmanager.googleapis.com

# Build and push Docker image
echo "🏗️ Building Docker image..."
gcloud builds submit --tag ${IMAGE_NAME}

# Create secrets (if they don't exist)
echo "🔐 Creating secrets..."
secrets=(
    "DATABASE_URL"
    "SECRET_KEY"
    "STRIPE_SECRET_KEY"
    "STRIPE_PUBLISHABLE_KEY"
    "STRIPE_WEBHOOK_SECRET"
    "EMAIL_HOST_USER"
    "EMAIL_HOST_PASSWORD"
    "AWS_ACCESS_KEY_ID"
    "AWS_SECRET_ACCESS_KEY"
    "AWS_STORAGE_BUCKET_NAME"
    "AWS_S3_ENDPOINT_URL"
    "CLOUDFLARE_R2_PUBLIC_URL"
)

for secret in "${secrets[@]}"; do
    if ! gcloud secrets describe app-secrets-${secret} &> /dev/null; then
        echo "Creating secret: ${secret}"
        echo -n "Please enter value for ${secret}: "
        read -s secret_value
        echo
        echo -n "${secret_value}" | gcloud secrets create app-secrets-${secret} --data-file=-
    fi
done

# Deploy to Cloud Run
echo "🚀 Deploying to Cloud Run..."
gcloud run deploy ${SERVICE_NAME} \
    --image ${IMAGE_NAME} \
    --platform managed \
    --region ${REGION} \
    --allow-unauthenticated \
    --memory 2Gi \
    --cpu 2 \
    --timeout 300s \
    --max-instances 10 \
    --min-instances 1 \
    --concurrency 100 \
    --set-env-vars="DEBUG=False,GOOGLE_CLOUD_PROJECT=${PROJECT_ID},GOOGLE_CLOUD_REGION=${REGION}" \
    --set-secrets="DATABASE_URL=app-secrets-DATABASE_URL:latest,SECRET_KEY=app-secrets-SECRET_KEY:latest,STRIPE_SECRET_KEY=app-secrets-STRIPE_SECRET_KEY:latest,STRIPE_PUBLISHABLE_KEY=app-secrets-STRIPE_PUBLISHABLE_KEY:latest,STRIPE_WEBHOOK_SECRET=app-secrets-STRIPE_WEBHOOK_SECRET:latest,EMAIL_HOST_USER=app-secrets-EMAIL_HOST_USER:latest,EMAIL_HOST_PASSWORD=app-secrets-EMAIL_HOST_PASSWORD:latest,AWS_ACCESS_KEY_ID=app-secrets-AWS_ACCESS_KEY_ID:latest,AWS_SECRET_ACCESS_KEY=app-secrets-AWS_SECRET_ACCESS_KEY:latest,AWS_STORAGE_BUCKET_NAME=app-secrets-AWS_STORAGE_BUCKET_NAME:latest,AWS_S3_ENDPOINT_URL=app-secrets-AWS_S3_ENDPOINT_URL:latest,CLOUDFLARE_R2_PUBLIC_URL=app-secrets-CLOUDFLARE_R2_PUBLIC_URL:latest"

# Get the service URL
SERVICE_URL=$(gcloud run services describe ${SERVICE_NAME} --region=${REGION} --format='value(status.url)')

echo "✅ Deployment completed successfully!"
echo "🌐 Service URL: ${SERVICE_URL}"
echo "🏥 Health check: ${SERVICE_URL}/health/"

# Run database migrations
echo "🗄️ Running database migrations..."
gcloud run jobs create migrate-db \
    --image ${IMAGE_NAME} \
    --region ${REGION} \
    --set-secrets="DATABASE_URL=app-secrets-DATABASE_URL:latest,SECRET_KEY=app-secrets-SECRET_KEY:latest" \
    --command="python,manage.py,migrate" \
    --memory 1Gi \
    --cpu 1 \
    --max-retries 3 \
    --parallelism 1 \
    --task-count 1

gcloud run jobs execute migrate-db --region=${REGION} --wait

echo "🎉 Deployment and migration completed!"
echo "📊 Monitor your service: https://console.cloud.google.com/run/detail/${REGION}/${SERVICE_NAME}"
# app/storage.py
import os
import boto3
import json
import logging
from io import BytesIO
from botocore.exceptions import ClientError

S3_ENDPOINT_URL = os.getenv("S3_ENDPOINT_URL")
S3_ACCESS_KEY = os.getenv("AWS_ACCESS_KEY_ID")
S3_SECRET_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
S3_BUCKET_NAME = os.getenv("S3_BUCKET_NAME")
STORAGE_PROVIDER = os.getenv("STORAGE_PROVIDER", "minio")  # "minio" for local, "tigris" for production

# Derive storage public URL from API_BASE_URL
API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")

def get_public_storage_url():
    """Get the public URL for storage access based on environment."""
    if STORAGE_PROVIDER == "tigris":
        # For Tigris (Fly.io production), files should be served through our API
        # since Tigris doesn't have direct public access like S3
        return f"{API_BASE_URL}/api/files"
    else:
        # For local development with MinIO
        if "localhost" in API_BASE_URL:
            # Replace port 8000 with 9000 for MinIO
            return API_BASE_URL.replace(":8000", ":9000")
        else:
            # Fallback for other local configurations
            return "http://localhost:9000"

logger = logging.getLogger(__name__)

try:
    s3_client = boto3.client(
        "s3",
        endpoint_url=S3_ENDPOINT_URL,
        aws_access_key_id=S3_ACCESS_KEY,
        aws_secret_access_key=S3_SECRET_KEY,
    )
    logger.info(f"✅ S3 client initialized with endpoint: {S3_ENDPOINT_URL}")
except Exception as e:
    logger.error(f"❌ Failed to initialize S3 client: {e}")
    s3_client = None


def ensure_bucket_exists():
    """Create bucket if it doesn't exist and set up proper access policies."""
    if not s3_client:
        logger.error("S3 client not initialized")
        return False

    try:
        # Check if bucket exists
        s3_client.head_bucket(Bucket=S3_BUCKET_NAME)
        logger.info(f"✅ Bucket {S3_BUCKET_NAME} exists")
        
        # For MinIO (local development), set public read policy
        if STORAGE_PROVIDER == "minio":
            try:
                # Set bucket policy for public read access
                public_read_policy = {
                    "Version": "2012-10-17",
                    "Statement": [
                        {
                            "Effect": "Allow",
                            "Principal": "*",
                            "Action": "s3:GetObject",
                            "Resource": f"arn:aws:s3:::{S3_BUCKET_NAME}/*"
                        }
                    ]
                }
                
                s3_client.put_bucket_policy(
                    Bucket=S3_BUCKET_NAME,
                    Policy=json.dumps(public_read_policy)
                )
                logger.info(f"✅ Set public read policy for bucket {S3_BUCKET_NAME}")
            except Exception as policy_error:
                logger.warning(f"⚠️ Could not set bucket policy: {policy_error}")
        
        return True
        
    except ClientError as e:
        error_code = e.response['Error']['Code']
        if error_code == '404':
            try:
                # Create bucket
                if S3_ENDPOINT_URL and "amazonaws.com" not in S3_ENDPOINT_URL:
                    # For non-AWS endpoints (MinIO, Tigris), don't specify LocationConstraint
                    s3_client.create_bucket(Bucket=S3_BUCKET_NAME)
                else:
                    # For AWS S3
                    s3_client.create_bucket(
                        Bucket=S3_BUCKET_NAME,
                        CreateBucketConfiguration={'LocationConstraint': 'us-west-2'}
                    )
                
                logger.info(f"✅ Created bucket: {S3_BUCKET_NAME}")
                
                # Set public read policy for MinIO only
                if STORAGE_PROVIDER == "minio":
                    public_read_policy = {
                        "Version": "2012-10-17",
                        "Statement": [
                            {
                                "Effect": "Allow",
                                "Principal": "*",
                                "Action": "s3:GetObject",
                                "Resource": f"arn:aws:s3:::{S3_BUCKET_NAME}/*"
                            }
                        ]
                    }
                    
                    s3_client.put_bucket_policy(
                        Bucket=S3_BUCKET_NAME,
                        Policy=json.dumps(public_read_policy)
                    )
                    logger.info(f"✅ Set public read policy for bucket {S3_BUCKET_NAME}")
                
                return True
            except Exception as create_error:
                logger.error(f"❌ Failed to create bucket {S3_BUCKET_NAME}: {create_error}")
                return False
        else:
            logger.error(f"❌ Error checking bucket {S3_BUCKET_NAME}: {e}")
            return False


def upload_file_to_storage(file_data: bytes, filename: str) -> str:
    """
    Upload file to storage and return the public URL.
    For Tigris, returns a URL that will be served through our API.
    For MinIO, returns a direct URL to the storage.
    """
    if not s3_client:
        raise Exception("S3 client not initialized")

    # Ensure bucket exists
    if not ensure_bucket_exists():
        raise Exception(f"Bucket {S3_BUCKET_NAME} does not exist and could not be created")

    try:
        # Upload file
        s3_client.put_object(
            Bucket=S3_BUCKET_NAME,
            Key=filename,
            Body=BytesIO(file_data),
            ContentType='application/pdf'
        )
        
        # Generate the appropriate URL based on storage provider
        if STORAGE_PROVIDER == "tigris":
            # For Tigris, return URL that will be served through our API
            public_url = f"{get_public_storage_url()}/{filename}"
        else:
            # For MinIO, return direct URL
            public_url = f"{get_public_storage_url()}/{S3_BUCKET_NAME}/{filename}"
        
        logger.info(f"✅ File uploaded successfully: {filename}")
        logger.info(f"📋 Public URL: {public_url}")
        
        return public_url
        
    except Exception as e:
        logger.error(f"❌ Failed to upload file {filename}: {e}")
        raise


def download_file_from_storage(filename: str) -> bytes:
    """Download file from storage."""
    if not s3_client:
        raise Exception("S3 client not initialized")
    
    try:
        response = s3_client.get_object(Bucket=S3_BUCKET_NAME, Key=filename)
        return response['Body'].read()
    except Exception as e:
        logger.error(f"❌ Failed to download file {filename}: {e}")
        raise


def health_check() -> dict:
    """Health check for storage service."""
    try:
        if not s3_client:
            return {"status": "error", "message": "S3 client not initialized"}
        
        # Try to list objects in bucket (this will also create bucket if it doesn't exist)
        ensure_bucket_exists()
        s3_client.list_objects_v2(Bucket=S3_BUCKET_NAME, MaxKeys=1)
        
        return {
            "status": "ok", 
            "storage_provider": STORAGE_PROVIDER,
            "bucket": S3_BUCKET_NAME,
            "endpoint": S3_ENDPOINT_URL,
            "public_url_base": get_public_storage_url()
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


# Initialize bucket on module load
if s3_client:
    ensure_bucket_exists()

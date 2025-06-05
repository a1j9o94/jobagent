# app/storage.py
import os
import boto3
import logging
from io import BytesIO
from botocore.exceptions import ClientError

S3_ENDPOINT_URL = os.getenv("S3_ENDPOINT_URL")
S3_ACCESS_KEY = os.getenv("AWS_ACCESS_KEY_ID")
S3_SECRET_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
S3_BUCKET_NAME = os.getenv("S3_BUCKET_NAME")

logger = logging.getLogger(__name__)

try:
    s3_client = boto3.client(
        "s3",
        endpoint_url=S3_ENDPOINT_URL,
        aws_access_key_id=S3_ACCESS_KEY,
        aws_secret_access_key=S3_SECRET_KEY,
    )
    logger.info(f"Successfully initialized S3 client for endpoint: {S3_ENDPOINT_URL}")
except Exception as e:
    logger.error(f"Failed to initialize S3 client: {e}")
    s3_client = None


def ensure_bucket_exists():
    """Create the bucket if it doesn't exist."""
    if not s3_client:
        return False

    try:
        s3_client.head_bucket(Bucket=S3_BUCKET_NAME)
        logger.info(f"Bucket {S3_BUCKET_NAME} exists")
        return True
    except ClientError as e:
        error_code = int(e.response["Error"]["Code"])
        if error_code == 404:
            try:
                s3_client.create_bucket(Bucket=S3_BUCKET_NAME)
                logger.info(f"Created bucket {S3_BUCKET_NAME}")
                return True
            except ClientError as create_error:
                logger.error(f"Failed to create bucket: {create_error}")
                return False
        else:
            logger.error(f"Error checking bucket: {e}")
            return False


def upload_file_to_storage(
    file_content: bytes,
    object_name: str,
    content_type: str = "application/octet-stream",
) -> str | None:
    """Upload file content to object storage."""
    if not s3_client:
        logger.error("S3 client not available. Cannot upload file.")
        return None

    if not ensure_bucket_exists():
        logger.error("Bucket not available. Cannot upload file.")
        return None

    try:
        file_stream = BytesIO(file_content)
        s3_client.upload_fileobj(
            File=file_stream,
            Bucket=S3_BUCKET_NAME,
            Key=object_name,
            ExtraArgs={"ContentType": content_type},
        )
        logger.info(f"Successfully uploaded {object_name} to bucket {S3_BUCKET_NAME}.")
        file_url = f"{S3_ENDPOINT_URL}/{S3_BUCKET_NAME}/{object_name}"
        return file_url
    except ClientError as e:
        logger.error(f"Failed to upload {object_name} to S3. Error: {e}")
        return None


def health_check() -> bool:
    """Check if object storage is accessible."""
    if not s3_client:
        return False

    try:
        s3_client.head_bucket(Bucket=S3_BUCKET_NAME)
        return True
    except Exception as e:
        logger.error(f"S3 health check failed: {e}")
        return False

import os
import io
import boto3
from datetime import timedelta
from minio import Minio
from dotenv import load_dotenv

load_dotenv()

STORAGE_PROVIDER = os.getenv("STORAGE_PROVIDER", "minio")
BUCKET_NAME = os.getenv("MINIO_BUCKET", "motivai-reels")

# MinIO client
minio_client = Minio(
    os.getenv("MINIO_ENDPOINT", "minio:9000"),
    access_key=os.getenv("MINIO_ACCESS_KEY", "minioadmin"),
    secret_key=os.getenv("MINIO_SECRET_KEY", "minioadmin"),
    secure=False
)

# boto3 client — works with both S3 and MinIO
def get_boto3_client():
    if STORAGE_PROVIDER == "s3":
        return boto3.client(
            "s3",
            aws_access_key_id=os.getenv("AWS_ACCESS_KEY"),
            aws_secret_access_key=os.getenv("AWS_SECRET_KEY"),
            region_name=os.getenv("AWS_REGION", "ap-south-1")
        )
    else:
        # boto3 pointing at MinIO
        return boto3.client(
            "s3",
            endpoint_url=f"http://{os.getenv('MINIO_ENDPOINT', 'minio:9000')}",
            aws_access_key_id=os.getenv("MINIO_ACCESS_KEY", "minioadmin"),
            aws_secret_access_key=os.getenv("MINIO_SECRET_KEY", "minioadmin"),
            region_name="us-east-1"  # MinIO requires a region string
        )

def ensure_bucket_exists():
    if STORAGE_PROVIDER == "minio":
        if not minio_client.bucket_exists(BUCKET_NAME):
            minio_client.make_bucket(BUCKET_NAME)
    else:
        s3 = get_boto3_client()
        try:
            s3.head_bucket(Bucket=BUCKET_NAME)
        except Exception:
            s3.create_bucket(Bucket=BUCKET_NAME)

def upload_file(file_content: bytes, object_key: str, content_type: str) -> str:
    if STORAGE_PROVIDER == "minio":
        minio_client.put_object(
            BUCKET_NAME,
            object_key,
            io.BytesIO(file_content),
            length=len(file_content),
            content_type=content_type
        )
    else:
        s3 = get_boto3_client()
        s3.upload_fileobj(
            io.BytesIO(file_content),
            BUCKET_NAME,
            object_key,
            ExtraArgs={"ContentType": content_type}
        )
    return object_key

def get_file_url(object_key: str, expires_hours: int = 1) -> str:
    if STORAGE_PROVIDER == "minio":
        url = minio_client.presigned_get_object(
            BUCKET_NAME,
            object_key,
            expires=timedelta(hours=expires_hours)
        )
        return url.replace("http://minio:9000", "http://localhost:9000")
    else:
        s3 = get_boto3_client()
        url = s3.generate_presigned_url(
            "get_object",
            Params={"Bucket": BUCKET_NAME, "Key": object_key},
            ExpiresIn=expires_hours * 3600
        )
        return url
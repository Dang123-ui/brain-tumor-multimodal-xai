"""Bounded retries for complete AI input/output transfers to MinIO or R2."""

import http.client
import logging
import os
import socket
import ssl
import time
from typing import Callable, TypeVar

import certifi
import urllib3
from minio.error import S3Error, ServerError

logger = logging.getLogger(__name__)
T = TypeVar("T")


class StorageTransferError(RuntimeError):
    """A storage transfer still failed after its bounded retry attempts."""


def build_storage_http_client() -> urllib3.PoolManager:
    # Retry the whole operation below, including response.read(), rather than
    # stacking HTTP retries that cannot recover an interrupted response body.
    return urllib3.PoolManager(
        timeout=urllib3.Timeout(connect=10, read=30),
        maxsize=10,
        cert_reqs="CERT_REQUIRED",
        ca_certs=os.environ.get("SSL_CERT_FILE") or certifi.where(),
        retries=urllib3.Retry(total=0),
    )


def _is_transient_error(exc: Exception) -> bool:
    if isinstance(exc, S3Error):
        return exc.code in {
            "InternalError", "RequestTimeout", "RequestTimeoutException",
            "ServiceUnavailable", "SlowDown", "Throttling", "ThrottlingException",
        }
    if isinstance(exc, ServerError):
        return exc.status_code == 429 or 500 <= exc.status_code < 600
    return isinstance(exc, (
        urllib3.exceptions.HTTPError,
        http.client.IncompleteRead,
        ConnectionError,
        TimeoutError,
        ssl.SSLError,
        socket.gaierror,
    ))


def retry_storage_operation(
    operation: Callable[[], T], *, label: str, attempts: int = 3,
) -> T:
    for attempt in range(1, attempts + 1):
        try:
            return operation()
        except Exception as exc:
            if not _is_transient_error(exc):
                raise
            if attempt == attempts:
                raise StorageTransferError(
                    f"{label}: khong the truyen du lieu sau {attempts} lan thu ({exc})"
                ) from exc
            logger.warning("%s: retry %d/%d after %s", label, attempt, attempts, exc)
            time.sleep(min(2 ** (attempt - 1), 4))
    raise ValueError("attempts must be at least 1")


def read_object_bytes(client, bucket: str, object_name: str) -> bytes:
    """Return a complete object; discard partial bytes and reopen on failure."""
    def read_complete_object() -> bytes:
        response = client.get_object(bucket, object_name)
        try:
            data = response.read()
            expected_length = response.headers.get("Content-Length")
            if expected_length is not None and len(data) != int(expected_length):
                raise urllib3.exceptions.ProtocolError(
                    f"Incomplete object: received {len(data)} of {expected_length} bytes"
                )
            return data
        finally:
            try:
                response.close()
            finally:
                response.release_conn()

    return retry_storage_operation(
        read_complete_object, label=f"Tai file /{bucket}/{object_name}",
    )


def list_object_files(client, bucket: str, prefix: str) -> list:
    # list_objects is lazy; materialize inside the retry to include page reads.
    return retry_storage_operation(
        lambda: list(client.list_objects(bucket, prefix=prefix, recursive=True)),
        label=f"Liet ke file /{bucket}/{prefix}",
    )


def ensure_storage_bucket(client, bucket: str) -> None:
    if not retry_storage_operation(
        lambda: client.bucket_exists(bucket), label=f"Kiem tra bucket {bucket}",
    ):
        retry_storage_operation(
            lambda: client.make_bucket(bucket), label=f"Tao bucket {bucket}",
        )

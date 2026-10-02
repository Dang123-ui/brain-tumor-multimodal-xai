import http.client
import ssl
import unittest
from unittest.mock import Mock, patch

import urllib3
from minio.error import S3Error, ServerError

from storage_io import (
    StorageTransferError, build_storage_http_client, list_object_files,
    read_object_bytes, retry_storage_operation,
)


def response(data=b"complete", *, error=None, length=None):
    result = Mock()
    result.headers = {"Content-Length": str(len(data) if length is None else length)}
    result.read.return_value = data
    result.read.side_effect = error
    return result


class StorageTransferTests(unittest.TestCase):
    def setUp(self):
        sleep_patch = patch("storage_io.time.sleep")
        self.sleep = sleep_patch.start()
        self.addCleanup(sleep_patch.stop)
        self.client = Mock()

    def test_interrupted_body_is_discarded_and_download_is_reopened(self):
        interrupted = response(error=http.client.IncompleteRead(b"partial", 6))
        complete = response()
        self.client.get_object.side_effect = [interrupted, complete]

        self.assertEqual(read_object_bytes(self.client, "data", "rna.csv"), b"complete")
        self.assertEqual(self.client.get_object.call_count, 2)
        for stream in (interrupted, complete):
            stream.close.assert_called_once()
            stream.release_conn.assert_called_once()

    def test_silent_short_body_is_not_passed_to_pipeline(self):
        short = response(b"part", length=8)
        complete = response()
        self.client.get_object.side_effect = [short, complete]

        self.assertEqual(read_object_bytes(self.client, "data", "mri.png"), b"complete")
        self.assertEqual(self.client.get_object.call_count, 2)
        short.close.assert_called_once()
        short.release_conn.assert_called_once()

    def test_handshake_failure_is_retried_before_reading(self):
        self.client.get_object.side_effect = [ssl.SSLEOFError("EOF"), response()]

        self.assertEqual(read_object_bytes(self.client, "data", "wsi.png"), b"complete")
        self.assertEqual(self.client.get_object.call_count, 2)

    def test_persistent_read_failure_stops_after_three_attempts(self):
        streams = [response(error=urllib3.exceptions.ReadTimeoutError(None, "/rna.csv", "timeout")) for _ in range(3)]
        self.client.get_object.side_effect = streams

        with self.assertRaisesRegex(StorageTransferError, r"/data/rna.csv.*3 lan thu"):
            read_object_bytes(self.client, "data", "rna.csv")
        self.assertEqual(self.client.get_object.call_count, 3)
        self.assertEqual(self.sleep.call_count, 2)
        for stream in streams:
            stream.close.assert_called_once()
            stream.release_conn.assert_called_once()

    def test_missing_object_and_access_denied_are_not_retried(self):
        for code in ("NoSuchKey", "AccessDenied"):
            with self.subTest(code=code):
                self.client.reset_mock()
                error = S3Error(code, "permanent", "/data/mri.png", "request", "host", None)
                self.client.get_object.side_effect = error
                with self.assertRaises(S3Error) as raised:
                    read_object_bytes(self.client, "data", "mri.png")
                self.assertIs(raised.exception, error)
                self.client.get_object.assert_called_once()
        self.sleep.assert_not_called()

    def test_response_without_content_length_can_be_read(self):
        stream = response()
        stream.headers = {}
        self.client.get_object.return_value = stream

        self.assertEqual(read_object_bytes(self.client, "data", "mri.png"), b"complete")

    def test_interrupted_paginated_listing_restarts_without_duplicates(self):
        def interrupted_listing():
            yield "first-tile"
            raise urllib3.exceptions.ProtocolError("interrupted listing")

        self.client.list_objects.side_effect = [interrupted_listing(), iter(["first-tile", "second-tile"])]

        self.assertEqual(list_object_files(self.client, "data", "wsi/"), ["first-tile", "second-tile"])
        self.assertEqual(self.client.list_objects.call_count, 2)

    def test_transient_server_error_retries_same_upload(self):
        operation = Mock(side_effect=[ServerError("unavailable", 503), "uploaded"])

        self.assertEqual(retry_storage_operation(operation, label="Upload result"), "uploaded")
        self.assertEqual(operation.call_count, 2)

    def test_local_file_error_is_not_treated_as_network_failure(self):
        operation = Mock(side_effect=FileNotFoundError("missing result file"))

        with self.assertRaises(FileNotFoundError):
            retry_storage_operation(operation, label="Upload result")
        operation.assert_called_once()
        self.sleep.assert_not_called()

    def test_pipeline_http_client_has_bounded_timeouts_and_no_nested_retries(self):
        pool = build_storage_http_client()
        timeout = pool.connection_pool_kw["timeout"]

        self.assertEqual(timeout.connect_timeout, 10)
        self.assertEqual(timeout.read_timeout, 30)
        self.assertEqual(pool.connection_pool_kw["retries"].total, 0)


if __name__ == "__main__":
    unittest.main()

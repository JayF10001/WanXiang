from __future__ import annotations

import unittest

from qq_adapter.utils.signature import build_callback_response, verify_qq_signature


class SignatureTestCase(unittest.TestCase):
    def test_build_callback_response(self) -> None:
        result = build_callback_response(event_ts="1750407202", plain_token="token-123", app_secret="a" * 32)
        self.assertEqual(result["plain_token"], "token-123")
        self.assertTrue(result["signature"])

    def test_verify_qq_signature(self) -> None:
        timestamp = "1750407202"
        body = b'{"op":13}'
        secret = "b" * 32
        signed = build_callback_response(event_ts=timestamp, plain_token=body.decode("utf-8"), app_secret=secret)
        self.assertTrue(
            verify_qq_signature(
                timestamp=timestamp,
                body=body,
                app_secret=secret,
                provided_signature=str(signed["signature"]),
            )
        )


if __name__ == "__main__":
    unittest.main()

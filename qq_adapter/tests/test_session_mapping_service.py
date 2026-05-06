from __future__ import annotations

from datetime import UTC, datetime, timedelta
import unittest

from qq_adapter.services.session_mapping_service import SessionBinding, SessionMappingService


class SessionMappingServiceTestCase(unittest.TestCase):
    def test_bind_and_get_session(self) -> None:
        service = SessionMappingService()
        service.bind_session(qq_user_id="user-1", session_id="session-1")
        self.assertEqual(service.get_session_id(qq_user_id="user-1"), "session-1")

    def test_expired_session_is_removed(self) -> None:
        service = SessionMappingService()
        service._store["user-1"] = SessionBinding(
            session_id="session-1",
            updated_at=datetime.now(UTC) - timedelta(days=1),
        )
        self.assertIsNone(service.get_session_id(qq_user_id="user-1"))
        self.assertNotIn("user-1", service._store)


if __name__ == "__main__":
    unittest.main()

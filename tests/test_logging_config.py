from __future__ import annotations

import unittest

from config.logging_config import SafeConsoleStreamHandler, logger


class TestLoggingConfig(unittest.TestCase):
    def test_has_safe_console_handler(self) -> None:
        self.assertTrue(any(isinstance(h, SafeConsoleStreamHandler) for h in logger.handlers))

    def test_file_handler_uses_utf8(self) -> None:
        file_handlers = [h for h in logger.handlers if hasattr(h, "encoding")]
        self.assertTrue(any(str(getattr(h, "encoding", "")).lower() == "utf-8" for h in file_handlers))


if __name__ == "__main__":
    unittest.main()


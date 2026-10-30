# © 2026 Bryan Gil — github.com/Bryanhackz — br4yangil006@gmail.com
"""Tests for run.py: config validation propagates before server boot."""

from __future__ import annotations

import os
import unittest
from unittest import mock

from run import main


class TestRunMain(unittest.TestCase):
    """Behavior of the entry point on invalid config."""

    def test_main_raises_on_invalid_env(self) -> None:
        """main() propagates ValueError from load_config on bad env."""
        with mock.patch.dict(os.environ, {"SMB_PORT": "abc"}, clear=True):
            with self.assertRaises(ValueError):
                main()

    def test_main_raises_on_zero_port(self) -> None:
        """Zero is below the minimum; main() must raise before binding."""
        with mock.patch.dict(os.environ, {"SMB_PORT": "0"}, clear=True):
            with self.assertRaises(ValueError):
                main()


if __name__ == "__main__":
    unittest.main()
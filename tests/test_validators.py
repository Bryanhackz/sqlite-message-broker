# © 2026 Bryan Gil — github.com/Bryanhackz — br4yangil006@gmail.com
"""Unit tests for src.validators: allowlist regex, length caps, closed role set."""

from __future__ import annotations

import unittest

from src.validators import (
    ValidationError,
    validate_body,
    validate_label,
    validate_queue_name,
    validate_role,
)


class TestQueueName(unittest.TestCase):
    """Queue names must match [a-z0-9][a-z0-9_-]{0,63}."""

    def test_valid_names(self) -> None:
        for name in ("q", "orders", "orders-v2", "orders_v2", "a1"):
            self.assertEqual(validate_queue_name(name), name, name)

    def test_rejects_uppercase(self) -> None:
        with self.assertRaises(ValidationError):
            validate_queue_name("Orders")

    def test_rejects_leading_dash(self) -> None:
        with self.assertRaises(ValidationError):
            validate_queue_name("-orders")

    def test_rejects_path_traversal(self) -> None:
        with self.assertRaises(ValidationError):
            validate_queue_name("../etc")

    def test_rejects_too_long(self) -> None:
        with self.assertRaises(ValidationError):
            validate_queue_name("a" * 65)


class TestLabel(unittest.TestCase):
    """Labels are free-text identifiers used to reference API keys."""

    def test_valid(self) -> None:
        self.assertEqual(validate_label("prod-1"), "prod-1")

    def test_rejects_empty(self) -> None:
        with self.assertRaises(ValidationError):
            validate_label("")

    def test_rejects_spaces(self) -> None:
        with self.assertRaises(ValidationError):
            validate_label("a b")


class TestBody(unittest.TestCase):
    """Payloads are opaque strings capped at 64 KiB UTF-8."""

    def test_within_limit(self) -> None:
        self.assertEqual(validate_body("x" * 100), "x" * 100)

    def test_over_limit(self) -> None:
        with self.assertRaises(ValidationError):
            validate_body("x" * (64 * 1024 + 1))

    def test_rejects_non_string(self) -> None:
        with self.assertRaises(ValidationError):
            validate_body(123)  # type: ignore[arg-type]


class TestRole(unittest.TestCase):
    """Roles are a closed set: producer | consumer | admin."""

    def test_valid(self) -> None:
        for r in ("producer", "consumer", "admin"):
            self.assertEqual(validate_role(r), r)

    def test_rejects_unknown(self) -> None:
        with self.assertRaises(ValidationError):
            validate_role("superuser")


if __name__ == "__main__":
    unittest.main()
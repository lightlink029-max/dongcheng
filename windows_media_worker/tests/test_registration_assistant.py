import unittest

from registration_assistant import EnvironmentMismatch, validate_environment


class RegistrationEnvironmentTests(unittest.TestCase):
    def test_exact_environment_passes(self):
        actual = {"ip": "203.0.113.7", "country": "US", "timezone": "America/New_York"}
        validate_environment(actual, dict(actual))

    def test_mismatch_stops_before_registration(self):
        actual = {"ip": "203.0.113.8", "country": "CN", "timezone": "Asia/Shanghai"}
        with self.assertRaises(EnvironmentMismatch) as raised:
            validate_environment(actual, {
                "ip": "203.0.113.7", "country": "US", "timezone": "America/New_York",
            })
        self.assertEqual(raised.exception.actual, actual)
        self.assertIn("IP", str(raised.exception))
        self.assertIn("国家", str(raised.exception))
        self.assertIn("时区", str(raised.exception))


if __name__ == "__main__":
    unittest.main()

import os
import unittest
from unittest.mock import patch

from fastapi import HTTPException

from app.security import require_demo_key


class DemoKeyTests(unittest.TestCase):
    def test_passes_when_no_key_is_configured(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("DEMO_KEY", None)
            self.assertIsNone(require_demo_key(None))
            self.assertIsNone(require_demo_key("anything"))

    def test_rejects_missing_or_wrong_key(self):
        with patch.dict(os.environ, {"DEMO_KEY": "secret"}):
            for given in (None, "", "wrong"):
                with self.assertRaises(HTTPException) as ctx:
                    require_demo_key(given)
                self.assertEqual(ctx.exception.status_code, 401)

    def test_accepts_the_right_key(self):
        with patch.dict(os.environ, {"DEMO_KEY": "secret"}):
            self.assertIsNone(require_demo_key("secret"))


if __name__ == "__main__":
    unittest.main()

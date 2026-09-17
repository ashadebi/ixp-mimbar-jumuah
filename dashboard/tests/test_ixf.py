import unittest, sys, os
sys.path.insert(0, os.path.dirname(__file__))
from test_app import ApplicationTests

class TestIXF(ApplicationTests):
    def test_ixf_export(self):
        status, data, _ = self.request("/ixf.json")
        self.assertEqual(status, 200)
        self.assertEqual(data["version"], "1.0")
        self.assertIn("ixp_list", data)

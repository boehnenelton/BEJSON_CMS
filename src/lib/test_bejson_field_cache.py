"""
Test:         test_bejson_field_cache.py
Description:  Unit tests for the Field Map Cache in lib_bejson_core.py.
"""
import sys
import os
import unittest

# Add library path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'Core')))
from lib_bejson_core import bejson_core_get_field_index, bejson_core_get_field_map

class TestFieldCache(unittest.TestCase):
    def test_cache_lookup(self):
        doc = {
            "Format_Version": "104",
            "Fields": [{"name": "id"}, {"name": "name"}, {"name": "value"}],
            "Values": []
        }
        
        # First call (Builds cache)
        idx = bejson_core_get_field_index(doc, "name")
        self.assertEqual(idx, 1)
        
        # Second call (Uses cache)
        idx2 = bejson_core_get_field_index(doc, "value")
        self.assertEqual(idx2, 2)
        
        # Third call (Field not found)
        idx3 = bejson_core_get_field_index(doc, "missing")
        self.assertEqual(idx3, -1)

    def test_cache_collission_safety(self):
        doc1 = {"Format_Version": "104", "Fields": [{"name": "a"}, {"name": "b"}]}
        doc2 = {"Format_Version": "104", "Fields": [{"name": "b"}, {"name": "a"}]}
        
        self.assertEqual(bejson_core_get_field_index(doc1, "a"), 0)
        self.assertEqual(bejson_core_get_field_index(doc2, "a"), 1)

if __name__ == '__main__':
    unittest.main()

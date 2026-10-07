"""Regression tests for issues found in code review."""

import unittest

from helpers import IsolatedHome

from resuskill_core import checklist


class ChecklistMatchingTests(unittest.TestCase):
    def test_degree_field_needs_whole_words(self):
        self.assertFalse(checklist._field_matches("Economics", ["CS"]))
        self.assertFalse(checklist._field_matches("Art", ["Computer Science and Artificial Intelligence"]))
        self.assertTrue(checklist._field_matches("Computer Science", ["Computer Science"]))
        self.assertTrue(checklist._field_matches("Computer Science and Engineering", ["Computer Science"]))

    def test_location_needs_whole_words(self):
        prof = {"preferences": {"locations": ["US"]}, "contact": {"location": "New York, NY"}}
        self.assertEqual(checklist._location({"locations": ["Australia"]}, prof)[0], checklist.UNKNOWN)
        self.assertEqual(checklist._location({"locations": ["Germany"]}, prof)[0], checklist.UNKNOWN)
        self.assertEqual(checklist._location({"locations": ["New York"]}, prof)[0], checklist.MET)

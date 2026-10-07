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

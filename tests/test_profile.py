import copy

from helpers import IsolatedHome, fixture

from resuskill_core import profile
from resuskill_core.util import ResuError


class ProfileTests(IsolatedHome):
    def test_save_assigns_stable_ids_and_revision(self):
        saved, changes, _ = profile.save(fixture("profile.json"))
        self.assertEqual(saved["_meta"]["revision"], 1)
        self.assertEqual(saved["experience"][0]["id"], "exp-1")
        self.assertEqual([b["id"] for b in saved["experience"][0]["bullets"]], ["exp-1-b1", "exp-1-b2", "exp-1-b3"])
        self.assertTrue(changes)

    def test_edit_preserves_ids_and_never_reuses_deleted_ones(self):
        saved, _, _ = profile.save(fixture("profile.json"))
        edited = copy.deepcopy(saved)
        bullets = edited["experience"][0]["bullets"]
        edited["experience"][0]["bullets"] = [{"text": bullets[1]["text"]}, {"text": "Mentored a new intern"}]
        again, changes, _ = profile.save(edited)
        ids = [b["id"] for b in again["experience"][0]["bullets"]]
        self.assertEqual(ids, ["exp-1-b2", "exp-1-b4"])
        self.assertEqual(again["_meta"]["revision"], 2)
        self.assertTrue(any(line.startswith("- exp-1-b1") for line in changes))

    def test_unchanged_save_keeps_revision(self):
        saved, _, _ = profile.save(fixture("profile.json"))
        again, changes, _ = profile.save(copy.deepcopy(saved))
        self.assertEqual(changes, [])
        self.assertEqual(again["_meta"]["revision"], 1)

    def test_previous_revision_is_archived(self):
        from resuskill_core import store

        saved, _, _ = profile.save(fixture("profile.json"))
        edited = copy.deepcopy(saved)
        edited["summary"] = "Changed summary."
        profile.save(edited)
        self.assertTrue((store.history_dir() / "profile-r1.json").exists())

    def test_invalid_profile_is_rejected_without_saving(self):
        bad = fixture("profile.json")
        bad["contact"]["name"] = ""
        bad["experience"][0]["start"] = "June 2024"
        with self.assertRaises(ResuError) as ctx:
            profile.save(bad)
        self.assertTrue(any("contact.name" in d for d in ctx.exception.details))
        self.assertTrue(any("start" in d for d in ctx.exception.details))
        self.assertIsNone(profile.load(required=False))

    def test_authorization_unknown_stays_null(self):
        data = fixture("profile.json")
        data["authorization"] = [{"country": "ca"}]
        saved, _, _ = profile.save(data)
        self.assertEqual(saved["authorization"], [{"country": "CA", "authorized": None, "requires_sponsorship": None}])

    def test_skill_in_both_lists_is_rejected(self):
        data = fixture("profile.json")
        data["skills_absent"] = ["python"]
        with self.assertRaises(ResuError):
            profile.save(data)

import json
import subprocess
import sys

from helpers import IsolatedHome, ROOT

from resuskill_core import jobs, repos
from resuskill_core.util import ResuError


def repo(name, **fields):
    data = {"name": name, "html_url": f"https://github.com/jordan-example/{name}", "description": None,
            "language": None, "topics": [], "fork": False, "archived": False, "size": 10,
            "stargazers_count": 0, "pushed_at": "2026-01-01T00:00:00Z"}
    data.update(fields)
    return data


class RepoRankingTests(IsolatedHome):
    def setUp(self):
        super().setUp()
        self.job_id = self.seed()

    def test_required_skills_rank_first_and_forks_and_empty_repos_are_excluded(self):
        result = repos.rank(self.job_id, [
            repo("notes", language="JavaScript"),
            repo("api", language="Python", description="REST service on PostgreSQL"),
            repo("forked", language="Python", fork=True),
            repo("blank", size=0),
        ])
        names = [c["name"] for c in result["candidates"]]
        self.assertEqual(names[0], "api")
        self.assertIn("Python", result["candidates"][0]["matches_job"])
        self.assertGreater(result["candidates"][0]["score"], result["candidates"][-1]["score"])
        self.assertEqual({e["name"]: e["reason"] for e in result["excluded"]},
                         {"forked": "fork of someone else's repository", "blank": "empty repository"})

    def test_readme_only_mentions_are_separate_and_weaker(self):
        result = repos.rank(self.job_id, [
            repo("described", description="Python and SQL reporting tool"),
            repo("mentioned", readme="This tool helps people apply to jobs asking for Python and SQL."),
        ])
        by_name = {c["name"]: c for c in result["candidates"]}
        self.assertEqual(by_name["mentioned"]["matches_job"], [])
        self.assertEqual(set(by_name["mentioned"]["readme_mentions_job"]), {"Python", "SQL"})
        self.assertGreater(by_name["described"]["score"], by_name["mentioned"]["score"])
        self.assertEqual(result["candidates"][0]["name"], "described")

    def test_marks_repos_already_in_profile(self):
        result = repos.rank(self.job_id, [repo("taskbot", html_url="https://www.github.com/Jordan-Example/TaskBot.git/")])
        self.assertEqual(result["candidates"][0]["in_profile"], "proj-1")

    def test_ties_break_by_most_recent_push(self):
        result = repos.rank(self.job_id, [repo("old", language="Python", pushed_at="2020-01-01T00:00:00Z"),
                                          repo("new", language="Python", pushed_at="2026-05-01T00:00:00Z")])
        self.assertEqual([c["name"] for c in result["candidates"]], ["new", "old"])

    def test_language_object_from_github_is_accepted(self):
        result = repos.rank(self.job_id, [repo("multi", languages={"Python": 900, "Shell": 10})])
        self.assertIn("Python", result["candidates"][0]["matches_job"])

    def test_custom_required_skill_matches_metadata_and_readme(self):
        job = jobs.add("Example", "UI engineer", "Qwik required.")
        jobs.set_requirements(job["id"], [{"text": "Qwik", "category": "skill", "importance": "required",
            "excerpt": "Qwik required.", "criterion": {"type": "skill", "skills": ["Qwik"], "match": "all"}}])
        result = repos.rank(job["id"], [repo("ui", description="Qwik user interface"),
                                      repo("notes", readme="Compare Qwik with other frameworks")])
        self.assertEqual(result["candidates"][0]["matches_job"], ["qwik"])
        self.assertEqual(result["candidates"][1]["readme_mentions_job"], ["qwik"])
        self.assertGreater(result["candidates"][0]["score"], result["candidates"][1]["score"])

    def test_lowercase_topics_match_without_weakening_prose_rules(self):
        job = jobs.add("Example", "UI engineer", "React required.")
        result = repos.rank(job["id"], [repo("tagged", topics=["react"]),
                                      repo("untagged", description="Let people react to messages")])
        self.assertEqual(result["candidates"][0]["matches_job"], ["React"])
        self.assertEqual(result["candidates"][1]["matches_job"], [])

    def test_readme_only_mentions_weigh_less_than_description_mentions(self):
        job = jobs.add("Example", "UI engineer", "JavaScript preferred.")
        result = repos.rank(job["id"], [repo("description", description="JavaScript utility"),
                                      repo("readme", readme="An example using JavaScript")])
        by_name = {c["name"]: c for c in result["candidates"]}
        self.assertGreater(by_name["description"]["score"], by_name["readme"]["score"])

    def test_malformed_languages_and_api_fields_are_rejected(self):
        invalid = [{"languages": [{"notes": "SQL"}]}, {"languages": [None]}, {"languages": [""]},
                   {"languages": {"Python": True}}, {"languages": {"Python": -1}},
                   {"languages": {"Python": "900"}}, {"languages": {"": 0}},
                   {"fork": "false"}, {"archived": 0}, {"size": False}, {"stargazers_count": -1}]
        for fields in invalid:
            with self.subTest(fields=fields), self.assertRaises(ResuError):
                repos.rank(self.job_id, [repo("malformed", **fields)])

    def test_invalid_input_is_rejected_with_paths(self):
        for bad in ({"name": "x"}, [{"name": "x"}], [repo("x", topics="python")], ["text"]):
            with self.subTest(bad=bad), self.assertRaises(ResuError):
                repos.rank(self.job_id, bad)

    def test_nothing_is_stored(self):
        from resuskill_core import profile
        before = profile.load()
        repos.rank(self.job_id, [repo("api", language="Python")])
        self.assertEqual(profile.load(), before)

    def test_cli(self):
        script = str(ROOT / "skills/resuskill/scripts/resuskill.py")
        data = json.dumps([repo("api", language="Python", readme="Uses Kafka in an example")])
        run = subprocess.run([sys.executable, script, "job", "repos", self.job_id, "--file", "-"],
                             input=data, text=True, encoding="utf-8", capture_output=True)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertIn("api (not in profile)", run.stdout)
        self.assertIn("README mentions (check context)", run.stdout)
        bad = subprocess.run([sys.executable, script, "job", "repos", self.job_id, "--file", "-"],
                             input="{}", text=True, encoding="utf-8", capture_output=True)
        self.assertEqual(bad.returncode, 1)

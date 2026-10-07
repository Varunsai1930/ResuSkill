"""Skill normalization, the alias map and the technology lexicon used by validation.

Matching is deliberately simple and explicit: case folding plus a small alias map.
Terms that are also ordinary English words (Go, R, C, React, Spring, Swift ...) only
match with their exact capitalization.
"""

from __future__ import annotations

import re
from functools import lru_cache

from .util import norm_text

# canonical name -> extra spellings. The canonical name is also a spelling.
ALIASES: dict[str, list[str]] = {
    "JavaScript": ["js", "javascript", "ecmascript", "es6"],
    "TypeScript": ["ts", "typescript"],
    "Python": ["python3"],
    "Go": ["golang"],
    "C++": ["cpp", "c plus plus"],
    "C#": ["c sharp", "csharp"],
    "Node.js": ["nodejs", "node js"],
    "React": ["react.js", "reactjs", "react js"],
    "React Native": ["react-native"],
    "Next.js": ["nextjs", "next js"],
    "Vue": ["vue.js", "vuejs"],
    "Angular": ["angularjs", "angular.js"],
    "Express": ["express.js", "expressjs"],
    "PostgreSQL": ["postgres", "postgre", "psql"],
    "MongoDB": ["mongo"],
    "Kubernetes": ["k8s"],
    "Amazon Web Services": ["aws"],
    "Google Cloud": ["gcp", "google cloud platform"],
    "Microsoft Azure": ["azure"],
    "scikit-learn": ["sklearn", "scikit learn"],
    "TensorFlow": ["tensorflow", "tf2"],
    "PyTorch": ["torch"],
    "Machine Learning": ["ml"],
    "Natural Language Processing": ["nlp"],
        "Continuous Integration": ["ci/cd", "ci", "cicd"],
    "Power BI": ["powerbi"],
    "GitHub Actions": ["gh actions"],
    "Hugging Face": ["huggingface", "hugging face transformers"],
    ".NET": ["dotnet", "dot net"],
    "Objective-C": ["objective c", "objc"],
    "Elasticsearch": ["elastic search"],
    "REST": ["rest api", "restful", "rest apis", "restful apis"],
    "SQL": ["structured query language"],
    "NoSQL": ["no-sql"],
    "Ruby on Rails": ["Rails"],
    "Spring Boot": ["springboot"],
}

# Technologies recognised in free text even when absent from the profile.
LEXICON: list[str] = [
    "Python", "Java", "JavaScript", "TypeScript", "Go", "Rust", "C", "C++", "C#", "R",
    "Ruby", "PHP", "Perl", "Kotlin", "Swift", "Objective-C", "Scala", "Dart", "Julia",
    "MATLAB", "Haskell", "Elixir", "Erlang", "Clojure", "Lua", "Solidity", "Bash",
    "PowerShell", "SQL", "NoSQL", "HTML", "CSS", "Sass", "GraphQL", "REST", "gRPC",
    "React", "React Native", "Next.js", "Vue", "Angular", "Svelte", "Redux", "jQuery",
    "Tailwind", "Bootstrap", "Node.js", "Express", "Django", "Flask", "FastAPI",
    "Spring", "Spring Boot", ".NET", "ASP.NET", "Laravel", "Ruby on Rails", "Flutter",
    "Android", "iOS", "Unity", "Unreal", "PostgreSQL", "MySQL", "SQLite", "MongoDB",
    "Redis", "DynamoDB", "Cassandra", "Elasticsearch", "Snowflake", "BigQuery",
    "Firebase", "Supabase", "Kafka", "RabbitMQ", "Celery", "Spark", "Hadoop",
    "Airflow", "dbt", "Tableau", "Power BI", "Looker", "Excel", "Docker", "Kubernetes",
    "Helm", "Terraform", "Ansible", "Jenkins", "GitHub Actions", "GitLab", "CircleCI",
    "Prometheus", "Grafana", "Nginx", "Linux", "Git", "Amazon Web Services",
    "Google Cloud", "Microsoft Azure", "Lambda", "S3", "EC2", "Heroku", "Vercel",
    "Netlify", "TensorFlow", "PyTorch", "Keras", "scikit-learn", "pandas", "NumPy",
    "SciPy", "OpenCV", "Hugging Face", "LangChain", "Selenium", "Playwright",
    "Cypress", "Jest", "pytest", "JUnit", "Webpack", "Vite", "Figma", "Jira",
    "Postman", "Machine Learning", "Natural Language Processing", "Computer Vision",
    "Continuous Integration",
]

# Spellings that must match with exact case because they are also common words.
CASE_SENSITIVE: set[str] = {
    "Go", "R", "C", "Rust", "Swift", "Spring", "React", "Express", "Spark", "Lambda",
    "Unity", "Excel", "Dart", "Julia", "Lua", "Helm", "Snowflake", "Looker", "Vite",
    "Jest", "REST", "Rails", "CV", "CI", "TS", "JS", "ML", "Unreal", "Git", "Celery",
    "Angular", "Flutter", "Keras", "Bootstrap", "Tailwind", "Svelte", "Redux",
}


def norm_skill(name: str) -> str:
    text = norm_text(name).rstrip(".")
    return re.sub(r"\s+", " ", text)


@lru_cache(maxsize=None)
def _alias_index() -> dict[str, str]:
    index: dict[str, str] = {}
    for canon, spellings in ALIASES.items():
        index[norm_skill(canon)] = canon
        for spelling in spellings:
            index[norm_skill(spelling)] = canon
    for term in LEXICON:
        index.setdefault(norm_skill(term), term)
    return index


def canon(name: str) -> str:
    """Return the canonical comparison key for a skill name (case-folded)."""
    key = norm_skill(name)
    return norm_skill(_alias_index().get(key, name))


def display(name: str) -> str:
    return _alias_index().get(norm_skill(name), name.strip())


def _spelling_pattern(spelling: str, case_sensitive: bool) -> re.Pattern:
    body = re.escape(spelling).replace(r"\ ", r"[\s-]+")
    # Boundaries: not glued to letters/digits; '+', '#' and '.' count as part of a term.
    # '/' separates terms ("Python/Django", "C/C++"), so it is a boundary on both sides.
    pattern = rf"(?<![\w+#.&-]){body}(?![\w+#&]|-\w)"
    return re.compile(pattern, 0 if case_sensitive else re.IGNORECASE)


def _patterns_for(extra_terms: tuple[str, ...]) -> list[tuple[str, re.Pattern]]:
    entries: dict[str, set[str]] = {}
    for term in list(LEXICON) + list(extra_terms):
        key = canon(term)
        spellings = entries.setdefault(key, set())
        spellings.add(display(term))
        spellings.add(term.strip())
        for alias in ALIASES.get(display(term), []):
            spellings.add(alias)
    compiled: list[tuple[str, re.Pattern]] = []
    for key, spellings in entries.items():
        for spelling in sorted(spellings, key=len, reverse=True):
            if not spelling:
                continue
            case_sensitive = spelling in CASE_SENSITIVE or len(spelling) <= 2
            if case_sensitive and spelling.islower():
                # Short lowercase aliases (js, ts, ml, ci ...) only count as written in caps.
                spelling = spelling.upper()
            compiled.append((key, _spelling_pattern(spelling, case_sensitive)))
    return compiled


_PATTERN_CACHE: dict[tuple[str, ...], list[tuple[str, re.Pattern]]] = {}


def find_terms(text: str, extra_terms=()) -> set[str]:
    """Canonical keys of every known technology mentioned in ``text``."""
    key = tuple(sorted({t for t in extra_terms if t and t.strip()}))
    if key not in _PATTERN_CACHE:
        _PATTERN_CACHE[key] = _patterns_for(key)
    found: set[str] = set()
    for canon_key, pattern in _PATTERN_CACHE[key]:
        if canon_key not in found and pattern.search(text or ""):
            found.add(canon_key)
    return found

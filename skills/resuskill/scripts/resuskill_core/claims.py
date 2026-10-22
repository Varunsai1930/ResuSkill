"""Shared source checks for reviewed derivative writing; not a semantic truth test."""
from __future__ import annotations

from . import input_schema, ledger, profile, validate
from .util import ResuError, content_hash

SPEC = {'text': str, 'sources': [str]}


def shape(part):
    input_schema.check(part, SPEC, 'factual passage')
    text, ids = part.get('text'), part.get('sources')
    if not isinstance(text, str) or not text.strip() or not ids or len(ids) != len(set(ids)):
        raise ResuError('Each factual passage needs text and distinct source IDs.')


def review(parts, prof, job=None):
    index = profile.sources(prof)
    references = {}
    for part in parts:
        shape(part)
        text, ids = part['text'], part['sources']
        texts, techs = [], set()
        for ident in ids:
            if ident.startswith('pe') and ident[2:].isdigit():
                row = ledger.resolve([ident])[0]
                ev = row['evidence']
                ref = {'kind': 'project_evidence', 'citation': ev,
                       'source_fingerprint': row['source_fingerprint'], 'evidence_fingerprint': row['evidence_fingerprint']}
                # Code facts alone do not establish personal contribution or impact.
                texts.extend([ev['observed_fact'], ev['contribution'], ev['outcome']])
            else:
                if ident not in index:
                    raise ResuError('Unknown factual source: ' + ident)
                ref = index[ident]
                texts.append(ref['text'])
                techs.update(validate.canon(t) for t in ref.get('technologies', []))
            references[ident] = ref
        problems = validate.claim_problems(text, texts, techs, validate.detection_terms(prof, job))
        if problems:
            raise ResuError('Factual passage failed source checks.', problems)
    return references


def fingerprint(content, references, context=None):
    return content_hash({'content': content, 'references': references, 'context': context})

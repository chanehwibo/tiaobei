"""Optional lexical evidence coverage, not semantic entailment or authorization."""
from __future__ import annotations

import re


POLICIES = ("similarity", "content_coverage_v1")
MIN_COVERAGE = 0.5
PARTS = re.compile(r"[a-z0-9_]+|[\u3400-\u9fff]+")
CJK = re.compile(r"[\u3400-\u9fff]+")
# Question scaffolding is not evidence. Negation and operational terms remain.
QUESTION_WORDS = re.compile(
    r"\u662f\u4ec0\u4e48|\u4ec0\u4e48|\u54ea\u4e9b|\u5982\u4f55|\u600e\u4e48|"
    r"\u600e\u6837|\u591a\u5c11|\u591a\u4e45|\u80fd\u5426|\u662f\u5426|"
    r"\u8bf7\u95ee|\u67e5\u8be2|\u8bf7\u67e5|\u6211\u9700\u8981|\u54ea\u4e2a|\u54ea\u4efd|"
    r"\b(?:what|which|how|where|when|please|the|a|an|is|are|of|for|to|and)\b"
)
PARTICLES = frozenset("\u7684\u4e86\u5728\u548c\u4e0e\u53ca\u5e76\u4e8e\u5417\u5462")


def _features(text):
    words, pairs = set(), set()
    for match in PARTS.finditer(text):
        part = match[0]
        if CJK.fullmatch(part):
            pairs.update(part[index:index + 2] for index in range(len(part) - 1))
        else:
            words.add(part)
    return words, pairs


def content_coverage(query, documents, *, constraints=()):
    """Measure the returned set's coverage after discounting its common title.

    Inputs are normalized text, never tags or relevance labels. Complementary
    documents may jointly cover a query. Shared title words alone cannot answer
    an additional relationship question. No query/document text is cached.
    """
    if not documents:
        return 0.0
    for _term, pattern in constraints:
        query = pattern.sub(" ", query)
    query = QUESTION_WORDS.sub(" ", query)
    titles = [_features(title) for title, _content in documents]
    common_words = set.intersection(*(row[0] for row in titles))
    common_pairs = set.intersection(*(row[1] for row in titles))
    words, pairs = set(), set()
    for title, content in documents:
        for text in (title, content):
            text_words, text_pairs = _features(text)
            words.update(text_words)
            pairs.update(text_pairs)
    supported = total = title_only = 0
    for match in PARTS.finditer(query):
        part = match[0]
        if not CJK.fullmatch(part):
            if part in common_words:
                title_only += 1
                continue
            total += 1
            supported += part in words
            continue
        background, covered = set(), set()
        for index in range(len(part) - 1):
            pair = part[index:index + 2]
            if pair in common_pairs:
                background.update((index, index + 1))
            if pair in pairs:
                covered.update((index, index + 1))
        for index, character in enumerate(part):
            if character in PARTICLES:
                continue
            if index in background:
                title_only += 1
                continue
            total += 1
            supported += index in covered
    # A title lookup remains possible, but a content-free question is not a hit.
    return supported / total if total else float(bool(title_only))

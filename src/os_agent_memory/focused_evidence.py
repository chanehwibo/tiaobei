"""Query-focused lexical support and bounded, same-subject evidence bundles.

This is a transparent retrieval heuristic, not a semantic entailment model.
Neither relevance labels, record IDs, tags nor source IDs participate in it.
"""
from __future__ import annotations

from collections import defaultdict
import re

from .retrieval_evidence import MIN_COVERAGE, PARTICLES, PARTS, CJK, QUESTION_WORDS, _features


POLICY = "focused_evidence_v2"
FOCUS_CUE = re.compile(
    r"\u6211(?:\u53ea)?(?:\u67e5\u8be2|\u9700\u8981)|"
    r"(?:\u672c\u6b21|\u8fd9\u6b21)(?:\u53ea)?(?:\u67e5\u8be2|\u67e5)|\u8bf7\u67e5"
)
INTERROGATIVE = re.compile(
    r"\u4ec0\u4e48|\u5982\u4f55|\u600e\u6837|\u600e\u4e48|\u54ea|\u8c01|"
    r"\u591a\u5c11|\u591a\u4e45|\u80fd\u5426|\u662f\u5426|[?\uff1f]|"
    r"\b(?:what|which|how|where|when|why)\b"
)
SCAFFOLDING = re.compile(
    r"\u5e94\u8be5|\u5e94\u5f53|\u53ef\u4ee5|\u9700\u8981|\u54ea\u4f4d|"
    r"\u51e0\u6b21|\u7531\u8c01|\u901a\u77e5\u8c01|"
    r"\b(?:should|can|could|would|be|been|it|its|does|do|did)\b"
)
FUNCTION_CHARACTERS = PARTICLES | frozenset("\u6211\u4f60\u4ed6\u5b83\u8fd9\u90a3\u4e5f\u90fd\u5c31\u53ea\u518d\u53c8\u800c")
ROLE_DESCRIPTION = re.compile(r"\u8d1f\u8d23([^,\uff0c;\uff1b\u3002]+?)\u7684(?:\u540c\u4e8b|\u4eba\u5458)")
HOW = re.compile(r"\u5982\u4f55|\u600e\u6837|\u600e\u4e48|\u54ea\u4f4d")
SECTION_SUFFIX = re.compile(
    r"(?:\u64cd\u4f5c\u6d41\u7a0b|\u6267\u884c\u6761\u4ef6|"
    r"\u6838\u9a8c\u4e0e\u56de\u9000|\u64cd\u4f5c\u8bf4\u660e|"
    r"\b(?:procedure|policy|instructions|requirements|verification|recovery))$"
)
CLAUSE = re.compile(r"[^,\uff0c;\uff1b\u3002!?\uff01\uff1f\n]+")
SCALAR_QUESTION = re.compile(
    r"\u662f\u4ec0\u4e48|\u662f\u591a\u5c11|\u662f\u54ea(?:\u4e00)?\u7248|\u662f\u8c01"
)
QUANTITY = re.compile(
    r"(?<![a-zA-Z0-9_.-])([\u96f6\u3007\u4e00\u4e8c\u4e24\u4e09\u56db\u4e94"
    r"\u516d\u4e03\u516b\u4e5d\u5341\u767e\u5343\u4e07]+)"
    r"(?=\u5206\u949f|\u5c0f\u65f6|\u79d2|\u5929|\u5468|\u4e2a\u6708|\u5e74|"
    r"\u5143|\u6b21|\u9875|\u6761|\u4efd|\u4eba)"
)
DIGITS = dict(zip("\u96f6\u3007\u4e00\u4e8c\u4e24\u4e09\u56db\u4e94\u516d\u4e03\u516b\u4e5d",
                  (0, 0, 1, 2, 2, 3, 4, 5, 6, 7, 8, 9)))
UNITS = dict(zip("\u5341\u767e\u5343\u4e07", (10, 100, 1000, 10000)))
PREREQUISITE_REQUEST = re.compile(
    r"\u6761\u4ef6|\u51c6\u5165|\u524d\u7f6e|"
    r"\u5148.+\u518d.+(?:\u6062\u590d|\u56de\u9000|\u56de\u6eda)|"
    r"\b(?:prerequisites|preconditions)\b"
)
PREREQUISITE_BODY = re.compile(
    r"\u6267\u884c\u6761\u4ef6|\u4ec5\u5728|\u53ea\u6709.+\u624d|"
    r"\b(?:only if|provided that|preconditions|prerequisites)\b"
)


def normalize_quantities(text: str) -> str:
    """Equate written Chinese quantities, not entity names or version strings."""
    def convert(match):
        value = match[1]
        if all(character in DIGITS for character in value):
            return "".join(str(DIGITS[character]) for character in value)
        total = section = digit = 0
        for character in value:
            if character in DIGITS:
                digit = DIGITS[character]
            elif UNITS[character] == 10000:
                total += (section + digit or 1) * 10000
                section = digit = 0
            else:
                section += (digit or 1) * UNITS[character]
                digit = 0
        return str(total + section + digit)
    return QUANTITY.sub(convert, text)


def query_focus(query: str) -> str:
    """Drop narrated background only when an explicit later request replaces it."""
    for cue in FOCUS_CUE.finditer(query):
        if not INTERROGATIVE.search(query[:cue.start()]):
            focused = query[cue.end():].strip()
            if focused:
                return focused
    return query


def support_focus(query: str) -> str:
    """Focus the requested operation, retaining all earlier interrogative clauses."""
    query = ROLE_DESCRIPTION.sub(r"\1", query)
    clauses = list(CLAUSE.finditer(query))
    if clauses:
        last = clauses[-1]
        if (INTERROGATIVE.search(last[0]) or last[0].endswith("\u5417")) and not INTERROGATIVE.search(query[:last.start()]):
            query = last[0]
    how = HOW.search(query)
    if how and not INTERROGATIVE.search(query[:how.start()]):
        remainder = query[how.start():]
        substantive = re.sub(r"\W", "", evidence_text(remainder))
        if len(substantive) >= 4 or (how[0] == "\u54ea\u4f4d" and len(substantive) >= 2):
            query = remainder
    return query


def evidence_text(query: str) -> str:
    query = SCAFFOLDING.sub(" ", QUESTION_WORDS.sub(" ", query))
    return "".join(" " if char in FUNCTION_CHARACTERS else char for char in query)


def body_passages(content: str):
    return (part.strip() for part in re.split(r"[\n\u3002\uff01\uff1f;\uff1b]|(?<=[.!?])\s+", content)
            if part.strip())


def subject_key(title: str) -> str:
    """Join sections by an exact subject, never fuzzy entity/version prefixes."""
    key = SECTION_SUFFIX.sub("", title.strip(" .\u3002:")).strip()
    if len(re.sub(r"\W", "", key)) < 4:
        return ""
    return key


def answer_facets(query: str) -> list[str]:
    """Keep a requested scalar/property separate from an already-known premise."""
    facets = []
    for match in CLAUSE.finditer(query):
        clause = match[0]
        scalar = SCALAR_QUESTION.search(clause)
        if scalar:
            left = clause[:scalar.start()]
            # A possessive separates the subject/premise from its requested property.
            facet = left.rsplit("\u7684", 1)[-1].strip()
            if facet:
                facets.append(facet)
        elif "\u591a\u5c11" in clause:
            right = clause.split("\u591a\u5c11", 1)[1].strip()
            if len(right) >= 4:
                facets.append(right)
        elif "\u8c01" in clause and "\u7684" in clause:
            facets.append(clause.rsplit("\u7684", 1)[1])
    return facets


def support_coverage(query: str, documents, *, constraints=(), allow_characters=True) -> float:
    """Count only authorized title/body evidence; titles cannot prove a property.

    Character fallback tolerates Chinese word-boundary changes, but requires a
    nontrivial question and a shared adjacent pair outside the common title.
    English terms always use full word boundaries.
    """
    if not documents:
        return 0.0
    for _term, pattern in constraints:
        query = pattern.sub(" ", query)
    query = normalize_quantities(query)
    documents = [(title, normalize_quantities(content)) for title, content in documents]
    query = SCAFFOLDING.sub(" ", QUESTION_WORDS.sub(" ", query))
    titles = [_features(title) for title, _content in documents]
    common_words = set.intersection(*(row[0] for row in titles))
    common_pairs = set.intersection(*(row[1] for row in titles))
    words, pairs, characters = set(), set(), set()
    for title, content in documents:
        for text in (title, content):
            text_words, text_pairs = _features(text)
            words.update(text_words)
            pairs.update(text_pairs)
            characters.update("".join(CJK.findall(text)))
    total = strict = relaxed = title_only = substantive_pairs = 0
    for match in PARTS.finditer(query):
        part = match[0]
        if not CJK.fullmatch(part):
            if part in common_words:
                title_only += 1
            else:
                total += 1
                strict += part in words
                relaxed += part in words
            continue
        background, covered = set(), set()
        for index in range(len(part) - 1):
            pair = part[index:index + 2]
            if pair in common_pairs:
                background.update((index, index + 1))
            elif pair in pairs:
                substantive_pairs += 1
            if pair in pairs:
                covered.update((index, index + 1))
        for index, character in enumerate(part):
            if character in FUNCTION_CHARACTERS:
                continue
            if index in background:
                title_only += 1
                continue
            total += 1
            strict += index in covered
            relaxed += character in characters
    if not total:
        return float(bool(title_only))
    supported = strict
    if allow_characters and total >= 6 and substantive_pairs:
        supported = max(supported, relaxed)
    return supported / total


def bundle_supported(query: str, documents, *, constraints=()) -> bool:
    focused = support_focus(query)
    if max(support_coverage(query, documents, constraints=constraints),
           support_coverage(focused, documents, constraints=constraints)) < MIN_COVERAGE:
        return False
    for facet in answer_facets(focused):
        parts = PARTS.findall(evidence_text(facet))
        head = parts[-1][-2:] if parts and CJK.fullmatch(parts[-1]) else (parts[-1] if parts else "")
        # A property's words must coexist with its head in one body passage.
        # Unrelated sentences cannot establish the requested relationship.
        passages = [passage for _title, content in documents for passage in body_passages(content)]
        if not any(
            head in set.union(*_features(passage))
            and support_coverage(facet, [("", passage)], constraints=constraints,
                                 allow_characters=False) >= MIN_COVERAGE
            for passage in passages
        ):
            return False
    return True


def select_evidence(query, scored, *, top_k, min_score, constraints=(), normalize=str.lower, direct_details=None):
    """Gate direct seeds, then select complementary sections of an exact subject.

    A companion's score is the seed's bundle relevance, not its own similarity.
    Both the unmodified direct score and the propagation source are returned.
    Coverage is checked again on the actual returned set, never on omitted text.
    """
    groups = defaultdict(list)
    for row in scored:
        title = normalize(row[1].title)
        subject = subject_key(title)
        # Empty/generic titles are not edges between unrelated records.
        groups[("subject", subject) if subject else ("single", row[1].id)].append(row)
    def seed_rank(row):
        document_score = (direct_details or {}).get(row[1].id, {}).get("document_score", row[0])
        return (document_score < min_score, -document_score, -row[0], row[1].id)
    seeds = sorted((row for row in scored if row[0] >= min_score), key=seed_rank)
    seen = set()
    for seed in seeds:
        subject = subject_key(normalize(seed[1].title))
        key = ("subject", subject) if subject else ("single", seed[1].id)
        if key in seen:
            continue
        seen.add(key)
        remaining = [row for row in groups[key] if row[1].id != seed[1].id]
        selected = [seed]
        query_words, query_pairs = _features(evidence_text(support_focus(query.lower())))
        subject_words, subject_pairs = _features(subject)
        query_words -= subject_words
        query_pairs -= subject_pairs

        def contributions(row):
            words, pairs = _features(normalize_quantities(normalize(
                row[1].title + " " + row[1].content)))
            return {("word", word) for word in words & query_words} | {
                ("pair", pair) for pair in pairs & query_pairs}

        features = {row[1].id: contributions(row) for row in [seed, *remaining]}
        if PREREQUISITE_REQUEST.search(query.lower()):
            for row in [seed, *remaining]:
                if PREREQUISITE_BODY.search(normalize(row[1].title + " " + row[1].content)):
                    features[row[1].id].add(("role", "prerequisite"))
        covered = set(features[seed[1].id])
        while remaining and len(selected) < top_k:
            # Only new query evidence warrants a slot, not more unrelated prose.
            row = max(remaining, key=lambda value: (
                len(features[value[1].id] - covered),
                value[0], value[1].id,
            ))
            if not features[row[1].id] - covered:
                fields = [(normalize(value[1].title), normalize(value[1].content)) for value in selected]
                if bundle_supported(query.lower(), fields, constraints=constraints):
                    break
                # A not-yet-supported paraphrase may need neighboring context.
                # It still must pass the final returned-set check below.
                body_features = set().union(*(
                    set.union(*_features(normalize(value[1].content))) for value in selected))
                remaining = [value for value in remaining if
                             set.union(*_features(normalize(value[1].content))) - body_features]
                if not remaining:
                    break
                row = max(remaining, key=lambda value: (value[0], value[1].id))
            selected.append(row)
            covered.update(features[row[1].id])
            remaining.remove(row)
        documents = [(normalize(row[1].title), normalize(row[1].content)) for row in selected]
        if not bundle_supported(query.lower(), documents, constraints=constraints):
            continue
        info = {
            row[1].id: {"policy": POLICY, "direct_score": round(row[0], 4),
                        "origin": "direct" if row[1].id == seed[1].id else "subject_companion",
                        "seed_id": seed[1].id,
                        "coverage": round(support_coverage(support_focus(query.lower()), documents,
                                                          constraints=constraints), 4),
                        **{key: round(value, 4)
                           for key, value in (direct_details or {}).get(row[1].id, {}).items()}}
            for row in selected
        }
        return [(max(row[0], seed[0]), *row[1:]) for row in selected], info
    return [], {}

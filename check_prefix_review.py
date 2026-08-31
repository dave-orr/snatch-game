#!/usr/bin/env python3
"""
Check the prefix-matching review against the current etymology.json.

etymology.js matches two roots when one is a prefix of the other, but only
from MIN_PREFIX_MATCH_LENGTH letters up, because shorter roots start plenty of
unrelated words. Every pair the rule matches was reviewed by hand once; the
verdicts live in prefix_pair_review.json.

Rebuilding etymology.json changes the set of pairs, so run this afterwards. It
reports pairs that are new since the review - those are the only ones needing
a fresh look - and pairs that have disappeared. It also checks that the
unrelated pairs still agree with UNRELATED_PREFIX_PAIRS in etymology.js, so
the two cannot drift apart.

Usage:
    python check_prefix_review.py
"""

import json
import re
import unicodedata
from bisect import bisect_right
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).parent
ETYMOLOGY_PATH = HERE / 'etymology.json'
REVIEW_PATH = HERE / 'prefix_pair_review.json'
ETYMOLOGY_JS = HERE / 'etymology.js'


def normalize_root(root):
    """Match normalizeRoot in etymology.js."""
    stripped = ''.join(c for c in unicodedata.normalize('NFD', root.lower())
                       if not unicodedata.combining(c))
    return stripped.strip('-')


def prefix_pairs(etymology, min_length):
    """Every (language, shorter, longer) the prefix rule matches."""
    roots_by_language = defaultdict(set)
    for entries in etymology.values():
        for entry in entries:
            language, _, root = entry.partition(':')
            root = normalize_root(root)
            if len(root) >= 3:
                roots_by_language[language].add(root)

    pairs = set()
    for language, roots in roots_by_language.items():
        ordered = sorted(roots)
        for root in ordered:
            if len(root) < min_length:
                continue
            i = bisect_right(ordered, root)
            while i < len(ordered) and ordered[i].startswith(root):
                longer = ordered[i]
                # a root that is also a suffix already matched under the older
                # rule and was never part of this review
                if longer != root and not longer.endswith(root):
                    pairs.add((language, root, longer))
                i += 1
    return pairs


def js_exclusions():
    """The pairs etymology.js refuses to match."""
    source = ETYMOLOGY_JS.read_text(encoding='utf-8')
    block = re.search(r'UNRELATED_PREFIX_PAIRS = new Set\(\[(.*?)\]\)', source, re.DOTALL)
    if not block:
        raise SystemExit("could not find UNRELATED_PREFIX_PAIRS in etymology.js")
    found = set()
    for entry in re.findall(r"'([^']+)'", block.group(1)):
        language, _, roots = entry.partition(':')
        shorter, _, longer = roots.partition('|')
        found.add((language, shorter, longer))
    return found


def main():
    review = json.loads(REVIEW_PATH.read_text(encoding='utf-8'))
    etymology = json.loads(ETYMOLOGY_PATH.read_text(encoding='utf-8'))

    reviewed = {(lang, short, long_): related
                for lang, short, long_, related in review['pairs']}
    current = prefix_pairs(etymology, review['min_root_length'])

    unreviewed = sorted(current - set(reviewed))
    gone = sorted(set(reviewed) - current)
    unrelated = {pair for pair, related in reviewed.items() if not related}

    print(f"reviewed pairs: {len(reviewed)}  "
          f"({len(reviewed) - len(unrelated)} related, {len(unrelated)} not)")
    print(f"pairs in etymology.json now: {len(current)}")

    drift = unrelated ^ js_exclusions()
    if drift:
        print(f"\nMISMATCH: {len(drift)} pairs differ between this review and "
              f"UNRELATED_PREFIX_PAIRS in etymology.js:")
        for pair in sorted(drift):
            print(f"    {pair[0]}:{pair[1]} ~ {pair[2]}")
    else:
        print("etymology.js exclusions agree with the review")

    if gone:
        print(f"\n{len(gone)} reviewed pairs no longer occur (harmless):")
        for pair in gone[:10]:
            print(f"    {pair[0]}:{pair[1]} ~ {pair[2]}")

    if unreviewed:
        print(f"\n{len(unreviewed)} pairs are NOT yet reviewed. The prefix rule "
              f"is matching these without anyone having checked them:")
        for language, shorter, longer in unreviewed:
            print(f"    {language}:{shorter} ~ {longer}")
        print("\nCheck each, then add it to prefix_pair_review.json, and add any "
              "unrelated ones to UNRELATED_PREFIX_PAIRS in etymology.js.")
    else:
        print("\nEvery pair the rule matches has been reviewed.")

    return 1 if (unreviewed or drift) else 0


if __name__ == '__main__':
    raise SystemExit(main())

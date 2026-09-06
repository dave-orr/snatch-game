#!/usr/bin/env python3
"""
Expand etymology dictionary by propagating etymologies to inflected forms.

This script fills in gaps by checking if words without etymology
appear to be inflected forms of words that DO have etymology.

Only fills in blanks - never overwrites existing etymologies.

Every propagated entry is recorded in etymology_sources.json with the rule
that produced it and the base word it came from, so guesses can be audited
and distinguished from entries parsed out of Wiktionary. Words absent from
that file were not produced by this script.

The pipeline is build_etymology.py first, then this script. A parse
overwrites etymology.json with parsed entries only, so run this straight
after it with no flags, and delete a stale etymology_sources.json first.

--rebuild is for the other case: changing a rule here and re-expanding
without re-parsing. It drops every entry the provenance file lists, so
running it against fresh parse output would also drop a word the parse had
just produced legitimately.

Usage:
    python build_etymology.py <dump.xml.bz2>    # parse, then:
    python expand_inflections.py                # expand and save
    python expand_inflections.py --rebuild      # re-expand, dropping the
                                                # previous propagation first
    python expand_inflections.py --audit        # report what each rule would
                                                # do, with samples, saving nothing
"""

import argparse
import json
import random
from collections import Counter
from pathlib import Path

ETYMOLOGY_PATH = Path(__file__).parent / 'etymology.json'
SOURCES_PATH = Path(__file__).parent / 'etymology_sources.json'
LINKS_PATH = Path(__file__).parent / 'etymology_links.json'
DICTIONARY_URL = "https://raw.githubusercontent.com/redbo/scrabble/master/dictionary.txt"


# Suffixes to try stripping (order matters - try longer ones first)
SUFFIXES = [
    'OLOGICALLY', 'ISTICALLY', 'ICALLY',  # adverb forms
    'ISATION', 'IZATION',  # nominalizations
    'URISTS', 'OLOGISTS', 'ISTS',  # agent plurals
    'IVENESS', 'FULNESS', 'LESSNESS',  # noun forms
    'INESS',  # happiness
    'NESSES', 'MENTS', 'ABLES', 'IBLES',  # plurals of noun forms
    'NESS', 'MENT', 'ABLE', 'IBLE', 'TION', 'SION',
    'URIST', 'OLOGIST',  # agent nouns
    'LING', 'INGS', 'IEST', 'IERS',
    'LETS',  # diminutive plurals (PIGLETS)
    'ICAL', 'IVES', 'ISTS',  # adjective/noun forms
    'ING', 'IES', 'IER', 'IED', 'EST', 'ERS', 'ENS',
    'LET',  # diminutives (PIGLET)
    'ILY', 'IVE', 'IST', 'ISH', 'ISE', 'IZE',  # adjective/verb forms
    'LY', 'ED', 'ER', 'ES', 'EN', 'EY',
    'Y', 'S', 'D',
]

# Extra stem repairs that only make sense for particular suffixes.
# Each entry maps a suffix to strings appended to the stripped stem.
SUFFIX_REPAIRS = {
    'IES': ['Y'],           # PARTIES -> PARTY
    'IED': ['Y'],           # PARTIED -> PARTY
    'IER': ['Y'],           # HAPPIER -> HAPPY
    'IEST': ['Y'],          # HAPPIEST -> HAPPY
    'INESS': ['Y'],         # HAPPINESS -> HAPPY
    'ILY': ['Y'],           # FUNKILY -> FUNKY
    'IST': ['Y', 'O'],      # COLONIST -> COLONY, LIBRETTIST -> LIBRETTO
    'ISTS': ['Y', 'O'],     # COLONISTS -> COLONY
    'ICALLY': ['IC', 'ICAL'],       # HISTORICALLY -> HISTORIC
    'OLOGICALLY': ['OLOGY'],        # PHENOLOGICALLY -> PHENOLOGY
    'IVE': ['ATE', 'E'],            # CREATIVE -> CREATE
}

# Consonants that commonly double before suffixes
DOUBLE_CONSONANTS = set('BCDFGKLMNPRSTVZ')

# Derivational suffixes, as (suffix, replacements for the stripped stem).
# Unlike the inflectional suffixes above these do not get the general stem
# repairs, because a repair can beat the right answer to the punch: stripping
# -ATION off CREATION leaves CRE, and CRE + E is CREE, a covered word.
#
# Native English suffixes attach to short words freely (SEEP, TENT, WORM), so
# they are matched against bases of any length.
NATIVE_SUFFIXES = [
    ('LESSLY', ['']), ('LESS', ['']), ('LIKE', ['']),
    ('SHIPS', ['']), ('SHIP', ['']), ('HOODS', ['']), ('HOOD', ['']),
    ('DOMS', ['']), ('DOM', ['']), ('WARDS', ['']), ('WARD', ['']),
    ('WISE', ['']), ('MOST', ['']),
    ('FULLY', ['']), ('FULS', ['']), ('FUL', ['']),
    ('AGES', ['', 'E']), ('AGE', ['', 'E']),
]

# Latinate and Greek suffixes need a base of at least MIN_LATINATE_BASE
# letters. On shorter bases they are mostly coincidence rather than
# derivation - CHOREIC>CHORE, ATONIC>ATONE, LITHIC>LITHE, HOLISM>HOLE,
# IMPIOUS>IMPI, MARTIAN>MART - and auditing put the error rate on bases of
# five letters or fewer at around 20%, against 3% above that.
MIN_LATINATE_BASE = 6
LATINATE_SUFFIXES = [
    ('ATIONS', ['', 'ATE']), ('ATION', ['', 'ATE']), ('ATIVE', ['', 'ATE']),
    ('ATORS', ['', 'ATE']), ('ATOR', ['', 'ATE']),
    ('ANCIES', ['', 'E']), ('ANCES', ['', 'E']), ('ANCY', ['', 'E']), ('ANCE', ['', 'E']),
    ('ENCIES', ['', 'E']), ('ENCES', ['', 'E']), ('ENCY', ['', 'E']), ('ENCE', ['', 'E']),
    ('ARIES', ['', 'E']), ('ARY', ['', 'E']), ('ORIES', ['', 'E']), ('ORY', ['', 'E']),
    ('OUSLY', ['', 'E', 'Y']), ('OUS', ['', 'E', 'Y']),
    ('ISMS', ['', 'E', 'Y']), ('ISM', ['', 'E', 'Y']),
    ('ITIES', ['', 'E', 'Y']), ('ITY', ['', 'E', 'Y']),
    ('ISTIC', ['', 'E', 'Y']), ('ICS', ['', 'E', 'Y']), ('IC', ['', 'E', 'Y']),
    ('ALLY', ['', 'E']), ('ALS', ['', 'E']), ('AL', ['', 'E']),
    ('ANTS', ['', 'E']), ('ANT', ['', 'E']), ('ENTS', ['', 'E']), ('ENT', ['', 'E']),
    ('OIDS', ['', 'E']), ('OID', ['', 'E']),
    ('IANS', ['', 'A', 'Y']), ('IAN', ['', 'A', 'Y']),
    ('ERIES', ['', 'E']), ('ERY', ['', 'E']), ('ETTES', ['', 'E']), ('ETTE', ['', 'E']),
    ('INGLY', ['', 'E']), ('EDLY', ['', 'E']), ('ISHLY', ['']),
    ('IFIES', ['Y', '']), ('IFIED', ['Y', '']), ('IFY', ['Y', '']),
    ('TH', ['', 'E']),
]

# -ITE is deliberately absent: mineral and trade names in -ite come from
# proper nouns or Greek roots, not from the English word left behind, and
# half its matches were wrong (BARITE>BARE, KERNITE>KERN, LUCITE>LUCE,
# STERNITE>STERN, RATITE>RATE).
DERIVATIONAL_SUFFIXES = (
    [(suffix, reps, 1) for suffix, reps in NATIVE_SUFFIXES] +
    [(suffix, reps, MIN_LATINATE_BASE) for suffix, reps in LATINATE_SUFFIXES]
)

# Latin plurals (special handling needed)
LATIN_PLURALS = [
    ('ICES', 'IX'),   # directrix -> directrices
    ('ICES', 'EX'),   # apex -> apices
    ('AE', 'A'),      # larva -> larvae
    ('I', 'US'),      # fungus -> fungi
]

# Greek/Latin plurals, as (plural ending, singular ending, ending the
# singular must have). These are checked only after ordinary English
# morphology has failed, because the endings collide with English ones
# (BASES is the plural of both BASE and BASIS).
#
# ES>IS is confined to Greek -sis/-xis singulars. Without that restriction
# it also matches ordinary English plurals that happen to have an unrelated
# -IS word nearby: TIKES>TIKIS, GELATES>GELATIS, GLACES>GLACIS.
CLASSICAL_PLURALS = [
    ('MATA', 'MA', ''),      # stoma -> stomata
    ('INA', 'EN', ''),       # foramen -> foramina
    ('ES', 'IS', ('SIS', 'XIS')),   # analysis -> analyses
    ('A', 'UM', ''),         # datum -> data
    ('A', 'ON', ''),         # criterion -> criteria
    ('I', 'O', ''),          # libretto -> libretti
]

# Irregular plurals
VES_SINGULARS = ['F', 'FE']   # aardwolf -> aardwolves, knife -> knives

# Below this length a word has too many coincidental inflections to trust
# the reverse direction.
MIN_REVERSE_LENGTH = 4

# British and American spellings of the same word, as (one spelling, the
# other, minimum word length). Tried in both directions.
#
# The single-letter substitutions need a length floor because on short words
# they land on unrelated words rather than the other spelling: MAE>ME,
# WAE>WE, PAEON>PEON, CELS>CELLS, SEL>SELL, RILED>RILLED, COED>COOED.
#
# CE<>SE is left out. Swapping C and S mid-word reaches a different word far
# more often than the other spelling of the same one, and it was 60-70%
# wrong: ASCENT>ASSENT, CENSUAL>SENSUAL, CEROUS>SEROUS, SENSOR>CENSOR.
SPELLING_VARIANTS = [
    ('ISATION', 'IZATION', 0), ('ISING', 'IZING', 0), ('ISED', 'IZED', 0),
    ('ISES', 'IZES', 0), ('ISE', 'IZE', 0),
    ('YSING', 'YZING', 0), ('YSED', 'YZED', 0), ('YSES', 'YZES', 0),
    ('YSE', 'YZE', 0),
    ('OUR', 'OR', 0), ('OGUE', 'OG', 0),
    ('AE', 'E', 6), ('OE', 'E', 6), ('LL', 'L', 6),
]

# Prefixes to try stripping
PREFIXES = [
    'UNDER', 'SUPER', 'OVER', 'SEMI', 'ANTI', 'FORE',
    'WITH', 'OUT', 'MIS', 'PRE', 'NON', 'DIS',
    'UN', 'RE', 'DE', 'BI', 'TRI', 'BE',
]

# Further prefixes. These attach to English words, so a four-letter base is
# enough; below that the splits are false ones (SUBBED>BED, ADMEN>MEN).
#
# PRO- and AB- are deliberately absent. Both attach to Latin stems that are
# not English words, so what they matched was mostly coincidence: PRO- was
# 43% wrong (PROLOGS>LOGS, PROLATE>LATE, PROCHAIN>CHAIN, PROMINE>MINE) and
# AB- 25% (ABBES>BES, ABLUSH>LUSH, ABLINS>LINS, ABOUGHT>OUGHT).
MIN_PREFIXED_BASE = 4
ENGLISH_PREFIXES = [
    'COUNTER', 'INTER', 'INTRA', 'TRANS', 'ULTRA', 'QUASI', 'CROSS',
    'AFTER', 'MULTI', 'SELF', 'HALF', 'BACK', 'DOWN', 'MINI', 'POST',
    'MID', 'SUB', 'UP', 'IN', 'IM', 'EN', 'EM', 'EX', 'AD',
]

# Greek and Latin prefixes need a longer base. What follows one of these is
# usually another combining form rather than an English word, and where it
# happens to spell an English word that word is a different root: MONOSOME
# and AUTOSOME are Greek soma, not SOME; RADIOLOGY and NEOLOGY are logos,
# not LOGY; MONOKINE is kinein, not KINE; HYDROPATH is pathos, not PATH.
# On four-letter bases MONO- was 8 of 13 wrong and HYDRO- 4 of 8.
#
# CO- belongs here for a different reason: so many English words simply
# begin with the letters, and 12 of its 23 four-letter-base matches were
# wrong (COARSE>ARSE, COCOON>COON, COLOUR>LOUR, COPOUT>POUT).
MIN_NEOCLASSICAL_BASE = 5
NEOCLASSICAL_PREFIXES = [
    'ELECTRO', 'PSEUDO', 'THERMO', 'MICRO', 'MACRO', 'PHOTO', 'RADIO',
    'HYDRO', 'AUTO', 'POLY', 'MONO', 'NEO', 'CO',
]

MORE_PREFIXES = (
    [(prefix, MIN_PREFIXED_BASE) for prefix in ENGLISH_PREFIXES] +
    [(prefix, MIN_NEOCLASSICAL_BASE) for prefix in NEOCLASSICAL_PREFIXES]
)


def load_scrabble_dictionary(source=DICTIONARY_URL):
    """Load the Scrabble dictionary from a URL or a local file."""
    print(f"Loading Scrabble dictionary from {source}...")
    if str(source).startswith(('http://', 'https://')):
        import urllib.request
        with urllib.request.urlopen(source) as response:
            text = response.read().decode('utf-8')
    else:
        text = Path(source).read_text(encoding='utf-8')
    words = set(word.strip().upper() for word in text.split('\n') if word.strip())
    print(f"Loaded {len(words)} Scrabble words")
    return words


def stem_variants(stem, suffix):
    """
    Yield plausible base spellings for a stem left over after stripping `suffix`.
    Handles the silent E (MAKING -> MAKE), doubled consonants (RUNNING -> RUN)
    and any repairs specific to the suffix (PARTIES -> PARTY).
    """
    yield stem
    yield stem + 'E'
    if len(stem) >= 3 and stem[-1] == stem[-2] and stem[-1] in DOUBLE_CONSONANTS:
        yield stem[:-1]
    for repair in SUFFIX_REPAIRS.get(suffix, ()):
        yield stem + repair


def inflected_forms(word):
    """
    Yield inflections OF a word, for propagating backwards from a covered
    derived form to its uncovered base (BUBBLING is covered, BUBBLE is not).
    Only inflections, never derivations: a derived form can carry a root the
    base does not share, which would make TIN a relative of TINY.
    """
    # A word ending in a sibilant takes -ES, not -S. Without that, DISCUS
    # picks up the etymology of DISCUSS.
    if not word.endswith(('S', 'X', 'Z', 'CH', 'SH')):
        yield word + 'S'
    yield word + 'ES'
    yield word + 'ED'
    yield word + 'ING'
    yield word + 'D'

    if word.endswith('E'):
        yield word[:-1] + 'ING'
        yield word[:-1] + 'ED'
        yield word[:-1] + 'ES'

    if word.endswith('Y'):
        yield word[:-1] + 'IES'
        yield word[:-1] + 'IED'

    # A short word with a final consonant doubles it: BAG -> BAGGED.
    # Sibilants are excluded for the same reason as above: doubling the S of
    # DISCUS reaches DISCUSSED.
    vowels = set('AEIOU')
    if len(word) >= 3 and word[-1] not in vowels and word[-1] not in 'SXZ' \
            and word[-2] in vowels and word[-3] not in vowels:
        yield word + word[-1] + 'ED'
        yield word + word[-1] + 'ING'


def candidate_bases(word, scrabble_words):
    """
    Yield (rule, base) pairs for a word, in priority order. A rule name is
    recorded alongside every propagated entry so the guess can be audited.
    `scrabble_words` is used by rules that need to know whether a related
    form is itself a word.
    """
    # Latin plurals first (special cases)
    for plural_suffix, singular_suffix in LATIN_PLURALS:
        if word.endswith(plural_suffix) and len(word) >= len(plural_suffix) + 2:
            yield (f'latin_plural:{plural_suffix}>{singular_suffix}',
                   word[:-len(plural_suffix)] + singular_suffix)

    # Suffix stripping
    for suffix in SUFFIXES:
        if word.endswith(suffix) and len(word) > len(suffix) + 2:
            for base in stem_variants(word[:-len(suffix)], suffix):
                yield (f'suffix:{suffix}', base)

    # Derivational suffixes, after inflection has failed
    for suffix, replacements, min_base in DERIVATIONAL_SUFFIXES:
        if word.endswith(suffix) and len(word) > len(suffix) + 2:
            stem = word[:-len(suffix)]
            for replacement in replacements:
                base = stem + replacement
                if len(base) >= min_base:
                    yield (f'derivational:{suffix}', base)

    # Irregular and classical plurals, after ordinary suffixes have failed
    if word.endswith('VES') and len(word) > 5:
        for singular in VES_SINGULARS:
            yield ('plural:VES', word[:-3] + singular)

    if word.endswith('MEN') and len(word) > 5:
        yield ('plural:MEN', word[:-3] + 'MAN')

    # A word that takes an English -S plural is a singular in its own right,
    # not a classical plural: ALGA, GAMMA, LASSI, LATINA, OPERA, RAYA.
    if word + 'S' not in scrabble_words:
        for plural_suffix, singular_suffix, required in CLASSICAL_PLURALS:
            if word.endswith(plural_suffix) and len(word) > len(plural_suffix) + 2:
                base = word[:-len(plural_suffix)] + singular_suffix
                if required and not base.endswith(required):
                    continue
                yield (f'classical_plural:{plural_suffix}>{singular_suffix}', base)

    # Prefix stripping
    for prefix in PREFIXES:
        if word.startswith(prefix) and len(word) > len(prefix) + 2:
            yield (f'prefix:{prefix}', word[len(prefix):])

    for prefix, min_base in MORE_PREFIXES:
        if word.startswith(prefix):
            base = word[len(prefix):]
            # Measure the base without the plural -S it shares with the word,
            # or a plural evades the minimum and then leaks back to its own
            # singular through the reverse rule: COCOONS passes as CO+COONS,
            # and COCOON then takes its etymology from COCOONS.
            effective = len(base) - 1 if base.endswith('S') else len(base)
            if effective >= min_base:
                yield (f'prefix:{prefix}', base)

    # The other spelling of the same word
    for one, other, min_length in SPELLING_VARIANTS:
        if len(word) < min_length:
            continue
        for source, target in ((one, other), (other, one)):
            if source in word:
                respelled = word.replace(source, target)
                if respelled != word:
                    yield (f'spelling:{source}>{target}', respelled)

    # Last resort: take the etymology from an inflection of this word. Every
    # rule above works down towards a base word, which leaves an uncovered
    # base stranded when only its inflections were parsed.
    if len(word) >= MIN_REVERSE_LENGTH:
        for form in inflected_forms(word):
            yield ('reverse_inflection', form)


def find_base_word(word, etymology_dict, scrabble_words):
    """
    Try to find a base word that has etymology.
    Returns (base_word, etymology, rule) if found, else (None, None, None).
    """
    for rule, base in candidate_bases(word, scrabble_words):
        if base in etymology_dict:
            return base, etymology_dict[base], rule
    return None, None, None


def marker_only(entry):
    """An entry like ['imitative:-'] records no root, only a label."""
    return all(e.endswith(':-') for e in entry)


def expand_inflections(etymology_dict, scrabble_words, sources, markers_as_bases=False):
    """
    Expand etymology dictionary by finding inflected forms.
    Records provenance for every entry it adds.

    A word carrying only a marker ('imitative:-', 'french:-') still counts as
    a blank here, because a real root found through a relative is better than
    a label: WANNING once kept a marker from the Chinese city Wanning while
    WAN, its actual base, had roots. Markers themselves are used as bases only
    in the final pass (markers_as_bases), so BUBBLES still inherits BUBBLE's
    marker once nothing better has turned up.
    """
    expanded = {k: list(v) for k, v in etymology_dict.items()}  # Deep copy lists
    propagated = 0

    bases = expanded if markers_as_bases else \
        {k: v for k, v in expanded.items() if not marker_only(v)}
    # Sorted, because a word propagated earlier in a pass is a base for the
    # rest of it; iterating a set made that order, and so the output, depend
    # on the hash seed.
    words_without = sorted(w for w in scrabble_words
                           if w not in expanded or (not markers_as_bases and marker_only(expanded[w])))
    print(f"Words without etymology: {len(words_without)}")

    for i, word in enumerate(words_without):
        if i > 0 and i % 10000 == 0:
            print(f"  Checked {i} words, propagated {propagated}...")

        base, etym, rule = find_base_word(word, bases, scrabble_words)
        if base and etym:
            expanded[word] = list(etym)  # Copy the list
            bases[word] = expanded[word]
            sources[word] = {'rule': rule, 'base': base}
            propagated += 1

    print(f"Propagated etymology to {propagated} inflected forms")
    return expanded


def load_links():
    """
    The links build_etymology.py could not resolve: for each still-rootless
    playable word, the playable words its page (or a base's page) ties it
    to. The parse resolves such links only through parsed roots, so a word
    whose target is covered by propagation - FEOFFOR, "alternative form of
    feoffer", where FEOFFER came from a suffix rule - stays blank without
    this step.
    """
    if not LINKS_PATH.exists():
        return {}
    with open(LINKS_PATH, encoding='utf-8') as f:
        return json.load(f)


def follow_links(etymology_dict, links, sources, markers_as_bases=False):
    """
    Give each linked word the roots of the targets that now have some.
    Provenance records the kind of link: 'stated' for a form-of or
    component on the word's own page, 'derived' for a listing under a base
    word's Derived terms, 'definition' for a definition that links the word
    it is built on.
    """
    expanded = {k: list(v) for k, v in etymology_dict.items()}
    followed = 0
    for word in sorted(links):
        if word in expanded and (markers_as_bases or not marker_only(expanded[word])):
            continue
        targets = [t for t in links[word]['targets'] if t in expanded]
        real = [t for t in targets if not marker_only(expanded[t])]
        # A real root beats a marker; markers pass on only among themselves.
        chosen = real or (targets if markers_as_bases else [])
        if not chosen:
            continue
        roots = set()
        for t in chosen:
            roots.update(expanded[t])
        expanded[word] = sorted(roots)
        sources[word] = {'rule': f"link:{links[word]['kind']}", 'base': chosen[0]}
        followed += 1
    print(f"Followed links for {followed} words")
    return expanded


def run_passes(etymology_dict, scrabble_words, sources, links=None, max_passes=10):
    """
    Propagate repeatedly until no new entries are found. Each pass follows
    links first, then the morphological rules: a link is something
    Wiktionary states, a rule is a guess.
    """
    expanded = etymology_dict
    links = links or {}
    for pass_num in range(1, max_passes + 1):
        print(f"\n=== Pass {pass_num}: Propagating to inflected forms ===")
        before_count = len(expanded)
        expanded = follow_links(expanded, links, sources)
        expanded = expand_inflections(expanded, scrabble_words, sources)
        new_this_pass = len(expanded) - before_count
        print(f"Pass {pass_num} added {new_this_pass} entries")

        if new_this_pass == 0:
            print("No new entries found, stopping.")
            break
    else:
        print("Reached maximum passes, stopping.")

    for pass_num in range(1, max_passes + 1):
        print(f"\n=== Marker pass {pass_num}: markers to inflections of marker-only words ===")
        before_count = len(expanded)
        expanded = follow_links(expanded, links, sources, markers_as_bases=True)
        expanded = expand_inflections(expanded, scrabble_words, sources, markers_as_bases=True)
        if len(expanded) == before_count:
            break
    return expanded


def report_audit(sources, sample_size, rules_filter=None):
    """Print per-rule counts and random samples so guesses can be eyeballed."""
    by_rule = {}
    for word, info in sources.items():
        by_rule.setdefault(info['rule'], []).append((word, info['base']))

    counts = Counter({rule: len(v) for rule, v in by_rule.items()})
    print(f"\n=== Provenance: {len(sources)} propagated entries, "
          f"{len(counts)} rules ===")
    for rule, count in counts.most_common():
        print(f"{count:7d}  {rule}")

    rng = random.Random(0)
    for rule, count in counts.most_common():
        if rules_filter and not any(rule.startswith(f) for f in rules_filter):
            continue
        pairs = sorted(by_rule[rule])
        sample = rng.sample(pairs, min(sample_size, len(pairs)))
        print(f"\n--- {rule} ({count}) ---")
        for word, base in sample:
            print(f"    {word} -> {base}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--audit', action='store_true',
                        help="report what the rules would do, saving nothing")
    parser.add_argument('--rebuild', action='store_true',
                        help="drop previously propagated entries and redo them, "
                             "so that changing a rule cannot leave its old "
                             "guesses behind")
    parser.add_argument('--sample', type=int, default=15,
                        help="samples per rule to print in audit mode")
    parser.add_argument('--rules', nargs='*',
                        help="only sample rules starting with these prefixes")
    parser.add_argument('--dictionary', default=DICTIONARY_URL,
                        help="Scrabble dictionary URL or local path")
    args = parser.parse_args()

    # Load existing etymology dictionary
    if not ETYMOLOGY_PATH.exists():
        print("No existing etymology.json found.")
        return
    print(f"Loading existing etymology from {ETYMOLOGY_PATH}...")
    with open(ETYMOLOGY_PATH, 'r', encoding='utf-8') as f:
        etymology_dict = json.load(f)
    print(f"Loaded {len(etymology_dict)} entries")

    # Load existing provenance, if any. Entries missing from this file were
    # not produced by this script (they came out of the Wiktionary parse, or
    # predate provenance tracking).
    sources = {}
    if SOURCES_PATH.exists():
        with open(SOURCES_PATH, 'r', encoding='utf-8') as f:
            sources = json.load(f)
        print(f"Loaded provenance for {len(sources)} entries")

    if args.rebuild and sources:
        etymology_dict = {word: etym for word, etym in etymology_dict.items()
                          if word not in sources}
        print(f"Dropped {len(sources)} previously propagated entries, "
              f"{len(etymology_dict)} parsed entries remain")
        sources = {}

    scrabble_words = load_scrabble_dictionary(args.dictionary)
    links = load_links()
    print(f"Loaded {len(links)} unresolved links from the parse")

    original_count = len(etymology_dict)
    new_sources = {}
    expanded_dict = run_passes(etymology_dict, scrabble_words, new_sources, links)

    if args.audit:
        report_audit(new_sources, args.sample, args.rules)
        print("\n(audit mode: nothing written)")
        return

    sources.update(new_sources)

    with open(ETYMOLOGY_PATH, 'w', encoding='utf-8') as f:
        json.dump(expanded_dict, f, indent=2, sort_keys=True)
    with open(SOURCES_PATH, 'w', encoding='utf-8') as f:
        json.dump(sources, f, indent=2, sort_keys=True)

    print(f"\nSaved expanded etymology dictionary to {ETYMOLOGY_PATH}")
    print(f"Saved provenance for {len(sources)} entries to {SOURCES_PATH}")
    print(f"Original entries: {original_count}")
    print(f"After expansion: {len(expanded_dict)}")
    print(f"New entries added: {len(expanded_dict) - original_count}")

    # Show coverage
    coverage = 100 * len(expanded_dict) / len(scrabble_words)
    print(f"Coverage: {coverage:.1f}% of Scrabble dictionary")


if __name__ == '__main__':
    main()

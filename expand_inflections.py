#!/usr/bin/env python3
"""
Expand etymology dictionary by propagating etymologies to inflected forms.

This script fills in gaps by checking if words without etymology
appear to be inflected forms of words that DO have etymology.

Only fills in blanks - never overwrites existing etymologies.

Usage:
    python expand_inflections.py
"""

import json
from pathlib import Path


# Suffixes to try stripping (order matters - try longer ones first)
SUFFIXES = [
    'OLOGICALLY', 'ISTICALLY', 'ICALLY',  # adverb forms
    'ISATION', 'IZATION',  # nominalizations
    'URISTS', 'OLOGISTS', 'ISTS',  # agent plurals
    'IVENESS', 'FULNESS', 'LESSNESS',  # noun forms
    'INESS', 'INESS',  # happiness
    'NESSES', 'MENTS', 'ABLES', 'IBLES',  # plurals of noun forms
    'NESS', 'MENT', 'ABLE', 'IBLE', 'TION', 'SION',
    'URIST', 'OLOGIST',  # agent nouns
    'LING', 'INGS', 'IEST', 'IERS',
    'ICAL', 'IVES', 'ISTS',  # adjective/noun forms
    'ING', 'IES', 'IER', 'IED', 'EST', 'ERS', 'ENS',
    'ILY', 'IVE', 'IST', 'ISH', 'ISE', 'IZE',  # adjective/verb forms
    'LY', 'ED', 'ER', 'ES', 'EN', 'EY',
    'Y', 'S', 'D',
]

# Latin plurals (special handling needed)
LATIN_PLURALS = [
    ('ICES', 'IX'),   # directrix -> directrices
    ('ICES', 'EX'),   # apex -> apices
    ('AE', 'A'),      # larva -> larvae
    ('I', 'US'),      # fungus -> fungi
]

# Prefixes to try stripping
PREFIXES = [
    'UNDER', 'SUPER', 'OVER', 'SEMI', 'ANTI', 'FORE',
    'WITH', 'OUT', 'MIS', 'PRE', 'NON', 'DIS',
    'UN', 'RE', 'DE', 'BI', 'TRI', 'BE',
]


def load_scrabble_dictionary(url="https://raw.githubusercontent.com/redbo/scrabble/master/dictionary.txt"):
    """Load the Scrabble dictionary."""
    import urllib.request
    print(f"Loading Scrabble dictionary from {url}...")
    with urllib.request.urlopen(url) as response:
        text = response.read().decode('utf-8')
    words = set(word.strip().upper() for word in text.split('\n') if word.strip())
    print(f"Loaded {len(words)} Scrabble words")
    return words


def find_base_word(word, etymology_dict, scrabble_words):
    """
    Try to find a base word that has etymology.
    Returns (base_word, etymology) if found, else (None, None).
    """
    # Try Latin plurals first (special cases)
    for plural_suffix, singular_suffix in LATIN_PLURALS:
        if word.endswith(plural_suffix) and len(word) >= len(plural_suffix) + 2:
            base = word[:-len(plural_suffix)] + singular_suffix
            if base in etymology_dict:
                return base, etymology_dict[base]

    # Try removing suffixes
    for suffix in SUFFIXES:
        if word.endswith(suffix) and len(word) > len(suffix) + 2:
            base = word[:-len(suffix)]

            # Direct match
            if base in etymology_dict:
                return base, etymology_dict[base]

            # Try adding back 'E' (e.g., MAKING -> MAKE)
            base_e = base + 'E'
            if base_e in etymology_dict:
                return base_e, etymology_dict[base_e]

            # Try doubling handling (e.g., RUNNING -> RUN, not RUNN)
            if len(base) >= 3 and base[-1] == base[-2]:
                base_undoubled = base[:-1]
                if base_undoubled in etymology_dict:
                    return base_undoubled, etymology_dict[base_undoubled]

            # Handle -IES -> -Y (e.g., PARTIES -> PARTY)
            if suffix == 'IES':
                base_y = base + 'Y'
                if base_y in etymology_dict:
                    return base_y, etymology_dict[base_y]

            # Handle -IED -> -Y (e.g., PARTIED -> PARTY)
            if suffix == 'IED':
                base_y = base + 'Y'
                if base_y in etymology_dict:
                    return base_y, etymology_dict[base_y]

            # Handle -IER -> -Y (e.g., HAPPIER -> HAPPY)
            if suffix == 'IER':
                base_y = base + 'Y'
                if base_y in etymology_dict:
                    return base_y, etymology_dict[base_y]

            # Handle -IEST -> -Y (e.g., HAPPIEST -> HAPPY)
            if suffix == 'IEST':
                base_y = base + 'Y'
                if base_y in etymology_dict:
                    return base_y, etymology_dict[base_y]

            # Handle -INESS -> -Y (e.g., HAPPINESS -> HAPPY)
            if suffix == 'INESS':
                base_y = base + 'Y'
                if base_y in etymology_dict:
                    return base_y, etymology_dict[base_y]

            # Handle -ILY -> -Y (e.g., FUNKILY -> FUNKY)
            if suffix == 'ILY':
                base_y = base + 'Y'
                if base_y in etymology_dict:
                    return base_y, etymology_dict[base_y]

            # Handle -IST -> -Y (e.g., COLONIST -> COLONY)
            if suffix == 'IST':
                base_y = base + 'Y'
                if base_y in etymology_dict:
                    return base_y, etymology_dict[base_y]
                # Also try -O base (Italian: LIBRETTO -> LIBRETTIST)
                base_o = base + 'O'
                if base_o in etymology_dict:
                    return base_o, etymology_dict[base_o]

            # Handle -ISTS -> -Y (e.g., COLONISTS -> COLONY)
            if suffix == 'ISTS':
                base_y = base + 'Y'
                if base_y in etymology_dict:
                    return base_y, etymology_dict[base_y]
                # Also try -O base (Italian: LIBRETTO -> LIBRETTISTS)
                base_o = base + 'O'
                if base_o in etymology_dict:
                    return base_o, etymology_dict[base_o]

            # Handle -ICALLY -> -IC (e.g., HISTORICALLY -> HISTORIC)
            if suffix == 'ICALLY':
                base_ic = base + 'IC'
                if base_ic in etymology_dict:
                    return base_ic, etymology_dict[base_ic]
                # Also try -ICAL base
                base_ical = base + 'ICAL'
                if base_ical in etymology_dict:
                    return base_ical, etymology_dict[base_ical]

            # Handle -OLOGICAL -> -OLOGY (e.g., PHENOLOGICAL -> PHENOLOGY... but also try PHENOMENON)
            if suffix == 'OLOGICALLY':
                base_ology = base + 'OLOGY'
                if base_ology in etymology_dict:
                    return base_ology, etymology_dict[base_ology]

            # Handle -IVE with -ATE base (e.g., CREATIVE -> CREATE)
            if suffix == 'IVE':
                base_ate = base + 'ATE'
                if base_ate in etymology_dict:
                    return base_ate, etymology_dict[base_ate]
                base_e = base + 'E'
                if base_e in etymology_dict:
                    return base_e, etymology_dict[base_e]

    # Try removing prefixes
    for prefix in PREFIXES:
        if word.startswith(prefix) and len(word) > len(prefix) + 2:
            base = word[len(prefix):]
            if base in etymology_dict:
                return base, etymology_dict[base]

    return None, None


def expand_inflections(etymology_dict, scrabble_words):
    """
    Expand etymology dictionary by finding inflected forms.
    Only fills in blanks - never overwrites.
    """
    expanded = dict(etymology_dict)
    propagated = 0

    # Find all words without etymology
    words_without = [w for w in scrabble_words if w not in expanded]
    print(f"Words without etymology: {len(words_without)}")

    for i, word in enumerate(words_without):
        if i > 0 and i % 10000 == 0:
            print(f"  Checked {i} words, propagated {propagated}...")

        base, etym = find_base_word(word, expanded, scrabble_words)
        if base and etym:
            expanded[word] = etym
            propagated += 1

    print(f"Propagated etymology to {propagated} inflected forms")
    return expanded


def main():
    # Load existing etymology dictionary
    etym_path = Path(__file__).parent / 'etymology.json'
    if etym_path.exists():
        print(f"Loading existing etymology from {etym_path}...")
        with open(etym_path, 'r', encoding='utf-8') as f:
            etymology_dict = json.load(f)
        print(f"Loaded {len(etymology_dict)} entries")
    else:
        print("No existing etymology.json found.")
        return

    # Load Scrabble dictionary
    scrabble_words = load_scrabble_dictionary()

    # Run multiple passes until no new entries are found
    original_count = len(etymology_dict)
    expanded_dict = etymology_dict
    pass_num = 1

    while True:
        print(f"\n=== Pass {pass_num}: Propagating to inflected forms ===")
        before_count = len(expanded_dict)
        expanded_dict = expand_inflections(expanded_dict, scrabble_words)
        new_this_pass = len(expanded_dict) - before_count
        print(f"Pass {pass_num} added {new_this_pass} entries")

        if new_this_pass == 0:
            print("No new entries found, stopping.")
            break

        pass_num += 1
        if pass_num > 10:  # Safety limit
            print("Reached maximum passes, stopping.")
            break

    # Save expanded dictionary
    output_path = Path(__file__).parent / 'etymology.json'
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(expanded_dict, f, indent=2, sort_keys=True)

    print(f"\nSaved expanded etymology dictionary to {output_path}")
    print(f"Original entries: {original_count}")
    print(f"After expansion: {len(expanded_dict)}")
    print(f"New entries added: {len(expanded_dict) - original_count}")

    # Show coverage
    coverage = 100 * len(expanded_dict) / len(scrabble_words)
    print(f"Coverage: {coverage:.1f}% of Scrabble dictionary")


if __name__ == '__main__':
    main()

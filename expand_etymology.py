#!/usr/bin/env python3
"""
Expand etymology dictionary by propagating etymologies to derived terms.

This script:
1. Loads the existing etymology.json
2. Parses Wiktionary to extract "Derived terms" sections
3. Propagates etymologies from base words to their derived terms
4. Saves the expanded dictionary

Usage:
    python expand_etymology.py enwiktionary-latest-pages-articles.xml.bz2
"""

import bz2
import json
import re
import sys
from collections import defaultdict
from pathlib import Path


def load_scrabble_dictionary(url="https://raw.githubusercontent.com/redbo/scrabble/master/dictionary.txt"):
    """Load the Scrabble dictionary to filter results."""
    import urllib.request
    print(f"Loading Scrabble dictionary from {url}...")
    with urllib.request.urlopen(url) as response:
        text = response.read().decode('utf-8')
    words = set(word.strip().upper() for word in text.split('\n') if word.strip())
    print(f"Loaded {len(words)} Scrabble words")
    return words


def extract_derived_terms(wiki_text, title):
    """
    Extract derived terms from the English section of a Wiktionary page.
    Returns a list of derived term strings.
    """
    # Only process if it has an English section
    if '==English==' not in wiki_text:
        return []

    # Extract the English section
    english_match = re.search(r'==English==(.*?)(?=\n==[^=]|\Z)', wiki_text, re.DOTALL)
    if not english_match:
        return []

    english_section = english_match.group(1)

    # Find "Derived terms" sections (may have multiple)
    derived_sections = re.findall(
        r'====?Derived terms====?(.*?)(?=\n===|\n====|\Z)',
        english_section,
        re.DOTALL
    )

    derived_terms = []

    for section in derived_sections:
        # Extract terms from {{col|en|term1|term2|...}} templates
        col_matches = re.findall(r'\{\{col\d*\|en\|([^}]+)\}\}', section)
        for match in col_matches:
            # Split by | and clean up
            terms = match.split('|')
            for term in terms:
                term = term.strip()
                # Skip parameters like title=, sort=, etc.
                if '=' in term:
                    continue
                # Clean up the term
                term = re.sub(r'\[\[([^\]|]+).*?\]\]', r'\1', term)  # [[term|display]] -> term
                term = re.sub(r"'''?([^']+)'''?", r'\1', term)  # '''term''' -> term
                term = re.sub(r'\{\{[^}]+\}\}', '', term)  # Remove any remaining templates
                term = term.strip()
                if term and term.isalpha():
                    derived_terms.append(term.upper())

        # Also extract from {{der2|en|...}}, {{der3|en|...}}, {{der4|en|...}}
        der_matches = re.findall(r'\{\{der\d\|en\|([^}]+)\}\}', section)
        for match in der_matches:
            terms = match.split('|')
            for term in terms:
                term = term.strip()
                if '=' in term:
                    continue
                term = re.sub(r'\[\[([^\]|]+).*?\]\]', r'\1', term)
                term = re.sub(r"'''?([^']+)'''?", r'\1', term)
                term = re.sub(r'\{\{[^}]+\}\}', '', term)
                term = term.strip()
                if term and term.isalpha():
                    derived_terms.append(term.upper())

        # Extract simple {{l|en|term}} links
        l_matches = re.findall(r'\{\{l\|en\|([^|}]+)', section)
        for term in l_matches:
            term = term.strip()
            if term and term.isalpha():
                derived_terms.append(term.upper())

    return list(set(derived_terms))  # Remove duplicates


def iter_wiktionary_pages(filepath):
    """
    Iterator that yields (title, text) tuples from Wiktionary XML dump.
    """
    filepath = Path(filepath)

    if filepath.suffix == '.bz2':
        open_func = lambda p: bz2.open(p, 'rt', encoding='utf-8')
    else:
        open_func = lambda p: open(p, 'r', encoding='utf-8')

    print(f"Parsing {filepath}...")

    with open_func(filepath) as f:
        current_title = None
        current_text = []
        in_text = False
        page_count = 0

        for line in f:
            # Look for title
            title_match = re.search(r'<title>([^<]+)</title>', line)
            if title_match:
                current_title = title_match.group(1)
                continue

            # Look for text start
            text_start = re.search(r'<text[^>]*>(.*)', line)
            if text_start:
                in_text = True
                content = text_start.group(1)
                if '</text>' in content:
                    content = content.split('</text>')[0]
                    in_text = False
                    if current_title and ':' not in current_title:
                        yield current_title, content
                        page_count += 1
                        if page_count % 50000 == 0:
                            print(f"  Processed {page_count} pages...")
                else:
                    current_text = [content]
                continue

            if in_text:
                if '</text>' in line:
                    current_text.append(line.split('</text>')[0])
                    in_text = False
                    if current_title and ':' not in current_title:
                        yield current_title, '\n'.join(current_text)
                        page_count += 1
                        if page_count % 50000 == 0:
                            print(f"  Processed {page_count} pages...")
                    current_text = []
                else:
                    current_text.append(line)

    print(f"  Total pages processed: {page_count}")


def build_derived_terms_map(wiktionary_path, scrabble_words):
    """
    Build a map of base words to their derived terms.
    Only includes words that are in the Scrabble dictionary.
    """
    derived_map = defaultdict(set)
    words_with_derived = 0

    for title, text in iter_wiktionary_pages(wiktionary_path):
        word_upper = title.upper()

        # Only process words in Scrabble dictionary
        if word_upper not in scrabble_words:
            continue

        # Extract derived terms
        derived = extract_derived_terms(text, title)

        # Filter to only Scrabble words
        derived = [d for d in derived if d in scrabble_words and d != word_upper]

        if derived:
            derived_map[word_upper].update(derived)
            words_with_derived += 1

            if words_with_derived % 1000 == 0:
                print(f"  Found {words_with_derived} words with derived terms...")

    print(f"\nFound {words_with_derived} words with derived terms")
    print(f"Total derived term relationships: {sum(len(v) for v in derived_map.values())}")

    return derived_map


def expand_etymology(etymology_dict, derived_map, scrabble_words):
    """
    Expand etymology dictionary by propagating to derived terms.
    """
    expanded = dict(etymology_dict)
    propagated = 0

    for base_word, derived_terms in derived_map.items():
        # If the base word has etymology
        if base_word in etymology_dict:
            base_etym = etymology_dict[base_word]

            # Propagate to derived terms that don't have etymology yet
            for derived in derived_terms:
                if derived not in expanded and derived in scrabble_words:
                    expanded[derived] = base_etym
                    propagated += 1

    print(f"Propagated etymology to {propagated} derived terms")
    return expanded


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        print("\nError: Please provide path to Wiktionary dump file")
        sys.exit(1)

    wiktionary_path = sys.argv[1]

    if not Path(wiktionary_path).exists():
        print(f"Error: File not found: {wiktionary_path}")
        sys.exit(1)

    # Load existing etymology dictionary
    etym_path = Path(__file__).parent / 'etymology.json'
    if etym_path.exists():
        print(f"Loading existing etymology from {etym_path}...")
        with open(etym_path, 'r', encoding='utf-8') as f:
            etymology_dict = json.load(f)
        print(f"Loaded {len(etymology_dict)} entries")
    else:
        print("No existing etymology.json found. Run build_etymology.py first.")
        sys.exit(1)

    # Load Scrabble dictionary
    scrabble_words = load_scrabble_dictionary()

    # Build derived terms map
    print("\n=== Pass 1: Extracting derived terms ===")
    derived_map = build_derived_terms_map(wiktionary_path, scrabble_words)

    # Expand etymology
    print("\n=== Pass 2: Propagating etymologies ===")
    expanded_dict = expand_etymology(etymology_dict, derived_map, scrabble_words)

    # Save expanded dictionary
    output_path = Path(__file__).parent / 'etymology.json'
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(expanded_dict, f, indent=2, sort_keys=True)

    print(f"\nSaved expanded etymology dictionary to {output_path}")
    print(f"Original entries: {len(etymology_dict)}")
    print(f"After expansion: {len(expanded_dict)}")
    print(f"New entries added: {len(expanded_dict) - len(etymology_dict)}")

    # Show coverage
    coverage = 100 * len(expanded_dict) / len(scrabble_words)
    print(f"Coverage: {coverage:.1f}% of Scrabble dictionary")


if __name__ == '__main__':
    main()

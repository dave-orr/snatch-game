#!/usr/bin/env python3
"""
Build etymology dictionary from Wiktionary dump.

Usage:
1. Download the Wiktionary dump from:
   https://dumps.wikimedia.org/enwiktionary/latest/enwiktionary-latest-pages-articles.xml.bz2

2. Run this script:
   python build_etymology.py enwiktionary-latest-pages-articles.xml.bz2

3. Output will be etymology.json
"""

import bz2
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

# Language codes we care about (stopping points for etymology - not going to PIE)
ROOT_LANGUAGES = {
    'la': 'latin',
    'grc': 'greek',
    'ang': 'old_english',
    'non': 'old_norse',
    'goh': 'old_high_german',
    'odt': 'old_dutch',
    'fro': 'old_french',
    'gem-pro': 'proto_germanic',
    'ar': 'arabic',
    'fa': 'persian',
    'sa': 'sanskrit',
    'hi': 'hindi',
    'ta': 'tamil',
    'zh': 'chinese',
    'ja': 'japanese',
    'ko': 'korean',
    'nl': 'dutch',
    'de': 'german',
    'fr': 'french',
    'es': 'spanish',
    'it': 'italian',
    'pt': 'portuguese',
}

# Skip these - too far back or not useful
SKIP_LANGUAGES = {'ine-pro', 'ine-bsl-pro', 'gem-pro'}


def load_scrabble_dictionary(url="https://raw.githubusercontent.com/redbo/scrabble/master/dictionary.txt"):
    """Load the Scrabble dictionary to filter results."""
    import urllib.request
    print(f"Loading Scrabble dictionary from {url}...")
    with urllib.request.urlopen(url) as response:
        text = response.read().decode('utf-8')
    words = set(word.strip().upper() for word in text.split('\n') if word.strip())
    print(f"Loaded {len(words)} Scrabble words")
    return words


def extract_etymology_from_text(wiki_text):
    """
    Extract ALL etymology information from wiki markup text.
    Returns a list of root language:word strings, or None if none found.
    Handles multiple etymology sections (Etymology 1, Etymology 2, etc.)
    """
    # Only process if it has an English section
    if '==English==' not in wiki_text:
        return None

    # Extract the English section
    english_match = re.search(r'==English==(.*?)(?=\n==[^=]|\Z)', wiki_text, re.DOTALL)
    if not english_match:
        return None

    english_section = english_match.group(1)

    # Find ALL etymology sections within English (Etymology, Etymology 1, Etymology 2, etc.)
    etym_sections = re.findall(
        r'===Etymology(?:\s*\d*)?===(.*?)(?=\n===|\Z)',
        english_section,
        re.DOTALL
    )

    if not etym_sections:
        return None

    # Extract etymology templates from ALL sections
    # Patterns: {{der|en|la|word}}, {{inh|en|la|word}}, {{bor|en|la|word}}
    # Also handles {{bor+|...}}, {{der+|...}}, {{inh+|...}} variants
    pattern = r'\{\{(?:der|inh|bor|borrowed|derived|inherited)\+?\|en\|([a-z-]+)\|([^|}]+)'

    all_etymologies = set()  # Use set to dedupe

    for etymology_text in etym_sections:
        for match in re.finditer(pattern, etymology_text, re.IGNORECASE):
            lang_code = match.group(1).lower()
            word = match.group(2).strip()

            # Clean up the word
            word = re.sub(r'<[^>]+>', '', word)  # Remove HTML
            word = re.sub(r'\[\[([^\]|]+)(\|[^\]]+)?\]\]', r'\1', word)  # [[word|display]] -> word
            word = word.split('|')[0].strip()
            word = word.strip('*')  # Remove reconstructed word marker

            # Skip PIE
            if lang_code in SKIP_LANGUAGES:
                continue

            # Skip if word is just '-' (placeholder meaning "same as headword")
            if word and len(word) > 0 and word != '-':
                readable_lang = ROOT_LANGUAGES.get(lang_code, lang_code)
                all_etymologies.add(f"{readable_lang}:{word.lower()}")

    if not all_etymologies:
        return None

    return list(all_etymologies)


def iter_wiktionary_pages(filepath):
    """
    Iterator that yields (title, text) tuples from Wiktionary XML dump.
    Uses simple regex parsing instead of XML parser for reliability.
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
                # Check if text ends on same line
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

            # In text block
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


def build_etymology_dict(wiktionary_path, scrabble_words):
    """
    Build etymology dictionary from Wiktionary dump.
    """
    etymology_dict = {}
    found = 0
    checked = 0

    for title, text in iter_wiktionary_pages(wiktionary_path):
        word_upper = title.upper()

        # Only process words in Scrabble dictionary
        if word_upper not in scrabble_words:
            continue

        checked += 1
        if checked % 5000 == 0:
            print(f"  Checked {checked} Scrabble words, found etymology for {found}...")

        # Parse etymology
        root = extract_etymology_from_text(text)

        if root:
            etymology_dict[word_upper] = root
            found += 1

    print(f"\nFound etymology for {found} out of {len(scrabble_words)} Scrabble words ({100*found/len(scrabble_words):.1f}%)")
    return etymology_dict


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        print("\nError: Please provide path to Wiktionary dump file")
        print("Download from: https://dumps.wikimedia.org/enwiktionary/latest/enwiktionary-latest-pages-articles.xml.bz2")
        sys.exit(1)

    wiktionary_path = sys.argv[1]

    if not Path(wiktionary_path).exists():
        print(f"Error: File not found: {wiktionary_path}")
        sys.exit(1)

    # Load Scrabble dictionary
    scrabble_words = load_scrabble_dictionary()

    # Build etymology dictionary
    etymology_dict = build_etymology_dict(wiktionary_path, scrabble_words)

    # Save to JSON
    output_path = Path(__file__).parent / 'etymology.json'
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(etymology_dict, f, indent=2, sort_keys=True)

    print(f"\nSaved etymology dictionary to {output_path}")
    print(f"Total entries: {len(etymology_dict)}")

    # Print some stats
    roots = defaultdict(int)
    multi_etym_count = 0
    for word, etym_list in etymology_dict.items():
        if len(etym_list) > 1:
            multi_etym_count += 1
        for etym in etym_list:
            lang = etym.split(':')[0]
            roots[lang] += 1

    print(f"Words with multiple etymologies: {multi_etym_count}")

    print("\nBreakdown by root language:")
    for lang, count in sorted(roots.items(), key=lambda x: -x[1])[:20]:
        print(f"  {lang}: {count}")

    # Show some examples (write to file to avoid Unicode issues)
    with open('etymology_samples.txt', 'w', encoding='utf-8') as f:
        f.write("Sample entries:\n")
        examples = ['FIX', 'AFFIX', 'SUFFIX', 'PREFIX', 'BANG', 'BANGLE', 'WIND', 'WINDY']
        for word in examples:
            if word in etymology_dict:
                f.write(f"  {word}: {etymology_dict[word]}\n")
    print("\nSample entries written to etymology_samples.txt")


if __name__ == '__main__':
    main()

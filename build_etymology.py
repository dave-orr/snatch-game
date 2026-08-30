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
import html
import json
import re
import sys
import unicodedata
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

SKIP_LANGUAGES = {'ine-pro', 'ine-bsl-pro', 'gem-pro'}

# {{tmpl|en|LANG|WORD}} - a root in another language
ROOT_TEMPLATES = ('der','inh','bor','borrowed','derived','inherited','uder','lbor',
                  'slbor','obor','cal','calque','clq','translit','psm','sl')
# {{tmpl|en|WORD|WORD}} - English components
AFFIX_TEMPLATES = ('af','affix','suf','suffix','pre','prefix','con','confix',
                   'com','compound','blend','univerbation','back-form',
                   'back-formation','clipping','rebracketing','surf')
IMITATIVE = ('onom','onomatopoeic','imitative','ideophonic')
UNKNOWN = ('unk','unknown','rfe')

def clean_arg(arg):
    """strip annotations, links and named parameters from a template argument"""
    # annotations nest: la-new:-<ety:from<la:-<ety:der<grc:-φοβία>>>>
    while True:
        stripped = re.sub(r'<[^<>]*>', '', arg)
        if stripped == arg: break
        arg = stripped
    arg = arg.replace('<', '').replace('>', '')
    arg = re.sub(r'\[\[([^\]|]+)(\|[^\]]+)?\]\]', r'\1', arg)
    return arg.strip()

def is_named(arg):
    return bool(re.match(r'^[a-z0-9_-]+\s*=', arg, re.IGNORECASE))

def split_template(body):
    """split a template body on | respecting nested {{ }} and [[ ]]"""
    parts, depth, cur = [], 0, ''
    for ch in body:
        if ch == '{' or ch == '[': depth += 1
        elif ch == '}' or ch == ']': depth -= 1
        if ch == '|' and depth == 0: parts.append(cur); cur = ''
        else: cur += ch
    parts.append(cur)
    return parts

def iter_templates(text):
    """yield (name, [args]) for each top-level template"""
    for m in re.finditer(r'\{\{([^{}]*(?:\{\{[^{}]*\}\}[^{}]*)*)\}\}', text):
        parts = split_template(m.group(1))
        yield parts[0].strip().lower(), parts[1:]

def valid_lang(code):
    return (bool(re.fullmatch(r'[a-z][a-z0-9-]{0,15}', code))
            and code not in SKIP_LANGUAGES)


def normalize(word):
    """Match the conventions of the existing data: one word, no reconstruction
    marker, lowercase."""
    word = word.split(',')[0].strip().lstrip('*').strip()
    return unicodedata.normalize('NFC', word).lower()

def affix_components(args, shape):
    """
    Yield the meaningful components of an affix template. `shape` says where
    affixes sit: suffix templates put the base first, prefix templates last,
    confix puts a prefix first and a suffix last.
    """
    # Keep empty positional arguments while deciding which slot is the affix.
    # {{suffix|en||an}} names its base through a separate template, and
    # compacting the blank away promotes -AN into the base slot, which is how
    # MESOZOAN came to take its etymology from the word AN.
    args = [clean_arg(a) for a in args if not is_named(clean_arg(a))]
    if not any(args): return
    for i, a in enumerate(args):
        if not a: continue
        first, last = i == 0, i == len(args) - 1
        written_affix = a.startswith('-') or a.endswith('-')
        if shape == 'suffix':   suffix = not first
        elif shape == 'prefix': suffix = False
        elif shape == 'confix': suffix = last and not first
        else:                   suffix = a.startswith('-')
        prefix = (shape == 'prefix' and first) or (shape == 'confix' and first) \
                 or a.endswith('-')
        bare = a.strip('-')
        if not bare: continue
        if (written_affix or suffix or prefix) and bare.lower() in NOISE_AFFIXES:
            continue
        # Keep the hyphen: the page for -LOGY (Greek logos) is a different
        # entry from LOGY (sluggish), and resolving the wrong one is how
        # RADIOLOGY came out descended from a word meaning sluggish.
        if suffix:   yield normalize('-' + bare)
        elif prefix: yield normalize(bare + '-')
        else:        yield normalize(bare)


def extract(ety_text):
    """returns (roots, english_components, flags)"""
    roots, components, flags = set(), set(), set()
    mentions = []
    if not ety_text: return roots, components, flags

    # Everything after "Compare"/"Cognate" lists relatives in other languages,
    # not ancestors. -LOGY picked up German Terminologie that way.
    ety_text = re.split(r'\b(?:Compare|Cognate|cognate with|Related to)\b',
                        ety_text)[0]

    def take_affix_args(args, shape):
        components.update(affix_components(args, shape))

    for name, args in iter_templates(ety_text):
        base = name.rstrip('+')
        if base in ('cog','noncog','w','q','qualifier','ref','r') or base.startswith('r:'):
            continue
        if base in IMITATIVE: flags.add('imitative'); continue
        if base in UNKNOWN: flags.add('unknown'); continue

        if base in ROOT_TEMPLATES and len(args) >= 3 and clean_arg(args[0]) == 'en':
            lang = clean_arg(args[1]).lower().strip('.,;:')
            word = clean_arg(args[2])
            if valid_lang(lang) and word and word != '-':
                roots.add((lang, normalize(word)))
        elif base in AFFIX_TEMPLATES and args and clean_arg(args[0]) == 'en':
            shape = ('suffix' if base in ('suf','suffix') else
                     'prefix' if base in ('pre','prefix') else
                     'confix' if base in ('con','confix') else 'free')
            take_affix_args(args[1:], shape)
        elif base in ('etymon','ety') and len(args) >= 2 and clean_arg(args[0]) == 'en':
            kind = clean_arg(args[1]).lstrip(':').lower()
            rest = args[2:]
            if kind == 'af':
                take_affix_args(rest, 'free')
            elif kind in ROOT_TEMPLATES and rest:
                # these pack language and word into one argument: grc:ἐπῐ-
                arg = clean_arg(rest[0])
                if ':' in arg:
                    lang, _, word = arg.partition(':')
                    lang, word = lang.strip().lower().strip('.,;:'), word.strip()
                    if valid_lang(lang) and word and word != '-':
                        roots.add((lang, normalize(word)))
        elif base == 'm' and len(args) >= 2:
            lang = clean_arg(args[0]).lower().strip('.,;:')
            # English mentions are "influenced by" noise, not ancestors
            if lang != 'en' and valid_lang(lang):
                word = clean_arg(args[1])
                if word and word != '-': mentions.append((lang, normalize(word)))

    # A bare {{m}} is only trustworthy when the section states no derivation
    # of its own ("From Middle English {{m|enm|bublen}}"). Where explicit
    # templates exist, they are the etymology and mentions are commentary.
    if not roots and mentions:
        roots.update(mentions[:3])

    roots = {(l, w) for l, w in roots if w not in ('-', '') and '-' * 2 not in w}
    return roots, components, flags


def load_scrabble_dictionary(url="https://raw.githubusercontent.com/redbo/scrabble/master/dictionary.txt"):
    """Load the Scrabble dictionary to filter results."""
    import urllib.request
    print(f"Loading Scrabble dictionary from {url}...")
    with urllib.request.urlopen(url) as response:
        text = response.read().decode('utf-8')
    words = set(word.strip().upper() for word in text.split('\n') if word.strip())
    print(f"Loaded {len(words)} Scrabble words")
    return words


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


def english_etymology_section(wiki_text):
    """Return the etymology wikitext inside the English section, if any."""
    if not wiki_text or '==English==' not in wiki_text:
        return None
    english = re.split(r'\n==[^=]', wiki_text.split('==English==', 1)[1])[0]
    sections = re.findall(r'\n=+\s*Etymology[^=\n]*=+\n(.*?)(?=\n=+[^=\n]|\Z)',
                          english, re.DOTALL)
    return '\n'.join(sections) if sections else None


MAX_RESOLUTION_DEPTH = 4

# Positional, quantitative and grammatical affixes. Sharing one of these
# tells a player nothing: every negated word has UN-, every repeated action
# RE-. Substantive combining forms are deliberately absent, because sharing
# -LOGY, BIO-, HYDRO- or -PHOBIA is exactly the connection worth showing.
#
# Frequency cannot make this split. Counted across languages the two groups
# interleave - SUB- 362, UNDER- 336, DE- 333 against -LOGIA 350, BIO- 268,
# -OID 218 - so the line has to be drawn by what the affix means.
NOISE_AFFIXES = {
    # negation, repetition, position, degree, number
    'un','re','non','nan','in','im','ir','il','dis','de','ab','ad','ex','ob',
    'per','pro','trans','pre','prae','post','ante','anti','over','ofer','under',
    'sub','super','hyper','out','ut','up','fore','back','co','com','con','inter',
    'intra','semi','multi','bi','tri','mono','uni','be','mis','mys','missa',
    'αντι','υπερ','υπο','επι','προ','συν','κατα','δια','παρα','αμφι',
    # grammatical endings
    'ally','ial','al','alis','an','ian','ate','ed','en','er','es','est','ial',
    'ic','ical','ide','ile','ine','ing','ion','tio','tion','ise','ish','ism',
    'ist','ity','ive','ize','le','ly','ment','ness','or','ory','ose','ous','s',
    'y','ee','ery','age','able','ible','ability','abilitas','ablete','ful',
    'less','like','ling','ward','wise','let','ette','th','dom','hood','ship',
    'a','acioun','uʀ','ur','ation','acion',
}


def affix_key(root):
    """The bare affix, without language, hyphens or diacritics."""
    word = root.split(':', 1)[1] if ':' in root else root
    word = word.strip('-')
    return ''.join(c for c in unicodedata.normalize('NFD', word)
                   if not unicodedata.combining(c)).lower()


def drop_noisy_affixes(etymology_dict):
    """Remove affixes too general to connect one word to another."""
    trimmed, dropped = {}, 0
    for word, roots in etymology_dict.items():
        kept = [r for r in roots
                if not (is_affix_root(r) and affix_key(r) in NOISE_AFFIXES)]
        dropped += len(roots) - len(kept)
        if kept:
            trimmed[word] = kept
    print(f"Dropped {dropped} grammatical affix roots")
    print(f"Words left with at least one root: {len(trimmed)} "
          f"(lost {len(etymology_dict) - len(trimmed)} that had only affixes)")
    return trimmed


def is_affix_root(root):
    word = root.split(':', 1)[1] if ':' in root else root
    return word.startswith('-') or word.endswith('-')


def resolve(title, pages, cache, seen=None):
    """
    Roots for a page, following affix and compound components when the page
    states no roots of its own. QUINIC gives no root directly; it says it is
    QUININE + -ic, so its roots are QUININE's.
    """
    if title in cache:
        return cache[title]
    seen = seen or set()
    if title in seen or len(seen) >= MAX_RESOLUTION_DEPTH:
        return set()
    entry = pages.get(title)
    if not entry:
        return set()
    roots, components = entry
    if roots:
        cache[title] = set(roots)
        return cache[title]
    resolved = set()
    for component in components:
        resolved |= resolve(component, pages, cache, seen | {title})
    cache[title] = resolved
    return resolved


def build_etymology_dict(wiktionary_path, scrabble_words):
    """
    Parse the dump, then resolve component links into roots.

    Every English page is kept, not just the Scrabble words: QUINIC resolves
    through QUININE and RADIOLOGY through -LOGY, and neither base has to be
    playable for its roots to be the right answer.
    """
    pages = {}
    flags = {}
    page_count = 0

    for title, text in iter_wiktionary_pages(wiktionary_path):
        if title[:1].isupper():   # proper nouns are not Scrabble words
            continue
        # The XML dump escapes markup, so <t:...> annotations arrive as
        # &lt;t:...&gt; and survive the stripper unless unescaped first.
        section = english_etymology_section(html.unescape(text))
        if not section:
            continue
        page_count += 1
        if page_count % 100000 == 0:
            print(f"  {page_count} pages with an etymology section...")
        roots, components, page_flags = extract(section)
        if roots or components:
            pages[title.lower()] = (frozenset(roots), tuple(components))
        if page_flags:
            flags[title.lower()] = page_flags

    print(f"Pages with etymology data: {len(pages)}")

    cache = {}
    etymology_dict = {}
    unresolved = 0
    for word in scrabble_words:
        roots = resolve(word.lower(), pages, cache)
        if roots:
            etymology_dict[word] = sorted(
                f"{ROOT_LANGUAGES.get(lang, lang)}:{root}" for lang, root in roots)
        elif word.lower() in pages:
            unresolved += 1

    etymology_dict = drop_noisy_affixes(etymology_dict)

    imitative = sum(1 for w in scrabble_words
                    if w not in etymology_dict and 'imitative' in flags.get(w.lower(), ()))
    print(f"Scrabble words with roots: {len(etymology_dict)} "
          f"({100*len(etymology_dict)/len(scrabble_words):.1f}%)")
    print(f"  had etymology data but resolved to no root: {unresolved}")
    print(f"  no root, but marked imitative by Wiktionary: {imitative}")
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

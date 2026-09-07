#!/usr/bin/env python3
"""
Look up words Wiktionary has no etymology for in Merriam-Webster's Collegiate
Dictionary API, and record the roots it gives.

The Scrabble list is Merriam-Webster's own, so Collegiate has an entry for
nearly every word in it. Its etymologies are prose in a fixed shape -
"Middle English, from Anglo-French {it}covert{/it}, from Latin
{it}coopertus{/it}" - which this script reads into the same language:root
form the Wiktionary parse produces.

Usage:
    python mw_lookup.py --build-queue mw_queue.json     # from etymology.json
    python mw_lookup.py --key KEY --queue mw_queue.json [--limit 950]

The queue holds one word per uncovered family: uncovered words are grouped
by the propagation rules and stated links that tie them together (ZIP,
ZIPS, ZIPPED, UNZIP), and the word the others point to is looked up, since
the expansion carries its roots to the rest. That is about 4,400 words for
10,500 uncovered ones. The free tier allows 1,000 lookups a day, so --limit
stops after that many new requests; rerun tomorrow to continue. Every raw response is cached in
--cache (default mw_cache/ next to this file, not committed), so a word is
never requested twice and the extraction can be rerun offline.

Output is etymology_mw.json: word -> {"roots", "components", "flags"}.
build_etymology.py merges it into etymology.json for words the Wiktionary
parse left blank, and records each such word in etymology_sources.json
under the rule "merriam-webster".
"""

import argparse
import json
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path

HERE = Path(__file__).parent
OUTPUT_PATH = HERE / 'etymology_mw.json'
ENDPOINT = 'https://dictionaryapi.com/api/v3/references/collegiate/json/'

# Language names as Merriam-Webster writes them, to the codes the Wiktionary
# parse uses, so that a root from either source compares with the other.
LANGUAGES = {
    'Middle English': 'enm', 'Old English': 'ang', 'Anglo-French': 'xno',
    'Old French': 'fro', 'Middle French': 'frm', 'French': 'fr',
    'Old North French': 'fro', 'Old Occitan': 'pro', 'Old Provençal': 'pro',
    'Occitan': 'oc', 'Provençal': 'oc', 'Catalan': 'ca',
    'Latin': 'la', 'Late Latin': 'la-lat', 'Medieval Latin': 'la-med',
    'New Latin': 'la-new', 'Vulgar Latin': 'la-vul', 'Old Latin': 'itc-ola',
    'Greek': 'grc', 'Late Greek': 'grc-koi', 'Middle Greek': 'gkm',
    'New Greek': 'el', 'Modern Greek': 'el',
    'Italian': 'it', 'Old Italian': 'roa-oit', 'Spanish': 'es', 'Old Spanish': 'osp',
    'American Spanish': 'es', 'Mexican Spanish': 'es-mx', 'Portuguese': 'pt',
    'Old Portuguese': 'roa-opt', 'Romanian': 'ro',
    'German': 'de', 'Old High German': 'goh', 'Middle High German': 'gmh',
    'Middle Low German': 'gml', 'Low German': 'nds', 'Old Saxon': 'osx',
    'Dutch': 'nl', 'Middle Dutch': 'dum', 'Old Dutch': 'odt', 'Afrikaans': 'af',
    'Flemish': 'nl', 'Frisian': 'fy', 'Old Frisian': 'ofs',
    'Old Norse': 'non', 'Icelandic': 'is', 'Old Icelandic': 'non',
    'Danish': 'da', 'Swedish': 'sv', 'Norwegian': 'no', 'Old Swedish': 'gmq-osw',
    'Old Danish': 'gmq-oda', 'Gothic': 'got',
    'Scots': 'sco', 'Irish': 'ga', 'Old Irish': 'sga', 'Middle Irish': 'mga',
    'Scottish Gaelic': 'gd', 'Welsh': 'cy', 'Breton': 'br', 'Cornish': 'kw',
    'Russian': 'ru', 'Polish': 'pl', 'Czech': 'cs', 'Ukrainian': 'uk',
    'Serbian': 'sr', 'Croatian': 'hr', 'Serbo-Croatian': 'sh', 'Bulgarian': 'bg',
    'Old Church Slavic': 'cu', 'Lithuanian': 'lt', 'Latvian': 'lv',
    'Hungarian': 'hu', 'Finnish': 'fi', 'Estonian': 'et', 'Turkish': 'tr',
    'Ottoman Turkish': 'ota', 'Persian': 'fa', 'Middle Persian': 'pal',
    'Arabic': 'ar', 'Hebrew': 'he', 'Aramaic': 'arc', 'Yiddish': 'yi',
    'Sanskrit': 'sa', 'Hindi': 'hi', 'Urdu': 'ur', 'Hindi & Urdu': 'hi',
    'Bengali': 'bn', 'Tamil': 'ta', 'Malayalam': 'ml', 'Telugu': 'te',
    'Marathi': 'mr', 'Gujarati': 'gu', 'Punjabi': 'pa', 'Sinhalese': 'si',
    'Malay': 'ms', 'Indonesian': 'id', 'Javanese': 'jv', 'Tagalog': 'tl',
    'Chinese': 'zh', 'Cantonese': 'yue', 'Mandarin': 'cmn', 'Japanese': 'ja',
    'Korean': 'ko', 'Tibetan': 'bo', 'Thai': 'th', 'Vietnamese': 'vi',
    'Hawaiian': 'haw', 'Maori': 'mi', 'Tahitian': 'ty', 'Samoan': 'sm',
    'Tongan': 'to', 'Fijian': 'fj', 'Malagasy': 'mg',
    'Swahili': 'sw', 'Zulu': 'zu', 'Xhosa': 'xh', 'Yoruba': 'yo', 'Hausa': 'ha',
    'Wolof': 'wo', 'Bantu': 'bnt-pro', 'Kongo': 'kg',
    'Nahuatl': 'nah', 'Quechua': 'qu', 'Taino': 'tnq', 'Tupi': 'tpw',
    'Guarani': 'gn', 'Arawak': 'arw', 'Carib': 'car', 'Algonquian': 'alg-pro',
    'Ojibwa': 'oj', 'Cree': 'cr', 'Narragansett': 'xnt', 'Massachusett': 'wam',
    'Inuit': 'iu', 'Aleut': 'ale', 'Yupik': 'esu',
    'Dharuk': 'xdk', 'Dharug': 'xdk', 'Nyungar': 'nys', 'Afrikaans': 'af',
    'Egyptian': 'egy', 'Coptic': 'cop', 'Akkadian': 'akk', 'Sumerian': 'sux',
    'Armenian': 'hy', 'Georgian': 'ka', 'Basque': 'eu', 'Maltese': 'mt',
    'Romany': 'rom', 'Esperanto': 'eo',
    'Old English (Anglian)': 'ang', 'Anglo-Norman': 'xno',
}
LANGUAGE_PATTERN = re.compile(
    '(' + '|'.join(sorted(map(re.escape, LANGUAGES), key=len, reverse=True)) + r')\b')

# Merriam-Webster's inline markup. {it} carries source words; {et_link}
# names another English entry the word was formed from ("back-formation
# from {et_link|zipper:1|zipper:1}") and is read like an italic English
# word. "More at" ({ma}) and "see" ({dx_ety}) references are not sources.
ITALIC = re.compile(r'\{it\}(.*?)\{/it\}|\{et_link\|([^|}]*?)(?::\d+)?\|[^}]*\}')
CROSSREF = re.compile(r'\{ma\}.*?\{/ma\}|\{dx_ety\}.*?\{/dx_ety\}')
TOKEN = re.compile(r'\{[^}]*\}')

# Statements that are the whole etymology, with no source word to give.
IMITATIVE = re.compile(r'\b(imitative|onomatopoeic|echoic)\b', re.IGNORECASE)
UNKNOWN = re.compile(r'\borigin unknown\b', re.IGNORECASE)


def parse_etymology(text):
    """
    Roots from one Merriam-Webster etymology string.

    "Middle English, from Anglo-French {it}covert{/it}, from Latin
    {it}coopertus{/it}, past participle of {it}cooperire{/it}" gives
    xno:covert, la:coopertus, la:cooperire: each italic word is attributed to
    the most recent language named before it. A language with no italic word
    after it (the "Middle English" above) becomes a from:<code> flag, as the
    Wiktionary parse does for "From French." with no word.

    English words in italics with no language before them are the parts
    the word was formed from - "{it}cable{/it} + {it}cast{/it}" - and come
    back as components, for build_etymology.py to resolve against the roots
    it already has. Returns (roots, components, flags) with roots as
    (code, word) pairs.
    """
    text = CROSSREF.sub(' ', text)
    roots, flags = [], set()
    if IMITATIVE.search(text):
        flags.add('imitative')
    if UNKNOWN.search(text):
        flags.add('unknown')

    # Walk languages and italic words in order of appearance.
    events = []
    for m in LANGUAGE_PATTERN.finditer(text):
        events.append((m.start(), 'lang', LANGUAGES[m.group(1)]))
    for m in ITALIC.finditer(text):
        events.append((m.start(), 'word', m.group(1) or m.group(2) or ''))
    events.sort()

    current, seen_word = None, False
    components = []
    for _, kind, value in events:
        if kind == 'lang':
            if current and not seen_word:
                flags.add(f'from:{current}')
            current, seen_word = value, False
        else:
            word = clean_word(value)
            if not word:
                continue
            if current:
                roots.append((current, word))
                seen_word = True
            elif re.fullmatch(r"[a-z][a-z'-]*", word):
                # English so far: "{it}cable{/it} + {it}cast{/it}",
                # "alteration of {it}pester{/it}"
                components.append(word.strip('-'))
    if current and not seen_word:
        flags.add(f'from:{current}')

    unique = []
    for root in roots:
        if root not in unique:
            unique.append(root)
    return unique, [c for i, c in enumerate(components) if c and c not in components[:i]], flags


def clean_word(word):
    """One italic phrase to one root word: drop glosses and markup, keep the
    first word of a phrase unless the whole phrase is short."""
    word = TOKEN.sub('', word).strip()
    word = re.sub(r'\s*\([^)]*\)', '', word)
    # "tellur-, tellus" lists a stem and the full word: prefer the full word
    parts = [p.strip().strip('"\'') for p in word.split(',')]
    whole = [p for p in parts if p and not p.endswith('-')]
    word = (whole or parts)[0]
    word = word.strip('*').lower()
    if not word or word == '-' or len(word.strip("'-")) < 2:
        return ''
    if any(ch in word for ch in ':#{}|[]='):
        return ''
    return word


def entry_etymologies(entry, word):
    """The etymology strings of one API entry, if it is for this word."""
    if not isinstance(entry, dict):
        return []
    headword = entry.get('hwi', {}).get('hw', '').replace('*', '')
    if headword.lower() != word.lower():
        return []
    texts = []
    for piece in entry.get('et', []):
        if isinstance(piece, list) and len(piece) == 2 and piece[0] == 'text':
            texts.append(piece[1])
    return texts


def fetch(word, key, cache_dir):
    """The API's JSON for one word, from the cache when it is there.
    Returns (data, was_request)."""
    path = cache_dir / f'{word.lower()}.json'
    if path.exists():
        return json.loads(path.read_text(encoding='utf-8')), False
    url = ENDPOINT + urllib.parse.quote(word.lower()) + '?' + urllib.parse.urlencode({'key': key})
    for attempt in range(4):
        try:
            with urllib.request.urlopen(url, timeout=60) as response:
                raw = response.read().decode('utf-8')
            break
        except Exception as error:      # network hiccup: back off and retry
            if attempt == 3:
                raise
            time.sleep(2 ** attempt * 2)
    if raw.startswith('Invalid API key') or 'Not subscribed' in raw[:80]:
        raise SystemExit(f"API refused the key: {raw[:80]}")
    data = json.loads(raw)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
    return data, True


def extract(data, word):
    """(roots, flags) for a word from its API response. Several entries can
    share a headword (a noun and a verb); all their etymologies count, as
    the Wiktionary parse merges a page's etymology sections."""
    roots, components, flags = [], [], set()
    if not isinstance(data, list):
        return roots, components, flags
    for entry in data:
        for text in entry_etymologies(entry, word):
            more_roots, more_components, more_flags = parse_etymology(text)
            for root in more_roots:
                if root not in roots:
                    roots.append(root)
            for component in more_components:
                if component not in components and component != word.lower():
                    components.append(component)
            flags |= more_flags
    return roots, components, flags


def build_queue(scrabble_words, etymology, links):
    """
    One word per uncovered family, largest families first. Two uncovered
    words belong together when a propagation rule (other than the reverse
    ones, which would tie everything to everything) or a stated link points
    from one to the other; the family's representative is the word most of
    the others point to, then the shortest.
    """
    from collections import Counter, defaultdict
    from expand_inflections import candidate_bases, marker_only
    uncovered = sorted(w for w in scrabble_words
                       if w not in etymology or marker_only(etymology[w]))
    uncovered_set = set(uncovered)
    parent = {w: w for w in uncovered}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    pointed_at = Counter()
    for word in uncovered:
        targets = set()
        for rule, base in candidate_bases(word, scrabble_words):
            if base in uncovered_set and base != word and not rule.startswith('reverse'):
                targets.add(base)
        for target in links.get(word, {}).get('targets', []):
            if target in uncovered_set and target != word:
                targets.add(target)
        for target in targets:
            pointed_at[target] += 1
            parent[find(word)] = find(target)

    families = defaultdict(list)
    for word in uncovered:
        families[find(word)].append(word)

    def representative(members):
        return sorted(members, key=lambda w: (-pointed_at[w], len(w), w))[0]

    ordered = sorted(families.values(), key=lambda m: (-len(m), representative(m)))
    return {'heads': [representative(m) for m in ordered],
            'families': {representative(m): sorted(m) for m in ordered}}


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--build-queue', metavar='FILE',
                        help='write the lookup queue from etymology.json and exit')
    parser.add_argument('--dictionary', default=None,
                        help='Scrabble dictionary URL or local path (for --build-queue)')
    parser.add_argument('--key', help='Merriam-Webster Collegiate API key')
    parser.add_argument('--queue',
                        help='JSON file: {"heads": [WORD, ...]} in the order to look up')
    parser.add_argument('--limit', type=int, default=950,
                        help='new requests to make in this run (free tier: 1,000 a day)')
    parser.add_argument('--cache', default=str(HERE / 'mw_cache'),
                        help='directory of raw responses, one file per word')
    parser.add_argument('--delay', type=float, default=0.5,
                        help='seconds between requests')
    args = parser.parse_args()

    if args.build_queue:
        from expand_inflections import load_scrabble_dictionary, DICTIONARY_URL
        scrabble_words = load_scrabble_dictionary(args.dictionary or DICTIONARY_URL)
        etymology = json.loads((HERE / 'etymology.json').read_text(encoding='utf-8'))
        links_path = HERE / 'etymology_links.json'
        links = json.loads(links_path.read_text(encoding='utf-8')) if links_path.exists() else {}
        queue = build_queue(scrabble_words, etymology, links)
        Path(args.build_queue).write_text(json.dumps(queue, indent=0), encoding='utf-8')
        print(f"{len(queue['heads'])} families for "
              f"{sum(len(m) for m in queue['families'].values())} uncovered words "
              f"-> {args.build_queue}")
        return
    if not args.key or not args.queue:
        parser.error('--key and --queue are required for lookups')

    cache_dir = Path(args.cache)
    cache_dir.mkdir(parents=True, exist_ok=True)
    queue = json.loads(Path(args.queue).read_text(encoding='utf-8'))['heads']

    results = {}
    if OUTPUT_PATH.exists():
        results = json.loads(OUTPUT_PATH.read_text(encoding='utf-8'))

    requests_made = looked_up = with_roots = 0
    for word in queue:
        if requests_made >= args.limit:
            break
        data, was_request = fetch(word, args.key, cache_dir)
        if was_request:
            requests_made += 1
            time.sleep(args.delay)
        looked_up += 1
        roots, components, flags = extract(data, word)
        if roots or components or flags:
            results[word] = {'roots': [f'{lang}:{root}' for lang, root in roots],
                             'components': components, 'flags': sorted(flags)}
            if roots:
                with_roots += 1
        if looked_up % 100 == 0:
            print(f"  {looked_up} looked up, {requests_made} new requests, "
                  f"{with_roots} with roots")

    OUTPUT_PATH.write_text(json.dumps(results, indent=1, sort_keys=True, ensure_ascii=False) + '\n',
                           encoding='utf-8')
    remaining = len(queue) - looked_up
    print(f"Looked up {looked_up} words ({requests_made} new requests); "
          f"{with_roots} gave roots. {len(results)} words in {OUTPUT_PATH}. "
          f"{remaining} still queued.")


if __name__ == '__main__':
    main()

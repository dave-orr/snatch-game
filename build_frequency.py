#!/usr/bin/env python3
"""
Build frequency.json: how often each Scrabble word appears in English.

Each value is a Zipf frequency, log10 of occurrences per billion words, so
3.5 means about 3,000 per billion (1 in 300,000) and every whole step is a
factor of ten. The app turns it into one of six labels and a "1 in N" figure.
A word with no trustworthy measurement is left out of the file; the app shows
it as Obscure with no figure. frequency_sources.json records, for every word
not taken from wordfreq, what each corpus said.

Sources:

1. wordfreq (the Python package), a blend of subtitles, news, Wikipedia,
   books, web text and social media. It covers about half the Scrabble list
   and stops at one in a hundred million words (Zipf 1).
2. Three single corpora, for words below wordfreq's floor:
   - Google Books 1-grams, 2020 release, English books from 1970 on,
     lowercase forms only. About 1.1 trillion words.
   - English Wikipedia word counts, April 2023. About 2.5 billion words.
   - OpenSubtitles 2018 English word counts. About 730 million words.

The rules, each measured before it was adopted (see FREQUENCY.md):

- A word wordfreq has keeps wordfreq's value.
- A word wordfreq lacks takes the median of the three corpora, each put on
  wordfreq's scale by one offset. A corpus that never saw the word counts as
  sitting just below the rarest word it lists. The median needs two corpora
  to agree, so a spike in one - legal jargon in Google Books, an OCR misread
  such as DENNED for "deemed", a surname in Wikipedia - cannot carry a word.
- If the median is one of those stand-ins rather than a real count, the word
  was seen in one corpus at most and has no figure: it is left out.

Usage:
    python build_frequency.py --fetch corpora/     # about an hour, resumable
    python build_frequency.py --sources corpora/

--fetch downloads the 24 Google Books shards one at a time (265-710 MB
each), counts the Scrabble words in each and deletes it, keeping a small
JSON of counts per shard, and downloads the Wikipedia and OpenSubtitles
lists. It skips whatever is already there.
"""

import argparse
import gzip
import json
import math
import re
import statistics
import time
import urllib.request
from pathlib import Path

from expand_inflections import DICTIONARY_URL, load_scrabble_dictionary

HERE = Path(__file__).parent
FREQUENCY_PATH = HERE / 'frequency.json'
SOURCES_PATH = HERE / 'frequency_sources.json'

BOOKS_URL = 'https://storage.googleapis.com/books/ngrams/books/20200217/eng/'
BOOKS_SHARDS = 24
# Books from before 1970 carry spellings and senses today's players do not
# use, and the OCR of older type turns "and" into ARID.
BOOKS_FROM_YEAR = 1970
# A word in fewer books than this is one author's term or an OCR slip, and
# Google Books is treated as not having seen it.
MIN_BOOKS_VOLUMES = 20

LISTS = {
    'wikipedia': 'https://raw.githubusercontent.com/IlyaSemenov/wikipedia-word-frequency/'
                 'master/results/enwiki-2023-04-13.txt',
    'subtitles': 'https://raw.githubusercontent.com/hermitdave/FrequencyWords/'
                 'master/content/2018/en/en_full.txt',
}
CORPORA = ('books', 'wikipedia', 'subtitles')

# wordfreq lists nothing below this.
WORDFREQ_FLOOR = 1.0
# Offsets are fitted on words every source knows well, clear of any floor.
CALIBRATION_RANGE = (2.0, 5.0)
# A corpus that never saw a word stands in at this far below its rarest
# listed count, about half a listing.
UNSEEN_MARGIN = 0.3


def zipf(count, total):
    return math.log10(count / total * 1e9)


# --- fetching --------------------------------------------------------------

def download(url, path, attempts=6):
    """Download to path, resuming a partial file, and check the size."""
    with urllib.request.urlopen(urllib.request.Request(url, method='HEAD'), timeout=60) as r:
        want = int(r.headers['Content-Length'])
    for attempt in range(attempts):
        have = path.stat().st_size if path.exists() else 0
        if have == want:
            return
        request = urllib.request.Request(url, headers={'Range': f'bytes={have}-'} if have else {})
        try:
            with urllib.request.urlopen(request, timeout=120) as r, open(path, 'ab') as out:
                while chunk := r.read(1 << 20):
                    out.write(chunk)
        except OSError:
            time.sleep(5 * (attempt + 1))
    if path.stat().st_size != want:
        raise SystemExit(f"could not download {url}: {path.stat().st_size} of {want} bytes")


def count_shard(path, scrabble_words):
    """
    Occurrences from BOOKS_FROM_YEAR on of each Scrabble word in one shard,
    kept apart by case: lc (house), cap (House), up (HOUSE), plus lc_vol,
    the number of books the lowercase form appears in.
    """
    variant = {}
    for word in scrabble_words:
        lower = word.lower()
        variant[lower] = (lower, 'lc')
        variant[lower.capitalize()] = (lower, 'cap')
        variant[word] = (lower, 'up')
    counts = {}
    with gzip.open(path, 'rt', encoding='utf-8', errors='replace') as f:
        for line in f:
            tab = line.find('\t')
            hit = variant.get(line[:tab])
            if not hit:
                continue
            word, kind = hit
            matches = volumes = 0
            for entry in line[tab + 1:].split('\t'):
                year, match_count, volume_count = entry.split(',')
                if int(year) >= BOOKS_FROM_YEAR:
                    matches += int(match_count)
                    volumes += int(volume_count)
            if matches:
                record = counts.setdefault(word, {})
                record[kind] = record.get(kind, 0) + matches
                if kind == 'lc':
                    record['lc_vol'] = record.get('lc_vol', 0) + volumes
    return counts


def fetch(out_dir, scrabble_words):
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, url in LISTS.items():
        path = out_dir / f'{name}.txt'
        if not path.exists():
            print(f"  downloading the {name} list")
            download(url, path)
    totals = out_dir / 'totalcounts-1.txt'
    if not totals.exists():
        download(BOOKS_URL + 'totalcounts-1', totals)
    for i in range(BOOKS_SHARDS):
        name = f'1-{i:05d}-of-{BOOKS_SHARDS:05d}.gz'
        result = out_dir / f'{i:05d}.json'
        if result.exists():
            continue
        shard = out_dir / name
        print(f"  Google Books shard {i + 1} of {BOOKS_SHARDS}")
        download(BOOKS_URL + name, shard)
        counts = count_shard(shard, scrabble_words)
        result.write_text(json.dumps({'shard': f'{i:05d}', 'counts': counts}))
        shard.unlink()


# --- loading ---------------------------------------------------------------

def load_books(corpora_dir):
    """Merged Google Books counts, and the total words from BOOKS_FROM_YEAR."""
    corpora_dir = Path(corpora_dir)
    merged, shards = {}, 0
    for path in sorted(corpora_dir.glob('[0-9]*.json')):
        shards += 1
        for word, record in json.loads(path.read_text())['counts'].items():
            into = merged.setdefault(word.upper(), {})
            for key, value in record.items():
                into[key] = into.get(key, 0) + value
    if shards != BOOKS_SHARDS:
        raise SystemExit(f"{corpora_dir} holds {shards} of {BOOKS_SHARDS} Google Books "
                         f"shards; run --fetch first")
    total = 0
    for entry in (corpora_dir / 'totalcounts-1.txt').read_text().split():
        year, match_count = entry.split(',')[:2]
        if int(year) >= BOOKS_FROM_YEAR:
            total += int(match_count)
    return merged, total


def load_list(path, scrabble_words):
    """
    Counts from a "word count" list, and the list's total words. Only plain
    lowercase ASCII tokens count: the Wikipedia list also has "houſe", whose
    long s upper-cases to HOUSE and once replaced HOUSE's count with 4.
    """
    wanted = {w.lower() for w in scrabble_words}
    counts, total = {}, 0
    for line in open(path, encoding='utf-8', errors='replace'):
        parts = line.split()
        if len(parts) != 2 or not parts[1].isdigit():
            continue
        total += int(parts[1])
        if re.fullmatch(r'[a-z]+', parts[0]) and parts[0] in wanted:
            word = parts[0].upper()
            counts[word] = counts.get(word, 0) + int(parts[1])
    return counts, total


# --- blending --------------------------------------------------------------

def build(scrabble_words, corpora_dir):
    import wordfreq

    wf = {w: wordfreq.zipf_frequency(w.lower(), 'en') for w in scrabble_words}

    books, books_total = load_books(corpora_dir)
    raw = {'books': {w: zipf(r['lc'], books_total) for w, r in books.items()
                     if r.get('lc_vol', 0) >= MIN_BOOKS_VOLUMES}}
    for name in LISTS:
        counts, total = load_list(Path(corpora_dir) / f'{name}.txt', scrabble_words)
        raw[name] = {w: zipf(c, total) for w, c in counts.items()}
    rarest = {'books': zipf(40, books_total)}   # Google lists nothing seen under 40 times
    for name in LISTS:
        rarest[name] = min(raw[name].values())

    # Each corpus is books, or encyclopedia, or speech, and each was counted
    # its own way; one offset per corpus puts it on wordfreq's scale.
    low, high = CALIBRATION_RANGE
    offset = {name: statistics.median(wf[w] - v for w, v in raw[name].items()
                                      if low <= wf[w] <= high)
              for name in CORPORA}
    unseen = {name: rarest[name] + offset[name] - UNSEEN_MARGIN for name in CORPORA}

    frequency, sources = {}, {}
    for word in sorted(scrabble_words):
        if wf[word] >= WORDFREQ_FLOOR:
            frequency[word] = round(wf[word], 2)
            continue
        readings = []            # (value, measured)
        for name in CORPORA:
            if word in raw[name]:
                readings.append((raw[name][word] + offset[name], True))
            else:
                readings.append((unseen[name], False))
        if not any(measured for _, measured in readings):
            continue
        value, measured = sorted(readings)[1]
        sources[word] = [round(v, 2) if m else None for v, m in readings]
        if measured:
            frequency[word] = round(value, 2)
    return frequency, sources, offset, unseen


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--fetch', metavar='DIR',
                        help='download and count the corpora into DIR')
    parser.add_argument('--sources', metavar='DIR', help='directory --fetch filled')
    parser.add_argument('--dictionary', default=DICTIONARY_URL,
                        help='Scrabble dictionary URL or local path')
    args = parser.parse_args()
    scrabble_words = load_scrabble_dictionary(args.dictionary)

    if args.fetch:
        fetch(Path(args.fetch), scrabble_words)
        return
    if not args.sources:
        parser.error('pass --sources DIR (after --fetch DIR)')

    frequency, sources, offset, unseen = build(scrabble_words, args.sources)

    FREQUENCY_PATH.write_text(json.dumps(frequency, separators=(',', ':'), sort_keys=True) + '\n')
    SOURCES_PATH.write_text(
        json.dumps({'columns': list(CORPORA),
                    'note': 'Zipf values on wordfreq\'s scale, null where the corpus never saw '
                            'the word. Words taken from wordfreq are not listed.',
                    'words': sources},
                   separators=(',', ':'), sort_keys=True) + '\n')

    from_corpora = sum(1 for w in sources if w in frequency)
    print("offsets to wordfreq's scale: " +
          ', '.join(f'{name} {offset[name]:+.2f}' for name in CORPORA))
    print(f"{len(frequency):,} of {len(scrabble_words):,} words have a frequency "
          f"({100 * len(frequency) / len(scrabble_words):.1f}%): "
          f"{len(frequency) - from_corpora:,} from wordfreq, {from_corpora:,} from the corpora")
    print(f"seen in one corpus only, no figure: {len(sources) - from_corpora:,}; "
          f"not seen at all: {len(scrabble_words) - len(frequency) - (len(sources) - from_corpora):,}")


if __name__ == '__main__':
    main()

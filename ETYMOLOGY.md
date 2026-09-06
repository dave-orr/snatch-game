# Etymology data

How `etymology.json` is built, and the decisions behind it. Thresholds are
explained where they are defined; this file records what was measured, what was
tried and rejected, and what a rebuild has to redo.

## Rebuilding

```
curl -O https://dumps.wikimedia.org/enwiktionary/latest/enwiktionary-latest-pages-articles.xml.bz2
rm -f etymology_sources.json
python build_etymology.py enwiktionary-latest-pages-articles.xml.bz2 --save-scan scan.json.gz
python expand_inflections.py                                            # propagate
python check_prefix_review.py                                           # see below
```

Order matters. `build_etymology.py` overwrites `etymology.json` with parsed
entries only, so run the expansion straight after with no flags, and delete a
stale `etymology_sources.json` first. `--rebuild` is for re-expanding *without*
re-parsing; run against fresh parse output it would drop entries the parse had
just produced.

Reading the dump takes about 40 minutes. `--save-scan` keeps what was read;
passing that file in place of the dump reruns only the resolution, in
seconds, which is how the resolution rules below were tested one at a time.

The current data came from the dump dated **2026-08-04**. `latest` moves, so a
rebuild will not reproduce these numbers exactly. From the same dump the build
is deterministic.

## What the files hold

| file | contents |
|---|---|
| `etymology.json` | word to list of `language:root` |
| `etymology_sources.json` | for each propagated word, the rule and base word it came from. Words absent from it were parsed |
| `etymology_links.json` | for each word the parse left without roots, the playable words its page ties it to. The expansion follows these once propagation covers a target |
| `prefix_pair_review.json` | hand-checked verdicts for the root pairs `etymology.js` matches by prefix |

Coverage as built: 168,919 of 178,691 words (94.5%), of which 162,307 parsed
and 6,612 propagated. 764 of those carry only a marker (imitative, or a
source language with no word) rather than a root, so coverage by real roots
is 168,155 words, 94.1%. 9,772 words have nothing.

How it got here, by real-root coverage: 86.5% from the original parse, 92.3%
after the parser learned form-of definitions, foreign-language sections and
prose, 94.1% after the template gaps, derived-terms lists, definition links
and link-following described below. The last round added 3,171 words at the
parse and cost 249: 248 whose only "root" had been a classifying suffix such
as `-ITE`, and DUXELLES, whose root was the French article `d'`.

Two entry shapes carry no root. `imitative:-` means Wiktionary calls the word
imitative; `french:-` means the entry says "From French" and names no word.
Both display as the language alone and never count as a shared root.

## Two stages

**Parsing** (`build_etymology.py`) reads the dump page by page. For a word it
uses, in order of preference:

1. the etymology section of its lowercase English page;
2. the English page under another casing (CHUNNEL, MIRANDIZE, PIG's page
   `PIG`), only when the word is playable;
3. for a playable lowercase word with no English section at all, the section
   of the language Wiktionary files it under (Scots first, then Middle
   English, Latin, the Romance languages and so on). The word itself in that
   language is its root, as `{{bor}}` would have recorded.

A lower tier only fills a gap; it never overrides a higher one. Within a tier
a page with roots beats one without. This matters because several titles
share a lowercase key: the page `pIg` (an abbreviation) once overwrote `pig`
and lost the whole PIG family. Markers come only from tier 1, because the
Chinese city *Wanning* is not evidence about the English word WANNING.

Within an etymology section the parser reads:

- the `der`/`inh`/`bor` family with its `-lite` variants, `uder`, `lbor`,
  `ubor`, the calques, and the structured `{{etymon}}`/`{{ety}}` forms
  including every kind chained inside one call (`:af ... :calque ...`). Only
  positional arguments count, because named ones (`tr=`, `sc=`, `id=`) were
  once read as the word and produced roots like `hindi:tr=janjal`.
  `{{semantic loan}}` is deliberately not read: HAVE took a sense from French
  *avoir*, not the word;
- the affix family (`compound`, `confix`, `suffix`, `af`, `blend`, `clipping`,
  `surf` and friends), which names English base words. Those are resolved
  recursively, so QUINIC reaches Quechua *kina-kina* through QUININE. A
  foreign part among them (`{{af|en|la:cāseus|-ous}}`) gets a page of its own
  holding that root, so it resolves alongside the English parts instead of
  silencing them. A resolution truncated by depth or a cycle is not cached,
  and the depth check comes before the cache, so each word's answer depends
  only on the dump and not on the order words were visited in. The affix
  pages themselves contribute their own roots and nothing else, or every word
  ending in `-ON` inherits carbon from the back-formation note on that page;
- `{{doublet}}` targets, as components: LIQUEUR and LIQUOR share a source by
  definition. Like all components they matter only when the page states no
  root of its own;
- form-of templates in the definitions (`plural of`, `alternative form of`,
  `en-third-person singular of`, ...), which link a page to the word it is a
  form of. The target is the first positional argument; a named one can
  precede it (`from=Non-Oxford British spelling` on RECOGNISE);
- prose. "From Middle English ''helthe''" is read when it is in the
  `From <Language> ''word''` shape; an English word after "From", "Derived
  from" or "Shortening of" is followed as a component; sentences opening with
  "Compare", "Cognate with" or "Related to" are dropped first, since a cognate
  is not an ancestor;
- `{{m}}` mentions, used only when nothing else yielded a root, and never on
  affix pages;
- language-only statements ("From French.") and imitative markers, which
  produce the marker entries above.

Two further sources stand in only for a page that states nothing about its
origin: no roots, no components, no form-of target, and no "unknown".

- **Derived terms.** A base word's page lists the words formed from it, and
  for a word whose own page has no etymology that listing is the only thing
  Wiktionary says: TELLURIUM lists TELLURITE. The lists carry topical entries
  too (BUDDLEIA under BUTTERFLY, LEPIDOPTERIST under BUTTERFLY), so a listing
  counts only when the word visibly contains the base: its stem, or the same
  opening four letters (PSORIATIC, PSORIASIS). About 6% of listings fail that
  test. Blind samples: 25 of 30 before the filter, 30 of 30 after.
- **Definition links.** "Of or pertaining to the [[ileum]]", "the state of
  being [[exorbitant]]". The link counts only when the headword shares an
  opening stem of five or more letters that reaches within four letters of
  the link's end, so ESCHATOLOGICAL takes eschatology and OSMOLE does not
  take mole. Blind samples: 23 of 23 on no-etymology pages, 29 of 30 among
  everything it added.

Both are kept apart from stated components in the scan, so either can be
switched off at resolution.

Grammatical and classifying affixes (`un-`, `re-`, `-ness`, `-ance`, `-ite`,
`-osis`, `-oid`) are dropped as roots, by a hand-kept list (`NOISE_AFFIXES`):
sharing one tells a player nothing, and a mineral named after a person had
`-ITE` as its only root, which made BARITE and LUCITE relatives. Contentful
combining forms (`-logy`, `bio-`, `-phobia`) are kept.

Both scripts iterate words in sorted order. They used to iterate sets, and
two runs of the same dump disagreed on a few hundred words because Python
seeds string hashing per process. A rebuild from the same dump now reproduces
the data exactly.

The dump text is HTML-escaped. Not unescaping it before parsing left
`&lt;t:...&gt;` annotations inside 11,383 roots.

**Propagation** (`expand_inflections.py`) first follows the links the parse
left unresolved, then fills the remaining gaps morphologically, recording
provenance for every entry. The parse resolves a form-of or component link
only through parsed roots, so FEOFFOR ("alternative form of feoffer") stayed
blank while FEOFFER was covered by a suffix rule; following the links after
each pass closes that, with provenance `link:stated`, `link:derived` or
`link:definition`. Marker-only words are
treated as blanks: a marker never blocks a real root from arriving by
propagation, and markers propagate to inflections only in a final pass, so
BUBBLES inherits BUBBLE's imitative marker only if nothing better was found.

## Rejected, with the measurements

Recorded because the numbers are not obvious and someone will otherwise try
them again.

- **Compound splitting** (a word is two covered words joined). Measured 88%
  correct at every threshold tried, including requiring both halves to be six
  letters. The errors are structural rather than tunable: the split is "unique"
  precisely *because* the correct boundary's halves are not both covered, giving
  MILKSHAKES = MILKS + HAKES and LOADSTONES = LOADS + TONES. Roughly 16% of what
  looks like a compound is a single morpheme that happens to be two words
  concatenated (PLANARIA = PLAN + ARIA, VASELINES = VASE + LINES). Worth about
  4,000 words if you accept that rate.
- **`-ITE` as a derivational suffix.** Half its matches were wrong; mineral and
  trade names come from proper nouns, not the English word left behind
  (BARITE > BARE, LUCITE > LUCE).
- **`PRO-` and `AB-` as prefixes.** 43% and 25% wrong. Both attach to Latin
  stems that are not English words.
- **`CE` <-> `SE` spelling variants.** 60-70% wrong (ASCENT > ASSENT,
  SENSOR > CENSOR).
- **Filtering affixes by frequency rather than meaning.** Counted across
  languages the two groups interleave - `SUB-` 362, `UNDER-` 336, `DE-` 333
  against `-LOGIA` 350, `BIO-` 268, `-OID` 218 - so no threshold separates
  "shared by everything" from "worth showing". Hence the hand-kept
  `NOISE_AFFIXES`.
- **Reading other-language sections for capitalized pages.** German
  capitalizes every noun, and its entries for PIXEL, REPRESSOR and FLIRT
  labelled English words as German borrowings when German borrowed them from
  English. Foreign sections are read only for lowercase titles, and not when
  the page is itself an inflected form (French *russifies*).
- **Falling back from a hyphenated component to the bare word** when the
  affix page yields nothing (`-chrome` to *chrome*). `-ONE` and `-ON` have
  pages that state nothing parseable, and the fallback gave 386 chemical
  names roots meaning "one" and "on". Restricted to affixes with no page at
  all it gained three words, so it is gone.
- **Reading `{{semantic loan}}` as descent.** HAVE took a sense from French
  *avoir* and BLACK one from Cantonese; the words themselves are native.
  Reading it had given 97 BLACK compounds a Cantonese root.
- **Unrestricted prefix matching** in the game's comparison. About 60% wrong;
  see below.

## Other sources

Everything above comes from the Wiktionary dump, and almost everything the
parse still misses is in the dump too, in shapes not yet read (see the residue
below). Sources that would add information Wiktionary lacks were considered:

- kaikki.org (wiktextract's parsed Wiktionary) would replace this parser with
  a maintained one, but adds no data Wiktionary does not have;
- Merriam-Webster's Collegiate API - the Scrabble list is Merriam-Webster's,
  so it covers the words - but the free tier is per-word lookup, not bulk;
- Wikidata has lexemes with etymology links for a small fraction of English;
- Etymological WordNet and MorphyNet are themselves derived from Wiktionary;
- Skeat's and the Century Dictionary are public domain, and OCR;
- Etymonline has no bulk licence.

None of them was reachable from the environment the data was built in, which
allows only en.wiktionary.org, dumps.wikimedia.org and raw.githubusercontent.com.

## Comparing roots

`rootsMatch` in `etymology.js` decides whether two roots count as the same, and
gates steal validity: a steal whose words share a root is illegal.

Roots match when one is a **suffix** of the other, which is how Latin and Greek
build words (*fixus* inside *suffixus*). Matching by **prefix** as well is
correct in principle - WATER and WATERY share a stem - but unrestricted it is
about 60% wrong, because a short root starts many unrelated longer ones
(`enm:dri` starts *drinkere*, `latin:qua` starts *quadriceps*). It would newly
reject 5,610 of 8,654 steal-compatible pairs.

Prefix matching is therefore limited to roots of 7+ letters, where the error
rate collapses. Every pair that rule matches has been checked by hand, in
four rounds as the data grew: 1,018 pairs, 1,009 genuine, 9 not. The unrelated ones are listed in `UNRELATED_PREFIX_PAIRS` because no
length rule separates them (chance/chancellor, hostile/hostler, market/march,
content/contentious). Note that `old_french:chancel ~ chancelerie` *is* related
while `enm:chaunce ~ chaunceler` is not, which is why this was reviewed rather
than patterned.

Affix hyphens are stripped before comparing, or `-phobia` never matches the
*hydrophobia* containing it.

## After a rebuild

Run `check_prefix_review.py`. It lists the prefix pairs that are new since the
review - only those need checking - and fails if the review and
`UNRELATED_PREFIX_PAIRS` have drifted apart. Add verdicts for new pairs to
`prefix_pair_review.json`, and any unrelated ones to `etymology.js`.

The propagation rules do not need re-review; their thresholds were set from
error rates that should hold on comparable data. Sampling after a rebuild is
still worthwhile. Blind samples of the current data, by the path that
produced the entry: template fixes 28 of 30, derived-terms listings 29 of
30, definition links 28 of 30, followed links right as links in every case
sampled (a few inherit a wrong base, CHIVVY from CHIVE). The misses are
almost all pages with several senses merged, below. Earlier rounds measured
parsed entries at about 27 in 30 and propagated ones at about 19 in 20.

`--save-scan` makes this cheap: the scan is read once, and each resolution
rule can be switched off and the difference sampled in seconds. Every rule
above was accepted or rejected that way.

## Known weak spots

- **Pages with several etymologies are merged.** TUT, MARE, TRAIN, HUH and
  WHOOF each have two or more unrelated English entries, and the parser reads
  all of them into one word; FIN carries both the fish's fin and the slang
  five-dollar bill. This is the largest error class among parsed entries, and
  every fallback that resolves through a base inherits it (ATTABOY gets the
  flour ATTA through BOY). A fix would prefer Etymology 1 or the sense the
  Scrabble list means.
- **A form-of chain can land on the wrong word.** TENSIVE is "tens + -ive"
  on its page, and TENS is the plural of TEN, so NORMOTENSIVE descends from
  the number ten.
- `-AGE` propagates at about 92% (MIRAGE > MIRE, RAVAGE > RAVE). Tightening it
  costs roughly 40 correct entries to remove 5 errors.
- Reverse propagation mis-fires on words ending in `-I` whose `-ES` form belongs
  to a `-Y` word (DENI < DENIES), 4 cases in 730.
- SETA > SETON and UNCI > UNCO survive the classical-plural guards.
- Words Wiktionary marks imitative (71 of them, 322 once
  inflections inherit the marker) carry `imitative:-` rather than a root.
  Imitative describes how a word was formed rather than what it descends from:
  BUZZ and HISS were each coined independently. Count them separately when
  quoting coverage.
- Words whose only Wiktionary information was a grammatical or classifying
  suffix (`-ance`, `-ite`, `-osis`) have no entry, since the suffix joined
  `NOISE_AFFIXES`. About 280 words, none of which had a real root; LUCITE
  and FLIMSY are now blank rather than misleading.
- The 297 words Wiktionary marks `{{unk}}` are deliberately not marked.
  "Origin unknown" and "we have no data" both read as "unknown" to a player.

## What is still missing

Of the 9,772 uncovered words, by what the dump has for them:

| count | what the dump has |
|---|---|
| 3,663 | English page, no etymology, defined as a form of an uncovered word |
| 2,391 | English page with no etymology section |
| 1,884 | English page with an etymology section the parser could not read |
| 935 | no Wiktionary page (or a page the parser skipped) |
| 289 | English page, etymology marked unknown |
| 247 | had only a classifying suffix (-ITE, -OSIS) for a root |
| 185 | capitalized English page only |

The form-of words fall with their bases, so the parser's remaining work is
the 1,884 unreadable sections and whatever the 2,391 no-etymology pages link
to that the definition rule does not yet catch. The rest is what Wiktionary
does not know: drug and trade names, and words it marks unknown. That is the
part where another source (Merriam-Webster's Collegiate API, whose list this
is) would have to come in.

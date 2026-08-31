# Etymology data

How `etymology.json` is built, and the decisions behind it. Thresholds are
explained where they are defined; this file records what was measured, what was
tried and rejected, and what a rebuild has to redo.

## Rebuilding

```
curl -O https://dumps.wikimedia.org/enwiktionary/latest/enwiktionary-latest-pages-articles.xml.bz2
python build_etymology.py enwiktionary-latest-pages-articles.xml.bz2   # parse
python expand_inflections.py                                            # propagate
python check_prefix_review.py                                           # see below
```

Order matters. `build_etymology.py` overwrites `etymology.json` with parsed
entries only, so run the expansion straight after with no flags, and delete a
stale `etymology_sources.json` first. `--rebuild` is for re-expanding *without*
re-parsing; run against fresh parse output it would drop entries the parse had
just produced.

The current data came from the dump dated **2026-08-04**. `latest` moves, so a
rebuild will not reproduce these numbers exactly.

## What the files hold

| file | contents |
|---|---|
| `etymology.json` | word to list of `language:root` |
| `etymology_sources.json` | for each propagated word, the rule and base word it came from. Words absent from it were parsed |
| `prefix_pair_review.json` | hand-checked verdicts for the root pairs `etymology.js` matches by prefix |

Coverage as built: 154,592 of 178,691 words (86.5%), of which 73,486 parsed and
81,106 propagated.

## Two stages

**Parsing** (`build_etymology.py`) reads etymology templates from the dump.
Beyond the `der`/`inh`/`bor` family it reads `uder`, `lbor`, the structured
`{{etymon}}`/`{{ety}}` forms, and the affix family (`{{compound}}`,
`{{confix}}`, `{{suffix}}`, `{{af}}`). Affix templates name *English* base
words, so QUINIC resolves through QUININE to Quechua *kina-kina*. That
resolution is what makes the parse worth more than its 73,486 direct hits.

**Propagation** (`expand_inflections.py`) fills gaps morphologically, recording
provenance for every entry. About 61% of the words the parse misses do have a
Wiktionary etymology in some form; the rest Wiktionary genuinely lacks.

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
- **Unrestricted prefix matching** in the game's comparison. About 60% wrong;
  see below.

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
rate collapses. Every pair that rule matches - 879 of them - was checked by
hand: 871 genuine, 8 not, and the 8 are listed in `UNRELATED_PREFIX_PAIRS`
because no length rule separates them (chance/chancellor, hostile/hostler,
market/march). Note that `old_french:chancel ~ chancelerie` *is* related while
`enm:chaunce ~ chaunceler` is not, which is why this was reviewed rather than
patterned.

Affix hyphens are stripped before comparing, or `-phobia` never matches the
*hydrophobia* containing it.

## After a rebuild

Run `check_prefix_review.py`. It lists the prefix pairs that are new since the
review - only those need checking - and fails if the review and
`UNRELATED_PREFIX_PAIRS` have drifted apart. Add verdicts for new pairs to
`prefix_pair_review.json`, and any unrelated ones to `etymology.js`.

The propagation rules do not need re-review; their thresholds were set from
error rates that should hold on comparable data. Sampling `etymology_sources.json`
after a rebuild is still worthwhile: a blind sample of 60 was 59 correct when
these rules were set.

## Known weak spots

- `-AGE` propagates at about 92% (MIRAGE > MIRE, RAVAGE > RAVE). Tightening it
  costs roughly 40 correct entries to remove 5 errors.
- Reverse propagation mis-fires on words ending in `-I` whose `-ES` form belongs
  to a `-Y` word (DENI < DENIES), 4 cases in 730.
- SETA > SETON and UNCI > UNCO survive the classical-plural guards.
- 109 words Wiktionary marks imitative (BUBBLE among them) are not written to
  `etymology.json`. Writing them would show "Etymology: imitative" instead of
  "unknown", but would also make every imitative word share a root during
  steals.

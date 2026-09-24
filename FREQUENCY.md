# Frequency data

How `frequency.json` is built, and the decisions behind it. As with
`ETYMOLOGY.md`, this records what was measured, what was tried and rejected,
and what a rebuild has to redo.

## What the files hold

| file | contents |
|---|---|
| `frequency.json` | word to Zipf frequency, for every word with a trustworthy figure |
| `frequency_sources.json` | for each word below wordfreq's floor, what Google Books, Wikipedia and OpenSubtitles each said, on wordfreq's scale, or null where the corpus never saw it; and for each word lowered as foreign, its wordfreq value and the language it belongs to |

A Zipf frequency is log10 of occurrences per billion words. 3.5 is about 3,000
per billion, one word in 300,000, and each whole step is a factor of ten. The
app derives everything it shows from that one number:

| label | Zipf | one word in | words |
|---|---|---|---|
| Everyday | 5 and up | fewer than 10,000 | 995 |
| Common | 4 to 5 | 10,000 to 100,000 | 5,453 |
| Uncommon | 3 to 4 | 100,000 to 1 million | 16,399 |
| Rare | 2 to 3 | 1 to 10 million | 30,332 |
| Very rare | 1 to 2 | 10 to 100 million | 47,084 |
| Obscure | below 1, or absent | more than 100 million | 78,428 |

The "1 in N" figure is 10 to the power (9 minus Zipf), rounded to two
significant figures. Every word gets a label. 138,595 of 178,691 (77.6%) also
get a figure. The other 40,096 are Obscure with no figure: 7,556 no source has
seen, and 32,540 were seen but not well enough to place - 26,494 by one corpus
only and 6,046 by two that disagreed widely (see below).

## Rebuilding

```
pip install wordfreq==3.1.1
python build_frequency.py --fetch corpora/      # about an hour, resumable
python build_frequency.py --sources corpora/
```

`--fetch` streams the 24 Google Books shards one at a time (265-710 MB each),
keeps only a small file of counts from each, and downloads the two word lists.
The current data used wordfreq 3.1.1, Google Books' 2020 release, Wikipedia
counts from April 2023 and OpenSubtitles 2018.

## Sources and rules

**wordfreq first.** The `wordfreq` package blends subtitles, news, Wikipedia,
books, web text and social media into one figure, which is better than any
single corpus. A word it lists keeps its value. It stops at Zipf 1, one word
in a hundred million, and lists 92,728 of the Scrabble words (51.9%). The rest
are almost all 7 to 15 letters long: inflections and derivatives of rare
words.

**Except foreign words.** Spanish, Portuguese, Italian and Malay turn up
inside English text, and every English source counts them: HOY is Spanish
"today", CASA "house", DATO a Malay title. A word at least two Zipf steps more
common in one of those languages than in English takes the lower of
wordfreq's value and its Google Books lowercase count; books print foreign
words less and capitalise them more. Words used far more in subtitles than in
Wikipedia (by 0.9 steps or more) are spared, because they are spoken English
that books undercount: without that, UM, CIAO and HO dropped a label. This
lowers 490 words and changes the label of 218, 214 of them by one step. Of
219 changes read, about 86% were clearly better, 10% toss-ups, and 4% perhaps
one label low - English loanwords such as FORTE, MANA, ROTI and TOQUE.

**Below wordfreq's floor, the median of three corpora.** Each corpus is put on
wordfreq's scale by one offset, fitted on words both know well:

| corpus | size | offset |
|---|---|---|
| Google Books, English books from 1970, lowercase | 1.1 trillion words | +0.08 |
| Wikipedia, April 2023 | 2.5 billion words | -0.02 |
| OpenSubtitles 2018 | 730 million words | +0.32 |

A corpus that never saw a word stands in at half a listing below the rarest
word it lists. If the median of the three is a real count, that is the word's
figure. If it is one of those stand-ins - one corpus saw the word, or two saw
it and disagreed across the missing one's limit - the word gets no figure.

The median was chosen by testing it on words wordfreq does know, near its
floor, where the answer is known:

| estimate | same label as wordfreq, Zipf 1-2.5 | same label, Zipf 1-1.5 | median bias |
|---|---|---|---|
| Google Books alone | 61% | 66% | +0.14 |
| mean of the three | 80% | 90% | +0.18 |
| median of the three | 78% | 82% | +0.06 |

The mean scores higher on the narrow band only because it runs high, and that
band's answers all sit on one side of the Obscure boundary. The median is
nearly unbiased, and because it needs two corpora to agree it cannot be
carried by a spike in one: legal jargon in Google Books, an OCR misread, a
surname in Wikipedia, slang in subtitles.

Google Books needs a word in at least 20 books from 1970 on to count as having
seen it. That filter changes no label; it only keeps one author's coinage or
a scanning slip from producing a figure.

## Rejected, with the measurements

- **Google Books alone below wordfreq's floor.** It would have lifted 556
  words to Rare or above that wordfreq never saw. The top of that list was
  government and legal text, ASSIGNORS and GRIEVANT ranking with SNATCH, and
  OCR misreads: DENNED is "deemed", CITHER "either", SCRIES "series", QUIRED
  "required" split across a line. The median puts all of them at Obscure or
  the edge of Very rare.
- **Scaling wordfreq's figure by a word's lowercase share in Google Books**,
  to stop names inflating words like JOHN. It would have changed the label of
  6,948 words, led by GOD, YES, OH, UNITED, MARCH and ENGLISH. Capitals in
  books mark sentence starts, titles, months and reverence as often as names,
  so the share cannot tell a name from a word.
- **Estimating an unseen inflection from its base word**, less a measured
  discount per ending (a plural -S is about 4 times rarer than its base, -NESS
  about 90 times). Tested on 23,223 unseen words that Wikipedia does count, it
  gave the right label 39% of the time, and 78% at best with a tuned cutoff,
  against 80% for simply calling unseen words Obscure. Words the corpora miss
  are missed because almost nobody writes them: INELIGIBLE is fairly common,
  INELIGIBLES is not.
- **A figure for the 32,540 words the median cannot place.** Tested by
  pretending Wikipedia and subtitles missed words they had seen, the most
  accurate figure is the stand-in itself (right label 98% of the time, within
  0.3 steps about 85%), but that gives every such word one of two figures, 1 in
  710 million or 1 in 1.7 billion, which says nothing the label does not.
  Google Books capped at the missing corpora's limit keeps some per-word
  variation but was less accurate, and a model of each corpus's noise was
  worse still. Below the smaller corpora's limits nothing can check a
  per-word figure, so none is given.
- **Google Books fiction only**, to avoid the legal and government text. As
  the Books vote in the median it gave the right label 66.5% of the time,
  against 78.0% for all books: it is a ninth the size and skews to narrative
  (it puts SNATCH a step higher). The median already neutralises the jargon.
- **Counting the books a word appears in** rather than its occurrences. Alone,
  it matched wordfreq's label 51% of the time against 61%.
- **Checking inflected forms against their base.** 1,513 forms sit more than a
  label above their base, but nearly all are right: CHANGING above CHANG, GREEN
  above GREE, where the matched base is a different word.
- **Google's trillion-word web list.** Reachable, but it keeps only the top
  333,000 words, so it stops near wordfreq's own floor.
- **Reading the Wikipedia list by upper-casing every entry.** It has "houſe"
  with a long s, which upper-cases to HOUSE and replaced HOUSE's count with 4.
  Only plain lowercase ASCII entries are read.

## Checks on the result

- **Blind samples.** First 20 random words per label, then 200 per label with
  a fresh seed, 1,320 in all, read without their figures and every doubtful
  word then checked against the corpora. About 97% look right. The rest fall
  into two groups, below: 21 of the 1,200 are names (LOGAN, MILLER, WILLIE,
  WORTHING), one to three labels too high as the lowercase word, and 10 are
  foreign words or read as them (HOY, PLAYA, DATO), one label too high. The
  Obscure words that looked one label low - COEVALS, TABOURET, UNCOCKED - all
  sit within a quarter of a step of the boundary.
- **Independent judges.** For the 92,707 wordfreq words the three corpora can
  also place, they put 87 (0.1%) two or more labels lower and none higher. All
  87 are informal speech - YEAH, NAH, HMM, CONGRATS, JEEZ - or geological eras
  that books capitalise. wordfreq's social-media sources are right about the
  first group, so its values stand.
- **Names.** 1,745 words are used lowercase in under 5% of their appearances
  in books and sit at least one label above their lowercase count: 823 one
  label, 803 two, 119 three. JOHN, AUGUST, CHINA, TEXAS and PARIS at the top,
  WORTHING and FLOSSIE further down. Their label reflects the name, since
  wordfreq folds case. For a player that is arguably right - the string is
  familiar - but the lowercase word itself (a john, august, china, a texas on
  a steamboat) is rarer than its label.
- **Foreign words** are now lowered by the rule above. Some keep a label that
  is one step high: PLAYA is only 1.5 steps more common in Spanish, under the
  two-step bar, and MAS is lowered but not across a label boundary.

## Known weak spots

- The name effect above, 1,745 words, one to three labels too high as the
  lowercase word. Kept deliberately: the label says how familiar the string
  is, and JOHN is familiar.
- The foreign-word rule lowers some English loanwords one label too far
  (FORTE, MANA, ROTI, TOQUE), about 4% of its changes.
- Pages of one corpus that happen to repeat a word are only guarded against by
  the median; a word seen in exactly two corpora takes one of their two
  readings, never a blend.
- Below Zipf 1 the corpora disagree more, so a figure there is a rougher guide
  than the label. The Obscure/Very rare boundary is right about 80% of the
  time on words where it can be checked.

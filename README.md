# Snatch

A word checker for Snatch, the tile game where you steal other players' words
by adding letters to them. It tells you whether a word is in the Scrabble
dictionary, whether one word can legally be stolen into another, and what
steals are possible from a given word.

**Live site: https://dave-orr.github.io/snatch-game/**

## What it does

Type a word and hit Check to see if it's valid. Type a second word in the
steal field and it checks whether the first can become the second. Find
Steals lists everything that can be stolen to make your word, and everything
your word can be stolen into.

The rules as the app enforces them:

- Words must be at least four letters and in the Scrabble dictionary.
- A steal must use every letter of the original word, plus at least one more.
- A steal is not allowed if the two words share a root. FROG to FROGS is
  out. CHANCE to CHANCELLOR is fine, because despite appearances one comes
  from Latin *cadere* and the other from *cancellarius*.
- Merge steals combine two words plus at least one new letter into a third,
  so they need nine or more letters. The result can't just contain one of the
  originals.

The shared-root check is the interesting part. It uses per-word etymology
data (see below), backed up by a list of common affixes and irregular verb
pairs for the cases the data misses (WIND and WINDY have different recorded
roots, but the suffix rule still catches it). Steals that fail the
root check are still listed, but marked invalid, so you can see why.

## The data

The word list is the TWL Scrabble dictionary, fetched at page load from
[redbo/scrabble](https://github.com/redbo/scrabble) on GitHub. If that
repository ever goes away, the site stops working.

The etymologies live in `etymology.json`, which maps each word to a list of
`language:root` pairs. It was built from a Wiktionary dump, with
Merriam-Webster's Collegiate API filling in what Wiktionary lacked, and
covers about 96% of the dictionary. How it was built, what was tried and
rejected, and how to rebuild it are all in [ETYMOLOGY.md](ETYMOLOGY.md).
Read that before touching any of the Python scripts.

## Running it locally

It's a static site with no build step, but the JavaScript uses ES modules,
so opening `index.html` straight from disk won't work. Serve the directory
instead:

```
python3 -m http.server 8000
```

Then open http://localhost:8000. The etymology file is about 18 MB, so the
first load takes a moment.

## Deploying

GitHub Pages serves the `master` branch directly. Push to master and the
site updates within a minute or two; there is nothing else to run. The
version number shown in the corner of the page is set by hand in
`index.html`.

## Layout

| file | what it is |
|---|---|
| `index.html`, `style.css` | the page |
| `app.js` | wiring: loads data, handles the form, renders results |
| `words.js` | validity, letter-subset and shared-root checks |
| `steals.js` | finds single-word and merge steals |
| `etymology.js` | root comparison and display, plus the hand-reviewed list of unrelated root pairs |
| `state.js` | dictionary and etymology state, and the URLs they load from |
| `etymology*.json` | the etymology data and its provenance |
| `*.py` | the etymology build pipeline |

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
                   'back-formation','clipping','clip','contraction','contr',
                   'rebracketing','surf')
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

NAMESPACES = ('appendix', 'reconstruction', 'thesaurus', 'category', 'w:',
              'wikipedia', 'wikisource', 'file', 'image')


def valid_root(word):
    """
    Reject links to Wiktionary's own pages and leftover markup. An etymology
    citing Appendix:Arabic roots/ن ج ل gave GOSSIPMONGERS a root that also
    broke the lang:root format the game splits on.
    """
    if not word or word == '-':
        return False
    if any(ch in word for ch in ':#{}|[]='):
        return False
    return not word.lower().startswith(NAMESPACES)


def valid_lang(code):
    # English cannot be an ancestor of an English word; an "en" root is a
    # self-reference that slipped through a template (AIRLINE = en:line).
    return (bool(re.fullmatch(r'[a-z][a-z0-9-]{0,15}', code))
            and code not in SKIP_LANGUAGES and code != 'en')


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


# Plain-prose etymologies: "From French." or "From Latin ''ursa''". Only the
# languages named here are recognised, mapped to the codes the templates use.
PROSE_LANGUAGES = {
    'Latin': 'la', 'Ancient Greek': 'grc', 'Greek': 'el', 'French': 'fr',
    'Old French': 'fro', 'Middle French': 'frm', 'Anglo-Norman': 'xno',
    'Italian': 'it', 'Spanish': 'es', 'Portuguese': 'pt', 'German': 'de',
    'Dutch': 'nl', 'Middle Dutch': 'dum', 'Old English': 'ang',
    'Middle English': 'enm', 'Old Norse': 'non', 'Scots': 'sco',
    'Irish': 'ga', 'Scottish Gaelic': 'gd', 'Welsh': 'cy', 'Arabic': 'ar',
    'Persian': 'fa', 'Hindi': 'hi', 'Sanskrit': 'sa', 'Hebrew': 'he',
    'Yiddish': 'yi', 'Japanese': 'ja', 'Chinese': 'zh', 'Russian': 'ru',
    'Turkish': 'tr', 'Malay': 'ms', 'Hawaiian': 'haw', 'Afrikaans': 'af',
    'Swedish': 'sv', 'Danish': 'da', 'Norwegian': 'no', 'Icelandic': 'is',
}
PROSE_FROM = re.compile(
    r"\bFrom (?:the )?(" + '|'.join(sorted(PROSE_LANGUAGES, key=len, reverse=True))
    + r")\b(?:\s+(?:word\s+)?''([^']+)'')?")


def prose_roots(text):
    """Roots and language flags stated in plain prose rather than templates."""
    roots, flags = set(), set()
    for m in PROSE_FROM.finditer(text):
        code = PROSE_LANGUAGES[m.group(1)]
        word = normalize(m.group(2)) if m.group(2) else ''
        if word and valid_root(word) and ' ' not in word:
            roots.add((code, word))
        else:
            flags.add(f'from:{code}')
    return roots, flags


COGNATE_CUE = re.compile(r'\b(?:Compare|Cognates?(?:\s+with)?|cognate with|Related to)\b')


def drop_cognate_sentences(text):
    """
    Remove each sentence that lists cognates. "Compare German Terminologie"
    names a relative, not an ancestor, and -LOGY once inherited it. Only the
    sentence goes: cutting everything after the cue threw away HEALTH's
    "Analyzable as {{suffix|en|heal|th}}", which came after "Cognate with".
    """
    out, i = [], 0
    while True:
        m = COGNATE_CUE.search(text, i)
        if not m:
            out.append(text[i:])
            break
        out.append(text[i:m.start()])
        # skip to the next full stop outside any template or link
        depth, j = 0, m.end()
        while j < len(text):
            ch = text[j]
            if ch in '{[': depth += 1
            elif ch in '}]': depth -= 1
            elif ch == '.' and depth <= 0:
                j += 1
                break
            j += 1
        i = j
    return ''.join(out)


# An English word named right after one of these is the base this word was
# formed from: "Derived from {{m|en|asquint}}", "Shortening of {{m|en|X}}".
# Elsewhere an English mention is commentary ("compare", "influenced by").
DERIVATION_CUE = re.compile(
    r'\b(?:From|Derived from|Shortening of|Short for|Shortened from|Variant of|'
    r'Alteration of|Altered from|Back-formation from|Clipping of|Clipped from|'
    r'Contraction of|Abbreviation of|Aphetic form of|Reduplication of)\s+'
    r'(?:the\s+|an?\s+)?\{\{[ml]\|en\|([^|}\[\]]+)', re.IGNORECASE)


def extract(ety_text, allow_mentions=True):
    """returns (roots, english_components, flags)"""
    roots, components, flags = set(), set(), set()
    mentions = []
    if not ety_text: return roots, components, flags

    ety_text = drop_cognate_sentences(ety_text)
    for m in DERIVATION_CUE.finditer(ety_text):
        components.add(normalize(m.group(1)))

    def take_affix_args(args, shape):
        components.update(affix_components(args, shape))

    for name, args in iter_templates(ety_text):
        base = name.rstrip('+')
        if base in ('cog','noncog','w','q','qualifier','ref','r') or base.startswith('r:'):
            continue
        if base in IMITATIVE: flags.add('imitative'); continue
        if base in UNKNOWN: flags.add('unknown'); continue

        # Named arguments can sit anywhere: {{bor|en|ja|sc=Jpan|鯉|tr=koi}}.
        # Read the language and word from the positional ones only, or the
        # word comes out as "sc=jpan" and KOI loses its root.
        positional = [clean_arg(a) for a in args if not is_named(clean_arg(a))]
        if base in ROOT_TEMPLATES and len(positional) >= 3 and positional[0] == 'en':
            lang = positional[1].lower().strip('.,;:')
            word = positional[2]
            if valid_lang(lang) and valid_root(normalize(word)):
                roots.add((lang, normalize(word)))
            elif valid_lang(lang) and word.strip() == '-':
                # "From French." - the language is given but no word. Kept
                # as a display-only marker when nothing better turns up.
                flags.add(f'from:{lang}')
        elif base in ROOT_TEMPLATES and len(positional) == 2 and positional[0] == 'en':
            lang = positional[1].lower().strip('.,;:')
            if valid_lang(lang):
                flags.add(f'from:{lang}')      # {{der|en|fr}} with no word at all
        elif base in AFFIX_TEMPLATES and args and clean_arg(args[0]) == 'en':
            shape = ('suffix' if base in ('suf','suffix') else
                     'prefix' if base in ('pre','prefix') else
                     'confix' if base in ('con','confix') else 'free')
            take_affix_args(args[1:], shape)
        elif base in AFFIX_TEMPLATES and args and valid_lang(clean_arg(args[0]).lower()) \
                and clean_arg(args[0]).lower() != 'en':
            # {{compound|nl|de|kooi}}: the parts are words of that language
            lang = clean_arg(args[0]).lower()
            for part in affix_components(args[1:], 'free'):
                if not (part.startswith('-') or part.endswith('-')) and valid_root(part):
                    roots.add((lang, part))
        elif base in ('etymon','ety') and args and clean_arg(args[0]) == 'en':
            # a named id= can come before the kind:
            # {{etymon|en|id=lack of illness|:inh|enm:helthe}}
            positional = [a for a in args[1:] if not is_named(clean_arg(a))]
            if not positional:
                continue
            kind = clean_arg(positional[0]).lstrip(':').lower()
            rest = positional[1:]
            if kind == 'af':
                take_affix_args(rest, 'free')
            elif kind in ROOT_TEMPLATES and rest:
                # these pack language and word into one argument: grc:ἐπῐ-
                arg = clean_arg(rest[0])
                if ':' in arg:
                    lang, _, word = arg.partition(':')
                    lang, word = lang.strip().lower().strip('.,;:'), word.strip()
                    if valid_lang(lang) and valid_root(normalize(word)):
                        roots.add((lang, normalize(word)))
        elif base == 'm' and len(args) >= 2:
            lang = clean_arg(args[0]).lower().strip('.,;:')
            # English mentions are "influenced by" noise, not ancestors
            if lang != 'en' and valid_lang(lang):
                word = normalize(clean_arg(args[1]))
                if valid_root(word): mentions.append((lang, word))

    # Prose is the last resort: only when no template gave a root
    if not roots:
        prose_r, prose_f = prose_roots(ety_text)
        roots |= prose_r
        if not roots:
            flags |= prose_f

    # A bare {{m}} is only trustworthy when the section states no derivation
    # of its own ("From Middle English {{m|enm|bublen}}"). Where explicit
    # templates exist, they are the etymology and mentions are commentary.
    # On an affix page the mentions are illustrations - the page for -ON
    # cites CARBON - so a word resolving through the affix would inherit the
    # example: BOSON came out descended from Latin carbo that way.
    if not roots and mentions and allow_mentions:
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


# A definition that reads "alternative form of X", "plural of X" or "obsolete
# spelling of X" names the word this one is a form of, and X's roots are its
# roots. These live in the definition line, not the etymology section, so
# HOMMOCK (alternative form of hummock) had no etymology at all. "synonym of"
# is deliberately absent: synonyms are not relatives.
FORM_OF = re.compile(
    r'\{\{(?:alternative form of|alt form|altform|alternative spelling of|alt sp|'
    r'altsp|plural of|obsolete form of|obsolete spelling of|archaic form of|'
    r'archaic spelling of|dated form of|dated spelling of|misspelling of|'
    r'nonstandard spelling of|nonstandard form of|eye dialect of|clipping of|'
    r'abbreviation of|short for|rare form of|rare spelling of|informal form of|'
    r'standard spelling of|less common spelling of|uncommon spelling of|'
    r'feminine of|diminutive of|augmentative of|inflection of|infl of|form of|'
    r'en-past of|en-simple past of|en-third-person singular of|'
    r'en-third person singular of|en-ing form of|en-comparative of|'
    r'en-superlative of|en-irregular plural of|past participle of|'
    r'present participle of|comparative of|superlative of)'
    r'\|en\|([^|}]+)', re.IGNORECASE)


# The en- inflection templates predate the language argument, so the target
# is usually the first argument: {{en-third-person singular of|Russify}}.
EN_INFLECTION = re.compile(r'\{\{en-[a-z -]+ of\|(?:en\|)?([^|}]+)', re.IGNORECASE)


def form_of_targets(english_section):
    """Words this entry is declared a form of."""
    targets = set()
    for regex in (FORM_OF, EN_INFLECTION):
        for m in regex.finditer(english_section):
            target = clean_arg(m.group(1))
            if target and target != '-' and '[' not in target:
                targets.add(normalize(target))
    return targets


# A foreign page that is itself an inflected form: French "russifies" is a
# verb form of russifier, not a word English borrowed.
INFLECTION_PAGE = re.compile(
    r'\{\{(?:inflection of|plural of|conjugation of|[a-z]{2,3}-[a-z]+ form of|'
    r'[a-z]{2,3}-form-of|(?:feminine|masculine) (?:singular|plural)? ?of|'
    r'[a-z ]*form of)\|', re.IGNORECASE)


def language_section(wiki_text, language):
    """The wikitext of one language's section, or None."""
    marker = f'=={language}=='
    if marker not in wiki_text:
        return None
    return re.split(r'\n==[^=]', wiki_text.split(marker, 1)[1])[0]


def etymology_of_section(section):
    """Etymology wikitext within one language section, if any."""
    found = re.findall(r'\n=+\s*Etymology[^=\n]*=+\n(.*?)(?=\n=+[^=\n]|\Z)',
                       section, re.DOTALL)
    return '\n'.join(found) if found else None


# Scrabble words that Wiktionary files under another language, in the order
# to try them. Scots first: Collins admits a great many Scots words (GLAIKET,
# SICCAN, WAEFUL) that have no English entry. Latin before the Romance
# languages, because URSA is Latin even though Esperanto also has a page.
OTHER_LANGUAGE_SECTIONS = [
    ('Scots', 'sco'), ('Middle English', 'enm'), ('Latin', 'la'),
    ('Italian', 'it'), ('French', 'fr'), ('Spanish', 'es'), ('German', 'de'),
    ('Dutch', 'nl'), ('Portuguese', 'pt'), ('Yola', 'yol'), ('Irish', 'ga'),
    ('Scottish Gaelic', 'gd'), ('Welsh', 'cy'), ('Hawaiian', 'haw'),
    ('Maori', 'mi'), ('Afrikaans', 'af'), ('Yiddish', 'yi'), ('Hebrew', 'he'),
    ('Japanese', 'ja'), ('Old English', 'ang'), ('Old Norse', 'non'),
]


def english_etymology_section(wiki_text):
    """Return the etymology wikitext inside the English section, if any."""
    if not wiki_text or '==English==' not in wiki_text:
        return None
    english = re.split(r'\n==[^=]', wiki_text.split('==English==', 1)[1])[0]
    sections = re.findall(r'\n=+\s*Etymology[^=\n]*=+\n(.*?)(?=\n=+[^=\n]|\Z)',
                          english, re.DOTALL)
    return '\n'.join(sections) if sections else None


IMITATIVE_MARKER = 'imitative'

MAX_RESOLUTION_DEPTH = 6

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
    'a','acioun','uʀ','ur','ation','acion','for','di',
    # spellings the same grammatical affixes take in older stages, found in
    # entries whose only root was the suffix: BARRISTER had just -ESTRE
    'um','ie','som','sam','sum','arie','estre','estere','astrija','ification',
    'o','ar','ere','en','ende','inge','nesse','lich','liche',
    'ance','ence','ancy','ency','aunce','entia','antia','antie','encie',
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
        # Cut short by a cycle or the depth limit. Return None rather than an
        # empty set so the caller does not cache "no roots" for a word that
        # would resolve fine from the top.
        return None
    entry = pages.get(title)
    if not entry:
        cache[title] = set()
        return cache[title]
    roots, components = entry
    if roots:
        cache[title] = set(roots)
        return cache[title]
    resolved, complete = set(), True
    for component in components:
        found = resolve(component, pages, cache, seen | {title})
        if found is None:
            complete = False
        else:
            resolved |= found
    if complete or resolved:
        cache[title] = resolved
        return resolved
    return None


def analyze_page(title, text, scrabble_words, playable):
    """
    What one dump page says about its word: (roots, components, flags, tier).
    English pages are read for their etymology and form-of templates; a
    playable word with no English entry is read from its source language.
    The tier ranks pages for the same word: a lowercase English page (0)
    beats a capitalized one (1), which beats a foreign-language page (2).
    """
    # Only a title that is entirely lowercase is the word's own page. The
    # page "pIg" (an abbreviation of polyclonal immunoglobulin) starts with a
    # lowercase letter but is not the page for PIG, and keyed by lowercase it
    # once overwrote the real one.
    lowercase = title == title.lower()
    capitalized = not lowercase
    tier = None
    # The XML dump escapes markup, so <t:...> annotations arrive as
    # &lt;t:...&gt; and survive the stripper unless unescaped first.
    text = html.unescape(text)
    key = title.lower()
    english = language_section(text, 'English')

    roots, components, page_flags = set(), set(), set()
    if english:
        tier = 0 if lowercase else 1
        section = etymology_of_section(english)
        if section:
            title_is_affix = title.startswith('-') or title.endswith('-')
            roots, components, page_flags = extract(
                section, allow_mentions=not title_is_affix)
            if title_is_affix:
                # An affix contributes its own roots and nothing else. Its
                # page also links the words it was formed from or alongside
                # - -ON is a back-formation from CARBON - and following
                # those made every word ending in the affix a relative of
                # the example. BOSON came out descended from Latin carbo.
                components = set()
        components = set(components) | form_of_targets(english)
    elif playable and not capitalized:
        # No English entry, but the word is playable: it is a borrowing
        # Wiktionary files under its source language. The word itself in
        # that language is its root, as {{bor}} would have recorded.
        # Capitalized pages are excluded because German capitalizes every
        # noun, and Wiktionary's German entries for PIXEL, REPRESSOR and
        # FLIRT would otherwise label English words as German borrowings
        # when German borrowed them from English.
        for language, code in OTHER_LANGUAGE_SECTIONS:
            other = language_section(text, language)
            if other and not INFLECTION_PAGE.search(other):
                tier = 2
                roots = {(code, normalize(title))}
                section = etymology_of_section(other)
                if section:
                    deeper, _, _ = extract(section)
                    roots |= deeper
                break

    return roots, components, page_flags, tier


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

    tiers = ({}, {}, {})          # lowercase English, capitalized English, foreign
    tier_flags = ({}, {}, {})

    for title, text in iter_wiktionary_pages(wiktionary_path):
        capitalized = title[:1].isupper()
        playable = title.upper() in scrabble_words
        # Proper nouns are skipped unless the Scrabble list has the word:
        # CHUNNEL, MIRANDIZE and EGYPTIAN are playable but Wiktionary files
        # them capitalized.
        if capitalized and not playable:
            continue
        roots, components, page_flags, tier = analyze_page(
            title, text, scrabble_words, playable)
        if tier is None:
            continue
        key = title.lower()
        if roots or components:
            page_count += 1
            if page_count % 100000 == 0:
                print(f"  {page_count} pages with etymology data...")
            # Several titles can share a key (PIG, Pig, PIGs). Within a tier
            # keep whichever has roots; never let a rootless page replace one
            # that resolved.
            existing = tiers[tier].get(key)
            if existing is None or (not existing[0] and roots):
                tiers[tier][key] = (frozenset(roots), tuple(sorted(components)))
        # Markers come only from a word's own lowercase English page. The
        # capitalized page for the Chinese city Wanning is not evidence about
        # the English word WANNING.
        if page_flags and tier == 0:
            tier_flags[tier][key] = page_flags

    # A lower tier fills in only where no better page said anything.
    for tier_pages, tier_flag in zip(tiers, tier_flags):
        for key, value in tier_pages.items():
            pages.setdefault(key, value)
        for key, value in tier_flag.items():
            flags.setdefault(key, value)

    print(f"Pages with etymology data: {len(pages)}")

    cache = {}
    etymology_dict = {}
    unresolved = 0
    for word in scrabble_words:
        roots = resolve(word.lower(), pages, cache) or set()
        if roots:
            etymology_dict[word] = sorted(
                f"{ROOT_LANGUAGES.get(lang, lang)}:{root}" for lang, root in roots)
        elif word.lower() in pages:
            unresolved += 1

    etymology_dict = drop_noisy_affixes(etymology_dict)

    with_roots = len(etymology_dict)

    # Words Wiktionary calls imitative have no ancestor to record: BUZZ and
    # HISS were each coined in imitation rather than inherited. The marker
    # says so instead of leaving them indistinguishable from words nobody has
    # researched. It carries no root, and etymology.js never counts a rootless
    # entry as shared, because two imitative words are not relatives.
    imitative = language_only = 0
    for word in scrabble_words:
        if word in etymology_dict:
            continue
        word_flags = flags.get(word.lower(), ())
        if 'imitative' in word_flags:
            etymology_dict[word] = [f'{IMITATIVE_MARKER}:-']
            imitative += 1
            continue
        languages = sorted(f[5:] for f in word_flags if f.startswith('from:'))
        if languages:
            # "From French." with no word given: show the language at least
            etymology_dict[word] = [f'{ROOT_LANGUAGES.get(l, l)}:-' for l in languages]
            language_only += 1

    print(f"Scrabble words with roots: {with_roots} "
          f"({100*with_roots/len(scrabble_words):.1f}%)")
    print(f"  had etymology data but resolved to no root: {unresolved}")
    print(f"  no root, marked imitative instead: {imitative}")
    print(f"  no root, source language only: {language_only}")
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

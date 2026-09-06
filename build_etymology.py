#!/usr/bin/env python3
"""
Build etymology dictionary from Wiktionary dump.

Usage:
1. Download the Wiktionary dump from:
   https://dumps.wikimedia.org/enwiktionary/latest/enwiktionary-latest-pages-articles.xml.bz2

2. Run this script:
   python build_etymology.py enwiktionary-latest-pages-articles.xml.bz2 [--save-scan scan.json.gz]

3. Output is etymology.json (word -> roots) and etymology_links.json (the
   playable words each still-rootless word is linked to, for
   expand_inflections.py to finish once propagation covers a target).

The dump takes about 40 minutes to read. --save-scan keeps what was read;
passing that .json.gz file instead of the dump reruns only the resolution,
in seconds.
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

# {{tmpl|en|LANG|WORD}} - a root in another language. {{semantic loan}} is
# absent on purpose: HAVE took a sense from French avoir, not the word, and
# the two do not share a root.
ROOT_TEMPLATES = ('der','inh','bor','borrowed','derived','inherited','uder','lbor',
                  'slbor','obor','ubor','abor','cal','calque','clq','pcal','pclq',
                  'partial calque','translit','psm',
                  'learned borrowing','semi-learned borrowing',
                  'orthographic borrowing','unadapted borrowing',
                  'adapted borrowing','phono-semantic matching',
                  # the -lite variants take the same arguments
                  'der-lite','inh-lite','bor-lite')
# {{doublet|en|WORD}}: an English word that shares this one's ultimate source
DOUBLET_TEMPLATES = ('doublet','dbt')
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
    # Codes are two or three letters, optionally with family or variety
    # suffixes (gmw-pro, la-new, cmn-pinyin). Anything else that reaches here
    # is a namespace read as a code: w:Mafeking gave 81 roots in language "w".
    return (bool(re.fullmatch(r'[a-z]{2,3}(-[a-z]{2,6})*', code))
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
        for part in affix_components(args, shape):
            # {{af|en|la:cāseus|-ous}} names a Latin word among the parts. It
            # stays a component, written lang:word, and scan_dump gives every
            # such part a page of its own holding that one root. Turning it
            # into a root here would make resolve() stop at it and drop the
            # English parts beside it: ARCHAEBACTERIUM, grc:ἀρχαῖος +
            # bacterium, lost bacterium that way.
            lang, sep, word = part.partition(':')
            if sep and lang == 'en':
                components.add(normalize(word))
            elif sep and valid_lang(lang):
                if valid_root(normalize(word)):
                    components.add(f'{lang}:{normalize(word)}')
            else:
                components.add(part)

    def affix_shape(name):
        return ('suffix' if name in ('suf','suffix') else
                'prefix' if name in ('pre','prefix') else
                'confix' if name in ('con','confix') else 'free')

    for name, args in iter_templates(ety_text):
        base = name.rstrip('+')
        if base in ('cog','cog-lite','noncog','w','q','qualifier','ref','r') or base.startswith('r:'):
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
        elif base == 'surf' and args and clean_arg(args[0]).startswith('+'):
            # {{surf|+com|en|short|fall}}: the kind comes first
            kind = clean_arg(args[0])[1:]
            if len(args) > 1 and clean_arg(args[1]) == 'en':
                take_affix_args(args[2:], affix_shape(kind))
        elif base in AFFIX_TEMPLATES and args and clean_arg(args[0]) == 'en':
            take_affix_args(args[1:], affix_shape(base))
        elif base in DOUBLET_TEMPLATES and positional and positional[0] == 'en':
            # LIQUEUR is a doublet of LIQUOR: same source by definition, so
            # the doublet's roots stand in when the page states none.
            for word in positional[1:]:
                word = normalize(word)
                if valid_root(word) and ' ' not in word:
                    components.add(word)
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
            # One template can chain several kinds:
            # {{ety|en|:af|la:cōnfīdentia|-al|:calque|fr:confidentiel}}
            segments, current = [], None
            for a in positional:
                if clean_arg(a).startswith(':'):
                    current = [clean_arg(a).lstrip(':').lower(), []]
                    segments.append(current)
                elif current is not None:
                    current[1].append(a)
            for kind, rest in segments:
                if kind == 'af' or kind in AFFIX_TEMPLATES:
                    # {{etymon|en|:blend|elevator|aileron}}, {{etymon|en|:clip|business}}
                    take_affix_args(rest, affix_shape(kind))
                elif kind in ROOT_TEMPLATES and rest:
                    # these pack language and word into one argument: grc:ἐπῐ-
                    arg = clean_arg(rest[0])
                    if ':' in arg:
                        lang, _, word = arg.partition(':')
                        lang, word = lang.strip().lower().strip('.,;:'), word.strip()
                        if valid_lang(lang) and valid_root(normalize(word)):
                            roots.add((lang, normalize(word)))
        elif base in ('m', 'm-lite') and len(args) >= 2:
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
    r'\|en\|([^}]*?)\}\}', re.IGNORECASE)


# The en- inflection templates predate the language argument, so the target
# is usually the first argument: {{en-third-person singular of|Russify}}.
EN_INFLECTION = re.compile(r'\{\{en-[a-z -]+ of\|(?:en\|)?([^}]*?)\}\}', re.IGNORECASE)


def form_of_targets(english_section):
    """Words this entry is declared a form of."""
    targets = set()
    for regex in (FORM_OF, EN_INFLECTION):
        for m in regex.finditer(english_section):
            # The target is the first positional argument. Named ones can
            # come first: {{standard spelling of|en|from=Non-Oxford British
            # spelling|recognize}} once made RECOGNISE a form of "from=...".
            positional = [clean_arg(a) for a in m.group(1).split('|')
                          if not is_named(clean_arg(a))]
            target = positional[0] if positional else ''
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

# Deep enough that no real chain of English components is cut short:
# OXYCODONE reaches Greek through hydroxy, hydroxyl, hydro- and -oxyl.
MAX_RESOLUTION_DEPTH = 10

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

    A hyphenated component is looked up only as written. -ONE and -ON have
    pages that state nothing parseable, and an experiment that fell back to
    the bare word gave 386 chemical names roots meaning "one" and "on";
    restricted to affixes with no page at all it gained three words.
    """
    seen = seen or set()
    if title in seen or len(seen) >= MAX_RESOLUTION_DEPTH:
        # Cut short by a cycle or the depth limit. Return None rather than an
        # empty set so the caller does not cache "no roots" for a word that
        # would resolve fine from the top. This check comes before the cache
        # so that a chain too deep to follow is too deep whatever was
        # visited before it; otherwise the answer depended on visit order.
        return None
    if title in cache:
        return cache[title]
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
    if complete:
        cache[title] = resolved
        return resolved
    # Incomplete: some component was cut off by the depth limit. Return what
    # was found but do not cache it, since the same component may resolve
    # fully when reached from a shallower start. Caching partial results made
    # the output depend on the order words were visited in, which for a set
    # is the hash seed, so two runs of the same dump disagreed.
    return resolved or None


# A base word's page lists the words formed from it under "Derived terms".
# For a word whose own page says nothing about its origin, that listing is
# the only statement Wiktionary makes: TELLURITE has no etymology section,
# but TELLURIUM lists it.
DERIVED_SECTION = re.compile(
    r'\n=+\s*Derived terms\s*=+\n(.*?)(?=\n=+[^=\n]|\Z)', re.DOTALL)
LIST_ITEM = re.compile(
    r'\[\[([^\]|#]+)(?:[|#][^\]]*)?\]\]'
    r'|\{\{(l|link|der\d|rel\d|col\d|col|col-auto|der-top\d?|rel-top\d?)\|en\|([^}]*)\}\}')


def plausibly_derived(item, base):
    """
    Does the listed word visibly contain the base? Derived-terms lists carry
    topical entries too - BUDDLEIA under BUTTERFLY (butterfly bush),
    LEPIDOPTERIST under BUTTERFLY - and those would take the base's roots.
    A real derivative either contains the base's stem (SANDPIPER, PIPER) or
    opens with the same four letters (PSORIATIC, PSORIASIS).
    """
    stem = base[:max(3, len(base) - 2)]
    return stem in item or shared_stem(item, base) >= 4


def shared_stem(a, b):
    n = 0
    while n < min(len(a), len(b)) and a[n] == b[n]:
        n += 1
    return n


def derived_terms(english, scrabble_words, title):
    """Playable words the English section lists under Derived terms, and
    that look derived from this page's word."""
    found = set()
    for body in DERIVED_SECTION.findall(english):
        for m in LIST_ITEM.finditer(body):
            if m.group(1):
                items = [m.group(1)]
            elif m.group(2) in ('l', 'link'):
                items = m.group(3).split('|')[:1]     # the rest is a gloss
            else:
                items = [a for a in m.group(3).split('|') if a and '=' not in a]
            for item in items:
                item = item.strip()
                if item and ' ' not in item and item == item.lower() \
                        and item.upper() in scrabble_words \
                        and plausibly_derived(item, title):
                    found.add(item)
    return found


# A definition often names the word it is built on: ILEAC is "Pertaining to
# the [[ileum]]", EXORBITANCE "The state of being [[exorbitant]]". Used only
# where the page has no etymology to read, and only for a link the headword
# visibly contains: they must share an opening stem of MIN_SHARED_STEM
# letters that reaches to within four letters of the link's end, so
# ESCHATOLOGICAL takes eschatology but OSMOLE does not take mole. In a
# blind sample of 100 no-etymology pages this fired on 23 and all 23 were
# right.
DEFINITION_LINE = re.compile(r'\n# ?([^\n]*)')
DEFINITION_LINK = re.compile(
    r'\[\[([^\]|#]+)(?:[|#][^\]]*)?\]\]|\{\{(?:l|m)\|en\|([^|}]+)')
MIN_SHARED_STEM = 5


def definition_link(english, title):
    """The linked word this one is visibly built on, as a one-element set."""
    best = None
    for line in DEFINITION_LINE.findall(english)[:3]:
        for m in DEFINITION_LINK.finditer(line):
            link = (m.group(1) or m.group(2)).strip()
            if ' ' in link or link != link.lower() or link == title:
                continue
            shared = shared_stem(title, link)
            if shared >= MIN_SHARED_STEM and shared >= len(link) - 4 \
                    and (best is None or shared > best[1]):
                best = (link, shared)
    return {normalize(best[0])} if best else set()


def analyze_page(title, text, scrabble_words, playable):
    """
    What one dump page says about its word:
    (roots, components, flags, tier, derived_terms, definition_link).
    English pages are read for their etymology and form-of templates; a
    playable word with no English entry is read from its source language.
    The tier ranks pages for the same word: a lowercase English page (0)
    beats a capitalized one (1), which beats a foreign-language page (2).
    derived_terms are the playable words this page lists as formed from it;
    definition_link is the word this page's definition shows it is built on,
    found only when the page states no etymology of its own. Both are kept
    apart from components so the resolution can weigh them separately.
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
    derived, def_link = set(), set()
    if english:
        tier = 0 if lowercase else 1
        title_is_affix = title.startswith('-') or title.endswith('-')
        section = etymology_of_section(english)
        if section:
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
        if lowercase and not title_is_affix:
            derived = derived_terms(english, scrabble_words, title)
            if not roots and not components and 'unknown' not in page_flags:
                def_link = definition_link(english, title)
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

    return roots, components, page_flags, tier, derived, def_link


def scan_dump(wiktionary_path, scrabble_words):
    """
    Read the dump once. Returns everything resolution needs, keyed by
    lowercase title: pages (roots and components), flags, the derived-terms
    listings inverted to derivative -> bases, and definition links.

    Every English page is kept, not just the Scrabble words: QUINIC resolves
    through QUININE and RADIOLOGY through -LOGY, and neither base has to be
    playable for its roots to be the right answer.
    """
    tiers = ({}, {}, {})          # lowercase English, capitalized English, foreign
    tier_flags = ({}, {}, {})
    derived_from = defaultdict(set)
    definition_links = {}
    page_count = 0

    for title, text in iter_wiktionary_pages(wiktionary_path):
        capitalized = title[:1].isupper()
        playable = title.upper() in scrabble_words
        # Proper nouns are skipped unless the Scrabble list has the word:
        # CHUNNEL, MIRANDIZE and EGYPTIAN are playable but Wiktionary files
        # them capitalized.
        if capitalized and not playable:
            continue
        roots, components, page_flags, tier, derived, def_link = analyze_page(
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
        # Markers, derived terms and definition links come only from a word's
        # own lowercase English page. The capitalized page for the Chinese
        # city Wanning is not evidence about the English word WANNING.
        if tier == 0:
            if page_flags:
                tier_flags[tier][key] = page_flags
            for item in derived:
                if item != key:
                    derived_from[item].add(key)
            if def_link:
                definition_links.setdefault(key, def_link)

    pages, flags = {}, {}
    # A lower tier fills in only where no better page said anything.
    for tier_pages, tier_flag in zip(tiers, tier_flags):
        for key, value in tier_pages.items():
            pages.setdefault(key, value)
        for key, value in tier_flag.items():
            flags.setdefault(key, value)
    # A foreign part of an affix template (la:cāseus) gets a page holding
    # that root, so it resolves like any other component. No real title
    # contains a colon; the reader skips namespaced pages.
    for key, (_, components) in list(pages.items()):
        for component in components:
            lang, sep, word = component.partition(':')
            if sep and valid_lang(lang) and component not in pages:
                pages[component] = (frozenset({(lang, word)}), ())

    print(f"Pages with etymology data: {len(pages)}")
    print(f"Words listed as derived terms: {len(derived_from)}")
    print(f"Pages with a definition link: {len(definition_links)}")
    return {'pages': pages, 'flags': flags, 'derived_from': dict(derived_from),
            'definition_links': definition_links}


def save_scan(scan, path):
    """Keep the scan so resolution can be rerun without another 40-minute
    pass over the dump."""
    import gzip
    data = {
        'pages': {k: [sorted(r), list(c)] for k, (r, c) in scan['pages'].items()},
        'flags': {k: sorted(v) for k, v in scan['flags'].items()},
        'derived_from': {k: sorted(v) for k, v in scan['derived_from'].items()},
        'definition_links': {k: sorted(v) for k, v in scan['definition_links'].items()},
    }
    with gzip.open(path, 'wt', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False)
    print(f"Saved scan to {path}")


def load_scan(path):
    import gzip
    with gzip.open(path, 'rt', encoding='utf-8') as f:
        data = json.load(f)
    return {
        'pages': {k: (frozenset(tuple(x) for x in r), tuple(c))
                  for k, (r, c) in data['pages'].items()},
        'flags': {k: set(v) for k, v in data['flags'].items()},
        'derived_from': {k: set(v) for k, v in data['derived_from'].items()},
        'definition_links': {k: set(v) for k, v in data['definition_links'].items()},
    }


def build_etymology_dict(scan, scrabble_words, use_derived=True, use_definitions=True):
    """
    Resolve a scan into word -> roots, plus the links left unresolved.

    Derived-terms listings and definition links stand in only for a word
    whose own page states nothing: no roots, no components, no form-of
    target, and no "unknown". A page that says "origin unknown" is not
    overruled by a definition that happens to link a lookalike.

    The second return value maps each still-rootless playable word to the
    playable words it is linked to, so expand_inflections can finish the
    job once propagation has covered a target the parse could not.
    """
    pages = dict(scan['pages'])
    flags = scan['flags']
    fallback = {}     # key -> 'derived' / 'definition' / 'derived+definition'

    def own_statement(key):
        entry = pages.get(key)
        return bool(entry and (entry[0] or entry[1])) or 'unknown' in flags.get(key, ())

    if use_definitions:
        for key, links in scan['definition_links'].items():
            if not own_statement(key):
                pages[key] = (frozenset(), tuple(sorted(links)))
                fallback[key] = 'definition'
    if use_derived:
        for key, bases in scan['derived_from'].items():
            if own_statement(key) and key not in fallback:
                continue
            existing = pages.get(key, (frozenset(), ()))
            pages[key] = (frozenset(), tuple(sorted(set(existing[1]) | bases)))
            fallback[key] = 'derived+definition' if key in fallback else 'derived'

    cache = {}
    etymology_dict = {}
    links = {}
    unresolved = 0
    for word in sorted(scrabble_words):
        key = word.lower()
        roots = resolve(key, pages, cache) or set()
        if roots:
            etymology_dict[word] = sorted(
                f"{ROOT_LANGUAGES.get(lang, lang)}:{root}" for lang, root in roots)
        elif key in pages:
            unresolved += 1
            targets = sorted(t.upper() for t in pages[key][1]
                             if t.upper() in scrabble_words and t != key)
            if targets:
                links[word] = {'kind': fallback.get(key, 'stated'), 'targets': targets}

    etymology_dict = drop_noisy_affixes(etymology_dict)

    with_roots = len(etymology_dict)

    # Words Wiktionary calls imitative have no ancestor to record: BUZZ and
    # HISS were each coined in imitation rather than inherited. The marker
    # says so instead of leaving them indistinguishable from words nobody has
    # researched. It carries no root, and etymology.js never counts a rootless
    # entry as shared, because two imitative words are not relatives.
    imitative = language_only = 0
    for word in sorted(scrabble_words):
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
    print(f"  of which linked to other playable words: {len(links)}")
    print(f"  no root, marked imitative instead: {imitative}")
    print(f"  no root, source language only: {language_only}")
    return etymology_dict, links


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        print("\nError: Please provide path to Wiktionary dump file")
        print("Download from: https://dumps.wikimedia.org/enwiktionary/latest/enwiktionary-latest-pages-articles.xml.bz2")
        sys.exit(1)

    source = sys.argv[1]
    save_to = None
    if '--save-scan' in sys.argv:
        save_to = sys.argv[sys.argv.index('--save-scan') + 1]

    if not Path(source).exists():
        print(f"Error: File not found: {source}")
        sys.exit(1)

    scrabble_words = load_scrabble_dictionary()

    if source.endswith('.json.gz'):
        scan = load_scan(source)
    else:
        scan = scan_dump(source, scrabble_words)
        if save_to:
            save_scan(scan, save_to)

    etymology_dict, links = build_etymology_dict(scan, scrabble_words)

    here = Path(__file__).parent
    with open(here / 'etymology.json', 'w', encoding='utf-8') as f:
        json.dump(etymology_dict, f, indent=2, sort_keys=True)
    with open(here / 'etymology_links.json', 'w', encoding='utf-8') as f:
        json.dump(links, f, indent=1, sort_keys=True, ensure_ascii=False)

    print(f"\nSaved etymology dictionary to {here / 'etymology.json'}")
    print(f"Saved {len(links)} unresolved links to {here / 'etymology_links.json'}")
    print(f"Total entries: {len(etymology_dict)}")

    roots = defaultdict(int)
    multi_etym_count = 0
    for word, etym_list in etymology_dict.items():
        if len(etym_list) > 1:
            multi_etym_count += 1
        for etym in etym_list:
            roots[etym.split(':')[0]] += 1
    print(f"Words with multiple etymologies: {multi_etym_count}")
    print("\nBreakdown by root language:")
    for lang, count in sorted(roots.items(), key=lambda x: -x[1])[:20]:
        print(f"  {lang}: {count}")


if __name__ == '__main__':
    main()

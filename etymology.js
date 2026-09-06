// Etymology display module for Snatch game
// Functions for formatting and comparing word etymologies

import { getEtymology } from './state.js';

// Format a single etymology entry as HTML
function formatEtymologyEntry(entry) {
    const [lang, root] = entry.split(':');
    if (!root || root === '-') {
        return `<span class="etymology-lang">${lang}</span>`;
    }
    return `<span class="etymology-lang">${lang}</span>:<span class="etymology-root">${root}</span>`;
}

// Format etymology for display (with "Etymology:" prefix)
export function formatEtymology(word) {
    const etymology = getEtymology();
    const etymList = etymology[word];
    if (!etymList || !Array.isArray(etymList) || etymList.length === 0) {
        return '<div class="etymology">Etymology: <span class="etymology-unknown">unknown</span></div>';
    }

    const formatted = etymList.map(formatEtymologyEntry).join(', ');
    return `<div class="etymology">Etymology: ${formatted}</div>`;
}

// Format etymology for compare display (simpler version without the "Etymology:" prefix)
export function formatEtymologySimple(word) {
    const etymology = getEtymology();
    const etymList = etymology[word];
    if (!etymList || !Array.isArray(etymList) || etymList.length === 0) {
        return '<span class="etymology-unknown">unknown</span>';
    }

    return etymList.map(formatEtymologyEntry).join(', ');
}

// Normalize a root for comparison: lowercase, strip diacritics, and drop the
// hyphens that mark an affix. Without the last step the combining form
// -phobia never matches the hydrophobia it appears in.
export function normalizeRoot(root) {
    return root
        .toLowerCase()
        .normalize('NFD')
        .replace(/[\u0300-\u036f]/g, '')
        .replace(/^-+|-+$/g, '');
}

// An entry with no root - imitative:- - says how a word was formed, not what
// it descends from. Two imitative words were each coined in imitation rather
// than inherited from a common ancestor, so they are not relatives and must
// never count as sharing a root. rootsMatch already rejects them, since a
// bare hyphen normalizes to nothing; this guards the exact-match path.
export function carriesRoot(entry) {
    const [, root] = entry.split(':');
    return Boolean(root) && root !== '-';
}

// Roots shorter than this are not compared by prefix. A short root is the
// opening of many unrelated longer ones - enm:dri starts drinkere, latin:qua
// starts quadriceps, old_english:ban starts bana - and matching them made
// about 60% of the pairs it found wrong. At seven letters and up the rule is
// reliable: all 998 pairs it matches in the current data were reviewed by
// hand and 989 are genuine.
const MIN_PREFIX_MATCH_LENGTH = 7;

// The nine survivors of that review: long roots where a word coincidentally
// begins with an unrelated one. No length rule separates them, so they are
// listed. The verdicts for all 998 pairs are in prefix_pair_review.json;
// after regenerating etymology.json run check_prefix_review.py, which reports
// the pairs that are new and so still unreviewed.
const UNRELATED_PREFIX_PAIRS = new Set([
    'enm:chaunce|chaunceler',              // cadentia vs cancellarius
    'enm:entrete|entretenement',           // tractare vs inter + tenere
    'enm:entreten|entretenement',
    'enm:forecast|forecastel',             // fore + cast vs fore + castle
    'frm:hostile|hostiler',                // hostis (enemy) vs hospes (host)
    'old_french:controver|controversie',   // contrive vs controversy
    'old_french:marchie|marchier',         // mercatus (market) vs marcare
    'xno:plainte|plainteine',              // planctus (plaint) vs plantago
    'frm:content|contentieux',             // continere (content) vs contendere
]);

// Do two roots of the same language descend from the same source?
export function rootsMatch(lang1, root1, lang2, root2) {
    if (lang1 !== lang2 || !root1 || !root2) {
        return false;
    }
    const r1 = normalizeRoot(root1);
    const r2 = normalizeRoot(root2);
    if (r1.length < 3 || r2.length < 3) {
        return false;
    }
    // One root inside the other, as Latin and Greek build words by prefixing:
    // fixus is the end of suffixus, affixus and praefixus.
    if (r1.endsWith(r2) || r2.endsWith(r1)) {
        return true;
    }
    const [shorter, longer] = r1.length <= r2.length ? [r1, r2] : [r2, r1];
    if (shorter.length >= MIN_PREFIX_MATCH_LENGTH && longer.startsWith(shorter)) {
        return !UNRELATED_PREFIX_PAIRS.has(`${lang1}:${shorter}|${longer}`);
    }
    return false;
}

// Get shared etymologies between two words
export function getSharedEtymologies(word1, word2) {
    const etymology = getEtymology();
    const etymList1 = etymology[word1];
    const etymList2 = etymology[word2];
    const shared = [];

    if (etymList1 && etymList2 && Array.isArray(etymList1) && Array.isArray(etymList2)) {
        for (const etym1 of etymList1) {
            for (const etym2 of etymList2) {
                // Check if they match
                if (etym1 === etym2) {
                    if (carriesRoot(etym1)) {
                        shared.push(etym1);
                    }
                } else {
                    const [lang1, root1] = etym1.split(':');
                    const [lang2, root2] = etym2.split(':');
                    if (rootsMatch(lang1, root1, lang2, root2)) {
                        // Return the shorter root as the "base"
                        shared.push(normalizeRoot(root1).length <= normalizeRoot(root2).length
                            ? etym1 : etym2);
                    }
                }
            }
        }
    }

    return [...new Set(shared)]; // Remove duplicates
}

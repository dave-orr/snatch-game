// Word validation module for Snatch game
// Pure word validation functions with minimal state dependencies

import { getDictionary, getIsLoaded, getEtymology } from './state.js';

export const MIN_WORD_LENGTH = 4;
export const MIN_MERGE_LENGTH = MIN_WORD_LENGTH * 2 + 1; // 9 letters minimum for merge steals

// Get letter frequency count for a word
export function getLetterCounts(word) {
    const counts = {};
    for (const letter of word) {
        counts[letter] = (counts[letter] || 0) + 1;
    }
    return counts;
}

// Check if smallerCounts is a strict subset of largerCounts (fewer total letters)
export function isStrictSubset(smallerCounts, largerCounts) {
    let smallerTotal = 0;
    let largerTotal = 0;

    for (const letter in largerCounts) {
        largerTotal += largerCounts[letter];
    }

    for (const letter in smallerCounts) {
        smallerTotal += smallerCounts[letter];
        if (!largerCounts[letter] || smallerCounts[letter] > largerCounts[letter]) {
            return false;
        }
    }

    return smallerTotal < largerTotal;
}

// Get the letters that need to be added to go from smaller to larger
export function getAddedLetters(smallerCounts, largerCounts) {
    const added = [];
    for (const letter in largerCounts) {
        const diff = largerCounts[letter] - (smallerCounts[letter] || 0);
        for (let i = 0; i < diff; i++) {
            added.push(letter);
        }
    }
    return added.sort().join('');
}

// Combine two letter count objects
export function combineLetterCounts(counts1, counts2) {
    const combined = { ...counts1 };
    for (const letter in counts2) {
        combined[letter] = (combined[letter] || 0) + counts2[letter];
    }
    return combined;
}

// Check if counts1 + counts2 is a strict subset of targetCounts (need at least 1 more letter)
export function isCombinedStrictSubset(counts1, counts2, targetCounts) {
    const combined = combineLetterCounts(counts1, counts2);
    return isStrictSubset(combined, targetCounts);
}

// Common grammatical suffixes and prefixes (fallback when etymology not available)
export const INFLECTION_SUFFIXES = ['S', 'ES', 'ED', 'D', 'ING', 'ER', 'EST', 'LY', 'NESS', 'MENT', 'ABLE', 'IBLE', 'TION', 'SION', 'FUL', 'LESS', 'ISH', 'IZE', 'ISE', 'EN', 'LET', 'LETS', 'Y', 'IER', 'IEST'];
export const INFLECTION_PREFIXES = ['UN', 'RE', 'PRE', 'DE', 'DIS', 'MIS', 'NON', 'OVER', 'UNDER', 'OUT', 'SUB', 'SEMI', 'ANTI', 'MID', 'BI', 'TRI'];
const DOUBLE_CONSONANTS = new Set('BCDFGKLMNPRSTVZ');

// Check if two etymology strings are related
function etymologiesMatch(etym1, etym2) {
    // Same exact etymology = same root
    if (etym1 === etym2) {
        return true;
    }

    // Check if they share the same language and have similar roots
    // e.g., "latin:fīxus" and "latin:suffīxus" both end in "fixus"
    const [lang1, root1] = etym1.split(':');
    const [lang2, root2] = etym2.split(':');

    if (lang1 === lang2 && root1 && root2) {
        // Check if one root contains the other (for Latin affixed forms)
        // e.g., "fixus" is contained in "suffixus", "affixus", "praefixus"
        const r1 = root1.toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '');
        const r2 = root2.toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '');
        if (r1.length >= 3 && r2.length >= 3) {
            if (r2.endsWith(r1) || r1.endsWith(r2)) {
                return true;
            }
        }
    }

    return false;
}

// Check if two words share ANY etymological root
// Etymology values are now arrays of possible etymologies
export function shareEtymology(word1, word2) {
    const etymology = getEtymology();
    const etymList1 = etymology[word1];
    const etymList2 = etymology[word2];

    // If both have etymology, check if ANY pair matches
    if (etymList1 && etymList2 && Array.isArray(etymList1) && Array.isArray(etymList2)) {
        for (const etym1 of etymList1) {
            for (const etym2 of etymList2) {
                if (etymologiesMatch(etym1, etym2)) {
                    return true;
                }
            }
        }
        // Both have etymologies but no matches found
        return false;
    }

    // If etymology not available for one or both, return null (unknown)
    return null;
}

// Check if a steal is invalid (words share the same root)
export function isInflection(baseWord, resultWord) {
    // First, check etymology if available
    const etymResult = shareEtymology(baseWord, resultWord);
    if (etymResult === true) {
        return true; // Same etymology = invalid steal
    }

    // Always check affix patterns as a safety net
    // Etymology data may be incomplete (e.g., WIND has cognates but not Old English root)
    // If it looks like a simple suffix/prefix addition, it's likely related

    // Check for suffix: result = base + suffix
    if (resultWord.startsWith(baseWord)) {
        const suffix = resultWord.slice(baseWord.length);
        if (INFLECTION_SUFFIXES.includes(suffix)) {
            return true;
        }
        // Check for doubled consonant + suffix (e.g., FROG -> FROGGING)
        if (suffix.length >= 2) {
            const doubledChar = suffix[0];
            const restOfSuffix = suffix.slice(1);
            if (DOUBLE_CONSONANTS.has(doubledChar) &&
                baseWord.endsWith(doubledChar) &&
                INFLECTION_SUFFIXES.includes(restOfSuffix)) {
                return true;
            }
        }
    }

    // Check for prefix: result = prefix + base
    if (resultWord.endsWith(baseWord)) {
        const prefix = resultWord.slice(0, resultWord.length - baseWord.length);
        if (INFLECTION_PREFIXES.includes(prefix)) {
            return true;
        }
    }

    return false;
}

// Check if result is a compound word containing one of the source words
export function isCompoundContaining(word1, word2, resultWord) {
    return resultWord.includes(word1) || resultWord.includes(word2);
}

// Check word validity
export function checkWord(word) {
    const normalizedWord = word.trim().toUpperCase();
    if (!normalizedWord || !getIsLoaded()) return null;

    if (normalizedWord.length < MIN_WORD_LENGTH) {
        return 'too_short';
    }

    return getDictionary().has(normalizedWord) ? 'valid' : 'invalid';
}

// Steal-finding module for Snatch game
// Functions to find words that can be stolen or merged

import { getWordList } from './state.js';
import {
    MIN_WORD_LENGTH,
    MIN_MERGE_LENGTH,
    getLetterCounts,
    isStrictSubset,
    getAddedLetters,
    combineLetterCounts,
    isCombinedStrictSubset,
    isInflection,
    isCompoundContaining
} from './words.js';

// Core steal-finding algorithm
// direction: 'from' finds words that can become referenceWord (candidates are shorter)
// direction: 'to' finds words referenceWord can become (candidates are longer)
function findStealsCore(referenceWord, direction) {
    const referenceCounts = getLetterCounts(referenceWord);
    const results = [];
    const wordList = getWordList();

    for (const word of wordList) {
        if (word.length < MIN_WORD_LENGTH) continue;

        // Length check: 'from' wants shorter candidates, 'to' wants longer
        const validLength = direction === 'from'
            ? word.length < referenceWord.length
            : word.length > referenceWord.length;
        if (!validLength) continue;

        const wordCounts = getLetterCounts(word);

        // Subset check: smaller word's counts must be subset of larger word's counts
        const [smallerCounts, largerCounts] = direction === 'from'
            ? [wordCounts, referenceCounts]
            : [referenceCounts, wordCounts];

        if (isStrictSubset(smallerCounts, largerCounts)) {
            const addedLetters = getAddedLetters(smallerCounts, largerCounts);
            // For inflection check: first arg is base word, second is result word
            const [baseWord, resultWord] = direction === 'from'
                ? [word, referenceWord]
                : [referenceWord, word];
            const invalid = isInflection(baseWord, resultWord);

            results.push({
                word,
                addedLetters,
                invalid
            });
        }
    }

    // Sort: valid first, then by length, then alphabetically
    // 'from': longer words first (descending), 'to': shorter words first (ascending)
    const lengthMultiplier = direction === 'from' ? -1 : 1;
    results.sort((a, b) => {
        if (a.invalid !== b.invalid) {
            return a.invalid ? 1 : -1;
        }
        if (a.word.length !== b.word.length) {
            return (a.word.length - b.word.length) * lengthMultiplier;
        }
        return a.word.localeCompare(b.word);
    });

    return results;
}

// Find all words that could be stolen to make the target word
export function findStealsFrom(targetWord) {
    return findStealsCore(targetWord, 'from').map(({ word, addedLetters, invalid }) => ({
        baseWord: word,
        addedLetters,
        invalid
    }));
}

// Find all words that can be made by stealing the source word
export function findStealsTo(sourceWord) {
    return findStealsCore(sourceWord, 'to').map(({ word, addedLetters, invalid }) => ({
        resultWord: word,
        addedLetters,
        invalid
    }));
}

// Find all pairs of words that can be merged (with at least 1 added letter) to make the target word
export function findMergeSteals(targetWord, maxResults = 200) {
    const targetCounts = getLetterCounts(targetWord);
    const targetLength = targetWord.length;
    const results = [];
    const wordList = getWordList();

    // Minimum: 4 + 4 + 1 = 9 letters needed for a merge steal
    if (targetLength < MIN_MERGE_LENGTH) {
        return results;
    }

    // First, find all valid words that are subsets of the target
    const candidateWords = [];
    for (const word of wordList) {
        if (word.length < MIN_WORD_LENGTH || word.length > targetLength - MIN_WORD_LENGTH - 1) continue;

        const wordCounts = getLetterCounts(word);
        // Check if this word's letters are contained in target
        let isSubset = true;
        for (const letter in wordCounts) {
            if (!targetCounts[letter] || wordCounts[letter] > targetCounts[letter]) {
                isSubset = false;
                break;
            }
        }
        if (isSubset) {
            candidateWords.push({ word, counts: wordCounts });
        }
    }

    // Now find pairs that combine to form a strict subset of target
    const seen = new Set();
    outer: for (let i = 0; i < candidateWords.length; i++) {
        for (let j = i + 1; j < candidateWords.length; j++) {
            if (results.length >= maxResults) break outer;

            const word1 = candidateWords[i];
            const word2 = candidateWords[j];

            // Combined length must be less than target (need at least 1 added letter)
            if (word1.word.length + word2.word.length >= targetLength) continue;

            // Check if combined letters form a strict subset
            if (isCombinedStrictSubset(word1.counts, word2.counts, targetCounts)) {
                const combined = combineLetterCounts(word1.counts, word2.counts);
                const addedLetters = getAddedLetters(combined, targetCounts);

                // Create a canonical key to avoid duplicates
                const key = [word1.word, word2.word].sort().join('|');
                if (!seen.has(key)) {
                    seen.add(key);
                    const invalid = isCompoundContaining(word1.word, word2.word, targetWord);
                    results.push({
                        word1: word1.word,
                        word2: word2.word,
                        addedLetters,
                        invalid
                    });
                }
            }
        }
    }

    // Sort: valid first, then by total letters used (more letters first = fewer added), then alphabetically
    results.sort((a, b) => {
        if (a.invalid !== b.invalid) {
            return a.invalid ? 1 : -1;
        }
        const aTotal = a.word1.length + a.word2.length;
        const bTotal = b.word1.length + b.word2.length;
        if (bTotal !== aTotal) {
            return bTotal - aTotal;
        }
        return a.word1.localeCompare(b.word1);
    });

    return results;
}

// Find all words that can be merged with sourceWord (plus added letters) to make valid words
export function findMergeStealsTo(sourceWord, maxResults = 200) {
    const sourceCounts = getLetterCounts(sourceWord);
    const sourceLength = sourceWord.length;
    const results = [];
    const wordList = getWordList();

    // For each word in dictionary that's long enough to be a merge result
    for (const targetWord of wordList) {
        if (results.length >= maxResults) break;

        const targetLength = targetWord.length;
        // Target must be at least sourceWord + MIN_WORD_LENGTH + 1 (for the added letter)
        if (targetLength < sourceLength + MIN_WORD_LENGTH + 1) continue;
        // Limit target length to avoid very long searches
        if (targetLength > sourceLength + 10) continue;

        const targetCounts = getLetterCounts(targetWord);

        // Check if source is a subset of target
        let sourceIsSubset = true;
        for (const letter in sourceCounts) {
            if (!targetCounts[letter] || sourceCounts[letter] > targetCounts[letter]) {
                sourceIsSubset = false;
                break;
            }
        }
        if (!sourceIsSubset) continue;

        // Find the remaining letters after removing source from target
        const remainingCounts = {};
        for (const letter in targetCounts) {
            const remaining = targetCounts[letter] - (sourceCounts[letter] || 0);
            if (remaining > 0) {
                remainingCounts[letter] = remaining;
            }
        }

        const remainingLength = Object.values(remainingCounts).reduce((a, b) => a + b, 0);

        // Now find valid words that are strict subsets of remaining (need at least 1 added letter)
        for (const otherWord of wordList) {
            if (results.length >= maxResults) break;
            if (otherWord.length < MIN_WORD_LENGTH || otherWord.length >= remainingLength) continue;

            const otherCounts = getLetterCounts(otherWord);

            // Check if other word is a strict subset of remaining
            let isSubset = true;
            for (const letter in otherCounts) {
                if (!remainingCounts[letter] || otherCounts[letter] > remainingCounts[letter]) {
                    isSubset = false;
                    break;
                }
            }

            if (isSubset) {
                // Calculate added letters
                const combined = combineLetterCounts(sourceCounts, otherCounts);
                const addedLetters = getAddedLetters(combined, targetCounts);

                if (addedLetters.length > 0) {
                    const invalid = isCompoundContaining(sourceWord, otherWord, targetWord);
                    results.push({
                        otherWord,
                        addedLetters,
                        resultWord: targetWord,
                        invalid
                    });
                }
            }
        }
    }

    // Sort: valid first, then by result word length (shorter first), then by other word length, then alphabetically
    results.sort((a, b) => {
        if (a.invalid !== b.invalid) {
            return a.invalid ? 1 : -1;
        }
        if (a.resultWord.length !== b.resultWord.length) {
            return a.resultWord.length - b.resultWord.length;
        }
        if (b.otherWord.length !== a.otherWord.length) {
            return b.otherWord.length - a.otherWord.length;
        }
        return a.resultWord.localeCompare(b.resultWord);
    });

    return results;
}

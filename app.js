const DICTIONARY_URL = 'https://raw.githubusercontent.com/redbo/scrabble/master/dictionary.txt';

let dictionary = new Set();
let wordList = [];
let isLoaded = false;

const wordInput = document.getElementById('word-input');
const wordForm = document.getElementById('word-form');
const resultDiv = document.getElementById('result');
const stealsResultDiv = document.getElementById('steals-result');
const loadingDiv = document.getElementById('loading');
const checkBtn = document.getElementById('check-btn');
const stealsBtn = document.getElementById('steals-btn');

async function loadDictionary() {
    loadingDiv.classList.remove('hidden');
    checkBtn.disabled = true;
    stealsBtn.disabled = true;

    try {
        const response = await fetch(DICTIONARY_URL);
        if (!response.ok) throw new Error('Failed to fetch dictionary');

        const text = await response.text();
        const words = text.split('\n').map(w => w.trim().toUpperCase()).filter(w => w.length > 0);
        dictionary = new Set(words);
        wordList = Array.from(dictionary);
        isLoaded = true;
        console.log(`Dictionary loaded: ${dictionary.size} words`);
    } catch (error) {
        console.error('Error loading dictionary:', error);
        resultDiv.innerHTML = 'Error loading dictionary. Please refresh the page.';
        resultDiv.className = 'result invalid';
        resultDiv.classList.remove('hidden');
    } finally {
        loadingDiv.classList.add('hidden');
        checkBtn.disabled = false;
        stealsBtn.disabled = false;
    }
}

const MIN_WORD_LENGTH = 4;

function checkWord(word) {
    const normalizedWord = word.trim().toUpperCase();
    if (!normalizedWord || !isLoaded) return null;

    if (normalizedWord.length < MIN_WORD_LENGTH) {
        return 'too_short';
    }

    return dictionary.has(normalizedWord) ? 'valid' : 'invalid';
}

function displayResult(word, result) {
    resultDiv.classList.remove('hidden', 'valid', 'invalid', 'too-short');
    stealsResultDiv.classList.add('hidden');

    if (result === 'valid') {
        resultDiv.classList.add('valid');
        resultDiv.innerHTML = `<span class="word">${word}</span>Valid Scrabble word!`;
    } else if (result === 'too_short') {
        resultDiv.classList.add('too-short');
        resultDiv.innerHTML = `<span class="word">${word}</span>Too short (minimum ${MIN_WORD_LENGTH} letters)`;
    } else {
        resultDiv.classList.add('invalid');
        resultDiv.innerHTML = `<span class="word">${word}</span>Not in dictionary`;
    }
}

// Get letter frequency count for a word
function getLetterCounts(word) {
    const counts = {};
    for (const letter of word) {
        counts[letter] = (counts[letter] || 0) + 1;
    }
    return counts;
}

// Check if smallerCounts is a strict subset of largerCounts (fewer total letters)
function isStrictSubset(smallerCounts, largerCounts) {
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
function getAddedLetters(smallerCounts, largerCounts) {
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
function combineLetterCounts(counts1, counts2) {
    const combined = { ...counts1 };
    for (const letter in counts2) {
        combined[letter] = (combined[letter] || 0) + counts2[letter];
    }
    return combined;
}

// Check if counts1 + counts2 is a strict subset of targetCounts (need at least 1 more letter)
function isCombinedStrictSubset(counts1, counts2, targetCounts) {
    const combined = combineLetterCounts(counts1, counts2);
    return isStrictSubset(combined, targetCounts);
}

// Find all words that could be stolen to make the target word
function findStealsFrom(targetWord) {
    const targetCounts = getLetterCounts(targetWord);
    const results = [];

    for (const word of wordList) {
        if (word.length >= targetWord.length || word.length < MIN_WORD_LENGTH) continue;

        const wordCounts = getLetterCounts(word);
        if (isStrictSubset(wordCounts, targetCounts)) {
            const addedLetters = getAddedLetters(wordCounts, targetCounts);
            results.push({ baseWord: word, addedLetters });
        }
    }

    // Sort by base word length (longer first), then alphabetically
    results.sort((a, b) => {
        if (b.baseWord.length !== a.baseWord.length) {
            return b.baseWord.length - a.baseWord.length;
        }
        return a.baseWord.localeCompare(b.baseWord);
    });

    return results;
}

// Find all words that can be made by stealing the source word
function findStealsTo(sourceWord) {
    const sourceCounts = getLetterCounts(sourceWord);
    const results = [];

    for (const word of wordList) {
        if (word.length <= sourceWord.length || word.length < MIN_WORD_LENGTH) continue;

        const wordCounts = getLetterCounts(word);
        if (isStrictSubset(sourceCounts, wordCounts)) {
            const addedLetters = getAddedLetters(sourceCounts, wordCounts);
            results.push({ resultWord: word, addedLetters });
        }
    }

    // Sort by result word length (shorter first), then alphabetically
    results.sort((a, b) => {
        if (a.resultWord.length !== b.resultWord.length) {
            return a.resultWord.length - b.resultWord.length;
        }
        return a.resultWord.localeCompare(b.resultWord);
    });

    return results;
}

// Find all pairs of words that can be merged (with at least 1 added letter) to make the target word
function findMergeSteals(targetWord, maxResults = 200) {
    const targetCounts = getLetterCounts(targetWord);
    const targetLength = targetWord.length;
    const results = [];

    // Minimum: 4 + 4 + 1 = 9 letters needed for a merge steal
    if (targetLength < MIN_WORD_LENGTH * 2 + 1) {
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
                    results.push({
                        word1: word1.word,
                        word2: word2.word,
                        addedLetters
                    });
                }
            }
        }
    }

    // Sort by total letters used (more letters first = fewer added), then alphabetically
    results.sort((a, b) => {
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
function findMergeStealsTo(sourceWord, maxResults = 200) {
    const sourceCounts = getLetterCounts(sourceWord);
    const sourceLength = sourceWord.length;
    const results = [];

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
                    results.push({
                        otherWord,
                        addedLetters,
                        resultWord: targetWord
                    });
                }
            }
        }
    }

    // Sort by result word length (shorter first), then by other word length, then alphabetically
    results.sort((a, b) => {
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

const MAX_RESULTS = 100;

async function displaySteals(word) {
    resultDiv.classList.add('hidden');
    stealsResultDiv.classList.remove('hidden');

    const normalizedWord = word.trim().toUpperCase();

    if (normalizedWord.length < MIN_WORD_LENGTH) {
        stealsResultDiv.innerHTML = `<div class="no-steals">"${normalizedWord}" is too short (minimum ${MIN_WORD_LENGTH} letters)</div>`;
        return;
    }

    if (!dictionary.has(normalizedWord)) {
        stealsResultDiv.innerHTML = `<div class="no-steals">"${normalizedWord}" is not a valid word</div>`;
        return;
    }

    const stealsFrom = findStealsFrom(normalizedWord);
    const stealsTo = findStealsTo(normalizedWord);

    // Allow UI to stay responsive between expensive operations
    await new Promise(resolve => setTimeout(resolve, 0));

    const mergeSteals = findMergeSteals(normalizedWord);

    await new Promise(resolve => setTimeout(resolve, 0));

    const mergeStealsTo = findMergeStealsTo(normalizedWord);

    let html = '';

    // Steals FROM section (what words can become this word)
    html += '<div class="steals-section">';
    html += `<h3>Steal to make ${normalizedWord}</h3>`;
    if (stealsFrom.length > 0) {
        html += '<div class="steals-list">';
        for (const { baseWord, addedLetters } of stealsFrom) {
            html += `
                <div class="steal-item">
                    <span class="base-word">${baseWord}</span>
                    <span class="added-letters">+${addedLetters}</span>
                </div>
            `;
        }
        html += '</div>';
    } else {
        html += '<div class="no-steals">No words can be stolen to make this word</div>';
    }
    html += '</div>';

    // Merge steals section (two words combined with added letters)
    html += '<div class="steals-section">';
    html += `<h3>Merge to make ${normalizedWord}</h3>`;
    if (mergeSteals.length > 0) {
        html += '<div class="steals-list">';
        for (const { word1, word2, addedLetters } of mergeSteals) {
            html += `
                <div class="steal-item merge-item">
                    <span class="base-word">${word1}</span>
                    <span class="merge-plus">+</span>
                    <span class="base-word">${word2}</span>
                    <span class="added-letters">+${addedLetters}</span>
                </div>
            `;
        }
        html += '</div>';
    } else {
        if (normalizedWord.length < MIN_WORD_LENGTH * 2 + 1) {
            html += `<div class="no-steals">Word too short for merge (need ${MIN_WORD_LENGTH * 2 + 1}+ letters)</div>`;
        } else {
            html += '<div class="no-steals">No merge steals found</div>';
        }
    }
    html += '</div>';

    // Steals TO section (what this word can become)
    html += '<div class="steals-section">';
    html += `<h3>Steal ${normalizedWord} to make</h3>`;
    if (stealsTo.length > 0) {
        html += '<div class="steals-list">';
        for (const { resultWord, addedLetters } of stealsTo) {
            html += `
                <div class="steal-item">
                    <span class="added-letters">+${addedLetters}</span>
                    <span class="arrow">→</span>
                    <span class="result-word">${resultWord}</span>
                </div>
            `;
        }
        html += '</div>';
    } else {
        html += '<div class="no-steals">This word cannot be stolen to make other words</div>';
    }
    html += '</div>';

    // Merge steals TO section (merge this word with another to make new words)
    html += '<div class="steals-section">';
    html += `<h3>Merge ${normalizedWord} with</h3>`;
    if (mergeStealsTo.length > 0) {
        html += '<div class="steals-list">';
        for (const { otherWord, addedLetters, resultWord } of mergeStealsTo) {
            html += `
                <div class="steal-item merge-item">
                    <span class="base-word">${otherWord}</span>
                    <span class="added-letters">+${addedLetters}</span>
                    <span class="arrow">→</span>
                    <span class="result-word">${resultWord}</span>
                </div>
            `;
        }
        html += '</div>';
    } else {
        html += '<div class="no-steals">No merge possibilities found</div>';
    }
    html += '</div>';

    stealsResultDiv.innerHTML = html;
}

wordForm.addEventListener('submit', (e) => {
    e.preventDefault();
    const word = wordInput.value.trim();
    if (!word) return;

    if (!isLoaded) {
        resultDiv.innerHTML = 'Dictionary still loading...';
        resultDiv.className = 'result';
        resultDiv.classList.remove('hidden');
        return;
    }

    const isValid = checkWord(word);
    displayResult(word, isValid);
});

stealsBtn.addEventListener('click', async () => {
    const word = wordInput.value.trim();
    if (!word) return;

    if (!isLoaded) {
        stealsResultDiv.innerHTML = '<div class="no-steals">Dictionary still loading...</div>';
        stealsResultDiv.classList.remove('hidden');
        return;
    }

    stealsBtn.disabled = true;
    stealsBtn.textContent = 'Searching...';
    resultDiv.classList.add('hidden');
    stealsResultDiv.classList.remove('hidden');
    stealsResultDiv.innerHTML = '<div class="loading">Finding steals...</div>';

    // Let the UI update before starting expensive computation
    await new Promise(resolve => setTimeout(resolve, 10));

    try {
        await displaySteals(word);
    } finally {
        stealsBtn.disabled = false;
        stealsBtn.textContent = 'Find Steals';
    }
});

// Load dictionary on page load
loadDictionary();

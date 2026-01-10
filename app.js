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

function displaySteals(word) {
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

stealsBtn.addEventListener('click', () => {
    const word = wordInput.value.trim();
    if (!word) return;

    if (!isLoaded) {
        stealsResultDiv.innerHTML = '<div class="no-steals">Dictionary still loading...</div>';
        stealsResultDiv.classList.remove('hidden');
        return;
    }

    displaySteals(word);
});

// Load dictionary on page load
loadDictionary();

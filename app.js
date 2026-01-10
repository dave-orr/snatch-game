const DICTIONARY_URL = 'https://raw.githubusercontent.com/redbo/scrabble/master/dictionary.txt';

let dictionary = new Set();
let isLoaded = false;

const wordInput = document.getElementById('word-input');
const wordForm = document.getElementById('word-form');
const resultDiv = document.getElementById('result');
const loadingDiv = document.getElementById('loading');
const checkBtn = document.getElementById('check-btn');

async function loadDictionary() {
    loadingDiv.classList.remove('hidden');
    checkBtn.disabled = true;

    try {
        const response = await fetch(DICTIONARY_URL);
        if (!response.ok) throw new Error('Failed to fetch dictionary');

        const text = await response.text();
        const words = text.split('\n').map(w => w.trim().toUpperCase()).filter(w => w.length > 0);
        dictionary = new Set(words);
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
    }
}

function checkWord(word) {
    const normalizedWord = word.trim().toUpperCase();

    if (!normalizedWord) {
        return null;
    }

    if (!isLoaded) {
        return null;
    }

    return dictionary.has(normalizedWord);
}

function displayResult(word, isValid) {
    resultDiv.classList.remove('hidden', 'valid', 'invalid');

    if (isValid) {
        resultDiv.classList.add('valid');
        resultDiv.innerHTML = `<span class="word">${word}</span>Valid Scrabble word!`;
    } else {
        resultDiv.classList.add('invalid');
        resultDiv.innerHTML = `<span class="word">${word}</span>Not in dictionary`;
    }
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

// Allow checking on Enter key
wordInput.addEventListener('keypress', (e) => {
    if (e.key === 'Enter') {
        e.preventDefault();
        wordForm.dispatchEvent(new Event('submit'));
    }
});

// Load dictionary on page load
loadDictionary();

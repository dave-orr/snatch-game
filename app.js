import {
    DICTIONARY_URL,
    ETYMOLOGY_URL,
    getDictionary,
    setDictionary,
    getEtymology,
    setEtymology,
    getIsLoaded,
    setIsLoaded,
    getHistoryIndex,
    setHistoryIndex,
    getIsNavigating,
    setIsNavigating,
    pushToHistory,
    truncateHistoryAt,
    getHistoryWord,
    getHistoryLength
} from './state.js';

import {
    MIN_WORD_LENGTH,
    checkWord,
    getLetterCounts,
    isStrictSubset,
    getAddedLetters,
    shareEtymology
} from './words.js';

import {
    findStealsFrom,
    findStealsTo,
    findMergeSteals,
    findMergeStealsTo
} from './steals.js';

const wordInput = document.getElementById('word-input');
const wordForm = document.getElementById('word-form');
const resultDiv = document.getElementById('result');
const stealsResultDiv = document.getElementById('steals-result');
const loadingDiv = document.getElementById('loading');
const checkBtn = document.getElementById('check-btn');
const stealsBtn = document.getElementById('steals-btn');
const backBtn = document.getElementById('back-btn');
const forwardBtn = document.getElementById('forward-btn');

// Compare mode elements
const compareToggle = document.getElementById('compare-toggle');
const compareField = document.getElementById('compare-field');
const compareWord = document.getElementById('compare-word');
const compareBtn = document.getElementById('compare-btn');

async function loadDictionary() {
    loadingDiv.classList.remove('hidden');
    checkBtn.disabled = true;
    stealsBtn.disabled = true;

    try {
        // Load dictionary and etymology in parallel
        const [dictResponse, etymResponse] = await Promise.all([
            fetch(DICTIONARY_URL),
            fetch(ETYMOLOGY_URL).catch(() => null) // Etymology is optional
        ]);

        if (!dictResponse.ok) throw new Error('Failed to fetch dictionary');

        const text = await dictResponse.text();
        const words = text.split('\n').map(w => w.trim().toUpperCase()).filter(w => w.length > 0);
        setDictionary(new Set(words));
        // wordList is set automatically by setDictionary

        // Load etymology if available
        if (etymResponse && etymResponse.ok) {
            setEtymology(await etymResponse.json());
            console.log(`Etymology loaded: ${Object.keys(getEtymology()).length} entries`);
        } else {
            console.log('Etymology not available, using affix-based detection only');
        }

        setIsLoaded(true);
        console.log(`Dictionary loaded: ${getDictionary().size} words`);
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

// Navigation history functions
function addToHistory(word) {
    if (getIsNavigating()) return;

    const normalizedWord = word.trim().toUpperCase();
    if (!normalizedWord) return;

    // Remove any forward history if we're not at the end
    const currentIndex = getHistoryIndex();
    const historyLength = getHistoryLength();

    if (historyLength > 0 && currentIndex < historyLength - 1) {
        truncateHistoryAt(currentIndex);
    }

    // Don't add duplicate if it's the same as current word
    const currentWord = historyLength > 0 ? getHistoryWord(currentIndex) : null;
    if (currentWord !== normalizedWord) {
        pushToHistory(normalizedWord);
    }

    console.log('History:', getHistoryLength(), 'Index:', getHistoryIndex());
    updateNavigationButtons();
}

function updateNavigationButtons() {
    backBtn.disabled = getHistoryIndex() <= 0;
    forwardBtn.disabled = getHistoryIndex() >= getHistoryLength() - 1;
    console.log('Navigation buttons updated - Back:', !backBtn.disabled, 'Forward:', !forwardBtn.disabled);
}

async function navigateBack() {
    if (getHistoryIndex() > 0) {
        setHistoryIndex(getHistoryIndex() - 1);
        setIsNavigating(true);
        const word = getHistoryWord(getHistoryIndex());
        console.log('Navigating back to:', word);
        wordInput.value = word;
        try {
            await performStealsSearch(word, false);
        } finally {
            setIsNavigating(false);
            updateNavigationButtons();
        }
    }
}

async function navigateForward() {
    if (getHistoryIndex() < getHistoryLength() - 1) {
        setHistoryIndex(getHistoryIndex() + 1);
        setIsNavigating(true);
        const word = getHistoryWord(getHistoryIndex());
        console.log('Navigating forward to:', word);
        wordInput.value = word;
        try {
            await performStealsSearch(word, false);
        } finally {
            setIsNavigating(false);
            updateNavigationButtons();
        }
    }
}

// Format etymology for display
function formatEtymology(word) {
    const etymology = getEtymology();
    const etymList = etymology[word];
    if (!etymList || !Array.isArray(etymList) || etymList.length === 0) {
        return '<div class="etymology">Etymology: <span class="etymology-unknown">unknown</span></div>';
    }

    // Format each etymology entry nicely
    const formatted = etymList.map(e => {
        const [lang, root] = e.split(':');
        if (!root || root === '-') {
            return `<span class="etymology-lang">${lang}</span>`;
        }
        return `<span class="etymology-lang">${lang}</span>:<span class="etymology-root">${root}</span>`;
    }).join(', ');

    return `<div class="etymology">Etymology: ${formatted}</div>`;
}

function displayResult(word, result) {
    resultDiv.classList.remove('hidden', 'valid', 'invalid', 'too-short');
    stealsResultDiv.classList.add('hidden');

    const normalizedWord = word.trim().toUpperCase();
    const etymHtml = result === 'valid' ? formatEtymology(normalizedWord) : '';

    if (result === 'valid') {
        resultDiv.classList.add('valid');
        resultDiv.innerHTML = `<span class="word">${normalizedWord}</span>Valid Scrabble word!${etymHtml}`;
    } else if (result === 'too_short') {
        resultDiv.classList.add('too-short');
        resultDiv.innerHTML = `<span class="word">${normalizedWord}</span>Too short (minimum ${MIN_WORD_LENGTH} letters)`;
    } else {
        resultDiv.classList.add('invalid');
        resultDiv.innerHTML = `<span class="word">${normalizedWord}</span>Not in dictionary`;
    }
}

const MAX_RESULTS = 100;

// Group results by number of added letters
function groupByAddedLetters(results, addedLettersKey = 'addedLetters') {
    const groups = {};
    for (const result of results) {
        const count = result[addedLettersKey].length;
        if (!groups[count]) {
            groups[count] = [];
        }
        groups[count].push(result);
    }
    return groups;
}

// Render a collapsible group
function renderCollapsibleGroup(letterCount, items, renderItem, expanded = false) {
    const id = `group-${Math.random().toString(36).substr(2, 9)}`;
    const expandedClass = expanded ? 'expanded' : '';
    const itemsHtml = items.map(renderItem).join('');

    return `
        <div class="collapsible-group ${expandedClass}">
            <button class="collapsible-header" onclick="toggleGroup('${id}')">
                <span class="collapsible-title">+${letterCount} letter${letterCount > 1 ? 's' : ''}</span>
                <span class="collapsible-count">${items.length} result${items.length > 1 ? 's' : ''}</span>
                <span class="collapsible-arrow">&#9660;</span>
            </button>
            <div class="collapsible-content" id="${id}">
                <div class="steals-list">${itemsHtml}</div>
            </div>
        </div>
    `;
}

// Toggle collapsible group
function toggleGroup(id) {
    const content = document.getElementById(id);
    const group = content.parentElement;
    group.classList.toggle('expanded');
}

// Make toggleGroup available globally
window.toggleGroup = toggleGroup;

async function displaySteals(word) {
    resultDiv.classList.add('hidden');
    stealsResultDiv.classList.remove('hidden');

    const normalizedWord = word.trim().toUpperCase();

    if (normalizedWord.length < MIN_WORD_LENGTH) {
        stealsResultDiv.innerHTML = `<div class="no-steals">"${normalizedWord}" is too short (minimum ${MIN_WORD_LENGTH} letters)</div>`;
        return;
    }

    if (!getDictionary().has(normalizedWord)) {
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

    // Show etymology at the top
    html += `<div class="steals-header">
        <h2 class="steals-word">${normalizedWord}</h2>
        ${formatEtymology(normalizedWord)}
    </div>`;

    // Render function for "steal from" items
    const renderStealFrom = ({ baseWord, addedLetters, invalid }) => `
        <div class="steal-item${invalid ? ' invalid-steal' : ''}">
            <span class="base-word">${baseWord}</span>
            <span class="added-letters">+${addedLetters}</span>
            ${invalid ? '<span class="invalid-label">same root</span>' : ''}
        </div>
    `;

    // Render function for "steal to" items
    const renderStealTo = ({ resultWord, addedLetters, invalid }) => `
        <div class="steal-item${invalid ? ' invalid-steal' : ''}">
            <span class="added-letters">+${addedLetters}</span>
            <span class="arrow">→</span>
            <span class="result-word">${resultWord}</span>
            ${invalid ? '<span class="invalid-label">same root</span>' : ''}
        </div>
    `;

    // Render function for merge items
    const renderMergeFrom = ({ word1, word2, addedLetters, invalid }) => `
        <div class="steal-item merge-item${invalid ? ' invalid-steal' : ''}">
            <span class="base-word">${word1}</span>
            <span class="merge-plus">+</span>
            <span class="base-word">${word2}</span>
            <span class="added-letters">+${addedLetters}</span>
            ${invalid ? '<span class="invalid-label">compound</span>' : ''}
        </div>
    `;

    // Render function for merge-to items
    const renderMergeTo = ({ otherWord, addedLetters, resultWord, invalid }) => `
        <div class="steal-item merge-item${invalid ? ' invalid-steal' : ''}">
            <span class="base-word">${otherWord}</span>
            <span class="added-letters">+${addedLetters}</span>
            <span class="arrow">→</span>
            <span class="result-word">${resultWord}</span>
            ${invalid ? '<span class="invalid-label">compound</span>' : ''}
        </div>
    `;

    // Helper to render grouped results
    const renderGroupedResults = (results, renderItem, emptyMessage) => {
        if (results.length === 0) {
            return `<div class="no-steals">${emptyMessage}</div>`;
        }

        const groups = groupByAddedLetters(results);
        const sortedCounts = Object.keys(groups).map(Number).sort((a, b) => a - b);

        let groupsHtml = '';
        for (const count of sortedCounts) {
            const expanded = count === 1; // Expand 1-letter groups by default
            groupsHtml += renderCollapsibleGroup(count, groups[count], renderItem, expanded);
        }
        return groupsHtml;
    };

    // Steals FROM section (what words can become this word)
    html += '<div class="steals-section">';
    html += `<h3>Steal to make ${normalizedWord}</h3>`;
    html += renderGroupedResults(stealsFrom, renderStealFrom, 'No words can be stolen to make this word');
    html += '</div>';

    // Merge steals section (two words combined with added letters)
    html += '<div class="steals-section">';
    html += `<h3>Merge to make ${normalizedWord}</h3>`;
    if (normalizedWord.length < MIN_WORD_LENGTH * 2 + 1) {
        html += `<div class="no-steals">Word too short for merge (need ${MIN_WORD_LENGTH * 2 + 1}+ letters)</div>`;
    } else {
        html += renderGroupedResults(mergeSteals, renderMergeFrom, 'No merge steals found');
    }
    html += '</div>';

    // Steals TO section (what this word can become)
    html += '<div class="steals-section">';
    html += `<h3>Steal ${normalizedWord} to make</h3>`;
    html += renderGroupedResults(stealsTo, renderStealTo, 'This word cannot be stolen to make other words');
    html += '</div>';

    // Merge steals TO section (merge this word with another to make new words)
    html += '<div class="steals-section">';
    html += `<h3>Merge ${normalizedWord} with</h3>`;
    html += renderGroupedResults(mergeStealsTo, renderMergeTo, 'No merge possibilities found');
    html += '</div>';

    stealsResultDiv.innerHTML = html;
}

wordForm.addEventListener('submit', (e) => {
    e.preventDefault();
    const word = wordInput.value.trim();
    if (!word) return;

    if (!getIsLoaded()) {
        resultDiv.innerHTML = 'Dictionary still loading...';
        resultDiv.className = 'result';
        resultDiv.classList.remove('hidden');
        return;
    }

    const isValid = checkWord(word);
    displayResult(word, isValid);
});

// Perform steals search - can be awaited by navigation functions
async function performStealsSearch(word, addToHistoryFlag = true) {
    if (!word) return;

    if (!getIsLoaded()) {
        stealsResultDiv.innerHTML = '<div class="no-steals">Dictionary still loading...</div>';
        stealsResultDiv.classList.remove('hidden');
        return;
    }

    // Add to history when finding steals (unless navigating)
    if (addToHistoryFlag) {
        addToHistory(word);
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
}

stealsBtn.addEventListener('click', async () => {
    const word = wordInput.value.trim();
    await performStealsSearch(word);
});

// Handle clicking on words to update the form
function handleWordClick(event) {
    const target = event.target;

    // Check if the clicked element is a word element
    if (target.classList.contains('word') ||
        target.classList.contains('base-word') ||
        target.classList.contains('result-word')) {

        const clickedWord = target.textContent.trim();

        // Update the input field
        wordInput.value = clickedWord;

        // Add to history before triggering search
        addToHistory(clickedWord);

        // Automatically trigger steals search
        stealsBtn.click();
    }
}

// Add event delegation for clickable words
resultDiv.addEventListener('click', handleWordClick);
stealsResultDiv.addEventListener('click', handleWordClick);

// Navigation button listeners
backBtn.addEventListener('click', navigateBack);
forwardBtn.addEventListener('click', navigateForward);

// Compare mode toggle
compareToggle.addEventListener('click', () => {
    const isActive = compareToggle.classList.toggle('active');
    if (isActive) {
        compareField.classList.remove('hidden');
        compareWord.focus();
    } else {
        compareField.classList.add('hidden');
        compareWord.value = '';
        // Clear any existing compare result
        const existingResult = document.querySelector('.compare-result');
        if (existingResult) {
            existingResult.remove();
        }
    }
});

// Format etymology for compare display (simpler version without the "Etymology:" prefix)
function formatEtymologySimple(word) {
    const etymology = getEtymology();
    const etymList = etymology[word];
    if (!etymList || !Array.isArray(etymList) || etymList.length === 0) {
        return '<span class="etymology-unknown">unknown</span>';
    }

    return etymList.map(e => {
        const [lang, root] = e.split(':');
        if (!root || root === '-') {
            return `<span class="etymology-lang">${lang}</span>`;
        }
        return `<span class="etymology-lang">${lang}</span>:<span class="etymology-root">${root}</span>`;
    }).join(', ');
}

// Get shared etymologies between two words
function getSharedEtymologies(word1, word2) {
    const etymology = getEtymology();
    const etymList1 = etymology[word1];
    const etymList2 = etymology[word2];
    const shared = [];

    if (etymList1 && etymList2 && Array.isArray(etymList1) && Array.isArray(etymList2)) {
        for (const etym1 of etymList1) {
            for (const etym2 of etymList2) {
                // Check if they match (reusing the same logic from words.js)
                if (etym1 === etym2) {
                    shared.push(etym1);
                } else {
                    const [lang1, root1] = etym1.split(':');
                    const [lang2, root2] = etym2.split(':');
                    if (lang1 === lang2 && root1 && root2) {
                        const r1 = root1.toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '');
                        const r2 = root2.toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '');
                        if (r1.length >= 3 && r2.length >= 3) {
                            if (r2.endsWith(r1) || r1.endsWith(r2)) {
                                // Return the shorter root as the "base"
                                shared.push(r1.length <= r2.length ? etym1 : etym2);
                            }
                        }
                    }
                }
            }
        }
    }

    return [...new Set(shared)]; // Remove duplicates
}

// Check if word2 can be stolen from word1
function checkSteal(baseWord, stealWord) {
    const base = baseWord.trim().toUpperCase();
    const steal = stealWord.trim().toUpperCase();

    // Validate both words
    if (base.length < MIN_WORD_LENGTH) {
        return { error: `"${base}" is too short (minimum ${MIN_WORD_LENGTH} letters)` };
    }
    if (steal.length < MIN_WORD_LENGTH) {
        return { error: `"${steal}" is too short (minimum ${MIN_WORD_LENGTH} letters)` };
    }
    if (!getDictionary().has(base)) {
        return { error: `"${base}" is not a valid word` };
    }
    if (!getDictionary().has(steal)) {
        return { error: `"${steal}" is not a valid word` };
    }
    if (steal.length <= base.length) {
        return { error: `Steal word must be longer than base word` };
    }

    const baseCounts = getLetterCounts(base);
    const stealCounts = getLetterCounts(steal);

    // Check if base is a strict subset of steal
    if (!isStrictSubset(baseCounts, stealCounts)) {
        return {
            canSteal: false,
            reason: 'letters',
            base,
            steal,
            message: `${base} cannot become ${steal} - letters don't match`
        };
    }

    const addedLetters = getAddedLetters(baseCounts, stealCounts);

    // Check if they share etymology (making it an invalid steal)
    const sharedEtym = shareEtymology(base, steal);
    const sharedRoots = getSharedEtymologies(base, steal);

    // Also check for affix patterns
    let isAffix = false;
    const INFLECTION_SUFFIXES = ['S', 'ES', 'ED', 'D', 'ING', 'ER', 'EST', 'LY', 'NESS', 'MENT', 'ABLE', 'IBLE', 'TION', 'SION', 'FUL', 'LESS', 'ISH', 'IZE', 'ISE', 'EN', 'LET', 'LETS', 'Y', 'IER', 'IEST'];
    const INFLECTION_PREFIXES = ['UN', 'RE', 'PRE', 'DE', 'DIS', 'MIS', 'NON', 'OVER', 'UNDER', 'OUT', 'SUB', 'SEMI', 'ANTI', 'MID', 'BI', 'TRI'];

    if (steal.startsWith(base)) {
        const suffix = steal.slice(base.length);
        if (INFLECTION_SUFFIXES.includes(suffix)) {
            isAffix = true;
        }
    }
    if (steal.endsWith(base)) {
        const prefix = steal.slice(0, steal.length - base.length);
        if (INFLECTION_PREFIXES.includes(prefix)) {
            isAffix = true;
        }
    }

    if (sharedEtym === true || isAffix) {
        return {
            canSteal: false,
            reason: 'same_root',
            base,
            steal,
            addedLetters,
            sharedRoots,
            message: 'Same root - invalid steal'
        };
    }

    return {
        canSteal: true,
        base,
        steal,
        addedLetters,
        message: 'Valid steal!'
    };
}

// Display compare result
function displayCompareResult(result) {
    // Remove any existing compare result
    const existingResult = document.querySelector('.compare-result');
    if (existingResult) {
        existingResult.remove();
    }

    // Hide the regular results
    resultDiv.classList.add('hidden');
    stealsResultDiv.classList.add('hidden');

    const resultContainer = document.createElement('div');
    resultContainer.className = 'compare-result';

    if (result.error) {
        resultContainer.classList.add('not-a-steal');
        resultContainer.innerHTML = `
            <div class="compare-verdict">${result.error}</div>
        `;
    } else if (!result.canSteal && result.reason === 'letters') {
        resultContainer.classList.add('not-a-steal');
        resultContainer.innerHTML = `
            <div class="compare-words">
                <div class="compare-word">
                    <div class="word-text">${result.base}</div>
                    <div class="etymology">${formatEtymologySimple(result.base)}</div>
                </div>
                <span class="compare-arrow-large">→</span>
                <div class="compare-word">
                    <div class="word-text">${result.steal}</div>
                    <div class="etymology">${formatEtymologySimple(result.steal)}</div>
                </div>
            </div>
            <div class="compare-verdict">Not a steal - letters don't match</div>
        `;
    } else if (!result.canSteal && result.reason === 'same_root') {
        resultContainer.classList.add('invalid-steal');
        let sharedRootsHtml = '';
        if (result.sharedRoots && result.sharedRoots.length > 0) {
            const rootsFormatted = result.sharedRoots.map(r => {
                const [lang, root] = r.split(':');
                return `<span class="etymology-lang">${lang}</span>:<span class="etymology-root">${root}</span>`;
            }).join(', ');
            sharedRootsHtml = `<div class="shared-roots"><strong>Shared root:</strong> ${rootsFormatted}</div>`;
        }
        resultContainer.innerHTML = `
            <div class="compare-words">
                <div class="compare-word">
                    <div class="word-text">${result.base}</div>
                    <div class="etymology">${formatEtymologySimple(result.base)}</div>
                </div>
                <span class="compare-arrow-large">→</span>
                <div class="compare-word">
                    <div class="word-text">${result.steal}</div>
                    <div class="etymology">${formatEtymologySimple(result.steal)}</div>
                </div>
            </div>
            <div class="compare-added">+${result.addedLetters}</div>
            <div class="compare-verdict">Invalid steal - same root</div>
            ${sharedRootsHtml}
        `;
    } else {
        resultContainer.classList.add('valid-steal');
        resultContainer.innerHTML = `
            <div class="compare-words">
                <div class="compare-word">
                    <div class="word-text">${result.base}</div>
                    <div class="etymology">${formatEtymologySimple(result.base)}</div>
                </div>
                <span class="compare-arrow-large">→</span>
                <div class="compare-word">
                    <div class="word-text">${result.steal}</div>
                    <div class="etymology">${formatEtymologySimple(result.steal)}</div>
                </div>
            </div>
            <div class="compare-added">+${result.addedLetters}</div>
            <div class="compare-verdict">Valid steal!</div>
        `;
    }

    // Insert after compare field
    compareField.insertAdjacentElement('afterend', resultContainer);
}

// Compare button click handler
compareBtn.addEventListener('click', () => {
    if (!getIsLoaded()) {
        displayCompareResult({ error: 'Dictionary still loading...' });
        return;
    }

    const baseWord = wordInput.value.trim();
    const stealWord = compareWord.value.trim();

    if (!baseWord) {
        displayCompareResult({ error: 'Please enter a base word above' });
        return;
    }
    if (!stealWord) {
        displayCompareResult({ error: 'Please enter a steal word' });
        return;
    }

    const result = checkSteal(baseWord, stealWord);
    displayCompareResult(result);
});

// Load dictionary on page load
loadDictionary();

// Navigation module for Snatch game
// History navigation and state management

import {
    getIsNavigating,
    setIsNavigating,
    getHistoryIndex,
    setHistoryIndex,
    getHistoryLength,
    getHistoryWord,
    pushToHistory,
    truncateHistoryAt
} from './state.js';

// Add a word to navigation history
export function addToHistory(word, updateButtonsFn) {
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
    updateButtonsFn();
}

// Update navigation button states
export function updateNavigationButtons(backBtn, forwardBtn) {
    backBtn.disabled = getHistoryIndex() <= 0;
    forwardBtn.disabled = getHistoryIndex() >= getHistoryLength() - 1;
    console.log('Navigation buttons updated - Back:', !backBtn.disabled, 'Forward:', !forwardBtn.disabled);
}

// Navigate back in history
export async function navigateBack(wordInput, searchFn, updateButtonsFn) {
    if (getHistoryIndex() > 0) {
        setHistoryIndex(getHistoryIndex() - 1);
        setIsNavigating(true);
        const word = getHistoryWord(getHistoryIndex());
        console.log('Navigating back to:', word);
        wordInput.value = word;
        try {
            await searchFn(word, false);
        } finally {
            setIsNavigating(false);
            updateButtonsFn();
        }
    }
}

// Navigate forward in history
export async function navigateForward(wordInput, searchFn, updateButtonsFn) {
    if (getHistoryIndex() < getHistoryLength() - 1) {
        setHistoryIndex(getHistoryIndex() + 1);
        setIsNavigating(true);
        const word = getHistoryWord(getHistoryIndex());
        console.log('Navigating forward to:', word);
        wordInput.value = word;
        try {
            await searchFn(word, false);
        } finally {
            setIsNavigating(false);
            updateButtonsFn();
        }
    }
}

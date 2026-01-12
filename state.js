// State management module for Snatch game
// Centralizes all mutable application state with getters/setters

// URLs
export const DICTIONARY_URL = 'https://raw.githubusercontent.com/redbo/scrabble/master/dictionary.txt';
export const ETYMOLOGY_URL = 'etymology.json';

// Dictionary state
let dictionary = new Set();
let wordList = [];
let etymology = {};
let isLoaded = false;

// Navigation state
let wordHistory = [];
let historyIndex = -1;
let isNavigating = false;

// Dictionary state accessors
export function getDictionary() {
    return dictionary;
}

export function setDictionary(dict) {
    dictionary = dict;
    wordList = Array.from(dict);
}

export function getWordList() {
    return wordList;
}

export function getEtymology() {
    return etymology;
}

export function setEtymology(etym) {
    etymology = etym;
}

export function getIsLoaded() {
    return isLoaded;
}

export function setIsLoaded(loaded) {
    isLoaded = loaded;
}

// Navigation state accessors
export function getWordHistory() {
    return wordHistory;
}

export function getHistoryIndex() {
    return historyIndex;
}

export function setHistoryIndex(index) {
    historyIndex = index;
}

export function getIsNavigating() {
    return isNavigating;
}

export function setIsNavigating(navigating) {
    isNavigating = navigating;
}

// Navigation helpers
export function pushToHistory(word) {
    wordHistory.push(word);
    historyIndex = wordHistory.length - 1;
}

export function truncateHistoryAt(index) {
    wordHistory = wordHistory.slice(0, index + 1);
}

export function getHistoryWord(index) {
    return wordHistory[index];
}

export function getHistoryLength() {
    return wordHistory.length;
}

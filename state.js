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

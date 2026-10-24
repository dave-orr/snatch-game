// Word frequency display module for Snatch game
// Turns a word's Zipf frequency into one of six labels and a "1 in N" figure.
// How the data was built, and why some words have no figure, is in FREQUENCY.md.

import { getFrequency } from './state.js';

// One label per factor of ten, commonest first. A word below the last
// threshold, or with no figure at all, is Obscure.
const LABELS = [
    { min: 5, name: 'Everyday' },
    { min: 4, name: 'Common' },
    { min: 3, name: 'Uncommon' },
    { min: 2, name: 'Rare' },
    { min: 1, name: 'Very rare' },
];
const OBSCURE = 'Obscure';

// The two rarest labels are shown in grey, so the eye skips words a player
// would struggle to defend.
const RARE_LABELS = new Set(['Very rare', OBSCURE]);

// Frequency is optional, like etymology. Without the data, show nothing
// rather than calling every word Obscure.
function hasFrequency() {
    return getFrequency() !== null;
}

// The word's Zipf value, or null when the data gives it no figure.
function getZipf(word) {
    const zipf = getFrequency()[word];
    return typeof zipf === 'number' ? zipf : null;
}

export function getFrequencyLabel(word) {
    const zipf = getZipf(word);
    if (zipf === null) {
        return OBSCURE;
    }
    const label = LABELS.find(l => zipf >= l.min);
    return label ? label.name : OBSCURE;
}

export function isRareWord(word) {
    return hasFrequency() && RARE_LABELS.has(getFrequencyLabel(word));
}

// Zipf is log10 of occurrences per billion words, so one word in
// 10^(9 - zipf). Rounded to two significant figures, and in words from a
// million up: 1 in 300,000, 1 in 1.9 million, 1 in 1.7 billion.
function formatOneIn(zipf) {
    const n = Number(Math.pow(10, 9 - zipf).toPrecision(2));
    if (n >= 1e9) {
        return `1 in ${Number((n / 1e9).toPrecision(2))} billion`;
    }
    if (n >= 1e6) {
        return `1 in ${Number((n / 1e6).toPrecision(2))} million`;
    }
    return `1 in ${n.toLocaleString('en-US')}`;
}

function formatLabel(word) {
    const label = getFrequencyLabel(word);
    const rareClass = RARE_LABELS.has(label) ? ' rare' : '';
    return `<span class="frequency-label${rareClass}">${label}</span>`;
}

function formatFigure(word, suffix) {
    const zipf = getZipf(word);
    if (zipf === null) {
        return '';
    }
    return `<span class="frequency-sep">·</span><span class="frequency-figure">${suffix(formatOneIn(zipf))}</span>`;
}

// Check result: "Frequency: Uncommon · about 1 in 300,000 words"
export function formatFrequency(word) {
    if (!hasFrequency()) {
        return '';
    }
    return `<div class="frequency">Frequency: ${formatLabel(word)}${formatFigure(word, s => `about ${s} words`)}</div>`;
}

// Steals header: "Uncommon · 1 in 300,000"
export function formatFrequencyHeader(word) {
    if (!hasFrequency()) {
        return '';
    }
    return `<div class="frequency">${formatLabel(word)}${formatFigure(word, s => s)}</div>`;
}

// Steal rows and the compare card: the label alone
export function formatFrequencySimple(word) {
    if (!hasFrequency()) {
        return '';
    }
    return formatLabel(word);
}

// Etymology display module for Snatch game
// Functions for formatting and comparing word etymologies

import { getEtymology } from './state.js';

// Format a single etymology entry as HTML
function formatEtymologyEntry(entry) {
    const [lang, root] = entry.split(':');
    if (!root || root === '-') {
        return `<span class="etymology-lang">${lang}</span>`;
    }
    return `<span class="etymology-lang">${lang}</span>:<span class="etymology-root">${root}</span>`;
}

// Format etymology for display (with "Etymology:" prefix)
export function formatEtymology(word) {
    const etymology = getEtymology();
    const etymList = etymology[word];
    if (!etymList || !Array.isArray(etymList) || etymList.length === 0) {
        return '<div class="etymology">Etymology: <span class="etymology-unknown">unknown</span></div>';
    }

    const formatted = etymList.map(formatEtymologyEntry).join(', ');
    return `<div class="etymology">Etymology: ${formatted}</div>`;
}

// Format etymology for compare display (simpler version without the "Etymology:" prefix)
export function formatEtymologySimple(word) {
    const etymology = getEtymology();
    const etymList = etymology[word];
    if (!etymList || !Array.isArray(etymList) || etymList.length === 0) {
        return '<span class="etymology-unknown">unknown</span>';
    }

    return etymList.map(formatEtymologyEntry).join(', ');
}

// Get shared etymologies between two words
export function getSharedEtymologies(word1, word2) {
    const etymology = getEtymology();
    const etymList1 = etymology[word1];
    const etymList2 = etymology[word2];
    const shared = [];

    if (etymList1 && etymList2 && Array.isArray(etymList1) && Array.isArray(etymList2)) {
        for (const etym1 of etymList1) {
            for (const etym2 of etymList2) {
                // Check if they match
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

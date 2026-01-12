# app.js Refactoring Tasks

Bite-sized chunks for parallel work. Each task should be completable in 1-2 Claude Code prompts.

---

## Category 1: DRY Violations

### 1.1 Extract letter counting utilities
- Create a single `getLetterCounts()` function used everywhere
- Remove duplicate counting logic from `isStrictSubset` (lines 184-193)
- Remove inline counting in `findMergeSteals` (lines 399-414)
- Remove inline counting in `findMergeStealsTo` (lines 485-518)

### 1.2 Unify findStealsFrom and findStealsTo
- Extract shared algorithm into helper function
- Both functions differ only in: length check direction, result key names, sort order
- Reduce ~54 lines to ~30

### 1.3 Extract common sorting comparator
- Lines 343-351, 373-381, 450-460, 539-550 all use same pattern
- Create `createStealSorter(lengthDirection, resultKey)` factory function

---

## Category 2: Code Organization

### 2.1 Extract state management module [DONE]
- ~~Move global state (lines 4-7, 20-22) into a state object~~
- ~~Create getter/setter functions for dictionary, wordList, etymology, isLoaded~~
- ~~Create navigation state helpers (wordHistory, historyIndex, isNavigating)~~
- Created state.js with all state and accessors
- Updated app.js to import from state module
- Updated index.html to use type=module

### 2.2 Extract word validation module [DONE]
- ~~Move `checkWord()`, `getLetterCounts()`, `isStrictSubset()`, `getAddedLetters()`~~
- ~~Move inflection checking: `INFLECTION_SUFFIXES`, `INFLECTION_PREFIXES`, `isInflection()`~~
- ~~Self-contained module with no DOM dependencies~~
- Created words.js with word validation functions
- Also moved `combineLetterCounts()`, `isCombinedStrictSubset()`, `shareEtymology()`, `isCompoundContaining()`
- Updated app.js to import from words module

### 2.3 Extract steal-finding module
- Move `findStealsFrom()`, `findStealsTo()`, `findMergeSteals()`, `findMergeStealsTo()`
- Depends on word validation module
- No DOM dependencies

### 2.4 Extract etymology module
- Move `getEtymology()`, `shareEtymology()`
- Self-contained lookup functions

### 2.5 Extract UI rendering module
- Move `renderCollapsibleGroup()`, `displaySteals()`, result rendering functions
- Move `toggleGroup()` and related UI helpers
- All DOM manipulation lives here

### 2.6 Extract navigation module
- Move `addToHistory()`, `navigateBack()`, `navigateForward()`, `updateNavButtons()`
- History state and navigation logic

---

## Category 3: Bug Fixes

### 3.1 Fix navigation race condition
- Lines 93-117: `isNavigating` set false before async operation completes
- Use async/await properly or callback pattern
- Ensure flag stays true until displaySteals completes

### 3.2 Add bounds checking to navigation
- Lines 99, 113: Add defensive checks for empty wordHistory
- Ensure historyIndex is always valid before access

### 3.3 Add proper error handling to displaySteals
- Wrap steal-finding calls in try-catch
- Show user-friendly error messages
- Don't leave UI in broken state on error

---

## Category 4: Performance

### 4.1 Cache letter counts
- Dictionary doesn't change after load
- Pre-compute letter counts for all words once
- Store in Map alongside wordList

### 4.2 Add early termination to merge steals
- Lines 418-446, 505-534: Add result limit during search
- Don't compute all results then slice - stop early

---

## Category 5: Code Quality

### 5.1 Replace magic numbers with named constants
- Line 119: `MIN_WORD_LENGTH = 4` (already done)
- Line 572: Extract ID generation to named function
- Line 761: `UI_YIELD_MS = 10` or similar
- Lines 393, 477: `MIN_MERGE_LENGTH = MIN_WORD_LENGTH * 2 + 1`

### 5.2 Fix inconsistent null handling
- Decide on null vs undefined convention
- Document return value semantics
- Add explicit checks where needed

### 5.3 Replace innerHTML with safer DOM APIs
- Lines 160, 163, 166: Use textContent or createElement
- Lines 576-587: Build DOM nodes instead of HTML strings
- Lines 637-675: Same treatment for result rendering

---

## Suggested Work Order

**Phase 1 - Foundation (do first, blocks others):**
- 2.1 Extract state management module
- 2.2 Extract word validation module

**Phase 2 - Can be parallelized:**
- 1.1 Extract letter counting utilities
- 1.2 Unify findStealsFrom/findStealsTo
- 1.3 Extract common sorting comparator
- 2.3 Extract steal-finding module
- 2.4 Extract etymology module
- 3.1 Fix navigation race condition
- 3.2 Add bounds checking to navigation
- 5.1 Replace magic numbers

**Phase 3 - After modules exist:**
- 2.5 Extract UI rendering module
- 2.6 Extract navigation module
- 3.3 Add proper error handling
- 5.2 Fix inconsistent null handling
- 5.3 Replace innerHTML with safer DOM APIs

**Phase 4 - Optimization (last):**
- 4.1 Cache letter counts
- 4.2 Add early termination to merge steals

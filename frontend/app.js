let currentQuery = '';
let selectedFrames = new Set();
let selectMode = false;

// Escape strings for use in onclick attributes
function escapeAttr(str) {
    return str ? str.replace(/\\/g, '\\\\').replace(/'/g, "\\'") : '';
}
let activeFilters = {
    season: new Set()
};
let episodeNames = {};
let hasSearched = false;
const MAX_RESULTS = 100;
const MIN_SCORE_THRESHOLD = 0.05;
const MAX_HISTORY = 10;
let searchMode = 'visual'; // 'visual' or 'quote'
let searchHistory = [];

function setSearchMode(mode) {
    searchMode = mode;
    document.getElementById('modeVisual').classList.toggle('active', mode === 'visual');
    document.getElementById('modeQuote').classList.toggle('active', mode === 'quote');

    // Update placeholder based on mode
    const input = document.getElementById('query');
    if (mode === 'quote') {
        input.placeholder = 'Search by quote or dialogue...';
    } else {
        input.placeholder = 'Search by scene or action...';
    }
}

function setSearchedState(searched) {
    hasSearched = searched;
    if (searched) {
        document.body.classList.add('searched');
    } else {
        document.body.classList.remove('searched');
    }
}

async function loadEpisodeNames() {
    try {
        const response = await fetch('/static/episode_names.json');
        episodeNames = await response.json();
    } catch (err) {
        console.error('Failed to load episode names:', err);
    }
}

function getEpisodeTitle(episodeStr) {
    // Extract season/episode code from "The Simpsons - s01e02" format
    const match = episodeStr.match(/s(\d+)e(\d+)/i);
    if (match) {
        const key = `s${match[1].padStart(2, '0')}e${match[2].padStart(2, '0')}`;
        return episodeNames[key] || null;
    }
    return null;
}

let indexedSeasons = [];

async function loadStats() {
    try {
        const response = await fetch('/stats');
        const stats = await response.json();
        document.getElementById('stats').innerHTML =
            `${stats.total_frames.toLocaleString()} frames from ${stats.episodes} episode${stats.episodes > 1 ? 's' : ''}`;
        document.getElementById('subtitle').innerHTML =
            `Search ${stats.total_frames.toLocaleString()} frames by scene or action`;

        // Load indexed seasons
        if (stats.seasons) {
            indexedSeasons = stats.seasons;
            renderSeasonFilters();
        }
    } catch (err) {
        document.getElementById('stats').innerHTML = '';
    }
}

function renderSeasonFilters() {
    const container = document.getElementById('seasonFilters');
    if (!indexedSeasons.length) {
        container.innerHTML = '';
        return;
    }

    container.innerHTML = indexedSeasons.map(s => {
        const isActive = activeFilters.season.has(String(s));
        return `<button class="filter-pill ${isActive ? 'active' : ''}"
            data-season="${s}"
            onclick="toggleFilter('season', '${s}')">S${s}</button>`;
    }).join('');
}


function toggleFilter(type, value) {
    if (activeFilters[type].has(value)) {
        activeFilters[type].delete(value);
    } else {
        activeFilters[type].add(value);
    }
    updateFilterUI();
    if (currentQuery) {
        search();
    }
}

function updateFilterUI() {
    // Re-render season filters to update active states
    if (indexedSeasons.length > 0) {
        renderSeasonFilters();
    }

    // Update active filters display
    const container = document.getElementById('activeFiltersContainer');
    const allFiltersArr = [
        ...Array.from(activeFilters.season).map(s => ({ type: 'season', value: s, label: `Season ${s}` }))
    ];

    if (allFiltersArr.length > 0) {
        container.innerHTML = `
            <div class="active-filters">
                ${allFiltersArr.map(f => `
                    <div class="active-filter-tag">
                        ${f.label}
                        <button onclick="toggleFilter('${f.type}', '${f.value}')" title="Remove filter">×</button>
                    </div>
                `).join('')}
            </div>
        `;
    } else {
        container.innerHTML = '';
    }
}

function buildSearchQuery() {
    return document.getElementById('query').value.trim();
}

let currentResultsList = [];
let currentModalIndex = -1;

async function search() {
    const query = buildSearchQuery();
    if (!query) return;

    currentQuery = document.getElementById('query').value.trim();
    const resultsDiv = document.getElementById('results');
    const searchBtn = document.getElementById('searchBtn');

    // Save to history and update URL
    saveToHistory(currentQuery);
    updateURL(currentQuery);
    hideHistoryDropdown();

    resultsDiv.innerHTML = `<div class="loading">bort searching</div>`;
    searchBtn.disabled = true;

    try {
        let url = `/search?q=${encodeURIComponent(query)}&limit=${MAX_RESULTS}`;

        // Add search mode
        if (searchMode === 'quote') {
            url += '&mode=quote';
        }

        // Add season filter
        if (activeFilters.season.size > 0) {
            const seasons = Array.from(activeFilters.season).map(s => `s${s.padStart(2, '0')}`);
            url += `&season=${seasons.join(',')}`;
        }

        const response = await fetch(url);

        if (!response.ok) {
            throw new Error(`Search failed: ${response.statusText}`);
        }

        let results = await response.json();

        // Filter by score threshold - stop showing results below threshold
        results = results.filter(r => r.score >= MIN_SCORE_THRESHOLD);

        // Switch to searched state
        setSearchedState(true);

        if (results.length === 0) {
            showEmptyState(resultsDiv);
            return;
        }

        // Store for navigation
        currentResultsList = results;

        resultsDiv.innerHTML = results.map((r, index) => {
            const episodeTitle = getEpisodeTitle(r.episode);
            const episodeCode = r.episode.match(/s\d+e\d+/i)?.[0]?.toUpperCase() || r.episode;
            const thumbUrl = r.thumb_url || r.image_url;  // Fallback to full-res if no thumbnail
            return `
                <div class="result${selectedFrames.has(r.path) ? ' selected' : ''}" data-path="${r.path}" onclick="handleFrameClick('${r.image_url}', '${escapeAttr(r.episode)}', ${r.timestamp}, '${escapeAttr(r.path)}', '${r.frame}', ${index}, event)">
                    <input type="checkbox" class="frame-checkbox" onclick="event.stopPropagation(); toggleFrameSelection('${r.path}')" data-path="${r.path}">
                    <span class="delete-btn" role="button" onclick="event.stopPropagation(); deleteFrame('${escapeAttr(r.path)}')" title="Delete frame">×</span>
                    <img src="${thumbUrl}" alt="${r.episode}" loading="lazy">
                    <div class="result-info">
                        <div class="result-meta">
                            <span class="episode">${episodeCode}${episodeTitle ? ` - ${episodeTitle}` : ''}</span>
                            <span class="time">${formatTime(r.timestamp)}</span>
                        </div>
                        <div class="result-buttons">
                            <button class="action-btn" onclick="event.stopPropagation(); copyImageUrl('${r.image_url}', this)" title="Copy image URL">Copy</button>
                            <button class="action-btn" onclick="event.stopPropagation(); downloadImage('${r.image_url}', '${r.episode}_${r.frame}')" title="Download image">Download</button>
                            <button class="action-btn" onclick="event.stopPropagation(); findSimilar('${escapeAttr(r.path)}')" title="Find similar frames">Similar</button>
                        </div>
                    </div>
                </div>
            `;
        }).join('');

    } catch (err) {
        resultsDiv.innerHTML = `
            <div class="error">
                <h3>❌ Error</h3>
                <p>${err.message}</p>
            </div>
        `;
    } finally {
        searchBtn.disabled = false;
    }
}

async function randomFrame() {
    const resultsDiv = document.getElementById('results');
    resultsDiv.innerHTML = `<div class="loading">bort searching</div>`;

    try {
        const response = await fetch('/random');
        if (!response.ok) {
            throw new Error(`Failed to get random frame: ${response.statusText}`);
        }

        const result = await response.json();
        const episodeTitle = getEpisodeTitle(result.episode);
        const episodeCode = result.episode.match(/s\d+e\d+/i)?.[0]?.toUpperCase() || result.episode;
        const thumbUrl = result.thumb_url || result.image_url;  // Fallback to full-res if no thumbnail

        // Switch to searched state
        setSearchedState(true);

        resultsDiv.innerHTML = `
            <div class="result" data-path="${result.path}" onclick="handleFrameClick('${result.image_url}', '${escapeAttr(result.episode)}', ${result.timestamp}, '${escapeAttr(result.path)}', '${result.frame}', -1, event)">
                <input type="checkbox" class="frame-checkbox" onclick="event.stopPropagation(); toggleFrameSelection('${result.path}')" data-path="${result.path}">
                <button class="delete-btn" onclick="event.stopPropagation(); deleteFrame('${result.path}')" title="Delete frame">×</button>
                <img src="${thumbUrl}" alt="${result.episode}" loading="lazy">
                <div class="result-info">
                    <div class="result-meta">
                        <span class="episode">${episodeCode}${episodeTitle ? ` - ${episodeTitle}` : ''}</span>
                        <span class="time">${formatTime(result.timestamp)}</span>
                    </div>
                    <div class="result-buttons">
                        <button class="action-btn" onclick="event.stopPropagation(); copyImageUrl('${result.image_url}', this)" title="Copy image URL">Copy</button>
                        <button class="action-btn" onclick="event.stopPropagation(); downloadImage('${result.image_url}', '${result.episode}_${result.frame}')" title="Download image">Download</button>
                        <button class="action-btn" onclick="event.stopPropagation(); findSimilar('${escapeAttr(result.path)}')" title="Find similar frames">Similar</button>
                    </div>
                </div>
            </div>
        `;
    } catch (err) {
        resultsDiv.innerHTML = `
            <div class="error">
                <h3>❌ Error</h3>
                <p>${err.message}</p>
            </div>
        `;
    }
}

let currentSimilarSource = null;  // Track source frame for similar search

async function findSimilar(path) {
    const resultsDiv = document.getElementById('results');
    resultsDiv.innerHTML = `<div class="loading">bort searching</div>`;

    // Store source path for back navigation
    currentSimilarSource = path;

    try {
        console.log('Finding similar for path:', path);
        const response = await fetch(`/similar?path=${encodeURIComponent(path)}&limit=24`);

        if (!response.ok) {
            const errorData = await response.json().catch(() => ({}));
            throw new Error(errorData.detail || `Search failed: ${response.statusText}`);
        }

        const results = await response.json();

        // Switch to searched state
        setSearchedState(true);

        if (results.length === 0) {
            resultsDiv.innerHTML = `
                <div class="empty-state">
                    <div class="empty-state-icon">🤷</div>
                    <h2>No similar frames found</h2>
                </div>
            `;
            return;
        }

        // Store for navigation
        currentResultsList = results;

        // Extract episode info from source path for display
        const sourceMatch = path.match(/The Simpsons - (s\d+e\d+)/i);
        const sourceEp = sourceMatch ? sourceMatch[1].toUpperCase() : '';
        const sourceFrame = path.match(/frame_(\d+)/)?.[1] || '';

        resultsDiv.innerHTML = `
            <div class="similar-header">
                <button class="back-btn" onclick="goBack()">← Back</button>
                <span>Similar to ${sourceEp}${sourceFrame ? ` @ frame ${parseInt(sourceFrame)}` : ''}</span>
            </div>
        ` + results.map((r, index) => {
            const episodeTitle = getEpisodeTitle(r.episode);
            const episodeCode = r.episode.match(/s\d+e\d+/i)?.[0]?.toUpperCase() || r.episode;
            const thumbUrl = r.thumb_url || r.image_url;  // Fallback to full-res if no thumbnail
            return `
                <div class="result${selectedFrames.has(r.path) ? ' selected' : ''}" data-path="${r.path}" onclick="handleFrameClick('${r.image_url}', '${escapeAttr(r.episode)}', ${r.timestamp}, '${escapeAttr(r.path)}', '${r.frame}', ${index}, event)">
                    <input type="checkbox" class="frame-checkbox" onclick="event.stopPropagation(); toggleFrameSelection('${r.path}')" data-path="${r.path}">
                    <span class="delete-btn" role="button" onclick="event.stopPropagation(); deleteFrame('${escapeAttr(r.path)}')" title="Delete frame">×</span>
                    <img src="${thumbUrl}" alt="${r.episode}" loading="lazy">
                    <div class="result-info">
                        <div class="result-meta">
                            <span class="episode">${episodeCode}${episodeTitle ? ` - ${episodeTitle}` : ''}</span>
                            <span class="time">${formatTime(r.timestamp)}</span>
                        </div>
                        <div class="result-buttons">
                            <button class="action-btn" onclick="event.stopPropagation(); copyImageUrl('${r.image_url}', this)" title="Copy image URL">Copy</button>
                            <button class="action-btn" onclick="event.stopPropagation(); downloadImage('${r.image_url}', '${r.episode}_${r.frame}')" title="Download image">Download</button>
                            <button class="action-btn" onclick="event.stopPropagation(); findSimilar('${escapeAttr(r.path)}')" title="Find similar frames">Similar</button>
                        </div>
                    </div>
                </div>
            `;
        }).join('');

    } catch (err) {
        resultsDiv.innerHTML = `
            <div class="error">
                <h3>❌ Error</h3>
                <p>${err.message}</p>
            </div>
        `;
    }
}

function clearResults() {
    document.getElementById('results').innerHTML = '';
}

async function showEmptyState(container) {
    const messages = [
        { title: "D'oh! No results found", sub: "Try a different search term" },
        { title: "Nothing here", sub: "Try searching for something else" },
        { title: "Ay caramba! Zero results", sub: "Maybe try different words?" },
        { title: "No frames found", sub: "Try a broader search" }
    ];
    const msg = messages[Math.floor(Math.random() * messages.length)];

    // Try to get a random reaction frame
    const reactionSearches = ['sad', 'confused', 'surprised', 'disappointed', 'shocked', 'crying'];
    const randomSearch = reactionSearches[Math.floor(Math.random() * reactionSearches.length)];

    let reactionImg = '';
    try {
        const response = await fetch(`/search?q=${randomSearch}&limit=10`);
        if (response.ok) {
            const results = await response.json();
            if (results.length > 0) {
                const randomResult = results[Math.floor(Math.random() * results.length)];
                reactionImg = `<img src="${randomResult.thumb_url}" alt="reaction" class="reaction-img">`;
            }
        }
    } catch (e) {
        // Fallback to emoji if fetch fails
    }

    container.innerHTML = `
        <div class="empty-state">
            ${reactionImg || '<div class="empty-state-icon">🤷</div>'}
            <h2>${msg.title}</h2>
            <p>${msg.sub}</p>
        </div>
    `;
}

function goBack() {
    // If there's a current query, re-run the search
    if (currentQuery) {
        search();
    } else {
        // Otherwise reset to landing
        resetToLanding();
    }
    currentSimilarSource = null;
}

function resetToLanding() {
    document.getElementById('results').innerHTML = '';
    document.getElementById('query').value = '';
    currentQuery = '';
    setSearchedState(false);
    // Scroll to top
    window.scrollTo({ top: 0, behavior: 'smooth' });
}

function searchExample(query) {
    document.getElementById('query').value = query;
    search();
}

function formatTime(seconds) {
    const m = Math.floor(seconds / 60);
    const s = seconds % 60;
    return `${m}:${s.toString().padStart(2, '0')}`;
}

async function copyImageUrl(imageUrl, button) {
    const fullUrl = window.location.origin + imageUrl;
    try {
        await navigator.clipboard.writeText(fullUrl);
        const originalText = button.textContent;
        button.textContent = 'Copied!';
        button.classList.add('copied');
        setTimeout(() => {
            button.textContent = originalText;
            button.classList.remove('copied');
        }, 1500);
    } catch (err) {
        console.error('Failed to copy:', err);
        alert('Failed to copy URL');
    }
}

async function downloadImage(imageUrl, filename) {
    try {
        const response = await fetch(imageUrl);
        const blob = await response.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = filename + '.jpg';
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        window.URL.revokeObjectURL(url);
    } catch (err) {
        console.error('Failed to download:', err);
        // Fallback: open in new tab
        window.open(imageUrl, '_blank');
    }
}

function openModal(imageUrl, episode, timestamp, path, frame, index = -1) {
    currentModalIndex = index;
    document.getElementById('modalImage').src = imageUrl;

    // Preload adjacent images for instant navigation
    if (index >= 0 && currentResultsList.length > 0) {
        if (index > 0) {
            new Image().src = currentResultsList[index - 1].image_url;
        }
        if (index < currentResultsList.length - 1) {
            new Image().src = currentResultsList[index + 1].image_url;
        }
    }

    // Set episode and time info
    const episodeCode = episode ? episode.match(/s\d+e\d+/i)?.[0]?.toUpperCase() || episode : '';
    document.getElementById('modalEpisode').textContent = episodeCode;
    document.getElementById('modalTime').textContent = timestamp ? formatTime(timestamp) : '';
    document.getElementById('modalPath').textContent = path || '';

    // Set buttons with prev/next navigation
    const filename = episode && frame ? `${episode}_${frame}` : 'frame';
    const hasPrev = index > 0;
    const hasNext = index >= 0 && index < currentResultsList.length - 1;

    const escapedPath = path ? path.replace(/'/g, "\\'") : '';
    document.getElementById('modalButtons').innerHTML = `
        ${hasPrev ? `<button class="modal-btn modal-nav" onclick="navigateModal(-1)">← Prev</button>` : ''}
        <button class="modal-btn" onclick="copyImageUrl('${imageUrl}', this)">Copy URL</button>
        <button class="modal-btn" onclick="downloadImage('${imageUrl}', '${filename}')">Download</button>
        ${path ? `<button class="modal-btn" onclick="closeModal(); findSimilar('${escapedPath}')">Similar</button>` : ''}
        ${hasNext ? `<button class="modal-btn modal-nav" onclick="navigateModal(1)">Next →</button>` : ''}
    `;

    document.getElementById('modal').classList.add('active');
}

function navigateModal(direction) {
    const newIndex = currentModalIndex + direction;
    if (newIndex >= 0 && newIndex < currentResultsList.length) {
        const r = currentResultsList[newIndex];
        openModal(r.image_url, r.episode, r.timestamp, r.path, r.frame, newIndex);
    }
}

function closeModal() {
    document.getElementById('modal').classList.remove('active');
}

document.addEventListener('keydown', (e) => {
    const modalActive = document.getElementById('modal').classList.contains('active');

    if (e.key === 'Escape') {
        closeModal();
        hideHistoryDropdown();
    }

    // Arrow keys for modal navigation
    if (modalActive && currentModalIndex >= 0) {
        if (e.key === 'ArrowLeft') {
            e.preventDefault();
            navigateModal(-1);
        } else if (e.key === 'ArrowRight') {
            e.preventDefault();
            navigateModal(1);
        }
    }

    // Press "/" to focus search (like GitHub, YouTube, etc.)
    if (e.key === '/' && document.activeElement.tagName !== 'INPUT') {
        e.preventDefault();
        document.getElementById('query').focus();
    }
});

function toggleSelectMode() {
    selectMode = !selectMode;
    document.body.classList.toggle('select-mode', selectMode);
    if (!selectMode) {
        clearSelection();
    }
    updateBulkActions();
}

function toggleFrameSelection(path, event) {
    if (event) event.stopPropagation();
    if (selectedFrames.has(path)) {
        selectedFrames.delete(path);
    } else {
        selectedFrames.add(path);
    }
    updateBulkActions();
}

function handleFrameClick(imageUrl, episode, timestamp, path, frame, index, event) {
    if (selectMode) {
        toggleFrameSelection(path, event);
    } else {
        openModal(imageUrl, episode, timestamp, path, frame, index);
    }
}

function updateBulkActions() {
    const bulkActions = document.getElementById('bulkActions');
    const bulkCount = document.getElementById('bulkCount');
    const selectToggle = document.getElementById('selectToggle');

    if (selectMode || selectedFrames.size > 0) {
        bulkActions.classList.add('visible');
        bulkCount.textContent = selectedFrames.size > 0 ? `${selectedFrames.size} selected` : 'Select frames';
        if (selectToggle) selectToggle.textContent = selectMode ? 'Done' : 'Select';
    } else {
        bulkActions.classList.remove('visible');
    }

    // Update checkboxes and card selected state
    document.querySelectorAll('.frame-checkbox').forEach(checkbox => {
        const path = checkbox.dataset.path;
        checkbox.checked = selectedFrames.has(path);
    });
    document.querySelectorAll('.result').forEach(card => {
        const path = card.dataset.path;
        card.classList.toggle('selected', selectedFrames.has(path));
    });
}

function clearSelection() {
    selectedFrames.clear();
    updateBulkActions();
}

async function bulkDelete() {
    if (selectedFrames.size === 0) return;

    if (!confirm(`Delete ${selectedFrames.size} selected frames from the index?`)) {
        return;
    }

    const pathsToDelete = Array.from(selectedFrames);
    let successCount = 0;

    for (const path of pathsToDelete) {
        try {
            const response = await fetch(`/frame/delete?path=${encodeURIComponent(path)}`, {
                method: 'POST'
            });

            if (response.ok) {
                // Remove the frame card from DOM
                const frameCard = document.querySelector(`.result[data-path="${path}"]`);
                if (frameCard) {
                    frameCard.remove();
                }
                selectedFrames.delete(path);
                successCount++;
            }
        } catch (err) {
            console.error(`Failed to delete ${path}:`, err);
        }
    }

    updateBulkActions();
    await loadStats();

    if (successCount > 0) {
        alert(`Successfully deleted ${successCount} frame(s)`);
    }
}

async function deleteFrame(path) {
    console.log('[DELETE] Path to delete:', path);

    if (!confirm('Are you sure you want to delete this frame from the index?')) {
        return;
    }

    try {
        const url = `/frame/delete?path=${encodeURIComponent(path)}`;
        console.log('[DELETE] Request URL:', url);

        const response = await fetch(url, {
            method: 'POST'
        });

        console.log('[DELETE] Response status:', response.status);

        if (!response.ok) {
            const errorText = await response.text();
            console.error('[DELETE] Error response:', errorText);
            throw new Error(`Delete failed: ${response.statusText}`);
        }

        const result = await response.json();

        // Remove the frame card from DOM instead of re-running search
        const frameCard = document.querySelector(`.result[data-path="${path}"]`);
        if (frameCard) {
            frameCard.remove();
        }

        // Remove from selection if it was selected
        if (selectedFrames.has(path)) {
            selectedFrames.delete(path);
            updateBulkActions();
        }

        // Update stats
        await loadStats();
    } catch (err) {
        alert(`Failed to delete frame: ${err.message}`);
    }
}

// Initialize on page load
loadStats();
loadEpisodeNames();
updateFilterUI();
loadFromURL();
loadSearchHistory();

// Handle browser back/forward
window.addEventListener('popstate', loadFromURL);

function loadFromURL() {
    const params = new URLSearchParams(window.location.search);
    const q = params.get('q');
    if (q) {
        document.getElementById('query').value = q;
        search();
    }
}

function updateURL(query) {
    const url = new URL(window.location);
    if (query) {
        url.searchParams.set('q', query);
    } else {
        url.searchParams.delete('q');
    }
    window.history.pushState({}, '', url);
}

// Search history
function loadSearchHistory() {
    try {
        searchHistory = JSON.parse(localStorage.getItem('searchHistory') || '[]');
    } catch (e) {
        searchHistory = [];
    }
    renderSearchHistory();
}

function saveToHistory(query) {
    if (!query.trim()) return;
    // Remove if exists, add to front
    searchHistory = searchHistory.filter(q => q !== query);
    searchHistory.unshift(query);
    searchHistory = searchHistory.slice(0, MAX_HISTORY);
    localStorage.setItem('searchHistory', JSON.stringify(searchHistory));
    renderSearchHistory();
}

function renderSearchHistory() {
    let dropdown = document.getElementById('searchHistoryDropdown');
    if (!dropdown) {
        dropdown = document.createElement('div');
        dropdown.id = 'searchHistoryDropdown';
        dropdown.className = 'search-history-dropdown';
        document.querySelector('.search-box').appendChild(dropdown);
    }

    if (searchHistory.length === 0) {
        dropdown.innerHTML = '';
        return;
    }

    dropdown.innerHTML = searchHistory.map(q =>
        `<div class="history-item" onclick="selectHistory('${q.replace(/'/g, "\\'")}')">${q}</div>`
    ).join('');
}

function selectHistory(query) {
    document.getElementById('query').value = query;
    hideHistoryDropdown();
    search();
}

function showHistoryDropdown() {
    const dropdown = document.getElementById('searchHistoryDropdown');
    if (dropdown && searchHistory.length > 0) {
        dropdown.classList.add('visible');
    }
}

function hideHistoryDropdown() {
    const dropdown = document.getElementById('searchHistoryDropdown');
    if (dropdown) {
        dropdown.classList.remove('visible');
    }
}

// Setup search input focus/blur for history dropdown
document.addEventListener('DOMContentLoaded', () => {
    const queryInput = document.getElementById('query');

    queryInput.addEventListener('focus', () => {
        showHistoryDropdown();
    });

    queryInput.addEventListener('blur', (e) => {
        // Delay hide to allow click on history item
        setTimeout(() => {
            hideHistoryDropdown();
        }, 150);
    });
});

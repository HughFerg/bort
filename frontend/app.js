let currentQuery = '';
let selectedFrames = new Set();
let activeFilters = {
    season: new Set(),
    character: new Set()
};
let allCharacters = [];
let charactersExpanded = false;
const INITIAL_CHARS_SHOWN = 8;
let episodeNames = {};
let hasSearched = false;
const MAX_RESULTS = 100;
const MIN_SCORE_THRESHOLD = 0.20;

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
            `Search ${stats.total_frames.toLocaleString()} frames by character, scene, or action`;

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

async function loadCharacters() {
    try {
        const response = await fetch('/characters');
        const data = await response.json();
        allCharacters = data.characters;
        renderCharacterFilters();
    } catch (err) {
        console.error('Failed to load characters:', err);
    }
}

function renderCharacterFilters() {
    const container = document.getElementById('characterFilters');
    if (!allCharacters.length) {
        container.innerHTML = '<span style="color: #999; font-size: 11px;">No characters found</span>';
        return;
    }

    const visibleChars = charactersExpanded ? allCharacters : allCharacters.slice(0, INITIAL_CHARS_SHOWN);
    const hiddenCount = allCharacters.length - INITIAL_CHARS_SHOWN;

    let html = visibleChars.map(c => {
        const isActive = activeFilters.character.has(c.name);
        return `<button class="filter-pill ${isActive ? 'active' : ''}"
            data-character="${c.name}"
            onclick="toggleFilter('character', '${c.name}')">
            ${c.name}<span class="character-count">(${c.count})</span>
        </button>`;
    }).join('');

    if (hiddenCount > 0 && !charactersExpanded) {
        html += `<button class="expand-btn" onclick="expandCharacters()">+${hiddenCount} more</button>`;
    } else if (charactersExpanded && allCharacters.length > INITIAL_CHARS_SHOWN) {
        html += `<button class="expand-btn" onclick="collapseCharacters()">Show less</button>`;
    }

    container.innerHTML = html;
}

function expandCharacters() {
    charactersExpanded = true;
    renderCharacterFilters();
}

function collapseCharacters() {
    charactersExpanded = false;
    renderCharacterFilters();
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

    // Re-render character filters to update active states
    if (allCharacters.length > 0) {
        renderCharacterFilters();
    }

    // Update active filters display
    const container = document.getElementById('activeFiltersContainer');
    const allFiltersArr = [
        ...Array.from(activeFilters.season).map(s => ({ type: 'season', value: s, label: `Season ${s}` })),
        ...Array.from(activeFilters.character).map(c => ({ type: 'character', value: c, label: c }))
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

function addCharacterFilter(character) {
    // Add character to filter pills if not already there
    const filterPills = document.getElementById('characterFilters');
    const existing = filterPills.querySelector(`[data-character="${character}"]`);
    if (!existing) {
        const pill = document.createElement('button');
        pill.className = 'filter-pill';
        pill.dataset.character = character;
        pill.textContent = character;
        pill.onclick = () => toggleFilter('character', character);
        filterPills.appendChild(pill);
    }
    // Activate the filter
    toggleFilter('character', character);
}

function buildSearchQuery() {
    const query = document.getElementById('query').value.trim();
    let fullQuery = query;

    // Add character filters to query
    if (activeFilters.character.size > 0) {
        const chars = Array.from(activeFilters.character).join(', ');
        fullQuery = fullQuery ? `${fullQuery} with ${chars}` : chars;
    }

    return fullQuery;
}

async function search() {
    const query = buildSearchQuery();
    if (!query) return;

    currentQuery = document.getElementById('query').value.trim();
    const resultsDiv = document.getElementById('results');
    const searchBtn = document.getElementById('searchBtn');

    resultsDiv.innerHTML = '<div class="loading">🔍 Searching...</div>';
    searchBtn.disabled = true;

    try {
        let url = `/search?q=${encodeURIComponent(query)}&limit=${MAX_RESULTS}`;

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
            resultsDiv.innerHTML = `
                <div class="empty-state">
                    <div class="empty-state-icon">🤷</div>
                    <h2>D'oh! No results found</h2>
                    <p>Try a different search term or adjust your filters</p>
                </div>
            `;
            return;
        }

        resultsDiv.innerHTML = results.map(r => {
            const characters = r.characters ? r.characters.split(', ').filter(c => c.trim()) : [];
            const episodeTitle = getEpisodeTitle(r.episode);
            const episodeCode = r.episode.match(/s\d+e\d+/i)?.[0]?.toUpperCase() || r.episode;
            return `
                <div class="result" data-path="${r.path}" onclick="openModal('${r.image_url}', '${r.episode}', ${r.timestamp}, '${r.path}', '${r.frame}')">
                    <input type="checkbox" class="frame-checkbox" onclick="event.stopPropagation(); toggleFrameSelection('${r.path}')" data-path="${r.path}">
                    <button class="delete-btn" onclick="event.stopPropagation(); deleteFrame('${r.path}')" title="Delete frame">×</button>
                    <img src="${r.image_url}" alt="${r.episode}" loading="lazy">
                    <div class="result-info">
                        <div class="result-meta">
                            <span class="episode">${episodeCode}</span>
                            <span class="time">${formatTime(r.timestamp)}</span>
                        </div>
                        ${episodeTitle ? `<div class="episode-title">${episodeTitle}</div>` : ''}
                        ${characters.length > 0 ? `
                            <div class="characters">
                                ${characters.map(c => `
                                    <span class="character-tag" onclick="event.stopPropagation(); addCharacterFilter('${c}')">${c}</span>
                                `).join('')}
                            </div>
                        ` : ''}
                        ${r.caption ? `<div class="caption">${r.caption}</div>` : ''}
                        <div class="result-buttons">
                            <button class="action-btn" onclick="event.stopPropagation(); copyImageUrl('${r.image_url}', this)" title="Copy image URL">Copy</button>
                            <button class="action-btn" onclick="event.stopPropagation(); downloadImage('${r.image_url}', '${r.episode}_${r.frame}')" title="Download image">Download</button>
                            <button class="action-btn" onclick="event.stopPropagation(); findSimilar('${r.path}')" title="Find similar frames">Similar</button>
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
    resultsDiv.innerHTML = '<div class="loading">🎲 Getting random frame...</div>';

    try {
        const response = await fetch('/random');
        if (!response.ok) {
            throw new Error(`Failed to get random frame: ${response.statusText}`);
        }

        const result = await response.json();
        const characters = result.characters ? result.characters.split(', ').filter(c => c.trim()) : [];
        const episodeTitle = getEpisodeTitle(result.episode);
        const episodeCode = result.episode.match(/s\d+e\d+/i)?.[0]?.toUpperCase() || result.episode;

        // Switch to searched state
        setSearchedState(true);

        resultsDiv.innerHTML = `
            <div class="result" data-path="${result.path}" onclick="openModal('${result.image_url}', '${result.episode}', ${result.timestamp}, '${result.path}', '${result.frame}')">
                <input type="checkbox" class="frame-checkbox" onclick="event.stopPropagation(); toggleFrameSelection('${result.path}')" data-path="${result.path}">
                <button class="delete-btn" onclick="event.stopPropagation(); deleteFrame('${result.path}')" title="Delete frame">×</button>
                <img src="${result.image_url}" alt="${result.episode}" loading="lazy">
                <div class="result-info">
                    <div class="result-meta">
                        <span class="episode">${episodeCode}</span>
                        <span class="time">${formatTime(result.timestamp)}</span>
                    </div>
                    ${episodeTitle ? `<div class="episode-title">${episodeTitle}</div>` : ''}
                    ${characters.length > 0 ? `
                        <div class="characters">
                            ${characters.map(c => `
                                <span class="character-tag" onclick="event.stopPropagation(); addCharacterFilter('${c}')">${c}</span>
                            `).join('')}
                        </div>
                    ` : ''}
                    ${result.caption ? `<div class="caption">${result.caption}</div>` : ''}
                    <div class="result-buttons">
                        <button class="action-btn" onclick="event.stopPropagation(); copyImageUrl('${result.image_url}', this)" title="Copy image URL">Copy</button>
                        <button class="action-btn" onclick="event.stopPropagation(); downloadImage('${result.image_url}', '${result.episode}_${result.frame}')" title="Download image">Download</button>
                        <button class="action-btn" onclick="event.stopPropagation(); findSimilar('${result.path}')" title="Find similar frames">Similar</button>
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

async function findSimilar(path) {
    const resultsDiv = document.getElementById('results');
    resultsDiv.innerHTML = '<div class="loading">🔍 Finding similar frames...</div>';

    try {
        const response = await fetch(`/similar?path=${encodeURIComponent(path)}&limit=24`);

        if (!response.ok) {
            throw new Error(`Search failed: ${response.statusText}`);
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

        resultsDiv.innerHTML = `
            <div class="similar-header">
                <span>Similar frames</span>
                <button class="clear-similar-btn" onclick="clearResults()">Clear</button>
            </div>
        ` + results.map(r => {
            const characters = r.characters ? r.characters.split(', ').filter(c => c.trim()) : [];
            const episodeTitle = getEpisodeTitle(r.episode);
            const episodeCode = r.episode.match(/s\d+e\d+/i)?.[0]?.toUpperCase() || r.episode;
            return `
                <div class="result" data-path="${r.path}" onclick="openModal('${r.image_url}', '${r.episode}', ${r.timestamp}, '${r.path}', '${r.frame}')">
                    <input type="checkbox" class="frame-checkbox" onclick="event.stopPropagation(); toggleFrameSelection('${r.path}')" data-path="${r.path}">
                    <button class="delete-btn" onclick="event.stopPropagation(); deleteFrame('${r.path}')" title="Delete frame">×</button>
                    <img src="${r.image_url}" alt="${r.episode}" loading="lazy">
                    <div class="result-info">
                        <div class="result-meta">
                            <span class="episode">${episodeCode}</span>
                            <span class="time">${formatTime(r.timestamp)}</span>
                        </div>
                        ${episodeTitle ? `<div class="episode-title">${episodeTitle}</div>` : ''}
                        ${characters.length > 0 ? `
                            <div class="characters">
                                ${characters.map(c => `
                                    <span class="character-tag" onclick="event.stopPropagation(); addCharacterFilter('${c}')">${c}</span>
                                `).join('')}
                            </div>
                        ` : ''}
                        ${r.caption ? `<div class="caption">${r.caption}</div>` : ''}
                        <div class="result-buttons">
                            <button class="action-btn" onclick="event.stopPropagation(); copyImageUrl('${r.image_url}', this)" title="Copy image URL">Copy</button>
                            <button class="action-btn" onclick="event.stopPropagation(); downloadImage('${r.image_url}', '${r.episode}_${r.frame}')" title="Download image">Download</button>
                            <button class="action-btn" onclick="event.stopPropagation(); findSimilar('${r.path}')" title="Find similar frames">Similar</button>
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

function openModal(imageUrl, episode, timestamp, path, frame) {
    document.getElementById('modalImage').src = imageUrl;

    // Set episode and time info
    const episodeCode = episode ? episode.match(/s\d+e\d+/i)?.[0]?.toUpperCase() || episode : '';
    document.getElementById('modalEpisode').textContent = episodeCode;
    document.getElementById('modalTime').textContent = timestamp ? formatTime(timestamp) : '';

    // Set buttons
    const filename = episode && frame ? `${episode}_${frame}` : 'frame';
    document.getElementById('modalButtons').innerHTML = `
        <button class="modal-btn" onclick="copyImageUrl('${imageUrl}', this)">Copy URL</button>
        <button class="modal-btn" onclick="downloadImage('${imageUrl}', '${filename}')">Download</button>
        ${path ? `<button class="modal-btn" onclick="closeModal(); findSimilar('${path}')">Find Similar</button>` : ''}
    `;

    document.getElementById('modal').classList.add('active');
}

function closeModal() {
    document.getElementById('modal').classList.remove('active');
}

document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
        closeModal();
    }
    // Press "/" to focus search (like GitHub, YouTube, etc.)
    if (e.key === '/' && document.activeElement.tagName !== 'INPUT') {
        e.preventDefault();
        document.getElementById('query').focus();
    }
});

function toggleFrameSelection(path) {
    if (selectedFrames.has(path)) {
        selectedFrames.delete(path);
    } else {
        selectedFrames.add(path);
    }
    updateBulkActions();
}

function updateBulkActions() {
    const bulkActions = document.getElementById('bulkActions');
    const bulkCount = document.getElementById('bulkCount');

    if (selectedFrames.size > 0) {
        bulkActions.classList.add('visible');
        bulkCount.textContent = `${selectedFrames.size} selected`;
    } else {
        bulkActions.classList.remove('visible');
    }

    // Update checkboxes to match selection state
    document.querySelectorAll('.frame-checkbox').forEach(checkbox => {
        const path = checkbox.dataset.path;
        checkbox.checked = selectedFrames.has(path);
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
loadCharacters();
loadEpisodeNames();
updateFilterUI();

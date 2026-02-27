// Admin-only functionality — loaded dynamically when delete_enabled is true (local dev only).
// Requires app.js to already be loaded (selectMode and selectedFrames are declared there).

// Inject select FAB and bulk actions bar into the page
(function injectAdminUI() {
    const fab = document.createElement('button');
    fab.className = 'select-fab';
    fab.id = 'selectFab';
    fab.textContent = 'Select';
    fab.onclick = toggleSelectMode;
    document.body.appendChild(fab);

    const bulkActions = document.createElement('div');
    bulkActions.className = 'bulk-actions';
    bulkActions.id = 'bulkActions';
    bulkActions.innerHTML = `
        <span id="bulkCount">0 selected</span>
        <button class="bulk-delete-btn" onclick="bulkDelete()">Delete Selected</button>
        <button class="bulk-clear-btn" onclick="clearSelection()">Clear</button>
        <button class="bulk-done-btn" onclick="toggleSelectMode()">Done</button>
    `;
    document.body.appendChild(bulkActions);
})();

// Delete button injected into the modal via hook in app.js
window.adminDeleteButton = function(escapedPath) {
    return `<button class="modal-btn modal-delete" onclick="deleteFrameFromModal('${escapedPath}')">Delete</button>`;
};

function toggleSelectMode() {
    selectMode = !selectMode;
    document.body.classList.toggle('select-mode', selectMode);
    showToast(selectMode ? 'SELECT MODE — tap frames to select' : 'SELECT MODE OFF');
    if (!selectMode) {
        clearSelection();
    }
    updateBulkActions();
}

function toggleFrameSelection(path) {
    if (selectedFrames.has(path)) {
        selectedFrames.delete(path);
    } else {
        selectedFrames.add(path);
    }
    updateBulkActions();
}

function updateBulkActions() {
    const bulkCount = document.getElementById('bulkCount');
    if (bulkCount) bulkCount.textContent = `${selectedFrames.size} selected`;
    document.querySelectorAll('.result').forEach(card => {
        card.classList.toggle('selected', selectedFrames.has(card.dataset.path));
    });
}

function clearSelection() {
    selectedFrames.clear();
    updateBulkActions();
}

async function bulkDelete() {
    if (selectedFrames.size === 0) {
        alert('No frames selected. Click on frames to select them first.');
        return;
    }
    if (!confirm(`Delete ${selectedFrames.size} selected frame(s) from the index?`)) return;

    const pathsToDelete = Array.from(selectedFrames);
    let successCount = 0;
    let errors = [];

    for (const path of pathsToDelete) {
        try {
            const response = await fetch(`/frame/delete?path=${encodeURIComponent(path)}`, { method: 'POST' });
            if (response.ok) {
                document.querySelectorAll(`.result[data-path="${CSS.escape(path)}"]`).forEach(c => c.remove());
                selectedFrames.delete(path);
                successCount++;
            } else {
                errors.push(`${path}: ${response.statusText}`);
            }
        } catch (err) {
            errors.push(`${path}: ${err.message}`);
        }
    }

    updateBulkActions();
    if (successCount > 0) {
        alert(`Deleted ${successCount} frame(s)` + (errors.length ? `\n\nFailed: ${errors.length}` : ''));
    } else if (errors.length > 0) {
        alert(`All deletes failed:\n${errors.join('\n')}`);
    }
}

async function deleteFrameFromModal(path) {
    try {
        const response = await fetch(`/frame/delete?path=${encodeURIComponent(path)}`, { method: 'POST' });
        if (!response.ok) throw new Error('Delete failed');

        document.querySelector(`.result[data-path="${CSS.escape(path)}"]`)?.remove();

        const idx = currentResultsList.findIndex(r => r.path === path);
        if (idx !== -1) currentResultsList.splice(idx, 1);

        if (currentModalIndex < currentResultsList.length) {
            const r = currentResultsList[currentModalIndex];
            openModal(r.image_url, r.episode, r.timestamp, r.path, r.frame, currentModalIndex);
        } else if (currentResultsList.length > 0) {
            currentModalIndex = currentResultsList.length - 1;
            const r = currentResultsList[currentModalIndex];
            openModal(r.image_url, r.episode, r.timestamp, r.path, r.frame, currentModalIndex);
        } else {
            closeModal();
        }
    } catch (err) {
        alert(`Failed to delete: ${err.message}`);
    }
}

// Event delegation: intercept result card clicks in select mode
document.getElementById('results').addEventListener('click', (e) => {
    if (!selectMode) return;
    const card = e.target.closest('.result');
    if (card?.dataset.path) toggleFrameSelection(card.dataset.path);
});

// 's' key to toggle select mode
document.addEventListener('keydown', (e) => {
    const modalActive = document.getElementById('modal').classList.contains('active');
    if (e.key === 's' && document.activeElement.tagName !== 'INPUT' && !modalActive && hasSearched) {
        e.preventDefault();
        toggleSelectMode();
    }
});

/** Stat card component factory. */
function createStatCard(label, value = '0', id = '') {
    const card = document.createElement('div');
    card.className = 'stat-card';
    if (id) card.id = id;
    card.innerHTML = `
        <div class="stat-value" data-stat-value>${value}</div>
        <div class="stat-label">${label}</div>
    `;
    return card;
}

function updateStatCard(card, value) {
    const el = card.querySelector('[data-stat-value]');
    if (el) el.textContent = value;
}

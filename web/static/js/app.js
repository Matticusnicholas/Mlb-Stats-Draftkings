// MLB Best Ball Analyzer - Frontend JavaScript

// Global state
let playersData = [];
let currentSort = { field: 'bestball_score', direction: 'desc' };
let currentScoringSystem = 'draftkings';
let currentStatsType = 'batting';

// DOM Elements
const loadBtn = document.getElementById('load-btn');
const exportBtn = document.getElementById('export-btn');
const refreshBtn = document.getElementById('refresh-btn');
const scoringSystem = document.getElementById('scoring-system');
const statsType = document.getElementById('stats-type');
const minGames = document.getElementById('min-games');
const limitSelect = document.getElementById('limit');
const loading = document.getElementById('loading');
const tbody = document.getElementById('players-tbody');
const dbStats = document.getElementById('db-stats');
const scoringInfo = document.getElementById('scoring-info');
const tableHeaders = document.getElementById('table-headers');

// Event Listeners
loadBtn.addEventListener('click', loadPlayers);
exportBtn.addEventListener('click', exportRankings);
refreshBtn.addEventListener('click', () => {
    loadPlayers();
    loadDatabaseStats();
});

// Scoring system change handler
scoringSystem.addEventListener('change', () => {
    currentScoringSystem = scoringSystem.value;
    updateScoringInfo();
    loadPlayers();
});

// Stats type change handler
statsType.addEventListener('change', () => {
    currentStatsType = statsType.value;
    updateTableHeaders();
    loadPlayers();
});

// Add click handlers for sortable headers (delegate to handle dynamic headers)
tableHeaders.addEventListener('click', (e) => {
    if (e.target.classList.contains('sortable')) {
        const field = e.target.dataset.sort;
        sortTable(field);
    }
});

// Initialize on page load
loadDatabaseStats();
updateScoringInfo();
updateTableHeaders();  // Initialize table headers with correct columns

/**
 * Update scoring system info in footer
 */
function updateScoringInfo() {
    const scoringNames = {
        'draftkings': 'DraftKings',
        'underdog': 'Underdog Fantasy',
        'drafters': 'Drafters'
    };
    scoringInfo.textContent = `MLB Best Ball Analyzer • Data from MLB Stats API • ${scoringNames[currentScoringSystem]} scoring`;
}

/**
 * Update table headers based on stats type
 */
function updateTableHeaders() {
    const isPitching = currentStatsType === 'pitching';
    const isCombined = currentStatsType === 'combined';

    // Show/hide workhorse info
    const workhorseInfo = document.getElementById('workhorse-info');
    const workhorseQs = document.getElementById('workhorse-qs');
    if (workhorseInfo && workhorseQs) {
        workhorseInfo.style.display = isPitching ? 'list-item' : 'none';
        workhorseQs.style.display = isPitching ? 'list-item' : 'none';
    }

    // Base headers
    let headers = `
        ${isCombined ? '<th class="sortable" data-sort="player_type">Pos</th>' : ''}
        <th class="sortable" data-sort="player_name">Player Name</th>
        <th class="sortable" data-sort="bestball_score">BB Score</th>
        <th class="sortable" data-sort="gini_coefficient" title="Gini Coefficient: point compression / burst tendency (0-1, higher = spikier)">Gini</th>
        <th class="sortable" data-sort="implied_volatility" title="Implied Volatility: player weekly σ / league median σ">IV</th>
        <th class="sortable" data-sort="iv_tier" title="IV Tier: Nuclear/Gamma/High-IV/Normal/Low-Vol">Tier</th>
        <th class="sortable" data-sort="useful_points_total">Useful Pts</th>
        <th class="sortable" data-sort="useful_weeks_count">Useful Wks</th>
        <th class="sortable" data-sort="useful_points_per_week">Pts/Wk</th>
        <th class="sortable" data-sort="best_week">Best Week</th>
        <th class="sortable" data-sort="boom_week_rate">Boom%</th>
        <th class="sortable" data-sort="tear3_rate">TEAR3</th>
    `;

    // Add workhorse columns for pitchers
    if (isPitching) {
        headers += `
            <th class="sortable" data-sort="workhorse_score">Workhorse</th>
            <th class="sortable" data-sort="quality_start_rate">QS%</th>
            <th class="sortable" data-sort="total_starts">Starts</th>
        `;
    }

    tableHeaders.innerHTML = headers;
}

/**
 * Load players from API
 */
async function loadPlayers() {
    try {
        showLoading(true);

        const params = new URLSearchParams({
            stats_type: currentStatsType,
            scoring_system: currentScoringSystem,
            min_games: minGames.value,
            limit: limitSelect.value,
            sort_by: currentSort.field
        });

        const response = await fetch(`/api/players?${params}`);
        const data = await response.json();

        if (!data.success) {
            throw new Error(data.error || 'Failed to load players');
        }

        playersData = data.players;
        console.log(`Loaded ${data.count} players using ${data.scoring_system} scoring`);

        renderTable();

    } catch (error) {
        console.error('Error loading players:', error);
        tbody.innerHTML = `<tr><td colspan="12" class="no-data">Error: ${error.message}</td></tr>`;
    } finally {
        showLoading(false);
    }
}

/**
 * Export rankings to CSV
 */
function exportRankings() {
    const params = new URLSearchParams({
        stats_type: currentStatsType,
        scoring_system: currentScoringSystem,
        min_games: minGames.value,
        limit: limitSelect.value,
        format: 'csv',
        include_workhorse: currentStatsType === 'pitching' ? 'true' : 'false'
    });

    const url = `/api/export?${params}`;
    window.location.href = url;
}

/**
 * Load database statistics
 */
async function loadDatabaseStats() {
    try {
        const response = await fetch('/api/stats');
        const data = await response.json();

        if (data.success) {
            const stats = data.stats;
            dbStats.textContent = `Database: ${stats.total_games} games • ${stats.total_players} players • ${stats.total_player_games} performances`;
        }
    } catch (error) {
        console.error('Error loading stats:', error);
    }
}

/**
 * Render players table
 */
function renderTable() {
    if (!playersData || playersData.length === 0) {
        tbody.innerHTML = '<tr><td colspan="12" class="no-data">No players found</td></tr>';
        return;
    }

    tbody.innerHTML = '';
    const isPitching = currentStatsType === 'pitching';
    const isCombined = currentStatsType === 'combined';

    playersData.forEach(player => {
        const row = document.createElement('tr');

        // Position (for combined only)
        if (isCombined) {
            const posCell = document.createElement('td');
            posCell.textContent = player.player_type === 'batting' ? 'BAT' : 'PIT';
            posCell.className = 'player-position';
            row.appendChild(posCell);
        }

        // Player Name with Profile Button
        const nameCell = document.createElement('td');
        nameCell.className = 'player-name';

        const nameContainer = document.createElement('div');
        nameContainer.style.display = 'flex';
        nameContainer.style.alignItems = 'center';
        nameContainer.style.gap = '8px';

        const nameSpan = document.createElement('span');
        nameSpan.textContent = player.player_name;

        const profileBtn = document.createElement('a');
        profileBtn.href = `/player/${player.player_id}?stats_type=${currentStatsType}&scoring_system=${currentScoringSystem}`;
        profileBtn.target = '_blank';
        profileBtn.className = 'profile-btn';
        profileBtn.title = 'View Player Profile';
        profileBtn.innerHTML = '📊';
        profileBtn.style.fontSize = '14px';
        profileBtn.style.cursor = 'pointer';
        profileBtn.style.textDecoration = 'none';

        nameContainer.appendChild(nameSpan);
        nameContainer.appendChild(profileBtn);
        nameCell.appendChild(nameContainer);
        row.appendChild(nameCell);

        // Base stats with percentile bars
        const baseStats = [
            { key: 'bestball_score', decimals: 1 },
            { key: 'gini_coefficient', decimals: 3 },  // Gini: burst compression (most persistent metric)
            { key: 'implied_volatility', decimals: 2 },  // IV metric
            // iv_tier handled separately below (not a number)
            { key: 'useful_points_total', decimals: 1 },
            { key: 'useful_weeks_count', decimals: 0 },
            { key: 'useful_points_per_week', decimals: 1 },
            { key: 'best_week', decimals: 1 },
            { key: 'boom_week_rate', decimals: 1 },
            { key: 'tear3_rate', decimals: 1 }
        ];

        // First stat: BB Score
        const bbScoreCell = createStatCell(player, baseStats[0].key, baseStats[0].decimals);
        row.appendChild(bbScoreCell);

        // Second stat: Gini
        const giniCell = createStatCell(player, baseStats[1].key, baseStats[1].decimals);
        row.appendChild(giniCell);

        // Third stat: IV
        const ivCell = createStatCell(player, baseStats[2].key, baseStats[2].decimals);
        row.appendChild(ivCell);

        // Fourth: IV Tier (text, not number)
        const tierCell = document.createElement('td');
        const tier = player.iv_tier || 'N/A';
        tierCell.textContent = tier;
        // Color code based on tier
        if (tier === 'Nuclear') {
            tierCell.style.color = '#ff0000';
            tierCell.style.fontWeight = 'bold';
        } else if (tier === 'Gamma') {
            tierCell.style.color = '#ff6600';
            tierCell.style.fontWeight = 'bold';
        } else if (tier === 'High-IV') {
            tierCell.style.color = '#ffaa00';
        } else if (tier === 'Normal') {
            tierCell.style.color = '#888';
        } else {
            tierCell.style.color = '#ccc';
        }
        row.appendChild(tierCell);

        // Remaining stats (skip first 3 since we already added BB Score, Gini, IV)
        baseStats.slice(3).forEach(stat => {
            const cell = createStatCell(player, stat.key, stat.decimals);
            row.appendChild(cell);
        });

        // Workhorse stats for pitchers
        if (isPitching) {
            const workhorseStats = [
                { key: 'workhorse_score', decimals: 1 },
                { key: 'quality_start_rate', decimals: 1 },
                { key: 'total_starts', decimals: 0 }
            ];

            workhorseStats.forEach(stat => {
                const cell = createStatCell(player, stat.key, stat.decimals);
                row.appendChild(cell);
            });
        }

        tbody.appendChild(row);
    });
}

/**
 * Create a stat cell with percentile bar
 */
function createStatCell(player, statKey, decimals) {
    const cell = document.createElement('td');
    const value = player[statKey] || 0;
    const percentile = player[`${statKey}_percentile`] || 0;

    // Create container
    const container = document.createElement('div');
    container.className = 'stat-cell';

    // Value
    const valueSpan = document.createElement('span');
    valueSpan.className = 'stat-value';
    valueSpan.textContent = decimals === 0 ? Math.round(value) : value.toFixed(decimals);

    // Percentile bar container
    const barContainer = document.createElement('div');
    barContainer.className = 'percentile-bar-container';

    // Percentile bar
    const bar = document.createElement('div');
    bar.className = 'percentile-bar ' + getPercentileClass(percentile);
    bar.style.width = percentile + '%';
    bar.title = `${percentile.toFixed(0)}th percentile`;

    barContainer.appendChild(bar);
    container.appendChild(valueSpan);
    container.appendChild(barContainer);
    cell.appendChild(container);

    return cell;
}

/**
 * Get percentile color class
 */
function getPercentileClass(percentile) {
    if (percentile >= 80) return 'percentile-80-100';
    if (percentile >= 60) return 'percentile-60-80';
    if (percentile >= 40) return 'percentile-40-60';
    if (percentile >= 20) return 'percentile-20-40';
    return 'percentile-0-20';
}

/**
 * Sort table by field
 */
function sortTable(field) {
    // Toggle sort direction
    if (currentSort.field === field) {
        currentSort.direction = currentSort.direction === 'desc' ? 'asc' : 'desc';
    } else {
        currentSort.field = field;
        currentSort.direction = 'desc';
    }

    // Sort data
    playersData.sort((a, b) => {
        let aVal = a[field];
        let bVal = b[field];

        // Handle string comparison for player names
        if (typeof aVal === 'string') {
            aVal = aVal.toLowerCase();
            bVal = bVal.toLowerCase();
        }

        if (currentSort.direction === 'desc') {
            return bVal > aVal ? 1 : -1;
        } else {
            return aVal > bVal ? 1 : -1;
        }
    });

    // Update header classes
    document.querySelectorAll('.sortable').forEach(th => {
        th.classList.remove('sorted-asc', 'sorted-desc');
        if (th.dataset.sort === field) {
            th.classList.add(currentSort.direction === 'desc' ? 'sorted-desc' : 'sorted-asc');
        }
    });

    // Re-render table
    renderTable();
}

/**
 * Show/hide loading indicator
 */
function showLoading(show) {
    if (show) {
        loading.classList.remove('hidden');
        tbody.innerHTML = '<tr><td colspan="12" class="no-data">Loading...</td></tr>';
    } else {
        loading.classList.add('hidden');
    }
}

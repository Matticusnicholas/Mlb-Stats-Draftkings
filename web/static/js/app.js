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

// Load database stats on page load
loadDatabaseStats();
updateScoringInfo();

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
        <th class="sortable" data-sort="useful_points_total">Useful Pts</th>
        <th class="sortable" data-sort="useful_weeks_count">Useful Wks</th>
        <th class="sortable" data-sort="useful_points_per_week">Pts/Wk</th>
        <th class="sortable" data-sort="best_week">Best Week</th>
        <th class="sortable" data-sort="boom_week_rate">Boom%</th>
        <th class="sortable" data-sort="tear3_rate">TEAR3</th>
        <th class="sortable" data-sort="tear4_rate">TEAR4</th>
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

        // Player Name
        const nameCell = document.createElement('td');
        nameCell.className = 'player-name';
        nameCell.textContent = player.player_name;
        row.appendChild(nameCell);

        // Base stats with percentile bars
        const baseStats = [
            { key: 'bestball_score', decimals: 1 },
            { key: 'useful_points_total', decimals: 1 },
            { key: 'useful_weeks_count', decimals: 0 },
            { key: 'useful_points_per_week', decimals: 1 },
            { key: 'best_week', decimals: 1 },
            { key: 'boom_week_rate', decimals: 1 },
            { key: 'tear3_rate', decimals: 1 },
            { key: 'tear4_rate', decimals: 1 }
        ];

        baseStats.forEach(stat => {
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

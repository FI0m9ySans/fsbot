// FSBot Dashboard — Frontend Logic

const API = '/api';

// Tab switching
document.querySelectorAll('.tab').forEach(btn => {
    btn.addEventListener('click', () => {
        document.querySelectorAll('.tab').forEach(b => b.classList.remove('active'));
        document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
        btn.classList.add('active');
        document.getElementById('tab-' + btn.dataset.tab).classList.add('active');
        loadTabData(btn.dataset.tab);
    });
});

function loadTabData(tab) {
    switch(tab) {
        case 'overview': loadOverview(); break;
        case 'users': loadUsers(); break;
        case 'leaderboard': loadLeaderboard(); break;
        case 'daily-checkin': loadDailyCheckinRanking(); break;
        case 'best-luck': loadBestLuckRanking(); break;
        case 'mods': loadMods(); break;
        case 'guilds': loadGuildsDetail(); break;
        case 'commands': loadCommands(); break;
        case 'logs': loadLogs(); break;
        case 'sdk-guilds': loadSdkGuilds(); break;
        case 'wiki': loadWiki(); break;
    }
    // 初始化公会和 Wiki 的搜索/筛选监听器
    if (tab === 'sdk-guilds' || tab === 'wiki') {
        initSdkWikiListeners();
    }
}

// Auto-refresh
let refreshInterval;
function startAutoRefresh() {
    refreshInterval = setInterval(() => {
        const activeTab = document.querySelector('.tab.active');
        if (activeTab && activeTab.dataset.tab === 'overview') {
            loadOverview();
        }
    }, 15000);
}

// ═══ Overview ═══
async function loadOverview() {
    try {
        const res = await fetch(API + '/status');
        if (!res.ok) throw new Error('Offline');
        const data = await res.json();

        document.getElementById('bot-status').className = 'status-dot online';
        document.getElementById('bot-name').textContent = data.bot_name;
        document.getElementById('uptime').textContent = '运行: ' + data.uptime;
        document.getElementById('ping').textContent = data.ping_ms === -1 ? '断连' : data.ping_ms + 'ms';

        // Bot info card
        document.getElementById('overview-bot').innerHTML = `
            <p class="big-number">${data.bot_name}</p>
            <p>🆔 ID: <strong>${data.bot_id}</strong></p>
            <p>📡 Ping: <strong>${data.ping_ms === -1 ? '🔴 断连' : data.ping_ms + 'ms'}</strong></p>
            <p>⏱ 运行时间: <strong>${data.uptime}</strong></p>
            <p>🕐 服务器时间: ${data.server_time}</p>
        `;

        // Guilds card
        document.getElementById('overview-guilds').innerHTML = `
            <p class="big-number">${data.guild_count}</p>
            <p>👥 总成员: <strong>${data.total_members.toLocaleString()}</strong></p>
            ${data.guilds.slice(0,3).map(g => `<p>📌 ${g.name} (${g.members}人)</p>`).join('')}
            ${data.guilds.length > 3 ? `<p>…还有 ${data.guilds.length - 3} 个服务器</p>` : ''}
        `;

        // Users card - fetch user count
        try {
            const uRes = await fetch(API + '/users?page=1&per_page=1');
            const uData = await uRes.json();
            document.getElementById('overview-users').innerHTML = `
                <p class="big-number">${uData.total.toLocaleString()}</p>
                <p>数据库注册用户总数</p>
            `;
        } catch(e) {
            document.getElementById('overview-users').innerHTML = '<p>加载失败</p>';
        }

        // Mods card
        document.getElementById('overview-mods').innerHTML = `
            <p class="big-number">${data.loaded_mods.length}</p>
            <p>已加载的模组</p>
            ${data.loaded_mods.map(m => `<p>🧩 ${esc(m.name || m)}</p>`).join('')}
        `;

    } catch(e) {
        document.getElementById('bot-status').className = 'status-dot offline';
        document.getElementById('bot-name').textContent = '连接失败';
    }
}

// ═══ Users ═══
let usersPage = 1;
async function loadUsers(page = 1) {
    usersPage = page;
    try {
        const res = await fetch(API + '/users?page=' + page + '&per_page=50');
        const data = await res.json();

        document.getElementById('user-total').textContent = `共 ${data.total.toLocaleString()} 个用户`;

        let html = '';
        data.users.forEach(u => {
            html += `<tr>
                <td><code>${u.user_id}</code></td>
                <td>${esc(u.username)}</td>
                <td>${(u.points ?? 0).toLocaleString()}</td>
                <td>${(u.monthly_points ?? 0).toLocaleString()}</td>
                <td>${u.exp.toLocaleString()}</td>
                <td><span class="badge badge-green">Lv ${u.level}</span></td>
                <td>${u.last_daily || '—'}</td>
            </tr>`;
        });
        document.getElementById('users-table').innerHTML = html || '<tr><td colspan="6" class="loading">无数据</td></tr>';

        // Pagination
        let phtml = '';
        phtml += `<button ${page <= 1 ? 'disabled' : ''} onclick="loadUsers(${page-1})">‹</button>`;
        for (let p = 1; p <= data.total_pages; p++) {
            if (p === 1 || p === data.total_pages || Math.abs(p - page) <= 2) {
                phtml += `<button class="${p === page ? 'active' : ''}" onclick="loadUsers(${p})">${p}</button>`;
            } else if (Math.abs(p - page) === 3) {
                phtml += '<button disabled>…</button>';
            }
        }
        phtml += `<button ${page >= data.total_pages ? 'disabled' : ''} onclick="loadUsers(${page+1})">›</button>`;
        document.getElementById('user-pagination').innerHTML = phtml;

    } catch(e) {
        document.getElementById('users-table').innerHTML = '<tr><td colspan="6" class="loading">加载失败</td></tr>';
    }
}

// Search
document.getElementById('user-search')?.addEventListener('input', function(e) {
    const query = e.target.value.toLowerCase();
    const rows = document.querySelectorAll('#users-table tr');
    rows.forEach(row => {
        const cells = row.querySelectorAll('td');
        if (cells.length > 1) {
            const name = cells[1].textContent.toLowerCase();
            const id = cells[0].textContent;
            row.style.display = (name.includes(query) || id.includes(query)) ? '' : 'none';
        }
    });
});

// ═══ Leaderboard ═══
async function loadLeaderboard() {
    try {
        const res = await fetch(API + '/leaderboard?limit=50');
        const data = await res.json();

        const medals = ['🥇','🥈','🥉'];
        let html = '';
        data.leaderboard.forEach(u => {
            html += `<tr>
                <td>${medals[u.rank-1] || '#' + u.rank}</td>
                <td><strong>${esc(u.username)}</strong></td>
                <td>${(u.monthly_points ?? u.points ?? 0).toLocaleString()}</td>
                <td>${u.exp.toLocaleString()}</td>
                <td><span class="badge badge-green">Lv ${u.level}</span></td>
            </tr>`;
        });
        document.getElementById('leaderboard-table').innerHTML = html || '<tr><td colspan="5" class="loading">无数据</td></tr>';

    } catch(e) {
        document.getElementById('leaderboard-table').innerHTML = '<tr><td colspan="5" class="loading">加载失败</td></tr>';
    }
}

// ═══ Daily Checkin Ranking (S1 麦收季) ═══
async function loadDailyCheckinRanking() {
    try {
        const res = await fetch(API + '/daily-checkin-ranking?limit=50');
        const data = await res.json();

        document.getElementById('daily-checkin-date').textContent =
            '📅 日期: ' + (data.date || '——') + ' | ' + (data.season || '');

        const medals = ['🥇','🥈','🥉'];
        let html = '';
        if (data.ranking && data.ranking.length > 0) {
            data.ranking.forEach(u => {
                const time = u.checkin_time || '—';
                const displayTime = time.length >= 16 ? time.substring(11, 16) : time;
                html += `<tr>
                    <td>${medals[u.rank-1] || '#' + u.rank}</td>
                    <td><strong>${esc(u.username)}</strong></td>
                    <td>🕐 <strong>${esc(displayTime)}</strong> <span style="color:#888;font-size:0.85em;">${esc(time)}</span></td>
                    <td><code>${u.user_id}</code></td>
                </tr>`;
            });
        } else {
            html = '<tr><td colspan="4" class="loading">今天还没有人签到，快来抢第一！🌾</td></tr>';
        }
        document.getElementById('daily-checkin-table').innerHTML = html;

    } catch(e) {
        document.getElementById('daily-checkin-table').innerHTML = '<tr><td colspan="4" class="loading">加载失败</td></tr>';
    }
}

// ═══ Best Luck Ranking (S1 麦收季) ═══
async function loadBestLuckRanking() {
    try {
        const res = await fetch(API + '/best-luck-ranking?limit=50');
        const data = await res.json();

        const medals = ['🥇','🥈','🥉'];
        let html = '';
        if (data.ranking && data.ranking.length > 0) {
            data.ranking.forEach(u => {
                html += `<tr>
                    <td>${medals[u.rank-1] || '#' + u.rank}</td>
                    <td><strong>${esc(u.username)}</strong></td>
                    <td>🍀 <strong>${u.best_luck_count}</strong> 次</td>
                    <td><code>${u.user_id}</code></td>
                </tr>`;
            });
        } else {
            html = '<tr><td colspan="4" class="loading">还没有人抢到过手气最佳，快来发红包吧！🧧</td></tr>';
        }
        document.getElementById('best-luck-table').innerHTML = html;

    } catch(e) {
        document.getElementById('best-luck-table').innerHTML = '<tr><td colspan="4" class="loading">加载失败</td></tr>';
    }
}

// ═══ Mods ═══
async function loadMods() {
    try {
        const [mRes, sRes] = await Promise.all([
            fetch(API + '/mods'),
            fetch(API + '/status')
        ]);
        const modData = await mRes.json();
        const statusData = await sRes.json();

        let html = '';
        if (modData.mods && modData.mods.length > 0) {
            modData.mods.forEach(m => {
                html += `<tr>
                    <td>🧩 <strong>${esc(m.name)}</strong></td>
                    <td><span class="badge badge-blue">${esc(m.version)}</span></td>
                    <td>${esc(m.author)}</td>
                    <td>${esc(m.description || '')}</td>
                </tr>`;
            });
        } else {
            html = '<tr><td colspan="4" class="loading">没有已加载的模组</td></tr>';
        }
        document.getElementById('mods-table').innerHTML = html;
    } catch(e) {
        document.getElementById('mods-table').innerHTML = '<tr><td colspan="4" class="loading">加载失败</td></tr>';
    }
}

// ═══ Guilds ═══
async function loadGuilds() {
    try {
        const res = await fetch(API + '/status');
        const data = await res.json();

        let html = '';
        data.guilds.forEach(g => {
            html += `<tr>
                <td>📌 <strong>${esc(g.name)}</strong></td>
                <td>${g.members.toLocaleString()}</td>
                <td>${esc(g.owner)}</td>
                <td><code>${g.id}</code></td>
            </tr>`;
        });
        document.getElementById('guilds-table').innerHTML = html || '<tr><td colspan="4" class="loading">无数据</td></tr>';
    } catch(e) {
        document.getElementById('guilds-table').innerHTML = '<tr><td colspan="4" class="loading">加载失败</td></tr>';
    }
}

// ═══ Commands ═══
async function loadCommands() {
    try {
        const res = await fetch(API + '/commands');
        const data = await res.json();

        let html = '';
        data.commands.forEach(c => {
            html += `<tr>
                <td><code>/${esc(c.name)}</code></td>
                <td>${esc(c.description)}</td>
            </tr>`;
        });
        document.getElementById('commands-table').innerHTML = html || '<tr><td colspan="2" class="loading">无命令</td></tr>';
    } catch(e) {
        document.getElementById('commands-table').innerHTML = '<tr><td colspan="2" class="loading">加载失败</td></tr>';
    }
}

// ═══ Logs ═══
async function loadLogs() {
    try {
        const res = await fetch(API + '/logs?limit=100');
        const data = await res.json();

        let html = '';
        data.logs.forEach(log => {
            html += `<div class="log-entry">
                <span class="log-time">${log.time}</span>
                <span class="log-level-${log.level.toLowerCase()}">[${log.level}]</span>
                <span>${esc(log.message)}</span>
            </div>`;
        });
        document.getElementById('log-container').innerHTML = html || '<div class="loading">无日志</div>';
    } catch(e) {
        document.getElementById('log-container').innerHTML = '<div class="loading">加载失败</div>';
    }
}

// ═══ SDK 公会列表 ═══
let sdkGuildsPage = 1;
let sdkGuildsCategory = '';
let sdkGuildsSearch = '';
let sdkGuildView = 'list'; // 'list' | 'leaderboard'

async function loadSdkGuilds(page = 1, category = '', search = '', view = '') {
    sdkGuildsPage = page;
    if (category !== undefined) sdkGuildsCategory = category;
    if (search !== undefined) sdkGuildsSearch = search;
    if (view) sdkGuildView = view;

    if (sdkGuildView === 'leaderboard') {
        await loadSdkGuildLeaderboard();
        return;
    }

    try {
        const params = new URLSearchParams();
        params.append('page', sdkGuildsPage);
        params.append('per_page', 20);
        if (sdkGuildsCategory) params.append('category', sdkGuildsCategory);
        if (sdkGuildsSearch) params.append('search', sdkGuildsSearch);
        const res = await fetch(`${API}/sdk-guilds?${params}`);
        const data = await res.json();

        document.getElementById('guild-total').textContent = `共 ${data.total.toLocaleString()} 个公会`;

        // 分类下拉
        const catSel = document.getElementById('guild-category-filter');
        if (catSel && data.categories) {
            const cur = catSel.value;
            catSel.innerHTML = '<option value="">全部分类</option>' +
                data.categories.map(c => `<option value="${esc(c)}">${esc(c)}</option>`).join('');
            catSel.value = cur || '';
        }

        let html = '';
        data.guilds.forEach(g => {
            html += `<tr>
                <td>${g.id}</td>
                <td><strong>${esc(g.name)}</strong></td>
                <td><span class="badge">${esc(g.category || '未分类')}</span></td>
                <td><span class="badge badge-green">Lv ${g.level}</span></td>
                <td>${g.exp.toLocaleString()}</td>
                <td>${g.funds !== undefined ? g.funds.toLocaleString() : '—'}</td>
                <td><code>${g.leader_id || '—'}</code></td>
                <td>${g.created_at || '—'}</td>
            </tr>`;
        });
        document.getElementById('sdk-guilds-table').innerHTML = html || '<tr><td colspan="8" class="loading">无数据</td></tr>';

        // 分页
        let phtml = '';
        phtml += `<button ${page <= 1 ? 'disabled' : ''} onclick="loadSdkGuilds(${page-1})">‹</button>`;
        for (let p = 1; p <= data.total_pages; p++) {
            if (p === 1 || p === data.total_pages || Math.abs(p - page) <= 2) {
                phtml += `<button class="${p === page ? 'active' : ''}" onclick="loadSdkGuilds(${p})">${p}</button>`;
            } else if (Math.abs(p - page) === 3) {
                phtml += '<button disabled>…</button>';
            }
        }
        phtml += `<button ${page >= data.total_pages ? 'disabled' : ''} onclick="loadSdkGuilds(${page+1})">›</button>`;
        document.getElementById('sdk-guilds-pagination').innerHTML = phtml;

    } catch(e) {
        document.getElementById('sdk-guilds-table').innerHTML = '<tr><td colspan="8" class="loading">加载失败</td></tr>';
    }
}

async function loadSdkGuildLeaderboard(sortBy = 'level') {
    try {
        const res = await fetch(`${API}/sdk-guild-leaderboard?sort_by=${sortBy}&limit=50`);
        const data = await res.json();

        let html = `<div class="lb-controls" style="margin-bottom:8px;">
                <button onclick="loadSdkGuilds(1, '', '', 'list')">← 返回列表</button>
                <button class="${data.sort_by === 'level' ? 'active' : ''}" onclick="loadSdkGuildLeaderboard('level')">按等级</button>
                <button class="${data.sort_by === 'exp' ? 'active' : ''}" onclick="loadSdkGuildLeaderboard('exp')">按经验</button>
                <button class="${data.sort_by === 'funds' ? 'active' : ''}" onclick="loadSdkGuildLeaderboard('funds')">按资金</button>
            </div>
            <table>
                <thead>
                    <tr><th>排名</th><th>公会名</th><th>等级</th><th>经验</th><th>资金</th><th>创建时间</th></tr>
                </thead>
                <tbody>`;

        const medals = ['🥇','🥈','🥉'];
        data.leaderboard.forEach(g => {
            html += `<tr>
                <td>${medals[g.rank-1] || '#' + g.rank}</td>
                <td><strong>${esc(g.name)}</strong></td>
                <td><span class="badge badge-green">Lv ${g.level}</span></td>
                <td>${g.exp.toLocaleString()}</td>
                <td>${g.funds !== undefined ? g.funds.toLocaleString() : '—'}</td>
                <td>${g.created_at || '—'}</td>
            </tr>`;
        });
        html += '</tbody></table>';

        // 替换整个 tab 内容
        document.getElementById('tab-sdk-guilds').innerHTML = html;

    } catch(e) {
        document.getElementById('tab-sdk-guilds').innerHTML = '<div class="loading">加载失败</div>';
    }
}


// ═══ Wiki 列表 ═══
let wikiPage = 1;
let wikiCategory = '';
let wikiSearch = '';

async function loadWiki(page = 1, category = '', search = '') {
    wikiPage = page;
    if (category !== undefined) wikiCategory = category;
    if (search !== undefined) wikiSearch = search;

    try {
        const params = new URLSearchParams();
        params.append('page', wikiPage);
        params.append('per_page', 20);
        if (wikiCategory) params.append('category', wikiCategory);
        if (wikiSearch) params.append('search', wikiSearch);
        const res = await fetch(`${API}/wiki?${params}`);
        const data = await res.json();

        document.getElementById('wiki-total').textContent = `共 ${data.total.toLocaleString()} 个页面`;

        // 分类下拉
        const catSel = document.getElementById('wiki-category-filter');
        if (catSel && data.categories) {
            const cur = catSel.value;
            catSel.innerHTML = '<option value="">全部分类</option>' +
                data.categories.map(c => `<option value="${esc(c)}">${esc(c)}</option>`).join('');
            catSel.value = cur || '';
        }

        let html = '';
        data.pages.forEach(p => {
            html += `<tr>
                <td>${p.id}</td>
                <td><a href="javascript:viewWikiPage(${p.id})" class="wiki-link"><strong>${esc(p.title)}</strong></a></td>
                <td><span class="badge">${esc(p.category || '未分类')}</span></td>
                <td><code>${p.author_id || '—'}</code></td>
                <td>${p.updated_at || p.created_at || '—'}</td>
            </tr>`;
        });
        document.getElementById('wiki-table').innerHTML = html || '<tr><td colspan="5" class="loading">无数据</td></tr>';

        // 分页
        let phtml = '';
        phtml += `<button ${page <= 1 ? 'disabled' : ''} onclick="loadWiki(${page-1})">‹</button>`;
        for (let p = 1; p <= data.total_pages; p++) {
            if (p === 1 || p === data.total_pages || Math.abs(p - page) <= 2) {
                phtml += `<button class="${p === page ? 'active' : ''}" onclick="loadWiki(${p})">${p}</button>`;
            } else if (Math.abs(p - page) === 3) {
                phtml += '<button disabled>…</button>';
            }
        }
        phtml += `<button ${page >= data.total_pages ? 'disabled' : ''} onclick="loadWiki(${page+1})">›</button>`;
        document.getElementById('wiki-pagination').innerHTML = phtml;

    } catch(e) {
        document.getElementById('wiki-table').innerHTML = '<tr><td colspan="5" class="loading">加载失败</td></tr>';
    }
}


// ═══ Wiki 详情 & 版本历史 ═══
let wikiDetailView = false;

async function viewWikiPage(pageId) {
    wikiDetailView = true;
    const tab = document.getElementById('tab-wiki');
    tab.innerHTML = '<div class="loading">加载中…</div>';

    try {
        const [pageRes, verRes] = await Promise.all([
            fetch(`${API}/wiki/${pageId}`),
            fetch(`${API}/wiki/${pageId}/versions`)
        ]);
        const page = await pageRes.json();
        const verData = await verRes.json();

        if (page.error) {
            tab.innerHTML = `<div class="wiki-detail">
                <button class="btn-back" onclick="backToWikiList()">← 返回列表</button>
                <div class="loading">❌ ${esc(page.error)}</div>
            </div>`;
            return;
        }

        let versionBar = '';
        if (verData.versions && verData.versions.length > 0) {
            versionBar = '<div class="wiki-versions"><span class="wiki-ver-label">📜 版本历史:</span> ';
            verData.versions.forEach((v, i) => {
                const cls = v.is_current ? 'wiki-ver-btn active' : 'wiki-ver-btn';
                const label = v.is_current ? '最新' : `v${v.version_num}`;
                versionBar += `<button class="${cls}" onclick="viewWikiVersion(${pageId}, ${v.version_num}, '${esc(v.title)}', '${esc(v.edited_at || '')}', ${v.editor_id || 0})">${label}</button>`;
            });
            versionBar += '</div>';
        }

        const contentHtml = page.content
            ? esc(page.content).replace(/\n/g, '<br>')
            : '<span class="loading">（空内容）</span>';

        tab.innerHTML = `
            <div class="wiki-detail">
                <div class="wiki-detail-header">
                    <button class="btn-back" onclick="backToWikiList()">← 返回列表</button>
                    <span class="badge">${esc(page.category || '未分类')}</span>
                </div>
                <h2 class="wiki-detail-title" id="wiki-detail-title">${esc(page.title)}</h2>
                <div class="wiki-detail-meta" id="wiki-detail-meta">
                    <span>👤 作者 ID: <code>${page.author_id || '—'}</code></span>
                    <span>🕐 更新: ${page.updated_at || page.created_at || '—'}</span>
                    <span>🆔 Page ID: ${page.id}</span>
                </div>
                ${versionBar}
                <div class="wiki-detail-content" id="wiki-detail-content">
                    ${contentHtml}
                </div>
            </div>
        `;
    } catch(e) {
        tab.innerHTML = `<div class="wiki-detail">
            <button class="btn-back" onclick="backToWikiList()">← 返回列表</button>
            <div class="loading">❌ 加载失败: ${esc(e.message)}</div>
        </div>`;
    }
}

async function viewWikiVersion(pageId, versionNum, title, editedAt, editorId) {
    // 高亮版本按钮
    document.querySelectorAll('.wiki-ver-btn').forEach(b => b.classList.remove('active'));
    event?.target?.classList?.add('active');

    const contentEl = document.getElementById('wiki-detail-content');
    const titleEl = document.getElementById('wiki-detail-title');
    const metaEl = document.getElementById('wiki-detail-meta');
    if (contentEl) contentEl.innerHTML = '<div class="loading">加载版本中…</div>';

    try {
        const res = await fetch(`${API}/wiki/${pageId}/version/${versionNum}`);
        const data = await res.json();
        if (data.error) {
            contentEl.innerHTML = `<div class="loading">❌ ${esc(data.error)}</div>`;
            return;
        }
        const contentHtml = data.content
            ? esc(data.content).replace(/\n/g, '<br>')
            : '<span class="loading">（空内容）</span>';

        if (titleEl) titleEl.innerHTML = esc(data.title) + (data.is_current ? '' : ' <span class="wiki-ver-tag">历史版本</span>');
        if (metaEl) {
            metaEl.innerHTML = `
                <span>👤 ${data.is_current ? '作者' : '编辑'} ID: <code>${data.editor_id || '—'}</code></span>
                <span>🕐 ${data.is_current ? '更新' : '编辑'}: ${data.edited_at || '—'}</span>
                <span>🆔 Page ID: ${pageId}</span>
                ${!data.is_current ? `<span>📌 版本: v${data.version_num}</span>` : ''}
            `;
        }
        contentEl.innerHTML = contentHtml;
    } catch(e) {
        contentEl.innerHTML = `<div class="loading">❌ 加载失败: ${esc(e.message)}</div>`;
    }
}

function backToWikiList() {
    wikiDetailView = false;
    // 恢复原始 Wiki tab HTML
    document.getElementById('tab-wiki').innerHTML = `
        <div class="table-controls">
            <input type="text" id="wiki-search" placeholder="搜索标题或内容..." class="search-input">
            <select id="wiki-category-filter" class="search-input" style="width:120px;margin-left:8px;">
                <option value="">全部分类</option>
            </select>
            <span id="wiki-total">共 0 个页面</span>
        </div>
        <div class="table-wrap">
            <table>
                <thead>
                    <tr>
                        <th>ID</th><th>标题</th><th>分类</th><th>作者ID</th><th>更新时间</th>
                    </tr>
                </thead>
                <tbody id="wiki-table">
                    <tr><td colspan="5" class="loading">加载中…</td></tr>
                </tbody>
            </table>
        </div>
        <div class="pagination" id="wiki-pagination"></div>
    `;
    // 重新绑定事件
    initSdkWikiListeners();
    loadWiki(wikiPage, wikiCategory, wikiSearch);
}


// ═══ 公会详情 (Discord 服务器) ═══
async function loadGuildsDetail() {
    try {
        const res = await fetch(API + '/guilds-detail');
        const data = await res.json();

        let summary = `
            <div class="guild-summary">
                <div class="guild-stat"><span class="guild-stat-num">${data.guild_count}</span><span class="guild-stat-label">服务器</span></div>
                <div class="guild-stat"><span class="guild-stat-num">${data.total_members.toLocaleString()}</span><span class="guild-stat-label">总成员</span></div>
                <div class="guild-stat"><span class="guild-stat-num">${data.total_online >= 0 ? data.total_online.toLocaleString() : '?'}</span><span class="guild-stat-label">在线</span></div>
            </div>
        `;

        let html = '';
        data.guilds.forEach(g => {
            const onlineStr = g.online >= 0 ? `<span class="online-badge">${g.online} 在线</span>` : '';
            const boostStr = g.boost_level > 0 ? `<span class="boost-badge">🚀 Lv${g.boost_level} (${g.boost_count})</span>` : '';
            const iconHtml = g.icon_url
                ? `<img src="${g.icon_url}" class="guild-icon" alt="" onerror="this.style.display='none'">`
                : '<span class="guild-icon-placeholder">🌐</span>';

            html += `<tr>
                <td>${iconHtml} <strong>${esc(g.name)}</strong></td>
                <td>
                    <span class="member-count">${g.members.toLocaleString()}</span>
                    ${onlineStr}
                </td>
                <td>${esc(g.owner)}<br><code style="font-size:11px;opacity:0.6;">${g.owner_id}</code></td>
                <td style="font-size:13px;">
                    📝 ${g.text_channels} 文字<br>
                    🔊 ${g.voice_channels} 语音<br>
                    📁 ${g.categories} 分类<br>
                    🎭 ${g.roles} 角色
                </td>
                <td>${boostStr || '<span style="color:var(--text-dim);">—</span>'}</td>
                <td style="font-size:12px;">${g.created_at}</td>
                <td><code style="font-size:11px;">${g.id}</code></td>
            </tr>`;
        });

        document.getElementById('guilds-detail-container').innerHTML =
            summary +
            `<div class="table-wrap"><table>
                <thead><tr>
                    <th>服务器</th><th>成员</th><th>服主</th><th>频道/角色</th><th>Boost</th><th>创建时间</th><th>ID</th>
                </tr></thead>
                <tbody>${html || '<tr><td colspan="7" class="loading">无数据</td></tr>'}</tbody>
            </table></div>`;
    } catch(e) {
        document.getElementById('guilds-detail-container').innerHTML = '<div class="loading">加载失败</div>';
    }
}


// ═══ 搜索/筛选事件绑定 ═══
function initSdkWikiListeners() {
    // 公会搜索
    const gs = document.getElementById('guild-search');
    if (gs && !gs.dataset.bound) {
        gs.addEventListener('input', function() {
            loadSdkGuilds(1, sdkGuildsCategory, this.value);
        });
        gs.dataset.bound = '1';
    }
    const gcf = document.getElementById('guild-category-filter');
    if (gcf && !gcf.dataset.bound) {
        gcf.addEventListener('change', function() {
            loadSdkGuilds(1, this.value, sdkGuildsSearch);
        });
        gcf.dataset.bound = '1';
    }

    // Wiki 搜索
    const ws = document.getElementById('wiki-search');
    if (ws && !ws.dataset.bound) {
        ws.addEventListener('input', function() {
            loadWiki(1, wikiCategory, this.value);
        });
        ws.dataset.bound = '1';
    }
    const wcf = document.getElementById('wiki-category-filter');
    if (wcf && !wcf.dataset.bound) {
        wcf.addEventListener('change', function() {
            loadWiki(1, this.value, wikiSearch);
        });
        wcf.dataset.bound = '1';
    }
}

// 在 tab 切换时初始化监听器
const _origLoadTabData = loadTabData;
// 直接在 Tab 点击里处理 — 在 dashboard.html 的 script 里调用 initSdkWikiListeners()


// ═══ Helpers ═══
function esc(str) {
    if (!str) return '';
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}

// Initial load
loadOverview();
startAutoRefresh();

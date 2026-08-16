let globalData = {
    members: [],
    summary: {},
    parties: {}
};

let currentSort = {
    field: 'id',
    direction: 1 // 1 for ascending, -1 for descending
};

document.addEventListener('DOMContentLoaded', () => {
    fetchData();

    document.getElementById('filter-house').addEventListener('change', renderMembersList);
    document.getElementById('filter-party').addEventListener('change', renderMembersList);
    document.getElementById('filter-school').addEventListener('change', renderMembersList);
    
    document.getElementById('sort-id').addEventListener('click', () => handleTableSort('id'));
    document.getElementById('sort-elections').addEventListener('click', () => handleTableSort('elections'));
    document.getElementById('sort-age').addEventListener('click', () => handleTableSort('age'));
    document.getElementById('sort-birthplace').addEventListener('click', () => handleTableSort('birthplace'));
    document.getElementById('sort-school').addEventListener('click', () => handleTableSort('school'));

    document.getElementById('birthplace-house-filter').addEventListener('change', renderBirthplaceChart);
    document.getElementById('birthplace-sort').addEventListener('change', renderBirthplaceChart);
    document.getElementById('birthplace-display-mode').addEventListener('change', renderBirthplaceChart);
});

/**
 * 生年月（日）または生年文字列から基準日（当年1月1日時点）での満年齢を計算する
 * - 年月日 / 年月の場合: 基準日（当年1月1日時点）での満年齢
 * - 生年のみの場合: 当年1月1日時点での年齢（当年 - 生年）
 */
function calculateAge(birthdateStr, refDate) {
    if (!birthdateStr || birthdateStr === "不明") return null;
    
    // 1. YYYY年M月D日 または YYYY年M月
    const mFull = birthdateStr.match(/(\d{4})年(\d{1,2})月(?:(\d{1,2})日)?/);
    if (mFull) {
        const birthYear = parseInt(mFull[1], 10);
        const birthMonth = parseInt(mFull[2], 10) - 1; // 0-indexed (0=Jan)
        const birthDay = mFull[3] ? parseInt(mFull[3], 10) : 1;
        
        const birthDate = new Date(birthYear, birthMonth, birthDay);
        let age = refDate.getFullYear() - birthDate.getFullYear();
        const monthDiff = refDate.getMonth() - birthDate.getMonth();
        
        if (monthDiff < 0 || (monthDiff === 0 && refDate.getDate() < birthDate.getDate())) {
            age--;
        }
        return age;
    }

    // 2. 生年のみ（YYYY年）の場合: 当年1月1日時点での年齢（当年 - 生年）
    const mYearOnly = birthdateStr.match(/(\d{4})年/);
    if (mYearOnly) {
        const birthYear = parseInt(mYearOnly[1], 10);
        return refDate.getFullYear() - birthYear;
    }
    
    return null;
}

/**
 * 年齢集計計算（平均、中央値、最高年齢、人数）
 */
function computeStats(members, filterFn) {
    const filtered = filterFn ? members.filter(filterFn) : members;
    const ages = filtered
        .map(m => m.age)
        .filter(a => a !== null && a !== undefined)
        .sort((a, b) => a - b);
        
    if (ages.length === 0) {
        return { mean: null, median: null, max: null, count: filtered.length };
    }
    
    const sum = ages.reduce((acc, v) => acc + v, 0);
    const mean = Math.round((sum / ages.length) * 10) / 10;
    
    let median;
    const mid = Math.floor(ages.length / 2);
    if (ages.length % 2 === 0) {
        median = Math.round(((ages[mid - 1] + ages[mid]) / 2) * 10) / 10;
    } else {
        median = ages[mid];
    }
    
    return {
        mean: mean,
        median: median,
        max: ages[ages.length - 1],
        count: filtered.length
    };
}

async function fetchData() {
    try {
        let data = null;
        
        // 1. file:// プロトコル等で直接開いた場合、data.js のグローバル変数を利用
        if (typeof window.DIET_DATA !== 'undefined' && window.DIET_DATA && window.DIET_DATA.members) {
            data = window.DIET_DATA;
        } else if (typeof window.membersData !== 'undefined' && window.membersData && window.membersData.members) {
            data = window.membersData;
        } else if (typeof membersData !== 'undefined' && membersData && membersData.members) {
            data = membersData;
        } else {
            // 2. Webサーバー経由等の場合は fetch API で取得
            const response = await fetch('data.json');
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            data = await response.json();
        }
        
        // 年齢の基準日: 当年1月1日時点
        const now = new Date();
        const refDate = new Date(now.getFullYear(), 0, 1);
        
        // 各議員レコードに対して生年月（日）から動的に年齢を計算・付与
        const enrichedMembers = (data.members || []).map(m => ({
            ...m,
            age: calculateAge(m.birthdate, refDate)
        }));

        // 集計データを動的に算出
        const summary = {
            overall: computeStats(enrichedMembers),
            shugiin: computeStats(enrichedMembers, m => m.house === "衆議院"),
            sangiin: computeStats(enrichedMembers, m => m.house === "参議院")
        };
        
        // 会派別集計
        const partySet = new Set(enrichedMembers.map(m => m.party).filter(Boolean));
        const parties = {};
        partySet.forEach(partyName => {
            parties[partyName] = computeStats(enrichedMembers, m => m.party === partyName);
        });

        globalData = {
            members: enrichedMembers,
            summary: summary,
            parties: parties,
            last_updated: data.last_updated
        };

        // UI更新
        updateHeader(data.last_updated, refDate);
        updateSummary(globalData.summary);
        populatePartyFilter(globalData.parties);
        populateSchoolFilter(enrichedMembers);
        renderPartyTable(globalData.parties);
        renderBirthplaceChart();
        
        // 初回は年齢の降順でソート
        globalData.members.sort((a, b) => {
            if (a.age === null) return 1;
            if (b.age === null) return -1;
            return (b.age - a.age);
        });
        
        renderMembersList();

    } catch (e) {
        console.error("データの読み込みに失敗しました", e);
        document.getElementById('last-updated-text').textContent = 'データの読み込みに失敗しました。';
    }
}

const PREFECTURE_ORDER = [
    '北海道', '青森県', '岩手県', '宮城県', '秋田県', '山形県', '福島県',
    '茨城県', '栃木県', '群馬県', '埼玉県', '千葉県', '東京都', '神奈川県',
    '新潟県', '富山県', '石川県', '福井県', '山梨県', '長野県', '岐阜県',
    '静岡県', '愛知県', '三重県', '滋賀県', '京都府', '大阪府', '兵庫県',
    '奈良県', '和歌山県', '鳥取県', '島根県', '岡山県', '広島県', '山口県',
    '徳島県', '香川県', '愛媛県', '高知県', '福岡県', '佐賀県', '長崎県',
    '熊本県', '大分県', '宮崎県', '鹿児島県', '沖縄県', '外国', '不明'
];

function renderBirthplaceChart() {
    const houseFilter = document.getElementById('birthplace-house-filter').value;
    const sortMode = document.getElementById('birthplace-sort').value;
    const displayMode = document.getElementById('birthplace-display-mode').value;

    const filteredMembers = globalData.members.filter(m => {
        return houseFilter === 'all' || m.house === houseFilter;
    });

    const totalCount = filteredMembers.length;
    if (totalCount === 0) {
        document.getElementById('birthplace-chart').innerHTML = '<div style="padding: 20px; text-align: center; color: var(--text-secondary);">該当するデータがありません。</div>';
        document.getElementById('birthplace-chart-summary').textContent = '';
        return;
    }

    // 各出身地の人数を集計
    const countMap = {};
    PREFECTURE_ORDER.forEach(p => { countMap[p] = 0; });
    
    filteredMembers.forEach(m => {
        const bp = m.birthplace || '不明';
        countMap[bp] = (countMap[bp] || 0) + 1;
    });

    let chartData = [];
    if (displayMode === 'all') {
        chartData = PREFECTURE_ORDER.map(name => ({
            name: name,
            count: countMap[name] || 0
        }));
    } else {
        // 出身者がいる地域のみ (nonzero / top20)
        chartData = Object.keys(countMap)
            .filter(name => countMap[name] > 0)
            .map(name => ({
                name: name,
                count: countMap[name]
            }));
    }

    // ソート適用
    if (sortMode === 'count_desc') {
        chartData.sort((a, b) => b.count - a.count || PREFECTURE_ORDER.indexOf(a.name) - PREFECTURE_ORDER.indexOf(b.name));
    } else if (sortMode === 'count_asc') {
        chartData.sort((a, b) => a.count - b.count || PREFECTURE_ORDER.indexOf(a.name) - PREFECTURE_ORDER.indexOf(b.name));
    } else if (sortMode === 'geo') {
        chartData.sort((a, b) => PREFECTURE_ORDER.indexOf(a.name) - PREFECTURE_ORDER.indexOf(b.name));
    }

    if (displayMode === 'top20') {
        chartData = chartData.slice(0, 20);
    }

    const maxCount = Math.max(...chartData.map(d => d.count), 1);
    const container = document.getElementById('birthplace-chart');
    container.innerHTML = '';

    chartData.forEach(item => {
        const row = document.createElement('div');
        row.className = 'bar-row';

        const percentage = totalCount > 0 ? ((item.count / totalCount) * 100).toFixed(1) : '0.0';
        const widthPercent = maxCount > 0 ? ((item.count / maxCount) * 100).toFixed(1) : '0';
        
        let barClass = 'bar-fill';
        if (item.name === '外国') barClass += ' foreign';
        if (item.name === '不明') barClass += ' unknown';

        row.innerHTML = `
            <div class="bar-label">${item.name}</div>
            <div class="bar-track">
                <div class="${barClass}" style="width: ${widthPercent}%;"></div>
            </div>
            <div class="bar-value">
                <span>${item.count}名</span>
                <span class="bar-percentage">(${percentage}%)</span>
            </div>
        `;
        container.appendChild(row);
    });

    const houseLabel = houseFilter === 'all' ? '全体 (衆参両院)' : houseFilter;
    const distinctRegions = Object.keys(countMap).filter(k => countMap[k] > 0 && k !== '不明' && k !== '外国').length;
    document.getElementById('birthplace-chart-summary').textContent = 
        `集計対象: ${houseLabel}（計${totalCount}名） / 出身都道府県数: ${distinctRegions}/47都道府県`;
}

function updateHeader(lastUpdatedStr, refDate) {
    const formattedRef = `${refDate.getFullYear()}年1月1日時点`;
    let updateText = `年齢基準日: ${formattedRef}`;
    
    if (lastUpdatedStr) {
        const date = new Date(lastUpdatedStr);
        const formattedDate = `${date.getFullYear()}年${date.getMonth() + 1}月${date.getDate()}日 ${String(date.getHours()).padStart(2, '0')}:${String(date.getMinutes()).padStart(2, '0')}`;
        updateText += ` / データ取得日: ${formattedDate}`;
    }
    document.getElementById('last-updated-text').textContent = updateText;
}

function formatAge(age) {
    return age !== null && age !== undefined ? `${age}歳` : '-';
}

function updateSummary(summary) {
    if (summary.shugiin) {
        document.getElementById('shugiin-mean').textContent = formatAge(summary.shugiin.mean);
        document.getElementById('shugiin-median').textContent = formatAge(summary.shugiin.median);
        document.getElementById('shugiin-max').textContent = formatAge(summary.shugiin.max);
    }

    if (summary.sangiin) {
        document.getElementById('sangiin-mean').textContent = formatAge(summary.sangiin.mean);
        document.getElementById('sangiin-median').textContent = formatAge(summary.sangiin.median);
        document.getElementById('sangiin-max').textContent = formatAge(summary.sangiin.max);
    }
}

function populatePartyFilter(parties) {
    const select = document.getElementById('filter-party');
    const partyNames = Object.keys(parties).sort();
    
    // 既存のオプション（すべて以外）をクリア
    select.innerHTML = '<option value="all">すべて</option>';
    
    partyNames.forEach(party => {
        const option = document.createElement('option');
        option.value = party;
        option.textContent = party;
        select.appendChild(option);
    });
}

function populateSchoolFilter(members) {
    const select = document.getElementById('filter-school');
    if (!select) return;
    
    const schoolCounts = {};
    members.forEach(m => {
        const s = m.school || '不明';
        schoolCounts[s] = (schoolCounts[s] || 0) + 1;
    });
    
    const schools = Object.keys(schoolCounts).sort((a, b) => {
        if (a === '不明') return 1;
        if (b === '不明') return -1;
        return schoolCounts[b] - schoolCounts[a] || a.localeCompare(b, 'ja');
    });

    select.innerHTML = '<option value="all">すべて (全校)</option>';
    schools.forEach(school => {
        const option = document.createElement('option');
        option.value = school;
        option.textContent = `${school} (${schoolCounts[school]}名)`;
        select.appendChild(option);
    });
}

function renderPartyTable(parties) {
    const tbody = document.querySelector('#party-table tbody');
    tbody.innerHTML = '';
    
    const partyArray = Object.keys(parties).map(key => ({
        name: key,
        ...parties[key]
    })).sort((a, b) => b.count - a.count);

    partyArray.forEach(party => {
        const tr = document.createElement('tr');
        tr.innerHTML = `
            <td>${party.name}</td>
            <td>${party.count}名</td>
            <td>${formatAge(party.mean)}</td>
            <td>${formatAge(party.median)}</td>
            <td>${formatAge(party.max)}</td>
        `;
        tbody.appendChild(tr);
    });
}

function handleTableSort(field) {
    if (currentSort.field === field) {
        currentSort.direction *= -1;
    } else {
        currentSort.field = field;
        currentSort.direction = (field === 'age' || field === 'elections') ? -1 : 1;
    }
    updateSortHeaders();
    renderMembersList();
}

function updateSortHeaders() {
    const idTh = document.getElementById('sort-id');
    const elecTh = document.getElementById('sort-elections');
    const ageTh = document.getElementById('sort-age');
    const bpTh = document.getElementById('sort-birthplace');
    const schTh = document.getElementById('sort-school');

    if (idTh) idTh.textContent = `ID ${currentSort.field === 'id' ? (currentSort.direction === 1 ? '▲' : '▼') : ''}`;
    if (elecTh) elecTh.textContent = `当選回数 ${currentSort.field === 'elections' ? (currentSort.direction === -1 ? '▼' : '▲') : ''}`;
    if (ageTh) ageTh.textContent = `年齢 ${currentSort.field === 'age' ? (currentSort.direction === -1 ? '▼' : '▲') : ''}`;
    if (bpTh) bpTh.textContent = `出身地 ${currentSort.field === 'birthplace' ? (currentSort.direction === 1 ? '▲' : '▼') : ''}`;
    if (schTh) schTh.textContent = `出身校 ${currentSort.field === 'school' ? (currentSort.direction === 1 ? '▲' : '▼') : ''}`;
}

function renderMembersList() {
    const houseFilter = document.getElementById('filter-house').value;
    const partyFilter = document.getElementById('filter-party').value;
    const schoolFilter = document.getElementById('filter-school') ? document.getElementById('filter-school').value : 'all';
    
    let filtered = globalData.members.filter(m => {
        const matchHouse = houseFilter === 'all' || m.house === houseFilter;
        const matchParty = partyFilter === 'all' || m.party === partyFilter;
        const matchSchool = schoolFilter === 'all' || (m.school || '不明') === schoolFilter;
        return matchHouse && matchParty && matchSchool;
    });

    filtered.sort((a, b) => {
        if (currentSort.field === 'age') {
            if (a.age === null && b.age === null) return 0;
            if (a.age === null) return 1;
            if (b.age === null) return -1;
            return (a.age - b.age) * currentSort.direction;
        } else if (currentSort.field === 'elections') {
            const elA = a.elections || 0;
            const elB = b.elections || 0;
            if (elA !== elB) {
                return (elA - elB) * currentSort.direction;
            }
            return (a.id || '').localeCompare(b.id || '') * currentSort.direction;
        } else if (currentSort.field === 'birthplace') {
            const orderA = PREFECTURE_ORDER.indexOf(a.birthplace || '不明');
            const orderB = PREFECTURE_ORDER.indexOf(b.birthplace || '不明');
            const idxA = orderA !== -1 ? orderA : 999;
            const idxB = orderB !== -1 ? orderB : 999;
            if (idxA !== idxB) {
                return (idxA - idxB) * currentSort.direction;
            }
            return (a.id || '').localeCompare(b.id || '') * currentSort.direction;
        } else if (currentSort.field === 'school') {
            const sA = a.school || '不明';
            const sB = b.school || '不明';
            if (sA !== sB) {
                return sA.localeCompare(sB, 'ja') * currentSort.direction;
            }
            return (a.id || '').localeCompare(b.id || '') * currentSort.direction;
        } else {
            return (a.id || '').localeCompare(b.id || '') * currentSort.direction;
        }
    });

    const tbody = document.querySelector('#members-table tbody');
    tbody.innerHTML = '';

    filtered.forEach(m => {
        const tr = document.createElement('tr');
        const nameCell = m.profile_url 
            ? `<a href="${m.profile_url}" target="_blank" rel="noopener noreferrer" class="profile-link" title="公式プロフィールページを開く">${m.name} 🔗</a>`
            : m.name;
        const elecDisplay = m.elections !== undefined && m.elections !== null ? `${m.elections}回` : '-';
        tr.innerHTML = `
            <td>${m.id || '-'}</td>
            <td>${nameCell}</td>
            <td>${m.house}</td>
            <td>${m.party}</td>
            <td>${elecDisplay}</td>
            <td>${m.birthdate || '-'}</td>
            <td>${formatAge(m.age)}</td>
            <td>${m.birthplace || '-'}</td>
            <td>${m.school || '-'}</td>
            <td>${m.faculty || '-'}</td>
        `;
        tbody.appendChild(tr);
    });

    document.getElementById('pagination-info').textContent = `表示件数: ${filtered.length}件`;
}

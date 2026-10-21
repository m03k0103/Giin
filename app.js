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
    document.getElementById('filter-gender').addEventListener('change', renderMembersList);
    document.getElementById('filter-birthplace').addEventListener('change', renderMembersList);
    document.getElementById('filter-school').addEventListener('change', renderMembersList);
    
    document.getElementById('sort-id').addEventListener('click', () => handleTableSort('id'));
    document.getElementById('sort-name').addEventListener('click', () => handleTableSort('name'));
    document.getElementById('sort-party').addEventListener('click', () => handleTableSort('party'));
    document.getElementById('sort-elections').addEventListener('click', () => handleTableSort('elections'));
    document.getElementById('sort-age').addEventListener('click', () => handleTableSort('age'));
    document.getElementById('sort-gender').addEventListener('click', () => handleTableSort('gender'));
    document.getElementById('sort-birthplace').addEventListener('click', () => handleTableSort('birthplace'));
    document.getElementById('sort-school').addEventListener('click', () => handleTableSort('school'));
    document.getElementById('sort-faculty').addEventListener('click', () => handleTableSort('faculty'));

    document.getElementById('birthplace-house-filter').addEventListener('change', renderBirthplaceChart);
    document.getElementById('birthplace-sort').addEventListener('change', renderBirthplaceChart);
    document.getElementById('birthplace-display-mode').addEventListener('change', renderBirthplaceChart);
    document.getElementById('generation-house-filter').addEventListener('change', renderGenerationChart);
    document.getElementById('generation-gender-mode').addEventListener('change', renderGenerationChart);
    document.getElementById('generation-sort').addEventListener('change', renderGenerationChart);
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
    
    const femaleCount = filtered.filter(m => m.gender === '女性').length;
    const femaleRatio = filtered.length > 0 ? Math.round((femaleCount / filtered.length) * 1000) / 10 : 0;

    return {
        mean: mean,
        median: median,
        max: ages[ages.length - 1],
        count: filtered.length,
        femaleCount: femaleCount,
        femaleRatio: femaleRatio
    };
}

async function fetchData() {
    try {
        let data = null;
        
        // data.js により定義されたグローバル変数（window.DIET_DATA）を利用
        if (typeof window.DIET_DATA !== 'undefined' && window.DIET_DATA && window.DIET_DATA.members) {
            data = window.DIET_DATA;
        } else if (typeof window.membersData !== 'undefined' && window.membersData && window.membersData.members) {
            data = window.membersData;
        } else if (typeof membersData !== 'undefined' && membersData && membersData.members) {
            data = membersData;
        } else {
            throw new Error("議員データ（window.DIET_DATA）が見つかりません。data.js が正しく読み込まれているか確認してください。");
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
        populateBirthplaceFilter(enrichedMembers);
        populateSchoolFilter(enrichedMembers);
        renderPartyTable(globalData.parties);
        renderBirthplaceChart();
        renderGenerationChart();
        
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

const GENERATION_KEYS = ['20代', '30代', '40代', '50代', '60代', '70代', '80代'];

/**
 * 年代別データ（棒グラフ）の描画
 */
function renderGenerationChart() {
    const houseFilter = document.getElementById('generation-house-filter').value;
    const genderMode = document.getElementById('generation-gender-mode').value;
    const sortMode = document.getElementById('generation-sort').value;
    const legendEl = document.getElementById('generation-legend');

    if (genderMode === 'color') {
        legendEl.style.display = 'flex';
    } else {
        legendEl.style.display = 'none';
    }

    const filteredMembers = globalData.members.filter(m => {
        return houseFilter === 'all' || m.house === houseFilter;
    });

    const totalCount = filteredMembers.length;
    const container = document.getElementById('generation-chart');
    const summaryEl = document.getElementById('generation-chart-summary');

    if (totalCount === 0) {
        container.innerHTML = '<div style="padding: 20px; text-align: center; color: var(--text-secondary);">該当するデータがありません。</div>';
        summaryEl.textContent = '';
        return;
    }

    // 集計初期化
    const genMap = {};
    GENERATION_KEYS.forEach(g => {
        genMap[g] = { name: g, total: 0, male: 0, female: 0 };
    });
    let others = { name: 'その他・不明', total: 0, male: 0, female: 0 };

    filteredMembers.forEach(m => {
        let key = null;
        if (m.age !== null && m.age !== undefined) {
            if (m.age >= 20 && m.age < 30) key = '20代';
            else if (m.age >= 30 && m.age < 40) key = '30代';
            else if (m.age >= 40 && m.age < 50) key = '40代';
            else if (m.age >= 50 && m.age < 60) key = '50代';
            else if (m.age >= 60 && m.age < 70) key = '60代';
            else if (m.age >= 70 && m.age < 80) key = '70代';
            else if (m.age >= 80 && m.age < 90) key = '80代';
            else if (m.age >= 90) key = '90代以上';
        }

        const target = key ? (genMap[key] || (genMap[key] = { name: key, total: 0, male: 0, female: 0 })) : others;
        target.total++;
        if (m.gender === '女性') {
            target.female++;
        } else {
            target.male++;
        }
    });

    let chartData = GENERATION_KEYS.map(g => genMap[g]);
    if (others.total > 0) {
        chartData.push(others);
    }

    // ソート処理
    if (sortMode === 'age_desc') {
        chartData.reverse();
    } else if (sortMode === 'count_desc') {
        chartData.sort((a, b) => b.total - a.total);
    } else if (sortMode === 'count_asc') {
        chartData.sort((a, b) => a.total - b.total);
    } else if (sortMode === 'female_desc') {
        chartData.sort((a, b) => {
            const ratioA = a.total > 0 ? (a.female / a.total) : -1;
            const ratioB = b.total > 0 ? (b.female / b.total) : -1;
            return ratioB - ratioA || b.total - a.total;
        });
    } else if (sortMode === 'female_asc') {
        chartData.sort((a, b) => {
            const ratioA = a.total > 0 ? (a.female / a.total) : 999;
            const ratioB = b.total > 0 ? (b.female / b.total) : 999;
            return ratioA - ratioB || a.total - b.total;
        });
    } // 'age_asc' の場合は GENERATION_KEYS 順のまま

    const maxCount = Math.max(...chartData.map(d => d.total), 1);
    container.innerHTML = '';

    chartData.forEach(item => {
        const row = document.createElement('div');
        row.className = 'bar-row';

        const percentage = totalCount > 0 ? ((item.total / totalCount) * 100).toFixed(1) : '0.0';
        const femaleRatio = item.total > 0 ? ((item.female / item.total) * 100).toFixed(1) : null;
        const femaleRatioDisplay = femaleRatio !== null ? `${femaleRatio}%` : '-';
        const femaleBadgeHtml = `<span class="bar-female-badge" title="${item.name}の女性比率: ${femaleRatioDisplay}">女性比率 ${femaleRatioDisplay}</span>`;

        let trackHtml = '';
        let valueHtml = '';

        if (genderMode === 'color') {
            const maleWidth = maxCount > 0 ? ((item.male / maxCount) * 100).toFixed(1) : '0';
            const femaleWidth = maxCount > 0 ? ((item.female / maxCount) * 100).toFixed(1) : '0';

            trackHtml = `
                <div class="bar-track stacked" title="${item.name}: 全体 ${item.total}名 (男性 ${item.male}名, 女性 ${item.female}名 / 女性比率 ${femaleRatioDisplay})">
                    ${item.male > 0 ? `<div class="bar-fill male" style="width: ${maleWidth}%;" title="男性: ${item.male}名"></div>` : ''}
                    ${item.female > 0 ? `<div class="bar-fill female" style="width: ${femaleWidth}%;" title="女性: ${item.female}名"></div>` : ''}
                </div>
            `;
            valueHtml = `
                <div class="bar-value">
                    <span class="bar-count">${item.total}名</span>
                    <span class="bar-percentage">(${percentage}%)</span>
                    <span class="bar-gender-detail">(男:${item.male} 女:${item.female})</span>
                    ${femaleBadgeHtml}
                </div>
            `;
        } else {
            const totalWidth = maxCount > 0 ? ((item.total / maxCount) * 100).toFixed(1) : '0';
            trackHtml = `
                <div class="bar-track" title="${item.name}: ${item.total}名 (${percentage}%) / 女性比率: ${femaleRatioDisplay}">
                    <div class="bar-fill" style="width: ${totalWidth}%;"></div>
                </div>
            `;
            valueHtml = `
                <div class="bar-value">
                    <span class="bar-count">${item.total}名</span>
                    <span class="bar-percentage">(${percentage}%)</span>
                    ${femaleBadgeHtml}
                </div>
            `;
        }

        row.innerHTML = `
            <div class="bar-label">${item.name}</div>
            ${trackHtml}
            ${valueHtml}
        `;
        container.appendChild(row);
    });

    // サマリー生成
    const houseLabel = houseFilter === 'all' ? '全体 (衆参両院)' : houseFilter;
    const sortedByCount = [...chartData].sort((a, b) => b.total - a.total);
    const topGen = sortedByCount[0];
    const topGenText = topGen && topGen.total > 0 ? `最多年代: ${topGen.name}（${topGen.total}名, ${((topGen.total / totalCount) * 100).toFixed(1)}%）` : '';

    const validGens = chartData.filter(d => d.total > 0);
    const topFemaleGen = [...validGens].sort((a, b) => (b.female / b.total) - (a.female / a.total))[0];
    const topFemaleText = topFemaleGen && topFemaleGen.female > 0 
        ? ` / 女性比率最高: ${topFemaleGen.name}（${((topFemaleGen.female / topFemaleGen.total) * 100).toFixed(1)}%, ${topFemaleGen.female}名）` 
        : '';

    summaryEl.textContent = `集計対象: ${houseLabel}（計${totalCount}名） / ${topGenText}${topFemaleText}`;
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
        const shugFem = document.getElementById('shugiin-female');
        if (shugFem) shugFem.textContent = `${summary.shugiin.femaleCount}名 (${summary.shugiin.femaleRatio}%)`;
    }

    if (summary.sangiin) {
        document.getElementById('sangiin-mean').textContent = formatAge(summary.sangiin.mean);
        document.getElementById('sangiin-median').textContent = formatAge(summary.sangiin.median);
        document.getElementById('sangiin-max').textContent = formatAge(summary.sangiin.max);
        const sangFem = document.getElementById('sangiin-female');
        if (sangFem) sangFem.textContent = `${summary.sangiin.femaleCount}名 (${summary.sangiin.femaleRatio}%)`;
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

function populateBirthplaceFilter(members) {
    const select = document.getElementById('filter-birthplace');
    if (!select) return;

    const bpCounts = {};
    members.forEach(m => {
        const bp = m.birthplace || '不明';
        bpCounts[bp] = (bpCounts[bp] || 0) + 1;
    });

    select.innerHTML = '<option value="all">すべて (全都道府県)</option>';
    
    // PREFECTURE_ORDER に基づき地域順（北海道〜沖縄・外国・不明）で追加
    const added = new Set();
    PREFECTURE_ORDER.forEach(bp => {
        const count = bpCounts[bp] || 0;
        if (count > 0) {
            const option = document.createElement('option');
            option.value = bp;
            option.textContent = `${bp} (${count}名)`;
            select.appendChild(option);
            added.add(bp);
        }
    });

    // 既存定義外の地域があれば末尾に追加
    Object.keys(bpCounts).forEach(bp => {
        if (!added.has(bp) && bpCounts[bp] > 0) {
            const option = document.createElement('option');
            option.value = bp;
            option.textContent = `${bp} (${bpCounts[bp]}名)`;
            select.appendChild(option);
        }
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
    const nameTh = document.getElementById('sort-name');
    const partyTh = document.getElementById('sort-party');
    const elecTh = document.getElementById('sort-elections');
    const ageTh = document.getElementById('sort-age');
    const genderTh = document.getElementById('sort-gender');
    const bpTh = document.getElementById('sort-birthplace');
    const schTh = document.getElementById('sort-school');
    const facTh = document.getElementById('sort-faculty');

    if (idTh) idTh.textContent = `ID ${currentSort.field === 'id' ? (currentSort.direction === 1 ? '▲' : '▼') : ''}`;
    if (nameTh) nameTh.textContent = `氏名 ${currentSort.field === 'name' ? (currentSort.direction === 1 ? '▲' : '▼') : ''}`;
    if (partyTh) partyTh.textContent = `会派 ${currentSort.field === 'party' ? (currentSort.direction === 1 ? '▲' : '▼') : ''}`;
    if (elecTh) elecTh.textContent = `当選回数 ${currentSort.field === 'elections' ? (currentSort.direction === -1 ? '▼' : '▲') : ''}`;
    if (ageTh) ageTh.textContent = `年齢 ${currentSort.field === 'age' ? (currentSort.direction === -1 ? '▼' : '▲') : ''}`;
    if (genderTh) genderTh.textContent = `性別 ${currentSort.field === 'gender' ? (currentSort.direction === 1 ? '▲' : '▼') : ''}`;
    if (bpTh) bpTh.textContent = `出身地 ${currentSort.field === 'birthplace' ? (currentSort.direction === 1 ? '▲' : '▼') : ''}`;
    if (schTh) schTh.textContent = `出身校 ${currentSort.field === 'school' ? (currentSort.direction === 1 ? '▲' : '▼') : ''}`;
    if (facTh) facTh.textContent = `学部名 ${currentSort.field === 'faculty' ? (currentSort.direction === 1 ? '▲' : '▼') : ''}`;
}

function renderMembersList() {
    const houseFilter = document.getElementById('filter-house').value;
    const genderFilter = document.getElementById('filter-gender') ? document.getElementById('filter-gender').value : 'all';
    const partyFilter = document.getElementById('filter-party').value;
    const birthplaceFilter = document.getElementById('filter-birthplace') ? document.getElementById('filter-birthplace').value : 'all';
    const schoolFilter = document.getElementById('filter-school') ? document.getElementById('filter-school').value : 'all';
    
    let filtered = globalData.members.filter(m => {
        const matchHouse = houseFilter === 'all' || m.house === houseFilter;
        const matchGender = genderFilter === 'all' || m.gender === genderFilter;
        const matchParty = partyFilter === 'all' || m.party === partyFilter;
        const matchBirthplace = birthplaceFilter === 'all' || (m.birthplace || '不明') === birthplaceFilter;
        const matchSchool = schoolFilter === 'all' || (m.school || '不明') === schoolFilter;
        return matchHouse && matchGender && matchParty && matchBirthplace && matchSchool;
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
        } else if (currentSort.field === 'gender') {
            const gA = a.gender || '';
            const gB = b.gender || '';
            if (gA !== gB) {
                return gA.localeCompare(gB, 'ja') * currentSort.direction;
            }
            return (a.id || '').localeCompare(b.id || '') * currentSort.direction;
        } else if (currentSort.field === 'school') {
            const sA = a.school || '不明';
            const sB = b.school || '不明';
            if (sA !== sB) {
                return sA.localeCompare(sB, 'ja') * currentSort.direction;
            }
            return (a.id || '').localeCompare(b.id || '') * currentSort.direction;
        } else if (currentSort.field === 'name') {
            const nA = a.name || '';
            const nB = b.name || '';
            if (nA !== nB) {
                return nA.localeCompare(nB, 'ja') * currentSort.direction;
            }
            return (a.id || '').localeCompare(b.id || '') * currentSort.direction;
        } else if (currentSort.field === 'party') {
            const pA = a.party || '';
            const pB = b.party || '';
            if (pA !== pB) {
                return pA.localeCompare(pB, 'ja') * currentSort.direction;
            }
            return (a.id || '').localeCompare(b.id || '') * currentSort.direction;
        } else if (currentSort.field === 'faculty') {
            const fA = a.faculty || '-';
            const fB = b.faculty || '-';
            const isEmpA = fA === '-' || fA === 'N/A' || fA === '';
            const isEmpB = fB === '-' || fB === 'N/A' || fB === '';
            if (isEmpA && isEmpB) {
                return (a.id || '').localeCompare(b.id || '') * currentSort.direction;
            }
            if (isEmpA) return 1;
            if (isEmpB) return -1;
            if (fA !== fB) {
                return fA.localeCompare(fB, 'ja') * currentSort.direction;
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

        const secFields = m.secondary_fields || (m.secondary_source === 'wikipedia' ? ['birthplace'] : []);
        const isWikiBdateFull = secFields.includes('birthdate');
        const isWikiBdateDay = secFields.includes('birthdate_day');
        const isWikiBdateMonthDay = secFields.includes('birthdate_month_day');
        const isWikiBplace = secFields.includes('birthplace');
        const isWikiSchool = secFields.includes('school');

        let bdateDisplay = m.birthdate || '-';
        if (m.birthdate) {
            if (isWikiBdateDay) {
                // 日のみ補完: YYYY年M月 は通常色、D日 のみ青色
                const match = m.birthdate.match(/^(\d+年\d+月)(\d+日)$/);
                if (match) {
                    bdateDisplay = `${match[1]}<span class="source-wiki" title="日をWikipediaより補完">${match[2]}</span>`;
                }
            } else if (isWikiBdateMonthDay) {
                // 月日を補完: YYYY年 は通常色、M月D日 のみ青色
                const match = m.birthdate.match(/^(\d+年)(\d+月\d+日)$/);
                if (match) {
                    bdateDisplay = `${match[1]}<span class="source-wiki" title="月日をWikipediaより補完">${match[2]}</span>`;
                }
            } else if (isWikiBdateFull) {
                // 公式に生年月日未記載で全量補完: 生年は通常色、月日のみ青色
                const match = m.birthdate.match(/^(\d+年)(.*)$/);
                if (match) {
                    bdateDisplay = `${match[1]}<span class="source-wiki" title="月日をWikipediaより補完">${match[2]}</span>`;
                } else {
                    bdateDisplay = `<span class="source-wiki" title="Wikipediaより補完">${m.birthdate}</span>`;
                }
            }
        }

        // 年齢（生年に基づくため通常色を維持）
        const ageDisplay = formatAge(m.age);

        const bplaceText = m.birthplace || '-';
        const bplaceDisplay = isWikiBplace 
            ? `<span class="source-wiki" title="Wikipedia（二次情報源）より取得">${bplaceText}</span>` 
            : bplaceText;

        const schoolText = m.school || '-';
        const schoolDisplay = isWikiSchool 
            ? `<span class="source-wiki" title="Wikipedia（二次情報源）より取得">${schoolText}</span>` 
            : schoolText;

        const facultyText = m.faculty || '-';
        const facultyDisplay = (isWikiSchool && m.faculty && m.faculty !== '-' && m.faculty !== 'N/A')
            ? `<span class="source-wiki" title="Wikipedia（二次情報源）より取得">${facultyText}</span>` 
            : facultyText;

        const isWikiGender = secFields.includes('gender');
        const genderText = m.gender || '-';
        const genderDisplay = isWikiGender 
            ? `<span class="source-wiki" title="Wikipedia（二次情報源）より取得">${genderText}</span>` 
            : genderText;

        tr.innerHTML = `
            <td>${m.id || '-'}</td>
            <td>${nameCell}</td>
            <td>${m.house}</td>
            <td>${m.party}</td>
            <td>${elecDisplay}</td>
            <td>${bdateDisplay}</td>
            <td>${ageDisplay}</td>
            <td>${genderDisplay}</td>
            <td>${bplaceDisplay}</td>
            <td>${schoolDisplay}</td>
            <td>${facultyDisplay}</td>
        `;
        tbody.appendChild(tr);
    });

    document.getElementById('pagination-info').textContent = `表示件数: ${filtered.length}件`;
}

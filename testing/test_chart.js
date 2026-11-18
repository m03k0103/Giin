const fs = require('fs');

// 簡易DOMモック
class ElementMock {
    constructor(id = '', tagName = 'div') {
        this.id = id;
        this.tagName = tagName;
        this.value = 'all';
        this._innerHTML = '';
        this.textContent = '';
        this.style = {};
        this.className = '';
        this.children = [];
        this.listeners = {};
    }

    get innerHTML() {
        return this._innerHTML;
    }

    set innerHTML(val) {
        this._innerHTML = val;
        if (val === '') {
            this.children = [];
        }
    }

    addEventListener(event, fn) {
        if (!this.listeners[event]) this.listeners[event] = [];
        this.listeners[event].push(fn);
    }

    trigger(event) {
        if (this.listeners[event]) {
            this.listeners[event].forEach(fn => fn());
        }
    }

    appendChild(child) {
        if (child.tagName === 'fragment') {
            this.children.push(...child.children);
            child.children = [];
        } else {
            this.children.push(child);
        }
    }
}

const elements = {};
function getElement(id) {
    if (!elements[id]) {
        elements[id] = new ElementMock(id);
    }
    return elements[id];
}

const domContentLoadedCallbacks = [];

const globalMock = {
    document: {
        getElementById: (id) => getElement(id),
        querySelector: (sel) => new ElementMock(),
        querySelectorAll: (sel) => [],
        createElement: (tag) => new ElementMock('', tag),
        createDocumentFragment: () => new ElementMock('', 'fragment'),
        addEventListener: (event, fn) => {
            if (event === 'DOMContentLoaded') {
                domContentLoadedCallbacks.push(fn);
            }
        }
    },
    window: {},
    console: console
};

// data.js をロード
const dataJs = fs.readFileSync('data.js', 'utf8');
eval(dataJs.replace('window.DIET_DATA', 'globalMock.window.DIET_DATA'));

// app.js をコンテキスト内で実行
const appJs = fs.readFileSync('app.js', 'utf8');

const vm = require('vm');
const context = vm.createContext({
    ...globalMock,
    window: globalMock.window,
    document: globalMock.document
});

// app.js パース・実行
vm.runInContext(appJs, context);

// DOMContentLoaded 発火
domContentLoadedCallbacks.forEach(fn => fn());

// 初期値セット
getElement('generation-house-filter').value = 'all';
getElement('generation-gender-mode').value = 'color';
getElement('generation-sort').value = 'age_asc';

// fetchData を実行
context.fetchData().then(() => {
    console.log('fetchData completed successfully!');

    // 初期状態のチェック（全体、colorモード、age_asc）
    const chart = getElement('generation-chart');
    const summary = getElement('generation-chart-summary');
    const legend = getElement('generation-legend');

    console.log('Legend display:', legend.style.display);
    console.log('Summary:', summary.textContent);
    console.log('Chart rows count:', chart.children.length);

    if (chart.children.length !== 7) {
        throw new Error(`Expected 7 rows (20代〜80代), got ${chart.children.length}`);
    }

    // 各年代の行内容チェック
    chart.children.forEach(row => {
        console.log(`Row: ${row.innerHTML.replace(/\s+/g, ' ').trim()}`);
    });

    // 1. 性別色分けなし（mono）モードテスト
    console.log('\n--- Testing Mono Mode ---');
    getElement('generation-gender-mode').value = 'mono';
    context.renderGenerationChart();
    console.log('Legend display:', legend.style.display);
    chart.children.forEach(row => {
        console.log(`Mono Row: ${row.innerHTML.replace(/\s+/g, ' ').trim()}`);
    });
    if (legend.style.display !== 'none') {
        throw new Error('Legend should be none in mono mode');
    }

    // 2. 議院切り替え（衆議院）テスト
    console.log('\n--- Testing House Filter: 衆議院 ---');
    getElement('generation-house-filter').value = '衆議院';
    getElement('generation-gender-mode').value = 'color';
    context.renderGenerationChart();
    console.log('Summary:', summary.textContent);
    chart.children.forEach(row => {
        console.log(`Shugiin Row: ${row.innerHTML.replace(/\s+/g, ' ').trim()}`);
    });

    // 3. 議院切り替え（参議院）テスト
    console.log('\n--- Testing House Filter: 参議院 ---');
    getElement('generation-house-filter').value = '参議院';
    context.renderGenerationChart();
    console.log('Summary:', summary.textContent);
    chart.children.forEach(row => {
        console.log(`Sangiin Row: ${row.innerHTML.replace(/\s+/g, ' ').trim()}`);
    });

    // 4. ソートテスト: 人数降順 (count_desc)
    console.log('\n--- Testing Sort: count_desc ---');
    getElement('generation-house-filter').value = 'all';
    getElement('generation-sort').value = 'count_desc';
    context.renderGenerationChart();
    console.log('Sorted rows (count_desc):');
    chart.children.forEach(row => {
        const match = row.innerHTML.match(/bar-label">(.*?)<\/div>/);
        const countMatch = row.innerHTML.match(/<span>(\d+)名<\/span>/);
        console.log(`  ${match ? match[1] : '?'}: ${countMatch ? countMatch[1] : '?'}名`);
    });

    // 5. ソートテスト: 年代高い順 (age_desc)
    console.log('\n--- Testing Sort: age_desc ---');
    getElement('generation-sort').value = 'age_desc';
    context.renderGenerationChart();
    console.log('Sorted rows (age_desc):');
    chart.children.forEach(row => {
        const match = row.innerHTML.match(/bar-label">(.*?)<\/div>/);
        console.log(`  ${match ? match[1] : '?'}`);
    });

    console.log('\nALL TESTS PASSED SUCCESSFULLY!');
}).catch(err => {
    console.error('Test failed:', err);
    process.exit(1);
});

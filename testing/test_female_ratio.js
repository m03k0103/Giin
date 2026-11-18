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

    const chart = getElement('generation-chart');
    const summary = getElement('generation-chart-summary');

    console.log('Summary:', summary.textContent);

    // 各年代の行内容チェック（女性比率バッジが含まれているか）
    console.log('\n--- Checking Color Mode Rows with Female Badge ---');
    chart.children.forEach(row => {
        console.log(`Row: ${row.innerHTML.replace(/\s+/g, ' ').trim()}`);
        if (!row.innerHTML.includes('bar-female-badge')) {
            throw new Error('bar-female-badge missing from row');
        }
    });

    // 1. 性別色分けなし（mono）モードテスト（バッジが含まれているか）
    console.log('\n--- Testing Mono Mode with Female Badge ---');
    getElement('generation-gender-mode').value = 'mono';
    context.renderGenerationChart();
    chart.children.forEach(row => {
        console.log(`Mono Row: ${row.innerHTML.replace(/\s+/g, ' ').trim()}`);
        if (!row.innerHTML.includes('bar-female-badge')) {
            throw new Error('bar-female-badge missing from mono row');
        }
    });

    // 2. 女性比率が高い順（female_desc）ソートテスト
    console.log('\n--- Testing Sort: female_desc ---');
    getElement('generation-sort').value = 'female_desc';
    context.renderGenerationChart();
    console.log('Sorted rows (female_desc):');
    chart.children.forEach(row => {
        const labelMatch = row.innerHTML.match(/bar-label">(.*?)<\/div>/);
        const badgeMatch = row.innerHTML.match(/bar-female-badge[^>]*>(.*?)<\/span>/);
        console.log(`  ${labelMatch ? labelMatch[1] : '?'}: ${badgeMatch ? badgeMatch[1] : '?'}`);
    });

    // 3. 参議院での女性比率が高い順テスト
    console.log('\n--- Testing Sangiin female_desc ---');
    getElement('generation-house-filter').value = '参議院';
    getElement('generation-sort').value = 'female_desc';
    context.renderGenerationChart();
    console.log('Sangiin Sorted rows (female_desc):');
    chart.children.forEach(row => {
        const labelMatch = row.innerHTML.match(/bar-label">(.*?)<\/div>/);
        const badgeMatch = row.innerHTML.match(/bar-female-badge[^>]*>(.*?)<\/span>/);
        console.log(`  ${labelMatch ? labelMatch[1] : '?'}: ${badgeMatch ? badgeMatch[1] : '?'}`);
    });

    console.log('\nALL FEMALE RATIO TESTS PASSED SUCCESSFULLY!');
}).catch(err => {
    console.error('Test failed:', err);
    process.exit(1);
});

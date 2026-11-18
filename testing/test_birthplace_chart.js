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
getElement('birthplace-house-filter').value = 'all';
getElement('birthplace-gender-mode').value = 'color';
getElement('birthplace-sort').value = 'count_desc';
getElement('birthplace-display-mode').value = 'top20';

// fetchData を実行
context.fetchData().then(() => {
    console.log('fetchData completed successfully!');

    const chart = getElement('birthplace-chart');
    const summary = getElement('birthplace-chart-summary');
    const legend = getElement('birthplace-legend');

    console.log('Summary:', summary.textContent);
    console.log('Legend display (color):', legend.style.display);
    if (legend.style.display !== 'flex') throw new Error('Legend should be flex');

    console.log('Top 5 rows (color mode):');
    chart.children.slice(0, 5).forEach(row => {
        console.log(`  ${row.innerHTML.replace(/\s+/g, ' ').trim()}`);
        if (!row.innerHTML.includes('bar-female-badge')) throw new Error('female badge missing');
        if (!row.innerHTML.includes('bar-fill male') && !row.innerHTML.includes('bar-fill female')) {
            throw new Error('stacked bar fill missing');
        }
    });

    // 1. mono モードテスト
    console.log('\n--- Testing Mono Mode ---');
    getElement('birthplace-gender-mode').value = 'mono';
    context.renderBirthplaceChart();
    console.log('Legend display (mono):', legend.style.display);
    if (legend.style.display !== 'none') throw new Error('Legend should be none in mono mode');
    console.log('Top 3 rows (mono mode):');
    chart.children.slice(0, 3).forEach(row => {
        console.log(`  ${row.innerHTML.replace(/\s+/g, ' ').trim()}`);
    });

    // 2. female_desc ソートテスト
    console.log('\n--- Testing female_desc sort ---');
    getElement('birthplace-gender-mode').value = 'color';
    getElement('birthplace-sort').value = 'female_desc';
    context.renderBirthplaceChart();
    console.log('Top 5 female ratio regions:');
    chart.children.slice(0, 5).forEach(row => {
        const label = row.innerHTML.match(/bar-label">(.*?)<\/div>/)[1];
        const badge = row.innerHTML.match(/bar-female-badge[^>]*>(.*?)<\/span>/)[1];
        const detail = row.innerHTML.match(/bar-gender-detail">(.*?)<\/span>/)[1];
        console.log(`  ${label}: ${badge} ${detail}`);
    });

    // 3. 参議院での地域フィルタテスト
    console.log('\n--- Testing House Filter: 参議院 ---');
    getElement('birthplace-house-filter').value = '参議院';
    context.renderBirthplaceChart();
    console.log('Sangiin Summary:', summary.textContent);

    console.log('\nALL BIRTHPLACE TESTS PASSED SUCCESSFULLY!');
}).catch(err => {
    console.error('Test failed:', err);
    process.exit(1);
});

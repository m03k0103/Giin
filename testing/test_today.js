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

getElement('generation-house-filter').value = 'all';
getElement('generation-gender-mode').value = 'color';
getElement('generation-sort').value = 'age_asc';

// fetchData を実行
context.fetchData().then(() => {
    console.log('fetchData completed successfully!');

    const header = getElement('last-updated-text');
    console.log('Header text:', header.textContent);

    const now = new Date();
    const expectedDate = `${now.getFullYear()}年${now.getMonth() + 1}月${now.getDate()}日時点`;
    if (!header.textContent.includes(expectedDate)) {
        throw new Error(`Expected header to include ${expectedDate}, got ${header.textContent}`);
    }

    const genSummary = getElement('generation-chart-summary');
    console.log('Generation summary:', genSummary.textContent);

    const chart = getElement('generation-chart');
    console.log('Generation chart rows:', chart.children.length);
    if (chart.children.length !== 7) throw new Error('Expected 7 rows');

    console.log('\nALL TESTS PASSED SUCCESSFULLY!');
}).catch(err => {
    console.error('Test failed:', err);
    process.exit(1);
});

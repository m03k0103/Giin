const fs = require('fs');
const vm = require('vm');

class ElementMock {
    constructor(id = '', tag = 'div') {
        this.id = id;
        this.tag = tag;
        this.children = [];
        this.attributes = {};
        this.value = 'all';
        this._innerHTML = '';
        this._textContent = '';
        this.style = {};
    }

    setAttribute(name, val) {
        this.attributes[name] = val;
    }

    getAttribute(name) {
        return this.attributes[name] || null;
    }

    appendChild(child) {
        if (child && child.tag === 'fragment') {
            while (child.children.length > 0) {
                this.children.push(child.children.shift());
            }
            return child;
        }
        this.children.push(child);
        return child;
    }

    get innerHTML() {
        return this._innerHTML;
    }

    set innerHTML(html) {
        this._innerHTML = html;
        this.children = [];
    }

    get textContent() {
        return this._textContent;
    }

    set textContent(text) {
        this._textContent = text;
        this._innerHTML = text;
    }

    addEventListener(event, fn) {}
}

const elements = {};
function getElement(id) {
    if (!elements[id]) {
        elements[id] = new ElementMock(id);
    }
    return elements[id];
}

const domContentLoadedCallbacks = [];

const docElement = new ElementMock('html', 'html');
const tbody = new ElementMock('tbody', 'members-tbody');
const partyTbody = new ElementMock('tbody', 'party-tbody');

const globalMock = {
    document: {
        documentElement: docElement,
        getElementById: (id) => getElement(id),
        querySelector: (sel) => {
            if (sel === '#members-table tbody') return tbody;
            if (sel === '#party-table tbody') return partyTbody;
            return new ElementMock();
        },
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
    console: console,
    Date: Date,
    Math: Math,
    parseInt: parseInt,
    parseFloat: parseFloat,
    String: String,
    Object: Object,
    Array: Array,
    Set: Set,
    RegExp: RegExp
};
globalMock.window = globalMock;

const context = vm.createContext(globalMock);

const dataJs = fs.readFileSync('data.js', 'utf8');
vm.runInContext(dataJs, context);

const appJs = fs.readFileSync('app.js', 'utf8');
vm.runInContext(appJs, context);

// DOMContentLoaded 発火
domContentLoadedCallbacks.forEach(fn => fn());

console.log('--- Checking Drop 22 Requirements ---');

// 1. Theme
const theme = docElement.getAttribute('data-theme');
console.log('1. Default theme on documentElement:', theme);
if (theme !== 'light') {
    throw new Error(`Expected default theme to be 'light', but got '${theme}'`);
}

// 2. Initial Sort
const curSort = vm.runInContext('currentSort', context);
console.log('2. currentSort state:', curSort);
if (curSort.field !== 'id' || curSort.direction !== 1) {
    throw new Error(`Expected currentSort { field: 'id', direction: 1 }, got: ${JSON.stringify(curSort)}`);
}
console.log('   ID sort header text:', getElement('sort-id').textContent);
if (!getElement('sort-id').textContent.includes('▲')) {
    throw new Error('ID sort header should contain ▲ indicator');
}

// 3. Status Bar Placement & Text
console.log('3. Pagination/Status text:', getElement('pagination-info').textContent);
if (!getElement('pagination-info').textContent.includes('712')) {
    throw new Error('Status bar should display member count');
}

// 4. BAN-02: 0-count options
console.log('4. Checking filter options (BAN-02):');
['filter-party', 'filter-birthplace', 'filter-school'].forEach(id => {
    const el = getElement(id);
    el.children.forEach(opt => {
        if (opt.textContent && opt.textContent.includes('(0名)')) {
            throw new Error(`Found 0-count option in ${id}: ${opt.textContent}`);
        }
    });
});
console.log('   All filter options have count > 0! (BAN-02 satisfied)');

// 5. Table Rows & escapeHtml (BAN-10)
console.log('5. Members table row count:', tbody.children.length);
if (tbody.children.length !== 712) {
    throw new Error(`Expected 712 rows, got ${tbody.children.length}`);
}

// Check first row ID
const firstRow = tbody.children[0];
console.log('   First row HTML sample:', firstRow.innerHTML.slice(0, 100));
if (!firstRow.innerHTML.includes('001')) {
    throw new Error('First row should have ID 001 under ascending ID sort');
}

console.log('\nALL DROP 22 UNIT CHECKS PASSED SUCCESSFULLY!');

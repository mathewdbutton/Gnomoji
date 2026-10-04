import {test, eq, done} from './assert.js';
import {placePicker, validCursor, GAP, CURSOR_MAX_AGE_MS} from '../../extension/placement.js';

// A 1080p screen under a 32 px top bar, a maximised target window, and the 380×420 picker.
const WA = {x: 0, y: 32, width: 1920, height: 1048};
const FRAME = {x: 0, y: 32, width: 1920, height: 1048};
const SIZE = {width: 380, height: 420};
const NOW = 10000;

const cursor = (x, y, over = {}) => ({rect: {x, y, width: 0, height: 22}, frame: FRAME, atMs: NOW, ...over});
const place = over => placePicker({cursorAt: null, nowMs: NOW, size: SIZE, dragged: null, workAreaFor: () => WA, ...over});
const at = (pos, x, y) => {
    eq(pos === null, false, 'position');
    eq(pos.x, x, 'x');
    eq(pos.y, y, 'y');
};

test('constants', () => {
    eq(GAP, 4);
    eq(CURSOR_MAX_AGE_MS, 2000);
});

test('middle: left edge at the cursor, just below its line (a zero-width cursor is fine)', () =>
    at(place({cursorAt: cursor(500, 300)}), 500, 326));

test('right edge: slides left to fit, still below', () =>
    at(place({cursorAt: cursor(1800, 300)}), 1540, 326));

test('bottom edge: opens above the line instead', () =>
    at(place({cursorAt: cursor(500, 900)}), 500, 476));

test('bottom-right corner: slides left and opens above', () =>
    at(place({cursorAt: cursor(1800, 900)}), 1540, 476));

test('left edge: pushed back on screen', () => {
    const frame = {x: -200, y: 100, width: 800, height: 600};
    at(place({cursorAt: {rect: {x: -150, y: 200, width: 0, height: 22}, frame, atMs: NOW}}), 0, 226);
});

test('top edge: pushed below the top bar', () => {
    const frame = {x: 100, y: 0, width: 800, height: 600};
    at(place({cursorAt: {rect: {x: 200, y: 5, width: 0, height: 10}, frame, atMs: NOW}}), 200, 32);
});

test('screen too short for above or below: kept inside the work area', () => {
    const short = {x: 0, y: 32, width: 1920, height: 500};
    at(place({cursorAt: cursor(500, 250), workAreaFor: () => short}), 500, 32);
});

test('picker bigger than the work area: top-left of the work area', () =>
    at(place({cursorAt: cursor(500, 300), size: {width: 2000, height: 1200}}), 0, 32));

test('second monitor: placed in that monitor\'s work area', () => {
    const wa2 = {x: 1920, y: 0, width: 2560, height: 1440};
    const frame = {x: 1920, y: 0, width: 2560, height: 1440};
    const workAreaFor = r => (r.x >= 1920 ? wa2 : WA);
    at(place({cursorAt: {rect: {x: 4300, y: 200, width: 0, height: 22}, frame, atMs: NOW}, workAreaFor}), 4100, 226);
});

test('asks for the work area of the cursor\'s monitor', () => {
    const seen = [];
    place({cursorAt: cursor(500, 300), workAreaFor: r => { seen.push(r); return WA; }});
    eq(seen.length, 1);
    eq(seen[0].x, 500);
    eq(seen[0].y, 300);
});

test('fractional numbers are rounded to whole pixels', () => {
    const c = {rect: {x: 500.6, y: 300.2, width: 0, height: 22.5}, frame: FRAME, atMs: NOW};
    at(place({cursorAt: c}), 501, 327);
});

test('a cursor exactly CURSOR_MAX_AGE_MS old is still used', () =>
    at(place({cursorAt: cursor(500, 300, {atMs: NOW - 2000})}), 500, 326));

const DRAGGED = {x: 700, y: 200};

test('a cursor older than that falls back to the dragged spot', () =>
    at(place({cursorAt: cursor(500, 300, {atMs: NOW - 2001}), dragged: DRAGGED}), 700, 200));

test('a cursor outside the target window (stale, from another app) falls back', () => {
    const frame = {x: 562, y: 263, width: 1440, height: 859};
    at(place({cursorAt: {rect: {x: 616, y: 43, width: 0, height: 18}, frame, atMs: NOW}, dragged: DRAGGED}), 700, 200);
});

test('a missing target frame falls back', () =>
    at(place({cursorAt: cursor(500, 300, {frame: null}), dragged: DRAGGED}), 700, 200));

for (const [name, rect] of [
    ['null', null],
    ['undefined', undefined],
    ['NaN', {x: NaN, y: 300, width: 0, height: 22}],
    ['Infinity', {x: 500, y: Infinity, width: 0, height: 22}],
    ['zero height', {x: 500, y: 300, width: 0, height: 0}],
    ['negative width', {x: 500, y: 300, width: -1, height: 22}],
    ['strings', {x: '500', y: '300', width: '0', height: '22'}],
]) {
    test(`an invalid cursor rect (${name}) falls back`, () => {
        eq(validCursor(rect), false);
        at(place({cursorAt: {rect, frame: FRAME, atMs: NOW}, dragged: DRAGGED}), 700, 200);
    });
}

test('no cursor: the dragged spot', () =>
    at(place({dragged: DRAGGED}), 700, 200));

test('a dragged spot off every monitor is pulled into the work area it\'s given', () => {
    const seen = [];
    at(place({dragged: {x: 5000, y: 3000}, workAreaFor: r => { seen.push(r); return WA; }}), 1540, 660);
    eq(seen[0].width, 380);
    eq(seen[0].height, 420);
});

test('nothing usable: null (leave it where GNOME put it)', () => {
    eq(place({}), null);
    eq(place({cursorAt: cursor(500, 300, {atMs: 0})}), null);
});

done();

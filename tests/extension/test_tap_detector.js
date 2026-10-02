import {test, eq, done} from './assert.js';
import {TapDetector, DOUBLE_TAP_MS, MIN_DOUBLE_TAP_MS} from '../../extension/tapDetector.js';

test('default window is 300 ms, minimum 50 ms', () => {
    eq(DOUBLE_TAP_MS, 300);
    eq(MIN_DOUBLE_TAP_MS, 50);
});

test('two taps within the window make a double-tap', () => {
    const d = new TapDetector();
    eq(d.tap(1000), false);
    eq(d.tap(1300), true);
});

test('two taps further apart than the window do not', () => {
    const d = new TapDetector();
    eq(d.tap(1000), false);
    eq(d.tap(1301), false);
});

test('a slow second tap becomes the first of a new pair', () => {
    const d = new TapDetector();
    d.tap(1000);
    eq(d.tap(2000), false);
    eq(d.tap(2100), true);
});

test('a third quick tap starts a new pair instead of doubling again', () => {
    const d = new TapDetector();
    d.tap(1000);
    eq(d.tap(1100), true);
    eq(d.tap(1200), false);
    eq(d.tap(1250), true);
});

test('custom window', () => {
    const d = new TapDetector(100);
    d.tap(0);
    eq(d.tap(150), false);
});

test('setWindow applies a valid window', () => {
    const d = new TapDetector();
    eq(d.setWindow(500), true);
    d.tap(0);
    eq(d.tap(450), true);
});

test('setWindow rejects too-small, fractional and non-numeric values', () => {
    const d = new TapDetector();
    eq(d.setWindow(49), false);
    eq(d.setWindow(120.5), false);
    eq(d.setWindow('300'), false);
    d.tap(0);
    eq(d.tap(300), true); // still the default
});

done();

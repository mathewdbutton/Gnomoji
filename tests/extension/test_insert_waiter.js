import {test, eq, done} from './assert.js';
import {decide, NO_IM_FOCUS_MS, GIVE_UP_MS} from '../../extension/insertWaiter.js';

const state = over => ({elapsedMs: 0, focusBack: false, backForMs: 0, imFocus: false, ...over});

test('constants', () => {
    eq(NO_IM_FOCUS_MS, 200);
    eq(GIVE_UP_MS, 1500);
});

test('commits once focus is back on the target and a text field has IM focus', () =>
    eq(decide(state({elapsedMs: 20, focusBack: true, backForMs: 5, imFocus: true})), 'commit'));

test('never commits while focus is elsewhere, even with IM focus (e.g. the picker)', () =>
    eq(decide(state({elapsedMs: 20, focusBack: false, imFocus: true})), 'wait'));

test('waits while focus is back but the text field has not checked in yet', () =>
    eq(decide(state({elapsedMs: 50, focusBack: true, backForMs: NO_IM_FOCUS_MS - 1})), 'wait'));

test('gives up when focus is back but no text field checks in', () =>
    eq(decide(state({elapsedMs: 250, focusBack: true, backForMs: NO_IM_FOCUS_MS})), 'no-text-field'));

test('keeps waiting for focus to come back', () =>
    eq(decide(state({elapsedMs: GIVE_UP_MS - 1})), 'wait'));

test('gives up when focus never comes back', () =>
    eq(decide(state({elapsedMs: GIVE_UP_MS})), 'focus-lost'));

test('commit wins over the give-up timer', () =>
    eq(decide(state({elapsedMs: GIVE_UP_MS + 5, focusBack: true, backForMs: 1, imFocus: true})), 'commit'));

done();

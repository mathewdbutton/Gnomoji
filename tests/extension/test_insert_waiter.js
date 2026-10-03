import {test, eq, done} from './assert.js';
import {acceptInsert, decide, MAX_INSERT_CODE_POINTS, NO_IM_FOCUS_MS, GIVE_UP_MS} from '../../extension/insertWaiter.js';

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

test('acceptInsert: the bound is 32 code points', () =>
    eq(MAX_INSERT_CODE_POINTS, 32));

test('acceptInsert: accepts emoji, including long ZWJ sequences with skin tones', () => {
    for (const text of ['🎉', '😀', '👍🏽', '🏳️‍🌈', '👩🏻‍❤️‍💋‍👨🏻', '🏴󠁧󠁢󠁳󠁣󠁴󠁿'])
        eq(acceptInsert(text), true, text);
});

test('acceptInsert: accepts exactly the bound, counted in code points not UTF-16 units', () => {
    eq(acceptInsert('😀'.repeat(MAX_INSERT_CODE_POINTS)), true);
    eq(acceptInsert('a'.repeat(MAX_INSERT_CODE_POINTS)), true);
});

test('acceptInsert: refuses longer text', () => {
    eq(acceptInsert('😀'.repeat(MAX_INSERT_CODE_POINTS + 1)), false);
    eq(acceptInsert('a'.repeat(MAX_INSERT_CODE_POINTS + 1)), false);
});

test('acceptInsert: refuses empty text and non-strings', () => {
    eq(acceptInsert(''), false);
    eq(acceptInsert(undefined), false);
    eq(acceptInsert(null), false);
    eq(acceptInsert(42), false);
});

test('acceptInsert: refuses C0 and C1 control characters', () => {
    for (const code of [0x00, 0x09, 0x0a, 0x0d, 0x1b, 0x1f, 0x7f, 0x80, 0x9b, 0x9f])
        eq(acceptInsert(`🎉${String.fromCodePoint(code)}`), false, code.toString(16));
});

test('acceptInsert: allows the characters either side of the control ranges', () => {
    eq(acceptInsert(' '), true);
    eq(acceptInsert('~'), true);
    eq(acceptInsert('\u00a0'), true);
});

done();

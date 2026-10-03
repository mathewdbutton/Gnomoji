// Minimal test helper for plain `gjs -m` test scripts (run by tests/test_extension_js.py).
import System from 'system';

let failures = 0;

export function test(name, fn) {
    try {
        fn();
        print(`ok ${name}`);
    } catch (e) {
        failures++;
        print(`FAIL ${name}: ${e.message}`);
    }
}

export function eq(actual, expected, label = '') {
    if (actual !== expected)
        throw new Error(`${label ? `${label}: ` : ''}expected ${JSON.stringify(expected)}, got ${JSON.stringify(actual)}`);
}

export function done() {
    System.exit(failures ? 1 : 0);
}

// Sanity check for the vitest toolchain (T1).
// Real suites live next to this file: sw.test.js / pwa-share.test.js / pwa-notify.test.js
import { describe, expect, it } from 'vitest';

describe('vitest toolchain', () => {
  it('runs a trivial assertion', () => {
    expect(1 + 1).toBe(2);
  });
});

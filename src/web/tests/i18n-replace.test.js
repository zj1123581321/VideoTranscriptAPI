import { describe, expect, it } from 'vitest';
import { installI18n } from './install-i18n.js';

describe('i18n placeholder replacement', () => {
  it('does not interpret $-patterns in interpolated values', () => {
    globalThis.window = globalThis;
    installI18n(globalThis);
    globalThis.I18N['web.js.test_dollar'] = 'before {err} after';
    expect(globalThis.t('web.js.test_dollar', { err: "$& $' $1 $$" })).toBe(
      "before $& $' $1 $$ after"
    );
  });
});

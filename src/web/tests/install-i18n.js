import { readFileSync } from 'node:fs';

const i18nSource = readFileSync('src/web/static/js/i18n.js', 'utf-8');

export function installI18n(windowObj, lang = 'zh-CN') {
  const catalog = JSON.parse(
    readFileSync(`src/video_transcript_api/i18n/locales/${lang}.json`, 'utf-8'),
  );
  windowObj.__VTA_LANG__ = lang;
  windowObj.I18N = Object.fromEntries(
    Object.entries(catalog).filter(([key]) => key.startsWith('web.')),
  );
  windowObj.eval(i18nSource);
}

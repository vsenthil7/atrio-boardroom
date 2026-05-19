/**
 * Caption overlay helper for ATRIO Boardroom demo recording.
 *
 * Ported from MendoraCI (AT-Hack0020) sibling project's caption-overlay.ts,
 * which itself was ported from Forensa (AT-Hack0018). Stable contract across
 * three projects:
 *   - showTitleCard:   full-screen title/subtitle/footnote, dwellMs
 *   - showSceneCard:   full-screen GIVEN/WHEN/THEN scene with step header
 *   - showCaptionPill: top-of-screen pill that does NOT block the UI
 *   - clearOverlay:    remove both
 *
 * Colours match ATRIO's brand: ink black background, paper white text,
 * orange accent (#f59e0b) for headers, blue for steps, green for success,
 * red for blockers/rejects.
 */
import { Page } from '@playwright/test';

const BG = '#0a0a0a';            // ATRIO ink
const BG_CARD = '#1a1a1a';
const WHITE = '#ffffff';
const TEXT_PRIMARY = '#e5e5e5';
const TEXT_SECONDARY = '#9ca3af';
const ACCENT_BLUE = '#3b82f6';
const ACCENT_GREEN = '#10b981';
const ACCENT_RED = '#dc2626';
const ACCENT_AMBER = '#f59e0b';   // ATRIO orange

export async function showTitleCard(
  page: Page,
  opts: { title: string; subtitle: string; footnote?: string; durationMs: number },
): Promise<void> {
  await page.evaluate(
    ({ title, subtitle, footnote, bg, white, textPrimary, textSecondary, blue, amber }) => {
      const existing = document.getElementById('atrio-overlay');
      if (existing) existing.remove();
      const overlay = document.createElement('div');
      overlay.id = 'atrio-overlay';
      overlay.style.cssText = `
        position: fixed; inset: 0; z-index: 999999;
        background: ${bg}; color: ${white};
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
        display: flex; flex-direction: column; justify-content: center; padding: 80px;
      `;
      const subtitleHtml = subtitle.split('\n').map((s) => `<div>${s}</div>`).join('');
      overlay.innerHTML = `
        <div style="display:flex;align-items:center;gap:16px;margin-bottom:48px;">
          <div style="width:24px;height:6px;background:${amber};border-radius:2px;"></div>
          <div style="font-size:14px;color:${textSecondary};letter-spacing:2px;">AT-HACK0021 \u00b7 MILAN AI WEEK 2026</div>
        </div>
        <div style="font-size:96px;font-weight:700;letter-spacing:-3px;margin-bottom:12px;line-height:0.95;">${title}</div>
        <div style="width:120px;height:4px;background:${blue};margin-bottom:32px;"></div>
        <div style="font-size:28px;color:${textPrimary};font-weight:400;line-height:1.5;">${subtitleHtml}</div>
        ${footnote ? `<div style="margin-top:48px;font-size:16px;color:${textSecondary};">${footnote}</div>` : ''}
      `;
      document.body.appendChild(overlay);
    },
    {
      title: opts.title,
      subtitle: opts.subtitle,
      footnote: opts.footnote ?? '',
      bg: BG,
      white: WHITE,
      textPrimary: TEXT_PRIMARY,
      textSecondary: TEXT_SECONDARY,
      blue: ACCENT_BLUE,
      amber: ACCENT_AMBER,
    },
  );
  await page.waitForTimeout(opts.durationMs);
}

export async function showSceneCard(
  page: Page,
  opts: {
    step: string;
    given: string;
    when: string;
    then: string;
    durationMs: number;
  },
): Promise<void> {
  await page.evaluate(
    ({ step, given, when, then, bg, white, textPrimary, blue, green, red, amber }) => {
      const existing = document.getElementById('atrio-overlay');
      if (existing) existing.remove();
      const overlay = document.createElement('div');
      overlay.id = 'atrio-overlay';
      overlay.style.cssText = `
        position: fixed; inset: 0; z-index: 999999;
        background: ${bg}; color: ${white};
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
        display: flex; flex-direction: column; justify-content: center; padding: 64px;
      `;
      overlay.innerHTML = `
        <div style="font-size:14px;color:${amber};letter-spacing:2px;margin-bottom:32px;font-weight:600;">${step}</div>
        <div style="display:grid;grid-template-columns:140px 1fr;gap:24px 32px;font-size:26px;line-height:1.5;">
          <div style="color:${red};font-weight:600;">GIVEN</div>
          <div style="color:${textPrimary};">${given}</div>
          <div style="color:${blue};font-weight:600;">WHEN</div>
          <div style="color:${textPrimary};">${when}</div>
          <div style="color:${green};font-weight:600;">THEN</div>
          <div style="color:${textPrimary};">${then}</div>
        </div>
      `;
      document.body.appendChild(overlay);
    },
    {
      step: opts.step,
      given: opts.given,
      when: opts.when,
      then: opts.then,
      bg: BG,
      white: WHITE,
      textPrimary: TEXT_PRIMARY,
      blue: ACCENT_BLUE,
      green: ACCENT_GREEN,
      red: ACCENT_RED,
      amber: ACCENT_AMBER,
    },
  );
  await page.waitForTimeout(opts.durationMs);
}

export async function showCaptionPill(
  page: Page,
  opts: { text: string; tone?: 'info' | 'success' | 'warn' | 'danger' },
): Promise<void> {
  await page.evaluate(
    ({ text, tone, bgCard, white, blue, green, amber, red }) => {
      const existing = document.getElementById('atrio-pill');
      if (existing) existing.remove();
      const accent =
        tone === 'success' ? green : tone === 'warn' ? amber : tone === 'danger' ? red : blue;
      const pill = document.createElement('div');
      pill.id = 'atrio-pill';
      pill.style.cssText = `
        position: fixed; top: 24px; left: 50%; transform: translateX(-50%);
        z-index: 999998;
        background: ${bgCard}; color: ${white};
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
        font-size: 18px; font-weight: 500;
        padding: 12px 24px; border-radius: 999px;
        border: 2px solid ${accent};
        box-shadow: 0 4px 16px rgba(0,0,0,0.4);
        max-width: 80vw;
        text-align: center;
      `;
      pill.textContent = text;
      document.body.appendChild(pill);
    },
    {
      text: opts.text,
      tone: opts.tone ?? 'info',
      bgCard: BG_CARD,
      white: WHITE,
      blue: ACCENT_BLUE,
      green: ACCENT_GREEN,
      amber: ACCENT_AMBER,
      red: ACCENT_RED,
    },
  );
}

export async function clearOverlay(page: Page): Promise<void> {
  await page.evaluate(() => {
    document.getElementById('atrio-overlay')?.remove();
    document.getElementById('atrio-pill')?.remove();
  });
}

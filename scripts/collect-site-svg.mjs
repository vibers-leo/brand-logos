#!/usr/bin/env node
/**
 * 공식 사이트에서 로고 SVG 를 찾아 스테이징에 받는다.
 *
 * 왜 필요한가 (2026-08-17 실측):
 *   한국 일상 브랜드·스타트업·공공서비스는 **위키데이터에 로고를 안 올린다.**
 *   요기요·쿠팡이츠·홈택스·정부24·맘스터치·닥터나우… 위키데이터를 아무리 더
 *   돌려도 이 무리는 안 채워진다. 소스가 또 바뀌어야 한다.
 *
 *   정적 HTML 만 받으면 안 나온다 — 대부분 SPA 라 로고가 JS 로 그려진다.
 *   렌더링한 뒤 DOM 에서 뽑으면 나온다:
 *     번개장터 → static.bunjang.co.kr/web/ui/logo-icon.svg
 *     맘스터치 → momstouch.co.kr/image/intro_logo.svg
 *     무신사   → svg 이미지 12개
 *
 * 무엇을 로고로 보는가 (가드):
 *   · <img src=*.svg> 중 경로에 logo|symbol|bi|ci|brand 가 있는 것 — 가장 확실
 *   · 헤더 영역(상단 200px)의 인라인 <svg> 중 크기가 로고다운 것
 *   · 아이콘(24x24 이하)·거대한 배경 그래픽 제외
 *   · 비트맵이 박힌 SVG 제외 — 그건 벡터가 아니다
 *
 * 운영 DB 를 바꾸지 않는다. 스테이징에 받고 대조 시트로 눈검사한 뒤 반영한다.
 *
 * 사용:
 *   node scripts/collect-site-svg.mjs --input targets.json
 *   node scripts/collect-site-svg.mjs --brand 맘스터치 --url https://www.momstouch.co.kr
 */
import { createRequire } from "node:module";

/* playwright-core 는 이 데이터 레포에 없다. semologo 앱에 설치된 것을 빌려 쓴다 —
   데이터 레포에 node_modules 를 만들지 않기 위해서다. */
function loadChromium() {
  const req = createRequire(import.meta.url);
  const roots = [
    process.env.PLAYWRIGHT_ROOT,
    "/Volumes/Untitled/dev/nextjs-apps/semologo/node_modules/playwright-core",
    `${homedir()}/Desktop/macminim4/dev/nextjs/apps/semologo/node_modules/playwright-core`,
  ].filter(Boolean);
  for (const r of roots) {
    try { return req(r).chromium; } catch { /* 다음 후보 */ }
  }
  try { return req("playwright-core").chromium; } catch { /* 없음 */ }
  return null;
}
import { existsSync, readdirSync, mkdirSync, writeFileSync, readFileSync } from "node:fs";
import { homedir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..");
const STAGE = join(ROOT, "_staging", "site-svg");
const UA =
  "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 " +
  "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36";

/** 이미 받아둔 headless 크로미움을 찾는다 (새로 설치하지 않는다). */
function findChromium() {
  if (process.env.CHROMIUM_PATH) return process.env.CHROMIUM_PATH;
  const base = `${homedir()}/Library/Caches/ms-playwright`;
  if (!existsSync(base)) return null;
  for (const d of readdirSync(base).filter((x) => x.startsWith("chromium_headless_shell"))) {
    for (const s of ["chrome-headless-shell-mac-arm64", "chrome-headless-shell-mac-x64"]) {
      const p = `${base}/${d}/${s}/chrome-headless-shell`;
      if (existsSync(p)) return p;
    }
  }
  return null;
}

const argOf = (name) => {
  const i = process.argv.indexOf(name);
  return i >= 0 ? process.argv[i + 1] : null;
};

/** 껍데기만 SVG 이고 안에 비트맵이 박힌 것은 벡터가 아니다. */
const isRealVector = (t) =>
  t.includes("<svg") && !t.includes("data:image/") && !t.includes("<image");

async function collectFrom(page, url) {
  await page.goto(url, { waitUntil: "domcontentloaded", timeout: 30000 });
  await page.waitForTimeout(4500);
  return page.evaluate(() => {
    const out = [];
    const looksLogo = (s) => /logo|symbol|brand|\bbi\b|\bci\b/i.test(s || "");

    // ① <img src="*.svg"> — 경로에 이름이 붙어 있어 판정이 가장 확실하다
    for (const img of document.querySelectorAll("img")) {
      const src = img.currentSrc || img.src || "";
      if (!/\.svg(\?|$)/i.test(src)) continue;
      const r = img.getBoundingClientRect();
      out.push({
        kind: "img", url: src, w: Math.round(r.width), h: Math.round(r.height),
        top: Math.round(r.top), score: (looksLogo(src) ? 10 : 0) + (r.top < 200 ? 5 : 0),
      });
    }

    // ② 헤더의 인라인 <svg>
    for (const svg of document.querySelectorAll("svg")) {
      const r = svg.getBoundingClientRect();
      if (r.width < 24 || r.width > 500 || r.height < 12) continue;  // 아이콘·배경 제외
      const id = `${svg.id} ${svg.getAttribute("class") || ""} ${svg.parentElement?.className || ""}`;
      out.push({
        kind: "inline", markup: svg.outerHTML, w: Math.round(r.width), h: Math.round(r.height),
        top: Math.round(r.top), score: (looksLogo(id) ? 10 : 0) + (r.top < 200 ? 5 : 0),
      });
    }
    return out.sort((a, b) => b.score - a.score).slice(0, 6);
  });
}

async function main() {
  const chromium = loadChromium();
  if (!chromium) {
    console.error("playwright-core 를 찾지 못했어요. PLAYWRIGHT_ROOT 로 경로를 알려주세요.");
    process.exit(2);
  }
  const exe = findChromium();
  if (!exe) {
    console.error("headless 크로미움을 찾지 못했어요. CHROMIUM_PATH 를 지정해 주세요.");
    process.exit(2);
  }

  let targets = [];
  const input = argOf("--input");
  if (input) targets = JSON.parse(readFileSync(input, "utf8"));
  else if (argOf("--brand")) targets = [{ name: argOf("--brand"), url: argOf("--url") }];
  else {
    console.error("--input 파일 또는 --brand/--url 이 필요합니다.");
    process.exit(2);
  }

  mkdirSync(STAGE, { recursive: true });
  const browser = await chromium.launch({ executablePath: exe });
  const report = [];

  for (const t of targets) {
    const page = await browser.newPage({ viewport: { width: 1280, height: 900 }, userAgent: UA });
    let found = 0, note = "";
    try {
      const cands = await collectFrom(page, t.url);
      for (const [i, c] of cands.entries()) {
        let text = c.markup;
        if (c.kind === "img") {
          try {
            const res = await page.request.get(c.url, { timeout: 15000 });
            text = res.ok() ? await res.text() : null;
          } catch { text = null; }
        }
        if (!text || !isRealVector(text)) continue;
        const dir = join(STAGE, t.slug || t.name);
        mkdirSync(dir, { recursive: true });
        writeFileSync(join(dir, found === 0 ? "logo.svg" : `cand-${i}.svg`), text);
        found++;
        if (found >= 3) break;                 // 후보는 3개까지만 (검수 부담을 줄인다)
      }
      if (!found) note = cands.length ? "SVG 후보는 있으나 벡터가 아님" : "SVG 없음(봇 차단 가능)";
    } catch (e) {
      note = `실패: ${String(e).split("\n")[0].slice(0, 60)}`;
    }
    await page.close();
    console.log(`  ${found ? "✅" : "✗ "} ${(t.name || t.url).padEnd(14)} ${found}건 ${note}`);
    report.push({ ...t, found, note });
  }

  await browser.close();
  writeFileSync(join(STAGE, "_report.json"), JSON.stringify(report, null, 1));
  const ok = report.filter((r) => r.found).length;
  console.log(`\n${ok}/${report.length} 성공 · 스테이징: ${STAGE}`);
  console.log("대조 시트로 눈검사한 뒤 반영하세요:");
  console.log("  python3 scripts/staging-contact-sheet.py --dir _staging/site-svg -o /tmp/site.html");
}

main();

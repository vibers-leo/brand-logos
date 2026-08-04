#!/usr/bin/env node
/**
 * gen-transparent.mjs
 * brand-logos CDN에서 logo-transparent.png 없는 브랜드를 찾아
 * rembg(Python)로 배경 제거 후 자동 생성.
 *
 * 사용법:
 *   node gen-transparent.mjs
 *   node gen-transparent.mjs --limit 10
 *   node gen-transparent.mjs --dry-run
 *   node gen-transparent.mjs --brand samsung
 */

import { readdirSync, existsSync } from "fs";
import { join } from "path";
import { execSync } from "child_process";

// ── 경로 설정 ──────────────────────────────────────────────
const CLIENTS_DIR = "/Users/juuuno/Desktop/macminim4/brand-logos/_clients";

// ── CLI 인수 파싱 ───────────────────────────────────────────
const args = process.argv.slice(2);

function getArg(flag) {
  const idx = args.indexOf(flag);
  if (idx === -1) return null;
  return args[idx + 1] ?? null;
}

const DRY_RUN = args.includes("--dry-run");
const LIMIT = getArg("--limit") ? parseInt(getArg("--limit"), 10) : Infinity;
const BRAND_FILTER = getArg("--brand") ?? null;

// ── 대상 브랜드 수집 ────────────────────────────────────────
function collectTargets() {
  let entries;
  try {
    entries = readdirSync(CLIENTS_DIR, { withFileTypes: true });
  } catch (err) {
    console.error(`ERROR: _clients 디렉토리를 읽을 수 없습니다. (${CLIENTS_DIR})`);
    console.error(err.message);
    process.exit(1);
  }

  const targets = [];

  for (const entry of entries) {
    if (!entry.isDirectory()) continue;

    const id = entry.name;

    // --brand 필터
    if (BRAND_FILTER && id !== BRAND_FILTER) continue;

    const brandDir = join(CLIENTS_DIR, id);
    const inputPath = join(brandDir, "logo.png");
    const outputPath = join(brandDir, "logo-transparent.png");

    if (!existsSync(inputPath)) continue;   // logo.png 없으면 스킵
    if (existsSync(outputPath)) continue;   // 이미 있으면 스킵

    targets.push({ id, inputPath, outputPath });
  }

  return targets;
}

// ── rembg 실행 ──────────────────────────────────────────────
function removeBackground(inputPath, outputPath) {
  // Python 한 줄 명령으로 배경 제거
  const pyCode = [
    "from rembg import remove",
    "from PIL import Image",
    `img = Image.open(r'${inputPath}')`,
    "out = remove(img)",
    `out.save(r'${outputPath}')`,
  ].join("; ");

  execSync(`python3 -c "${pyCode}"`, {
    timeout: 60_000,   // 브랜드당 최대 60초
    stdio: "pipe",
  });
}

// ── 메인 ────────────────────────────────────────────────────
function main() {
  const allTargets = collectTargets();

  if (allTargets.length === 0) {
    console.log("처리할 브랜드가 없습니다. 모든 브랜드에 logo-transparent.png가 이미 존재합니다.");
    return;
  }

  const targets = allTargets.slice(0, LIMIT);
  const total = targets.length;

  if (DRY_RUN) {
    console.log(`[DRY-RUN] 처리 대상 ${total}개 (전체 ${allTargets.length}개 중):\n`);
    targets.forEach(({ id, inputPath, outputPath }) => {
      console.log(`  ${id}`);
      console.log(`    input : ${inputPath}`);
      console.log(`    output: ${outputPath}`);
    });
    return;
  }

  console.log(`배경 제거 시작: 총 ${total}개 브랜드 (전체 미처리 ${allTargets.length}개 중)\n`);

  let successCount = 0;
  let errorCount = 0;

  for (let i = 0; i < targets.length; i++) {
    const { id, inputPath, outputPath } = targets[i];
    const prefix = `[${i + 1}/${total}] ${id}`;

    try {
      removeBackground(inputPath, outputPath);

      // 결과물이 실제로 생성됐는지 확인
      if (!existsSync(outputPath)) {
        throw new Error("출력 파일이 생성되지 않았습니다.");
      }

      console.log(`${prefix} → OK`);
      successCount++;
    } catch (err) {
      const msg = err.stderr
        ? err.stderr.toString().trim().split("\n").pop()
        : err.message;
      console.log(`${prefix} → ERROR: ${msg}`);
      errorCount++;
    }
  }

  // ── 요약 ──────────────────────────────────────────────────
  console.log("\n─────────────────────────────");
  console.log(`완료: 처리됨 ${successCount}개, 실패 ${errorCount}개`);
  if (allTargets.length > total) {
    console.log(`(--limit ${LIMIT} 적용으로 ${allTargets.length - total}개 미처리)`);
  }
}

main();

#!/usr/bin/env python3
"""
브랜드별 로고 변형 매니페스트 생성

무엇을 하나
-----------
브랜드 폴더 안에 이미 있는 파일들(logo.svg, sources/**)을 형태별로 분류해
`_clients/{id}/variants.json` 을 만든다. 새로 수집하지 않는다 — **이미 모아둔
것을 보여줄 수 있게 정리**하는 게 목적이다.

왜 사이드카인가
---------------
brands.json 은 이미 2.9MB 이고 정적 빌드 중 약 13,600회 읽힌다. 여기에 변형
정보를 인라인하면 5.2MB(+76%)가 되어 빌드가 느려진다. 반면 브랜드별 파일은
상세 페이지에서만 1개 받으면 되고, 목록(grid)은 brands-slim.json 만 보므로
영향이 없다.

핵심 설계: alts 병합
--------------------
다중 소스 브랜드 1,349개 중 910개는 **제공자만 다른 같은 형태**다
(iconify 의 '컬러 심볼' + wvl 의 '컬러 심볼'). 이걸 그대로 카드로 만들면
사용자에게는 똑같아 보이는 카드가 4장 뜬다. 같은 key 로 묶고 대표 하나만
노출하되, 나머지 제공자는 alts[] 에 남겨 주소는 유지한다.

멱등성
------
항목마다 src_sha1 + algo_v 를 기록한다. 둘 다 같으면 건너뛴다.
logoform.ALGO_V 를 올리면 의도적으로 전량 재계산된다.
origin="manual" (variants.override.json) 은 절대 덮어쓰지 않는다.

사용
----
  python3 scripts/build-logo-variants.py --brand kakaobank --dry-run
  python3 scripts/build-logo-variants.py --limit 200 --report /tmp/pilot.json
  python3 scripts/build-logo-variants.py --force
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import sys
from collections import OrderedDict
from pathlib import Path

import cairosvg
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
import logoform as L  # noqa: E402

BASE = Path(__file__).resolve().parent.parent / "_clients"
BRANDS_JSON = BASE / "brands.json"
SCHEMA = 1

# 형태별 노출 순서와 한국어 라벨.
# 대표(logo.svg)를 맨 앞에 두고, 그 다음은 활용 빈도 순.
FORM_META = {
    "horizontal": (10, "가로조합형"),
    "vertical":   (20, "세로조합형"),
    "symbol":     (30, "심볼형"),
    "wordmark":   (40, "워드마크형"),
    "unknown":    (90, "기타"),
}

# 제공자 신뢰도 — 같은 형태가 여러 소스에 있을 때 대표를 고르는 기준.
# 공식/위키미디어가 브랜드 원본에 가깝고, 아이콘 세트는 재해석이 섞인다.
PROVIDER_RANK = {
    "official": 0, "wikimedia": 1, "simple-icons": 2, "simpleicons": 2,
    "gilbarbara-logos": 3, "iconify": 4, "wvl": 5, "devicons": 6,
    "font-awesome": 7, "logo.dev": 8, "project-scan": 9,
}

# 라틴 문자만 다루는 제공자 — 언어 힌트로만 쓴다.
LATIN_PROVIDERS = {"wvl", "iconify", "devicons", "font-awesome",
                   "simple-icons", "simpleicons", "gilbarbara-logos"}


def sha1(path: Path) -> str:
    h = hashlib.sha1()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


def provider_of(raw: str) -> str:
    return (raw or "").split(":")[0] or "unknown"


def guess_lang(brand: dict, file: str, provider: str) -> str:
    """언어는 **증거가 있을 때만** 판정한다.

    외곽선화된 path 에서 한글과 라틴을 구분할 방법이 없다. 잘못된 '영문'
    라벨을 다는 것보다 unknown 으로 두고 언어 탭을 안 그리는 게 낫다.
    """
    name = Path(file).name.lower()
    if "-en" in name or "_en" in name:
        return "en"
    if "-ko" in name or "_ko" in name or "-kr" in name:
        return "ko"
    if brand.get("lang") in ("ko", "en"):
        return brand["lang"]
    if provider in LATIN_PROVIDERS:
        return "en"
    return "unknown"


def guess_color(arr) -> str:
    """색상 모드. 다크 배경용 자산을 구분하는 데 쓴다."""
    import numpy as np
    m = L.ink_mask(arr)
    if not m.any():
        return "color"
    px = arr[..., :3][m].astype(np.int16)
    chroma = (px.max(1) - px.min(1)).mean()
    lum = px.mean()
    if chroma < 18:
        return "mono-light" if lum > 200 else "mono-dark"
    return "color"


def rel(p: Path) -> str:
    return p.name if p.parent.name == p.parent.name else str(p)


def analyze_file(path: Path, brand: dict, provider: str, rel_path: str):
    """한 파일 → 변형 레코드 (분석 불가면 None)."""
    arr = L.render(path, 900)
    if arr is None:
        return None
    ar = L.aspect(arr)
    form = L.classify(ar)
    return {
        "form": form,
        "lang": guess_lang(brand, rel_path, provider),
        "color": guess_color(arr),
        "aspect": round(ar, 3) if ar else None,
        "provider": provider,
        "file": rel_path,
        "arr": arr,          # 심볼 크롭에 재사용 (레코드에는 안 들어감)
    }


def derive_symbol(brand_dir: Path, svg_rel: str, arr, dry: bool):
    """가로형/워드마크형에서 심볼을 떼어내 variants/symbol.svg + PNG 생성.

    파일은 variants/ 아래에 **추가만** 한다. 기존 파일명을 바꾸면 Firestore
    logo_votes 가 파일 경로를 키로 쓰고 있어 투표가 전부 고아가 된다.
    """
    src = brand_dir / svg_rel
    if not src.exists():
        return None
    # 세로 분리는 정밀도가 낮아 자동으로 쓰지 않는다 (logoform 문서 참조).
    # 세로 로크업은 variants.override.json 으로 사람이 확인한 것만 등록한다.
    split = L.find_symbol_split(arr, 900)
    if split is None:
        return None
    cropped = L.crop_viewbox(src.read_text(errors="ignore"), split,
                             (arr.shape[1], arr.shape[0]))
    if not cropped:
        return None
    if dry:
        return {"files": {"svg": "variants/symbol.svg",
                          "png": "variants/symbol-512.png"},
                "confidence": split.confidence, "side": split.side}

    out_dir = brand_dir / "variants"
    out_dir.mkdir(exist_ok=True)
    (out_dir / "symbol.svg").write_text(cropped)
    try:
        raw = cairosvg.svg2png(bytestring=cropped.encode(), output_width=512)
        img = Image.open(io.BytesIO(raw)).convert("RGBA")
        if img.getbbox() is None:
            (out_dir / "symbol.svg").unlink(missing_ok=True)
            return None
        img.save(out_dir / "symbol-512.png", "PNG", optimize=True)
    except Exception:
        (out_dir / "symbol.svg").unlink(missing_ok=True)
        return None
    return {"files": {"svg": "variants/symbol.svg",
                      "png": "variants/symbol-512.png"},
            "confidence": split.confidence, "side": split.side}


def png_sibling(brand_dir: Path, svg_rel: str) -> str | None:
    """소스 SVG 에는 같은 이름의 PNG 가 함께 생성돼 있다."""
    cand = Path(svg_rel).with_suffix(".png")
    return str(cand) if (brand_dir / cand).exists() else None


def build_brand(brand: dict, force: bool, dry: bool):
    bid = brand["id"]
    d = BASE / bid
    if not d.is_dir():
        return None, "폴더 없음"

    manifest_path = d / "variants.json"
    override_path = d / "variants.override.json"

    # 후보 파일 = 대표 logo.svg + sources[] 의 SVG
    candidates: list[tuple[str, str]] = []          # (rel_path, provider)
    if (d / "logo.svg").exists():
        candidates.append(("logo.svg", provider_of(brand.get("svg_source") or brand.get("source") or "")))
    seen = {"logo.svg"}
    for s in (brand.get("sources") or []):
        f = s.get("file")
        if not f or f in seen or not f.endswith(".svg"):
            continue
        if not (d / f).exists():
            continue
        seen.add(f)
        candidates.append((f, provider_of(s.get("provider", ""))))

    if not candidates:
        return None, "SVG 없음"

    # 멱등성: 입력 파일이 그대로고 알고리즘도 그대로면 건너뛴다
    fingerprint = {rp: sha1(d / rp) for rp, _ in candidates}
    if not force and manifest_path.exists():
        try:
            old = json.loads(manifest_path.read_text())
            if old.get("algo_v") == L.ALGO_V and old.get("fingerprint") == fingerprint:
                return None, "변경 없음"
        except Exception:
            pass

    records = []
    for rel_path, prov in candidates:
        rec = analyze_file(d / rel_path, brand, prov, rel_path)
        if rec:
            records.append(rec)
    if not records:
        return None, "분석 불가"

    # 대표(logo.svg)에서 심볼을 떼어낼 수 있으면 파생 변형으로 추가
    primary_rec = next((r for r in records if r["file"] == "logo.svg"), records[0])
    # 이미 수집된 심볼형 소스가 있으면 파생 심볼을 만들지 않는다.
    # 공식 아이콘이 있는데 자동 크롭본을 나란히 놓으면 중복이고,
    # 품질도 공식 쪽이 낫다 (예: adobe 는 iconify 에 adobe-icon 이 있다).
    has_symbol_source = any(r["form"] == "symbol" for r in records)
    if not has_symbol_source and primary_rec["form"] in ("horizontal", "wordmark"):
        sym = derive_symbol(d, "logo.svg", primary_rec["arr"], dry)
        if sym:
            # 심볼이 떨어져 나왔다는 건 이게 순수 워드마크가 아니라
            # '심볼+워드마크' 로크업이라는 뜻이다. 종횡비만 보면 wordmark 로
            # 분류되지만 의미상으로는 조합형이므로 라벨을 바로잡는다.
            # side="top" 이면 심볼이 위에 있는 세로 로크업이다
            primary_rec["_lockup"] = "세로형" if sym.get("side") == "top" else "가로형"
            records.append({
                "form": "symbol", "lang": "none", "color": primary_rec["color"],
                "aspect": None, "provider": "derived:autocrop",
                "file": sym["files"]["svg"], "arr": None,
                "_derived": {"from": "logo.svg", "confidence": sym["confidence"],
                             "png": sym["files"]["png"]},
            })

    # key 로 묶기 — 같은 형태·언어·색상은 카드 1장, 나머지 제공자는 alts 로
    groups: "OrderedDict[str, list]" = OrderedDict()
    for r in records:
        key = f"{r['form']}-{r['lang']}-{r['color']}"
        groups.setdefault(key, []).append(r)

    variants = []
    for key, group in groups.items():
        group.sort(key=lambda r: (
            0 if r["file"] == "logo.svg" else 1,               # 대표 파일 우선
            PROVIDER_RANK.get(r["provider"].split(":")[0], 50),
        ))
        head = group[0]
        order, label = FORM_META.get(head["form"], (90, "기타"))
        if head.get("_lockup"):
            order, label = 10, f"심볼+워드마크 ({head['_lockup']})"
        files = {"svg": head["file"]}
        if head.get("_derived"):
            files["png"] = head["_derived"]["png"]
            label = "심볼만"
        else:
            p = png_sibling(d, head["file"])
            if head["file"] == "logo.svg" and (d / "logo-800.png").exists():
                files["png"] = "logo-800.png"
            elif p:
                files["png"] = p
            elif (d / "logo.png").exists() and head["file"] == "logo.svg":
                files["png"] = "logo.png"
        v = OrderedDict([
            ("key", key), ("form", head["form"]), ("lang", head["lang"]),
            ("color", head["color"]), ("label", label),
            ("files", files), ("aspect", head["aspect"]),
            ("provider", head["provider"]),
            ("origin", "derived" if head.get("_derived") else "collected"),
            ("order", order),
        ])
        if head.get("_derived"):
            v["derived_from"] = head["_derived"]["from"]
            v["confidence"] = head["_derived"]["confidence"]
        alts = [{"provider": g["provider"], "file": g["file"]} for g in group[1:]]
        if alts:
            v["alts"] = alts
        variants.append(v)

    variants.sort(key=lambda v: (v["order"], v["key"]))
    primary_key = next((v["key"] for v in variants
                        if v["files"]["svg"] == "logo.svg"), variants[0]["key"])

    manifest = OrderedDict([
        ("schema", SCHEMA), ("algo_v", L.ALGO_V), ("id", bid),
        ("primary", primary_key), ("fingerprint", fingerprint),
        ("variants", variants),
    ])

    # 손으로 쓴 라벨은 생성기가 절대 덮어쓰지 않는다
    if override_path.exists():
        try:
            ov = json.loads(override_path.read_text())
            by_key = {v["key"]: v for v in manifest["variants"]}
            for o in ov.get("variants", []):
                if o.get("key") in by_key:
                    by_key[o["key"]].update(o)
                    by_key[o["key"]]["origin"] = "manual"
                else:
                    o["origin"] = "manual"
                    manifest["variants"].append(o)
        except Exception:
            pass

    if not dry:
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=1))
    return manifest, None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--brand")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--report")
    args = ap.parse_args()

    brands = json.loads(BRANDS_JSON.read_text())["brands"]
    if args.brand:
        brands = [b for b in brands if b["id"] == args.brand]
        if not brands:
            print(f"❌ 브랜드 '{args.brand}' 없음")
            return 1
    if args.limit:
        brands = brands[:args.limit]

    index = {}
    stats = {"생성": 0, "변경 없음": 0, "SVG 없음": 0, "분석 불가": 0, "폴더 없음": 0}
    multi = derived = 0

    for b in brands:
        m, skip = build_brand(b, args.force, args.dry_run)
        if skip:
            stats[skip] = stats.get(skip, 0) + 1
            continue
        stats["생성"] += 1
        n = len(m["variants"])
        if n > 1:
            multi += 1
        if any(v["origin"] == "derived" for v in m["variants"]):
            derived += 1
        index[b["id"]] = {"n": n, "forms": sorted({v["form"] for v in m["variants"]})}
        if stats["생성"] % 500 == 0:
            print(f"  ... {stats['생성']}개 처리", flush=True)

    print("\n결과:", " | ".join(f"{k} {v}" for k, v in stats.items() if v))
    print(f"변형 2종 이상: {multi}개 | 심볼 파생 포함: {derived}개")

    if not args.dry_run and not args.brand:
        # 인덱스는 이번 실행 결과가 아니라 **디스크에 있는 매니페스트 전부**를
        # 스캔해서 만든다. 이번 실행에서 "변경 없음"으로 건너뛴 브랜드도
        # 인덱스에는 있어야 하기 때문이다 (안 그러면 부분 실행마다 인덱스가 깎인다).
        full = {}
        for mp in sorted(BASE.glob("*/variants.json")):
            try:
                m = json.loads(mp.read_text())
            except Exception:
                continue
            vs = m.get("variants", [])
            full[mp.parent.name] = {"n": len(vs),
                                    "forms": sorted({v["form"] for v in vs})}
        idx_path = BASE / "variants-index.json"
        idx_path.write_text(json.dumps(
            {"schema": SCHEMA, "algo_v": L.ALGO_V, "count": len(full), "brands": full},
            ensure_ascii=False, separators=(",", ":")))
        print(f"📝 variants-index.json — {len(full)}개 ({idx_path.stat().st_size:,}B)")

    if args.report:
        Path(args.report).write_text(json.dumps(index, ensure_ascii=False, indent=1))
        print(f"📝 리포트: {args.report}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

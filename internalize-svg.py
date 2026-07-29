#!/usr/bin/env python3
"""
SVG 내재화 (Internalize)
외부 소스 SVG를 로고창고 표준으로 정제한다.

- 불필요한 메타데이터 제거 (Inkscape, Sodipodi, Adobe, Sketch 등)
- viewBox 정규화
- 외부 리소스 참조 제거
- 일관된 xmlns 정리
- XML 선언 표준화

사용:
  python3 internalize-svg.py                  # 전체 브랜드
  python3 internalize-svg.py --brand hyundai  # 특정 브랜드만
  python3 internalize-svg.py --dry-run        # 변경 없이 미리보기
"""

import argparse, json, re, sys
from pathlib import Path
import xml.etree.ElementTree as ET

BASE = Path(__file__).parent / "_clients"
BRANDS_JSON = BASE / "brands.json"

# 제거할 네임스페이스 prefix 목록
REMOVE_NS = {
    'inkscape', 'sodipodi', 'dc', 'cc', 'rdf',
    'sketch', 'xlink', 'adobe', 'illustrator',
}

# 제거할 태그 (네임스페이스 포함)
REMOVE_TAGS = {
    'metadata', 'title', 'desc',
    '{http://www.inkscape.org/namespaces/inkscape}',
    '{http://sodipodi.sourceforge.net/DTD/sodipodi-0.0.dtd}',
    '{http://purl.org/dc/elements/1.1/}',
    '{http://creativecommons.org/ns#}',
    '{http://www.w3.org/1999/02/22-rdf-syntax-ns#}',
}

# 제거할 속성 패턴
REMOVE_ATTR_PATTERNS = [
    r'^inkscape:',
    r'^sodipodi:',
    r'^dc:',
    r'^cc:',
    r'^rdf:',
    r'^sketch:',
    r'^xmlns:inkscape$',
    r'^xmlns:sodipodi$',
    r'^xmlns:dc$',
    r'^xmlns:cc$',
    r'^xmlns:rdf$',
    r'^xmlns:sketch$',
    r'^xmlns:xlink$',
    r'^xml:space$',
    r'^xml:lang$',
]


def should_remove_attr(name: str) -> bool:
    for pat in REMOVE_ATTR_PATTERNS:
        if re.match(pat, name):
            return True
    return False


def should_remove_tag(tag: str) -> bool:
    local = tag.split('}')[-1] if '}' in tag else tag
    if local in REMOVE_TAGS:
        return True
    for ns in REMOVE_TAGS:
        if tag.startswith(ns):
            return True
    return False


def normalize_viewbox(root: ET.Element) -> ET.Element:
    """viewBox 없으면 width/height로 추가"""
    if root.get('viewBox'):
        return root
    w = root.get('width', '').replace('px', '').replace('pt', '').strip()
    h = root.get('height', '').replace('px', '').replace('pt', '').strip()
    try:
        root.set('viewBox', f'0 0 {float(w):.4g} {float(h):.4g}')
    except (ValueError, TypeError):
        pass
    return root


def clean_element(elem: ET.Element) -> list:
    """재귀적으로 불필요한 요소·속성 정리. 제거할 자식 인덱스 반환."""
    to_remove = []
    for child in list(elem):
        if should_remove_tag(child.tag):
            to_remove.append(child)
        else:
            clean_element(child)

    for child in to_remove:
        elem.remove(child)

    # 속성 정리
    for attr in list(elem.attrib.keys()):
        if should_remove_attr(attr):
            del elem.attrib[attr]

    return to_remove


def clean_comments(text: str) -> str:
    """XML 주석 제거"""
    return re.sub(r'<!--.*?-->', '', text, flags=re.DOTALL)


def clean_xmlns(text: str) -> str:
    """사용하지 않는 xmlns 선언 제거"""
    for ns in REMOVE_NS:
        text = re.sub(rf'\s+xmlns:{ns}="[^"]*"', '', text)
    return text


def internalize(svg_path: Path, dry_run: bool = False) -> dict:
    original = svg_path.read_text(encoding='utf-8', errors='replace')

    # UTF-16 BOM 처리
    raw = svg_path.read_bytes()
    if raw[:2] in (b'\xff\xfe', b'\xfe\xff'):
        original = raw.decode('utf-16')

    # 비트맵 embedded 체크
    if 'data:image/' in original:
        return {'status': 'skip', 'reason': '비트맵 embedded — 교체 필요'}
    if 'DOCTYPE html' in original or '<html' in original:
        return {'status': 'skip', 'reason': 'HTML 에러페이지'}
    if '<svg' not in original:
        return {'status': 'skip', 'reason': 'SVG 태그 없음'}

    # XML 파싱
    try:
        # 네임스페이스 보존하며 파싱
        ET.register_namespace('', 'http://www.w3.org/2000/svg')
        root = ET.fromstring(original)
    except ET.ParseError as e:
        return {'status': 'error', 'reason': f'파싱 실패: {e}'}

    # 정제
    clean_element(root)
    normalize_viewbox(root)

    # 직렬화
    result = ET.tostring(root, encoding='unicode', xml_declaration=False)

    # 주석 제거 + xmlns 정리
    result = clean_comments(result)
    result = clean_xmlns(result)

    # 표준 헤더 추가
    output = '<?xml version="1.0" encoding="UTF-8"?>\n' + result

    # 변경량 계산
    before = len(original.encode())
    after = len(output.encode())
    reduction = before - after

    if dry_run:
        return {'status': 'ok', 'before': before, 'after': after, 'reduction': reduction}

    svg_path.write_text(output, encoding='utf-8')
    return {'status': 'ok', 'before': before, 'after': after, 'reduction': reduction}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--brand', help='특정 브랜드 ID만')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()

    brands = json.loads(BRANDS_JSON.read_text())['brands']
    if args.brand:
        brands = [b for b in brands if b['id'] == args.brand]
        if not brands:
            print(f"❌ '{args.brand}' 없음")
            sys.exit(1)

    total_saved = 0
    for b in brands:
        svg = BASE / b['id'] / 'logo.svg'
        if not svg.exists():
            print(f"[{b['name_ko']}] ⏭  SVG 없음")
            continue

        r = internalize(svg, dry_run=args.dry_run)
        if r['status'] == 'ok':
            saved = r['reduction']
            total_saved += max(saved, 0)
            tag = '[DRY RUN] ' if args.dry_run else ''
            arrow = '↓' if saved > 0 else '↑'
            print(f"[{b['name_ko']}] ✅ {tag}{r['before']}B → {r['after']}B ({arrow}{abs(saved)}B)")
        elif r['status'] == 'skip':
            print(f"[{b['name_ko']}] ⏭  {r['reason']}")
        else:
            print(f"[{b['name_ko']}] ❌ {r['reason']}")

    print(f"\n완료 | 총 {total_saved}B 절감")


if __name__ == '__main__':
    main()

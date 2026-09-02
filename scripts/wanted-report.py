#!/usr/bin/env python3
"""수집 대상 현황을 로컬 HTML 한 장으로 낸다. **배포하지 않는다.**

사이트에 /admin 을 두는 대신 로컬 파일로 가는 이유:
링크가 새면 그만인 토큰 방식과 달리 여기엔 샐 경로가 없고,
robots.txt·noindex 를 신경 쓸 일도 없다. 회색 시트와 같은 방식이다.

세 갈래를 한 장에 모은다:
  ① 미보유       collect-wanted.json — 아직 폴더조차 없는 브랜드
  ② SVG 대기     svg-wanted.json     — PNG 로 서비스 중이고 벡터만 없는 것
  ③ 홈페이지 미확보  _targets/*.json  — 리스트업은 됐는데 사이트를 못 찾은 것

실행:  python3 scripts/wanted-report.py && open /tmp/semologo-wanted.html
"""
import json, html, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
C, T = ROOT / "_clients", ROOT / "_targets"
OUT = Path("/tmp/semologo-wanted.html")


def load(p, key=None):
    if not p.exists():
        return []
    d = json.loads(p.read_text())
    if key and isinstance(d, dict):
        return d.get(key, [])
    return d if isinstance(d, list) else d.get("brands", [])


def main():
    raw = json.loads((C / "brands.json").read_text())
    br = raw["brands"] if isinstance(raw, dict) else raw
    have_dom = {(b.get("domain") or "").lower() for b in br if b.get("domain")}
    byid = {b["id"]: b for b in br}

    unowned = [x for x in load(C / "collect-wanted.json", "brands")
               if (x.get("domain") or "").lower() not in have_dom]
    novec = [x for x in load(C / "svg-wanted.json")
             if x["id"] in byid and not byid[x["id"]].get("has_svg")]

    nosite = []
    for f in sorted(T.glob("*.json")):
        for x in load(f):
            if not x.get("site"):
                nosite.append({"name": x.get("name") or x.get("name_ko") or "?",
                               "hq": x.get("hq") or x.get("market") or "",
                               "src": f.stem})

    secs = [
        ("① 미보유 — 폴더조차 없음", unowned,
         ["name_ko", "name_en", "domain", "category"],
         "수집하면 순증이다. 우선순위가 가장 높다."),
        ("② SVG 대기 — PNG 로 서비스 중", novec,
         ["id", "name_ko", "domain", "failed_source"],
         "이미 보이고는 있다. 벡터가 오면 품질이 오른다."),
        ("③ 홈페이지 미확보 — 접속할 주소가 없음", nosite,
         ["name", "hq", "src"],
         "네이버 검색으로 사이트를 찾아야 수집을 시도할 수 있다."),
    ]

    p = [f"""<!doctype html><meta charset="utf-8"><title>세모로고 수집 대상</title>
<style>
body{{font:14px/1.6 -apple-system,'Pretendard',sans-serif;margin:0;background:#fafafa;color:#18181b}}
header{{background:#18181b;color:#fff;padding:20px 28px}}
h1{{margin:0;font-size:19px}} .sub{{opacity:.6;font-size:12px;margin-top:4px}}
section{{margin:28px}} h2{{font-size:15px;margin:0 0 4px}}
.note{{color:#71717a;font-size:12px;margin-bottom:10px}}
table{{border-collapse:collapse;width:100%;background:#fff;font-size:13px}}
th{{background:#f4f4f5;text-align:left;padding:7px 10px;font-size:11px;color:#52525b;
   text-transform:uppercase;letter-spacing:.04em;position:sticky;top:0}}
td{{padding:6px 10px;border-top:1px solid #f0f0f0}}
tr:hover td{{background:#fafafa}}
.n{{background:#18181b;color:#fff;border-radius:20px;padding:1px 9px;font-size:12px;margin-left:6px}}
.wrap{{max-height:520px;overflow:auto;border:1px solid #e4e4e7;border-radius:8px}}
input{{width:100%;padding:8px 11px;margin-bottom:8px;border:1px solid #d4d4d8;
  border-radius:7px;font-size:13px}}
</style>
<header><h1>세모로고 — 수집 대상</h1>
<div class="sub">로컬 전용 · 배포되지 않음 · {time.strftime('%Y-%m-%d %H:%M')} 생성
 · 현재 보유 {len(br):,}건</div></header>"""]

    for i, (title, rows, cols, note) in enumerate(secs):
        p.append(f'<section><h2>{html.escape(title)}<span class="n">{len(rows):,}</span></h2>')
        p.append(f'<div class="note">{html.escape(note)}</div>')
        p.append(f'<input placeholder="이 표에서 검색…" oninput="flt(this,{i})">')
        p.append(f'<div class="wrap"><table id="t{i}"><thead><tr>'
                 + "".join(f"<th>{html.escape(c)}</th>" for c in cols)
                 + "</tr></thead><tbody>")
        for r in rows[:4000]:
            p.append("<tr>" + "".join(
                f"<td>{html.escape(str(r.get(c) or ''))}</td>" for c in cols) + "</tr>")
        p.append("</tbody></table></div>")
        if len(rows) > 4000:
            p.append(f'<div class="note">앞 4,000건만 표시 (전체 {len(rows):,}건)</div>')
        p.append("</section>")

    p.append("""<script>
function flt(inp,i){const q=inp.value.toLowerCase();
 document.querySelectorAll('#t'+i+' tbody tr').forEach(tr=>{
   tr.style.display = tr.textContent.toLowerCase().includes(q) ? '' : 'none';});}
</script>""")
    OUT.write_text("\n".join(p))
    print(f"✅ {OUT}")
    print(f"   미보유 {len(unowned):,} · SVG대기 {len(novec):,} · 홈페이지미확보 {len(nosite):,}")


if __name__ == "__main__":
    main()

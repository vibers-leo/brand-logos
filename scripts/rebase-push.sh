#!/bin/bash
# brand-logos rebase + push — 크론과 충돌할 때 쓴다.
#
# ⚠️ 2026-08-31: 충돌 해소 규칙 때문에 작업분이 세 번 날아갔다.
#    예전엔 brands.json 만 의미 병합하고 "그 외 전부"를 원격 것으로 택했는데,
#    그 "그 외"에 **내가 방금 고친 scripts/ 와 _targets/** 가 들어갔다.
#    HTTP 수정 5개와 명단 URL 교정 25곳이 통째로 사라졌다.
#
#    파일 성격에 따라 편을 나눈다:
#      scripts/**  _targets/**  → 항상 내 것 (사람이 고친 소스·명단)
#      _clients/brands.json     → 의미 병합 (양쪽 브랜드를 다 살린다)
#      collect/svg-wanted.json  → 합집합
#      그 외 (_clients/*/brand.json 등) → 원격 것 (전부 재생성물)
cd ~/Desktop/macminim4/brand-logos || exit 1

# ⚠️ unstaged 가 하나라도 있으면 rebase 는 시작조차 안 한다.
#    예전엔 그 실패를 `|| true` 가 삼켜서, 리베이스를 안 한 채 push 로 내려가
#    "non-fast-forward" 만 세 번 찍고 끝났다. 원인이 안 보였다.
if ! git diff --quiet || [ -n "$(git ls-files -m)" ]; then
  echo "⛔ 커밋 안 된 변경이 있어 rebase 를 시작할 수 없다:"
  git status --short | grep -v '^??' | head -10
  exit 1
fi

for i in 1 2 3; do
  git fetch origin main
  git rebase origin/main || true
  guard=0
  while [ -d .git/rebase-merge ] || [ -d .git/rebase-apply ]; do
    guard=$((guard+1)); [ "$guard" -gt 20 ] && { git rebase --abort; echo "GUARD_ABORT"; exit 1; }

    if git diff --name-only --diff-filter=U | grep -q "^_clients/brands.json$"; then
      git show :2:_clients/brands.json > /tmp/b.json
      git show :3:_clients/brands.json > /tmp/m.json
      python3 scripts/merge-brands-json.py /tmp/m.json /tmp/b.json _clients/brands.json
    fi

    for f in $(git diff --name-only --diff-filter=U | grep -v "^_clients/brands.json$"); do
      case "$f" in
        scripts/*|_targets/*)
          # 사람이 고친 소스·명단은 절대 원격으로 덮지 않는다
          # ⚠️ rebase 에서는 ours/theirs 가 **뒤바뀐다**.
          #    --ours = 원격(rebase 기준), --theirs = 내 커밋. 실측으로 확인했다.
          #    직관대로 --ours 를 쓰면 정반대로 원격이 이겨서 작업이 날아간다.
          git checkout --theirs -- "$f" 2>/dev/null || true ;;
        _clients/collect-wanted.json|_clients/svg-wanted.json)
          git show :2:"$f" > /tmp/b2.json; git show :3:"$f" > /tmp/m2.json
          python3 scripts/merge-wanted-json.py /tmp/m2.json /tmp/b2.json "$f" 2>/dev/null \
            || git checkout --theirs -- "$f" 2>/dev/null ;;
        *)
          # 재생성물은 러너(원격)가 방금 만든 쪽 = rebase 기준으로 --ours
          git checkout --ours -- "$f" 2>/dev/null || git checkout --theirs -- "$f" 2>/dev/null ;;
      esac
    done
    # ⚠️ 병합 스크립트가 실패해도 git add 는 충돌마커째 스테이징한다.
    #    실제로 그렇게 깨진 brands.json 이 커밋된 적이 있다(2026-08-31).
    if grep -q '^<<<<<<< ' _clients/brands.json 2>/dev/null; then
      echo "⛔ brands.json 에 충돌마커가 남았다 — 병합 실패"; git rebase --abort; exit 1
    fi
    if ! python3 -c "import json,sys; json.load(open('_clients/brands.json'))" 2>/dev/null; then
      echo "⛔ brands.json 이 유효한 JSON 이 아니다"; git rebase --abort; exit 1
    fi
    git add -A _clients _targets scripts 2>/dev/null
    GIT_EDITOR=true git rebase --continue || true
  done

  if git push; then echo "PUSH_OK"; exit 0; fi
  echo "푸시 거부 — 재시도 $i"
  sleep 5
done
echo "PUSH_FAILED"
exit 1

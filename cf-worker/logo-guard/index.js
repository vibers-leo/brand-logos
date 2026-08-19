/**
 * logo-guard — logo.vibers.co.kr 앞단 워커
 *
 * 하는 일 두 가지
 *   1. 핫링크 차단 (기존 기능, 그대로 유지)
 *   2. PNG 를 NCP 오브젝트 스토리지에서 서빙 (신규)
 *
 * 왜 PNG 만 옮기나 —
 * GitHub Pages 는 사이트 용량이 1GB 하드 리밋인데, PNG 파생물(logo.png·
 * logo-800·transparent·white·icon)이 전체의 79%(566MB)를 먹고 있었다.
 * 원본인 SVG 는 70MB 뿐이고 PNG 는 전부 SVG 에서 다시 만들 수 있다.
 * PNG 를 버킷으로 내보내면 브랜드를 5만 개까지 늘려도 Pages 가 버틴다.
 *
 * ⚠️ 폴백이 이 워커의 안전장치다.
 * 버킷에 없으면 **기존 Pages 원본으로 떨어진다.** 그래서 파일을 옮기기
 * 전에 워커를 먼저 배포해도 동작이 하나도 안 바뀐다. 이관 도중에 일부만
 * 올라가 있어도 나머지는 계속 원본에서 나온다.
 */

const BUCKET = "https://kr.object.ncloudstorage.com/vibers-bucket";

// _clients 아래 PNG 전부 — logo.png·logo-800·transparent·white·icon 과
// sources/·variants/ 하위 PNG 까지 포함한다.
const BUCKET_PATH = /^\/_clients\/[^/]+\/.*\.png$/i;

const ALLOWED_DOMAINS = [
  // Cloudflare 등록 도메인 전체
  "vibers.co.kr",
  "semologo.com",
  "faneasy.kr",
  "yahwabar.com",
  "oluolu.co.kr",
  "bizonmarketing.co.kr",
  "chefbridge.co.kr",
  "designd.co.kr",
  "designdlab.co.kr",
  "semophone.co.kr",
  "betheline.co.kr",
  "guestring.co.kr",
  "goodzz.co.kr",
  "nusucheck.com",
  "vibefolio.net",
  "keyenai.com",
  "kospatrading.co.kr",
  "premiumpage.kr",
  "monopage.kr",
  "wayo.co.kr",
  "zer0makers.kr",
  "honsul.app",
  "honsulmap.kr",
  "myratingis.kr",
  "giexpo.co.kr",
  "goodff.co.kr",
  "d-us.co.kr",
  // 한글 도메인 (퓨니코드 포함)
  "xn--ok1b401abvd0pl7qd.kr", // 작당페스타.kr
  "xn--3e0bj8jdshwkforkx2b.com", // 조선돼지국밥.com
  "xn--o39a53dg0bv12b6ecs6p.kr", // 이가네양꼬치.kr
  "xn--2f5b212a.com", // 야화.com
  "xn--bb0b37am4cuob.com", // 세모폰.com
  // Cloudflare Pages 미리보기 — 우리 프로젝트 것만 (와일드카드 pages.dev 는
  // 남의 사이트까지 핫링크를 허용하므로 넣지 않는다)
  "semologo.pages.dev",
  // localhost 개발환경
  "localhost",
  "127.0.0.1",
];

function isAllowedReferer(referer) {
  if (!referer) return true;
  try {
    const host = new URL(referer).hostname.toLowerCase();
    return ALLOWED_DOMAINS.some((d) => host === d || host.endsWith("." + d));
  } catch {
    return false;
  }
}

function isImagePath(path) {
  return /\.(svg|png|jpg|jpeg|webp|gif)$/i.test(path);
}

/**
 * 버킷에서 PNG 를 가져온다. 없으면 null 을 돌려 호출부가 원본으로 폴백하게 한다.
 *
 * 캐시 키에서 쿼리(`?v=`)는 뺀다 — 버킷 객체는 경로만으로 정해지고,
 * 버전 파라미터는 브라우저 캐시를 깨기 위한 것이라 엣지까지 갈 필요가 없다.
 * 안 그러면 VERSION 을 올릴 때마다 전 PoP 이 버킷을 다시 때린다.
 */
async function fromBucket(path) {
  const res = await fetch(BUCKET + path, {
    cf: {
      cacheEverything: true,
      cacheTtl: 31536000,
      // 404 도 잠깐 캐시해 둔다. 이관 전 브랜드가 매 요청마다 버킷을
      // 때리는 걸 막되, 이관 직후 반영이 하루씩 늦어지지 않게 짧게 잡는다.
      cacheTtlByStatus: { "200-299": 31536000, "404": 60, "500-599": 0 },
    },
  });
  return res.ok ? res : null;
}

export default {
  async fetch(request) {
    const url = new URL(request.url);
    const path = url.pathname;
    const referer = request.headers.get("Referer") || "";

    if (isImagePath(path) && !isAllowedReferer(referer)) {
      return new Response("Hotlinking not allowed", {
        status: 403,
        headers: { "Content-Type": "text/plain" },
      });
    }

    let response = null;
    if (BUCKET_PATH.test(path)) {
      try {
        response = await fromBucket(path);
      } catch {
        response = null; // 버킷 장애 시 원본으로 폴백한다
      }
    }
    if (!response) response = await fetch(request);

    const out = new Response(response.body, response);
    out.headers.set("Access-Control-Allow-Origin", "*");
    out.headers.set("Vary", "Origin");
    return out;
  },
};

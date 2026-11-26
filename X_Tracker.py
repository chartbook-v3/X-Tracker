# -*- coding: utf-8 -*-
"""
X-Tracker - 글로벌 빅테크·AI·반도체·매크로·네오클라우드 주요 인사 및 공식 계정 55곳 X(트위터) 24시간 실시간 추적 봇
- 출력 대상: 텔레그램 채널 (@chartbookx)
- 핵심 개선 사항:
  1) 고빈도 핵심 인물(일론 머스크 등) 단독 쿼리 + 나머지 소그룹 27개 분할 (저빈도 CEO·공식 그룹은 24h 윈도우 적용)
  2) 키워드 필터 전면 폐지(누락 방지) + 최소 위생 필터만 유지 (빈 리포스트 껍데기·초단문·짧은 답글·스포츠/연예 노이즈만 차단)
  3) X Article(장문 아티클) 블록 추출 지원 + URL 단독 입력 번역 환각 차단 가드레일
  4) X Snowflake 64비트 Status ID 기반 100% 정확한 UTC 발행시각 및 원작성자 핸들 검증
  5) Gemini Flash 금융 특화 한국어 번역 + 무료 Google Translate 자동 폴백
  6) GitHub Actions 24시간 무중단 Zero-Lag Relay 탑재
"""

import os
import re
import sys
import html
import json
import time
import hashlib
import argparse
import subprocess
import urllib.parse
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from datetime import datetime, timezone, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
    except Exception:
        pass
else:
    try:
        sys.stdout.reconfigure(line_buffering=True)
    except Exception:
        pass

KST = timezone(timedelta(hours=9))
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
HISTORY_FILE = os.path.join(BASE_DIR, "sent_history.json")
ENV_PATH = os.path.join(BASE_DIR, ".env")


def load_local_env():
    if not os.path.exists(ENV_PATH):
        return
    try:
        with open(ENV_PATH, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k = k.strip()
                v = v.strip().strip("'").strip('"')
                if k and k not in os.environ:
                    os.environ[k] = v
    except Exception:
        pass


load_local_env()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "@chartbookx").strip()
DEFAULT_MAX_AGE_MINUTES = 90
MAX_SEND_PER_CYCLE = 15

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "application/rss+xml, application/xml, text/xml, */*",
}

# X 주요 인사 및 공식 계정 56개 핸들 매핑 (SemiAnalysis 공식 @SemiAnalysis_ 추가)
X_VIP_PROFILES = {
    # 1. 반도체 · 하드웨어 · 빅테크 애널리스트 (10개)
    "semianalysis_": "X ｜ SEMIANALYSIS",
    "dylan522p": "X ｜ DYLAN PATEL (SEMIANALYSIS)",
    "zephyr_z9": "X ｜ ZEPHYR (AI · CHIPS)",
    "mingchikuo": "X ｜ MING-CHI KUO (TF INTERNATIONAL)",
    "divestech": "X ｜ DAN IVES (WEDBUSH)",
    "benbajarin": "X ｜ BEN BAJARIN (CREATIVE STRATEGIES)",
    "patrickmoorhead": "X ｜ PATRICK MOORHEAD (MOOR INSIGHTS)",
    "iancutress": "X ｜ IAN CUTRESS (CHIP ANALYST)",
    "markgurman": "X ｜ MARK GURMAN (BLOOMBERG)",
    "jukan05": "X ｜ JUKAN (SEMI · CITRINI)",
    # 2. 거시경제(매크로) · 월가 시장 전략가 (5명)
    "nicktimiraos": "X ｜ NICK TIMIRAOS (WSJ)",
    "elerianm": "X ｜ MOHAMED EL-ERIAN (ALLIANZ)",
    "schuldensuehner": "X ｜ HOLGER ZSCHAEPITZ (WELT)",
    "charliebilello": "X ｜ CHARLIE BILELLO (CREATIVE PLANNING)",
    "kobeissiletter": "X ｜ THE KOBEISSI LETTER",
    # 3. AI 연구자 · 빌더 · 뉴스 큐레이터 (8명)
    "karpathy": "X ｜ ANDREJ KARPATHY (OPENAI CO-FOUNDER)",
    "andrewyng": "X ｜ ANDREW NG (COURSERA)",
    "ylecun": "X ｜ YANN LECUN (NYU · AMI LABS)",
    "drjimfan": "X ｜ JIM FAN (NVIDIA ROBOTICS)",
    "emollick": "X ｜ ETHAN MOLLICK (WHARTON)",
    "rowancheung": "X ｜ ROWAN CHEUNG (THE RUNDOWN AI)",
    "simonw": "X ｜ SIMON WILLISON (DATASETTE)",
    "_akhaliq": "X ｜ AK (AI PAPER CURATOR)",
    # 4. 실리콘밸리 VC · 창업가 · 테크 리뷰어 (5명)
    "pmarca": "X ｜ MARC ANDREESSEN (A16Z)",
    "paulg": "X ｜ PAUL GRAHAM (Y COMBINATOR)",
    "garrytan": "X ｜ GARRY TAN (Y COMBINATOR CEO)",
    "eladgil": "X ｜ ELAD GIL (TECH VC)",
    "mkbhd": "X ｜ MARQUES BROWNLEE (MKBHD)",
    # 5. 빅테크 · 반도체 · 프론티어 AI 수장 (16명)
    "elonmusk": "X ｜ ELON MUSK (TESLA · XAI · SPACEX)",
    "tim_cook": "X ｜ TIM COOK (APPLE CHAIRMAN)",
    "sundarpichai": "X ｜ SUNDAR PICHAI (GOOGLE CEO)",
    "satyanadella": "X ｜ SATYA NADELLA (MICROSOFT CEO)",
    "ajassy": "X ｜ ANDY JASSY (AMAZON CEO)",
    "finkd": "X ｜ MARK ZUCKERBERG (META CEO)",
    "tobi": "X ｜ TOBI LUTKE (SHOPIFY CEO)",
    "lisasu": "X ｜ LISA SU (AMD CEO)",
    "jensenhuang": "X ｜ JENSEN HUANG (NVIDIA CEO)",
    "sama": "X ｜ SAM ALTMAN (OPENAI CEO)",
    "gdb": "X ｜ GREG BROCKMAN (OPENAI)",
    "darioamodei": "X ｜ DARIO AMODEI (ANTHROPIC CEO)",
    "demishassabis": "X ｜ DEMIS HASSABIS (DEEPMIND CEO)",
    "aravsrinivas": "X ｜ ARAVIND SRINIVAS (PERPLEXITY CEO)",
    "alexandr_wang": "X ｜ ALEXANDR WANG (META AI)",
    "clementdelangue": "X ｜ CLEMENT DELANGUE (HUGGING FACE CEO)",
    # 6. 핵심 빅테크 · 반도체 · AI 공식 계정 (9개)
    "googleaistudio": "X ｜ GOOGLE AI STUDIO OFFICIAL",
    "nvidianewsroom": "X ｜ NVIDIA NEWSROOM",
    "nvidia": "X ｜ NVIDIA OFFICIAL",
    "nvidiaai": "X ｜ NVIDIA AI",
    "openai": "X ｜ OPENAI OFFICIAL",
    "anthropicai": "X ｜ ANTHROPIC OFFICIAL",
    "openrouter": "X ｜ OPENROUTER OFFICIAL",
    "amd": "X ｜ AMD OFFICIAL",
    "intel": "X ｜ INTEL OFFICIAL",
    # 7. 네오클라우드 (CRWV · NBIS · IREN) C급 임원진 계정 (5개)
    "branninmcbee": "X ｜ BRANNIN MCBEE (COREWEAVE CO-FOUNDER · CDO)",
    "romanchernin": "X ｜ ROMAN CHERNIN (NEBIUS CO-FOUNDER · CBO)",
    "marcboroditsky": "X ｜ MARC BORODITSKY (NEBIUS CRO)",
    "sjkirschner": "X ｜ SETH J. KIRSCHNER (NEBIUS FIELD CISO)",
    "danroberts0101": "X ｜ DANIEL ROBERTS (IREN CO-CEO)",
}

# 초핵심 저빈도 CEO·뉴스룸: 초단문 원글(6자 이상, 예: 'Jensen!', "I'm back.") 및 짧은 답글(25자 이상) 허용
VIP_SHORT_ALLOW_HANDLES = {
    "semianalysis_",
    "dylan522p",
    "zephyr_z9",
    "googleaistudio",
    "jensenhuang",
    "sama",
    "darioamodei",
    "lisasu",
    "tim_cook",
    "sundarpichai",
    "satyanadella",
    "finkd",
    "ajassy",
    "karpathy",
    "demishassabis",
    "nvidianewsroom",
}

# Google News 색인 지연(1~12시간) 방어용 24시간(1d) 윈도우 적용 그룹 (고빈도 3개 그룹만 2h 유지)
LOW_FREQ_MAX_AGE_MINUTES = 1440
LOW_FREQ_GROUPS = {
    "X-SemiAnalysis",
    "X-DylanPatel",
    "X-Semi-Zephyr",
    "X-SamAltman",
    "X-Jensen-Karpathy",
    "X-BigTech1",
    "X-BigTech2",
    "X-ChipCEO",
    "X-AI-CEO1",
    "X-AI-CEO2",
    "X-Official-NVDA",
    "X-Official-AI",
    "X-Official-GoogleAI",
    "X-Official-OpenRouter",
    "X-Neocloud-Exec1",
    "X-Neocloud-Exec2",
    "X-Semi1",
    "X-Semi2",
    "X-Semi3",
    "X-Macro1",
    "X-Macro2",
    "X-AI-Res1",
    "X-AI-Res2",
    "X-AI-Res3",
    "X-VC1",
    "X-VC2",
}

# 고빈도 3개 그룹(when:2h) + 저/중빈도 및 색인 지연 방어 26개 그룹(when:1d) = 총 29개 정밀 분할 쿼리
X_QUERY_GROUPS = [
    # 고빈도 실시간 VIP 단독 쿼리 (when:2h)
    ("X-ElonMusk", ["elonmusk"]),
    ("X-Kobeissi", ["KobeissiLetter"]),
    ("X-Semi-Jukan", ["jukan05"]),
    # SemiAnalysis 공식 및 반도체 특종 분석가 단독 쿼리 (when:1d)
    ("X-SemiAnalysis", ["SemiAnalysis_"]),
    ("X-DylanPatel", ["dylan522p"]),
    ("X-Semi-Zephyr", ["zephyr_z9"]),
    # AI · 빅테크 · 반도체 CEO (when:1d)
    ("X-SamAltman", ["sama"]),
    ("X-Jensen-Karpathy", ["jensenhuang", "karpathy"]),
    ("X-BigTech1", ["tim_cook", "sundarpichai", "satyanadella"]),
    ("X-BigTech2", ["ajassy", "finkd", "tobi"]),
    ("X-ChipCEO", ["LisaSu", "AMD", "Intel"]),
    ("X-AI-CEO1", ["gdb", "DarioAmodei", "demishassabis"]),
    ("X-AI-CEO2", ["AravSrinivas", "alexandr_wang", "ClementDelangue"]),
    # 핵심 공식 계정 소그룹 (when:1d)
    ("X-Official-NVDA", ["nvidianewsroom", "nvidia", "nvidiaai"]),
    ("X-Official-AI", ["OpenAI", "AnthropicAI"]),
    ("X-Official-GoogleAI", ["GoogleAIStudio"]),
    ("X-Official-OpenRouter", ["OpenRouter"]),
    # 네오클라우드 (CRWV · NBIS · IREN) C급 임원진 (when:1d, 2그룹 통합)
    ("X-Neocloud-Exec1", ["branninmcbee", "danroberts0101"]),
    ("X-Neocloud-Exec2", ["romanchernin", "marcboroditsky", "sjkirschner"]),
    # 반도체·하드웨어 애널리스트 소그룹 (when:1d)
    ("X-Semi1", ["mingchikuo", "divestech"]),
    ("X-Semi2", ["benbajarin", "patrickmoorhead"]),
    ("X-Semi3", ["iancutress", "markgurman"]),
    # 매크로 전략가 소그룹 (when:1d)
    ("X-Macro1", ["NickTimiraos", "elerianm", "Schuldensuehner"]),
    ("X-Macro2", ["charliebilello"]),
    # AI 연구자·빌더 소그룹 (when:1d)
    ("X-AI-Res1", ["AndrewYNg", "ylecun", "DrJimFan"]),
    ("X-AI-Res2", ["emollick", "rowancheung"]),
    ("X-AI-Res3", ["simonw", "_akhaliq"]),
    # 실리콘밸리 VC 소그룹 (when:1d)
    ("X-VC1", ["pmarca", "paulg", "garrytan"]),
    ("X-VC2", ["eladgil", "MKBHD"]),
]


def build_gnews_x_url(handles: list[str], window: str = "2h") -> str:
    if len(handles) == 1:
        q = f"site:x.com/{handles[0]} when:{window}"
    else:
        clause = " OR ".join(f"site:x.com/{h}" for h in handles)
        q = f"({clause}) when:{window}"
    return f"https://news.google.com/rss/search?q={urllib.parse.quote(q)}&hl=en-US&gl=US&ceid=US:en"


# 명백한 비시장 잡담·스포츠·연예 노이즈 차단 (키워드 필터 전면 폐지, 최소 위생 필터만 유지)
NOISE_REGEX = re.compile(
    r"\b("
    r"nba|nfl|mlb|nhl|premier\s*league|world\s*cup|olympics|grammy|oscar|box\s*office|"
    r"horoscope|wordle|sudoku|recipe|homeless\s*batman|uranus|happy\s*birthday|merry\s*christmas|"
    r"good\s*morning\s*everyone|follow\s*me|giveaway"
    r")\b",
    flags=re.IGNORECASE,
)

# 본문 없는 껍데기 리포스트·프로필 헤더 차단
REPOST_SHELL_RE = re.compile(
    r"^(?:reposts?\s+by\s+.+|.+\s+(?:reposted|retweeted)|.{1,50}\(@[A-Za-z0-9_]+\))\s*$",
    flags=re.IGNORECASE,
)
LEADING_MENTIONS_RE = re.compile(r"^(?:@[A-Za-z0-9_]+\s+)+")


def load_history() -> dict:
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    return {
                        "status_ids": data.get("status_ids", []),
                        "title_hashes": data.get("title_hashes", []),
                        "recent_titles": data.get("recent_titles", []),
                    }
        except Exception:
            pass
    return {"status_ids": [], "title_hashes": [], "recent_titles": []}


def save_history(hist: dict) -> None:
    compact = {
        "status_ids": hist.get("status_ids", [])[-3000:],
        "title_hashes": hist.get("title_hashes", [])[-3000:],
        "recent_titles": hist.get("recent_titles", [])[-150:],
    }
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(compact, f, ensure_ascii=False, indent=2)


def parse_pub_date(date_str: str) -> datetime | None:
    if not date_str:
        return None
    try:
        dt = parsedate_to_datetime(date_str.strip())
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def resolve_canonical_url(url: str) -> str:
    if "news.google.com" not in url or "/articles/" not in url:
        return url
    art_id = url.split("/articles/")[1].split("?")[0]
    gn_ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
    for _ in range(2):
        try:
            r1 = requests.get(
                f"https://news.google.com/rss/articles/{art_id}",
                headers={"User-Agent": gn_ua},
                verify=False,
                timeout=(4, 6),
            )
            ts = re.search(r'data-n-a-ts="([^"]+)"', r1.text)
            sg = re.search(r'data-n-a-sg="([^"]+)"', r1.text)
            if ts and sg:
                req_inner = [
                    "garturlreq",
                    [
                        ["X", "X", ["X", "X"], None, None, 1, 1, "US:en", None, 1, None, None, None, None, None, 0, 1],
                        "X",
                        "X",
                        1,
                        [1, 1, 1],
                        1,
                        1,
                        None,
                        0,
                        0,
                        None,
                        0,
                    ],
                    art_id,
                    int(ts.group(1)),
                    sg.group(1),
                ]
                payload = [[["Fbv4je", json.dumps(req_inner), None, "generic"]]]
                r2 = requests.post(
                    "https://news.google.com/_/DotsSplashUi/data/batchexecute",
                    headers={
                        "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
                        "User-Agent": gn_ua,
                    },
                    data="f.req=" + urllib.parse.quote(json.dumps(payload)),
                    verify=False,
                    timeout=(4, 6),
                )
                m = re.search(r'\\"garturlres\\",\\"([^"]+)\\"', r2.text)
                if m:
                    raw_escaped = m.group(1)
                    return (
                        raw_escaped.replace(r"\\u003d", "=")
                        .replace(r"\u003d", "=")
                        .replace(r"\\u0026", "&")
                        .replace(r"\u0026", "&")
                        .replace(r"\\/", "/")
                        .replace(r"\/", "/")
                    )
        except Exception:
            pass
        time.sleep(0.3)
    return url


def parse_x_status_url(final_url: str) -> tuple[str | None, str | None, datetime | None]:
    """정식 X URL에서 (handle_low, status_id, snowflake_utc_dt) 추출."""
    m = re.search(r"(?:x\.com|twitter\.com)/([A-Za-z0-9_]{1,20})/status/(\d{15,22})", final_url, flags=re.IGNORECASE)
    if not m:
        return None, None, None
    handle_low = m.group(1).lower()
    sid_str = m.group(2)
    try:
        sid = int(sid_str)
        tweet_ts = ((sid >> 22) + 1288834974657) / 1000.0
        tweet_dt = datetime.fromtimestamp(tweet_ts, tz=timezone.utc)
        return handle_low, sid_str, tweet_dt
    except Exception:
        return handle_low, sid_str, None


def clean_and_filter_x_text(raw_text: str, allow_short: bool = False) -> tuple[str, bool]:
    """
    X 게시글 정제 및 최소 위생 필터링 (키워드 필터 없음):
    - 본문 없는 'reposted' 껍데기 및 'RT @' 차단
    - '@' 답글: 멘션 제거 후 35자 이상(초핵심 VIP는 25자 이상) 허용
    - 일반 원글: 10자 이상(초핵심 VIP는 6자 이상) 허용 ('😂', 'True' 등 초단문 제외)
    - 명백한 스포츠·연예 노이즈 블랙리스트만 차단
    """
    t = html.unescape(raw_text or "").strip()
    t = re.sub(r"\s*[-–—]\s*(?:X|Twitter)\s*$", "", t, flags=re.IGNORECASE).strip()
    t = re.sub(r"https?://\S+", "", t).strip()
    t = re.sub(r"\s+", " ", t).strip()

    if not t or t.lower().startswith("rt @") or REPOST_SHELL_RE.match(t):
        return "", False

    is_reply = t.startswith("@")
    if is_reply:
        t = LEADING_MENTIONS_RE.sub("", t).strip()
        min_rep_len = 25 if allow_short else 35
        if len(t) < min_rep_len:
            return "", False
    else:
        min_post_len = 6 if allow_short else 10
        if len(t) < min_post_len:
            return "", False

    if NOISE_REGEX.search(t):
        return "", False

    # Google News 제목 절단 보정 (최대 3문장, 250자)
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+(?=[A-Z0-9\"'“(\[$])", t) if s.strip()]
    if len(sentences) > 1:
        last_s = sentences[-1]
        if len(t) >= 210 and not re.search(r"[.!?\"'”%)\]]$", last_s):
            sentences = sentences[:-1]

    selected = []
    total_len = 0
    for s in sentences[:3]:
        if selected and total_len + len(s) > 250:
            break
        selected.append(s)
        total_len += len(s) + 1

    cleaned = " ".join(selected).strip() if selected else t[:240].strip()
    return cleaned, is_reply


# ==============================================================================
# 번역 엔진 (Gemini Flash 우선 + 무료 Google Translate 폴백)
# ==============================================================================
GEMINI_CIPHERTEXT_HEX = "651cfb4432c6861f71df2b24687ad702fd889fdb48ab8bb4cfa615a998362f4e6c0ce518784152805185f2a2ac17cea54b84563125"
_GEMINI_MODEL_COOLDOWN: dict[str, float] = {}


def _get_gemini_api_key() -> str | None:
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if api_key:
        return api_key
    if TELEGRAM_BOT_TOKEN:
        try:
            tg_bytes = TELEGRAM_BOT_TOKEN.encode("utf-8")
            key = (
                hashlib.sha256(tg_bytes + b"::chartbook_gemini_v1").digest()
                + hashlib.sha256(tg_bytes + b"::chartbook_gemini_v2").digest()
            )
            enc_bytes = bytes.fromhex(GEMINI_CIPHERTEXT_HEX)
            return bytes([b ^ key[i] for i, b in enumerate(enc_bytes)]).decode("utf-8")
        except Exception:
            pass
    return None


def _extract_article_text(article: dict, max_chars: int = 4800) -> str:
    """X Article(장문 아티클) 객체에서 제목과 본문 블록을 안전하게 추출합니다."""
    if not isinstance(article, dict):
        return ""
    title = (article.get("title") or "").strip()
    paragraphs = []

    content = article.get("content")
    if isinstance(content, dict):
        blocks = content.get("blocks") or []
        for blk in blocks:
            if not isinstance(blk, dict):
                continue
            b_txt = (blk.get("text") or "").strip()
            if b_txt:
                paragraphs.append(b_txt)

    if not paragraphs:
        preview = (article.get("preview_text") or "").strip()
        if preview:
            paragraphs.append(preview)

    if not paragraphs and not title:
        return ""

    parts = []
    if title:
        parts.append(f"[{title}]")
    total_len = len(parts[0]) if parts else 0
    truncated = False

    for p in paragraphs:
        if parts and total_len + len(p) + 2 > max_chars:
            truncated = True
            break
        parts.append(p)
        total_len += len(p) + 2

    if not parts and paragraphs:
        parts.append(paragraphs[0][:max_chars].rstrip() + "...")
        truncated = True

    result = "\n\n".join(parts).strip()
    if truncated:
        result += "\n\n[이하 전문은 상단 원문 링크 참고]"
    return result


def _strip_all_urls(text: str) -> str:
    """본문 내 모든 URL(t.co, x.com/i/article 등)을 제거합니다."""
    return re.sub(r"https?://\S+", "", text or "").strip()


def fetch_full_x_text(handle_low: str, status_id: str) -> str | None:
    """Google News 245자 절단을 보완해 X 원문 전문(일반 트윗 + X Article)을 가져옵니다 (API 키 불필요)."""
    raw_full = ""
    # 1순위: fxtwitter 공개 JSON API
    try:
        r = requests.get(
            f"https://api.fxtwitter.com/{handle_low}/status/{status_id}",
            headers={"User-Agent": "Mozilla/5.0"},
            verify=False,
            timeout=(3, 5),
        )
        if r.status_code == 200:
            tw = r.json().get("tweet") or {}
            base_text = _strip_all_urls(tw.get("text") or "")
            art_text = _extract_article_text(tw.get("article"))
            if art_text:
                raw_full = f"{base_text}\n\n{art_text}".strip() if base_text else art_text
            else:
                raw_full = base_text
    except Exception:
        pass

    # 2순위: X 공식 Syndication 엔드포인트 폴백
    if not raw_full:
        try:
            r2 = requests.get(
                f"https://cdn.syndication.twimg.com/tweet-result?id={status_id}&lang=en&token=4c2mmul6mnh",
                headers={"User-Agent": "Mozilla/5.0"},
                verify=False,
                timeout=(3, 5),
            )
            if r2.status_code == 200:
                d2 = r2.json() or {}
                base_text = _strip_all_urls(d2.get("text") or "")
                art_text = _extract_article_text(d2.get("article"))
                if art_text:
                    raw_full = f"{base_text}\n\n{art_text}".strip() if base_text else art_text
                else:
                    raw_full = base_text
        except Exception:
            pass

    if not raw_full:
        return None

    t = html.unescape(raw_full).strip()
    t = LEADING_MENTIONS_RE.sub("", t).strip()
    t = _strip_all_urls(t)
    # 문단 줄바꿈은 보존하고 불필요한 연속 공백만 정리
    lines = [re.sub(r"[ \t]+", " ", ln).strip() for ln in t.splitlines()]
    cleaned = "\n".join(lines)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
    return cleaned if len(cleaned) >= 10 else None


def _has_meaningful_text(text: str) -> bool:
    """URL을 제외한 실질적 텍스트(영문·숫자·한글)가 5자 이상 있는지 검증합니다."""
    stripped = _strip_all_urls(text)
    if len(stripped) < 5:
        return False
    return bool(re.search(r"[A-Za-z0-9\uac00-\ud7a3]", stripped))


def _translate_with_gemini(text: str) -> str | None:
    if not _has_meaningful_text(text):
        return None
    api_key = _get_gemini_api_key()
    if not api_key:
        return None

    models = [
        "gemini-flash-lite-latest",
        "gemini-3.1-flash-lite",
        "gemini-3-flash-preview",
    ]
    prompt = (
        "당신은 전문 영한 번역가입니다. "
        "다음 X(트위터) 원문을 요약하거나 생략·각색하지 말고, 원문의 모든 내용과 문단 구조를 그대로 살려 한국어로 충실하게 완역하세요.\n"
        "지침:\n"
        "1. 원문을 절대 요약하거나 문장을 빼지 말고 전문을 번역하세요.\n"
        "2. '누군가가 ~라고 언급했습니다' 같은 3인칭 보도문이나 해설을 임의로 붙이지 말고, 원문 화자의 시점과 어조를 그대로 번역하세요.\n"
        "3. 부가 설명, 접두어, 바깥쪽 따옴표 없이 번역된 본문만 출력하세요.\n"
        "4. 원문의 모든 숫자, 배수, 버전 번호, 고유명사, 금액, 비율(%)과 문단 줄바꿈을 100% 그대로 유지하세요.\n"
        "5. 원문에 없는 내용이나 다른 기업·제품 이야기를 절대 창작하거나 추측해 덧붙이지 마세요. 번역할 텍스트가 없거나 URL만 주어진 경우 아무 내용도 지어내지 말고 빈 문자열만 출력하세요.\n\n"
        f"원문:\n{text}"
    )
    payload_fast = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.1,
            "maxOutputTokens": 4096,
            "thinkingConfig": {"thinkingBudget": 0},
        },
    }
    payload_fb = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.1,
            "maxOutputTokens": 4096,
        },
    }

    now = time.time()
    for model in models:
        if now < _GEMINI_MODEL_COOLDOWN.get(model, 0.0):
            continue
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
            resp = requests.post(url, json=payload_fast, verify=False, timeout=(4, 10))
            if resp.status_code == 400 and "thinking" in resp.text.lower():
                resp = requests.post(url, json=payload_fb, verify=False, timeout=(4, 10))
            if resp.status_code == 200:
                cands = resp.json().get("candidates", [])
                if cands:
                    for part in cands[0].get("content", {}).get("parts", []):
                        if part.get("thought"):
                            continue
                        raw_out = (part.get("text") or "").strip()
                        raw_out = re.sub(r"\n{3,}", "\n\n", raw_out)
                        if len(raw_out) >= 2 and raw_out[0] == raw_out[-1] and raw_out[0] in ('"', "'"):
                            raw_out = raw_out[1:-1].strip()
                        if raw_out:
                            return raw_out
            elif resp.status_code == 429:
                _GEMINI_MODEL_COOLDOWN[model] = now + 600.0
            elif resp.status_code == 404:
                _GEMINI_MODEL_COOLDOWN[model] = now + 3600.0
        except Exception:
            pass
    return None


def translate_to_korean(text: str) -> str:
    if not _has_meaningful_text(text):
        return ""
    if len(re.findall(r"[\uac00-\ud7a3]", text)) >= 4:
        return text.strip()
    gem = _translate_with_gemini(text)
    if gem:
        return gem
    try:
        r = requests.get(
            "https://clients5.google.com/translate_a/t",
            params={"client": "dict-chrome-ex", "sl": "auto", "tl": "ko", "q": text},
            headers={"User-Agent": HEADERS["User-Agent"]},
            verify=False,
            timeout=(4, 5),
        )
        if r.status_code == 200:
            data = r.json()
            if isinstance(data, list) and data:
                first = data[0]
                if isinstance(first, list) and first:
                    return str(first[0]).strip()
                if isinstance(first, str):
                    return first.strip()
    except Exception:
        pass
    return text


def is_quiet_hours_kst() -> bool:
    return 0 <= datetime.now(KST).hour < 7


def format_message(profile_label: str, text_ko: str, x_url: str) -> str:
    safe_src = html.escape(profile_label, quote=False)
    safe_body = html.escape(text_ko, quote=False)
    safe_url = html.escape(x_url, quote=True)
    return f'<a href="{safe_url}"><b>{safe_src}</b></a>\n\n{safe_body}'


def send_telegram(profile_label: str, text_ko: str, x_url: str, dry_run: bool = False) -> bool:
    msg = format_message(profile_label, text_ko, x_url)
    if dry_run:
        print(f"[DRY-RUN]\n{msg}\n" + "-" * 40)
        return True
    if not TELEGRAM_BOT_TOKEN:
        print("[ERROR] TELEGRAM_BOT_TOKEN 환경변수가 설정되지 않았습니다.")
        return False

    api_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": msg,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
        "disable_notification": is_quiet_hours_kst(),
    }
    for attempt in range(3):
        try:
            r = requests.post(api_url, data=payload, timeout=10, verify=False)
            if r.status_code == 200:
                return True
            if r.status_code == 429:
                wait_sec = r.json().get("parameters", {}).get("retry_after", 5)
                time.sleep(wait_sec + 1)
            else:
                print(f"[ERROR] Telegram API HTTP {r.status_code}: {r.text[:200]}")
                return False
        except Exception as e:
            print(f"[ERROR] Telegram exception (attempt {attempt + 1}/3): {e}")
            time.sleep(2)
    return False


def fetch_group(name: str, handles: list[str], max_age_minutes: int, window: str = "2h") -> list[dict]:
    results = []
    is_low_freq = name in LOW_FREQ_GROUPS
    eff_window = "1d" if is_low_freq else window
    eff_max_age = max(max_age_minutes, LOW_FREQ_MAX_AGE_MINUTES) if is_low_freq else max_age_minutes
    group_allows_short = any(h.lower() in VIP_SHORT_ALLOW_HANDLES for h in handles)

    url = build_gnews_x_url(handles, window=eff_window)
    try:
        r = requests.get(url, headers=HEADERS, timeout=10, verify=False)
        if r.status_code != 200:
            return results
        root = ET.fromstring(r.content)
        items = root.findall(".//item")
    except Exception:
        return results

    now_utc = datetime.now(timezone.utc)
    for it in items:
        raw_t = (it.findtext("title") or "").strip()
        raw_link = (it.findtext("link") or "").strip()
        pub_s = (it.findtext("pubDate") or "").strip()
        if not raw_t or not raw_link:
            continue
        pub_dt = parse_pub_date(pub_s)
        if pub_dt is None:
            continue
        age_m = (now_utc - pub_dt).total_seconds() / 60.0
        if age_m < -5 or age_m > eff_max_age:
            continue

        cleaned, is_reply = clean_and_filter_x_text(raw_t, allow_short=group_allows_short)
        if not cleaned:
            continue

        results.append({
            "group": name,
            "raw_title": raw_t,
            "text_en": cleaned,
            "is_reply": is_reply,
            "gn_url": raw_link,
            "pub_dt": pub_dt,
            "max_age_m": eff_max_age,
        })
    return results


def is_similar_title(text_en: str, recent_titles: list[str]) -> bool:
    tokens = set(re.findall(r"[a-zA-Z0-9]{2,}", text_en.lower()))
    if len(tokens) < 3:
        return False
    for prev in recent_titles[-100:]:
        p_tokens = set(re.findall(r"[a-zA-Z0-9]{2,}", prev.lower()))
        if len(p_tokens) < 3:
            continue
        overlap = len(tokens & p_tokens) / min(len(tokens), len(p_tokens))
        if overlap >= 0.65:
            return True
    return False


def run_scan_cycle(hist: dict, max_age_minutes: int, dry_run: bool, window: str = "2h", deadline: float | None = None) -> int:
    sid_set = set(hist["status_ids"])
    th_set = set(hist["title_hashes"])
    candidates = []

    with ThreadPoolExecutor(max_workers=8) as ex:
        futures = [
            ex.submit(fetch_group, name, handles, max_age_minutes, window)
            for name, handles in X_QUERY_GROUPS
        ]
        for fut in as_completed(futures):
            try:
                candidates.extend(fut.result())
            except Exception:
                pass

    candidates.sort(key=lambda x: x["pub_dt"])

    now_utc = datetime.now(timezone.utc)
    sent_count = 0
    for item in candidates:
        if deadline is not None and time.time() >= deadline:
            print("[WARN] Safety budget reached inside scan cycle; stopping early to preserve relay.")
            break
        if sent_count >= MAX_SEND_PER_CYCLE:
            break
        t_hash = hashlib.md5(item["text_en"].lower().encode("utf-8")).hexdigest()[:16]
        if t_hash in th_set or is_similar_title(item["text_en"], hist["recent_titles"]):
            continue

        # 정식 X URL 복원 + Snowflake UTC 발행시각 및 VIP 작성자 핸들 1:1 실증 검증
        final_url = resolve_canonical_url(item["gn_url"])
        handle_low, sid_str, tweet_dt = parse_x_status_url(final_url)
        if not handle_low or not sid_str or handle_low not in X_VIP_PROFILES:
            continue
        if handle_low not in VIP_SHORT_ALLOW_HANDLES:
            strict_cleaned, _ = clean_and_filter_x_text(item.get("raw_title", item["text_en"]), allow_short=False)
            if not strict_cleaned:
                continue
        if sid_str in sid_set:
            continue
        if tweet_dt is not None:
            true_age_m = (now_utc - tweet_dt).total_seconds() / 60.0
            item_max_age = item.get("max_age_m", max_age_minutes)
            if true_age_m > item_max_age + 5:
                continue

        profile_label = X_VIP_PROFILES[handle_low]
        # Google News 245자 절단 보완: 원문 전문(일반 트윗 + X Article) 확보 후 요약 없이 충실 완역
        full_en = fetch_full_x_text(handle_low, sid_str) or item["text_en"]
        if not _has_meaningful_text(full_en):
            continue
        text_ko = translate_to_korean(full_en)
        if not _has_meaningful_text(text_ko):
            continue
        if len(text_ko) > 3800:
            cut = text_ko[:3750]
            nl_idx = cut.rfind("\n")
            if nl_idx > 2500:
                cut = cut[:nl_idx]
            text_ko = cut.rstrip() + "\n\n...(이하 전문은 상단 원문 링크 참고)"

        if send_telegram(profile_label, text_ko, final_url, dry_run=dry_run):
            hist["status_ids"].append(sid_str)
            hist["title_hashes"].append(t_hash)
            hist["recent_titles"].append(item["text_en"])
            sid_set.add(sid_str)
            th_set.add(t_hash)
            sent_count += 1
            if not dry_run:
                time.sleep(0.5)

    print(f"[DONE] groups={len(X_QUERY_GROUPS)}, candidates={len(candidates)}, sent={sent_count}")
    return sent_count


# ==============================================================================
# GitHub Actions 24시간 무중단 Zero-Lag Relay 엔진
# ==============================================================================
RELAY_REPO = "chartbook-v3/X-Tracker"
RELAY_WORKFLOW_ID = "x_tracker.yml"
RELAY_CIPHERTEXT_HEX = "d98d1546754122c8f7bbcbc55d90fb4efcf8884f1dcd0f3b02e7809e1ea66cb9a6c84dd8b70a1e84"


def git_push_history_in_actions() -> None:
    try:
        subprocess.run(["git", "config", "user.name", "github-actions[bot]"], check=False)
        subprocess.run(["git", "config", "user.email", "github-actions[bot]@users.noreply.github.com"], check=False)
        subprocess.run(["git", "add", "sent_history.json"], check=False)
        diff_res = subprocess.run(["git", "diff", "--staged", "--quiet"], check=False)
        if diff_res.returncode != 0:
            subprocess.run(["git", "commit", "-m", "chore: update sent_history.json [skip ci]"], check=False)
            pull_res = subprocess.run(["git", "pull", "--rebase", "origin", "main"], check=False)
            if pull_res.returncode != 0:
                subprocess.run(["git", "rebase", "--abort"], check=False)
                return
            subprocess.run(["git", "push"], check=False)
    except Exception as e:
        print(f"[WARN] Git history push error: {e}")


def trigger_next_github_workflow() -> None:
    if not TELEGRAM_BOT_TOKEN:
        return
    try:
        tg_bytes = TELEGRAM_BOT_TOKEN.encode("utf-8")
        key = (
            hashlib.sha256(tg_bytes + b"::chartbook_relay_v1").digest()
            + hashlib.sha256(tg_bytes + b"::chartbook_relay_v2").digest()
        )
        enc_bytes = bytes.fromhex(RELAY_CIPHERTEXT_HEX)
        gh_token = bytes([b ^ key[i] for i, b in enumerate(enc_bytes)]).decode("utf-8")
        headers = {
            "Authorization": f"Bearer {gh_token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        try:
            r_chk = requests.get(
                f"https://api.github.com/repos/{RELAY_REPO}/actions/runs?status=queued&per_page=10",
                headers=headers,
                verify=False,
                timeout=(4, 6),
            )
            if r_chk.status_code == 200:
                now_utc = datetime.now(timezone.utc)
                has_fresh_queued = False
                for q_run in r_chk.json().get("workflow_runs", []):
                    ca = q_run.get("created_at")
                    if not ca:
                        continue
                    try:
                        ca_dt = datetime.fromisoformat(ca.replace("Z", "+00:00"))
                        if (now_utc - ca_dt).total_seconds() < 600:
                            has_fresh_queued = True
                            break
                    except Exception:
                        pass
                if has_fresh_queued:
                    print("[RELAY] Queued run already exists; skipping duplicate dispatch.")
                    return
        except Exception:
            pass

        for attempt in range(3):
            try:
                r_disp = requests.post(
                    f"https://api.github.com/repos/{RELAY_REPO}/actions/workflows/{RELAY_WORKFLOW_ID}/dispatches",
                    headers=headers,
                    json={"ref": "main"},
                    verify=False,
                    timeout=(4, 10),
                )
                if r_disp.status_code == 204:
                    print("[RELAY] Dispatched next X-Tracker run (HTTP 204).")
                    return
                print(f"[RELAY] Dispatch HTTP {r_disp.status_code} (attempt {attempt + 1}/3)")
            except Exception as e:
                print(f"[RELAY] Dispatch exception (attempt {attempt + 1}/3): {e}")
            time.sleep(2)
    except Exception as e:
        print(f"[RELAY] Init exception: {e}")


def main():
    script_start = time.time()
    parser = argparse.ArgumentParser(description="X-Tracker VIP Telegram Bot")
    parser.add_argument("--dry-run", action="store_true", help="텔레그램 미발송, 콘솔 미리보기만 출력")
    parser.add_argument("--test-send", action="store_true", help="현재 출력 양식으로 텔레그램 테스트 메시지 1건 발송")
    parser.add_argument("--max-age", type=int, default=DEFAULT_MAX_AGE_MINUTES, help="수집 허용 최대 경과 시간(분)")
    parser.add_argument("--window", type=str, default="2h", help="Google News when 파라미터 (기본 2h)")
    args = parser.parse_args()

    if args.test_send:
        ok = send_telegram(
            "X ｜ OPENROUTER OFFICIAL",
            "[출력 양식 테스트]\n제목 하이퍼링크 및 본문 표시 확인용 테스트 메시지입니다.",
            "https://x.com/OpenRouter/status/2124925631012209137",
            dry_run=args.dry_run,
        )
        print(f"[TEST-SEND] sent={ok}")
        return

    hist = load_history()

    if os.getenv("GITHUB_ACTIONS") == "true" and not args.dry_run:
        actions_deadline = script_start + 200.0
        burst_cycles = 3
        burst_interval = 65.0
        total_sent = 0
        try:
            for idx in range(burst_cycles):
                if idx > 0 and time.time() + 35.0 >= actions_deadline:
                    break
                cycle_start = time.time()
                print(f"[CYCLE {idx + 1}/{burst_cycles}] scanning X VIPs...")
                sent = run_scan_cycle(
                    hist,
                    args.max_age,
                    dry_run=False,
                    window=args.window,
                    deadline=actions_deadline - 20.0,
                )
                total_sent += sent
                if sent > 0:
                    save_history(hist)
                if idx < burst_cycles - 1:
                    elapsed = time.time() - cycle_start
                    remaining = actions_deadline - time.time()
                    if remaining <= 40.0:
                        break
                    sleep_sec = min(max(10.0, burst_interval - elapsed), remaining - 35.0)
                    if sleep_sec >= 5.0:
                        time.sleep(sleep_sec)
        finally:
            if total_sent > 0:
                save_history(hist)
                git_push_history_in_actions()
            trigger_next_github_workflow()
    else:
        sent = run_scan_cycle(hist, args.max_age, dry_run=args.dry_run, window=args.window)
        if sent > 0 and not args.dry_run:
            save_history(hist)


if __name__ == "__main__":
    main()

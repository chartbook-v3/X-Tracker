# -*- coding: utf-8 -*-
"""
X-Tracker - 글로벌 빅테크·AI·반도체·매크로 주요 인사 44인 X(트위터) 24시간 실시간 추적 봇
- 출력 대상: 텔레그램 채널 (@chartbooknews)
- 핵심 개선 사항:
  1) 고빈도 핵심 인물(일론 머스크 등) 단독 쿼리 + 나머지 2~3인 소그룹 분할 (Google News when:2h 정상화)
  2) 핵심 기술·시장 발언을 담은 45자 이상 '@' 답글 선택 허용 (짧은 감탄사·잡담 답글 및 'reposted' 껍데기 차단)
  3) FSD·AI4/5/6·SRAM·SoC·compute·Grok·Starlink 등 첨단 기술·매크로 키워드 정밀 매칭
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
        sys.stdout.reconfigure(encoding="utf-8")
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
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "@chartbooknews").strip()
DEFAULT_MAX_AGE_MINUTES = 90
MAX_SEND_PER_CYCLE = 10

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "application/rss+xml, application/xml, text/xml, */*",
}

# X 주요 인사 44개 핸들 매핑
X_VIP_PROFILES = {
    # 1. 반도체 · 하드웨어 · 빅테크 애널리스트 (7명)
    "dylan522p": "X ｜ DYLAN PATEL (SEMIANALYSIS)",
    "mingchikuo": "X ｜ MING-CHI KUO (TF INTERNATIONAL)",
    "divestech": "X ｜ DAN IVES (WEDBUSH)",
    "benbajarin": "X ｜ BEN BAJARIN (CREATIVE STRATEGIES)",
    "patrickmoorhead": "X ｜ PATRICK MOORHEAD (MOOR INSIGHTS)",
    "iancutress": "X ｜ IAN CUTRESS (CHIP ANALYST)",
    "markgurman": "X ｜ MARK GURMAN (BLOOMBERG)",
    # 2. 거시경제(매크로) · 월가 시장 전략가 (6명)
    "nicktimiraos": "X ｜ NICK TIMIRAOS (WSJ)",
    "elerianm": "X ｜ MOHAMED EL-ERIAN (ALLIANZ)",
    "schuldensuehner": "X ｜ HOLGER ZSCHAEPITZ (WELT)",
    "charliebilello": "X ｜ CHARLIE BILELLO (CREATIVE PLANNING)",
    "kobeissiletter": "X ｜ THE KOBEISSI LETTER",
    "northmantrader": "X ｜ SVEN HENRICH (NORTHMANTRADER)",
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
    # 5. 빅테크 · 반도체 · 프론티어 AI 수장 (18개)
    "elonmusk": "X ｜ ELON MUSK (TESLA · XAI · SPACEX)",
    "tim_cook": "X ｜ TIM COOK (APPLE)",
    "sundarpichai": "X ｜ SUNDAR PICHAI (GOOGLE CEO)",
    "satyanadella": "X ｜ SATYA NADELLA (MICROSOFT CEO)",
    "ajassy": "X ｜ ANDY JASSY (AMAZON CEO)",
    "finkd": "X ｜ MARK ZUCKERBERG (META CEO)",
    "tobi": "X ｜ TOBI LUTKE (SHOPIFY CEO)",
    "lisasu": "X ｜ LISA SU (AMD CEO)",
    "jensenhuang": "X ｜ JENSEN HUANG (NVIDIA CO-FOUNDER)",
    "intel": "X ｜ INTEL OFFICIAL",
    "intelnews": "X ｜ INTEL NEWS",
    "sama": "X ｜ SAM ALTMAN (OPENAI CEO)",
    "gdb": "X ｜ GREG BROCKMAN (OPENAI)",
    "darioamodei": "X ｜ DARIO AMODEI (ANTHROPIC CEO)",
    "demishassabis": "X ｜ DEMIS HASSABIS (DEEPMIND CEO)",
    "aravsrinivas": "X ｜ ARAVIND SRINIVAS (PERPLEXITY CEO)",
    "alexandr_wang": "X ｜ ALEXANDR WANG (META AI)",
    "clementdelangue": "X ｜ CLEMENT DELANGUE (HUGGING FACE CEO)",
}

# Google News when:2h 무력화 방지를 위해 고빈도 단독(1인) + 소그룹(2~3인) 20개 쿼리로 정밀 분할
X_QUERY_GROUPS = [
    # 고빈도 핵심 VIP 단독 쿼리 (5개)
    ("X-ElonMusk", ["elonmusk"]),
    ("X-Kobeissi", ["KobeissiLetter"]),
    ("X-SamAltman", ["sama"]),
    ("X-JensenHuang", ["jensenhuang"]),
    ("X-Karpathy", ["karpathy"]),
    # 빅테크·반도체 CEO 소그룹 (4개)
    ("X-BigTech1", ["tim_cook", "sundarpichai", "satyanadella"]),
    ("X-BigTech2", ["ajassy", "finkd", "tobi"]),
    ("X-ChipCEO", ["LisaSu", "Intel", "IntelNews"]),
    ("X-AI-CEO1", ["gdb", "DarioAmodei", "demishassabis"]),
    ("X-AI-CEO2", ["AravSrinivas", "alexandr_wang", "ClementDelangue"]),
    # 반도체·하드웨어 애널리스트 소그룹 (3개)
    ("X-Semi1", ["dylan522p", "mingchikuo", "divestech"]),
    ("X-Semi2", ["benbajarin", "patrickmoorhead"]),
    ("X-Semi3", ["iancutress", "markgurman"]),
    # 매크로 전략가 소그룹 (2개)
    ("X-Macro1", ["NickTimiraos", "elerianm", "Schuldensuehner"]),
    ("X-Macro2", ["charliebilello", "NorthmanTrader"]),
    # AI 연구자·빌더 소그룹 (3개)
    ("X-AI-Res1", ["AndrewYNg", "ylecun", "DrJimFan"]),
    ("X-AI-Res2", ["emollick", "rowancheung"]),
    ("X-AI-Res3", ["simonw", "_akhaliq"]),
    # 실리콘밸리 VC 소그룹 (2개)
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


# 핵심 기술·반도체·AI·기업·매크로 정밀 정규식 (기존 누락 용어 전면 보강)
X_TECH_MARKET_REGEX = re.compile(
    r"\b("
    # 빅테크·AI 기업 및 제품
    r"tesla|tsla|fsd|autopilot|robotaxi|cybercab|optimus|grok|xai|spacex|starlink|starship|"
    r"ai4|ai5|ai6|trip|dojo|megapack|supercharger|radar|"
    r"nvidia|nvda|tsmc|asml|intel|amd|broadcom|avgo|micron|samsung|hynix|arm|qualcomm|"
    r"apple|aapl|microsoft|msft|google|alphabet|meta|amazon|amzn|aws|azure|oracle|"
    r"openai|anthropic|claude|gpt|gemini|deepseek|llama|mistral|perplexity|hugging\s*face|genie|sora|codex|"
    # 반도체·하드웨어·컴퓨트
    r"chip|chips|semiconductor|gpu|gpus|tpu|npu|asic|soc|sram|dram|hbm|hbm3e|hbm4|nand|"
    r"wafer|foundry|cowos|packaging|lithography|euv|compute|cluster|datacenter|data\s*center|"
    r"cooling|gigawatt|megawatt|server|accelerator|silicon|blackwell|rubin|decoder|inference|"
    r"robotics|humanoid|autonomous|ev|battery|lithium|energy|nuclear|smr|"
    # 프론티어 AI
    r"superintelligence|super\s*intelligence|agi|asi|singularity|llm|reasoning|agent|agents|"
    r"alignment|benchmark|post-training|sft|rlhf|synthetic\s*data|video\s*generation|world\s*model|"
    r"neural|model|models|ai\s+model|ai\s+system|open\s*source|"
    # 매크로·증시·기업 이벤트
    r"fed|fomc|powell|rate\s*cut|rate\s*hike|cpi|pce|gdp|inflation|deflation|recession|"
    r"tariff|tariffs|treasury|yield|bond|bonds|liquidity|cash\s*shortage|capex|revenue|"
    r"earnings|guidance|valuation|ipo|m&a|acquisition|merger|buyout|selloff|oversold|"
    r"s&p|nasdaq|dow|stock|stocks|shares|market|markets|oil|crude|gold|silver|copper|"
    r"bitcoin|btc|crypto|china|export\s*control|sanction|sanctions|antitrust|doj|sec|ftc|"
    r"billion|trillion|economy|economic|unemployment|payroll|jobs|retail\s*sales|pmi"
    r")\b",
    flags=re.IGNORECASE,
)

# 명백한 비시장 잡담·스포츠·연예 노이즈 차단
NOISE_REGEX = re.compile(
    r"\b("
    r"nba|nfl|mlb|nhl|premier\s*league|world\s*cup|olympics|grammy|oscar|box\s*office|"
    r"horoscope|wordle|sudoku|recipe|homeless\s*batman|uranus|happy\s*birthday|merry\s*christmas|"
    r"good\s*morning\s*everyone|follow\s*me|giveaway"
    r")\b",
    flags=re.IGNORECASE,
)

# 본문 없는 껍데기 리포스트 및 단순 감탄사 차단
REPOST_SHELL_RE = re.compile(r"^.+\s+(?:reposted|retweeted)\s*$", flags=re.IGNORECASE)
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


def clean_and_filter_x_text(raw_text: str) -> tuple[str, bool]:
    """
    X 게시글 정제 및 필터링:
    - 본문 없는 'reposted' 껍데기 및 'RT @' 차단
    - '@' 답글은 앞 멘션 제거 후 본문이 45자 이상이면서 핵심 키워드 매칭 시 선택 허용
    - 일반 원글은 15자 이상이면서 핵심 키워드 매칭 시 허용
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
        if len(t) < 45:
            return "", False
    else:
        if len(t) < 15:
            return "", False

    if NOISE_REGEX.search(t):
        return "", False

    if not X_TECH_MARKET_REGEX.search(t):
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
GEMINI_CIPHERTEXT_HEX = "651cfb4432c6861f71de1e590d7e9832baa8f9e3639581bd9abc11f4a12a4d34620e910b645a4cb2458baa9cd720c1ae518b641403"
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


def _translate_with_gemini(text: str) -> str | None:
    api_key = _get_gemini_api_key()
    if not api_key:
        return None

    models = [
        "gemini-flash-lite-latest",
        "gemini-3.1-flash-lite",
        "gemini-3-flash-preview",
    ]
    prompt = (
        "당신은 증권사 및 테크 전문 외신 속보 데스크입니다. "
        "다음 X(트위터) 주요 인사 게시글을 한국 텔레그램 증권 속보 채널 스타일에 맞춰 "
        "핵심 팩트 중심의 자연스러운 한국어 1~3문장(한 문단)으로 압축 번역하세요.\n"
        "지침:\n"
        "1. 부가 설명, 접두어, 줄바꿈, 바깥쪽 따옴표 없이 번역된 본문 텍스트만 출력하세요.\n"
        "2. '~말했습니다' 대신 '~전망', '~밝혀', '~언급', '~강조', '~지적' 등 간결한 속보 문체를 사용하세요.\n"
        "3. 원문의 숫자, 버전 번호(예: FSD V15, AI4, AI6, 25배), 금액, 비율(%)을 절대 변경하지 마세요.\n\n"
        f"원문: {text}"
    )
    payload_fast = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.2,
            "maxOutputTokens": 300,
            "thinkingConfig": {"thinkingBudget": 0},
        },
    }
    payload_fb = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.2,
            "maxOutputTokens": 300,
        },
    }

    now = time.time()
    for model in models:
        if now < _GEMINI_MODEL_COOLDOWN.get(model, 0.0):
            continue
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
            resp = requests.post(url, json=payload_fast, verify=False, timeout=(3, 6))
            if resp.status_code == 400 and "thinking" in resp.text.lower():
                resp = requests.post(url, json=payload_fb, verify=False, timeout=(3, 6))
            if resp.status_code == 200:
                cands = resp.json().get("candidates", [])
                if cands:
                    for part in cands[0].get("content", {}).get("parts", []):
                        if part.get("thought"):
                            continue
                        txt = " ".join(ln.strip() for ln in (part.get("text") or "").splitlines() if ln.strip())
                        if len(txt) >= 2 and txt[0] == txt[-1] and txt[0] in ('"', "'"):
                            txt = txt[1:-1].strip()
                        if txt:
                            return txt
            elif resp.status_code == 429:
                _GEMINI_MODEL_COOLDOWN[model] = now + 600.0
            elif resp.status_code == 404:
                _GEMINI_MODEL_COOLDOWN[model] = now + 3600.0
        except Exception:
            pass
    return None


def translate_to_korean(text: str) -> str:
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
    url = build_gnews_x_url(handles, window=window)
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
        if age_m < -5 or age_m > max_age_minutes:
            continue

        cleaned, is_reply = clean_and_filter_x_text(raw_t)
        if not cleaned:
            continue

        results.append({
            "group": name,
            "text_en": cleaned,
            "is_reply": is_reply,
            "gn_url": raw_link,
            "pub_dt": pub_dt,
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


def run_scan_cycle(hist: dict, max_age_minutes: int, dry_run: bool, window: str = "2h") -> int:
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
        if sid_str in sid_set:
            continue
        if tweet_dt is not None:
            true_age_m = (now_utc - tweet_dt).total_seconds() / 60.0
            if true_age_m > max_age_minutes + 5:
                continue

        profile_label = X_VIP_PROFILES[handle_low]
        text_ko = translate_to_korean(item["text_en"])

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
                f"https://api.github.com/repos/{RELAY_REPO}/actions/runs?status=queued&per_page=2",
                headers=headers,
                verify=False,
                timeout=(4, 6),
            )
            if r_chk.status_code == 200 and r_chk.json().get("total_count", 0) > 0:
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
    parser.add_argument("--max-age", type=int, default=DEFAULT_MAX_AGE_MINUTES, help="수집 허용 최대 경과 시간(분)")
    parser.add_argument("--window", type=str, default="2h", help="Google News when 파라미터 (기본 2h)")
    args = parser.parse_args()

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
                sent = run_scan_cycle(hist, args.max_age, dry_run=False, window=args.window)
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

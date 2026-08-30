"""autofix.py v12.1 — 정규식 자동교정 + 챕터 즉시검사 + 합본 최종검증 (채널A·채널C 성공공식 반영)

v10에서는 챕터마다 check_chapter()로 15개 항목을 검증하고, 실패하면 AI가 부분 수정을
반복했다. 그 왕복이 시간의 상당 부분을 잡아먹었다.

v10.1은 두 가지로 나눈다.
  - autofix()    : 기계적으로 고칠 수 있는 것은 AI 판단 없이 정규식으로 무조건 치환.
                   챕터 저장 직후 + 합본 직후에 실행한다. 결과 보고 없음.
  - check_final(): 나머지 검증 전체를 합본에서 딱 1회 실행한다.

★ 모든 글자수는 공백 제외 기준이다(야담 대본 지침.txt v12_main과 동일).
★ v11 추가 — check_formula(): 두 채널 14편에서 100% 일치한 성공공식 7항목을 기계 검사한다.
  check_final() 안에서 자동 호출된다. 눈으로 훑는 방식으로는 반드시 놓친다.
  15비트 배분표가 공백 포함 기준이었다면 CHAR_BASIS를 "include_space"로 바꾼다.
★ v12.1 — check_address(): 대사 화자를 추정해 호칭 오류를 잡는다(하인이 상전을 "며느리"라 부름).
  check_chapter_quick()·check_final()에서 자동 호출되는 하드 게이트. cast는 본문에서 자동 추출.
  경위·실측은 학습_누적.txt 2026-08-23 항목.
"""
import re

CHAR_BASIS = "exclude_space"   # "exclude_space" | "include_space"

CHAPTER_THRESHOLDS_N = {
    # v12.4 (2026-08-24) 길이 옵션 1시간/1시간30분/2시간으로 교체.
    5:  {"narration_max_run": 500, "dialogue_ratio_min": 0.25},   # 23,000자 / 1시간 (기본·최소)
    7:  {"narration_max_run": 500, "dialogue_ratio_min": 0.25},   # 34,000자 / 1시간 30분
    9:  {"narration_max_run": 500, "dialogue_ratio_min": 0.25},   # 45,000자 / 2시간
    # 하위호환 (구 2시간30분 옵션·v11 이하 대본을 다시 검증할 때만)
    6:  {"narration_max_run": 500, "dialogue_ratio_min": 0.25},
    11: {"narration_max_run": 500, "dialogue_ratio_min": 0.25},   # 구 57,000자 / 2시간 30분
}

CHARS_PER_SCENE = 425          # 1장면 ≈ 공백 제외 400~450자
CHAPTER_FLOOR_RATIO = 0.90     # 챕터 하한선 (상한은 보지 않는다). v12에서 0.85→0.90
FINAL_TOLERANCE = 0.10         # 합본 총량 ±10%

HANJA_PATTERN = re.compile(r'[一-鿿]')
META_PATTERNS = [
    re.compile(r'^\s*제?\s*\d+\s*[장화챕터]\b.*$', re.M),
    # ⚠️ 2026-08-05 — 위 패턴은 "3장·제3화"처럼 숫자가 앞에 올 때만 잡는다.
    #   실제로 채팅에 쓰이는 형태는 "챕터 3"(숫자가 뒤)이라 안 잡혔다.
    #   v10.2부터는 사용자가 화면에서 본문을 복사하므로 이 제목이 그대로 따라온다.
    #   그대로 두면 브루에서 TTS가 "챕터 삼"을 소리 내 읽는다.
    # ⚠️ 한 줄만 지워야 한다. \s 는 줄바꿈도 먹으므로 여기서는 절대 쓰지 않는다.
    #    (실수로 \s*.*$ 로 썼다가 제목 다음 본문까지 통째로 삭제된 적이 있다 — 2026-08-05)
    #    가로 공백은 [ \t]*, 줄 내용은 [^\n]* 로만 표현한다.
    re.compile(r'^[ \t]*\[?[ \t]*(챕터|챕|장|화)[ \t]*\d+[^\n]*$', re.M),
    re.compile(r'^[ \t]*Chapter[ \t]*\d+[^\n]*$', re.M | re.I),
    re.compile(r'^[ \t]*={2,}[^\n]*$', re.M),
    re.compile(r'^[ \t]*-{3,}[ \t]*$', re.M),
    re.compile(r'^[ \t]*#{1,6}[ \t][^\n]*$', re.M),
    re.compile(r'^[ \t]*\*{2,}[^\n]*\*{2,}[ \t]*$', re.M),   # **굵은 글씨 제목**
    re.compile(r'^[ \t]*\[?[ \t]*(글자수|자수)[ \t]*[:：][^\n]*$', re.M),
    # v10.2 '이어쓰기 카드' — 집필 중 화면에 남는 진행 메모. 본문이 아니므로 제거한다.
    re.compile(r'^[ \t]*\[?[ \t]*이어쓰기[ \t]*카드[^\n]*$', re.M),
    re.compile(r'^[ \t]*(장소[ \t]*[·ㆍ][ \t]*시점|직전[ \t]*상황[^\n:：]*|마지막[ \t]*두[ \t]*문장|누적)[ \t]*[:：][^\n]*$', re.M),
]
# ⚠️ 2026-08-05 실사고 — 예전엔 "년" 한 글자를 그대로 셌다.
#   등장인물 이름이 "서분년"이면 그 이름이 나올 때마다 비하 표현으로 잡혀
#   197건이 검출됐고(실제 비하는 0건), 최종 게이트가 ❌로 막혔다.
#   "작년·내년·수십 년" 같은 흔한 낱말도 전부 오탐이었다.
#   → 한 글자 매칭을 버리고, **실제 욕으로 쓰이는 꼴**만 정규식으로 잡는다.
#   ⚠️ 한글에는 \b(단어 경계)가 듣지 않는다. "이년아"의 '년' 뒤에는 경계가 없어서
#      \b 를 붙이면 실제 욕을 통째로 놓친다. 대신 **뒤에 오는 말**로 걸러낸다.
# ⚠️ 2026-08-19 실사고 2차 — "십이 년을 모셨습니다"의 "이 년"이 비하 호칭으로 잡혔다.
#   제외 목록(동안|간|째|…)에 조사 "을/를/이/가"가 없어 새어 나간 것인데,
#   조사를 계속 늘리는 방식으로는 끝이 없다 — "이년을 죽여라"(진짜 욕)와 구분이 안 되기 때문이다.
#   → 판별 기준을 **띄어쓰기**로 바꿨다. 실제 한국어에서 이게 가장 잘 갈리는 신호다.
#      비하: 이년/저년/그년   (붙여 씀)          예) 이년아, 저년이, 그년 때문에
#      시간: 이 년 / 십이 년  (띄어 씀, 앞에 숫자) 예) 십이 년을, 삼 년 뒤
#   띄어 쓴 형태는 "아/한테/에게/같은/들" 같은 확실한 욕 표지가 붙을 때만 잡는다.
#   앞에 수사(십이·삼 등)가 오면 무조건 시간 표현이므로 lookbehind로 차단한다.
_NUM_BEFORE = r'(?<![0-9일이삼사오육칠팔구십백천만몇수])'
_TIME_AFTER = r'(?!\s*(동안|간|째|여|만에|만|뒤|후|전|이나|씩|생|대|치))'
_INSULT_MARK = r'\s*(아|한테|에게|같은|들)'
DEROGATORY_PATTERNS = [
    re.compile(_NUM_BEFORE + r'[이저그]년' + _TIME_AFTER),   # 붙여 쓴 형태 = 거의 항상 비하
    re.compile(r'[이저그]\s+년' + _INSULT_MARK),             # 띄어 썼으면 욕 표지 필수
    re.compile(r'년\s*놈'),                                   # 년놈
    re.compile(r'[이저그]\s*놈'),                             # 이놈 / 저놈 / 그놈
    re.compile(r'새끼'),
]

def count_derogatory(text):
    """비하 호칭 실제 사용 횟수. 인명·시간표현에 든 '년'은 세지 않는다."""
    return sum(len(p.findall(text)) for p in DEROGATORY_PATTERNS)
TIME_TRANSITIONS = ["그때였습니다", "며칠 후", "세월이 흘러", "어느덧"]
# v11 — 채널A·채널C 14편 실측 그대로. 검사 시 공백을 무시하므로 띄어쓰기 차이는 통과된다.
FIXED_ENDING = (
    "다음 영상을 빠르게 만나 보시려면 좋아요와 구독을 눌러 주세요.\n"
    "지금 화면에 나오는 더 재미있는 영상들도 함께 해 주세요.\n"
    "그럼 모두 행복한 하루 보내세요. 감사합니다."
)
FIXED_TRANSITION = "자, 그럼 오늘도 감동적인 옛날 이야기 지금 바로 시작합니다."
FIXED_OPENING_CTA = "구독과 좋아요를 눌러 주시고 어디서 듣고 계신지 댓글에 남겨 주세요."

# 오프닝 5문장 훅 4문형 (모티프_뱅크.txt H1~H4). 3연속 동일 문형 금지 판정에도 쓴다.
HOOK_PATTERNS = {
    "H1": re.compile(r'그런데[^.!?]{0,140}?몰랐'),
    "H2": re.compile(r'그런데[^.!?]{0,140}?진짜\s*이유[^.!?]{0,20}?따로'),
    "H3": re.compile(r'그런데[^.!?]{0,140}?비밀[^.!?]{0,20}?숨어'),
    "H4": re.compile(r'그런데[^.!?]{0,140}?(시작한|시작된|무너지기\s*시작)[^.!?]{0,20}?날이었'),
}

# 나이 표기 — TTS가 제대로 읽도록 한글 수사를 기본으로 하되 아라비아 숫자도 인정한다.
AGE_PATTERN = re.compile(
    r'(\d+\s*살'
    r'|[한두세네]\s*살|다섯\s*살|여섯\s*살|일곱\s*살|여덟\s*살|아홉\s*살'
    r'|열[한두세네]?\s*살|열다섯\s*살|열여섯\s*살|열일곱\s*살|열여덟\s*살|열아홉\s*살'
    r'|스[무물][^\s]{0,2}\s*살|서른[^\s]{0,2}\s*살|마흔[^\s]{0,2}\s*살|쉰[^\s]{0,2}\s*살'
    r'|예순[^\s]{0,2}\s*살|일흔[^\s]{0,2}\s*살|여든[^\s]{0,2}\s*살|아흔[^\s]{0,2}\s*살'
    r'|나이는\s*[^\s.,]{1,6})'
)

CLIFFHANGER_PATTERN = re.compile(r'(몰랐습니다|몰랐지요|알지\s*못했습니다|알\s*리\s*없었)')

# v12.14 — 포워드 리퍼런스 훅(모티프_뱅크.txt F열). 타 장르(재테크 유튜브) 구조 분석에서
# 역수입한 참고 패턴이다. 클리프행어(사후 암시: "그때는 몰랐습니다")와 달리
# 사전에 명시적으로 찌르는 예고형("이건 뒤에 벌어질 일에 비하면 아무것도 아니었습니다").
# ★ 40편 실측 기반이 아니라 교차 장르 사례 1건에서 나온 것이라 하드 게이트로 쓰지 않는다.
#   check_final()/check_chapter_quick()에 넣지 않고, 참고용 카운터 함수만 별도로 둔다.
FORWARD_REF_PATTERN = re.compile(r'(비하면\s*아무것도\s*아니|아직\s*나오지도\s*않았|시작에\s*불과)')


def count_forward_ref(text):
    """포워드 리퍼런스 훅(F열) 사용 횟수. 참고용 — 게이트가 아니다."""
    return len(FORWARD_REF_PATTERN.findall(text))


def _nospace(t):
    return re.sub(r'\s', '', t)


# ---------------------------------------------------------------- 공통 유틸

def count_chars(text):
    """v10.1 표준 글자수. 기본은 공백 제외."""
    if CHAR_BASIS == "include_space":
        return len(text)
    return len(re.sub(r'\s', '', text))


def scenes_for(target_chars):
    """목표 글자수 → 지시할 장면 수 범위."""
    base = target_chars / CHARS_PER_SCENE
    return (int(base * 0.95), int(base * 1.10) + 1)


def next_chapter_scenes(base_scenes, target_cum, actual_cum):
    """피드포워드 보정 — 이미 쓴 것을 고치지 않고 다음 챕터 목표를 올린다."""
    if actual_cum <= 0:
        return base_scenes
    ratio = target_cum / actual_cum
    ratio = max(0.85, min(ratio, 1.35))          # 과보정 방지
    return int(base_scenes * ratio + 0.999)


def _sentence_split(text):
    return [s for s in re.split(r'(?<=[.!?」"])\s+', text.strip()) if s]


# ---------------------------------------------------------------- 자동교정

def _fix_quotes(text):
    """따옴표 개수가 홀수면 마지막 여는 따옴표를 닫아준다."""
    if text.count('"') % 2 == 0:
        return text
    lines = text.split('\n')
    for i in range(len(lines) - 1, -1, -1):
        if lines[i].count('"') % 2 == 1:
            lines[i] = lines[i].rstrip() + '"'
            break
    return '\n'.join(lines)


def _dedupe_time_transitions(text):
    """같은 시간 전환구가 2회 이상이면 첫 번째만 남긴다.

    2026-08-25 버그 수정 — 예전에는 전환구가 문장 중간에 있어도 그 낱말만 뽑아내서
    "어느덧 3년이 지났습니다" → "3년이 지났습니다"처럼 문장을 깨뜨렸다.
    (사용자 보고: 깨진 문장을 찾아 복구하는 데 시간이 들었다.)
    이제 **전환구가 문장 전체이거나 문장 맨 앞에 올 때만** 지운다.
    문장 중간에 박힌 것은 건드리지 않는다 — 지우면 뜻이 무너진다.
    """
    for term in TIME_TRANSITIONS:
        if text.count(term) < 2:
            continue
        first = text.find(term)
        head, tail = text[:first + len(term)], text[first + len(term):]
        # 문장 시작 위치(줄머리 또는 문장부호 뒤)에 있는 것만 제거 대상으로 본다.
        # 뒤에 조사·명사가 바로 붙는 경우("어느덧 3년이")는 문장 일부이므로 남긴다.
        tail = re.sub(
            r'(?<=[.!?"\n])(\s*)' + re.escape(term) + r'\s*\.\s*',
            r'\1', tail)
        text = head + tail
    return re.sub(r'\.\s*\.', '.', text)


def autofix(text):
    """AI 판단 0회. 기계적 결함만 무조건 치환한다."""
    text = HANJA_PATTERN.sub('', text)
    for p in META_PATTERNS:
        text = p.sub('', text)
    text = _fix_quotes(text)
    text = _dedupe_time_transitions(text)
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


# ---------------------------------------------------------------- 챕터 (3항목만)

def check_chapter_light(text, target):
    """v10.1 챕터 검증 — 하한선과 훅만 본다. 상한은 보지 않는다.

    챕터는 완성 영상에 존재하지 않는 단위이므로(부록 A) ±10% 게이트를 걸 이유가 없다.
    나머지 12개 항목은 check_final()에서 한 번에 검증한다.
    """
    n = count_chars(text)
    tail = text.strip()[-200:]
    hook = bool(re.search(r'[?？]|것이었습니다|몰랐습니다|시작되었습니다|않았습니다', tail))
    return {
        "글자수_실측": n,
        "하한_통과": n >= target * CHAPTER_FLOOR_RATIO,
        "이탈방어_훅": hook,          # False면 마지막 1~2문장만 부분 수정
    }


# ------------------------------------------------- 챕터 즉시 검사 (v12 신설)

def check_chapter_quick(text, target, cast=None, ages=None):
    """챕터를 쓴 직후 1회 실행한다. 눈으로는 절대 못 잡는 것만 본다.

    2026-08-19 실사고: 챕터마다 "약 5,000자"라고 자체 보고했는데 실측 평균 1,780자였다
    (목표의 37%). 집필 중 파이썬을 금지해 둔 탓에 셀 수단이 없어 눈대중으로 답한 것이다.
    글자수는 사람도 모델도 눈으로 못 센다. 세는 일은 코드가 한다 — 그래서 이 함수를 만들었다.

    '더써야_할_자수'가 0보다 크면 그 응답 안에서 계속 이어 쓴 뒤 다시 돌린다.
    """
    n = count_chars(text)
    floor = int(target * 0.90)
    sentences = _sentence_split(text)
    runs = _find_desu_runs(sentences)
    dialogue = sum(count_chars(m) for m in re.findall(r'"[^"]*"', text))

    r = {
        "글자수": n,
        "목표": target,
        "달성률(%)": round(n / target * 100) if target else 0,
        "하한_통과": n >= floor,
        "더써야_할_자수": max(0, floor - n),
        "추가_장면수": max(0, -(-(floor - n) // CHARS_PER_SCENE)),
        "습니다_3연속_건수": len(runs),
        "습니다_3연속_예": [sentences[i][:30] for i in runs[:5]],
        "비하_호칭_수": count_derogatory(text),
        "대사_비중": round(dialogue / n, 3) if n else 0,
    }
    # v13 — 호칭 검사. 챕터 단계에서 잡아야 뒤 챕터가 틀린 호칭을 그대로 물려받지 않는다.
    addr = check_address(text, cast)
    r["호칭_위반_수"] = addr["호칭_위반_수"]
    r["호칭_위반"] = addr["호칭_위반"]
    r["호칭_주의_수"] = addr["호칭_주의_수"]
    r["화자_미상_비율"] = addr["화자_미상_비율"]
    # v12.7 — 성씨 정합성(친남매인데 성씨 다름). 챕터 단계에서 잡는다.
    sur = check_surnames(text, list(cast) if cast else None)
    r["성씨_위반_수"] = sur["성씨_위반_수"]
    r["성씨_위반"] = sur["성씨_위반"]
    # v12.8 — 나이 개연성(부모-자식·조손 나이차). ages={"이름": 나이} 를 넘겨야 검사한다.
    age_r = check_age_arithmetic(text, ages)
    r["나이_위반_수"] = age_r["나이_위반_수"]
    r["나이_위반"] = age_r["나이_위반"]
    r["통과"] = (r["하한_통과"] and r["습니다_3연속_건수"] == 0
                 and r["비하_호칭_수"] <= 2 and r["대사_비중"] >= 0.25
                 and r["호칭_위반_수"] == 0 and r["성씨_위반_수"] == 0
                 and r["나이_위반_수"] == 0)
    return r


# ---------------------------------------------------------------- 합본 (전체 1회)

def _find_desu_runs(sentences):
    """~습니다 계열 3연속(2개까지만 허용) 위치."""
    violations, run = [], 0
    for i, s in enumerate(sentences):
        if s.rstrip('."\'”’').endswith(('습니다', '였습니다', '했습니다')):
            run += 1
            if run >= 3:
                violations.append(i)
        else:
            run = 0
    return violations


def check_final(text, target, total_chapters, cast=None, ages=None):
    """검증 전체를 합본에서 1회 실행한다."""
    r = {}
    th = CHAPTER_THRESHOLDS_N.get(total_chapters, CHAPTER_THRESHOLDS_N[7])
    n = count_chars(text)

    r["글자수_실측"] = n
    r["글자수"] = abs(n - target) / target <= FINAL_TOLERANCE
    r["부족분_장면수"] = max(0, int((target * 0.95 - n) / CHARS_PER_SCENE + 0.999))
    r["한자_잔존"] = not bool(HANJA_PATTERN.search(text))
    r["메타_정보"] = not any(p.search(text) for p in META_PATTERNS)
    r["따옴표_짝"] = text.count('"') % 2 == 0

    sentences = _sentence_split(text)
    r["습니다_3연속"] = len(_find_desu_runs(sentences)) == 0
    r["비하_호칭_수"] = count_derogatory(text)
    r["비하_호칭"] = r["비하_호칭_수"] <= 2
    r["시간_표현_중복"] = not any(text.count(t) >= 2 for t in TIME_TRANSITIONS)

    blocks = re.split(r'"[^"]*"', text)
    r["나레이션_연속"] = max((count_chars(b) for b in blocks), default=0) <= th["narration_max_run"]

    dialogue = sum(count_chars(m) for m in re.findall(r'"[^"]*"', text))
    r["대사_비중_실측"] = round(dialogue / n, 3) if n else 0
    r["대사_비중"] = r["대사_비중_실측"] >= th["dialogue_ratio_min"]

    r["고정_마무리_멘트"] = _nospace(FIXED_ENDING) in _nospace(text)

    # ------------------------------------------------------------------
    # v11 문체 지표 — 게이트가 아니라 참고치다.
    #   두 채널 14편을 편별로 재보니 편차가 매우 컸다(아래 주석의 실측 범위 참조).
    #   그런데도 전부 상위작이다. 즉 이 수치를 맞춰서 터진 게 아니다.
    #   따라서 값은 항상 보고하되, 실패(bool)로 잡는 것은 극단값일 때뿐이다.
    # ------------------------------------------------------------------

    # 25자 이상 문장 비율 — 편별 실측 4~34%. v10의 "10% 이하"는 실측과 맞지 않아 폐기.
    long_sents = [x for x in sentences if count_chars(x) >= 25]
    r["25자이상_비율"] = round(len(long_sents) / len(sentences), 3) if sentences else 0
    r["25자이상_비율_정상"] = r["25자이상_비율"] <= 0.35        # 35% 초과일 때만 실패

    # 종결어미 비율 — 편별 실측 13~97%. 성적과 무관해 게이트로 쓰지 않는다(수치만 보고).
    desu = len(re.findall(r'습니다[.!?]', text))
    jiyo = len(re.findall(r'지요[.!?]', text))
    r["종결어미_습니다비율"] = round(desu / (desu + jiyo), 3) if (desu + jiyo) else 0

    # 문장 평균 길이 — 편별 실측 14.3~21.1자. 극단일 때만 실패.
    r["문장_평균길이"] = round(sum(count_chars(x) for x in sentences) / len(sentences), 1) if sentences else 0
    r["문장_평균길이_정상"] = 12.0 <= r["문장_평균길이"] <= 24.0

    # 클리프행어 — 이 패턴 기준 편별 실측 1~13회(중앙 4회). 14편 전부 1회 이상이었다.
    #   3회 이상으로 걸었더니 상위작 3편이 걸렸다. 성공 요인이 아니므로 하한은 1회만 둔다.
    r["클리프행어_수"] = len(CLIFFHANGER_PATTERN.findall(text))
    r["클리프행어"] = r["클리프행어_수"] >= 1

    # v12.14 — 포워드 리퍼런스(F열) 사용 횟수. 게이트 아님, 참고 보고만.
    r["포워드리퍼런스_수"] = count_forward_ref(text)

    r.update(check_formula(text))

    # v13 — 호칭 검사(게이트 A군). 예전엔 _수동확인_필요에 있었는데
    #   절약모드에서는 사람이 훑을 기회가 없어 3편 연속 오류가 그대로 나갔다.
    addr = check_address(text, cast)
    r["호칭_위반_수"] = addr["호칭_위반_수"]
    r["호칭_위반"] = addr["호칭_위반"]
    r["호칭_주의_수"] = addr["호칭_주의_수"]
    r["호칭_주의"] = addr["호칭_주의"]
    r["화자_미상_비율"] = addr["화자_미상_비율"]
    r["호칭_검사"] = addr["호칭_검사_통과"]

    # v12.7 — 성씨 정합성(게이트 A군). 친남매인데 성씨가 다르면 무조건 고친다.
    sur = check_surnames(text, list(cast) if cast else None)
    r["성씨_위반_수"] = sur["성씨_위반_수"]
    r["성씨_위반"] = sur["성씨_위반"]
    r["성씨_검사"] = sur["성씨_검사_통과"]

    # v12.8 — 나이 개연성(게이트 A군). 예전엔 "_수동확인_필요"에 있었다 —
    #   절약모드에서 사람이 안 보면 검사가 안 도는 2026-08-23 호칭 사고와 같은 구멍이었다.
    age_r = check_age_arithmetic(text, ages)
    r["나이_위반_수"] = age_r["나이_위반_수"]
    r["나이_위반"] = age_r["나이_위반"]
    r["나이_검사"] = age_r["나이_검사_통과"]

    r["모두_통과"] = all(v for k, v in r.items() if isinstance(v, bool))
    r["_수동확인_필요"] = [
        "비트별_분량_±20%", "복선_회수(①⑮/②⑫/⑦⑬/상징물3회)",
        "피날레_5단계", "한자어_비율_60%이하",
        "주제문_②에서_심고_엔딩에서_회수(뜻: 태어남이 아니라 살아감)",
    ]
    return r


# ------------------------------------------------- v11 성공공식 검사 (게이트 A군)

def check_formula(text):
    """채널A·채널C 14편에서 예외 없이 지켜진 항목만 기계 검사한다.

    여기서 실패가 나오면 수치 항목과 달리 "보고 후 판단"이 아니라 무조건 고친다.
    두 채널이 100% 지킨 것들이라, 하나라도 빠지면 이 채널 결의 대본이 아니게 된다.
    눈으로 훑으면 반드시 놓치므로 check_final() 안에서 자동 호출한다.
    """
    r = {}
    head = text.strip()[:700]          # 인트로 6문장 구간
    ns = _nospace(text)

    # 1. 오프닝 첫 문장이 인물의 대사인가 (나레이션 시작 금지)
    r["공식_오프닝_대사시작"] = text.strip().startswith('"')

    # 2. 나이를 인트로 안에서 명시했는가
    r["공식_나이_명시"] = bool(AGE_PATTERN.search(head))

    # 3. "그런데 ~" 훅 문형 — 어느 문형을 썼는지도 돌려준다(scripts.txt 기록용)
    hooks = [k for k, pat in HOOK_PATTERNS.items() if pat.search(head)]
    r["공식_훅_문형"] = hooks or None
    r["공식_훅_존재"] = bool(hooks)

    # 4. 구독 유도는 오프닝 1회 + 엔딩 1회뿐. 중간 CTA가 있으면 실패.
    r["공식_구독_횟수"] = text.count("구독")
    r["공식_중간CTA_없음"] = r["공식_구독_횟수"] == 2

    # 5. 전환 문구 정확 일치
    r["공식_전환문구"] = _nospace(FIXED_TRANSITION) in ns

    # 6. 오프닝 구독 멘트 정확 일치
    r["공식_오프닝_구독멘트"] = _nospace(FIXED_OPENING_CTA) in ns

    # 7. 본편 도입 틀 — 전환 문구 직후 "옛날 옛적 ~ 살고 있었습니다"
    pos = ns.find(_nospace(FIXED_TRANSITION))
    body_head = ns[pos:pos + 300] if pos >= 0 else ""
    r["공식_본편_도입틀"] = ("옛날" in body_head) and bool(
        re.search(r'(살고있었습니다|살았습니다|있었습니다)', body_head))

    return r


# ============================ 40씬 분할 (v12.6) ============================
# 출력 형식은 '브루 자동매칭' 앱(v2.5+) 입력 규격을 그대로 따른다.
#   · 태그는 [img:001] — **3자리 제로패딩**. 앱 사용법.txt "대본 태그 예시" 기준.
#     (v12.5까지 [img:1]로 뽑아서 앱에 그대로 넣을 수 없었다. 2026-08-25 수정)
#   · 태그는 단독 줄, 다음 줄부터 그 구간 원문.
#   · 빈 블록([img:N] 다음에 본문이 없는 것) 금지 — 앱이 누락으로 검출한다.

def split_scenes(text, n=40, intro_anchor=FIXED_TRANSITION):
    """본문(인트로 제외)을 n개 씬으로 자르고 각 씬 앞에 [img:001] 형식 태그를 붙인다.

    부록_양식.txt 부록 B 규격 + 브루 자동매칭 앱 입력 규격.
    문장 끝에서만 자르고, 태그를 전부 지우면 원문과 글자 단위로 100% 일치해야 한다
    (verify_scenes 로 검산).
    """
    ns = _nospace(text)
    pos = ns.find(_nospace(intro_anchor))
    body = text
    if pos >= 0:                       # 인트로를 잘라낸다 — 공백 무시 위치를 원문 위치로 환산
        target, cnt = pos + len(_nospace(intro_anchor)), 0
        for i, ch in enumerate(text):
            if not ch.isspace():
                cnt += 1
                if cnt == target:
                    body = text[i + 1:]
                    break
    body = body.lstrip('\n')

    sents = [x for x in re.split(r'(?<=[.!?])(?=\s|$)', body) if x.strip()]
    if not sents:
        return "", body
    total = sum(count_chars(x) for x in sents)
    per = total / n if n else total

    # 누적 글자수가 (씬번호+1)*per 를 넘으면 끊는다 — 씬 크기가 고르게 나온다.
    scenes, cur, acc = [], [], 0
    for idx, x in enumerate(sents):
        cur.append(x)
        acc += count_chars(x)
        remain_sents = len(sents) - idx - 1
        remain_scenes = n - len(scenes) - 1
        if remain_scenes <= 0:
            continue
        if acc >= per * (len(scenes) + 1) or remain_sents <= remain_scenes:
            scenes.append(''.join(cur)); cur = []
    if cur:
        scenes.append(''.join(cur))
    while len(scenes) > n:
        scenes[-2] += scenes[-1]; scenes.pop()

    out = []
    for i, sc in enumerate(scenes, 1):
        out.append(f"[img:{i:03d}]")       # 브루 자동매칭 앱 규격 — 3자리 제로패딩
        out.append(sc.strip('\n'))
        out.append("")                     # 블록 사이 빈 줄(앱 사용법의 태그 예시와 동일)
    return '\n'.join(out).rstrip() + '\n', body


def verify_scenes(scenes_text, body):
    """태그를 전부 제거한 결과가 본문과 글자 단위로 일치하는지 검산한다.

    브루 자동매칭 앱 입력 규격까지 같이 본다 — 3자리 태그 / 빈 블록 없음 /
    각 블록 첫 문장이 매칭 니들로 쓸 만큼 긴가(앱은 12자 이상을 [정확] 매칭으로 친다).
    """
    tag_re = re.compile(r'^\[img:(\d{3})\]$', re.M)
    stripped = re.sub(r'^\[img:\d+\]\n?', '', scenes_text, flags=re.M)
    ok = _nospace(stripped) == _nospace(body)

    # 블록별 본문을 갈라 빈 블록·짧은 시작문장을 찾는다
    parts = re.split(r'^\[img:\d+\]$', scenes_text, flags=re.M)[1:]
    empty, weak = [], []
    for i, p in enumerate(parts, 1):
        p = p.strip()
        if not p:
            empty.append(i)
            continue
        first = next((ln.strip() for ln in p.splitlines() if ln.strip()), "")
        if count_chars(first) < 12:        # 앱 [정확] 매칭 기준
            weak.append((i, first[:20]))

    nums = [int(m) for m in tag_re.findall(scenes_text)]
    return {
        "씬_수": len(nums),
        "원문_일치": ok,
        "본문_글자수": count_chars(body),
        "복원_글자수": count_chars(stripped),
        # ── 브루 자동매칭 앱 규격 ──
        "태그_3자리": len(nums) == len(re.findall(r'^\[img:\d+\]$', scenes_text, flags=re.M)),
        "번호_연속": nums == list(range(1, len(nums) + 1)),
        "빈_블록": empty,
        "짧은_시작문장": weak,
        "앱_규격_통과": ok and not empty and nums == list(range(1, len(nums) + 1)),
    }


# ========================= 타임테이블 (v12.3) =========================
# 낭독 속도 실측치로 챕터 시작 시각을 계산한다. 눈대중 금지 — 글자수와 같은 이유다.
READ_CHARS_PER_MIN = 378        # 브루 '자비 왕후' 실측(2026-08-19).
# ★ 브루에서 목소리나 속도를 바꾸면 이 값이 달라진다.
#   1편 뽑아 (공백 제외 실제 자수 ÷ 실제 분수)로 다시 구해 넘긴다.

# 유튜브 챕터 규칙 — 하나라도 어기면 챕터가 아예 안 붙는다.
YT_MIN_CHAPTERS = 3
YT_MIN_SECONDS = 10


def _mmss(sec):
    sec = max(0, int(round(sec)))
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def timetable(sections, cpm=READ_CHARS_PER_MIN, offset_sec=0):
    """sections = [(제목, 본문), ...] 또는 [(제목, 글자수), ...] → (타임테이블 문자열, 검증)

    본문을 넘기면 공백 제외 글자수를 직접 센다. 숫자를 넘기면 그 값을 쓴다.
    offset_sec — 대본 앞에 별도 인트로 영상을 붙였다면 그 길이(초)를 넣는다.
    """
    rows, t = [], float(offset_sec)
    for title, src in sections:
        n = src if isinstance(src, int) else count_chars(src)
        rows.append({"제목": str(title).strip(), "시작초": t, "글자수": n,
                     "길이초": n / cpm * 60})
        t += n / cpm * 60

    lines = [f"{_mmss(r['시작초'])} {r['제목']}" for r in rows]
    short = [f"{r['제목']}({int(r['길이초'])}초)" for r in rows if r["길이초"] < YT_MIN_SECONDS]
    v = {
        "구간_수": len(rows),
        "총_길이": _mmss(t),
        "총_글자수": sum(r["글자수"] for r in rows),
        "첫_구간_0시작": bool(rows) and rows[0]["시작초"] == 0,
        "최소_3구간": len(rows) >= YT_MIN_CHAPTERS,
        "10초_미만_구간": short,
        "낭독속도_기준": f"{cpm}자/분",
    }
    v["유튜브_규칙_통과"] = (v["첫_구간_0시작"] and v["최소_3구간"] and not short)
    return "\n".join(lines), v


# ==================== 성씨·연령 정합성 (v12.7 신설) ====================
# 사고(2026-08-25 수강생 제보):
#   "주인공이 임씨 성인데 친 오라비는 서씨입니다" — 친남매인데 성씨가 다름.
#   "할멈인데 애들 부르듯 부르고"                — 노인을 아이 취급 호칭으로 부름.
# 원인: name_picker.py가 인물마다 성씨를 독립 무작위로 뽑았고(가족 개념 없음),
#       인물표에 나이·혈연 칸이 없어 연령에 맞는 호칭을 강제할 근거가 없었다.

SURNAME_CHARS = "김이박최정강조윤장임한오서신권황안송류배백허남심노하곽성차주우구민유"

# 혈연(성씨 공유) 관계어 — 이 말로 이어진 두 인물은 성씨가 같아야 한다.
# v12.10.1 — "어머니"·"아들"·"딸"·"손자"·"손녀"는 뺐다. 자식은 아버지 성을 따르지만
# 어머니는 친정 성을 그대로 쓰는 게 이 시대 정상이라(조선시대 여성은 혼인 후에도 원래 성을
# 유지) "어머니"만 있으면 성씨가 달라야 정상이다. "아들"·"딸"·"손자"·"손녀"는 문장에 부·모
# 어느 쪽이 같이 나왔는지 코드가 구분 못 해 같은 위험이 있어 함께 뺐다 — 실제로 "어머니"가
# 남아 있을 때 정상적으로 성씨를 다르게 쓴 대본에서 오탐이 났다(003_상단안주인 실측).
# "아버지"·"아비"만 남긴다 — 부계 성 승계는 예외 없이 성립하므로 안전하다.
BLOOD_RELATIONS = ("오라비", "오라버니", "누이", "누님", "언니", "형", "아우", "동생",
                   "아버지", "아비")
# 혼인으로 맺어진 관계 — 성씨가 **달라야** 정상이다(친정 성을 유지하므로).
MARRIAGE_RELATIONS = ("남편", "아내", "지아비", "지어미", "며느리", "사위",
                      "시아버지", "시어머니", "장인", "장모", "올케", "동서")

def check_surnames(text, cast_names=None):
    """혈연 관계로 묶인 인물들의 성씨가 일치하는지 검사한다.

    **인물 이름을 추측하지 않는다.** 조사 붙은 어절을 이름으로 오인하면 오탐만 쏟아진다
    (1차 구현에서 "임분이에"·"오라비"를 이름으로 잡았다).
    그래서 story_bible 인물표의 실제 이름 목록(cast_names)을 받아 그 이름만 대조한다.
    목록을 안 주면 본문에서 '성+이름' 3글자가 2회 이상 반복되는 것만 이름으로 본다.
    """
    if not cast_names:
        # ★ 인물표(cast_names)가 없으면 검사하지 않는다. (2026-08-25 2차 수정)
        #   1차 구현은 본문에서 '성+2글자' 토큰을 자동 추출했는데, "오빠가"·"정류장"·"이었습"
        #   같은 일반 어절을 사람 이름으로 잡아 실제 대본 25편 중 2편에서 오탐이 났다.
        #   한국어는 성씨 글자가 흔한 낱말에도 널려 있어 이름만 보고는 못 가른다.
        #   → 추측하지 않고, 이름 목록을 받았을 때만 검사한다. 놓치는 편이 틀리는 것보다 낫다.
        return {"성씨_위반_수": 0, "성씨_위반": [], "성씨_검사_통과": True,
                "검사한_인물": [], "검사_생략": "인물표 없음 — cast_names 를 넘겨야 검사한다"}
    cast_names = [n for n in cast_names if len(n) >= 2]
    if len(cast_names) < 2:
        return {"성씨_위반_수": 0, "성씨_위반": [], "성씨_검사_통과": True,
                "검사한_인물": cast_names}

    fails = []
    for sent in _sentence_split(text):
        rel = next((r for r in BLOOD_RELATIONS if r in sent), None)
        if not rel:
            continue
        # 혼인 관계어가 같이 있으면 성씨가 달라도 정상이므로 건너뛴다
        if any(m in sent for m in MARRIAGE_RELATIONS):
            continue
        found = [n for n in cast_names if n in sent]
        surnames = {n[0] for n in found}
        if len(found) >= 2 and len(surnames) >= 2:
            fails.append({
                "문장": sent.strip()[:60],
                "관계": rel,
                "이름": found[:4],
                "성씨": sorted(surnames),
                "고칠_방향": f'"{rel}"로 이어진 사이인데 성씨가 다르다({"/".join(sorted(surnames))}). '
                             f'피가 섞였으면 성씨를 같게 맞춘다 — 혼인으로 맺어진 사이면 정상이다',
            })
    return {
        "성씨_위반_수": len(fails),
        "성씨_위반": fails,
        "성씨_검사_통과": not fails,
        "검사한_인물": cast_names,
    }


# 부모-자식 관계어 — 이 사이는 나이 차가 충분해야 한다
PARENT_CHILD_RELATIONS = ("아들", "딸", "어머니", "아버지", "어미", "아비", "친어머니", "친아버지")
# 조손 관계어 — 두 세대가 벌어져야 한다
GRANDPARENT_RELATIONS = ("손자", "손녀", "손주", "할머니", "할아버지")
MIN_PARENT_GAP = 13     # 집필규칙_통합.md 기준(부모-자식 13세 이상)
MIN_GRANDPARENT_GAP = 26  # 부모 세대 갭의 2배로 본다


def check_age_arithmetic(text, cast_ages=None):
    """부모-자식·조손 나이 개연성을 검사한다 (v12.8 신설).

    check_final()의 '_수동확인_필요' 목록에 "인물 나이 산수"가 계속 남아 있었다 —
    2026-08-23 호칭 사고와 같은 리스크 패턴이다(사람이 봐야 하는 항목은 절약모드에서 새어 나간다).
    인물표에 이미 나이 칸이 있으므로(부록_양식.txt 2번) 그 값을 cast_ages로 넘기면 자동 검사된다.

    cast_ages: {"이름": 나이(int)}. 안 넘기면 검사를 생략한다 — 나이를 본문에서 추측하지 않는다
    (성씨 검사와 같은 원칙: 추측하면 오탐이 난다).
    """
    if not cast_ages:
        return {"나이_위반_수": 0, "나이_위반": [], "나이_검사_통과": True,
                "검사_생략": "인물표 없음 — cast_ages 를 넘겨야 검사한다"}

    names = [n for n in cast_ages if len(n) >= 2]
    fails = []
    for sent in _sentence_split(text):
        for rel_group, min_gap in ((PARENT_CHILD_RELATIONS, MIN_PARENT_GAP),
                                    (GRANDPARENT_RELATIONS, MIN_GRANDPARENT_GAP)):
            rel = next((r for r in rel_group if r in sent), None)
            if not rel:
                continue
            found = [n for n in names if n in sent]
            if len(found) < 2:
                continue
            ages = [(n, cast_ages[n]) for n in found[:2]]
            gap = abs(ages[0][1] - ages[1][1])
            if gap < min_gap:
                fails.append({
                    "문장": sent.strip()[:60],
                    "관계": rel,
                    "인물": [f"{n}({a}세)" for n, a in ages],
                    "나이차": gap,
                    "기준": min_gap,
                    "고칠_방향": f'"{rel}" 관계인데 나이차가 {gap}세뿐이다(기준 {min_gap}세 이상). '
                                 f'인물표의 나이를 다시 맞추거나 관계를 다른 것으로 바꾼다',
                })
    return {
        "나이_위반_수": len(fails),
        "나이_위반": fails,
        "나이_검사_통과": not fails,
    }


# 구버전 호환
remove_meta = autofix


# ============================ 호칭 검사 (v12.1) ============================
# 호칭은 화자의 신분이 아니라 화자↔청자의 관계가 정한다.
# 규칙 본체 = 집필규칙_통합.md V-5-1 / 사고 경위 = 학습_누적.txt 2026-08-23.

# 신분이 낮은 인물을 가리키는 말 (화자 판별용)
SERVANT_WORDS = (
    "유모", "여종", "계집종", "몸종", "종년", "종놈", "하녀", "하인", "머슴", "노비",
    "침모", "찬모", "무수리", "시녀", "행랑어멈", "어멈", "할멈", "부엌데기", "종",
)
# 상전(주인 계층)을 가리키는 말
MASTER_WORDS = (
    "대감", "영감", "마님", "마나님", "안주인", "주인", "나리", "아씨", "도련님",
    "아기씨", "상전", "판서", "참판", "현감", "사또", "원님",
)

# FAIL — 주인집 가족 구성을 전제하는 말. 하인은 청자가 누구든 쓸 수 없다.
KINSHIP_ONLY_TERMS = (
    "며느리", "며늘", "새아기", "새악시", "사위", "올케", "동서", "시누이",
    "처남", "처제", "처형", "장인", "장모", "시아버지", "시어머니", "제수", "형수",
)
# WARN — 하인끼리는 "형님·누님"이 정상이고 하인에게도 제 부모가 있다. 사람이 판정한다.
KINSHIP_AMBIGUOUS_TERMS = (
    "아버님", "어머님", "형님", "아우님", "누님", "오라버니", "서방님", "아주버님",
)
# WARN — 상전에게 썼으면 오류, 하인끼리면 정상. 청자를 코드가 모르므로 FAIL로 올리지 않는다.
CONDESCENDING_TERMS = ("자네", "이보게", "여보게", "그대")
# 하인이 상전에게 쓰는 정상 호칭 (참고용 · 보고서에 같이 낸다)
SERVANT_PROPER_TERMS = ("아씨", "마님", "작은마님", "큰마님", "대감마님", "나리",
                        "도련님", "아기씨", "어르신", "영감마님")
# 하인의 정상 자칭
SERVANT_SELF_TERMS = ("소인", "쇤네", "소녀", "소생", "이 몸")
# 상전이 아랫사람에게 쓰면 안 되는 존대 호칭
MASTER_FORBIDDEN_TERMS = ("마님", "아씨", "대감마님", "나리", "도련님", "어르신")

# ── 연령 호칭 (2026-08-25 신설) ──────────────────────────────────
# 사고: "할멈인데 애들 부르듯 부르고" — 노인을 아이 취급 호칭으로 불렀다.
# 나이는 신분과 별개 축이다. 종이어도 예순이면 아이 부르듯 부르지 않는다.
ELDER_WORDS = ("할멈", "할범", "할미", "노파", "노인", "영감", "어멈", "어르신",
               "늙은이", "할머니", "할아버지", "노친")
# 아이에게만 쓰는 호칭·어투. 위 노인 인물에게 쓰면 오류다.
CHILD_ADDRESS_TERMS = ("얘야", "아가", "아가야", "이 녀석", "요 녀석", "꼬마",
                       "애야", "어린것", "이놈아", "요놈", "고놈")
# 노인에게 쓰는 정상 호칭 (대체안으로 제시한다)
ELDER_PROPER_TERMS = ("할멈", "어멈", "노인장", "어르신", "할머니", "영감")

# 화자 귀속에 쓰는 발화 동사
_SPEECH_VERB = (r'(말했|말하|말할|말문|물었|묻|되물었|외쳤|소리쳤|답했|대답|대꾸|덧붙|'
                r'중얼|읊조|타일렀|호통|꾸짖|다그쳤|속삭|입을\s*열|목소리|여쭈|아뢰|'
                r'소곤|수군|쑥덕|뇌까|되뇌|되받|반문|부르짖|울부짖|하소연|내뱉|타이르|일렀|고했|아뢰었|여쭈었|읊었|'
                r'귀띔|알려|알렸|일러주|귀엣말|언성을\s*높였|목청을\s*높였|소리를\s*높였|다짐했|다짐하)')
# "…" 뒤에 화자가 오는 꼴:  "대사" 하고 유모가 말했습니다 / "대사" 유모가 물었습니다
_SPEECH_VERB_RE = re.compile(_SPEECH_VERB)
# 발화 동사가 없어도 화자를 특정해 주는 동작 서술("…따라 나왔습니다." + 다음 줄 대사).
_ACTION_VERB_RE = re.compile(
    r'(나왔|나섰|나가|다가[섰가]|들어[섰왔]|일어[섰나]|달려|쫓아|따라|섰습니다|앉았|엎드|'
    r'무릎|고개를|허리를|손을|눈물|울먹|한숨|헛기침|혀를|이를 악|주먹|붙들|잡았|가로막|'
    r'돌아보|바라보|노려보|내려다보|올려다보|웃었|웃으며|한참을|치맛자락|소맷자락)')
# 주격조사가 붙은 명사 — "유모가", "대감이", "삼월이는". 화자 후보다.
# 앞 어절까지 잡는다 — "유모 삼월이가"에서 '삼월이'만 떼면 신분이 날아간다.
_SUBJECT_RE = re.compile(r'((?:[가-힣]{1,6}\s)?[가-힣]{1,10}?)(?:이|가|은|는|께서)(?=[\s,]|$)')

_DIALOGUE_RE = re.compile(r'"([^"]*)"')


# 이름으로 오인하기 쉬운 낱말
_NOT_A_NAME = {
    "하나", "둘", "셋", "넷", "여럿", "모두", "몇몇", "그것", "이것", "저것",
    "사람", "아이", "여인", "사내", "노인", "젊은", "어린", "늙은", "누구",
    "자기", "자신", "서로", "저마다", "하인", "여종", "머슴", "몸종",
}
_JOSA = r'(?:이|가|은|는|을|를|에게|한테|의|도|와|과|께|께서)'
_HAN = r'[가-힣]'


def infer_cast(text):
    """본문에서 '이름 → 역할군'을 자동 추출한다. cast 를 손으로 넘기지 않아도 검사가 돈다.

    "유모 삼월이가" / "삼월이라는 유모" / "삼월이는 이 집 유모였다" 세 꼴을 찾고,
    한 번 잡힌 이름은 대본 전체에 적용한다.
    """
    cast = {}
    seen = {}

    def put(name, role):
        name = name.strip()
        if len(name) < 2 or name in _NOT_A_NAME:
            return
        keys = [name]
        # "삼월이" → "삼월" 도 같이 등록한다 (붙는 조사에 따라 형태가 갈린다)
        if len(name) >= 3 and name.endswith("이"):
            keys.append(name[:-1])
        for k in keys:
            seen.setdefault(k, set()).add(role)

    for words, role in ((SERVANT_WORDS, "하인"), (MASTER_WORDS, "상전")):
        for w in words:
            if len(w) < 2:      # '종' 같은 한 글자는 오인이 많아 추론에 쓰지 않는다
                continue
            e = re.escape(w)
            # ① "유모 삼월이가"  — 역할 낱말 + 이름
            for m in re.finditer(e + r'\s+(' + _HAN + r'{2,6}?)' + _JOSA
                                 + r'(?=[\s,.…"\']|$)', text):
                put(m.group(1), role)
            # ② "삼월이라는 유모" — 이름 + 라는 + 역할 낱말
            for m in re.finditer(r'(' + _HAN + r'{2,6})(?:이)?라는\s+' + _HAN
                                 + r'{0,4}\s?' + e, text):
                put(m.group(1), role)
            # ③ "삼월이는 이 집 유모였습니다" — 이름 + … + 역할 낱말 + 서술어
            for m in re.finditer(r'(' + _HAN + r'{2,6}?)(?:이|가|은|는)\s[^"\n]{0,25}?'
                                 + e + r'(?:였|이었|입니|이옵)', text):
                put(m.group(1), role)

    # 신분이 바뀌는 인물(축C의 "종이 마님이 된다")은 두 역할이 다 잡힌다 → 검사에서 뺀다.
    for k, roles in seen.items():
        cast[k] = roles.pop() if len(roles) == 1 else "신분변동"
    return cast


def _role_of(word):
    """화자 낱말을 역할군으로 분류한다. 모르면 None."""
    if not word:
        return None
    if any(w in word for w in SERVANT_WORDS):
        return "하인"
    if any(w in word for w in MASTER_WORDS):
        return "상전"
    return None


# 이름 대신 관계어로만 불리는 경우의 별칭을 만든다 (v12.9 신설).
# "친정 오라비 오만석"처럼 관계어+이름이 붙어 나오면, 그 뒤로 "오라비가 말했다"처럼
# 이름 없이 관계어만 나와도 그 사람으로 인식한다. infer_cast()의 "역할+이름 인접" 패턴과
# 같은 원리를 관계어에도 적용한 것 — 관계어 자체는 여러 사람을 가리킬 수 있어 위험하므로
# **등록된 이름 바로 옆에 붙어 나온 경우만** 별칭으로 삼는다(문장 전체 동시출현은 보지 않는다 —
# 그러면 "동생을 자랑스러워했다"의 '동생'이 엉뚱한 사람에게 붙는 등 오배정이 난다).
_RELATION_WORDS = ("오라비", "오라버니", "언니", "누님", "형님", "형", "아우", "동생",
                   "아들", "딸", "아버지", "어머니", "아비", "어미", "남편", "지아비", "지어미",
                   "며느리", "사위", "시아버지", "시어머니", "장인", "장모", "삼촌", "숙부",
                   "고모", "이모", "조카", "손자", "손녀")


def _build_relation_aliases(text, cast):
    """관계어 → 역할 별칭. 안전장치: 같은 관계어가 **역할이 다른** 인물 여럿에
    붙으면(예: 적자·서자처럼 "아들"이 둘인데 한쪽만 상전) 어느 쪽인지 코드가 모르므로
    별칭을 아예 만들지 않는다 — 모호하면 포기, 틀리게 배정하지 않는다."""
    alias = {}
    for word in _RELATION_WORDS:
        e = re.escape(word)
        matched_roles = set()
        for name in cast:
            if not name or len(name) < 2:
                continue
            n = re.escape(name)
            # "관계어 이름" 또는 "이름 관계어" — 바로 붙어 나오는 경우만 별칭으로 인정
            if re.search(e + r'\s*' + n, text) or re.search(n + r'\s*' + e, text):
                matched_roles.add(cast[name])
        if len(matched_roles) == 1:
            alias[word] = matched_roles.pop()
    return alias


def attribute_speakers(text, cast=None):
    """대사마다 화자를 추정한다. cast 는 생략 가능(infer_cast 자동 추출 위에 덮어쓴다).

    반환: [(대사, 화자낱말 or None, 역할군 or None, 시작 위치), ...]
    """
    merged = infer_cast(text)      # 본문에서 자동 추출
    merged.update(cast or {})      # 사람이 넘긴 값이 우선
    cast = merged
    cast = {**_build_relation_aliases(text, cast), **cast}  # 관계어 별칭은 실제 이름에 밀린다

    def resolve(word):
        # v12.8 버그 수정 — "오순이"로 인물표에 등록했는데 본문에서는 성을 떼고
        # "순이가 말했습니다"로만 부르는 경우(매우 흔한 한국어 관습)를 놓치고 있었다.
        # 예전엔 "등록명이 word의 부분 문자열"인지만 봐서 "오순이" in "순이"가 False였다.
        # → 양방향 부분일치 + "성 뗀 이름"까지 본다.
        for name, r in cast.items():
            if not name:
                continue
            if name in word or (len(word) >= 2 and word in name):
                return r
            if len(name) >= 3 and word == name[1:]:   # "오순이" 등록 → "순이"만 나와도 인식
                return r
        return _role_of(word)

    def pick(window, nearest="last", verb_re=_SPEECH_VERB_RE):
        # nearest="first" — 대사 뒤 창은 대사에 가까운 쪽이 화자다("대사" 유모가 말했다).
        # nearest="last"  — 대사 앞 창은 대사에 가까운 쪽이 뒤에 있다(유모가 말했다. "대사").
        verb_m = verb_re.search(window)
        if not verb_m:
            return None, None
        # v12.9 버그 수정 — 한 문장에 절이 여럿이면("오라비가 그리 말할 때마다 순이는
        # 부끄러워했다") "말하다"의 진짜 주어(오라비)가 아니라 다른 절의 주어(순이)가
        # 뽑혀서 화자가 틀리게 배정됐다. 한국어는 주어-동사 순서(SOV)라 진짜 주어는
        # 거의 항상 동사 **앞**에 온다. 그래서 동사 앞 후보를 전부 우선(그중 동사에
        # 가장 가까운 것부터) 시도하고, 그래도 없을 때만 동사 뒤 후보를 본다 —
        # 단순 거리 정렬은 "말할 때마다 순이는"처럼 뒤 후보가 글자 수로 더 가까워서
        # 틀리게 이긴다.
        before_v = sorted((m for m in _SUBJECT_RE.finditer(window) if m.start() < verb_m.start()),
                           key=lambda m: -m.start())
        after_v = sorted((m for m in _SUBJECT_RE.finditer(window) if m.start() >= verb_m.end()),
                          key=lambda m: m.start())
        order = [m.group(1) for m in before_v] + [m.group(1) for m in after_v]
        for w in order:
            r = resolve(w)
            if r:
                return w, r
            # v12.9 버그 수정 — _SUBJECT_RE의 "역할+이름" 앞어절 옵션이 부사까지 잘못 삼킨다
            # ("매화가 나직이" → "매화가 나직"). 공백으로 갈라 앞·뒤 어절을 따로 재시도한다
            # ("유모 삼월이" 처럼 진짜 역할+이름이면 이미 위에서 잡히므로 여기까진 안 온다).
            if " " in w:
                for part in w.split(" "):
                    part_bare = re.sub(r'(이|가|은|는)$', '', part)  # 남은 조사 꼬리 제거
                    for cand in (part, part_bare):
                        r2 = resolve(cand)
                        if r2:
                            return cand, r2
        return (order[0], None) if order else (None, None)

    def one_sentence(window, side):
        """화자 탐색 범위 = 문단 경계를 넘지 않는, 대사에 붙어 있는 문장 하나."""
        para = re.split(r'\n[ \t]*\n', window)
        window = para[0] if side == "after" else para[-1]
        parts = [p for p in re.split(r'(?<=[.!?])(?=\s|$)', window) if p.strip()]
        if not parts:
            return window
        return parts[0] if side == "after" else parts[-1]

    out = []
    for m in _DIALOGUE_RE.finditer(text):
        after_raw = text[m.end():m.end() + 90]
        before = text[max(0, m.start() - 90):m.start()]
        if '"' in before:
            before = before[before.rindex('"') + 1:]
        before = one_sentence(before, "before")

        # 대사 뒤 나레이션 한 문장. 단 그 뒤에 또 대사가 오면 그 문장은 "뒤에 올 대사"의 화자다.
        after = one_sentence(after_raw, "after")
        rest = after_raw[len(after):] if after_raw.startswith(after) else ""
        if rest.lstrip().startswith('"'):
            after = ""
        elif '"' in after:
            after = after[:after.index('"')]

        spk, role = pick(after, "first")  # "대사" 하고 유모가 말했습니다
        if role is None:
            spk2, role2 = pick(before, "last")   # 유모가 말했습니다. "대사"
            if role2 or spk is None:
                spk, role = spk2, role2
        if role is None:
            # 발화 동사가 없을 때 — 대사 직전 나레이션의 동작 주어를 화자로 본다.
            spk3, role3 = pick(before, "last", _ACTION_VERB_RE)
            if role3:
                spk, role = spk3, role3
        out.append((m.group(1), spk, role, m.start()))
    return out


def _line_no(text, pos):
    return text.count("\n", 0, pos) + 1


def check_address(text, cast=None):
    """호칭 오류를 기계 검사한다. FAIL 1건이라도 있으면 그 대사를 고쳐 쓴다.

    FAIL: 하인이 주인집 가족 호칭 사용("유모→며느리").
    WARN: 하인의 관계호칭·하대호칭·자칭 '나', 상전의 존대호칭. 청자를 몰라 사람이 판정한다.
    """
    auto = infer_cast(text)
    lines = attribute_speakers(text, cast)
    fails, warns = [], []
    unknown = 0

    for utt, spk, role, pos in lines:
        if role is None:
            unknown += 1
        ln = _line_no(text, pos)
        snippet = utt[:34]

        if role == "하인":
            for t in KINSHIP_ONLY_TERMS:
                if t in utt:
                    fails.append({
                        "줄": ln, "화자": spk, "유형": "하인→혈연호칭",
                        "호칭": t, "대사": snippet,
                        "고칠_방향": f'"{t}"은 주인집 가족만 쓰는 말이다. '
                                     f'아씨 / 마님 / 작은마님 / 도련님 중 신분에 맞는 것으로 바꾼다',
                    })
            for t in KINSHIP_AMBIGUOUS_TERMS:
                if t in utt:
                    warns.append({
                        "줄": ln, "화자": spk, "유형": "하인→관계호칭(듣는사람 확인)",
                        "호칭": t, "대사": snippet,
                        "고칠_방향": f'상전에게 한 말이면 오류다("{t}" → 아씨/마님/도련님). '
                                     f'같은 하인이나 제 식구에게 한 말이면 그대로 둔다',
                    })
            taken = []
            for t in sorted(CONDESCENDING_TERMS, key=len, reverse=True):
                i = utt.find(t)
                if i >= 0 and not any(a <= i < b for a, b in taken):
                    taken.append((i, i + len(t)))
                    warns.append({
                        "줄": ln, "화자": spk, "유형": "하인→하대호칭(듣는사람 확인)",
                        "호칭": t, "대사": snippet,
                        "고칠_방향": f'상전에게 한 말이면 오류다("{t}" → 아씨/마님 + 존대 어미). '
                                     f'같은 하인끼리면 그대로 둔다',
                    })
            if re.search(r'(^|[\s"])(내가|나는|나도|나를)', utt):
                warns.append({
                    "줄": ln, "화자": spk, "유형": "하인_자칭",
                    "호칭": "나", "대사": snippet,
                    "고칠_방향": "상전 앞이면 자칭을 소인 / 쇤네 / 소녀 로 바꾼다",
                })

        elif role == "상전":
            for t in MASTER_FORBIDDEN_TERMS:
                if t in utt:
                    warns.append({
                        "줄": ln, "화자": spk, "유형": "상전→존대호칭",
                        "호칭": t, "대사": snippet,
                        "고칠_방향": f'상전이 아랫사람을 "{t}"라 부르지 않는다. 이름 또는 "너/네가"',
                    })

        # ── 연령 호칭 (신분과 무관하게 검사) ──
        # 한 대사 안에 노인 지칭어와 아이 호칭이 같이 나오면 대상이 어긋난 것이다.
        # "할멈, 얘야 이리 오너라" 처럼. 종이어도 예순이면 아이 부르듯 부르지 않는다.
        elder_hit = [w for w in ELDER_WORDS if w in utt]
        if elder_hit:
            for t in CHILD_ADDRESS_TERMS:
                if t in utt:
                    fails.append({
                        "줄": ln, "화자": spk, "유형": "노인→아이호칭",
                        "호칭": t, "대사": snippet,
                        "고칠_방향": f'같은 대사에 "{elder_hit[0]}"(노인)과 "{t}"(아이 호칭)가 같이 있다. '
                                     f'노인장 / 어르신 / 할멈 처럼 나이에 맞는 호칭으로 바꾼다',
                    })

    n = len(lines)
    return {
        "대사_수": n,
        "화자_확인_수": n - unknown,
        "화자_미상_비율": round(unknown / n, 3) if n else 0,
        "호칭_위반_수": len(fails),
        "호칭_위반": fails,
        "호칭_주의_수": len(warns),
        "호칭_주의": warns,
        "호칭_검사_통과": len(fails) == 0,
        "자동추출_인물": auto,          # 본문에서 스스로 잡아낸 이름 → 역할군
    }


def address_report(text, cast=None):
    """사람이 읽을 수 있게 한 덩어리로 출력한다."""
    r = check_address(text, cast)
    out = [f"[호칭 검사] 대사 {r['대사_수']}개 / 화자확인 {r['화자_확인_수']}개 "
           f"/ 위반 {r['호칭_위반_수']}건 / 주의 {r['호칭_주의_수']}건"]
    for f in r["호칭_위반"]:
        out.append(f"  ❌ {f['줄']}줄 [{f['화자']}] {f['유형']} \"{f['호칭']}\" "
                   f"— {f['대사']}\n     → {f['고칠_방향']}")
    for w in r["호칭_주의"]:
        out.append(f"  ⚠️ {w['줄']}줄 [{w['화자']}] {w['유형']} — {w['대사']}\n"
                   f"     → {w['고칠_방향']}")
    if not r["호칭_위반"] and not r["호칭_주의"]:
        out.append("  ✅ 위반 없음")

    # v12.7 — 성씨 정합성도 같이 보고한다(친남매인데 성씨 다름)
    sur = check_surnames(text, list(cast) if cast else None)
    if sur["성씨_위반_수"]:
        out.append(f"[성씨 검사] 위반 {sur['성씨_위반_수']}건")
        for f in sur["성씨_위반"]:
            out.append(f"  ❌ [{f['관계']}] {' / '.join(f['이름'])} — 성씨 {'/'.join(f['성씨'])}")
            out.append(f"     {f['문장']}")
            out.append(f"     → {f['고칠_방향']}")
    return "\n".join(out)


# v12.10 — 업로드.txt(채널 소개 멘트) 실명 유출 검사
# 실제로 학생 채널명 대신 벤치마킹 채널 실명이 그대로 나간 사례가 발견돼 추가.
# 정답(학생의 실제 채널명)은 알 수 없으니 "이 안에 실명이 없는가"만 기계로 확인한다.
BENCHMARK_CHANNEL_NAMES = ("월하야담26", "월하야담", "송림야담", "산골야담26", "청월야담26")


def check_upload_text(text):
    """업로드.txt 최종 산출물에 벤치마킹 채널 실명이나 미치환 플레이스홀더가 남았는지 검사한다.

    FAIL: 벤치마킹 채널 실명이 그대로 노출됨(치환 누락 또는 예시 베끼기).
    FAIL: `{채널명}` 등 중괄호 플레이스홀더가 치환되지 않고 그대로 남음.
    """
    leaked = [name for name in BENCHMARK_CHANNEL_NAMES if name in text]
    unresolved = re.findall(r"\{[^{}]{1,20}\}", text)
    통과 = not leaked and not unresolved
    return {
        "실명_유출": leaked,
        "미치환_플레이스홀더": unresolved,
        "통과": 통과,
    }


# v12.13 — scripts.txt 로그 한 줄 검사
# 사고: 첫 편에서 S후크 칸에 "신분 은닉·정변 생존자"(= A3 플롯 유형)가 적혔다.
# 그 편의 실제 장면은 "쫓기는 여인을 곳간에 숨겨 줌" = S1이었다.
# 후크는 제대로 골라 놓고 기록만 플롯 층위로 되돌린 것이라, 다음 화가
# "S1을 최근에 썼는지"를 판정할 수 없게 됐다. 그래서 기계로 막는다.
V축_허용값 = {
    "V1": ["아홉 살 소년", "열 살", "열두 살", "소녀", "열한 살", "누나",
           "스무 살", "처녀", "서른", "본처", "과부", "노인"],
    "V2": ["몸종", "머슴", "소금장수", "약초꾼", "장사치", "상민", "처녀",
           "몰락 양반", "반가", "아씨", "대갓댁", "안주인"],
    "V3": ["구하는 쪽", "구해지는 쪽", "제3자", "양쪽 다 모름"],
    "V4": ["약초", "의술", "완력", "씨름", "글씨", "장부", "반쪽", "신물",
           "말버릇", "습관", "밥 한 상", "밥한상", "관상"],
    "V5": ["그날 밤", "그날밤", "열흘 뒤", "열흘뒤", "49일", "삼 년", "삼년",
           "십 년", "십년"],
    "V6": ["본인", "자식", "은인의 가문", "은인가문", "마을 전체", "마을전체"],
}


def check_log_line(line):
    """scripts.txt에 넣을 로그 한 줄이 규격대로 적혔는지 검사한다.

    FAIL: S후크 칸이 S번호(S1~S16)로 시작하지 않음 — 플롯 유형을 적은 경우.
    FAIL: V축 6칸(V1~V6)이 다 없음.
    FAIL: V축 값이 모티프_뱅크 V축 표에 없는 자유 서술.
    """
    문제 = []

    # 두 가지 표기를 다 받는다.
    #   라벨형  : `S후크(S1)` / `S후크 S1`
    #   파이프형: `... | S1 | ...`  (scripts.txt 표의 실제 모양)
    S번호 = re.compile(r"^S(1[0-6]|[1-9])(\s|$)")
    m = re.search(r"S후크[^\w]{0,3}([^/|,)\n]+)", line)
    if m:
        값 = m.group(1).strip()
        if not S번호.match(값):
            문제.append(f"S후크가 S번호로 시작하지 않는다: {값!r} "
                       f"(A3·E5 같은 플롯 유형을 여기 적으면 안 된다 — 반전재료 칸이다)")
    else:
        칸 = [c.strip() for c in line.split("|")]
        if not any(S번호.match(c) for c in 칸):
            문제.append("S후크 칸이 없다 — S1~S16 중 하나를 한 칸에 적는다 "
                       "(A3·E5 같은 플롯 유형은 반전재료 칸이다)")

    빠진축 = [축 for 축 in ("V1", "V2", "V3", "V4", "V5", "V6")
             if not re.search(축 + r"\s", line)]
    if 빠진축:
        문제.append("V축 누락: " + ", ".join(빠진축))

    미정의 = []
    for 축, 허용 in V축_허용값.items():
        mm = re.search(축 + r"\s+([^/|)\n]+)", line)
        if not mm:
            continue
        값 = mm.group(1).strip()
        if not any(a.replace(" ", "") in 값.replace(" ", "") for a in 허용):
            미정의.append(f"{축}={값!r}")
    if 미정의:
        문제.append("뱅크 V축 표에 없는 값: " + " / ".join(미정의))

    return {"문제": 문제, "통과": not 문제}

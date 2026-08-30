"""name_picker.py — 야담 캐릭터 이름 코드 기반 추출기

scripts.txt에 누적된 기존 등장인물 이름(name_bank)과 충돌하지 않는 새 이름을 무작위로 뽑는다.
학습_누적.md 카테고리 A 규칙(성씨 첫 글자 + 이름 첫 글자 충돌 회피)을 코드로 강제한다.
AI가 매번 수동으로 충돌 검사를 하는 대신, 이 스크립트를 실행해 이름을 확정한다.

사용법:
    python name_picker.py --count 4 --existing "덕구,월매,최치원,박아전"
    python name_picker.py --count 2 --existing "" --gender female

★ v2 (2026-08-25) — 가족(혈연) 성씨 공유 기능 추가.
  예전에는 인물마다 성씨를 독립 무작위로 뽑아서, 주인공이 임씨인데 친오라비가 서씨로
  나오는 사고가 있었다. 혈연은 성씨를 공유해야 한다.

    # 주인공 + 친오라비 + 친여동생을 한 집안(같은 성씨)으로
    python name_picker.py --family 3 --count 2 --existing "..."
      → --family 로 지정한 인원은 같은 성씨를 받는다(첫 N명).
      → 나머지 --count 인원은 각자 다른 성씨(혼인·타인)로 뽑는다.
"""
import argparse
import random
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

SURNAMES = ["김", "이", "박", "최", "정", "강", "조", "윤", "장", "임", "한", "오", "서", "신", "권", "황", "안", "송"]

GIVEN_MALE = ["구", "돌", "석", "복", "만", "환", "수", "철", "용", "식", "규", "웅", "찬", "혁", "훈", "길", "봉"]
GIVEN_FEMALE = ["순", "이", "옥", "매", "년", "화", "선", "월", "희", "숙", "분", "례", "정", "은", "덕", "심", "단"]
GIVEN_NEUTRAL = ["동", "청", "산", "연", "미", "우", "경", "빈", "율", "다", "온", "겸"]


def build_existing_keys(existing_names):
    """기존 이름들의 '성씨 첫 글자 + 이름 첫 글자' 키 집합을 만든다."""
    keys = set()
    for n in existing_names:
        n = n.strip()
        if len(n) >= 2:
            keys.add(n[0] + n[1])
    return keys


def pick_family(size, existing_names, gender_mix="mixed"):
    """혈연 가족 N명을 **같은 성씨**로 뽑는다 (2026-08-25 신설).

    친남매·부모자식처럼 피가 섞인 인물은 성씨가 같아야 한다.
    혼인으로 들어온 인물(며느리·사위·처가)은 친정 성씨를 그대로 쓰므로 여기 넣지 않는다.
    """
    existing_keys = build_existing_keys(existing_names)
    for _ in range(3000):
        surname = random.choice(SURNAMES)
        members, used = [], set(existing_keys)
        for _ in range(size):
            for _ in range(200):
                if gender_mix == "male":
                    pool = GIVEN_MALE
                elif gender_mix == "female":
                    pool = GIVEN_FEMALE
                elif gender_mix == "neutral":
                    pool = GIVEN_NEUTRAL
                else:
                    pool = random.choice([GIVEN_MALE, GIVEN_FEMALE, GIVEN_NEUTRAL])
                given = random.choice(pool) + random.choice(pool)
                full = surname + given
                key = surname + given[0]
                if key in used or full in members:
                    continue
                used.add(key)
                members.append(full)
                break
        if len(members) == size:
            return members
    return []


def pick_names(count, existing_names, gender_mix="mixed"):
    existing_keys = build_existing_keys(existing_names)
    picked = []
    used_keys = set(existing_keys)
    attempts = 0

    while len(picked) < count and attempts < 3000:
        attempts += 1
        surname = random.choice(SURNAMES)

        if gender_mix == "male":
            pool = GIVEN_MALE
        elif gender_mix == "female":
            pool = GIVEN_FEMALE
        elif gender_mix == "neutral":
            pool = GIVEN_NEUTRAL
        else:
            pool = random.choice([GIVEN_MALE, GIVEN_FEMALE, GIVEN_NEUTRAL])

        given = random.choice(pool) + random.choice(pool)
        full = surname + given
        key = surname + given[0]

        if key in used_keys or full in picked:
            continue

        used_keys.add(key)
        picked.append(full)

    if len(picked) < count:
        print(f"[name_picker] 경고: {attempts}회 시도 후 {len(picked)}/{count}명만 확보 — 기존 이름 목록이 너무 많으면 성씨/음절 풀을 늘려야 함")

    return picked


def main():
    parser = argparse.ArgumentParser(description="야담 캐릭터 이름 코드 기반 추출기")
    parser.add_argument("--count", type=int, default=4, help="뽑을 인물 수 (기본 4)")
    parser.add_argument("--family", type=int, default=0,
                        help="혈연 가족 인원 수 — 이 인원은 같은 성씨를 받는다 (친남매·부모자식)")
    parser.add_argument("--existing", type=str, default="", help="scripts.txt 등장인물 열에서 가져온 기존 이름, 콤마 구분")
    parser.add_argument("--gender", type=str, default="mixed", choices=["male", "female", "neutral", "mixed"])
    args = parser.parse_args()

    existing_names = [n for n in args.existing.split(",") if n.strip()]

    family = []
    if args.family > 0:
        family = pick_family(args.family, existing_names, args.gender)
        if not family:
            print(f"[name_picker] 경고: 가족 {args.family}명을 같은 성씨로 못 뽑았다 — 기존 이름이 너무 많다")
        existing_names = existing_names + family

    names = pick_names(args.count, existing_names, args.gender)

    if family:
        print(f"[name_picker] 혈연 가족 {len(family)}명 (같은 성씨 '{family[0][0]}')")
        for n in family:
            print(f"  - {n}   ← 성씨 공유")
    print(f"[name_picker] 기존 {len(existing_names)}명과 충돌 없는 신규 인물 {len(names)}명 추출")
    for n in names:
        print(f"  - {n}")
    if family:
        print("\n  ※ 혼인으로 들어온 인물(며느리·사위·처가)은 친정 성씨를 그대로 씁니다 —")
        print("    위 '신규 인물' 쪽에서 골라 쓰세요. 가족 성씨를 붙이면 안 됩니다.")


if __name__ == "__main__":
    main()

import sys

# --- 기본 가정 설정 (상수로 분리) ---
ANNUAL_RETURN = 0.10  # 납입 기간 연평균 수익률 (10%)
POST_55_ANNUAL_RETURN = 0.05  # 55세 이후(안전자산) 연평균 수익률 (5%)
INFLATION_RATE = 0.03  # 연평균 물가상승률 (3%)

# 연금 수령 및 과세 관련 상수
PENSION_START_AGE = 55  # 연금 수령 시작 시기 (55세)
LIFE_EXPECTANCY = 90 # 기대 수명 (90세)
PENSION_TAX_THRESHOLD = 15_000_000  # 2025년 기준 1500만원 초과시 종합과세

# 연령별 연금소득세율 (지방소득세 포함)
PENSION_TAX_RATES = {
    "age_55_69": 0.055,  # 55-69세: 5.5%
    "age_70_79": 0.044,  # 70-79세: 4.4%
    "age_80_plus": 0.033, # 80세 이상: 3.3%
}
SEPARATE_TAX_RATE = 0.165  # 분리과세율 16.5%


def get_user_input():
    """사용자로부터 필요한 정보를 입력받고 유효성을 검사합니다."""
    try:
        start_age = int(input("▶ 연금 납입을 시작할 나이를 입력하세요: "))
        monthly_contribution = int(input("▶ 매달 납입할 금액(원)을 입력하세요: "))
    except ValueError:
        print("오류: 나이와 금액은 숫자로만 입력해주세요.")
        return None, None

    if not (20 <= start_age < PENSION_START_AGE):
        print(f"오류: 납입 시작 나이는 20세 이상 {PENSION_START_AGE}세 미만이어야 합니다.")
        return None, None
    
    if monthly_contribution <= 0:
        print("오류: 월 납입액은 0보다 커야 합니다.")
        return None, None

    return start_age, monthly_contribution


def calculate_total_at_55(start_age, monthly_contribution):
    """
    55세 시점의 총 적립금(미래가치)을 계산합니다.
    - 개선점: 비효율적인 for 반복문 대신 '연금 미래가치(FVA)' 공식을 사용합니다.
    - 공식: FV = PMT * [((1 + r)^n - 1) / r]
      (PMT: 매월 납입액, r: 월 이율, n: 총 납입 횟수)
    """
    contribution_years = PENSION_START_AGE - start_age
    total_months_contribution = contribution_years * 12
    monthly_return = (1 + ANNUAL_RETURN)**(1/12) - 1

    if monthly_return == 0: # 이자율이 0인 극단적인 경우
        return monthly_contribution * total_months_contribution

    # 연금 미래가치 공식 적용
    future_value = monthly_contribution * (
        ((1 + monthly_return)**total_months_contribution - 1) / monthly_return
    )
    return future_value


def calculate_pension_payouts(total_at_55):
    """
    55세 적립금을 기준으로 월 수령액(세전)을 계산합니다.
    - '연금 현재가치(PVA)' 공식을 역으로 이용하여 월 수령액(PMT)을 계산합니다.
    - 공식: PMT = PV * [r / (1 - (1 + r)^-n)]
      (PV: 55세 시점 적립금, r: 월 이율, n: 총 수령 개월 수)
    """
    withdrawal_years = LIFE_EXPECTANCY - PENSION_START_AGE
    total_months_withdrawal = withdrawal_years * 12
    monthly_return = (1 + POST_55_ANNUAL_RETURN)**(1/12) - 1

    if monthly_return == 0: # 이자율이 0인 극단적인 경우
        return total_at_55 / total_months_withdrawal
    
    # 월 수령액(PMT) 계산 공식 적용
    annuity_factor = monthly_return / (1 - (1 + monthly_return)**-total_months_withdrawal)
    monthly_withdrawal_pre_tax = total_at_55 * annuity_factor
    
    return monthly_withdrawal_pre_tax


def display_results(start_age, monthly_contribution, total_at_55, monthly_withdrawal_pre_tax):
    """계산된 결과를 형식에 맞게 출력합니다."""
    
    annual_withdrawal_pre_tax = monthly_withdrawal_pre_tax * 12

    # --- 기본 결과 출력 ---
    print("\n" + "="*50)
    print(" " * 18 + "< 연금 수령액 예상 결과 >")
    print("="*50)
    print(f"입력 정보:")
    print(f"  - 시작 나이: {start_age}세")
    print(f"  - 월 납입액: {monthly_contribution:,.0f}원")
    print("-" * 50)
    print(f"예상 결과:")
    print(f"  - {PENSION_START_AGE}세 시점의 총 적립금(세전): 약 {total_at_55:,.0f} 원")
    print(f"  - {PENSION_START_AGE}세부터의 월 수령액(세전): 약 {monthly_withdrawal_pre_tax:,.0f} 원")
    print(f"  - {PENSION_START_AGE}세부터의 연 수령액(세전): 약 {annual_withdrawal_pre_tax:,.0f} 원")
    print("="*50 + "\n")

    # --- 1) 나이별 월 실수령액(세후) 계산 및 출력 ---
    print(f"1) {PENSION_START_AGE}세부터 {LIFE_EXPECTANCY}세까지의 나이별 월 실수령액(세후)은?")
    print("-" * 50)
    if annual_withdrawal_pre_tax > PENSION_TAX_THRESHOLD:
        print(f"연간 수령액이 {PENSION_TAX_THRESHOLD/10000:,.0f}만원을 초과하여 분리과세(16.5%)가 유리할 수 있습니다.")
        monthly_take_home = monthly_withdrawal_pre_tax * (1 - SEPARATE_TAX_RATE)
        print(f"▶ 전 연령대 월 실수령액: 약 {monthly_take_home:,.0f} 원 (분리과세 선택 시)")
    else:
        print(f"연간 수령액이 {PENSION_TAX_THRESHOLD/10000:,.0f}만원 이하이므로 연령별 연금소득세가 적용됩니다.")
        take_home_1 = monthly_withdrawal_pre_tax * (1 - PENSION_TAX_RATES["age_55_69"])
        take_home_2 = monthly_withdrawal_pre_tax * (1 - PENSION_TAX_RATES["age_70_79"])
        take_home_3 = monthly_withdrawal_pre_tax * (1 - PENSION_TAX_RATES["age_80_plus"])
        print(f"  - 55세 ~ 69세: 약 {take_home_1:,.0f} 원 (세율 {PENSION_TAX_RATES['age_55_69']*100}%)")
        print(f"  - 70세 ~ 79세: 약 {take_home_2:,.0f} 원 (세율 {PENSION_TAX_RATES['age_70_79']*100}%)")
        print(f"  - 80세 ~ {LIFE_EXPECTANCY}세: 약 {take_home_3:,.0f} 원 (세율 {PENSION_TAX_RATES['age_80_plus']*100}%)")
    print("-" * 50 + "\n")

    # --- 2) 인플레이션을 고려한 연금의 현재 가치 계산 및 출력 ---
    print(f"2) {PENSION_START_AGE}세에 받을 월 연금액은 현재 가치로 얼마일까요?")
    print("-" * 50)
    
    # 55세 기준 세후 수령액 계산
    if annual_withdrawal_pre_tax > PENSION_TAX_THRESHOLD:
        base_monthly_take_home_at_55 = monthly_withdrawal_pre_tax * (1 - SEPARATE_TAX_RATE)
    else:
        base_monthly_take_home_at_55 = monthly_withdrawal_pre_tax * (1 - PENSION_TAX_RATES["age_55_69"])

    years_to_discount = PENSION_START_AGE - start_age
    present_value_of_pension = base_monthly_take_home_at_55 / ((1 + INFLATION_RATE) ** years_to_discount)
    
    print(f"{years_to_discount}년 후({start_age}세→{PENSION_START_AGE}세)에 받을 월 실수령액 약 {base_monthly_take_home_at_55:,.0f} 원은...")
    print(f"연평균 물가상승률 {INFLATION_RATE * 100}%를 적용하면,")
    print(f"▶ 현재 가치로 약 {present_value_of_pension:,.0f} 원의 구매력을 가집니다.")
    print("-" * 50 + "\n")

    print("*중요: 위 결과는 설정된 가정에 기반한 추정치이며, 실제 수익률, 세법 개정, 물가상승률에 따라 달라질 수 있습니다.")


def main():
    """메인 실행 함수"""
    start_age, monthly_contribution = get_user_input()
    
    # 사용자 입력이 유효할 경우에만 계산 및 출력 실행
    if start_age is not None and monthly_contribution is not None:
        total_at_55 = calculate_total_at_55(start_age, monthly_contribution)
        monthly_withdrawal_pre_tax = calculate_pension_payouts(total_at_55)
        display_results(start_age, monthly_contribution, total_at_55, monthly_withdrawal_pre_tax)


# 스크립트 실행
if __name__ == "__main__":
    main()

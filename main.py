import sys

# --- 기본 가정 및 상수 설정 ---
INFLATION_RATE = 0.03  # 연평균 물가상승률 (3%)
PENSION_TAX_THRESHOLD = 15_000_000  # 연금소득 종합과세 기준 금액 (2025년)

# 연령별 연금소득세율 (지방소득세 포함)
PENSION_TAX_RATES = {
    "under_70": 0.055,  # 70세 미만: 5.5%
    "under_80": 0.044,  # 70세 이상 80세 미만: 4.4%
    "over_80": 0.033,   # 80세 이상: 3.3%
}
SEPARATE_TAX_RATE = 0.165  # 분리과세 선택 시 세율 (16.5%)

# 2025년 기준 종합소득세 과세표준 구간 및 세율 (누진공제액 최종 수정 완료)
COMPREHENSIVE_TAX_BRACKETS = [
    (14_000_000, 0.066, 0),
    (50_000_000, 0.165, 1_260_000 * 1.1),
    (88_000_000, 0.264, 5_760_000 * 1.1),
    (150_000_000, 0.385, 15_440_000 * 1.1),
    (300_000_000, 0.418, 19_940_000 * 1.1),
    (500_000_000, 0.440, 25_940_000 * 1.1),
    (1_000_000_000, 0.462, 35_940_000 * 1.1),
    (float('inf'), 0.495, 65_940_000 * 1.1),
]


def get_user_input():
    """계산에 필요한 사용자 정보를 그룹으로 묶어 입력받고 유효성을 검사합니다."""
    while True:
        try:
            age_input_str = input("▶ 납입 시작, 은퇴, 수령 종료 나이를 띄어쓰기로 구분하여 입력하세요 (예: 30 60 90): ")
            start_age, retirement_age, end_age = map(int, age_input_str.split())

            print("\n# 단계별 예상 수익률 및 물가상승률 입력 (연평균, %)")
            pre_retirement_return_input = float(input(f"▶ 은퇴 전({retirement_age}세 이전) 예상 수익률 (예: 7.5): "))
            pre_retirement_return = pre_retirement_return_input / 100.0

            post_retirement_return_input = float(input(f"▶ 은퇴 후({retirement_age}세 이후) 예상 수익률 (예: 4.0): "))
            post_retirement_return = post_retirement_return_input / 100.0
            
            inflation_rate_input = float(input("▶ 예상 연평균 물가상승률 (예: 3.0): "))
            inflation_rate = inflation_rate_input / 100.0

            print("\n[참고] 연금저축 납입 한도 (2025년 기준)")
            print("  - 세액공제 한도: 연 600만원")
            print("  - 계좌 총 납입 한도: 연 1,800만원")
            annual_contribution = int(input("▶ 위 내용을 참고하여, 매년 납입할 금액(원)을 입력하세요: "))

            if 6_000_000 < annual_contribution:
                print("[안내] 입력하신 납입액 중 600만원을 초과하는 금액은 세액공제 대상이 아닙니다.")
            if annual_contribution > 18_000_000:
                print("[주의] 연간 납입액이 연금저축 총 납입 한도(1,800만원)를 초과했습니다.")
            
            if not (start_age < retirement_age):
                print("\n오류: 은퇴 나이는 납입 시작 나이보다 커야 합니다.\n")
                continue
            if end_age <= retirement_age:
                print(f"\n오류: 수령 종료 나이는 은퇴 나이({retirement_age}세)보다 커야 합니다.\n")
                continue
            if annual_contribution <= 0:
                print("\n오류: 연 납입액은 0보다 커야 합니다.\n")
                continue
            
            payout_years = end_age - retirement_age
            return start_age, retirement_age, annual_contribution, payout_years, pre_retirement_return, post_retirement_return, inflation_rate

        except ValueError:
            print("\n오류: 입력 형식이 올바르지 않습니다. 각 항목의 개수와 숫자 여부를 확인 후 다시 입력해주세요.\n")


def calculate_total_at_retirement(start_age, retirement_age, annual_contribution, pre_retirement_return):
    """납입 정보와 수익률을 바탕으로 은퇴 시점의 총 적립금을 계산합니다."""
    monthly_contribution = annual_contribution / 12
    
    contribution_years = retirement_age - start_age
    total_months_contribution = contribution_years * 12
    monthly_return = (1 + pre_retirement_return)**(1/12) - 1

    if monthly_return == 0:
        return monthly_contribution * total_months_contribution
    future_value = monthly_contribution * (((1 + monthly_return)**total_months_contribution - 1) / monthly_return)
    return future_value


def calculate_pension_payouts(total_at_retirement, payout_years, post_retirement_return):
    """은퇴 시점 총 적립금을 수령 기간과 은퇴 후 수익률에 맞춰 월 수령액으로 변환합니다."""
    total_months_withdrawal = payout_years * 12
    monthly_return = (1 + post_retirement_return)**(1/12) - 1

    if monthly_return == 0:
        return total_at_retirement / total_months_withdrawal
    annuity_factor = monthly_return / (1 - (1 + monthly_return)**-total_months_withdrawal)
    monthly_withdrawal_pre_tax = total_at_retirement * annuity_factor
    return monthly_withdrawal_pre_tax


def calculate_pension_income_deduction(pension_income):
    """연간 연금소득액에 대한 연금소득공제 금액을 계산합니다. (2025년 기준)"""
    if pension_income <= 350_0000:
        return pension_income
    elif pension_income <= 700_0000:
        return 350_0000 + (pension_income - 350_0000) * 0.4
    elif pension_income <= 1400_0000:
        return 490_0000 + (pension_income - 700_0000) * 0.2
    else:
        return min(630_0000 + (pension_income - 1400_0000) * 0.1, 900_0000)


def calculate_comprehensive_tax(taxable_income):
    """주어진 소득 과세표준에 대한 종합소득세 산출세액을 계산합니다."""
    if taxable_income <= 0: return 0
    for threshold, rate, deduction in COMPREHENSIVE_TAX_BRACKETS:
        if taxable_income <= threshold:
            return taxable_income * rate - deduction
    return 0


def display_results(start_age, retirement_age, annual_contribution, payout_years, pre_retirement_return, post_retirement_return, inflation_rate, total_at_retirement, monthly_withdrawal_pre_tax):
    """모든 계산 결과를 종합하여 사용자에게 형식에 맞춰 보여주고, 계산의 한계점을 안내합니다."""
    width = 70
    title = "< 연금저축 예상 수령액 >"
    annual_withdrawal_pre_tax = monthly_withdrawal_pre_tax * 12

    print("\n" + "=" * width)
    print(title.center(width))
    print("=" * width)
    print(f"입력 정보:\n  - 시작 나이: {start_age}세\n  - 은퇴 나이: {retirement_age}세")
    print(f"  - 은퇴 전 예상 연평균 수익률: {pre_retirement_return*100:.1f}%")
    print(f"  - 은퇴 후 예상 연평균 수익률: {post_retirement_return*100:.1f}%")
    print(f"  - 예상 연평균 물가상승률: {inflation_rate*100:.1f}%")
    print(f"  - 연 납입액: {annual_contribution:,.0f}원")
    print(f"  - 수령 기간: {payout_years}년 ({retirement_age}세~{retirement_age + payout_years}세)")
    print("-" * width)
    print(f"예상 결과:\n  - {retirement_age}세 시점 총 적립금(세전): 약 {total_at_retirement:,.0f}원")
    print(f"  - 월 수령액(세전): 약 {monthly_withdrawal_pre_tax:,.0f}원")
    print("=" * width + "\n")

    print(f"1) 나이별 월 실수령액(세후) 예상".center(width))
    print("-" * width)

    base_monthly_take_home_at_retirement = 0

    if annual_withdrawal_pre_tax > PENSION_TAX_THRESHOLD:
        print(f"연간 연금저축 수령액이 {PENSION_TAX_THRESHOLD/10000:,.0f}만원을 초과하여 종합과세 대상입니다.")
        print("\n[안내] 정확한 계산을 위해, 본 연금저축 외 다른 소득(근로, 사업, 국민연금 등)에 대한")
        print("각종 공제(인적, 보험료 등)를 모두 마친 후의 '연간 과세표준' 금액을 입력해주세요.")
        
        other_income_base = -1
        while other_income_base < 0:
            try:
                other_income_str = input("▶ 연금저축 외 다른 소득의 연간 과세표준을 입력하세요 (없으면 0): ")
                other_income_base = int(other_income_str)
                if other_income_base < 0: print("오류: 0 이상의 숫자로 입력해주세요.")
            except ValueError: print("오류: 숫자로만 입력해주세요.")

        pension_deduction = calculate_pension_income_deduction(annual_withdrawal_pre_tax)
        taxable_pension_income = annual_withdrawal_pre_tax - pension_deduction
        
        total_taxable_income = taxable_pension_income + other_income_base
        tax_on_other_income = calculate_comprehensive_tax(other_income_base)
        tax_on_total_income = calculate_comprehensive_tax(total_taxable_income)
        comprehensive_pension_tax = tax_on_total_income - tax_on_other_income
        separate_pension_tax = annual_withdrawal_pre_tax * SEPARATE_TAX_RATE

        print("-" * width)
        print(" [예상 세금 비교]".center(width))
        print(f" 1. 종합과세 선택 시: 약 {comprehensive_pension_tax:,.0f} 원")
        print(f" 2. 분리과세 선택 시 (16.5%): 약 {separate_pension_tax:,.0f} 원")

        if comprehensive_pension_tax < separate_pension_tax:
            final_tax = comprehensive_pension_tax
            print("\n▶ 종합과세가 더 유리합니다.")
        elif separate_pension_tax < comprehensive_pension_tax:
            final_tax = separate_pension_tax
            print("\n▶ 분리과세가 더 유리합니다.")
        else:
            final_tax = separate_pension_tax
            print("\n▶ 두 방식의 예상 세액이 동일합니다.")
        
        monthly_take_home = (annual_withdrawal_pre_tax - final_tax) / 12
        base_monthly_take_home_at_retirement = monthly_take_home
        print(f"▶ 전 연령대 월 실수령액: 약 {monthly_take_home:,.0f} 원")

    else:
        print(f"연간 연금저축 수령액이 {PENSION_TAX_THRESHOLD/10000:,.0f}만원 이하이므로 연령별 연금소득세가 적용됩니다.")
        end_payout_age = retirement_age + payout_years
        
        if retirement_age < 70: initial_rate = PENSION_TAX_RATES["under_70"]
        elif retirement_age < 80: initial_rate = PENSION_TAX_RATES["under_80"]
        else: initial_rate = PENSION_TAX_RATES["over_80"]
        base_monthly_take_home_at_retirement = monthly_withdrawal_pre_tax * (1 - initial_rate)
        
        age_ranges = [(retirement_age, 69), (70, 79), (80, end_payout_age)]
        for i, (start, end) in enumerate(age_ranges):
            if retirement_age > end or end_payout_age <= start: continue
            start_display = max(retirement_age, start)
            end_display = min(end_payout_age - 1, end)
            if start_display > end_display: continue

            if start < 70: rate = PENSION_TAX_RATES["under_70"]
            elif start < 80: rate = PENSION_TAX_RATES["under_80"]
            else: rate = PENSION_TAX_RATES["over_80"]
            
            take_home = monthly_withdrawal_pre_tax * (1 - rate)
            print(f"  - {start_display}세 ~ {end_display}세: 약 {take_home:,.0f} 원 (세율 {rate*100:.1f}%)")

    print("-" * width + "\n")
    
    print(f"2) 은퇴 후 첫 월 실수령액의 현재가치".center(width))
    print("-" * width)
    years_to_discount = retirement_age - start_age
    present_value_of_pension = base_monthly_take_home_at_retirement / ((1 + inflation_rate) ** years_to_discount)
    
    print(f"미래({retirement_age}세)에 받을 첫 월 실수령액 약 {base_monthly_take_home_at_retirement:,.0f}원은")
    print(f"입력하신 연평균 물가상승률(연 {inflation_rate * 100:.1f}%)을 감안하면,")
    print(f"▶ 현재 시점의 약 {present_value_of_pension:,.0f}원과 같은 가치입니다.")
    print("-" * width + "\n")
    
    print("*"*width)
    print("<< '연금저축 실수령액 계산기' 안내 및 주의사항 >>".center(width))
    print("\n이 계산은 아래와 같은 한계를 가진 '개략적인 추정치'이므로 참고용으로만 활용해주십시오.")
    print("1. 계산 대상: 본 계산기는 '연금저축'을 가정합니다. IRP(특히 퇴직금 재원)는 세금 계산 방식이 다를 수 있습니다.")
    print("2. 세금: 실제 세금은 개인별 소득/세액공제(부양가족, 의료비 등)에 따라 달라집니다.")
    print("3. 수익률: 투자는 원금 손실이 가능하며, 수익률과 물가상승률은 예측과 다를 수 있습니다.")
    print("4. 연금재원: 세액공제 받지 않은 납입금(비과세 재원)은 계산에 미반영되었습니다.")
    print("5. 세법 개정: 본 계산은 2025년 기준 세법을 따르며, 향후 세법 개정에 따라 결과가 달라질 수 있습니다.") # 수정된 문구 추가
    print("*"*width)


def main():
    """메인 실행 함수"""
    user_inputs = get_user_input()
    if user_inputs and user_inputs[0] is not None:
        (start_age, retirement_age, annual_contribution, payout_years, 
         pre_retirement_return, post_retirement_return, inflation_rate) = user_inputs
        
        total_at_retirement = calculate_total_at_retirement(start_age, retirement_age, annual_contribution, pre_retirement_return)
        monthly_withdrawal_pre_tax = calculate_pension_payouts(total_at_retirement, payout_years, post_retirement_return)
        display_results(start_age, retirement_age, annual_contribution, payout_years, 
                        pre_retirement_return, post_retirement_return, inflation_rate, 
                        total_at_retirement, monthly_withdrawal_pre_tax)


if __name__ == "__main__":
    main()

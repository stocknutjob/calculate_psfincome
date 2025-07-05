import streamlit as st

# --------------------------------------------------------------------------
# --- 계산 함수들 (Functions for Calculation) ---
# --------------------------------------------------------------------------

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
    if pension_income <= 3_500_000:
        return pension_income
    elif pension_income <= 7_000_000:
        return 3_500_000 + (pension_income - 3_500_000) * 0.4
    elif pension_income <= 14_000_000:
        return 4_900_000 + (pension_income - 7_000_000) * 0.2
    else:
        return min(6_300_000 + (pension_income - 14_000_000) * 0.1, 9_000_000)

def calculate_comprehensive_tax(taxable_income):
    """주어진 소득 과세표준에 대한 종합소득세 산출세액을 계산합니다."""
    if taxable_income <= 0: return 0
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
    for threshold, rate, deduction in COMPREHENSIVE_TAX_BRACKETS:
        if taxable_income <= threshold:
            return taxable_income * rate - deduction
    return 0

# --------------------------------------------------------------------------
# --- 웹사이트 UI 구성 (Streamlit UI Configuration) ---
# --------------------------------------------------------------------------

st.set_page_config(layout="wide", page_title="연금저축 계산기")
st.title("연금저축 예상 수령액 계산기")

# --- 상수 설정 ---
PENSION_TAX_THRESHOLD = 15_000_000
PENSION_TAX_RATES = {"under_70": 0.055, "under_80": 0.044, "over_80": 0.033}
SEPARATE_TAX_RATE = 0.165

# --- 세션 상태 초기화 ---
# 앱이 처음 실행되거나 새로고침될 때 기본값을 설정합니다.
if 'start_age' not in st.session_state:
    st.session_state.start_age = 30
    st.session_state.retirement_age = 60
    st.session_state.end_age = 90
    st.session_state.pre_retirement_return_input = 7.5
    st.session_state.post_retirement_return_input = 4.0
    st.session_state.inflation_rate_input = 3.0
    st.session_state.annual_contribution = 6000000
    st.session_state.other_income_base = 0
    st.session_state.calculated = False

# 1. 사용자 입력 부분 (사이드바에 배치)
with st.sidebar:
    st.header("정보 입력")
    
    # 각 입력 위젯을 st.session_state의 'key'와 연결하여 상태를 유지합니다.
    st.number_input("납입 시작 나이", min_value=1, max_value=100, key="start_age")
    st.number_input("은퇴 나이 (연금 수령 시작)", min_value=st.session_state.start_age + 1, max_value=100, key="retirement_age")
    st.number_age = st.number_input("수령 종료 나이", min_value=st.session_state.retirement_age + 1, max_value=120, key="end_age")
    
    st.subheader("예상 연평균 수익률 및 물가상승률 (%)")
    st.number_input(f"은퇴 전 ({st.session_state.retirement_age}세 이전) 수익률", format="%.1f", step=0.1, key="pre_retirement_return_input")
    st.number_input(f"은퇴 후 ({st.session_state.retirement_age}세 이후) 수익률", format="%.1f", step=0.1, key="post_retirement_return_input")
    st.number_input("물가상승률", format="%.1f", step=0.1, key="inflation_rate_input")

    st.subheader("연간 납입액 (원)")
    st.info("세액공제 한도: 연 600만원\n\n계좌 총 납입 한도: 연 1,800만원")
    st.number_input("매년 납입할 금액", step=100000, label_visibility="collapsed", key="annual_contribution")
    
    if st.button("결과 확인하기"):
        # 버튼을 누르면 계산 상태 플래그만 True로 변경
        if not (st.session_state.start_age < st.session_state.retirement_age < st.session_state.end_age):
            st.error("나이 순서(시작 < 은퇴 < 종료)가 올바르지 않습니다.")
            st.session_state.calculated = False
        else:
            st.session_state.calculated = True

# 2. 계산 결과 출력 (세션 상태가 '계산 완료'일 때만)
if st.session_state.calculated:
    # 세션 상태에서 최신 입력값을 불러와 계산
    payout_years = st.session_state.end_age - st.session_state.retirement_age
    pre_retirement_return = st.session_state.pre_retirement_return_input / 100.0
    post_retirement_return = st.session_state.post_retirement_return_input / 100.0
    inflation_rate = st.session_state.inflation_rate_input / 100.0

    total_at_retirement = calculate_total_at_retirement(st.session_state.start_age, st.session_state.retirement_age, st.session_state.annual_contribution, pre_retirement_return)
    monthly_withdrawal_pre_tax = calculate_pension_payouts(total_at_retirement, payout_years, post_retirement_return)
    annual_withdrawal_pre_tax = monthly_withdrawal_pre_tax * 12

    # 결과 디스플레이
    st.header("📈 예상 결과")
    col1, col2 = st.columns(2)
    col1.metric(f"{st.session_state.retirement_age}세 시점 총 적립금", f"{total_at_retirement:,.0f} 원")
    col2.metric("월 수령액 (세전)", f"{monthly_withdrawal_pre_tax:,.0f} 원")

    st.header("💰 나이별 월 실수령액 (세후)")
    base_monthly_take_home_at_retirement = 0

    if annual_withdrawal_pre_tax > PENSION_TAX_THRESHOLD:
        st.info(f"연간 수령액이 {PENSION_TAX_THRESHOLD/10000:,.0f}만원을 초과하여 종합과세 대상입니다.")
        
        # 이 입력창도 세션 상태와 연결하여 실시간 반영
        st.number_input("연금저축 외 다른 소득의 연간 과세표준을 입력하세요 (없으면 0)", step=1000000, key="other_income_base")
        
        pension_deduction = calculate_pension_income_deduction(annual_withdrawal_pre_tax)
        taxable_pension_income = annual_withdrawal_pre_tax - pension_deduction
        
        total_taxable_income = taxable_pension_income + st.session_state.other_income_base
        tax_on_other_income = calculate_comprehensive_tax(st.session_state.other_income_base)
        tax_on_total_income = calculate_comprehensive_tax(total_taxable_income)
        comprehensive_pension_tax = tax_on_total_income - tax_on_other_income
        separate_pension_tax = annual_withdrawal_pre_tax * SEPARATE_TAX_RATE

        st.subheader("세금 비교")
        col1, col2 = st.columns(2)
        col1.metric("종합과세 선택 시", f"{comprehensive_pension_tax:,.0f} 원")
        col2.metric("분리과세 선택 시 (16.5%)", f"{separate_pension_tax:,.0f} 원")

        if comprehensive_pension_tax < separate_pension_tax:
            final_tax = comprehensive_pension_tax
            st.success("종합과세가 더 유리합니다.")
        elif separate_pension_tax < comprehensive_pension_tax:
            final_tax = separate_pension_tax
            st.success("분리과세가 더 유리합니다.")
        else:
            final_tax = separate_pension_tax
            st.success("두 방식의 예상 세액이 동일합니다.")
        
        monthly_take_home = (annual_withdrawal_pre_tax - final_tax) / 12
        base_monthly_take_home_at_retirement = monthly_take_home
        st.metric("모든 연령대 월 실수령액", f"{monthly_take_home:,.0f} 원")

    else:
        st.info(f"연간 수령액이 {PENSION_TAX_THRESHOLD/10000:,.0f}만원 이하로 연령별 연금소득세가 적용됩니다.")
        
        if st.session_state.retirement_age < 70: initial_rate = PENSION_TAX_RATES["under_70"]
        elif st.session_state.retirement_age < 80: initial_rate = PENSION_TAX_RATES["under_80"]
        else: initial_rate = PENSION_TAX_RATES["over_80"]
        base_monthly_take_home_at_retirement = monthly_withdrawal_pre_tax * (1 - initial_rate)
        
        data = []
        age_ranges = [(st.session_state.retirement_age, 69), (70, 79), (80, st.session_state.end_age)]
        for start, end in age_ranges:
            if st.session_state.retirement_age > end or st.session_state.end_age <= start: continue
            start_display = max(st.session_state.retirement_age, start)
            end_display = min(st.session_state.end_age - 1, end)
            if start_display > end_display: continue
            
            if start < 70: rate = PENSION_TAX_RATES["under_70"]
            elif start < 80: rate = PENSION_TAX_RATES["under_80"]
            else: rate = PENSION_TAX_RATES["over_80"]
            
            take_home = monthly_withdrawal_pre_tax * (1 - rate)
            data.append({"구간": f"{start_display}세 ~ {end_display}세", "월 실수령액 (원)": f"{take_home:,.0f}", "세율": f"{rate*100:.1f}%"})
        
        st.table(data)
    
    st.header("🕒 은퇴 후 첫 월급의 현재가치")
    years_to_discount = st.session_state.retirement_age - st.session_state.start_age
    present_value_of_pension = base_monthly_take_home_at_retirement / ((1 + inflation_rate) ** years_to_discount)
    st.markdown(f"미래({st.session_state.retirement_age}세)에 받을 첫 월 실수령액 **{base_monthly_take_home_at_retirement:,.0f}원**은,")
    st.markdown(f"연평균 물가상승률(연 {inflation_rate * 100:.1f}%)을 감안하면, **현재 시점의 약 {present_value_of_pension:,.0f}원**과 같은 가치입니다.")

with st.expander("주의사항 보기"):
    st.caption("""
    1. **계산 대상**: 본 계산기는 '연금저축'을 가정합니다. IRP(특히 퇴직금 재원)는 세금 계산 방식이 다를 수 있습니다.
    2. **세금**: 실제 세금은 개인별 소득/세액공제(부양가족, 의료비 등)에 따라 달라집니다.
    3. **수익률**: 투자는 원금 손실이 가능하며, 수익률과 물가상승률은 예측과 다를 수 있습니다.
    4. **연금재원**: 세액공제 받지 않은 납입금(비과세 재원)은 계산에 미반영되었습니다.
    5. **세법 개정**: 본 계산은 2025년 기준 세법을 따르며, 향후 세법 개정에 따라 실제 수령액은 달라질 수 있습니다.
    """)

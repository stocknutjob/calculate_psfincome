import streamlit as st
import pandas as pd
import plotly.express as px

# --------------------------------------------------------------------------
# --- 1. 계산 함수들 (Functions for Calculation) ---
# --------------------------------------------------------------------------

def calculate_total_at_retirement(start_age, retirement_age, annual_contribution, pre_retirement_return):
    """납입 정보와 수익률을 바탕으로 은퇴 시점의 총 적립금을 계산하고, 연도별 자산 성장 데이터를 반환합니다."""
    monthly_contribution = annual_contribution / 12
    contribution_years = retirement_age - start_age
    monthly_return = (1 + pre_retirement_return)**(1/12) - 1
    
    asset_growth = []
    current_value = 0
    for year in range(contribution_years):
        for month in range(12):
            current_value = (current_value + monthly_contribution) * (1 + monthly_return)
        asset_growth.append({'year': start_age + year + 1, 'value': current_value})

    return current_value, pd.DataFrame(asset_growth)

def calculate_pension_payouts(total_at_retirement, payout_years, post_retirement_return):
    """은퇴 시점 총 적립금을 수령 기간과 은퇴 후 수익률에 맞춰 월 수령액으로 변환합니다."""
    total_months_withdrawal = payout_years * 12
    monthly_return = (1 + post_retirement_return)**(1/12) - 1
    if monthly_return == 0:
        return total_at_retirement / total_months_withdrawal if total_months_withdrawal > 0 else 0
    annuity_factor = monthly_return / (1 - (1 + monthly_return)**-total_months_withdrawal)
    return total_at_retirement * annuity_factor

def calculate_pension_income_deduction(pension_income):
    """연간 연금소득액에 대한 연금소득공제 금액을 계산합니다. (2025년 기준)"""
    if pension_income <= 3_500_000: return pension_income
    elif pension_income <= 7_000_000: return 3_500_000 + (pension_income - 3_500_000) * 0.4
    elif pension_income <= 14_000_000: return 4_900_000 + (pension_income - 7_000_000) * 0.2
    else: return min(6_300_000 + (pension_income - 14_000_000) * 0.1, 9_000_000)

def calculate_comprehensive_tax(taxable_income):
    """주어진 소득 과세표준에 대한 종합소득세 산출세액을 계산합니다."""
    if taxable_income <= 0: return 0
    COMPREHENSIVE_TAX_BRACKETS = [
        (14_000_000, 0.066, 0), (50_000_000, 0.165, 1_260_000 * 1.1),
        (88_000_000, 0.264, 5_760_000 * 1.1), (150_000_000, 0.385, 15_440_000 * 1.1),
        (300_000_000, 0.418, 19_940_000 * 1.1), (500_000_000, 0.440, 25_940_000 * 1.1),
        (1_000_000_000, 0.462, 35_940_000 * 1.1), (float('inf'), 0.495, 65_940_000 * 1.1),
    ]
    for threshold, rate, deduction in COMPREHENSIVE_TAX_BRACKETS:
        if taxable_income <= threshold: return taxable_income * rate - deduction
    return 0

# --------------------------------------------------------------------------
# --- 2. UI 및 결과 표시 함수들 (Functions for Display) ---
# --------------------------------------------------------------------------

def display_asset_visuals(total_at_retirement, total_principal, asset_growth_df):
    """자산 성장 그래프와 기여도 파이차트를 시각화합니다."""
    st.header("📊 자산 성장 시각화")
    
    col1, col2 = st.columns([2, 1])
    with col1:
        st.subheader("연령별 예상 적립금 추이")
        st.line_chart(asset_growth_df.rename(columns={'year':'나이', 'value':'적립금'}).set_index('나이'))

    with col2:
        st.subheader("최종 적립금 기여도")
        total_profit = total_at_retirement - total_principal
        if total_profit < 0: total_profit = 0
        
        pie_data = pd.DataFrame({'금액': [total_principal, total_profit], '항목': ['총 납입 원금', '총 투자 수익']})
        fig = px.pie(pie_data, values='금액', names='항목', hole=.3, color_discrete_sequence=px.colors.sequential.Blues_r)
        fig.update_traces(textposition='inside', textinfo='percent+label')
        st.plotly_chart(fig, use_container_width=True)

def display_payout_analysis(retirement_age, end_age, taxable_monthly_payout, other_income_base):
    """세후 실수령액 및 세금 비교 결과를 표시합니다."""
    st.header("💰 나이별 월 실수령액 (세후)")
    taxable_annual_payout = taxable_monthly_payout * 12
    base_monthly_take_home = 0
    
    if taxable_annual_payout > PENSION_TAX_THRESHOLD:
        st.info(f"과세 대상 연간 수령액이 {PENSION_TAX_THRESHOLD/10000:,.0f}만원을 초과하여 종합과세 대상입니다.")
        
        pension_deduction = calculate_pension_income_deduction(taxable_annual_payout)
        taxable_pension_income = taxable_annual_payout - pension_deduction
        total_taxable_income = taxable_pension_income + other_income_base
        tax_on_other_income = calculate_comprehensive_tax(other_income_base)
        tax_on_total_income = calculate_comprehensive_tax(total_taxable_income)
        comprehensive_pension_tax = tax_on_total_income - tax_on_other_income
        separate_pension_tax = taxable_annual_payout * SEPARATE_TAX_RATE

        st.subheader("세금 비교")
        col1, col2 = st.columns(2)
        col1.metric("종합과세 선택 시", f"{comprehensive_pension_tax:,.0f} 원")
        col2.metric("분리과세 선택 시 (16.5%)", f"{separate_pension_tax:,.0f} 원")

        if comprehensive_pension_tax < separate_pension_tax: final_tax = comprehensive_pension_tax; st.success("종합과세가 더 유리합니다.")
        elif separate_pension_tax < comprehensive_pension_tax: final_tax = separate_pension_tax; st.success("분리과세가 더 유리합니다.")
        else: final_tax = separate_pension_tax; st.success("두 방식의 예상 세액이 동일합니다.")
        
        base_monthly_take_home = (taxable_annual_payout - final_tax) / 12
        st.metric("모든 연령대 과세대상 월 실수령액", f"{base_monthly_take_home:,.0f} 원")

    else:
        st.info(f"과세 대상 연간 수령액이 {PENSION_TAX_THRESHOLD/10000:,.0f}만원 이하로 연령별 연금소득세가 적용됩니다.")
        if retirement_age < 70: initial_rate = PENSION_TAX_RATES["under_70"]
        elif retirement_age < 80: initial_rate = PENSION_TAX_RATES["under_80"]
        else: initial_rate = PENSION_TAX_RATES["over_80"]
        base_monthly_take_home = taxable_monthly_payout * (1 - initial_rate)
        
        data = []
        age_ranges = [(retirement_age, 69), (70, 79), (80, end_age)]
        for start, end in age_ranges:
            if retirement_age > end or end_age <= start: continue
            start_display = max(retirement_age, start); end_display = min(end_age - 1, end)
            if start_display > end_display: continue
            if start < 70: rate = PENSION_TAX_RATES["under_70"]
            elif start < 80: rate = PENSION_TAX_RATES["under_80"]
            else: rate = PENSION_TAX_RATES["over_80"]
            take_home = taxable_monthly_payout * (1 - rate)
            data.append({"구간": f"{start_display}세 ~ {end_display}세", "과세대상 월 실수령액 (원)": f"{take_home:,.0f}", "세율": f"{rate*100:.1f}%"})
        st.table(data)
    
    return base_monthly_take_home

def display_present_value_analysis(s, base_monthly_take_home, taxable_monthly_payout, taxable_annual_payout, inflation_rate):
    """연금의 현재가치를 분석하여 표시합니다."""
    with st.expander("🕒 연금의 현재가치 분석 보기"):
        years_to_discount = s.retirement_age - s.start_age
        monthly_inflation_rate = (1 + inflation_rate)**(1/12) - 1
        
        col1, col2 = st.columns(2)
        with col1:
            st.subheader("첫 연금(월)의 현재가치")
            present_value_of_first_month = base_monthly_take_home / ((1 + inflation_rate) ** years_to_discount)
            st.metric("현재가치", f"{present_value_of_first_month:,.0f} 원", help=f"미래({s.retirement_age}세)에 받을 첫 월 실수령액 {base_monthly_take_home:,.0f}원의 현재가치입니다.")

        with col2:
            st.subheader("첫 연금(연간)의 현재가치")
            first_year_present_value = 0
            for month_offset in range(12):
                months_to_discount_pv = years_to_discount * 12 + month_offset
                discounted_value = base_monthly_take_home / ((1 + monthly_inflation_rate) ** (months_to_discount_pv if monthly_inflation_rate > 0 else 1))
                first_year_present_value += discounted_value
            st.metric("현재가치", f"{first_year_present_value:,.0f} 원", help=f"미래({s.retirement_age}세)에 받을 첫 해 연금 총액(세후) {base_monthly_take_home*12:,.0f}원의 현재가치입니다.")

        st.subheader("연금 총액의 현재가치")
        total_present_value = 0
        payout_years = s.end_age - s.retirement_age
        for year_offset in range(payout_years):
            current_age = s.retirement_age + year_offset
            if taxable_annual_payout > PENSION_TAX_THRESHOLD:
                monthly_take_home = base_monthly_take_home
            else:
                if current_age < 70: rate = PENSION_TAX_RATES["under_70"]
                elif current_age < 80: rate = PENSION_TAX_RATES["under_80"]
                else: rate = PENSION_TAX_RATES["over_80"]
                monthly_take_home = taxable_monthly_payout * (1 - rate)
            for month_offset in range(12):
                months_to_discount_pv = years_to_discount * 12 + year_offset * 12 + month_offset
                discounted_value = monthly_take_home / ((1 + monthly_inflation_rate) ** (months_to_discount_pv if monthly_inflation_rate > 0 else 1))
                total_present_value += discounted_value
        st.markdown(f"은퇴 후 **{payout_years}년간** 받을 연금 총액을 현재가치로 환산하면,")
        st.metric("총 연금의 현재가치", f"약 {total_present_value:,.0f} 원")

# --------------------------------------------------------------------------
# --- 3. 메인 앱 로직 (Main App Logic) ---
# --------------------------------------------------------------------------

st.set_page_config(layout="wide", page_title="연금저축 계산기")
st.title("연금저축 예상 수령액 계산기")

# --- 상수 및 세션 상태 초기화 ---
MIN_RETIREMENT_AGE, MIN_CONTRIBUTION_YEARS, MIN_PAYOUT_YEARS = 55, 5, 10
PENSION_TAX_THRESHOLD, SEPARATE_TAX_RATE = 15_000_000, 0.165
PENSION_TAX_RATES = {"under_70": 0.055, "under_80": 0.044, "over_80": 0.033}

def reset_calculation_state():
    st.session_state.calculated = False

if 'start_age' not in st.session_state:
    st.session_state.start_age = 30
    st.session_state.retirement_age = 60
    st.session_state.end_age = 90
    st.session_state.investment_profile = '중립형'
    st.session_state.pre_retirement_return_input = 6.0
    st.session_state.post_retirement_return_input = 4.0
    st.session_state.inflation_rate_input = 3.0
    st.session_state.annual_contribution = 6000000
    st.session_state.non_deductible_contribution = 0
    st.session_state.other_income_base = 0
    st.session_state.calculated = False
    st.session_state.has_calculated_once = False

# --- 사용자 입력 (사이드바) ---
with st.sidebar:
    st.header("정보 입력")
    
    st.number_input("납입 시작 나이", min_value=15, max_value=100, key="start_age", on_change=reset_calculation_state)
    st.number_input("은퇴 나이", min_value=1, max_value=100, key="retirement_age", on_change=reset_calculation_state)
    st.number_input("수령 종료 나이", min_value=1, max_value=120, key="end_age", on_change=reset_calculation_state)
    
    st.subheader("투자 성향 및 수익률 (%)")
    profiles = {'안정형': (4.0, 3.0), '중립형': (6.0, 4.0), '공격형': (8.0, 5.0), '직접 입력': (st.session_state.pre_retirement_return_input, st.session_state.post_retirement_return_input)}
    profile_help = "각 투자 성향별 예상 수익률(은퇴 전/후)입니다:\n- 안정형: 4.0% / 3.0%\n- 중립형: 6.0% / 4.0%\n- 공격형: 8.0% / 5.0%"
    profile = st.selectbox("투자 성향 선택", options=list(profiles.keys()), key="investment_profile", on_change=reset_calculation_state, help=profile_help)
    
    if profile == '직접 입력':
        st.number_input("은퇴 전 수익률", format="%.1f", step=0.1, key="pre_retirement_return_input", on_change=reset_calculation_state)
        st.number_input("은퇴 후 수익률", format="%.1f", step=0.1, key="post_retirement_return_input", on_change=reset_calculation_state)
    else:
        st.session_state.pre_retirement_return_input, st.session_state.post_retirement_return_input = profiles[profile]

    st.number_input("예상 연평균 물가상승률", format="%.1f", step=0.1, key="inflation_rate_input", on_change=reset_calculation_state)

    st.subheader("연간 납입액 (원)")
    st.info("세액공제 한도: 연 600만원\n\n계좌 총 납입 한도: 연 1,800만원")
    st.number_input("연간 총 납입액", step=100000, key="annual_contribution", on_change=reset_calculation_state)
    st.number_input("이 중, 세액공제 받지 않는 금액", step=100000, key="non_deductible_contribution", on_change=reset_calculation_state, help="연 600만원을 초과하여 납입하는 금액 등, 세액공제 혜택을 받지 않은 원금은 나중에 연금 수령 시 비과세됩니다.")
    
    st.subheader("기타 소득 정보")
    st.number_input("연금 외 다른 소득의 연간 과세표준", step=1000000, key="other_income_base", on_change=reset_calculation_state, help="종합소득에서 각종 공제를 모두 뺀 후, 세금이 부과되는 최종 금액입니다. 종합과세 시에만 사용됩니다.")

    if st.button("결과 확인하기"):
        st.session_state.warnings = []
        if not (st.session_state.start_age < st.session_state.retirement_age < st.session_state.end_age):
            st.error("나이 순서(시작 < 은퇴 < 종료)가 올바르지 않습니다.")
            st.session_state.calculated = False
        else:
            st.session_state.calculated = True
            st.session_state.has_calculated_once = True

# --- 결과 표시 (메인 화면) ---
if st.session_state.calculated:
    if st.session_state.get("warnings"):
        for warning in st.session_state.warnings: st.warning(warning)
        st.session_state.warnings = []

    s = st.session_state
    payout_years = s.end_age - s.retirement_age
    pre_ret_return = s.pre_retirement_return_input / 100.0
    post_ret_return = s.post_retirement_return_input / 100.0
    inflation_rate = s.inflation_rate_input / 100.0
    
    contribution_years = s.retirement_age - s.start_age
    total_principal_paid = s.annual_contribution * contribution_years
    total_non_deductible_paid = s.non_deductible_contribution * contribution_years

    total_at_retirement, asset_growth_df = calculate_total_at_retirement(s.start_age, s.retirement_age, s.annual_contribution, pre_ret_return)
    monthly_withdrawal_pre_tax = calculate_pension_payouts(total_at_retirement, payout_years, post_ret_return)
    
    non_taxable_ratio = (total_non_deductible_paid / total_at_retirement) if total_at_retirement > 0 else 0
    non_taxable_monthly_payout = monthly_withdrawal_pre_tax * non_taxable_ratio
    taxable_monthly_payout = monthly_withdrawal_pre_tax - non_taxable_monthly_payout
    taxable_annual_payout = taxable_monthly_payout * 12 # [수정] 누락된 변수 계산 추가
    
    st.header("📈 예상 결과")
    col1, col2 = st.columns(2)
    col1.metric(f"{s.retirement_age}세 시점 총 적립금", f"{total_at_retirement:,.0f} 원")
    col2.metric("월 수령액 (세전)", f"{monthly_withdrawal_pre_tax:,.0f} 원", help=f"과세대상 {taxable_monthly_payout:,.0f}원 + 비과세 {non_taxable_monthly_payout:,.0f}원")
    
    display_asset_visuals(total_at_retirement, total_principal_paid, asset_growth_df)
    
    base_monthly_take_home_taxable = display_payout_analysis(s.retirement_age, s.end_age, taxable_monthly_payout, s.other_income_base)
    
    # [수정] 수정된 함수 호출에 맞게 인자 전달
    display_present_value_analysis(s, base_monthly_take_home_taxable + non_taxable_monthly_payout, taxable_monthly_payout, taxable_annual_payout, inflation_rate)

else:
    if st.session_state.get('has_calculated_once', False):
        st.info("입력값이 바뀌었습니다. 사이드바에서 '결과 확인하기' 버튼을 다시 눌러주세요.")
    else:
        st.info("사이드바에서 정보를 입력하고 '결과 확인하기' 버튼을 눌러주세요.")

with st.expander("주의사항 보기"):
    st.caption("""
    1. **계산 대상**: 본 계산기는 '연금저축'을 가정합니다. IRP(특히 퇴직금 재원)는 세금 계산 방식이 다를 수 있습니다.
    2. **세금**: 실제 세금은 개인별 소득/세액공제(부양가족, 의료비 등)에 따라 달라집니다.
    3. **수익률**: 투자는 원금 손실이 가능하며, 수익률과 물가상승률은 예측과 다를 수 있습니다.
    4. **연금재원**: 세액공제 받지 않은 납입금(비과세 재원)은 계산에 미반영되었습니다.
    5. **세법 개정**: 본 계산은 2025년 기준 세법을 따르며, 향후 세법 개정에 따라 실제 수령액은 달라질 수 있습니다.
    """)

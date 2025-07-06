import streamlit as st
import pandas as pd
import plotly.express as px
from dataclasses import dataclass

# --- 데이터 클래스 및 상수 정의 ---
@dataclass
class UserInput:
    """사용자 입력을 관리하는 데이터 클래스"""
    start_age: int
    retirement_age: int
    end_age: int
    pre_retirement_return: float
    post_retirement_return: float
    inflation_rate: float
    annual_contribution: int
    non_deductible_contribution: int
    other_non_deductible_total: int
    other_pension_income: int
    other_comprehensive_income: int
    income_level: str
    contribution_timing: str

# 소득 구간 선택 옵션
INCOME_LEVEL_LOW = '총급여 5,500만원 이하 (종합소득 4,500만원 이하)'
INCOME_LEVEL_HIGH = '총급여 5,500만원 초과 (종합소득 4,500만원 초과)'

# 세법 기준 상수
MIN_RETIREMENT_AGE, MIN_CONTRIBUTION_YEARS, MIN_PAYOUT_YEARS = 55, 5, 10
PENSION_TAX_THRESHOLD, SEPARATE_TAX_RATE, OTHER_INCOME_TAX_RATE = 15_000_000, 0.165, 0.165
PENSION_SAVING_TAX_CREDIT_LIMIT, MAX_CONTRIBUTION_LIMIT = 6_000_000, 18_000_000
PENSION_TAX_RATES = {"under_70": 0.055, "under_80": 0.044, "over_80": 0.033}
LOCAL_TAX_RATE = 0.1

# 종합소득세 과세표준 구간
COMPREHENSIVE_TAX_BRACKETS = [
    (14_000_000, 0.06, 0), (50_000_000, 0.15, 1_260_000),
    (88_000_000, 0.24, 5_760_000), (150_000_000, 0.35, 15_440_000),
    (300_000_000, 0.38, 19_940_000), (500_000_000, 0.40, 25_940_000),
    (1_000_000_000, 0.42, 35_940_000), (float('inf'), 0.45, 65_940_000),
]

# --- 계산 함수 ---

def calculate_total_at_retirement(inputs: UserInput):
    """은퇴 시점의 총 예상 적립금을 계산합니다."""
    pre_ret_rate = inputs.pre_retirement_return / 100.0
    contribution_years = inputs.retirement_age - inputs.start_age

    asset_growth_data, current_value = [], 0
    for year in range(contribution_years):
        if inputs.contribution_timing == '연초':
            current_value = (current_value + inputs.annual_contribution) * (1 + pre_ret_rate)
        else:
            current_value = current_value * (1 + pre_ret_rate) + inputs.annual_contribution
        asset_growth_data.append({'year': inputs.start_age + year + 1, 'value': current_value})
    return current_value, pd.DataFrame(asset_growth_data)

def calculate_annual_pension_tax(payout_under_limit: float, other_pension_income: int, other_comprehensive_income: int, current_age: int) -> dict:
    """연간 연금소득세를 계산하고, 과세 방식 선택 과정을 반환합니다."""
    total_pension_gross = payout_under_limit + other_pension_income

    if total_pension_gross <= PENSION_TAX_THRESHOLD:
        if current_age < 70: rate = PENSION_TAX_RATES["under_70"]
        elif current_age < 80: rate = PENSION_TAX_RATES["under_80"]
        else: rate = PENSION_TAX_RATES["over_80"]
        tax = payout_under_limit * rate
        return {'chosen': tax, 'comprehensive': tax, 'separate': tax, 'choice': "저율과세"}
    else:
        # 옵션 A: 종합과세 시 추가되는 세액 계산
        # 1. 사적연금을 제외한 다른 소득에 대한 세금 계산
        taxable_other_income = (other_pension_income - get_pension_income_deduction_amount(other_pension_income)) + other_comprehensive_income
        tax_without_private_pension = get_comprehensive_tax(taxable_other_income)

        # 2. 사적연금을 포함한 총소득에 대한 세금 계산
        taxable_total_income = (total_pension_gross - get_pension_income_deduction_amount(total_pension_gross)) + other_comprehensive_income
        tax_with_private_pension = get_comprehensive_tax(taxable_total_income)

        # 3. 사적연금으로 인해 순수하게 증가하는 세액 계산
        tax_on_private_pension_comp = max(0, tax_with_private_pension - tax_without_private_pension)

        # 옵션 B: 16.5% 분리과세 시 세액 계산
        separate_tax = payout_under_limit * SEPARATE_TAX_RATE

        if tax_on_private_pension_comp < separate_tax:
            return {'chosen': tax_on_private_pension_comp, 'comprehensive': tax_on_private_pension_comp, 'separate': separate_tax, 'choice': "종합과세"}
        else:
            return {'chosen': separate_tax, 'comprehensive': tax_on_private_pension_comp, 'separate': separate_tax, 'choice': "분리과세"}

def run_payout_simulation(inputs: UserInput, total_at_retirement, total_non_deductible_paid):
    """연금 인출 시뮬레이션을 실행하여 연도별 상세 데이터를 생성합니다."""
    post_ret_rate = inputs.post_retirement_return / 100.0
    non_taxable_wallet = total_non_deductible_paid
    taxable_wallet = total_at_retirement - non_taxable_wallet
    payout_years = inputs.end_age - inputs.retirement_age
    annual_breakdown = []

    for year_offset in range(payout_years):
        current_balance = non_taxable_wallet + taxable_wallet
        if current_balance <= 0: break

        current_age = inputs.retirement_age + year_offset
        payout_year_count = year_offset + 1
        remaining_years = payout_years - year_offset

        # 1. 연간 수령액 계산 (연초 인출 기준)
        if remaining_years <= 0:
            annual_payout = 0
        elif post_ret_rate == 0:
            annual_payout = current_balance / remaining_years
        elif post_ret_rate <= -1: # -100% 수익률
            annual_payout = current_balance
        else:
            annuity_factor_ordinary = (1 - (1 + post_ret_rate)**-remaining_years) / post_ret_rate
            annuity_factor = annuity_factor_ordinary * (1 + post_ret_rate)
            annual_payout = current_balance / annuity_factor if annuity_factor > 0 else 0
        
        annual_payout = min(annual_payout, current_balance)

        # 2. 인출 재원 구분 (비과세 재원 우선 인출)
        from_non_taxable = min(annual_payout, non_taxable_wallet)
        from_taxable = annual_payout - from_non_taxable

        # 3. 과세 대상 인출액에 대한 세금 계산
        pension_tax_info = {'chosen': 0, 'comprehensive': 0, 'separate': 0, 'choice': "해당없음"}
        tax_on_limit_excess = 0
        pension_payout_under_limit = from_taxable

        # 연금수령한도 초과분 계산 (매년 계좌 평가액 기준으로 재계산)
        if payout_year_count <= 10:
            pension_payout_limit = (current_balance * 1.2) / (11 - payout_year_count)
            if from_taxable > pension_payout_limit:
                pension_payout_over_limit = from_taxable - pension_payout_limit
                pension_payout_under_limit = pension_payout_limit
                tax_on_limit_excess = pension_payout_over_limit * OTHER_INCOME_TAX_RATE

        # 한도 내 금액은 연금소득세 과세
        if pension_payout_under_limit > 0:
            pension_tax_info = calculate_annual_pension_tax(
                payout_under_limit=pension_payout_under_limit,
                other_pension_income=inputs.other_pension_income,
                other_comprehensive_income=inputs.other_comprehensive_income,
                current_age=current_age
            )

        pension_tax = pension_tax_info['chosen']
        total_tax_paid = pension_tax + tax_on_limit_excess
        annual_take_home = annual_payout - total_tax_paid

        # 4. 연말 잔액 업데이트 (인출 후 수익 발생)
        non_taxable_wallet = (non_taxable_wallet - from_non_taxable) * (1 + post_ret_rate)
        taxable_wallet = (taxable_wallet - from_taxable) * (1 + post_ret_rate)

        annual_breakdown.append({
            "나이": current_age, "연간 수령액(세전)": annual_payout,
            "연간 실수령액(세후)": annual_take_home, "납부세금(총)": total_tax_paid,
            "연금소득세": pension_tax, "한도초과 인출세금": tax_on_limit_excess,
            "연말 총 잔액": non_taxable_wallet + taxable_wallet,
            "과세대상 연금액": pension_payout_under_limit,
            "종합과세액": pension_tax_info['comprehensive'],
            "분리과세액": pension_tax_info['separate'],
            "선택": pension_tax_info['choice'],
        })
    return pd.DataFrame(annual_breakdown)

def get_pension_income_deduction_amount(pension_income):
    """연금소득공제액을 계산합니다."""
    if pension_income <= 3_500_000: return pension_income
    if pension_income <= 7_000_000: return 3_500_000 + (pension_income - 3_500_000) * 0.4
    if pension_income <= 14_000_000: return 4_900_000 + (pension_income - 7_000_000) * 0.2
    deduction = 6_300_000 + (pension_income - 14_000_000) * 0.1
    return min(deduction, 9_000_000)

def get_comprehensive_tax(taxable_income, include_local_tax=True):
    """종합소득 과세표준에 대한 세액을 계산합니다."""
    if taxable_income <= 0: return 0
    tax = 0
    for threshold, rate, deduction in COMPREHENSIVE_TAX_BRACKETS:
        if taxable_income <= threshold:
            tax = taxable_income * rate - deduction
            break
    return tax * (1 + LOCAL_TAX_RATE) if include_local_tax else tax

def calculate_lump_sum_tax(taxable_lump_sum):
    """연금계좌 일시금 수령 시 적용될 기타소득세를 계산합니다."""
    if taxable_lump_sum <= 0: return 0
    return taxable_lump_sum * OTHER_INCOME_TAX_RATE

# --- UI 및 결과 표시 함수 ---

def display_initial_summary(inputs: UserInput, total_at_retirement, simulation_df, total_tax_credit):
    """핵심 예상 결과를 3개의 지표로 요약하여 보여줍니다."""
    st.header("📈 예상 결과 요약")
    first_year_take_home = simulation_df.iloc[0]["연간 실수령액(세후)"] if not simulation_df.empty else 0
    
    col1, col2, col3 = st.columns(3)
    col1.metric(f"{inputs.retirement_age}세 시점 총 적립금", f"{total_at_retirement:,.0f} 원")
    col2.metric("첫 해 연간 수령액 (세후)", f"{first_year_take_home:,.0f} 원")
    col3.metric("총 예상 절세액 (세액공제)", f"{total_tax_credit:,.0f} 원", help="납입 기간 동안 최대로 받을 수 있는 세액공제 혜택의 총합입니다.")

def display_asset_visuals(total_at_retirement, total_principal, asset_growth_df):
    """자산 성장 그래프와 최종 기여도 파이 차트를 보여줍니다."""
    st.header("📊 자산 성장 시각화")
    col1, col2 = st.columns([2, 1])
    with col1:
        st.subheader("연령별 예상 적립금 추이")
        st.line_chart(asset_growth_df.rename(columns={'year':'나이', 'value':'적립금'}).set_index('나이'))
    with col2:
        st.subheader("최종 적립금 기여도")
        total_profit = total_at_retirement - total_principal
        if total_profit < 0:
            st.warning(f"총 투자 손실이 {total_profit:,.0f}원 발생했습니다.")
            pie_data = pd.DataFrame({'금액': [total_principal], '항목': ['총 납입 원금']})
        else:
            pie_data = pd.DataFrame({'금액': [total_principal, total_profit], '항목': ['총 납입 원금', '총 투자 수익']})
        fig = px.pie(pie_data, values='금액', names='항목', hole=.3, color_discrete_sequence=px.colors.sequential.Blues_r)
        fig.update_traces(textposition='inside', textinfo='percent+label')
        st.plotly_chart(fig, use_container_width=True)

def display_present_value_analysis(inputs: UserInput, simulation_df, total_at_retirement, total_non_deductible_paid):
    """현재가치 분석 및 일시금 수령액을 비교하여 보여줍니다."""
    st.header("🕒 현재가치 분석 및 일시금 수령 비교")

    # 일시금 수령액 계산
    taxable_lump_sum = total_at_retirement - total_non_deductible_paid
    lump_sum_tax = calculate_lump_sum_tax(taxable_lump_sum)
    lump_sum_take_home = total_at_retirement - lump_sum_tax
    lump_sum_help_text = f"은퇴 후 일시금 수령 시, 과세대상금액({taxable_lump_sum:,.0f}원)에 대해 기타소득세(16.5%)가 적용됩니다."
    
    # 첫 해 연금 수령액의 현재가치 계산
    first_year_pv = 0
    if not simulation_df.empty:
        inflation_rate = inputs.inflation_rate / 100.0
        first_year_row = simulation_df.iloc[0]
        first_year_take_home = first_year_row["연간 실수령액(세후)"]
        first_year_age = first_year_row["나이"]
        if 1 + inflation_rate > 0:
            first_year_pv = first_year_take_home / ((1 + inflation_rate) ** (first_year_age - inputs.start_age))
    
    pv_help_text = f"첫 해({inputs.retirement_age}세)에 받는 세후 연금수령액을 납입 시작 시점({inputs.start_age}세)의 가치로 환산({inputs.inflation_rate}%)한 금액입니다."

    col1, col2 = st.columns(2)
    with col1:
        st.subheader("연금 수령 시 (현재가치)")
        st.metric("첫 해 연금수령액의 현재가치", f"{first_year_pv:,.0f} 원", help=pv_help_text)
    with col2:
        st.subheader("일시금 수령 시 (세후)")
        st.metric("세후 일시금 수령액", f"{lump_sum_take_home:,.0f} 원", help=lump_sum_help_text)

def display_tax_choice_summary(simulation_df):
    """연금소득세 과세 방식 비교 결과를 보여줍니다."""
    st.header("💡 연금소득세 비교 분석")
    
    choice_df = simulation_df[simulation_df['선택'].isin(['종합과세', '분리과세'])].copy()
    
    if choice_df.empty:
        st.info("모든 연금 수령 기간 동안 총 연금소득이 1,500만원 이하로 예상되어, 유리한 저율 분리과세(3.3%~5.5%)가 적용됩니다.")
        return
        
    st.info("총 연금소득(다른 연금 포함)이 연 1,500만원을 초과하면 종합과세와 분리과세(16.5%) 중 더 유리한 쪽을 선택할 수 있습니다. 아래는 각 방식에 따른 예상 세금 비교입니다.")
    
    cols_to_format = ['과세대상 연금액', '종합과세액', '분리과세액', '연금소득세']
    for col in cols_to_format:
        choice_df[col] = choice_df[col].apply(lambda x: f"{x:,.0f} 원")

    display_cols = ['나이', '과세대상 연금액', '종합과세액', '분리과세액', '선택']
    st.dataframe(choice_df[display_cols], use_container_width=True, hide_index=True)

def display_simulation_details(simulation_df):
    """연금 인출 상세 시뮬레이션 결과(그래프, 테이블)를 보여줍니다."""
    st.info("실제 인출 순서(비과세 재원 우선) 및 연금수령한도를 반영한 연도별 상세 예상치입니다.")
    
    chart_df = simulation_df.melt(id_vars='나이', value_vars=['연간 실수령액(세후)', '연금소득세', '한도초과 인출세금'], var_name='항목', value_name='금액')
    fig = px.bar(chart_df, x='나이', y='금액', color='항목', title='연도별 연금 수령액 구성')
    st.plotly_chart(fig, use_container_width=True)
    
    display_df = simulation_df.copy()
    cols_to_format = ["연간 수령액(세전)", "연간 실수령액(세후)", "납부세금(총)", "연금소득세", "한도초과 인출세금", "연말 총 잔액"]
    for col in cols_to_format:
        display_df[col] = display_df[col].apply(lambda x: f"{x:,.0f} 원" if pd.notna(x) else "0 원")
    
    display_cols = ["나이", "연간 수령액(세전)", "연간 실수령액(세후)", "납부세금(총)", "연금소득세", "한도초과 인출세금"]
    st.dataframe(display_df[display_cols], use_container_width=True, hide_index=True)

# --- 메인 앱 로직 ---

st.set_page_config(layout="wide", page_title="연금저축 계산기")
st.title("연금저축 예상 수령액 계산기")

PROFILES = {'안정형': (4.0, 3.0), '중립형': (6.0, 4.0), '공격형': (8.0, 5.0), '직접 입력': (6.0, 4.0)}

# --- 콜백 함수 정의 ---
def reset_calculation_state():
    st.session_state.calculated = False

def update_from_profile():
    profile_key = st.session_state.investment_profile
    if profile_key != '직접 입력':
        pre_ret, post_ret = PROFILES[profile_key]
        st.session_state.pre_retirement_return = pre_ret
        st.session_state.post_retirement_return = post_ret
    reset_calculation_state()

def auto_calculate_non_deductible():
    if st.session_state.auto_calc_non_deductible:
        annual_contribution = st.session_state.annual_contribution
        st.session_state.non_deductible_contribution = max(0, annual_contribution - PENSION_SAVING_TAX_CREDIT_LIMIT)
    reset_calculation_state()

# --- 세션 상태 초기화 ---
def initialize_session():
    if 'initialized' in st.session_state:
        return

    st.session_state.start_age = 30
    st.session_state.retirement_age = 60
    st.session_state.end_age = 90
    st.session_state.pre_retirement_return = PROFILES['중립형'][0]
    st.session_state.post_retirement_return = PROFILES['중립형'][1]
    st.session_state.inflation_rate = 3.5
    st.session_state.annual_contribution = 9_000_000
    st.session_state.other_non_deductible_total = 0
    st.session_state.other_pension_income = 0
    st.session_state.other_comprehensive_income = 0
    st.session_state.income_level = INCOME_LEVEL_LOW
    st.session_state.contribution_timing = '연말'
    
    st.session_state.investment_profile = '중립형'
    st.session_state.auto_calc_non_deductible = True
    
    st.session_state.non_deductible_contribution = max(0, st.session_state.annual_contribution - PENSION_SAVING_TAX_CREDIT_LIMIT)
    
    st.session_state.calculated = False
    st.session_state.has_calculated_once = False
    st.session_state.initialized = True

initialize_session()

# --- 사이드바 UI 구성 ---
with st.sidebar:
    st.header("정보 입력")
    
    st.session_state.start_age = st.number_input("납입 시작 나이", 15, 100, key='start_age_input', on_change=reset_calculation_state, args=(st.session_state, 'start_age'))
    st.session_state.retirement_age = st.number_input("은퇴 나이", MIN_RETIREMENT_AGE, 100, key='retirement_age_input', on_change=reset_calculation_state, args=(st.session_state, 'retirement_age'))
    st.session_state.end_age = st.number_input("수령 종료 나이", st.session_state.retirement_age + MIN_PAYOUT_YEARS, 120, key='end_age_input', on_change=reset_calculation_state, args=(st.session_state, 'end_age'))

    st.subheader("투자 성향 및 수익률 (%)")
    profile_help = "각 투자 성향별 예상 수익률(은퇴 전/후)입니다:\n- 안정형: 4.0% / 3.0%\n- 중립형: 6.0% / 4.0%\n- 공격형: 8.0% / 5.0%"
    profile = st.selectbox("투자 성향 선택", list(PROFILES.keys()), key="investment_profile", on_change=update_from_profile, help=profile_help)
    is_direct_input = profile == '직접 입력'
    help_text_return = "투자는 원금 손실이 발생할 수 있으며, 손실이 예상될 경우에만 음수 값을 입력하세요."
    st.session_state.pre_retirement_return = st.number_input("은퇴 전 수익률", -99.9, 99.9, key='pre_retirement_return', format="%.1f", step=0.1, on_change=reset_calculation_state, disabled=not is_direct_input, help=help_text_return)
    st.session_state.post_retirement_return = st.number_input("은퇴 후 수익률", -99.9, 99.9, key='post_retirement_return', format="%.1f", step=0.1, on_change=reset_calculation_state, disabled=not is_direct_input, help=help_text_return)
    st.session_state.inflation_rate = st.number_input("예상 연평균 물가상승률", -99.9, 99.9, key='inflation_rate', format="%.1f", step=0.1, on_change=reset_calculation_state)
    
    st.subheader("연간 납입액 (원)")
    st.info(
        f"연금저축 세액공제 한도: 연 {PENSION_SAVING_TAX_CREDIT_LIMIT/10000:,.0f}만원\n"
        f"연금계좌 총 납입 한도: 연 {MAX_CONTRIBUTION_LIMIT/10000:,.0f}만원"
    )
    st.session_state.contribution_timing = st.radio("납입 시점", ['연말', '연초'], key='contribution_timing_radio', on_change=reset_calculation_state, horizontal=True, help="연초 납입은 납입금이 1년 치 수익을 온전히 반영하여 복리 효과가 더 큽니다.")
    st.session_state.annual_contribution = st.number_input("연간 총 납입액", 0, MAX_CONTRIBUTION_LIMIT, key='annual_contribution', step=100000, on_change=auto_calculate_non_deductible)
    st.checkbox("세액공제 한도 초과분을 비과세 원금으로 자동 계산", key="auto_calc_non_deductible", on_change=auto_calculate_non_deductible)
    st.session_state.non_deductible_contribution = st.number_input("└ 자동 계산된 비과세 원금 (연간)", 0, MAX_CONTRIBUTION_LIMIT, key='non_deductible_contribution', step=100000, on_change=reset_calculation_state, disabled=st.session_state.auto_calc_non_deductible)
    st.session_state.other_non_deductible_total = st.number_input("그 외, 세액공제 받지 않은 총액", 0, key='other_non_deductible_total', step=100000, on_change=reset_calculation_state, help="ISA 만기 이전분 등 납입 기간 동안 발생한 비과세 원금 총합을 입력합니다.")
    
    st.subheader("세금 정보")
    st.session_state.income_level = st.selectbox("연 소득 구간 (세액공제율 결정)", [INCOME_LEVEL_LOW, INCOME_LEVEL_HIGH], key='income_level_select', on_change=reset_calculation_state)
    st.info("**💡 은퇴 후 다른 소득이 있으신가요?**\n\n소득 종류에 따라 세금 계산이 달라집니다. 아래 항목을 구분해서 입력하면 더 정확한 결과를 얻을 수 있습니다.")
    st.session_state.other_pension_income = st.number_input("국민연금 등 다른 연금 소득 (연간 세전)", 0, key='other_pension_income_input', step=500000, on_change=reset_calculation_state)
    st.session_state.other_comprehensive_income = st.number_input("임대, 사업 등 그 외 종합소득금액", 0, key='other_comprehensive_income_input', step=1000000, on_change=reset_calculation_state, help="부동산 임대소득 등 사업소득금액(총수입-필요경비)을 입력하세요.")

    if st.button("결과 확인하기", type="primary"):
        # 최신 UI 값으로 UserInput 객체 생성
        current_inputs = UserInput(
            start_age=st.session_state.start_age, retirement_age=st.session_state.retirement_age, end_age=st.session_state.end_age,
            pre_retirement_return=st.session_state.pre_retirement_return, post_retirement_return=st.session_state.post_retirement_return,
            inflation_rate=st.session_state.inflation_rate, annual_contribution=st.session_state.annual_contribution,
            non_deductible_contribution=st.session_state.non_deductible_contribution, other_non_deductible_total=st.session_state.other_non_deductible_total,
            other_pension_income=st.session_state.other_pension_income, other_comprehensive_income=st.session_state.other_comprehensive_income,
            income_level=st.session_state.income_level, contribution_timing=st.session_state.contribution_timing
        )
        st.session_state.user_input_obj = current_inputs

        errors = []
        ui = current_inputs
        if not (ui.start_age < ui.retirement_age < ui.end_age): errors.append("나이 순서(시작 < 은퇴 < 종료)가 올바르지 않습니다.")
        if ui.retirement_age < MIN_RETIREMENT_AGE: errors.append(f"은퇴 나이는 만 {MIN_RETIREMENT_AGE}세 이상이어야 합니다.")
        if ui.retirement_age - ui.start_age < MIN_CONTRIBUTION_YEARS: errors.append(f"최소 납입 기간은 {MIN_CONTRIBUTION_YEARS}년입니다.")
        if ui.end_age - ui.retirement_age < MIN_PAYOUT_YEARS: errors.append(f"최소 연금 수령 기간은 {MIN_PAYOUT_YEARS}년입니다.")
        if ui.annual_contribution > MAX_CONTRIBUTION_LIMIT: errors.append(f"연간 총 납입액은 최대 한도({MAX_CONTRIBUTION_LIMIT:,.0f}원)를 초과할 수 없습니다.")
        if ui.non_deductible_contribution > ui.annual_contribution: errors.append("'비과세 원금'은 '연간 총 납입액'보다 클 수 없습니다.")
        
        if errors:
            for error in errors: st.error(error, icon="🚨")
            st.session_state.calculated = False
        else:
            st.session_state.calculated = True
            st.session_state.has_calculated_once = True

# --- 결과 표시 로직 ---
if st.session_state.get('calculated', False):
    ui = st.session_state.user_input_obj
    contribution_years = ui.retirement_age - ui.start_age
    total_principal_paid = ui.annual_contribution * contribution_years
    non_deductible_from_annual = ui.non_deductible_contribution * contribution_years
    total_non_deductible_paid = non_deductible_from_annual + ui.other_non_deductible_total
    
    tax_credit_rate = 0.165 if ui.income_level == INCOME_LEVEL_LOW else 0.132
    tax_credit_base = ui.annual_contribution - ui.non_deductible_contribution
    tax_credit_per_year = min(tax_credit_base, PENSION_SAVING_TAX_CREDIT_LIMIT) * tax_credit_rate
    total_tax_credit = tax_credit_per_year * contribution_years

    total_at_retirement, asset_growth_df = calculate_total_at_retirement(ui)
    
    if total_at_retirement > 0:
        simulation_df = run_payout_simulation(ui, total_at_retirement, total_non_deductible_paid)
        
        display_initial_summary(ui, total_at_retirement, simulation_df, total_tax_credit)
        display_asset_visuals(total_at_retirement, total_principal_paid, asset_growth_df)
        display_present_value_analysis(ui, simulation_df, total_at_retirement, total_non_deductible_paid)
        
        if not simulation_df.empty:
            display_tax_choice_summary(simulation_df)
            with st.expander("연금 인출 상세 시뮬레이션 보기"):
                display_simulation_details(simulation_df)
        else:
            st.warning("인출 기간 동안 수령할 금액이 없습니다. 은퇴 시점 잔액이 너무 적거나 인출 기간이 짧을 수 있습니다.")
    else:
        st.warning("계산 결과, 은퇴 시점 적립금이 0원 이하입니다. 납입액이나 수익률을 조정해주세요.")
else:
    if st.session_state.get('has_calculated_once', False):
        st.info("입력값이 바뀌었습니다. 사이드바에서 '결과 확인하기' 버튼을 다시 눌러주세요.")
    else:
        st.info("사이드바에서 정보를 입력하고 '결과 확인하기' 버튼을 눌러주세요.")

with st.expander("주의사항 및 가정 보기"):
    st.caption("""
    1. **계산 대상**: '연금저축' 계좌만을 가정하며, IRP 계좌의 퇴직금 재원은 고려하지 않습니다.
    2. **납입 및 수령 가정**: 연간 납입은 사이드바 옵션(연초/연말)을 따르며, 연금 수령은 **매년 초**에 이루어진다고 가정합니다. (인출 후 잔액에 대해 연간 수익 발생)
    3. **세금**: 모든 세금 계산은 **지방소득세(소득세의 10%)를 포함**하며, 개인별 공제 항목에 따라 실제 세금은 달라질 수 있습니다.
    4. **수익률 및 물가**: 입력된 수익률과 물가상승률이 매년 일정하게 유지된다고 가정한 결과입니다. 실제 투자는 원금 손실의 위험이 있습니다.
    5. **연금수령한도**: 연금 수령 1~10년차에 적용되는 한도는 **'해당 연도 개시 시점의 연금계좌 평가액'**을 기준으로 계산됩니다. 한도 초과 인출액은 기타소득세(16.5%)가 적용됩니다.
    6. **일시금 수령 세금**: 연금 수령 연령에 도달하여 연금 외 형태로 수령하는 경우, **기타소득세(16.5%)**가 적용되어 계산됩니다.
    7. **세법 기준**: 이 계산기는 **현행 세법**을 기반으로 하며, 향후 세법 개정 시 결과가 달라질 수 있습니다.
    """)

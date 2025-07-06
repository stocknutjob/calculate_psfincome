import streamlit as st
import pandas as pd
import plotly.express as px
from dataclasses import dataclass
import math

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

# 소득 구간 선택 옵션을 위한 상수
INCOME_LEVEL_LOW = '총급여 5,500만원 이하 (종합소득 4,500만원 이하)'
INCOME_LEVEL_HIGH = '총급여 5,500만원 초과 (종합소득 4,500만원 초과)'

# --- 2025년 귀속 세법 기준 상수 ---
MIN_RETIREMENT_AGE, MIN_CONTRIBUTION_YEARS, MIN_PAYOUT_YEARS = 55, 5, 10
MONTHS_IN_YEAR = 12
PENSION_TAX_THRESHOLD, SEPARATE_TAX_RATE, OTHER_INCOME_TAX_RATE = 15_000_000, 0.165, 0.165
PENSION_SAVING_TAX_CREDIT_LIMIT, MAX_CONTRIBUTION_LIMIT = 6_000_000, 18_000_000
PENSION_TAX_RATES = {"under_70": 0.055, "under_80": 0.044, "over_80": 0.033}
LOCAL_TAX_RATE = 0.1

# 2025년 귀속 종합소득세 과세표준 구간
COMPREHENSIVE_TAX_BRACKETS = [
    (14_000_000, 0.06, 0), (50_000_000, 0.15, 1_260_000),
    (88_000_000, 0.24, 5_760_000), (150_000_000, 0.35, 15_440_000),
    (300_000_000, 0.38, 19_940_000), (500_000_000, 0.40, 25_940_000),
    (1_000_000_000, 0.42, 35_940_000), (float('inf'), 0.45, 65_940_000),
]

# --- 계산 함수 ---

def calculate_total_at_retirement(inputs: UserInput):
    """은퇴 시점 총 적립금을 계산합니다."""
    pre_ret_rate = inputs.pre_retirement_return / 100.0
    contribution_years = inputs.retirement_age - inputs.start_age
    
    asset_growth_data, current_value = [], 0
    for year in range(contribution_years):
        if inputs.contribution_timing == '연초':
            # 연초 납입: (기존 자산 + 납입금)에 수익 발생
            current_value = (current_value + inputs.annual_contribution) * (1 + pre_ret_rate)
        else: # '연말' 납입
            # 연말 납입: 기존 자산에 수익 발생 후 납입금 추가
            current_value = current_value * (1 + pre_ret_rate) + inputs.annual_contribution
            
        asset_growth_data.append({'year': inputs.start_age + year + 1, 'value': current_value})

    return current_value, pd.DataFrame(asset_growth_data)

def calculate_annual_pension_tax(payout_under_limit: float, other_pension_income: int, other_comprehensive_income: int, current_age: int) -> float:
    """연간 연금소득세를 계산합니다. (유리한 과세 방식 자동 선택)"""
    # 2025년 귀속 세법 기준
    total_pension_gross = payout_under_limit + other_pension_income

    # CASE 1: 총 연금소득이 1,500만원 이하이면 저율 분리과세 적용
    if total_pension_gross <= PENSION_TAX_THRESHOLD:
        if current_age < 70: rate = PENSION_TAX_RATES["under_70"]
        elif current_age < 80: rate = PENSION_TAX_RATES["under_80"]
        else: rate = PENSION_TAX_RATES["over_80"]
        return payout_under_limit * rate

    # CASE 2: 총 연금소득이 1,500만원을 초과하면 종합과세와 분리과세 중 유리한 쪽 선택
    else:
        # 옵션 A: 종합과세 시 추가되는 세액 계산
        # A-1. 사적연금을 포함한 총 소득에 대한 세금 계산
        pension_deduction_total = get_pension_income_deduction_amount(total_pension_gross)
        tax_base_with_pension = (total_pension_gross - pension_deduction_total) + other_comprehensive_income
        tax_with_pension = get_comprehensive_tax(tax_base_with_pension)
        
        # A-2. 사적연금을 제외한 기존 소득에 대한 세금 계산
        base_pension_deduction = get_pension_income_deduction_amount(other_pension_income)
        tax_base_without_pension = (other_pension_income - base_pension_deduction) + other_comprehensive_income
        tax_without_pension = get_comprehensive_tax(tax_base_without_pension)
        
        # A-3. 사적연금으로 인해 추가로 발생하는 종합소득세액
        tax_on_private_pension_comp = max(0, tax_with_pension - tax_without_pension)
        
        # 옵션 B: 16.5% 분리과세 시 세액 계산
        separate_tax = payout_under_limit * SEPARATE_TAX_RATE
        
        # 두 옵션 중 세금이 더 적은 쪽을 최종 연금소득세로 결정
        return min(tax_on_private_pension_comp, separate_tax)

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
        if remaining_years <= 0: annual_payout = 0
        elif post_ret_rate == 0: annual_payout = current_balance / remaining_years
        else:
            if post_ret_rate > -1: # 수익률이 -100%가 아닌 경우
                # 연초 수령(Annuity Due) 기준의 연금지급률(annuity factor)
                annuity_factor_ordinary = (1 - (1 + post_ret_rate)**-remaining_years) / post_ret_rate
                annuity_factor = annuity_factor_ordinary * (1 + post_ret_rate)
            else:
                annuity_factor = 0
            annual_payout = current_balance / annuity_factor if annuity_factor > 0 else 0
        
        annual_payout = min(annual_payout, current_balance)

        # 2. 인출 재원 구분 (비과세 재원 우선 인출)
        from_non_taxable = min(annual_payout, non_taxable_wallet)
        from_taxable = annual_payout - from_non_taxable

        # 3. 과세 대상 인출액에 대한 세금 계산
        pension_tax, tax_on_limit_excess = 0, 0
        
        # 연금수령한도 초과 금액 분리 및 기타소득세(16.5%) 부과
        pension_payout_under_limit = from_taxable
        if payout_year_count <= 10:
            pension_payout_limit = (total_at_retirement * 1.2) / (11 - payout_year_count)
            if from_taxable > pension_payout_limit:
                pension_payout_over_limit = from_taxable - pension_payout_limit
                pension_payout_under_limit = pension_payout_limit
                tax_on_limit_excess = pension_payout_over_limit * OTHER_INCOME_TAX_RATE

        # 한도 내 금액은 연금소득세 과세
        if pension_payout_under_limit > 0:
            pension_tax = calculate_annual_pension_tax(
                payout_under_limit=pension_payout_under_limit,
                other_pension_income=inputs.other_pension_income,
                other_comprehensive_income=inputs.other_comprehensive_income,
                current_age=current_age
            )

        total_tax_paid = pension_tax + tax_on_limit_excess
        annual_take_home = annual_payout - total_tax_paid

        # 4. 연말 잔액 업데이트 (인출 후 수익 발생)
        non_taxable_wallet = (non_taxable_wallet - from_non_taxable) * (1 + post_ret_rate)
        taxable_wallet = (taxable_wallet - from_taxable) * (1 + post_ret_rate)
        
        annual_breakdown.append({
            "나이": current_age, "연간 수령액(세전)": annual_payout,
            "연간 실수령액(세후)": annual_take_home, "납부세금(총)": total_tax_paid,
            "연금소득세": pension_tax, "한도초과 인출세금": tax_on_limit_excess,
            "연말 총 잔액": non_taxable_wallet + taxable_wallet
        })
    return pd.DataFrame(annual_breakdown)

def get_pension_income_deduction_amount(pension_income):
    """연금소득공제액을 계산합니다. (2025년 귀속 세법 기준)"""
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

def calculate_retirement_tax(taxable_lump_sum, contribution_years):
    """일시금 수령 시 적용될 퇴직소득세를 계산합니다. (2025년 귀속 세법 기준)"""
    if taxable_lump_sum <= 0 or contribution_years <= 0: return 0
    
    # 1. 근속연수공제
    if contribution_years <= 5: years_deduction = contribution_years * 1_000_000
    elif contribution_years <= 10: years_deduction = 5_000_000 + (contribution_years - 5) * 2_000_000
    elif contribution_years <= 20: years_deduction = 15_000_000 + (contribution_years - 10) * 2_500_000
    else: years_deduction = 40_000_000 + (contribution_years - 20) * 3_000_000
    
    retirement_income = taxable_lump_sum - years_deduction
    if retirement_income <= 0: return 0

    # 2. 환산급여 계산 (연봉으로 환산)
    converted_salary = retirement_income / contribution_years
    
    # 3. 환산급여공제
    if converted_salary <= 8_000_000: converted_deduction = converted_salary
    elif converted_salary <= 70_000_000: converted_deduction = 8_000_000 + (converted_salary - 8_000_000) * 0.6
    elif converted_salary <= 100_000_000: converted_deduction = 45_200_000 + (converted_salary - 70_000_000) * 0.55
    elif converted_salary <= 300_000_000: converted_deduction = 61_700_000 + (converted_salary - 100_000_000) * 0.45
    else: converted_deduction = 151_700_000 + (converted_salary - 300_000_000) * 0.35
    
    # 4. 과세표준 및 세액 계산
    tax_base_annual = converted_salary - converted_deduction
    if tax_base_annual <= 0: return 0
    tax_calc_annual = get_comprehensive_tax(tax_base_annual, include_local_tax=False)
    final_tax_without_local = tax_calc_annual * contribution_years
    
    return final_tax_without_local * (1 + LOCAL_TAX_RATE)

# --- UI 및 결과 표시 함수 ---

def display_initial_summary(inputs: UserInput, total_at_retirement, first_year_payout, total_tax_credit):
    """계산 결과 요약을 표시합니다."""
    st.header("📈 예상 결과 요약")
    col1, col2, col3 = st.columns(3)
    col1.metric(f"{inputs.retirement_age}세 시점 총 적립금", f"{total_at_retirement:,.0f} 원")
    col2.metric("첫 해 월 수령액 (세전)", f"{first_year_payout/MONTHS_IN_YEAR:,.0f} 원" if first_year_payout else "0 원")
    col3.metric("총 예상 절세액 (세액공제)", f"{total_tax_credit:,.0f} 원", help="납입 기간 동안 최대로 받을 수 있는 세액공제 혜택의 총합입니다.")

def display_asset_visuals(total_at_retirement, total_principal, asset_growth_df):
    """자산 성장 그래프와 최종 기여도 파이 차트를 표시합니다."""
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

def display_simulation_details(simulation_df):
    """연금 인출 상세 시뮬레이션 결과(그래프, 테이블)를 표시합니다."""
    st.header("💰 연금 인출 상세 시뮬레이션")
    st.info("실제 인출 순서(비과세 재원 우선) 및 연금수령한도를 반영한 연도별 상세 예상치입니다.")
    with st.expander("시뮬레이션 결과 그래프 보기"):
        chart_df = simulation_df.melt(id_vars='나이', value_vars=['연간 실수령액(세후)', '연금소득세', '한도초과 인출세금'], var_name='항목', value_name='금액')
        fig = px.bar(chart_df, x='나이', y='금액', color='항목', title='연도별 연금 수령액 구성')
        st.plotly_chart(fig, use_container_width=True)
    
    display_df = simulation_df.copy()
    cols_to_format = ["연간 수령액(세전)", "연간 실수령액(세후)", "납부세금(총)", "연금소득세", "한도초과 인출세금", "연말 총 잔액"]
    for col in cols_to_format:
        display_df[col] = display_df[col].apply(lambda x: f"{x:,.0f} 원" if pd.notna(x) else "0 원")
    
    display_cols = ["나이", "연간 수령액(세전)", "연간 실수령액(세후)", "납부세금(총)", "연금소득세", "한도초과 인출세금"]
    st.dataframe(display_df[display_cols], use_container_width=True, hide_index=True)

def display_present_value_analysis(inputs: UserInput, simulation_df, total_at_retirement, total_non_deductible_paid):
    """연금 수령의 현재가치와 일시금 수령액을 비교 분석하여 표시합니다."""
    st.header("🕒 현재가치 분석 및 일시금 수령 비교")
    inflation_rate = inputs.inflation_rate / 100.0
    total_pension_take_home_pv = sum(row["연간 실수령액(세후)"] / ((1 + inflation_rate) ** (row["나이"] - inputs.start_age)) for _, row in simulation_df.iterrows() if 1 + inflation_rate > 0)
    
    taxable_lump_sum = total_at_retirement - total_non_deductible_paid
    contribution_years = inputs.retirement_age - inputs.start_age
    lump_sum_tax = calculate_retirement_tax(taxable_lump_sum, contribution_years)
    lump_sum_take_home = total_at_retirement - lump_sum_tax
    lump_sum_help_text = (f"은퇴 후 일시금 수령 시, 과세대상금액({taxable_lump_sum:,.0f}원)에 대해 퇴직소득세가 적용됩니다.")
    
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("연금 수령 시 (현재가치)")
        st.metric("총 실수령액의 현재가치", f"{total_pension_take_home_pv:,.0f} 원", help=f"매년 받는 세후 수령액을 납입 시작 시점({inputs.start_age}세)의 가치로 환산({inputs.inflation_rate}%)하여 모두 더한 금액입니다.")
    with col2:
        st.subheader("일시금 수령 시 (세후)")
        st.metric("세후 일시금 수령액", f"{lump_sum_take_home:,.0f} 원", help=lump_sum_help_text)

# --- 메인 앱 로직 ---

st.set_page_config(layout="wide", page_title="연금저축 계산기")
st.title("연금저축 예상 수령액 계산기")

# 투자 성향 프로필 정의
PROFILES = {'안정형': (4.0, 3.0), '중립형': (6.0, 4.0), '공격형': (8.0, 5.0), '직접 입력': (6.0, 4.0)}

# --- 콜백 함수 정의 ---
def reset_calculation_state():
    """입력값이 변경될 때 계산 상태를 초기화합니다."""
    st.session_state.calculated = False

def update_profile_and_reset():
    """투자 성향 프로필 선택 시 수익률을 업데이트하고 상태를 초기화합니다."""
    profile_key = st.session_state.investment_profile
    if profile_key != '직접 입력':
        pre_ret, post_ret = PROFILES[profile_key]
        st.session_state.user_input.pre_retirement_return = pre_ret
        st.session_state.user_input.post_retirement_return = post_ret
    reset_calculation_state()

def auto_calculate_non_deductible():
    """총 납입액 변경 시 세액공제 한도 초과분을 자동으로 계산합니다."""
    if st.session_state.get('auto_calc_non_deductible', False):
        if 'user_input' in st.session_state and hasattr(st.session_state.user_input, 'annual_contribution'):
            annual_contribution = st.session_state.user_input.annual_contribution
            st.session_state.user_input.non_deductible_contribution = max(0, annual_contribution - PENSION_SAVING_TAX_CREDIT_LIMIT)
    reset_calculation_state()

# 앱 최초 실행 시 세션 상태를 초기화합니다.
if 'user_input' not in st.session_state:
    st.session_state.user_input = UserInput(
        start_age=30, retirement_age=60, end_age=90,
        pre_retirement_return=PROFILES['중립형'][0], post_retirement_return=PROFILES['중립형'][1], 
        inflation_rate=2.5, annual_contribution=9_000_000, non_deductible_contribution=0,
        other_non_deductible_total=0, other_pension_income=0, other_comprehensive_income=0,
        income_level=INCOME_LEVEL_LOW,
        contribution_timing='연말'
    )
    st.session_state.investment_profile = '중립형'
    st.session_state.auto_calc_non_deductible = True
    st.session_state.calculated = False
    st.session_state.has_calculated_once = False
    auto_calculate_non_deductible()

# --- 사이드바 UI 구성 ---
with st.sidebar:
    st.header("정보 입력")
    ui = st.session_state.user_input
    
    ui.start_age, ui.retirement_age, ui.end_age = (
        st.number_input("납입 시작 나이", 15, 100, ui.start_age, on_change=reset_calculation_state),
        st.number_input("은퇴 나이", MIN_RETIREMENT_AGE, 100, ui.retirement_age, on_change=reset_calculation_state),
        st.number_input("수령 종료 나이", ui.retirement_age + MIN_PAYOUT_YEARS, 120, ui.end_age, on_change=reset_calculation_state)
    )
    
    st.subheader("투자 성향 및 수익률 (%)")
    profile_help = "각 투자 성향별 예상 수익률(은퇴 전/후)입니다:\n- 안정형: 4.0% / 3.0%\n- 중립형: 6.0% / 4.0%\n- 공격형: 8.0% / 5.0%"
    profile = st.selectbox("투자 성향 선택", list(PROFILES.keys()), key="investment_profile", on_change=update_profile_and_reset, help=profile_help)
    is_direct_input = profile == '직접 입력'
    help_text_return = "투자는 원금 손실이 발생할 수 있으며, 손실이 예상될 경우에만 음수 값을 입력하세요."
    ui.pre_retirement_return = st.number_input("은퇴 전 수익률", -99.9, 99.9, format="%.1f", step=0.1, value=ui.pre_retirement_return, on_change=reset_calculation_state, disabled=not is_direct_input, help=help_text_return)
    ui.post_retirement_return = st.number_input("은퇴 후 수익률", -99.9, 99.9, format="%.1f", step=0.1, value=ui.post_retirement_return, on_change=reset_calculation_state, disabled=not is_direct_input, help=help_text_return)
    ui.inflation_rate = st.number_input("예상 연평균 물가상승률", -99.9, 99.9, format="%.1f", step=0.1, value=ui.inflation_rate, on_change=reset_calculation_state)
    
    st.subheader("연간 납입액 (원)")
    st.info(f"연금계좌 총 세액공제 한도: 연 900만원\n(단, 이 계산기는 연금저축 단독 한도인 연 {PENSION_SAVING_TAX_CREDIT_LIMIT/10000:,.0f}만원까지만 자동 계산에 반영합니다.)\n계좌 총 납입 한도: 연 {MAX_CONTRIBUTION_LIMIT/10000:,.0f}만원")
    ui.contribution_timing = st.radio("납입 시점", ['연말', '연초'], index=0 if ui.contribution_timing == '연말' else 1, on_change=reset_calculation_state, horizontal=True, help="연초 납입은 납입금이 1년 치 수익을 온전히 반영하여 복리 효과가 더 큽니다.")
    ui.annual_contribution = st.number_input("연간 총 납입액", 0, MAX_CONTRIBUTION_LIMIT, ui.annual_contribution, 100000, on_change=auto_calculate_non_deductible)
    st.checkbox("세액공제 한도 초과분을 비과세 원금으로 자동 계산", key="auto_calc_non_deductible", on_change=auto_calculate_non_deductible)
    ui.non_deductible_contribution = st.number_input("└ 자동 계산된 비과세 원금 (연간)", 0, MAX_CONTRIBUTION_LIMIT, step=100000, value=ui.non_deductible_contribution, on_change=reset_calculation_state, disabled=st.session_state.auto_calc_non_deductible)
    ui.other_non_deductible_total = st.number_input("그 외, 세액공제 받지 않은 총액", 0, step=100000, value=ui.other_non_deductible_total, on_change=reset_calculation_state, help="ISA 만기 이전분 등 납입 기간 동안 발생한 비과세 원금 총합을 입력합니다.")
    
    st.subheader("세금 정보")
    ui.income_level = st.selectbox("연 소득 구간 (세액공제율 결정)", [INCOME_LEVEL_LOW, INCOME_LEVEL_HIGH], on_change=reset_calculation_state)
    st.info("**💡 은퇴 후 다른 소득이 있으신가요?**\n\n소득 종류에 따라 세금 계산이 달라집니다. 아래 항목을 구분해서 입력하면 더 정확한 결과를 얻을 수 있습니다.")
    ui.other_pension_income = st.number_input("국민연금 등 다른 연금 소득 (연간 세전)", 0, step=500000, value=ui.other_pension_income, on_change=reset_calculation_state)
    ui.other_comprehensive_income = st.number_input("임대, 사업 등 그 외 종합소득금액", 0, step=1000000, value=ui.other_comprehensive_income, on_change=reset_calculation_state, help="부동산 임대소득 등 사업소득금액(총수입-필요경비)을 입력하세요.")

    if st.button("결과 확인하기", type="primary"):
        errors = []
        if not (ui.start_age < ui.retirement_age < ui.end_age): errors.append("나이 순서(시작 < 은퇴 < 종료)가 올바르지 않습니다.")
        if ui.retirement_age < MIN_RETIREMENT_AGE: errors.append(f"은퇴 나이는 만 {MIN_RETIREMENT_AGE}세 이상이어야 합니다.")
        if ui.retirement_age - ui.start_age < MIN_CONTRIBUTION_YEARS: errors.append(f"최소 납입 기간은 {MIN_CONTRIBUTION_YEARS}년입니다.")
        if ui.end_age - ui.retirement_age < MIN_PAYOUT_YEARS: errors.append(f"최소 연금 수령 기간은 {MIN_PAYOUT_YEARS}년입니다.")
        if ui.annual_contribution > MAX_CONTRIBUTION_LIMIT: errors.append(f"연간 총 납입액은 최대 한도({MAX_CONTRIBUTION_LIMIT:,.0f}원)를 초과할 수 없습니다.")
        if ui.non_deductible_contribution > ui.annual_contribution: errors.append("'비과세 원금'은 '연간 총 납입액'보다 클 수 없습니다.")
        if ui.pre_retirement_return <= -100 or ui.post_retirement_return <= -100: errors.append("수익률은 -100%보다 커야 합니다.")
        
        if errors:
            for error in errors: st.error(error, icon="🚨")
            st.session_state.calculated = False
        else:
            st.session_state.calculated = True
            st.session_state.has_calculated_once = True

# --- 결과 표시 로직 ---
if st.session_state.get('calculated', False):
    ui = st.session_state.user_input
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
        first_year_payout = simulation_df.iloc[0]["연간 수령액(세전)"] if not simulation_df.empty else 0
        
        display_initial_summary(ui, total_at_retirement, first_year_payout, total_tax_credit)
        display_asset_visuals(total_at_retirement, total_principal_paid, asset_growth_df)
        
        if not simulation_df.empty:
            display_simulation_details(simulation_df)
            display_present_value_analysis(ui, simulation_df, total_at_retirement, total_non_deductible_paid)
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
    5. **연금수령한도**: 연금 수령 1~10년차에 적용되는 한도는 **'은퇴 시점의 연금계좌 총평가액'**을 기준으로 계산됩니다. 한도 초과 인출액은 기타소득세(16.5%)가 적용됩니다.
    6. **일시금 수령 세금**: 은퇴 후 일시금으로 수령하는 경우, 세법에 따라 **퇴직소득세**가 적용되어 계산됩니다.
    7. **세법 기준**: 이 계산기는 **현행 세법(2025년 기준)**을 기반으로 하며, 향후 세법 개정 시 결과가 달라질 수 있습니다.
    """)

import streamlit as st
import pandas as pd
import plotly.express as px
from dataclasses import dataclass

# --- 데이터 클래스 및 상수 정의 ---
@dataclass
class UserInput:
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

# 소득 구간 옵션
INCOME_LEVEL_LOW  = '총급여 5,500만원 이하 (종합소득 4,500만원 이하)'
INCOME_LEVEL_HIGH = '총급여 5,500만원 초과 (종합소득 4,500만원 초과)'

# 세법 기준
MIN_RETIREMENT_AGE, MIN_CONTRIBUTION_YEARS, MIN_PAYOUT_YEARS = 55, 5, 10
PENSION_TAX_THRESHOLD, SEPARATE_TAX_RATE, OTHER_INCOME_TAX_RATE = 15_000_000, 0.165, 0.165
PENSION_SAVING_TAX_CREDIT_LIMIT, MAX_CONTRIBUTION_LIMIT = 6_000_000, 18_000_000
PENSION_TAX_RATES = {"under_70": 0.055, "under_80": 0.044, "over_80": 0.033}
LOCAL_TAX_RATE = 0.1

COMPREHENSIVE_TAX_BRACKETS = [
    (14_000_000, 0.06, 0), (50_000_000, 0.15, 1_260_000),
    (88_000_000, 0.24, 5_760_000), (150_000_000, 0.35, 15_440_000),
    (300_000_000, 0.38, 19_940_000), (500_000_000, 0.40, 25_940_000),
    (1_000_000_000, 0.42, 35_940_000), (float('inf'), 0.45, 65_940_000),
]

# --- 계산 함수들 ---
def calculate_total_at_retirement(inputs: UserInput):
    pre_rate = inputs.pre_retirement_return / 100
    years = inputs.retirement_age - inputs.start_age
    data, val = [], 0
    for i in range(years):
        if inputs.contribution_timing == '연초':
            val = (val + inputs.annual_contribution) * (1 + pre_rate)
        else:
            val = val * (1 + pre_rate) + inputs.annual_contribution
        data.append({'year': inputs.start_age + i + 1, 'value': val})
    return val, pd.DataFrame(data)

def get_pension_income_deduction_amount(pension_income):
    if pension_income <= 3_500_000:
        return pension_income
    if pension_income <= 7_000_000:
        return 3_500_000 + (pension_income - 3_500_000) * 0.4
    if pension_income <= 14_000_000:
        return 4_900_000 + (pension_income - 7_000_000) * 0.2
    ded = 6_300_000 + (pension_income - 14_000_000) * 0.1
    return min(ded, 9_000_000)

def get_comprehensive_tax(taxable_income, include_local=True):
    if taxable_income <= 0:
        return 0
    tax = 0
    for threshold, rate, deduction in COMPREHENSIVE_TAX_BRACKETS:
        if taxable_income <= threshold:
            tax = taxable_income * rate - deduction
            break
    return tax * (1 + LOCAL_TAX_RATE) if include_local else tax

def calculate_annual_pension_tax(payout_under_limit, other_pension_income, other_comprehensive_income, current_age):
    total_pension_gross = payout_under_limit + other_pension_income

    # 저율 과세
    if total_pension_gross <= PENSION_TAX_THRESHOLD:
        if current_age < 70:
            rate = PENSION_TAX_RATES["under_70"]
        elif current_age < 80:
            rate = PENSION_TAX_RATES["under_80"]
        else:
            rate = PENSION_TAX_RATES["over_80"]
        tax = payout_under_limit * rate
        return {'chosen': tax, 'comprehensive': tax, 'separate': tax, 'choice': "저율과세"}

    # 종합과세 추가분
    base_tax = get_comprehensive_tax(
        (other_pension_income - get_pension_income_deduction_amount(other_pension_income))
        + other_comprehensive_income
    )
    total_tax = get_comprehensive_tax(
        (total_pension_gross - get_pension_income_deduction_amount(total_pension_gross))
        + other_comprehensive_income
    )
    comp_extra = max(0, total_tax - base_tax)

    # 분리과세
    sep_tax = payout_under_limit * SEPARATE_TAX_RATE

    if comp_extra < sep_tax:
        return {'chosen': comp_extra, 'comprehensive': comp_extra, 'separate': sep_tax, 'choice': "종합과세"}
    else:
        return {'chosen': sep_tax, 'comprehensive': comp_extra, 'separate': sep_tax, 'choice': "분리과세"}

def run_payout_simulation(inputs: UserInput, total_at_retirement, total_non_deductible_paid):
    r = inputs.post_retirement_return / 100
    non_taxable = total_non_deductible_paid
    taxable_wallet = total_at_retirement - non_taxable
    years = inputs.end_age - inputs.retirement_age
    rows = []

    for i in range(years):
        age = inputs.retirement_age + i
        rem = years - i
        balance = non_taxable + taxable_wallet

        # 연금 연초 인출액 계산
        if rem <= 0:
            payout = 0
        elif r == 0:
            payout = balance / rem
        else:
            factor = (1 - (1 + r) ** -rem) / r * (1 + r)
            payout = balance / factor if factor > 0 else 0
        payout = min(payout, balance)

        # 비과세 먼저 인출
        from_non = min(payout, non_taxable)
        from_tax = payout - from_non

        # 한도초과 과세 계산 (1~10년차)
        under = from_tax
        over_tax = 0
        year_count = i + 1
        if year_count <= 10:
            limit = balance * 1.2 / (11 - year_count)
            if from_tax > limit:
                over_tax = (from_tax - limit) * OTHER_INCOME_TAX_RATE
                under = limit

        # 연금소득세
        tax_info = calculate_annual_pension_tax(
            payout_under_limit=under,
            other_pension_income=inputs.other_pension_income,
            other_comprehensive_income=inputs.other_comprehensive_income,
            current_age=age
        )
        pen_tax = tax_info['chosen']
        total_tax = pen_tax + over_tax
        take_home = payout - total_tax

        # 잔액 업데이트
        non_taxable = (non_taxable - from_non) * (1 + r)
        taxable_wallet = (taxable_wallet - from_tax) * (1 + r)

        rows.append({
            "나이": age,
            "연간 수령액(세전)": payout,
            "연간 실수령액(세후)": take_home,
            "납부세금(총)": total_tax,
            "연금소득세": pen_tax,
            "한도초과 인출세금": over_tax,
            "연말 총 잔액": non_taxable + taxable_wallet,
            "과세대상 연금액": under,
            "종합과세액": tax_info['comprehensive'],
            "분리과세액": tax_info['separate'],
            "선택": tax_info['choice'],
        })
    return pd.DataFrame(rows)

def calculate_lump_sum_tax(taxable_lump_sum):
    return taxable_lump_sum * OTHER_INCOME_TAX_RATE if taxable_lump_sum > 0 else 0

# --- UI 표시 함수들 ---
def display_initial_summary(ui, total_at_ret, sim_df, total_credit):
    st.header("📈 예상 결과 요약")
    first_take = sim_df.iloc[0]["연간 실수령액(세후)"] if not sim_df.empty else 0
    c1, c2, c3 = st.columns(3)
    c1.metric(f"{ui.retirement_age}세 시점 적립금", f"{total_at_ret:,.0f} 원")
    c2.metric("첫 해 수령액(세후)", f"{first_take:,.0f} 원")
    c3.metric("총 세액공제", f"{total_credit:,.0f} 원")

def display_asset_visuals(total_at_ret, total_principal, growth_df, sim_df):
    st.header("📊 자산 성장 시각화")
    c1, c2 = st.columns([2,1])
    with c1:
        st.subheader("적립금 추이")
        pre = growth_df.rename(columns={'year':'나이','value':'예상 적립금'})
        post = pd.DataFrame()
        if not sim_df.empty:
            post = sim_df[['나이','연말 총 잔액']].rename(columns={'연말 총 잔액':'예상 적립금'})
        if not pre.empty:
            retire_row = pd.DataFrame([{'나이':pre['나이'].iloc[-1],'예상 적립금':total_at_ret}])
            full = pd.concat([pre, retire_row, post], ignore_index=True)
        else:
            full = pd.concat([pd.DataFrame([{'나이':sim_df['나이'].iloc[0],'예상 적립금':total_at_ret}]), post], ignore_index=True)
        st.line_chart(full.set_index('나이'))
    with c2:
        st.subheader("최종 적립금 구성")
        profit = total_at_ret - total_principal
        if profit < 0:
            st.warning(f"손실: {profit:,.0f}원")
            pie = pd.DataFrame({'금액':[total_principal],'항목':['원금']})
        else:
            pie = pd.DataFrame({'금액':[total_principal,profit],'항목':['원금','수익']})
        fig = px.pie(pie, values='금액', names='항목', hole=.3)
        fig.update_traces(textposition='inside', textinfo='percent+label')
        st.plotly_chart(fig, use_container_width=True)

def display_present_value_analysis(ui, sim_df, total_at_ret, non_deduct):
    st.header("🕒 현재가치 분석 및 일시금 비교")
    years = ui.end_age - ui.retirement_age
    inf = ui.inflation_rate / 100
    pv = sim_df.apply(lambda r: r['연간 실수령액(세후)'] / ((1 + inf) ** (r['나이'] - ui.start_age)), axis=1).sum() if not sim_df.empty else 0
    st.markdown(f"은퇴 후 {years}년간 연금 현재가치: **{pv:,.0f} 원**")
    taxable_lump = total_at_ret - non_deduct
    lump_tax = calculate_lump_sum_tax(taxable_lump)
    lump_take = total_at_ret - lump_tax
    st.metric("세후 일시금", f"{lump_take:,.0f} 원", help=f"기타소득세({OTHER_INCOME_TAX_RATE*100:.1f}%) 적용")

def display_tax_choice_summary(simulation_df):
    st.header("💡 연금소득세 비교 분석")
    choice_df = simulation_df[simulation_df['선택'].isin(['종합과세', '분리과세'])].copy()
    if choice_df.empty:
        st.info("모든 해에 1,500만원 이하 연금소득 ⇒ 저율 분리과세만 적용됩니다.")
        return

    example = choice_df.iloc[0]
    age = int(example['나이'])
    comp_tax = example['종합과세액']
    sep_tax  = example['분리과세액']

    c1, c2 = st.columns(2)
    with c1:
        st.markdown(f"**{age}세** 종합과세: **{comp_tax:,.0f}원**")
    with c2:
        st.markdown(f"**{age}세** 분리과세: **{sep_tax:,.0f}원**")

    total_comp = choice_df['종합과세액'].sum()
    total_sep  = choice_df['분리과세액'].sum()
    if total_comp < total_sep:
        msg = f"종합과세가 약 {(total_sep - total_comp):,.0f}원 더 유리합니다."
    elif total_sep < total_comp:
        msg = f"분리과세가 약 {(total_comp - total_sep):,.0f}원 더 유리합니다."
    else:
        msg = "두 방식의 총 세금이 동일합니다."
    st.markdown(f"> {msg}")

    with st.expander("연도별 상세 세금 비교 보기"):
        df = choice_df.copy()
        for col in ['과세대상 연금액','종합과세액','분리과세액']:
            df[col] = df[col].map(lambda x: f"{x:,.0f} 원")
        df['실수령(종합)'] = (choice_df['과세대상 연금액'] - choice_df['종합과세액']).map(lambda x: f"{x:,.0f} 원")
        df['실수령(분리)'] = (choice_df['과세대상 연금액'] - choice_df['분리과세액']).map(lambda x: f"{x:,.0f} 원")
        cols = ['나이','과세대상 연금액','종합과세액','실수령(종합)','분리과세액','실수령(분리)','선택']
        st.dataframe(df[cols], use_container_width=True, hide_index=True)

def display_simulation_details(sim_df):
    st.info("연금 수령 순서 및 세금 반영 상세")
    chart = sim_df.melt(id_vars='나이',
                        value_vars=['연간 실수령액(세후)','연금소득세','한도초과 인출세금'],
                        var_name='항목', value_name='금액')
    fig = px.bar(chart, x='나이', y='금액', color='항목')
    st.plotly_chart(fig, use_container_width=True)

    df = sim_df.copy()
    for c in ["연간 수령액(세전)","연간 실수령액(세후)","납부세금(총)","연금소득세","한도초과 인출세금"]:
        df[c] = df[c].map(lambda x: f"{x:,.0f} 원")
    cols = ["나이","연간 수령액(세전)","연간 실수령액(세후)","납부세금(총)","연금소득세","한도초과 인출세금"]
    st.dataframe(df[cols], use_container_width=True, hide_index=True)

# --- 메인 앱 로직 ---
st.set_page_config(layout="wide", page_title="연금저축 계산기")
st.title("연금저축 예상 수령액 계산기")

PROFILES = {'안정형': (4.0, 3.0), '중립형': (6.0, 4.0), '공격형': (8.0, 5.0), '직접 입력': (6.0, 4.0)}

def reset_calculation_state():
    st.session_state.calculated = False

def update_from_profile():
    profile_key = st.session_state.investment_profile
    if profile_key != '직접 입력':
        pre, post = PROFILES[profile_key]
        st.session_state.pre_retirement_return = pre
        st.session_state.post_retirement_return = post
    reset_calculation_state()

def auto_calculate_non_deductible():
    if st.session_state.auto_calc_non_deductible:
        ac = st.session_state.annual_contribution
        st.session_state.non_deductible_contribution = max(0, ac - PENSION_SAVING_TAX_CREDIT_LIMIT)
    else:
        st.session_state.non_deductible_contribution = 0
    reset_calculation_state()

def initialize_session():
    if 'initialized' in st.session_state:
        return
    st.session_state.update({
        'start_age': 30,
        'retirement_age': 60,
        'end_age': 90,
        'pre_retirement_return': PROFILES['중립형'][0],
        'post_retirement_return': PROFILES['중립형'][1],
        'inflation_rate': 3.5,
        'annual_contribution': 6_000_000,
        'non_deductible_contribution': 0,
        'other_non_deductible_total': 0,
        'other_pension_income': 0,
        'other_comprehensive_income': 0,
        'income_level': INCOME_LEVEL_LOW,
        'contribution_timing': '연말',
        'investment_profile': '중립형',
        'auto_calc_non_deductible': False,
        'calculated': False,
        'has_calculated_once': False,
        'initialized': True
    })

initialize_session()

# =========================================
# 1) 사이드바: 사용자 입력
# =========================================
st.sidebar.header("📝 정보 입력")
st.sidebar.markdown("모든 옵션을 이곳에서 설정 후 ▶ 결과 확인하기 클릭")
st.sidebar.markdown("---")

st.sidebar.number_input("납입 시작 나이", 15, 100, key='start_age', on_change=reset_calculation_state)
st.sidebar.number_input("은퇴 나이", MIN_RETIREMENT_AGE, 100, key='retirement_age', on_change=reset_calculation_state)
st.sidebar.number_input("수령 종료 나이", st.session_state.retirement_age + MIN_PAYOUT_YEARS, 120,
                        key='end_age', on_change=reset_calculation_state)
st.sidebar.markdown("---")

st.sidebar.subheader("📈 투자 성향 및 수익률")
st.sidebar.selectbox("투자 프로필", list(PROFILES.keys()), key='investment_profile', on_change=update_from_profile)
direct = (st.session_state.investment_profile == '직접 입력')
st.sidebar.number_input("은퇴 전 수익률(%)", -99.9, 99.9, key='pre_retirement_return', disabled=not direct, on_change=reset_calculation_state)
st.sidebar.number_input("은퇴 후 수익률(%)", -99.9, 99.9, key='post_retirement_return', disabled=not direct, on_change=reset_calculation_state)
st.sidebar.number_input("물가상승률(%)", -99.9, 99.9, key='inflation_rate', on_change=reset_calculation_state)
st.sidebar.markdown("---")

st.sidebar.subheader("💰 연간 납입액")
st.sidebar.radio("납입 시점", ['연말', '연초'], key='contribution_timing', on_change=reset_calculation_state)
st.sidebar.number_input("연간 총 납입액", 0, MAX_CONTRIBUTION_LIMIT, key='annual_contribution',
                       step=100000, on_change=auto_calculate_non_deductible)
st.sidebar.checkbox("세액공제 초과분 자동 비과세 처리", key="auto_calc_non_deductible", on_change=auto_calculate_non_deductible)
st.sidebar.number_input("└ 비과세 원금 (연간)", 0, MAX_CONTRIBUTION_LIMIT,
                       key='non_deductible_contribution', step=100000,
                       disabled=st.session_state.auto_calc_non_deductible,
                       on_change=reset_calculation_state)
st.sidebar.number_input("기타 비과세 원금 (총)", 0, key='other_non_deductible_total', step=100000, on_change=reset_calculation_state)
st.sidebar.markdown("---")

st.sidebar.subheader("🧾 세금 정보")
st.sidebar.selectbox("연 소득 구간", [INCOME_LEVEL_LOW, INCOME_LEVEL_HIGH],
                     key='income_level', on_change=reset_calculation_state)
st.sidebar.number_input("국민연금 등 기타 연금소득", 0, key='other_pension_income', step=500000, on_change=reset_calculation_state)
st.sidebar.number_input("임대⋅사업 등 기타 종합소득", 0, key='other_comprehensive_income', step=1000000, on_change=reset_calculation_state)
st.sidebar.markdown("---")
st.sidebar.button("결과 확인하기", type="primary")

# =========================================
# 2) 결과: 요약 지표
# =========================================
if st.session_state.get('calculated', False):
    ui = st.session_state.user_input_obj
    contribution_years = ui.retirement_age - ui.start_age
    total_principal = ui.annual_contribution * contribution_years
    non_deduct_total = ui.non_deductible_contribution * contribution_years + ui.other_non_deductible_total

    tax_rate = 0.165 if ui.income_level == INCOME_LEVEL_LOW else 0.132
    credit_base = ui.annual_contribution - ui.non_deductible_contribution
    credit_per_year = min(credit_base, PENSION_SAVING_TAX_CREDIT_LIMIT) * tax_rate
    total_credit = credit_per_year * contribution_years

    total_at_ret, growth_df = calculate_total_at_retirement(ui)
    if total_at_ret > 0:
        sim_df = run_payout_simulation(ui, total_at_ret, non_deduct_total)

        st.header("📈 예상 결과 요약")
        st.markdown("은퇴 후 첫 해와 총 적립금을 한눈에 확인하세요.")
        display_initial_summary(ui, total_at_ret, sim_df, total_credit)
        st.markdown("---")

        st.header("📊 자산 성장 시각화")
        st.markdown("은퇴 전후 자산 변화를 그래프로 보여줍니다.")
        display_asset_visuals(total_at_ret, total_principal, growth_df, sim_df)
        st.markdown("---")

        st.header("🕒 현재가치 분석 및 일시금 비교")
        st.markdown("물가상승률을 반영한 현재가치와 일시금(세후)을 비교합니다.")
        display_present_value_analysis(ui, sim_df, total_at_ret, non_deduct_total)
        st.markdown("---")

        display_tax_choice_summary(sim_df)
        st.markdown("---")

        with st.expander("연금 인출 상세 시뮬레이션 보기"):
            display_simulation_details(sim_df)

    else:
        st.warning("은퇴 시점 적립금이 0 이하입니다.")
else:
    if st.session_state.get('has_calculated_once'):
        st.info("입력값이 변경되었습니다. ▶ 결과 확인하기 버튼을 다시 눌러주세요.")
    else:
        st.info("사이드바에서 정보를 입력하고 ▶ 결과 확인하기 버튼을 눌러주세요.")

with st.expander("⚠️ 주의사항 및 가정"):
    st.caption("""
    1. 연금저축 계좌만 계산 대상입니다.
    2. 납입은 연초/연말, 수령은 매년 초로 가정합니다.
    3. 모든 세금에 지방소득세(10%) 포함.
    4. 물가·수익률은 고정 가정.
    5. 1~10년차 연금 한도 초과 시 기타소득세(16.5%) 적용.
    6. 일시금 수령 시 기타소득세(16.5%) 적용.
    7. 세법 개정 시 과세표준 구간만 업데이트하세요.
    """)

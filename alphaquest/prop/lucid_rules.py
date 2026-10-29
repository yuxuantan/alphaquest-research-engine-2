"""Dated LucidFlex contract. Provider pages are evidence, never runtime inputs."""
MODEL_VERSION='alphaquest-lucidflex50k-eod-v1'
SOURCES={
    'customization':'https://support.lucidtrading.com/en/articles/16226050-lucidflex-customization',
    'evaluation':'https://support.lucidtrading.com/en/articles/12945790-lucidflex-evaluation-account',
    'consistency':'https://support.lucidtrading.com/en/articles/12945805-lucidflex-consistency-percentage',
    'drawdown':'https://support.lucidtrading.com/en/articles/12945815-lucidflex-drawdown',
    'funded':'https://support.lucidtrading.com/en/articles/12945795-lucidflex-funded-account',
    'scaling':'https://support.lucidtrading.com/en/articles/12945808-lucidflex-scaling-plan',
    'payouts':'https://support.lucidtrading.com/en/articles/12945796-lucidflex-payouts',
    'inactivity':'https://support.lucidtrading.com/en/articles/11404632-inactivity-policy',
    'commissions':'https://support.lucidtrading.com/en/articles/11508978-approved-products-and-commissions',
    'plan_cards':'https://lucidtrading.com/',
    'live_boundary':'https://support.lucidtrading.com/en/articles/16558826-new-live-structure',
    'trading_times':'https://support.lucidtrading.com/en/articles/11404729-allowed-trading-times',
    'account_limits':'https://support.lucidtrading.com/en/articles/11404617-maximum-number-of-accounts',
}
CONTRACT=dict(checked_on='2026-10-29',sources=SOURCES,
    price_origin='User-supplied current evaluation purchase price: USD 80.50; editable, not a guaranteed checkout quote.',
    evaluation=dict(target=3000,drawdown=2000,consistency=.4,deadline=None,activation_fee=0,extra_activation_weekdays=0),
    funded=dict(drawdown=2000,lock_profit=100,winning_days=5,daily_profit=150,
        withdrawal_fraction=.5,minimum_gross_request=500,maximum_gross_request=2000,
        trader_share=.9,maximum_simulated_payouts=5,scaling=[[0,20],[1000,30],[2000,40]]),
    scope='Simulated evaluation and sim-funded stage only. Risk-team early live transitions and live trading returns are not modeled.',
    timing='DLL-on requests occur at the first eligible observed completed-trade mark within 18:00–15:45 America/New_York and stop that session. If no intraday request was made, eligibility is checked at session close; DLL-off always uses session close. No favorable unobserved intratrade request is invented. Gross withdrawals reduce equity; trader payouts are 90%. Reports date payouts at request/deduction, not bank settlement; the provider disbursement delay is not simulated.',
    inactivity='Activity is an observed closed result of at least USD 1 in absolute value, within 30 calendar days. Bootstrap clocks start Monday; historical replay uses actual elapsed calendar days.',
    horizon='No provider evaluation deadline. Monte Carlo paths still open at 2,000 weekdays are censored, not failed evaluations. Censored funding chains have unavailable acquisition timing; no fallback delay is invented.',
    renewal='Annual-per-slot and historical replacement are research renewal assumptions, not a simulation of live accounts after the fifth payout.',
    documentation_conflict='The newer customization and consistency pages specify 40% standard; the older evaluation overview still lists 50%. This version supports the 40% standard, not the 50% add-on/cushion.')
CONTRACT['daily_loss_assumption']='DLL-on uses a fixed USD 1,200 soft daily stop in both phases. The customization page confirms the soft breach and phase coverage but does not specify an above-trail adjustment. Holding this amount fixed above the trail is an explicit modeling assumption, not verified provider parity. DLL-off has no daily stop.'
CONTRACT['source_hours']='Sources must already close positions by the regular 16:45 America/New_York cutoff and enter only during the 18:00–16:45 Sunday-evening through Friday session windows. Late exits reject as incompatible because their earlier liquidation price is unavailable; they are not counted as provider account breaches. Eastern civil time includes DST. Holiday early closes are not independently validated by this adapter and require correctly session-filtered source data.'

def defaults(apex):
    return dict(apex,PROP_FIRM='Lucid',ACCOUNT_TYPE='LucidFlex',EVAL_PRICE='80.5',ACTIVATION_FEE='0',SLOTS='5',
        COMMISSION_BROKER='Lucid',DAILY_LOSS_LIMIT='on')

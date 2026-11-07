"""Observable entry-time regimes with thresholds fitted only on inner training.

Names describe observable conditions, not ex-post profitable regimes. Replays
start validation features cold: neither training bars nor purge/embargo bars
warm their state. A trade uses completed bars strictly before its entry label,
including for same-close fills. True range is measured in instrument points so
zero/negative prices never create unstable percentage denominators.
"""
from collections import Counter, deque
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
import re
from typing import Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_validator, model_validator

from .backtest_data import read_selected_bars
from .research_folds import SESSION_CONVENTION, SessionDateRange
from .session_calendar import NQ_SYMBOL_PATTERN, session_date


RegimeName = Literal[
    'trend', 'range', 'high_volatility', 'low_volatility',
    'high_liquidity', 'low_liquidity', 'asia_session', 'europe_session', 'us_session',
]
GROUPS = {
    'trend': 'direction', 'range': 'direction',
    'high_volatility': 'volatility', 'low_volatility': 'volatility',
    'high_liquidity': 'liquidity', 'low_liquidity': 'liquidity',
    'asia_session': 'session', 'europe_session': 'session', 'us_session': 'session',
}
MAX_FIT_SAMPLES = 2_000_000


def _decimal(value):
    if isinstance(value, bool) or not isinstance(value, (str, int, float, Decimal)):
        raise ValueError('Supply a finite decimal number, never a boolean.')
    try:
        result = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError('Supply a finite decimal number.') from exc
    if not result.is_finite():
        raise ValueError('Supply a finite decimal number.')
    return result


class RegimeSettings(BaseModel):
    """Predeclared labels; only separately required labels gate qualification."""
    model_config = ConfigDict(extra='forbid', frozen=True)

    enabled_names: tuple[RegimeName, ...] = ()
    lookback_bars: StrictInt = Field(default=20, ge=2, le=10000)
    minimum_training_features: StrictInt = Field(default=20, ge=2, le=MAX_FIT_SAMPLES)
    trend_efficiency_threshold: Decimal = Field(default=Decimal('.6'), gt=0, lt=1)
    volatility_quantile: Decimal = Field(default=Decimal('.5'), gt=0, lt=1)
    liquidity_quantile: Decimal = Field(default=Decimal('.5'), gt=0, lt=1)
    timezone: Literal['America/Chicago'] = 'America/Chicago'
    asia_start_hour: StrictInt = Field(default=17, ge=0, le=23)
    europe_start_hour: StrictInt = Field(default=2, ge=0, le=23)
    us_start_hour: StrictInt = Field(default=8, ge=0, le=23)

    @field_validator('trend_efficiency_threshold', 'volatility_quantile', 'liquidity_quantile', mode='before')
    @classmethod
    def finite_threshold(cls, value):
        return _decimal(value)

    @model_validator(mode='after')
    def coherent(self):
        if len(set(self.enabled_names)) != len(self.enabled_names):
            raise ValueError('Enabled regime names must be unique.')
        if not self.europe_start_hour < self.us_start_hour < self.asia_start_hour:
            raise ValueError('Chicago session starts require Europe < US < Asia; Asia wraps midnight.')
        return self


def _window(value):
    if not isinstance(value, dict) or set(value) != {'first_session', 'last_session', 'sessions'}:
        raise ValueError('Each window requires first_session, last_session and the exact sessions list.')
    sessions = value['sessions']
    if type(sessions) is not list or not sessions:
        raise ValueError('Window sessions must be a nonempty chronological list.')
    for day in sessions:
        if type(day) is not str or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', day):
            raise ValueError('Window dates must use YYYY-MM-DD.')
        date.fromisoformat(day)
    if sessions != sorted(set(sessions)) or (sessions[0], sessions[-1]) != (value['first_session'], value['last_session']):
        raise ValueError('Window bounds must match unique chronological sessions.')
    return SessionDateRange.parse(sessions[0], sessions[-1])


def _stamp(value):
    if not isinstance(value, str):
        raise ValueError('Trade timestamps must be explicit timezone-aware ISO strings.')
    try:
        stamp = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError as exc:
        raise ValueError('Trade timestamps must be explicit timezone-aware ISO strings.') from exc
    if stamp.utcoffset() is None:
        raise ValueError('Trade timestamps must be timezone-aware.')
    return stamp.astimezone(timezone.utc)


def _iso(stamp):
    return stamp.isoformat().replace('+00:00', 'Z') if stamp is not None else None


def _trades(rows, sessions):
    if not isinstance(rows, list):
        raise ValueError('Trades must be a chronological list.')
    result, ids, previous = [], set(), None
    for row in rows:
        if not isinstance(row, dict) or any(key not in row for key in ('trade_id', 'entry_time_utc', 'exit_time_utc', 'net_pnl')):
            raise ValueError('Each trade requires trade_id, entry_time_utc, exit_time_utc and net_pnl.')
        id = row['trade_id']
        if type(id) not in (str, int) or not str(id).strip() or str(id) in ids:
            raise ValueError('Trade IDs must be unique nonempty strings or integers.')
        ids.add(str(id))
        entry, exit = _stamp(row['entry_time_utc']), _stamp(row['exit_time_utc'])
        if exit < entry or previous is not None and entry < previous:
            raise ValueError('Trades must have entry <= exit and chronological entry order; input is never sorted.')
        previous = entry
        entry_day, exit_day = session_date(entry).isoformat(), session_date(exit).isoformat()
        if entry_day not in sessions or exit_day not in sessions:
            raise ValueError('Trade entry and exit must both lie within the declared validation sessions.')
        result.append(dict(id=str(id), entry=entry, exit=exit, exit_session=exit_day, net=_decimal(row['net_pnl'])))
    return result


class _Features:
    def __init__(self, lookback):
        self.lookback = lookback
        self.bars = deque(maxlen=lookback + 1)
        self.moves = deque()
        self.totals = [Decimal(0), Decimal(0), Decimal(0)]

    def advance(self, bar):
        if self.bars and bar.timestamp_utc <= self.bars[-1].timestamp_utc:
            raise ValueError('Feature bars must be strictly chronological.')
        if self.bars:
            previous = self.bars[-1]
            item = (abs(bar.close-previous.close),
                    max(bar.high-bar.low, abs(bar.high-previous.close), abs(bar.low-previous.close)),
                    bar.volume)
            if len(self.moves) == self.lookback:
                old = self.moves.popleft()
                self.totals = [total-value for total, value in zip(self.totals, old)]
            self.moves.append(item)
            self.totals = [total+value for total, value in zip(self.totals, item)]
        self.bars.append(bar)

    def current(self):
        if len(self.bars) < self.lookback + 1:
            return None
        travel, ranges, volume = self.totals
        return dict(
            directional_efficiency=abs(self.bars[-1].close-self.bars[0].close)/travel if travel else Decimal(0),
            mean_true_range_points=ranges/self.lookback,
            mean_volume=volume/self.lookback,
        )


def _quantile(values, quantile):
    """Linear interpolation between ordered training observations, in Decimal."""
    values = sorted(values)
    index = Decimal(len(values)-1) * quantile
    left = int(index)
    fraction = index-left
    return values[left] if left == len(values)-1 else values[left] + fraction*(values[left+1]-values[left])


def _validate_bar_window(bar, sessions, observed):
    day = session_date(bar.timestamp_utc).isoformat()
    if day not in sessions:
        raise ValueError('Window omitted an observed session between its bounds.')
    observed.add(day)


def _session_label(stamp, settings):
    hour = stamp.astimezone(ZoneInfo(settings.timezone)).hour
    if hour >= settings.asia_start_hour or hour < settings.europe_start_hour:
        return 'asia_session'
    return 'europe_session' if hour < settings.us_start_hour else 'us_session'


def build_regime_evidence(datasets, dataset_id, train_window, validation_window, trades, settings):
    """Fit on training, then classify validation entries using only their past.

    Realized net P&L is attributed to exit sessions *after* classification and is
    never an input to features or thresholds. Overlapping labels are intentional
    comparisons, not additive portfolio totals. Availability records distinguish
    excluded target conditions from genuinely unobservable classifications.
    """
    settings = settings if isinstance(settings, RegimeSettings) else RegimeSettings.model_validate(settings)
    train_dates, validation_dates = _window(train_window), _window(validation_window)
    if train_window['last_session'] >= validation_window['first_session']:
        raise ValueError('Training must finish before validation; windows cannot overlap.')
    dataset = datasets.get(dataset_id)
    if dataset is None:
        raise ValueError('Dataset not found.')
    symbol = str(dataset.get('symbol') or '').strip().upper()
    if not re.fullmatch(NQ_SYMBOL_PATTERN, symbol.replace('MNQ', 'NQ', 1)):
        raise ValueError('CME regime labels currently support explicit NQ/MNQ symbols only.')
    train_sessions, validation_sessions = set(train_window['sessions']), set(validation_window['sessions'])
    trades = _trades(trades, validation_sessions)
    groups = sorted({GROUPS[name] for name in settings.enabled_names})
    series = {'volatility': [], 'liquidity': []}
    train_features = _Features(settings.lookback_bars)
    training_observed, training_bars, feature_samples, cutoff = set(), 0, 0, None
    with read_selected_bars(datasets, dataset_id, train_dates) as selected:
        for bar in selected.bars:
            _validate_bar_window(bar, train_sessions, training_observed)
            train_features.advance(bar)
            training_bars += 1; cutoff = bar.timestamp_utc
            feature = train_features.current()
            if feature is not None:
                feature_samples += 1
                if feature_samples > MAX_FIT_SAMPLES:
                    raise ValueError('Training exceeds 2,000,000 regime feature observations; narrow the declared training window.')
                if 'volatility' in groups: series['volatility'].append(feature['mean_true_range_points'])
                if 'liquidity' in groups: series['liquidity'].append(feature['mean_volume'])
    if training_observed != train_sessions:
        raise ValueError('Training inventory contains sessions without source bars.')
    enough = feature_samples >= settings.minimum_training_features
    thresholds = dict(trend_efficiency=str(settings.trend_efficiency_threshold),
        volatility_points=str(_quantile(series['volatility'], settings.volatility_quantile)) if enough and series['volatility'] else None,
        liquidity_volume=str(_quantile(series['liquidity'], settings.liquidity_quantile)) if enough and series['liquidity'] else None)
    fitted = {group: group not in ('volatility', 'liquidity') or enough for group in groups}
    fit = dict(cutoff=_iso(cutoff), information_cutoff_session=train_window['last_session'],
        thresholds=thresholds, samples=feature_samples, training_bars=training_bars,
        minimum_training_features=settings.minimum_training_features,
        status='complete' if all(fitted.values()) else 'insufficient_training_features',
        groups={group:dict(complete=complete, reason=None if complete else 'insufficient_training_features') for group, complete in fitted.items()},
        method='Training-only linearly interpolated empirical quantiles; fixed declared directional threshold.',
        feature_units=dict(directional_efficiency='unitless 0–1', mean_true_range_points='instrument price points', mean_volume='source volume units'),
        convention=SESSION_CONVENTION, settings=settings.model_dump(mode='json'),
        validation_warmup='Cold start; lookback_bars+1 prior validation bars. Training and purge/embargo bars are excluded.',
        source=dict(dataset_id=dataset_id, sha256=dataset['sha256'], symbol=symbol, source_timezone=dataset['source_timezone']),
        session_buckets=dict(timezone=settings.timezone,
            asia=dict(start_hour=settings.asia_start_hour, end_hour=settings.europe_start_hour, wraps_midnight=True),
            europe=dict(start_hour=settings.europe_start_hour, end_hour=settings.us_start_hour, wraps_midnight=False),
            us=dict(start_hour=settings.us_start_hour, end_hour=settings.asia_start_hour, wraps_midnight=False)),
        limitations=['Quantiles describe this training history; they are not future regime forecasts.',
                    'Labels may overlap; their P&L totals must not be added together.',
                    'Whole-bar timestamp labels are used conservatively; genuine tick-time decision equivalence remains unverified.'])
    sums = {name: {day:dict(session=day, net_pnl=Decimal(0), trade_count=0)
                  for day in validation_window['sessions']} for name in settings.enabled_names}
    observable = Counter(); reasons = Counter(); assignments = []
    validation_features = _Features(settings.lookback_bars)
    validation_observed, validation_bars = set(), 0
    with read_selected_bars(datasets, dataset_id, validation_dates) as selected:
        first_bar, last_bar = _stamp(selected.metadata['start_utc']), _stamp(selected.metadata['end_utc'])
        if any(trade['entry'] < first_bar or trade['exit'] > last_bar for trade in trades):
            raise ValueError('Trade entry and exit must lie within the observed validation timestamp bounds.')
        bars = iter(selected.bars)
        pending = next(bars, None)
        for trade in trades:
            while pending is not None and pending.timestamp_utc < trade['entry']:
                _validate_bar_window(pending, validation_sessions, validation_observed)
                validation_features.advance(pending); validation_bars += 1
                pending = next(bars, None)
            feature = validation_features.current()
            labels, missing, available = [], [], []
            for group in groups:
                if not fitted[group]:
                    missing.append(group+':insufficient_training_features')
                elif group != 'session' and feature is None:
                    missing.append(group+':insufficient_prior_validation_bars')
                else:
                    available.append(group); observable[group] += 1
            if 'session' in available: labels.append(_session_label(trade['entry'], settings))
            if 'direction' in available:
                labels.append('trend' if feature['directional_efficiency'] >= settings.trend_efficiency_threshold else 'range')
            if 'volatility' in available:
                labels.append('high_volatility' if feature['mean_true_range_points'] >= Decimal(thresholds['volatility_points']) else 'low_volatility')
            if 'liquidity' in available:
                labels.append('high_liquidity' if feature['mean_volume'] >= Decimal(thresholds['liquidity_volume']) else 'low_liquidity')
            labels = sorted(set(labels).intersection(settings.enabled_names))
            for name in labels:
                sums[name][trade['exit_session']]['net_pnl'] += trade['net']
                sums[name][trade['exit_session']]['trade_count'] += 1
            reasons.update(missing)
            asof = validation_features.bars[-1].timestamp_utc if validation_features.bars else None
            assignments.append(dict(trade_id=trade['id'], entry_time=_iso(trade['entry']),
                feature_asof=_iso(asof), labels=labels,
                features={key:str(value) for key, value in feature.items()} if feature else None,
                available_groups=available, unclassified_reasons=missing))
        # Complete source/window verification without changing saved assignments.
        while pending is not None:
            _validate_bar_window(pending, validation_sessions, validation_observed)
            validation_bars += 1
            pending = next(bars, None)
    if validation_observed != validation_sessions:
        raise ValueError('Validation inventory contains sessions without source bars.')
    availability = {name:dict(group=GROUPS[name], thresholds_available=fitted[GROUPS[name]],
        observable_trades=observable[GROUPS[name]], total_trades=len(trades),
        complete=fitted[GROUPS[name]] and observable[GROUPS[name]] == len(trades)) for name in settings.enabled_names}
    return dict(regimes=[dict(name=name, observable_at_decision=True,
        classification_complete=availability[name]['complete'],
        unclassified_trades=len(trades)-availability[name]['observable_trades'],
        sessions=[dict(row, net_pnl=str(row['net_pnl'])) for row in sums[name].values()]) for name in settings.enabled_names],
        fit=fit, assignments=assignments, availability=availability, validation_bars=validation_bars,
        unclassified=dict(trade_count=sum(bool(a['unclassified_reasons']) for a in assignments),
            fully_unclassified_trade_count=sum(not a['available_groups'] for a in assignments),
            outside_enabled_regimes_trade_count=sum(not a['labels'] and not a['unclassified_reasons'] for a in assignments),
            reasons=dict(sorted(reasons.items()))))

"""Causal observed-block draws through the ordinary native execution engine.

This module owns no sizing, account transitions or economic selection. Source
bars keep their prices and timestamps. Only the phase owner's clock view is
mapped to explicitly modeled dates. Every block starts a fresh strategy warmed
with its permitted original prefix; the original-capital cash continuation and
provider owner persist across blocks.
"""
from dataclasses import asdict, dataclass, replace
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from hashlib import sha256
import json

import numpy as np

from ..execution import EquityPoint, ExecutionContinuation, execute, _validate_bar
from ..session_calendar import CT, session_date
from ..strategies.vwap_pullback_risk_sizing import Parameters, VwapPullbackRiskSizing
from .adapter import canonical
from .native_control import SessionContext, json_native


VERSION = 'observed_contiguous_blocks_with_prior_prefix_v1'


def _json(value):
    return canonical(json_native(value))


def _hash(value):
    return sha256(_json(value).encode()).hexdigest()


def _integer(value, name, minimum=0, maximum=2**32-1):
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError(f'{name} must be an integer from {minimum} through {maximum}.')


def _parameters(parameters):
    if type(parameters) is not Parameters or not parameters.use_eod_flat or parameters.use_vol_sizing:
        raise ValueError('Native block draws require VWAP EOD-flat with local volume sizing disabled.')
    return _json(asdict(parameters))


def _shape(context, parameters, *, kind):
    if type(context) is not SessionContext or context.kind != kind:
        raise ValueError(f'Native draw calendar requires explicitly {kind} contexts.')
    close = context.scheduled_close_utc.astimezone(CT)
    day = context.session
    if close.date() != day or session_date(context.scheduled_close_utc) != day:
        raise ValueError('Native draw close must be on its declared CME session date.')
    begin = datetime.combine(day-timedelta(days=1), time(17, 1), CT).astimezone(timezone.utc)
    duration = context.scheduled_close_utc-begin
    seconds = duration.total_seconds()
    if seconds < 0 or seconds % 60:
        raise ValueError('Native draw session must have whole complete minute bars.')
    count = int(seconds/60)+1
    declared = context.observed_bar_count if kind == 'observed' else context.expected_bar_count
    if declared != count:
        raise ValueError('Native draw session count differs from its complete calendar shape.')
    configured = datetime.combine(day, time(parameters.eod_flat_time//100,
                                            parameters.eod_flat_time % 100), CT)
    cutoff = min(configured, close-timedelta(minutes=parameters.close_buffer_minutes))
    return (close.strftime('%H:%M:%S'), cutoff.strftime('%H:%M:%S'), count)


@dataclass(frozen=True, slots=True)
class SourceSession:
    context: SessionContext
    first_bar: int
    end_bar: int
    shape: tuple
    content_sha256: str
    prefix_sha256: str


@dataclass(frozen=True, slots=True)
class SourceBlock:
    index: int
    first_session: int
    end_session: int
    content_sha256: str
    prefix_sha256: str


@dataclass(frozen=True, slots=True)
class SourceCatalogue:
    bars: tuple
    sessions: tuple[SourceSession, ...]
    blocks: tuple[SourceBlock, ...]
    block_sessions: int
    parameters_json: str
    source_identity_json: str
    content_sha256: str
    catalogue_sha256: str

    def metadata(self):
        """Small saved identity; bars and repeated prefixes are never copied."""
        return dict(version=VERSION, block_sessions=self.block_sessions,
            source_identity=json.loads(self.source_identity_json),
            parameters=json.loads(self.parameters_json), content_sha256=self.content_sha256,
            sessions=[json_native(asdict(s)) for s in self.sessions],
            blocks=[asdict(b) for b in self.blocks], catalogue_sha256=self.catalogue_sha256,
            source_bars=len(self.bars), source_sessions=len(self.sessions),
            source_row_number_convention='one_based_admitted_selection_ordinal',
            prefix_law='all permitted original source bars strictly before block; entries disabled',
            strategy_reset='once per sampled contiguous source block', price_rebasing=False)


def _catalogue_identity(catalogue):
    value = catalogue.metadata()
    value.pop('catalogue_sha256')
    return _hash(value)


def build_catalogue(bars, source_contexts, parameters, *, block_sessions, source_identity,
                    checkpoint=lambda: None):
    """Index every complete contiguous observed block, independent of outcomes.

    Contexts must already cover every scheduled open source session in the
    admitted IS window. The caller owns reviewed closure admission. This layer
    independently verifies all actual minute rows and immutable content hashes.
    Prefix identities are computed incrementally in O(number of source bars).
    """
    if type(block_sessions) is not int or block_sessions not in (1, 5, 10):
        raise ValueError('Native block_sessions must be 1, 5 or 10.')
    parameter_json = _parameters(parameters)
    if type(source_identity) is not dict or not source_identity:
        raise ValueError('Native block catalogue requires the complete checked source identity.')
    identity_json = _json(source_identity)
    values = tuple(bars)
    if not values or type(source_contexts) is not dict or not source_contexts:
        raise ValueError('Native block catalogue requires observed bars and session contexts.')
    contexts = tuple(source_contexts[key] for key in sorted(source_contexts))
    if any(type(key) is not date or context.session != key for key, context in source_contexts.items()):
        raise ValueError('Source contexts must be keyed by their actual session date.')
    if len(contexts) < block_sessions:
        raise ValueError('Insufficient observed sessions for one complete source block.')
    groups = []
    cursor = 0
    running = sha256()
    previous = None
    for context in contexts:
        shape = _shape(context, parameters, kind='observed')
        start = cursor
        prefix = running.hexdigest()
        content = sha256()
        beginning = datetime.combine(context.session-timedelta(days=1), time(17, 1), CT).astimezone(timezone.utc)
        for offset in range(shape[2]):
            if cursor >= len(values):
                raise ValueError('Incomplete source session rows; no bars are invented.')
            bar = values[cursor]
            _validate_bar(bar, previous)
            if (session_date(bar.timestamp_utc) != context.session
                    or bar.timestamp_utc != beginning+timedelta(minutes=offset)):
                raise ValueError('Source bars differ from complete ordered observed session contexts.')
            encoded = (_json(asdict(bar))+'\n').encode()
            content.update(encoded); running.update(encoded)
            previous = bar; cursor += 1
            if cursor % 1000 == 0:
                checkpoint()
        groups.append(SourceSession(context, start, cursor, shape, content.hexdigest(), prefix))
    if cursor != len(values):
        raise ValueError('Source contains bars outside the permitted observed inventory.')
    groups = tuple(groups)
    blocks = tuple(SourceBlock(index, index, index+block_sessions,
        _hash([s.content_sha256 for s in groups[index:index+block_sessions]]), groups[index].prefix_sha256)
        for index in range(len(groups)-block_sessions+1))
    result = SourceCatalogue(values, groups, blocks, block_sessions, parameter_json,
                             identity_json, running.hexdigest(), '')
    return replace(result, catalogue_sha256=_catalogue_identity(result))


def verify_catalogue(catalogue, *, checkpoint=lambda: None):
    """Rehash actual bars/prefixes; retained hash fields are not proof of bytes."""
    if type(catalogue) is not SourceCatalogue:
        raise ValueError('Native execution requires a checked source catalogue.')
    fresh = build_catalogue(catalogue.bars,
        {s.context.session:s.context for s in catalogue.sessions},
        Parameters(**{key:Decimal(value) if isinstance(getattr(Parameters(), key), Decimal) else value
                      for key, value in json.loads(catalogue.parameters_json).items()}),
        block_sessions=catalogue.block_sessions, source_identity=json.loads(catalogue.source_identity_json),
        checkpoint=checkpoint)
    if fresh.metadata() != catalogue.metadata():
        raise ValueError('Native source catalogue content/prefix identity changed.')
    return fresh


def _target(contexts, parameters):
    if type(contexts) is not dict or not contexts:
        raise ValueError('Supply a nonempty explicit modeled target session calendar.')
    days = sorted(contexts)
    if any(type(day) is not date or contexts[day].session != day for day in days):
        raise ValueError('Modeled contexts must be keyed by their declared target dates.')
    return [(day, _shape(contexts[day], parameters, kind='modeled')) for day in days]


def _block_shape(sessions):
    first = sessions[0][0]
    return [[(day-first).days, *shape] for day, shape in sessions]


def build_schedule(catalogue, target_contexts, parameters, *, phase, seed, path_index, start_date,
                   cutoff_date_exclusive=None):
    """Address each block draw by phase/path/slot, independent of outcomes.

    Source blocks never wrap. A short final draw uses the declared leading
    prefix of an otherwise complete source block. All matching blocks enter
    its equal-probability pool; no redraw on execution failure is supported.
    """
    if type(catalogue) is not SourceCatalogue or catalogue.catalogue_sha256 != _catalogue_identity(catalogue):
        raise ValueError('Source catalogue identity changed before scheduling.')
    if _parameters(parameters) != catalogue.parameters_json:
        raise ValueError('Strategy parameters changed before native scheduling.')
    if phase not in ('evaluation', 'funded'):
        raise ValueError('Native forecast requires an explicit independent phase.')
    _integer(seed, 'seed'); _integer(path_index, 'path_index')
    target = _target(target_contexts, parameters)
    if type(start_date) is str:
        start_date = date.fromisoformat(start_date)
    if type(start_date) is not date or start_date > target[0][0]:
        raise ValueError('Modeled start date must precede or equal its first open session.')
    if start_date <= catalogue.sessions[-1].context.session:
        raise ValueError('Modeled forecast starts must follow the admitted source IS history.')
    if cutoff_date_exclusive is None:
        cutoff_date_exclusive = target[-1][0]+timedelta(days=1)
    elif type(cutoff_date_exclusive) is str:
        cutoff_date_exclusive = date.fromisoformat(cutoff_date_exclusive)
    if type(cutoff_date_exclusive) is not date or cutoff_date_exclusive <= target[-1][0]:
        raise ValueError('Modeled cutoff must be exclusive and follow every target session.')
    draws, pools = [], {}
    for slot, offset in enumerate(range(0, len(target), catalogue.block_sessions)):
        take = min(catalogue.block_sessions, len(target)-offset)
        shape = _block_shape(target[offset:offset+take])
        pool_id = _hash(dict(shape=shape, used_sessions=take))
        if pool_id not in pools:
            pool = []
            for block in catalogue.blocks:
                selected = catalogue.sessions[block.first_session:block.first_session+take]
                if _block_shape([(s.context.session, s.shape) for s in selected]) == shape:
                    pool.append(block.index)
            pools[pool_id] = dict(pool_id=pool_id, pool_sha256=_hash(pool), indices=pool,
                                  shape=shape, used_sessions=take)
        pool = pools[pool_id]['indices']
        if not pool:
            raise ValueError(f'No complete source block matches modeled target shape at slot {slot}; missing early-close or civil-gap evidence cannot be redrawn.')
        generator = np.random.default_rng(np.random.SeedSequence(
            [seed, 0 if phase == 'evaluation' else 1, path_index, slot]))
        block = catalogue.blocks[pool[int(generator.integers(len(pool)))]]
        selected = catalogue.sessions[block.first_session:block.first_session+take]
        draws.append(dict(slot=slot, source_block_index=block.index,
            source_sessions=[str(s.context.session) for s in selected],
            target_sessions=[str(day) for day, _ in target[offset:offset+take]],
            used_sessions=take, full_block_sessions=catalogue.block_sessions,
            leading_prefix_tail=take<catalogue.block_sessions,
            source_block_sha256=block.content_sha256, prefix_sha256=block.prefix_sha256,
            pool_id=pool_id, pool_count=len(pool), shape=shape,
            warmup_bars=selected[0].first_bar,
            executed_bars=selected[-1].end_bar-selected[0].first_bar))
    result = dict(version=VERSION, phase=phase, seed=seed, path_index=path_index,
        start_date=str(start_date), cutoff_date_exclusive=str(cutoff_date_exclusive),
        catalogue_sha256=catalogue.catalogue_sha256,
        target_contexts=[json_native(asdict(target_contexts[day])) for day, _ in target],
        pools=list(pools.values()), draws=draws, estimated_warmup_bars=sum(d['warmup_bars'] for d in draws),
        estimated_executed_bars=sum(d['executed_bars'] for d in draws))
    result['schedule_sha256'] = _hash(result)
    return result


def modeled_stamp(stamp, source_session, target_session):
    """Map a callback view, preserving local clock and overnight date offset."""
    if stamp is None:
        return None
    if stamp.tzinfo is None or stamp.utcoffset() != timedelta(0):
        raise ValueError('Source clock mapping requires an aware UTC timestamp.')
    local = stamp.astimezone(CT)
    day = target_session+(local.date()-source_session)
    naive = datetime.combine(day, local.timetz().replace(tzinfo=None))
    possible = set()
    for fold in (0, 1):
        utc = naive.replace(tzinfo=CT, fold=fold).astimezone(timezone.utc)
        if utc.astimezone(CT).replace(tzinfo=None) == naive:
            possible.add(utc)
    if len(possible) != 1:
        raise ValueError('Ambiguous/nonexistent modeled local time is unsupported.')
    return next(iter(possible))


class _ClockView:
    def __init__(self, owner, source_contexts, target_contexts, mapping):
        self.owner = owner
        self.source = source_contexts
        self.target = target_contexts
        self.mapping = mapping
        self.acceptances = {}

    def stamp(self, value):
        if value is None:
            return None
        source = session_date(value)
        if source not in self.mapping:
            raise ValueError('Callback timestamp lies outside the active source block.')
        return modeled_stamp(value, source, self.mapping[source])

    def snapshot(self, value):
        position = replace(value.position, entry_time_utc=self.stamp(value.position.entry_time_utc)) if value.position else None
        return replace(value, timestamp_utc=self.stamp(value.timestamp_utc), position=position)

    def session_context(self, stamp):
        day = session_date(stamp)
        if day not in self.source:
            raise ValueError('Execution received foreign source bars.')
        return self.source[day]

    def begin_session(self, context, snapshot):
        self.owner.begin_session(self.target[self.mapping[context.session]], self.snapshot(snapshot))

    def risk_orders(self, snapshot):
        return replace(self.owner.risk_orders(self.snapshot(snapshot)), session=session_date(snapshot.timestamp_utc))

    def admit_entry(self, proposal, snapshot):
        view = replace(proposal, decision_time_utc=self.stamp(proposal.decision_time_utc),
            initial_stop_known_at_utc=self.stamp(proposal.initial_stop_known_at_utc),
            exit_deadline_utc=self.stamp(proposal.exit_deadline_utc))
        acceptance = self.owner.admit_entry(view, self.snapshot(snapshot))
        self.acceptances[acceptance.opportunity_id] = acceptance
        intent = replace(acceptance.accepted_intent, exit_deadline_utc=proposal.exit_deadline_utc) if acceptance.accepted_intent else None
        return replace(acceptance, accepted_intent=intent)

    def after_entry_fill(self, snapshot, acceptance):
        self.owner.after_entry_fill(self.snapshot(snapshot), self.acceptances[acceptance.opportunity_id])

    def cancel_entry(self, acceptance, snapshot, reason):
        self.owner.cancel_entry(self.acceptances[acceptance.opportunity_id], self.snapshot(snapshot), reason)

    def after_trade_close(self, trade, snapshot, *, triggering_floor):
        view = replace(trade, entry_time_utc=self.stamp(trade.entry_time_utc),
            exit_time_utc=self.stamp(trade.exit_time_utc), exit_deadline_utc=self.stamp(trade.exit_deadline_utc))
        self.owner.after_trade_close(view, self.snapshot(snapshot), triggering_floor=triggering_floor)

    def end_session(self, context, snapshot):
        self.owner.end_session(self.target[self.mapping[context.session]], self.snapshot(snapshot))


def run_path(catalogue, schedule, owner, strategy_factory, config, target_contexts, *,
             capture=False, checkpoint=lambda: None):
    """Run one full declared path; failures invalidate the path, never redraw it."""
    if type(capture) is not bool:
        raise ValueError('Detailed path capture must be a strict boolean.')
    catalogue = verify_catalogue(catalogue, checkpoint=checkpoint)
    strategy = strategy_factory()
    if type(strategy) is not VwapPullbackRiskSizing or strategy.config != config:
        raise ValueError('Native draws require the actual supported VWAP strategy and exact execution configuration.')
    parameters = strategy.parameters
    fresh = build_schedule(catalogue, target_contexts, parameters, phase=schedule.get('phase'),
        seed=schedule.get('seed'), path_index=schedule.get('path_index'), start_date=schedule.get('start_date'),
        cutoff_date_exclusive=schedule.get('cutoff_date_exclusive'))
    if fresh != schedule:
        raise ValueError('Native schedule content, source, prefix or modeled target shape changed.')
    if owner.phase != fresh['phase'] or owner.contexts != target_contexts:
        raise ValueError('Native forecast owner phase or modeled contexts differ from the schedule.')
    if (owner.start_date != date.fromisoformat(fresh['start_date'])
            or owner.cutoff != date.fromisoformat(fresh['cutoff_date_exclusive'])):
        raise ValueError('Native forecast owner start or exclusive cutoff differs from its schedule.')
    planning = owner.sizing.planning_execution
    if (config.tick_size != Decimal('.25') or config.point_value != Decimal('2')
            or Decimal(planning['tick_size']) != config.tick_size or Decimal(planning['point_value']) != config.point_value
            or Decimal(planning['commission_per_contract_per_side']) != config.commission_per_contract_per_side
            or planning['entry_slippage_ticks'] != config.slippage_ticks
            or planning['stop_exit_slippage_ticks'] != config.slippage_ticks):
        raise ValueError('Native planning costs must exactly match actual MNQ source fills.')
    continuation = None
    captures, mappings = [], []
    target_provenance = {}
    for draw in fresh['draws']:
        checkpoint()
        block = catalogue.blocks[draw['source_block_index']]
        selected = catalogue.sessions[block.first_session:block.first_session+draw['used_sessions']]
        first, end = selected[0].first_bar, selected[-1].end_bar
        strategy = strategy_factory()
        if (type(strategy) is not VwapPullbackRiskSizing or strategy.config != config
                or _parameters(strategy.parameters) != catalogue.parameters_json):
            raise ValueError('Strategy factory changed its immutable block parameters.')
        for index in range(first):
            value = catalogue.bars[index]
            strategy.validate_holding_bar(value, None)
            if strategy.on_bar_controlled(value, None, lambda proposal: None) is not None:
                raise ValueError('Feature-only prefix produced an executable intent.')
            if index % 1000 == 0:
                checkpoint()
        mapping = {s.context.session:date.fromisoformat(target)
                   for s, target in zip(selected, draw['target_sessions'], strict=True)}
        for source_day, target_day in mapping.items():
            target_provenance[str(target_day)] = dict(path_index=fresh['path_index'], draw_slot=draw['slot'],
                source_session=str(source_day), target_session=str(target_day))
        adapter = _ClockView(owner, {s.context.session:s.context for s in selected}, target_contexts, mapping)
        detail = []
        final = None

        def replay_bars():
            for index in range(first, end):
                if index % 1000 == 0:
                    checkpoint()
                yield replace(catalogue.bars[index], bar_number=index-first+1)

        for value in execute(replay_bars(), strategy, config, account_control=adapter,
                continuation=continuation, completion='require_flat', capture_decisions=capture, capture_risk=capture):
            final = value
            if capture and type(value) is not EquityPoint:
                event_stamp = getattr(value, 'exit_time_utc', None) or value.timestamp_utc
                source_day = session_date(event_stamp)
                detail.append(dict(event_type=type(value).__name__, path_index=fresh['path_index'],
                    draw_slot=draw['slot'], source_session=str(source_day),
                    target_session=str(mapping[source_day]), **json_native(asdict(value))))
        if type(final) is not EquityPoint or final.position_contracts:
            raise ValueError('Native draw did not finish flat; no EOF liquidation is fabricated.')
        continuation = ExecutionContinuation(config.initial_capital, final.cash_balance)
        row = dict(slot=draw['slot'], source_block_index=block.index,
            source_sessions=draw['source_sessions'], target_sessions=draw['target_sessions'],
            warmup_bars=first, warmup_first_utc=(catalogue.bars[0].timestamp_utc.isoformat() if first else None),
            warmup_last_utc=(catalogue.bars[first-1].timestamp_utc.isoformat() if first else None),
            local_bar_numbers='1..executed_bars within each draw',
            source_row_number_convention='one_based_admitted_selection_ordinal',
            original_source_rows=[catalogue.bars[index].bar_number for index in range(first, end)] if capture else None,
            source_first_row=catalogue.bars[first].bar_number, source_last_row=catalogue.bars[end-1].bar_number,
            executed_bars=end-first, source_clock='actual observed source UTC', account_clock='modeled target UTC')
        mappings.append(row)
        if capture:
            captures.append(dict(**row, events=detail, final_equity=json_native(asdict(final))))
    result = owner.finish_replay()
    if result.get('observation_kind') != 'modeled' or 'historical_paths' in result:
        raise ValueError('Native forecast owner must return explicitly modeled outcomes, never historical observations.')
    for name, day_field in (('control_events', 'session'), ('trace', 'date'), ('sizing_decisions', 'session')):
        for row in result.get(name, []):
            day = row.get(day_field)
            row.update(target_provenance.get(day, dict(path_index=fresh['path_index'], draw_slot=None,
                source_session=None, target_session=day)))
    return dict(result=result, source_model_clock_mapping=mappings, captures=captures,
                schedule_sha256=fresh['schedule_sha256'], catalogue_sha256=catalogue.catalogue_sha256)

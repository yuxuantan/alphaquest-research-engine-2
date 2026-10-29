"""LucidFlex 50K transitions, qualified against the dated provider rule snapshot.

Dollar balances exclude the $50,000 starting balance. Only observed adverse
frontiers enter breach checks; no tick paths or live-account outcomes are invented.
"""
from dataclasses import dataclass, field
import numpy as np
import cython
from .native_engine import risk_hit, sampled_days


@dataclass(frozen=True)
class Rules:
    provider: str = 'lucidflex'
    max_dd: float = 2000.
    lock_profit: float = 100.
    safety_net: float = 0.
    ladder: tuple = (2000.,) * 5
    qualifying_days: int = 5
    qualifying_profit: float = 150.
    consistency: float = 1.  # No funded consistency rule.
    evaluation_consistency: float = .4
    daily_loss: float | None = 1200.
    payout_share: float = .9
    minimum_request: float = 500.
    inactivity_calendar_days: int = 30
    approval_day_counts: bool = True
    levels: tuple = ((0.,20,1200.), (1000.,30,1200.), (2000.,40,1200.))


@cython.ccall
@cython.locals(equity=cython.double,size=cython.double,dll=cython.double,floor=cython.double,
               daily_floor=cython.double,net=cython.double,adverse=cython.double,trough=cython.double,
               opening=cython.double,balance=cython.double)
def trade_result(trade, equity, size, daily_floor, floor):
    """Return balance and 0=continue, 1=DLL pause, 2=account breach."""
    net,adverse=trade[0],trade[1]
    trough=equity-adverse*size/10.
    threshold=max(daily_floor,floor)
    if trough<=threshold:
        if len(trade)>2 and trade[2] is not None:
            hit,balance=risk_hit(trade[2],equity,size,daily_floor,floor)
            if hit:return balance,hit
        return threshold,2 if floor>=daily_floor else 1
    balance=equity+net*size/10.
    if balance<=threshold:
        # A realized net/cost jump is observed, rather than clipped optimistically.
        return balance,2 if balance<=floor else 1
    return balance,0


@dataclass
class FundedAccount:
    rules: Rules = field(default_factory=Rules)
    equity: float = 0.
    high: float = 0.
    locked: bool = False
    day: int = 0
    cycle_start: float = 0.
    qualifying: int = 0
    payouts: list = field(default_factory=list)  # Trader receipts, after 90/10.
    withdrawals: list = field(default_factory=list)  # Full account deductions.
    outcome: str = 'open'
    last_activity: int = 0

    @cython.locals(opening=cython.double,floor=cython.double,size=cython.double,
                   daily_floor=cython.double,profit=cython.double,gross=cython.double,
                   previous=cython.double,balance=cython.double)
    def advance(self,trades,micros,max_micros=40,calendar_day=None):
        if self.outcome!='open':raise ValueError('Cannot advance a closed account.')
        self.day+=1
        calendar_day=((self.day-1)//5*7+(self.day-1)%5) if calendar_day is None else calendar_day
        if calendar_day-self.last_activity>self.rules.inactivity_calendar_days:
            self.outcome='inactive';return 0.
        opening=self.equity;r=self.rules
        floor=r.lock_profit if self.locked else min(self.high-r.max_dd,r.lock_profit)
        cap=20
        for threshold,level_cap,_ in r.levels:
            if opening>=threshold:cap=level_cap
        size=min(micros,cap,max_micros)
        daily_floor=opening-r.daily_loss if r.daily_loss is not None else -float('inf')
        amount=0.
        for trade in trades:
            previous=self.equity
            self.equity,hit=trade_result(trade,self.equity,size,daily_floor,floor)
            if abs(self.equity-previous)>=1:self.last_activity=calendar_day
            if hit==2:self.outcome='blown';return 0.
            profit=self.equity-opening
            # With DLL on, eligibility is checked at observed completed-trade
            # marks; a request stops trading for the remainder of that session.
            if r.daily_loss is not None and (len(trade)<4 or trade[3]) and self._eligible(profit):
                amount=self._withdraw();break
            if hit:break
        profit=self.equity+sum(v for d,v in self.withdrawals if d==self.day)-opening
        if not amount and self._eligible(profit):amount=self._withdraw()
        if not amount:self.qualifying+=profit>=r.qualifying_profit
        self.high=max(self.high,self.equity+(self.withdrawals[-1][1] if amount else 0.))
        if self.high-r.max_dd>=r.lock_profit:self.locked=True
        if calendar_day-self.last_activity>=r.inactivity_calendar_days and self.last_activity!=calendar_day:
            self.outcome='inactive'
        return amount

    def _eligible(self,profit):
        r=self.rules
        return (self.qualifying+(profit>=r.qualifying_profit)>=r.qualifying_days
                and self.equity>self.cycle_start
                and min(self.equity*.5,r.ladder[len(self.payouts)])>=r.minimum_request)

    def _withdraw(self):
        gross=min(self.equity*.5,self.rules.ladder[len(self.payouts)])
        self.equity-=gross;self.locked=True
        receipt=gross*self.rules.payout_share
        self.withdrawals.append((self.day,gross));self.payouts.append((self.day,receipt))
        self.cycle_start=self.equity;self.qualifying=0
        if len(self.payouts)==len(self.rules.ladder):self.outcome='paid_all'
        return receipt


@cython.locals(equity=cython.double,high=cython.double,opening=cython.double,
               floor=cython.double,daily_floor=cython.double,size=cython.double,
               best_day=cython.double,profit=cython.double,previous=cython.double,
               duration=cython.longlong,day=cython.longlong,last_activity=cython.longlong,
               calendar=cython.longlong,remaining=cython.longlong,index=cython.longlong,
               cursor=cython.longlong,length=cython.longlong,starts=cython.longlong[:])
def evaluation(days,micros,sims,seed,block=5,deadline=2000,chain=False,max_micros=40,
               daily_loss=1200.,consistency=.4):
    """No provider deadline: unfinished paths at 2,000 sessions are censored.

    A successful evaluation is assessed at session close, including consistency.
    Activation adds zero extra weekdays; new funded sampling begins next session.
    """
    if not days:raise ValueError('LucidFlex requires a nonempty source sample.')
    rng=np.random.RandomState(seed);outcomes=[];durations=[];attempts=[]
    length=len(days);starts=rng.randint(length,size=4096,dtype=np.int64);cursor=0
    for _ in range(sims):
        duration=0;remaining=0;index=0
        for attempt in range(1,10001 if chain else 2):
            equity=high=best_day=0.;last_activity=0;result='timeout'
            size=min(micros,40,max_micros)
            for day in range(1,deadline+1):
                calendar=(day-1)//5*7+(day-1)%5
                if calendar-last_activity>30:result='inactive';break
                opening=equity;floor=min(high-2000.,100.)
                daily_floor=opening-daily_loss if daily_loss is not None else -float('inf')
                if remaining==0:
                    if cursor==4096:starts=rng.randint(length,size=4096,dtype=np.int64);cursor=0
                    index=starts[cursor];cursor+=1;remaining=block
                trades=days[index];index=(index+1)%length;remaining-=1
                for trade in trades:
                    previous=equity
                    equity,hit=trade_result(trade,equity,size,daily_floor,floor)
                    if abs(equity-previous)>=1:last_activity=calendar
                    if hit==2:result='blown';break
                    if hit:break
                best_day=max(best_day,equity-opening);high=max(high,equity)
                if result=='blown':break
                if equity>=3000. and best_day<=consistency*equity:result='passed';break
                if calendar-last_activity>=30:result='inactive';break
            duration+=day
            if not chain or result=='passed':break
            if result=='timeout':raise ValueError('LucidFlex funding chain is censored at 2,000 sessions; acquisition time is unavailable.')
        if chain and result!='passed':raise ValueError('No pass within the 10,000-attempt funding-time bound; acquisition time is unavailable.')
        outcomes.append(result);durations.append(duration);attempts.append(attempt)
    return dict(outcomes=np.array(outcomes),days=np.array(durations),attempts=np.array(attempts))


@cython.locals(equity=cython.double,high=cython.double,opening=cython.double,floor=cython.double,
               daily_floor=cython.double,size=cython.double,profit=cython.double,gross=cython.double,
               receipt=cython.double,previous=cython.double,cycle_start=cython.double,
               qual=cython.longlong,day=cython.longlong,last_activity=cython.longlong,calendar=cython.longlong,
               cap=cython.longlong,hit=cython.longlong,remaining=cython.longlong,index=cython.longlong,
               length=cython.longlong,qual_days=cython.longlong,inactivity=cython.longlong,
               max_dd=cython.double,lock_profit=cython.double,dll=cython.double,qual_profit=cython.double,
               minimum=cython.double,share=cython.double,tier1=cython.double,tier2=cython.double,
               cap0=cython.longlong,cap1=cython.longlong,cap2=cython.longlong,limit=cython.longlong,
               has_dll=cython.bint,cursor=cython.longlong,starts=cython.longlong[:])
def funded(days,micros,sims,seed,block=5,horizon=2000,rules=Rules(),max_micros=40):
    """Primitive batch loop; every requested path consumes its own RNG stream.

    Avoid constructing Python account state at every session. Boundary tests
    compare the full final state against the public step-by-step account ledger.
    """
    rng=np.random.RandomState(seed);accounts=[];r=rules
    length=len(days);qual_days=r.qualifying_days;inactivity=r.inactivity_calendar_days
    max_dd=r.max_dd;lock_profit=r.lock_profit;has_dll=r.daily_loss is not None
    dll=r.daily_loss if has_dll else 0.;qual_profit=r.qualifying_profit;minimum=r.minimum_request;share=r.payout_share
    cap0=r.levels[0][1];tier1=r.levels[1][0];cap1=r.levels[1][1];tier2=r.levels[2][0];cap2=r.levels[2][1]
    limits=r.ladder;limit=len(limits)
    # Batched bounded integers are consumed in exactly the scalar stream order,
    # across account boundaries. Prefetching never changes or omits path draws.
    starts=rng.randint(length,size=4096,dtype=np.int64);cursor=0
    for _ in range(sims):
        equity=high=cycle_start=0.;locked=False;qual=day=last_activity=0
        payouts=[];withdrawals=[];outcome='open';remaining=0;index=0
        while day<horizon:
            if remaining==0:
                if cursor==4096:starts=rng.randint(length,size=4096,dtype=np.int64);cursor=0
                index=starts[cursor];cursor+=1;remaining=block
            trades=days[index];index=(index+1)%length;remaining-=1
            day+=1;calendar=(day-1)//5*7+(day-1)%5
            if calendar-last_activity>inactivity:outcome='inactive';break
            opening=equity;floor=lock_profit if locked else min(high-max_dd,lock_profit)
            cap=cap0 if opening<tier1 else cap1 if opening<tier2 else cap2
            size=min(micros,cap,max_micros)
            daily_floor=opening-dll if has_dll else -float('inf')
            gross=receipt=0.
            for trade in trades:
                previous=equity;equity,hit=trade_result(trade,equity,size,daily_floor,floor)
                if abs(equity-previous)>=1:last_activity=calendar
                if hit==2:outcome='blown';break
                profit=equity-opening
                if (has_dll and (len(trade)<4 or trade[3]) and qual+(profit>=qual_profit)>=qual_days
                        and equity>cycle_start and min(equity*.5,limits[len(payouts)])>=minimum):
                    gross=min(equity*.5,limits[len(payouts)]);break
                if hit:break
            if outcome=='blown':break
            profit=equity-opening
            if (not gross and qual+(profit>=qual_profit)>=qual_days
                    and equity>cycle_start and min(equity*.5,limits[len(payouts)])>=minimum):
                gross=min(equity*.5,limits[len(payouts)])
            high=max(high,equity)
            if gross:
                equity-=gross;locked=True;receipt=gross*share
                payouts.append((day,receipt));withdrawals.append((day,gross));qual=0;cycle_start=equity
                if len(payouts)==limit:outcome='paid_all'
            else:qual+=profit>=qual_profit
            if high-max_dd>=lock_profit:locked=True
            if calendar-last_activity>=inactivity and last_activity!=calendar:outcome='inactive'
            if outcome!='open' or day==horizon:break
        account=FundedAccount(rules=r,equity=equity,high=high,locked=locked,day=day,cycle_start=cycle_start,
            qualifying=qual,payouts=payouts,withdrawals=withdrawals,outcome=outcome,last_activity=last_activity)
        accounts.append(account)
    return accounts

"""One shared monthly fee budget; account equity is never investor cash."""
from datetime import date
from decimal import Decimal
from .cash_ledger import cash,payout_amounts

ZERO=Decimal('0.00')


class PortfolioCash:
    def __init__(self,monthly_cap,cutoff):
        self.cap=cash(monthly_cap);self.cutoff=date.fromisoformat(cutoff)
        self.month=None;self.spent=ZERO;self.reservations={};self.evaluation=ZERO;self.activation=ZERO;self.received=ZERO
        self.pending=[];self.ledger=[];self.months={};self.day=None

    @property
    def reserved(self):return sum(self.reservations.values(),ZERO)

    def emit(self,event,slot=None,fee=ZERO,receipt=ZERO,**details):
        if not ZERO<=self.spent<=self.cap or not ZERO<=self.reserved<=self.cap-self.spent:
            raise ValueError('Portfolio monthly fee/reservation budget failed conservation.')
        row=dict(date=str(self.day),month=self.month,event=event,slot=slot,paid_fee=str(fee),trader_receipt=str(receipt),
            cash_delta=str(receipt-fee),paid_this_month=str(self.spent),reserved_allowance=str(self.reserved),
            available_allowance=str(self.cap-self.spent-self.reserved),net_cash=str(self.received-self.evaluation-self.activation),**details)
        self.ledger.append(row)
        m=self.months[self.month]
        m['fees']+=fee;m['receipts']+=receipt

    def advance(self,day):
        self.day=day;month=day.strftime('%Y-%m')
        if month!=self.month:
            self.month=month;self.spent=ZERO
            self.months[month]=dict(fees=ZERO,receipts=ZERO)
            self.emit('month_reset',policy='No rollover; existing activation obligations are reserved against the new month. Receipts never enlarge the cap.')
        self.receive_due()

    def buy(self,slot,evaluation,activation):
        fee,reserve=cash(evaluation),cash(activation)
        if self.cap-self.spent-self.reserved<fee+reserve:
            return False
        self.spent+=fee;self.evaluation+=fee;self.reservations[slot]=reserve
        self.emit('evaluation_purchase',slot,fee=fee,activation_reserved=str(reserve));return True

    def release(self,slot,reason):
        amount=self.reservations.pop(slot,ZERO)
        if amount:self.emit('activation_reservation_released',slot,amount=str(amount),reason=reason)

    def activate(self,slot,fee):
        fee=cash(fee)
        if self.reservations.get(slot,ZERO)!=fee:raise ValueError('Activation lacks its exact reserved fee.')
        self.reservations.pop(slot,None);self.spent+=fee;self.activation+=fee
        self.emit('activation_payment',slot,fee=fee)

    def payout(self,slot,event):
        amounts=payout_amounts(event['raw_trader_entitlement'],event['gross_account_deduction'])
        self.emit('payout_request',slot,amount=amounts['trader_amount'],gross_account_deduction=amounts['gross_account_deduction'])
        self.emit('account_deduction',slot,amount=amounts['gross_account_deduction'],already_applied_by_account_owner=True)
        self.pending.append(dict(slot=slot,receipt_date=event['receipt_date'],amount=amounts['trader_amount'],received=False))

    def receive_due(self):
        for item in self.pending:
            if not item['received'] and date.fromisoformat(item['receipt_date'])<=self.day<self.cutoff:
                amount=Decimal(item['amount']);self.received+=amount;item['received']=True
                self.emit('trader_receipt',item['slot'],receipt=amount,receipt_date=item['receipt_date'])

    def result(self):
        return dict(received_trader_cash=str(self.received),paid_evaluation_fees=str(self.evaluation),
            paid_activation_fees=str(self.activation),paid_fees=str(self.evaluation+self.activation),
            net_cash=str(self.received-self.evaluation-self.activation),
            pending_receipts=str(sum((Decimal(p['amount']) for p in self.pending if not p['received']),ZERO)),
            outstanding_activation_reservations=str(self.reserved),
            monthly=[dict(month=m,paid_fees=str(v['fees']),trader_receipts=str(v['receipts']),
                net_cash=str(v['receipts']-v['fees']),cap=str(self.cap)) for m,v in self.months.items()])

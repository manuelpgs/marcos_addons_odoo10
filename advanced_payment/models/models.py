# -*- coding: utf-8 -*-
########################################################################################################################
#  Copyright (c) 2015 - Marcos Organizador de Negocios SRL. (<https://marcos.do/>) #  Write by Eneldo Serrata (eneldo@marcos.do)
#  See LICENSE file for full copyright and licensing details.
#
# Odoo Proprietary License v1.0
#
# This software and associated files (the "Software") may only be used
# (nobody can redistribute (or sell) your module once they have bought it, unless you gave them your consent)
# if you have purchased a valid license
# from the authors, typically via Odoo Apps, or if you have received a written
# agreement from the authors of the Software (see the COPYRIGHT file).
#
# You may develop Odoo modules that use the Software as a library (typically
# by depending on it, importing it and using its resources), but without copying
# any source code or material from the Software. You may distribute those
# modules under the license of your choice, provided that this license is
# compatible with the terms of the Odoo Proprietary License (For example:
# LGPL, MIT, or proprietary licenses similar to this one).
#
# It is forbidden to publish, distribute, sublicense, or sell copies of the Software
# or modified copies of the Software.
#
# The above copyright notice and this permission notice must be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.
# IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM,
# DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE,
# ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER
# DEALINGS IN THE SOFTWARE.
########################################################################################################################

from openerp import models, fields, api, exceptions, _


class AccountPayment(models.Model):
    _inherit = "account.payment"

    move_type = fields.Selection([('auto', 'Automatic'), ('manual', 'Manual'), ('invoice', 'Pay bills')],
                                 string=u"Method of accounting entries",
                                 default="auto", required=True, copy=False)
    state = fields.Selection([('draft', 'Draft'), ('request', 'Solicitud'), ('posted', 'Posted'), ('sent', 'Sent'),
                              ('reconciled', 'Reconciled')], readonly=True, default='draft', copy=False,
                             string="Status")
    payment_move_ids = fields.One2many("payment.move.line", "payment_id", copy=False)
    payment_invoice_ids = fields.One2many("payment.invoice.line", "payment_id", copy=False, limit=1000)


    def _create_payment_entry_manual(self, amount):
        manual_debit = round(sum([line.debit for line in self.payment_move_ids]), 2)
        manual_credit = round(sum([line.credit for line in self.payment_move_ids]), 2)
        if manual_credit != manual_debit:
            raise exceptions.UserError(_("You can not create journal entry that is not square."))

        aml_obj = self.env['account.move.line'].with_context(check_move_validity=False)
        invoice_currency = False
        if self.invoice_ids and all([x.currency_id == self.invoice_ids[0].currency_id for x in self.invoice_ids]):
            # if all the invoices selected share the same currency, record the paiement in that currency too
            invoice_currency = self.invoice_ids[0].currency_id
        debit, credit, amount_currency, currency_id = aml_obj.with_context(
            date=self.payment_date).compute_amount_fields(amount, self.currency_id, self.company_id.currency_id,
                                                          invoice_currency)

        move = self.env['account.move'].create(self._get_move_vals())

        # Write line corresponding to invoice payment
        counterpart_aml_dict = self._get_shared_move_line_vals(debit, credit, amount_currency, move.id, False)
        counterpart_aml_dict.update(self._get_counterpart_move_line_vals(self.invoice_ids))
        counterpart_aml_dict.update({'currency_id': currency_id})

        account_id = self.payment_type in ('outbound',
                                           'transfer') and self.journal_id.default_debit_account_id.id or self.journal_id.default_credit_account_id.id,
        manual_lines = [line for line in self.payment_move_ids if line.account_id.id not in account_id]
        rate = False
        if counterpart_aml_dict.get("amount_currency", False):
            rate = counterpart_aml_dict["debit"] / counterpart_aml_dict["amount_currency"] if counterpart_aml_dict[
                                                                                                  "debit"] > 0 else \
                counterpart_aml_dict["credit"] / counterpart_aml_dict["amount_currency"]
        for line in manual_lines:

            line_amount_currency = False
            line_debit = line.debit
            line_credit = line.credit
            if rate:
                line_amount_currency = line.debit if line.debit else line.credit
                line_debit = line_debit * rate
                line_credit = line_credit * rate

            line_dict = {'account_id': line.account_id.id,
                         'amount_currency': line_amount_currency,
                         'credit': line_credit,
                         'currency_id': counterpart_aml_dict["currency_id"],
                         'debit': line_debit,
                         'invoice_id': counterpart_aml_dict["invoice_id"],
                         'journal_id': counterpart_aml_dict["journal_id"],
                         'move_id': counterpart_aml_dict["move_id"],
                         'name': line.name or counterpart_aml_dict["name"],
                         'partner_id': line.partner_id.id if line.partner_id else counterpart_aml_dict["partner_id"],
                         'product_id': line.product_id.id,
                         'payment_id': counterpart_aml_dict["payment_id"]}
            aml_obj.create(line_dict)

        # Write counterpart lines
        if not self.currency_id != self.company_id.currency_id:
            amount_currency = 0
        liquidity_aml_dict = self._get_shared_move_line_vals(credit, debit, -amount_currency, move.id, False)
        liquidity_aml_dict.update(self._get_liquidity_move_line_vals(-amount))
        aml_obj.create(liquidity_aml_dict)

        return move

    def _create_payment_entry_invoice(self, amount):
        """ Create a journal entry corresponding to a payment, if the payment references invoice(s) they are reconciled.
            Return the journal entry.
        """

        aml_obj = self.env['account.move.line'].with_context(check_move_validity=False)
        invoice_currency = False
        if self.invoice_ids and all([x.currency_id == self.invoice_ids[0].currency_id for x in self.invoice_ids]):
            # if all the invoices selected share the same currency, record the paiement in that currency too
            invoice_currency = self.invoice_ids[0].currency_id
        debit, credit, amount_currency, currency_id = aml_obj.with_context(
            date=self.payment_date).compute_amount_fields(amount, self.currency_id, self.company_id.currency_id,
                                                          invoice_currency)

        move = self.env['account.move'].create(self._get_move_vals())

        [inv.unlink() for inv in self.payment_invoice_ids if inv.amount == 0]
        self.invoice_ids = self.env["account.invoice"].browse(
            [m_line.move_line_id.invoice_id.id for m_line in self.payment_invoice_ids])
        for inv in self.payment_invoice_ids:
            # Write line corresponding to invoice payment
            inv_credit = inv.amount if credit > 0 else 0
            inv_debit = inv.amount if debit > 0 else 0
            counterpart_aml_dict = self._get_shared_move_line_vals(inv_debit, inv_credit, amount_currency, move.id,
                                                                   False)
            counterpart_aml_dict.update(self._get_counterpart_move_line_vals(inv.move_line_id.invoice_id))
            counterpart_aml_dict.update({'currency_id': currency_id})
            counterpart_aml = aml_obj.create(counterpart_aml_dict)
            inv.move_line_id.invoice_id.register_payment(counterpart_aml)

        # Write counterpart lines
        if not self.currency_id != self.company_id.currency_id:
            amount_currency = 0
        liquidity_aml_dict = self._get_shared_move_line_vals(credit, debit, -amount_currency, move.id, False)
        liquidity_aml_dict.update(self._get_liquidity_move_line_vals(-amount))
        aml_obj.create(liquidity_aml_dict)
        move.post()
        return move

    def set_payment_name(self):
        if self.state not in ('draft', 'request'):
            raise exceptions.UserError(
                _("Only a draft payment can be posted. Trying to post a payment in state %s.") % self.state)

        if any(inv.state != 'open' for inv in self.invoice_ids):
            raise Exception.ValidationError(_("The payment cannot be processed because the invoice is not open!"))

        if not self.name or self.name == "Draft Payment":
            if self.payment_type == 'transfer':
                sequence_code = 'account.payment.transfer'
            else:
                if self.partner_type == 'customer':
                    if self.payment_type == 'inbound':
                        sequence_code = 'account.payment.customer.invoice'
                    if self.payment_type == 'outbound':
                        sequence_code = 'account.payment.customer.refund'
                if self.partner_type == 'supplier':
                    if self.payment_type == 'inbound':
                        sequence_code = 'account.payment.supplier.refund'
                    if self.payment_type == 'outbound':
                        sequence_code = 'account.payment.supplier.invoice'
            self.name = self.env['ir.sequence'].with_context(ir_sequence_date=self.payment_date).next_by_code(
                sequence_code)

    @api.multi
    def post(self):
        for rec in self:
            if rec.move_type == "auto":
                # Create the journal entry
                amount = rec.amount * (rec.payment_type in ('outbound', 'transfer') and 1 or -1)
                move = rec._create_payment_entry(amount)
                if rec.payment_type == 'transfer':
                    transfer_credit_aml = move.line_ids.filtered(
                        lambda r: r.account_id == rec.company_id.transfer_account_id)
                    transfer_debit_aml = rec._create_transfer_entry(amount)
                    (transfer_credit_aml + transfer_debit_aml).reconcile()
                rec.state = 'posted'
            elif rec.move_type == "manual":
                amount = rec.amount * (rec.payment_type in ('outbound', 'transfer') and 1 or -1)
                rec._create_payment_entry_manual(amount)
                rec.state = 'posted'
            elif rec.move_type == "invoice":
                amount = rec.amount * (rec.payment_type in ('outbound', 'transfer') and 1 or -1)
                rec._create_payment_entry_invoice(amount)
                rec.state = 'posted'

    @api.multi
    def payment_request(self):
        for rec in self:
            if rec.move_type == "auto":
                rec.state = 'request'
            elif rec.move_type == "manual":
                rec.state = 'request'
            elif rec.move_type == "invoice":
                rec.calc_invoice_check()
                [inv_line.unlink for inv_line in rec.payment_invoice_ids if inv_line.amount == 0]
                rec.state = 'request'
            rec.set_payment_name()

    @api.model
    def set_default_account_move(self):
        if self.journal_id:
            if self.payment_move_ids:
                self.payment_move_ids = False
            if self.payment_type == "outbound":
                first_move = self.env["payment.move.line"].create(
                    {"account_id": self.journal_id.default_credit_account_id.id, "credit": self.amount})
                self.payment_move_ids = first_move

            elif self.payment_type == "inbound":
                first_move = self.env["payment.move.line"].create(
                    {"account_id": self.journal_id.default_debit_account_id.id, "debit": self.amount})
                self.payment_move_ids = first_move

    def reset_move_type(self):
        self.move_type = "auto"

    @api.onchange('payment_type')
    def _onchange_payment_type(self):
        self.reset_move_type()
        return super(AccountPayment, self)._onchange_payment_type()

    @api.onchange('journal_id')
    def _onchange_journal(self):
        self.reset_move_type()
        return super(AccountPayment, self)._onchange_journal()

    @api.onchange('partner_type')
    def _onchange_partner_type(self):
        self.reset_move_type()
        return super(AccountPayment, self)._onchange_partner_type()

    @api.onchange("payment_invoice_ids")
    def onchange_payment_invoice_ids(self):
        self.amount = sum([rec.amount for rec in self.payment_invoice_ids])
        full_payment = [rec.move_line_id.invoice_id.number[-4:] for rec in self.payment_invoice_ids if
                        rec.amount == rec.balance]
        partinal_payment = [rec.move_line_id.invoice_id.number[-4:] for rec in self.payment_invoice_ids if
                            rec.amount < rec.balance and rec.amount > 0]
        communication = ""
        if full_payment:
            communication += "PAGO FAC: {} ".format(",".join(full_payment))
        if partinal_payment:
            communication += "ABONO FAC: {} ".format(",".join(partinal_payment))
        self.communication = communication

    @api.one
    @api.constrains('amount')
    def _check_amount(self):
        if not self.amount > 0.0 and self.state != "draft":
            raise exceptions.ValidationError(_('The payment amount must be strictly positive.'))

    @api.multi
    def calc_invoice_check(self):
        self.onchange_payment_invoice_ids()

    @api.onchange("move_type")
    def onchange_move_type(self):
        if self.move_type == "manual":
            [rec.unlink for rec in self.payment_invoice_ids]
            self.set_default_account_move()
        elif self.move_type == "invoice":
            self.update_invoice()
            [rec.unlink for rec in self.payment_move_ids]
        else:
            [rec.unlink for rec in self.payment_invoice_ids]
            [rec.unlink for rec in self.payment_move_ids]

    @api.multi
    def update_invoice(self):
        for rec in self:
            journal_type = 'purchase' if rec.payment_type == "outbound" else 'sale'

            if not rec.partner_id:
                rec.move_type = "auto"
                return {
                    'value': {"move_type": "auto"},
                    'warning': {'title': "Warning", 'message': _("You must first select a partner.")},
                }

            to_reconciled_move_lines = []


            open_invoice = self.env["account.invoice"].search([('state', '=', 'open'),
                                                                    ('pay_to', '=', rec.partner_id.id),
                                                                    ('journal_id.type', '=', journal_type)])


            if not open_invoice:
                open_invoice = self.env["account.invoice"].search([('state', '=', 'open'),
                                                               ('partner_id', '=', rec.partner_id.id),
                                                               ('journal_id.type', '=', journal_type),
                                                               ('pay_to', '=', False)])


            inv_ids = [inv.id for inv in open_invoice]


            if inv_ids == []:
                rec.move_type = "auto"

            rows = self.env['account.move.line'].search([('invoice_id', 'in', inv_ids),
                                                         ('account_id.reconcile', '=', True),
                                                         ('reconciled', '=', False)
                                                         ])

            lines_on_payment = [line.move_line_id.id for line in rec.payment_invoice_ids]

            for row in rows:
                if not row.id in lines_on_payment:
                    to_reconciled_move_lines.append(rec.payment_invoice_ids.create({'move_line_id': row.id}))

            move_ids = [move.id for move in to_reconciled_move_lines]
            to_reconciled_move_lines = rec.payment_invoice_ids.browse(move_ids)
            rec.payment_invoice_ids += to_reconciled_move_lines

    @api.onchange('partner_id')
    def onchange_partner_id(self):
        self.reset_move_type()

    @api.multi
    def pay_all(self):
        for rec in self:
            for line in rec.payment_invoice_ids:
                line.full_pay()
        self.calc_invoice_check()

    @api.multi
    def payment_request_print(self):
        """ Print the invoice and mark it as sent, so that we can see more
            easily the next step of the workflow
        """
        self.ensure_one()
        self.sent = True
        return self.env['report'].get_action(self, 'advanced_payment.payment_request_report_doc')


class PaymentInvoiceLine(models.Model):
    _name = "payment.invoice.line"

    @api.one
    def _calc_amount(self):
        for rec in self:
            rec.net = rec.move_line_id.balance * -1 if rec.move_line_id.balance < 0 else rec.move_line_id.balance
            rec.balance_cash_basis = rec.move_line_id.balance_cash_basis * -1 if rec.move_line_id.balance_cash_basis < 0 else rec.move_line_id.balance_cash_basis
            rec.balance = rec.net - rec.balance_cash_basis

    payment_id = fields.Many2one("account.payment")
    currency_id = fields.Many2one('res.currency', string='Currency', related="payment_id.currency_id",
                                  help="The optional other currency if it is a multi-currency entry.")
    company_currency_id = fields.Many2one('res.currency', related='payment_id.currency_id', readonly=True,
                                          help='Utility field to express amount currency', store=True)

    move_line_id = fields.Many2one("account.move.line", "Facturas", readonly=True)
    move_date = fields.Date("Date", related="move_line_id.date", readonly=True)
    date_maturity = fields.Date("Due date", related="move_line_id.date_maturity", readonly=True)
    net = fields.Float("Amount", compute=_calc_amount)
    balance_cash_basis = fields.Float("Paid", compute=_calc_amount)
    balance = fields.Float("Balance", compute=_calc_amount)
    amount = fields.Float("To pay", default=0.0)
    state = fields.Selection([('draft', 'Draft'), ('request', 'Solicitud'), ('posted', 'Posted'), ('sent', 'Sent'),
                              ('reconciled', 'Reconciled')], related="payment_id.state")

    @api.onchange('amount')
    def onchange_amount(self):
        if self.amount > self.balance:
            self.amount = 0
        elif self.amount < 0:
            self.amount = 0

    @api.one
    def full_pay(self):
        self.amount = self.balance

    @api.one
    def unfull_pay(self):
        self.amount = 0


class PaymentMoveLine(models.Model):
    _name = "payment.move.line"

    payment_id = fields.Many2one("account.payment")
    account_id = fields.Many2one("account.account", string="Account", required=True)
    name = fields.Char("Etiqueta")
    product_id = fields.Many2one('product.product', string='Producto')
    partner_id = fields.Many2one('res.partner', string='Partner', index=True, ondelete='restrict')
    analytic_account_id = fields.Many2one('account.analytic.account', string='Analytic Account')
    company_currency_id = fields.Many2one('res.currency', related='company_id.currency_id', readonly=True,
                                          help='Utility field to express amount currency', store=True)
    company_currency_id = fields.Many2one('res.currency', related='payment_id.currency_id', readonly=True,
                                          help='Utility field to express amount currency', store=True)
    company_id = fields.Many2one('res.company', related='account_id.company_id', string='Company', store=True)

    debit = fields.Monetary(string="Debit", default=0.0, currency_field='company_currency_id', digits=(16, 2))
    credit = fields.Monetary(string="Credit", default=0.0, currency_field='company_currency_id', digits=(16, 2))


class PaymentRquestReport(models.AbstractModel):
    _name = 'report.advanced_payment.payment_request_report_doc'

    @api.multi
    def render_html(self, data=None):
        report_obj = self.env['report']
        report = report_obj._get_report_from_name('advanced_payment.payment_request_report_doc')
        payments = self.env["account.payment"].browse(self._ids)
        docargs = {
            'doc_ids': self._ids,
            'doc_model': report.model,
            'docs': payments,
        }
        return report_obj.render('advanced_payment.payment_request_report_doc', docargs)

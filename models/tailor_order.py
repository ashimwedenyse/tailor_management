# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
from twilio.rest import Client
import logging

_logger = logging.getLogger(__name__)


class TailorOrder(models.Model):
    _name = 'tailor.order'
    _description = 'Tailor Order'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'create_date desc'

    # =========================
    # Fields
    # =========================
    name = fields.Char(
        string="Order Reference",
        required=True,
        readonly=True,
        default='New',
        copy=False,
        tracking=True
    )

    customer_id = fields.Many2one(
        'res.partner',
        string="Customer",
        required=True,
        tracking=True,
        domain=[]
    )

    status = fields.Selection([
        ('draft', "Draft"),
        ('received', "Received"),
        ('measurement', "Measurement"),
        ('cutting', "Cutting"),
        ('sewing', "Sewing"),
        ('finishing', "Finishing"),
        ('quality_check', "Quality Check"),
        ('ready', "Ready for Delivery"),
        ('delivered', "Delivered"),
        ('cancelled', "Cancelled")
    ], default='draft', tracking=True)

    order_date = fields.Datetime(default=fields.Datetime.now, required=True)
    delivery_date = fields.Datetime(tracking=True)

    # --- Document Management ---
    design_image = fields.Binary(string="Design Sketch", attachment=True)
    fabric_image = fields.Binary(string="Fabric Photo", attachment=True)

    # Counts attached files for the Smart Button
    document_count = fields.Integer(compute='_compute_document_count', string="Document Count")

    # Measurements
    chest_measurement = fields.Float(tracking=True)
    waist_measurement = fields.Float(tracking=True)
    hip_measurement = fields.Float(tracking=True)
    shoulder_width = fields.Float(tracking=True)
    sleeve_length = fields.Float(tracking=True)
    armhole = fields.Float(tracking=True)
    back_length = fields.Float(tracking=True)
    front_length = fields.Float(tracking=True)

    # Garment
    garment_type = fields.Selection([
        ('kandura', "Kandura"),
        ('thobe', "Thobe"),
        ('shirt', "Shirt"),
        ('pants', "Pants"),
        ('suit', "Suit"),
        ('other', "Other")
    ], default='kandura', tracking=True)

    fabric_type = fields.Char(tracking=True)
    color = fields.Char(tracking=True)
    special_instructions = fields.Text()

    # --- Financial & KPIs (UPDATED) ---
    currency_id = fields.Many2one(
        'res.currency',
        default=lambda self: self.env.company.currency_id,
        required=True
    )

    total_amount = fields.Monetary(string="Total Revenue", tracking=True)
    advance_paid = fields.Monetary(tracking=True)
    balance_due = fields.Monetary(compute='_compute_balance', store=True)

    # NEW: Costs & Profit for Dashboard
    production_cost = fields.Monetary(string="Production Cost", default=0.0, tracking=True)
    net_profit = fields.Monetary(string="Net Profit", compute="_compute_profit", store=True, tracking=True)

    # Notifications
    send_email_notifications = fields.Boolean(default=True, tracking=True)
    send_sms_notifications = fields.Boolean(default=True, tracking=True)

    # Relations
    attachment_ids = fields.Many2many('ir.attachment')
    salesperson_id = fields.Many2one('res.users', default=lambda self: self.env.user, tracking=True)
    tailor_id = fields.Many2one('res.users', tracking=True)

    customer_phone = fields.Char(related='customer_id.phone', readonly=True)
    customer_email = fields.Char(related='customer_id.email', readonly=True)

    # =========================
    # Computed Methods
    # =========================
    @api.depends('total_amount', 'advance_paid')
    def _compute_balance(self):
        for order in self:
            order.balance_due = order.total_amount - order.advance_paid

    @api.depends('total_amount', 'production_cost')
    def _compute_profit(self):
        for order in self:
            order.net_profit = order.total_amount - order.production_cost

    def _compute_document_count(self):
        for order in self:
            order.document_count = self.env['ir.attachment'].search_count([
                ('res_model', '=', 'tailor.order'),
                ('res_id', '=', order.id)
            ])

    # =========================
    # Actions (Buttons)
    # =========================
    def action_view_documents(self):
        """ Opens the standard Odoo document view for this record """
        self.ensure_one()
        return {
            'name': _('Documents'),
            'type': 'ir.actions.act_window',
            'res_model': 'ir.attachment',
            'view_mode': 'kanban,tree,form',
            'domain': [('res_model', '=', 'tailor.order'), ('res_id', '=', self.id)],
            'context': {'default_res_model': 'tailor.order', 'default_res_id': self.id},
        }

    # =========================
    # Constraints
    # =========================
    @api.constrains('advance_paid', 'total_amount')
    def _check_advance(self):
        for order in self:
            if order.advance_paid < 0:
                raise ValidationError(_("Advance cannot be negative"))
            if order.advance_paid > order.total_amount:
                raise ValidationError(_("Advance cannot exceed total"))

    # =========================
    # Create override
    # =========================
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code('tailor.order') or 'New'
        return super(TailorOrder, self).create(vals_list)

    # =========================
    # Status update actions
    # =========================
    def _update_status(self, new_status):
        for order in self:
            old_status = order.status
            order.status = new_status
            order._send_status_notifications(old_status, new_status)

    def action_confirm_received(self):
        self._update_status('received')

    def action_start_measurement(self):
        self._update_status('measurement')

    def action_start_cutting(self):
        self._update_status('cutting')

    def action_start_sewing(self):
        self._update_status('sewing')

    def action_start_finishing(self):
        self._update_status('finishing')

    def action_quality_check(self):
        self._update_status('quality_check')

    def action_mark_ready(self):
        self._update_status('ready')

    def action_mark_delivered(self):
        self._update_status('delivered')

    def action_cancel(self):
        self._update_status('cancelled')

    # =========================
    # Notifications (CLEAN PRODUCTION VERSION)
    # =========================
    def _send_status_notifications(self, old, new):
        for order in self:
            # 1. Log the status change
            order.message_post(
                body=_("Status changed from %s to %s") % (old.capitalize(), new.capitalize()),
                subtype_xmlid='mail.mt_note'
            )

            # 2. Handle Email
            if order.send_email_notifications:
                order._send_email_notification(new)

            # 3. Handle SMS
            mobile = getattr(order.customer_id, 'mobile', False)
            target_phone = order.customer_phone or mobile
            if order.send_sms_notifications and target_phone:
                order._send_sms_notification(new, target_phone)

    def _send_email_notification(self, status):
        """Send email notification based on order status using Tailor Gmail server"""
        self.ensure_one()
        mapping = {
            'received': 'tailor_management.email_template_order_received',
            'measurement': 'tailor_management.email_template_measurement',
            'cutting': 'tailor_management.email_template_production',
            'sewing': 'tailor_management.email_template_production',
            'finishing': 'tailor_management.email_template_production',
            'quality_check': None,
            'ready': 'tailor_management.email_template_ready',
            'delivered': 'tailor_management.email_template_delivered',
            'cancelled': 'tailor_management.email_template_cancelled',
        }

        xmlid = mapping.get(status)
        if not xmlid:
            return

        template = self.env.ref(xmlid, raise_if_not_found=False)
        if not template:
            _logger.warning("Email template not found: %s", xmlid)
            return

        if not self.customer_email:
            _logger.warning("Customer email missing for order %s", self.name)
            return

        # Force Gmail Server
        mail_server = self.env['ir.mail_server'].search([('name', '=', 'Tailor Gmail')], limit=1)

        email_values = {
            'email_to': self.customer_email,
            'email_from': mail_server.smtp_user if mail_server else (self.env.user.email or self.env.company.email),
            'reply_to': self.env.company.email or '',
        }

        if mail_server:
            email_values['mail_server_id'] = mail_server.id

        try:
            template.sudo().send_mail(
                self.id,
                force_send=True,
                email_values=email_values
            )
            _logger.info("Email sent for order %s (status: %s)", self.name, status)
        except Exception as e:
            _logger.error("Failed to send email for order %s: %s", self.name, str(e))

    # =========================
    # Twilio helpers
    # =========================
    def _get_twilio_config(self):
        params = self.env['ir.config_parameter'].sudo()
        return {
            'sid': params.get_param('tailor_management.twilio_account_sid'),
            'token': params.get_param('tailor_management.twilio_auth_token'),
            'from': params.get_param('tailor_management.twilio_from_number'),
        }

    def _send_sms_notification(self, status, target_phone=None):
        self.ensure_one()

        # 1. DEFINE MESSAGES
        messages = {
            'received': _("Hello %s! Your order %s has been received."),
            'measurement': _("Hi %s! Measurement scheduled for order %s."),
            'cutting': _("Hello %s, your order %s is now in cutting."),
            'sewing': _("Hello %s, your order %s is being sewn."),
            'finishing': _("Hello %s, your order %s is in finishing."),
            'quality_check': _("Hello %s, order %s is under quality check."),
            'ready': _("Hello %s, Order %s ready! Balance: %.2f %s"),
            'delivered': _("Hello %s, Order %s delivered. Thank you!"),
            'cancelled': _("Hello %s, Order %s has been cancelled."),
        }

        template_text = messages.get(status)
        if not template_text:
            return

        # 2. FORMAT BODY TEXT
        if status == 'ready':
            body = template_text % (
                self.customer_id.name or "Customer",
                self.name,
                self.balance_due,
                self.currency_id.symbol
            )
        else:
            body = template_text % (
                self.customer_id.name or "Customer",
                self.name
            )

        # 3. GET CONFIG & SEND
        try:
            cfg = self._get_twilio_config()

            if not all(cfg.values()):
                # Log to server logs only, keep chatter clean
                _logger.warning("Twilio config missing. SMS skipped for %s", self.name)
                return

            # Formatting
            from_number = cfg['from']
            if not from_number.startswith('whatsapp:'):
                from_number = f"whatsapp:{from_number}"

            if not target_phone:
                mobile = getattr(self.customer_id, 'mobile', False)
                target_phone = self.customer_phone or mobile

            if not target_phone:
                return  # Skip silently if no phone found

            # Clean Number
            to_number = target_phone.replace(' ', '')
            if to_number.startswith('0'):
                to_number = '+250' + to_number[1:]

            if not to_number.startswith('+'):
                # Log error to chatter only if phone number format is invalid
                self.message_post(body=f"⚠️ WhatsApp Failed: Number {to_number} invalid format.")
                return

            if not to_number.startswith('whatsapp:'):
                to_number = f"whatsapp:{to_number}"

            # SEND MESSAGE
            client = Client(cfg['sid'], cfg['token'])
            client.messages.create(body=body, from_=from_number, to=to_number)

            # Log Success in Chatter (Professional Note)
            self.message_post(body=f"WhatsApp notification sent to {target_phone}")

        except Exception as e:
            _logger.error("WhatsApp failed: %s", str(e))
            # Only show critical errors in chatter
            self.message_post(body=f"⚠️ WhatsApp Failed: {str(e)}")
# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
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
        default=lambda self: _('New'),
        tracking=True
    )

    customer_id = fields.Many2one(
        'res.partner',
        string="Customer",
        required=True,
        tracking=True,
        domain=[('customer_rank', '>', 0)]
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
    ], string="Status", default='draft', tracking=True)

    order_date = fields.Datetime(string="Order Date", default=fields.Datetime.now, required=True)
    delivery_date = fields.Datetime(string="Expected Delivery Date", tracking=True)

    # Measurements
    chest_measurement = fields.Float(string="Chest (cm)", tracking=True)
    waist_measurement = fields.Float(string="Waist (cm)", tracking=True)
    hip_measurement = fields.Float(string="Hip (cm)", tracking=True)
    shoulder_width = fields.Float(string="Shoulder Width (cm)", tracking=True)
    sleeve_length = fields.Float(string="Sleeve Length (cm)", tracking=True)
    armhole = fields.Float(string="Armhole (cm)", tracking=True)
    back_length = fields.Float(string="Back Length (cm)", tracking=True)
    front_length = fields.Float(string="Front Length (cm)", tracking=True)

    # Garment details
    garment_type = fields.Selection([
        ('kandura', "Kandura"),
        ('thobe', "Thobe"),
        ('shirt', "Shirt"),
        ('pants', "Pants"),
        ('suit', "Suit"),
        ('other', "Other")
    ], string="Garment Type", default='kandura', tracking=True)
    fabric_type = fields.Char(string="Fabric Type", tracking=True)
    color = fields.Char(string="Color", tracking=True)
    special_instructions = fields.Text(string="Special Instructions")

    # Financial
    currency_id = fields.Many2one(
        'res.currency',
        string="Currency",
        default=lambda self: self.env.company.currency_id,
        required=True
    )
    total_amount = fields.Monetary(string="Total Amount", currency_field='currency_id', tracking=True)
    advance_paid = fields.Monetary(string="Advance Paid", currency_field='currency_id', tracking=True)
    balance_due = fields.Monetary(string="Balance Due", currency_field='currency_id', compute='_compute_balance', store=True)

    # Notifications
    send_email_notifications = fields.Boolean(string="Email Notifications", default=True, tracking=True)
    send_sms_notifications = fields.Boolean(string="SMS/WhatsApp Notifications", default=False, tracking=True)

    # Related fields
    attachment_ids = fields.Many2many('ir.attachment', string="Attachments")

    # Assigned staff
    salesperson_id = fields.Many2one('res.users', string="Salesperson", default=lambda self: self.env.user, tracking=True)
    tailor_id = fields.Many2one('res.users', string="Assigned Tailor", tracking=True)

    # Computed/related fields
    customer_phone = fields.Char(string="Customer Phone", related='customer_id.phone', readonly=True)
    customer_email = fields.Char(string="Customer Email", related='customer_id.email', readonly=True)

    # =========================
    # Constraints & computations
    # =========================
    @api.depends('total_amount', 'advance_paid')
    def _compute_balance(self):
        for order in self:
            order.balance_due = order.total_amount - order.advance_paid

    @api.constrains('advance_paid', 'total_amount')
    def _check_advance_amount(self):
        for order in self:
            if order.advance_paid < 0:
                raise ValidationError(_("Advance paid cannot be negative."))
            if order.advance_paid > order.total_amount:
                raise ValidationError(_("Advance paid cannot exceed total amount."))

    @api.constrains('chest_measurement', 'waist_measurement', 'hip_measurement')
    def _check_measurements(self):
        for order in self:
            if order.chest_measurement < 0 or order.waist_measurement < 0 or order.hip_measurement < 0:
                raise ValidationError(_("Measurements cannot be negative."))

    @api.model
    def create(self, vals):
        if vals.get('name', _('New')) == _('New'):
            vals['name'] = self.env['ir.sequence'].next_by_code('tailor.order') or _('New')
        return super(TailorOrder, self).create(vals)

    # =========================
    # Status update methods
    # =========================
    def _update_status(self, new_status):
        """Update status and trigger notifications"""
        old_status = self.status
        self.write({'status': new_status})
        
        # Send notifications for specific status changes
        self._send_status_notifications(old_status, new_status)

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
    # Portal & communication buttons
    # =========================
    def call_customer(self):
        self.ensure_one()
        if not self.customer_phone:
            raise UserError(_("No phone number available for customer."))
        return {'type': 'ir.actions.act_url', 'url': f'tel:{self.customer_phone}', 'target': 'self'}

    def email_customer(self):
        self.ensure_one()
        if not self.customer_email:
            raise UserError(_("No email available for customer."))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Compose Email'),
            'res_model': 'mail.compose.message',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_composition_mode': 'comment',
                'default_model': 'tailor.order',
                'default_res_id': self.id,
                'default_partner_ids': [(6, 0, [self.customer_id.id])],
                'default_subject': _('Regarding your order %s') % self.name,
            },
        }

    def _get_portal_url(self):
        """Generate portal URL for this order"""
        self.ensure_one()
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        return f"{base_url}/my/tailor/orders/{self.id}"

    def get_portal_url(self):
        """Action to open portal URL"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_url', 
            'url': self._get_portal_url(), 
            'target': 'new'
        }

    def action_send_test_email(self):
        """Test email button"""
        self.ensure_one()
        self._send_email_notification(self.status)
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Test Email Sent'),
                'message': _('A test email has been sent to %s') % self.customer_email,
                'type': 'success',
                'sticky': False,
            }
        }

    def action_send_test_sms(self):
        """Test SMS button"""
        self.ensure_one()
        self._send_sms_notification(self.status)
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Test SMS Sent'),
                'message': _('A test SMS would be sent to %s') % self.customer_phone,
                'type': 'info',
                'sticky': False,
            }
        }

    # =========================
    # Notification system
    # =========================
    def _send_status_notifications(self, old_status, new_status):
        """Send notifications when status changes"""
        self.ensure_one()
        
        # Log in chatter
        status_display = dict(self._fields['status'].selection).get(new_status)
        self.message_post(
            body=_("Status updated from %s to: %s") % (
                dict(self._fields['status'].selection).get(old_status, old_status),
                status_display
            ),
            subtype_xmlid='mail.mt_note'
        )
        
        # Send email notification
        if self.send_email_notifications and self.customer_email:
            self._send_email_notification(new_status)
        
        # Send SMS/WhatsApp notification
        if self.send_sms_notifications and self.customer_phone:
            self._send_sms_notification(new_status)

    def _send_email_notification(self, status):
        """Send email notification based on status"""
        self.ensure_one()
        
        # Map status to email template
        template_mapping = {
            'received': 'tailor_management.email_template_order_received',
            'measurement': 'tailor_management.email_template_measurement',
            'cutting': 'tailor_management.email_template_production',
            'sewing': 'tailor_management.email_template_production',
            'finishing': 'tailor_management.email_template_production',
            'quality_check': 'tailor_management.email_template_quality_check',
            'ready': 'tailor_management.email_template_ready',
            'delivered': 'tailor_management.email_template_delivered',
            'cancelled': 'tailor_management.email_template_cancelled',
        }
        
        template_xmlid = template_mapping.get(status)
        if not template_xmlid:
            _logger.info(f"No email template for status: {status}")
            return
        
        try:
            template = self.env.ref(template_xmlid)
            if template:
                template.send_mail(self.id, force_send=True, raise_exception=False)
                _logger.info(f"Email sent for order {self.name} - status: {status}")
            else:
                _logger.warning(f"Email template not found: {template_xmlid}")
        except Exception as e:
            _logger.error(f"Failed to send email for order {self.name}: {str(e)}")

    def _send_sms_notification(self, status):
        """Send SMS/WhatsApp notification based on status"""
        self.ensure_one()
        
        # SMS message templates
        sms_messages = {
            'received': _("Hello %s! Your order %s has been received. We'll contact you soon for measurements."),
            'measurement': _("Hi %s! Time to schedule measurements for order %s. Please call us."),
            'cutting': _("Hi %s! Your order %s is now in production (Cutting stage)."),
            'sewing': _("Hi %s! Your order %s is being sewn. We're making progress!"),
            'finishing': _("Hi %s! Your order %s is in finishing stage. Almost ready!"),
            'quality_check': _("Hi %s! Your order %s is undergoing quality check."),
            'ready': _("Great news %s! Your order %s is ready for pickup! Balance due: %.2f %s"),
            'delivered': _("Thank you %s! Order %s has been delivered. We hope you're satisfied!"),
            'cancelled': _("Hi %s, your order %s has been cancelled. Please contact us for details."),
        }
        
        message_template = sms_messages.get(status)
        if not message_template:
            _logger.info(f"No SMS template for status: {status}")
            return
        
        try:
            # Format message
            if status == 'ready':
                message = message_template % (
                    self.customer_id.name,
                    self.name,
                    self.balance_due,
                    self.currency_id.symbol
                )
            else:
                message = message_template % (self.customer_id.name, self.name)
            
            # Send SMS (this requires SMS module or WhatsApp integration)
            # For now, we'll just log it
            _logger.info(f"SMS would be sent to {self.customer_phone}: {message}")
            
            # If you have SMS module installed, uncomment:
            # self.env['sms.sms'].create({
            #     'number': self.customer_phone,
            #     'body': message,
            # })._send()
            
        except Exception as e:
            _logger.error(f"Failed to send SMS for order {self.name}: {str(e)}")

    # =========================
    # Scheduled Actions
    # =========================
    @api.model
    def _cron_send_delivery_reminders(self):
        """Cron job to send reminders for orders due today"""
        today = fields.Date.today()
        orders = self.search([
            ('delivery_date', '=', today),
            ('status', 'in', ['cutting', 'sewing', 'finishing', 'quality_check'])
        ])
        
        for order in orders:
            try:
                if order.send_email_notifications and order.customer_email:
                    template = self.env.ref('tailor_management.email_template_delivery_reminder')
                    template.send_mail(order.id, force_send=True, raise_exception=False)
                
                if order.send_sms_notifications and order.customer_phone:
                    message = _("Reminder: Order %s is scheduled for delivery today. We're working to complete it!") % order.name
                    _logger.info(f"Reminder SMS for {order.name}: {message}")
                    
            except Exception as e:
                _logger.error(f"Failed to send reminder for order {order.name}: {str(e)}")
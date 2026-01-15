from odoo import models, fields, api


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    # --- Tailoring Specific Fields ---
    fabric_type = fields.Char(string="Fabric Type")
    fabric_color = fields.Char(string="Fabric Color")
    garment_type = fields.Selection([
        ('suit', 'Suit'),
        ('shirt', 'Shirt'),
        ('trousers', 'Trousers'),
        ('dress', 'Dress')
    ], string="Garment Type")

    # --- Measurements (Auto-filled from Partner, but editable per order) ---
    measure_chest = fields.Float(string="Chest", related='partner_id.chest', readonly=False, store=True)
    measure_waist = fields.Float(string="Waist", related='partner_id.waist', readonly=False, store=True)
    measure_sleeve = fields.Float(string="Sleeve", related='partner_id.sleeve', readonly=False, store=True)
    measure_shoulder = fields.Float(string="Shoulder", related='partner_id.shoulder', readonly=False, store=True)

    # --- Automation Logic ---
    def action_confirm(self):
        """
        1. Confirms the Sale
        2. Automatically creates the Tailor Manufacturing Order
        """
        res = super(SaleOrder, self).action_confirm()

        for order in self:
            # Check if this is a tailoring order (e.g., has a garment type)
            if order.garment_type:
                self.env['tailor.order'].create({
                    'customer_id': order.partner_id.id,
                    'name': order.name ,
                    'garment_type': order.garment_type,
                    'fabric_type': order.fabric_type,
                    'color': order.fabric_color,
                    'chest_measurement': order.measure_chest,
                    'waist_measurement': order.measure_waist,
                    'sleeve_length': order.measure_sleeve,
                    'shoulder_width': order.measure_shoulder,
                    'delivery_date': order.commitment_date or fields.Date.add(fields.Date.today(), days=7),
                    'total_amount': order.amount_total,
                })

        return res
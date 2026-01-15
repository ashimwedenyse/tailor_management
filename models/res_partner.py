# -*- coding: utf-8 -*-
from odoo import models, fields


class ResPartner(models.Model):
    _inherit = 'res.partner'

    # --- Existing Field ---
    is_customer = fields.Boolean(
        string="Is a Customer",
        default=True
    )

    # --- NEW: Tailoring Measurements (Stored permanently on Customer) ---
    chest = fields.Float(string="Chest (cm)")
    waist = fields.Float(string="Waist (cm)")
    hip = fields.Float(string="Hip (cm)")
    shoulder = fields.Float(string="Shoulder (cm)")
    sleeve = fields.Float(string="Sleeve Length (cm)")
    armhole = fields.Float(string="Armhole (cm)")
    trouser_length = fields.Float(string="Trouser Length (cm)")

    # --- NEW: Preferences ---
    preferred_fit = fields.Selection([
        ('slim', 'Slim Fit'),
        ('regular', 'Regular Fit'),
        ('loose', 'Loose Fit')
    ], string="Preferred Fit", default='regular')
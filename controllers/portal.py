# -*- coding: utf-8 -*-
from odoo import http, _
from odoo.http import request
from odoo.addons.portal.controllers.portal import CustomerPortal, pager as portal_pager
from odoo.osv import expression


class TailorPortal(CustomerPortal):

    def _prepare_home_portal_values(self, counters):
        """Add the count of Tailor Orders to the main Portal Home page"""
        values = super(TailorPortal, self)._prepare_home_portal_values(counters)
        if 'tailor_order_count' in counters:
            partner = request.env.user.partner_id
            values['tailor_order_count'] = request.env['tailor.order'].search_count([
                ('customer_id', '=', partner.id)
            ])
        return values

    # 1. LIST VIEW: Shows all orders
    @http.route(['/my/tailor/orders', '/my/tailor/orders/page/<int:page>'], type='http', auth="user", website=True)
    def portal_my_orders(self, page=1, sortby=None, filterby=None, **kw):
        values = self._prepare_portal_layout_values()
        partner = request.env.user.partner_id
        TailorOrder = request.env['tailor.order']

        domain = [('customer_id', '=', partner.id)]

        # Count total for pagination
        order_count = TailorOrder.search_count(domain)

        # Pager configuration
        pager = portal_pager(
            url="/my/tailor/orders",
            total=order_count,
            page=page,
            step=10
        )

        # Get the orders
        orders = TailorOrder.search(domain, order='create_date desc', limit=10, offset=pager['offset'])

        values.update({
            'orders': orders,
            'page_name': 'tailor_orders',
            'pager': pager,
            'default_url': '/my/tailor/orders',
        })
        return request.render("tailor_management.portal_my_tailor_orders", values)

    # 2. DETAIL VIEW: Shows one specific order
    @http.route(['/my/tailor/orders/<int:order_id>'], type='http', auth="user", website=True)
    def portal_my_order_detail(self, order_id, access_token=None, **kw):
        # Securely fetch order (ensure user owns it)
        order_sudo = request.env['tailor.order'].sudo().search([
            ('id', '=', order_id),
            ('customer_id', '=', request.env.user.partner_id.id)
        ], limit=1)

        if not order_sudo:
            return request.redirect('/my/tailor/orders')

        values = {
            'order': order_sudo,
            'page_name': 'tailor_order',
        }
        return request.render("tailor_management.portal_my_tailor_order_detail", values)
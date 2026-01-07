# -*- coding: utf-8 -*-
from odoo import http
from odoo.http import request
from odoo.addons.portal.controllers.portal import CustomerPortal, pager as portal_pager

class TailorPortal(CustomerPortal):
    
    def _prepare_home_portal_values(self, counters):
        """Add tailor orders count to portal home"""
        values = super()._prepare_home_portal_values(counters)
        partner = request.env.user.partner_id
        
        if 'tailor_order_count' in counters:
            tailor_order_count = request.env['tailor.order'].search_count([
                ('customer_id', '=', partner.id)
            ])
            values['tailor_order_count'] = tailor_order_count
        
        return values
    
    @http.route(['/my/tailor/orders', '/my/tailor/orders/page/<int:page>'], 
                type='http', auth="user", website=True)
    def portal_my_orders(self, page=1, sortby=None, filterby=None, **kw):
        """Customer portal orders list page"""
        partner = request.env.user.partner_id
        TailorOrder = request.env['tailor.order']
        
        # Domain for current customer's orders
        domain = [('customer_id', '=', partner.id)]
        
        # Filters
        searchbar_filters = {
            'all': {'label': 'All', 'domain': []},
            'active': {'label': 'Active', 'domain': [('status', 'not in', ['delivered', 'cancelled'])]},
            'production': {'label': 'In Production', 'domain': [('status', 'in', ['cutting', 'sewing', 'finishing'])]},
            'ready': {'label': 'Ready', 'domain': [('status', '=', 'ready')]},
            'delivered': {'label': 'Delivered', 'domain': [('status', '=', 'delivered')]},
        }
        
        if not filterby:
            filterby = 'all'
        domain += searchbar_filters[filterby]['domain']
        
        # Sorting
        searchbar_sortings = {
            'date': {'label': 'Order Date', 'order': 'order_date desc'},
            'name': {'label': 'Reference', 'order': 'name'},
            'status': {'label': 'Status', 'order': 'status'},
        }
        
        if not sortby:
            sortby = 'date'
        order = searchbar_sortings[sortby]['order']
        
        # Count orders
        order_count = TailorOrder.search_count(domain)
        
        # Pager
        pager = portal_pager(
            url="/my/tailor/orders",
            url_args={'sortby': sortby, 'filterby': filterby},
            total=order_count,
            page=page,
            step=self._items_per_page
        )
        
        # Get orders
        orders = TailorOrder.search(domain, order=order, limit=self._items_per_page, offset=pager['offset'])
        
        # Order statistics
        all_orders = TailorOrder.search([('customer_id', '=', partner.id)])
        orders_in_production = all_orders.filtered(
            lambda o: o.status in ['cutting', 'sewing', 'finishing']
        )
        orders_ready = all_orders.filtered(lambda o: o.status == 'ready')
        orders_delivered = all_orders.filtered(lambda o: o.status == 'delivered')
        
        values = {
            'orders': orders,
            'page_name': 'tailor_orders',
            'pager': pager,
            'default_url': '/my/tailor/orders',
            'searchbar_sortings': searchbar_sortings,
            'searchbar_filters': searchbar_filters,
            'sortby': sortby,
            'filterby': filterby,
            'total_orders': len(all_orders),
            'orders_in_production': len(orders_in_production),
            'orders_ready': len(orders_ready),
            'orders_delivered': len(orders_delivered),
        }
        return request.render("tailor_management.portal_my_tailor_orders", values)
    
    @http.route(['/my/tailor/orders/<int:order_id>'], 
                type='http', auth="user", website=True)
    def portal_my_order_detail(self, order_id, access_token=None, **kw):
        """Customer portal order detail page"""
        try:
            order_sudo = self._document_check_access('tailor.order', order_id, access_token)
        except Exception:
            return request.redirect('/my')
        
        # Check if order belongs to current user
        if order_sudo.customer_id != request.env.user.partner_id:
            return request.redirect('/my')
        
        values = {
            'order': order_sudo,
            'page_name': 'tailor_order',
        }
        return request.render("tailor_management.portal_my_tailor_order_detail", values)
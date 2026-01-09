from odoo import models, api

class SaleOrder(models.Model):
    _inherit = 'sale.order'

    # 1. AL CREAR/GUARDAR LA VENTA
    @api.model_create_multi
    def create(self, vals_list):
        orders = super().create(vals_list)
        for order in orders:
            order._check_l10n_ar_tax_threshold_so()
        return orders

    def write(self, vals):
        res = super().write(vals)
        # Si cambian las líneas, recalculamos
        if 'order_line' in vals and not self.env.context.get('skip_check_tax_so'):
            for order in self:
                order._check_l10n_ar_tax_threshold_so()
        return res

    # 2. AL CONFIRMAR LA VENTA
    def action_confirm(self):
        # Limpiamos antes de confirmar para que el pedido quede prolijo
        for order in self:
            order._check_l10n_ar_tax_threshold_so()
        return super().action_confirm()

    # 3. AL CREAR FACTURAS (Lo que ya tenías, como refuerzo)
    def _create_invoices(self, grouped=False, final=False, date=None):
        moves = super()._create_invoices(grouped=grouped, final=final, date=date)
        for move in moves:
            # Llamamos al método de la factura (AccountMove)
            if hasattr(move, '_check_l10n_ar_tax_threshold'):
                move.with_context(check_move_validity=False)._check_l10n_ar_tax_threshold(manual_compute=True)
        return moves

    # LÓGICA ADAPTADA PARA VENTAS
    def _check_l10n_ar_tax_threshold_so(self):
        # Buscamos impuestos con umbral
        taxes_with_threshold = self.env['account.tax'].search([
            ('l10n_ar_non_taxable_amount', '>', 0),
            ('type_tax_use', '=', 'sale'),
            ('company_id', '=', self.company_id.id or self.env.company.id)
        ])
        if not taxes_with_threshold:
            return

        # Calcular Total Base (Sumando subtotales)
        # En ventas usamos 'price_subtotal' o calculamos si no está guardado aún
        total_base = sum(line.price_subtotal for line in self.order_line if not line.display_type)

        lines_to_update = []
        
        for line in self.order_line:
            if line.display_type: continue # Saltar notas/secciones
            
            current_taxes = line.tax_id
            new_taxes = current_taxes
            
            # Obtener impuestos originales del producto
            product = line.product_id
            if not product: continue
            
            base_product_taxes = product.taxes_id.filtered(lambda t: t.company_id == (self.company_id or self.env.company))
            
            # Mapeo fiscal
            if self.fiscal_position_id:
                target_product_taxes = self.fiscal_position_id.map_tax(base_product_taxes)
            else:
                target_product_taxes = base_product_taxes

            taxes_threshold_for_this_line = target_product_taxes & taxes_with_threshold

            for tax in taxes_with_threshold:
                threshold = tax.l10n_ar_non_taxable_amount
                
                # REGLA: Menor a 100k -> QUITAR
                if total_base < threshold:
                    if tax in new_taxes:
                        new_taxes -= tax
                # REGLA: Mayor a 100k -> PONER
                else:
                    if tax in taxes_threshold_for_this_line and tax not in new_taxes:
                        new_taxes |= tax
            
            if new_taxes != current_taxes:
                # En ventas usamos (6,0,ids) para actualizar Many2many
                lines_to_update.append((1, line.id, {'tax_id': [(6, 0, new_taxes.ids)]}))

        if lines_to_update and not self.env.context.get('skip_check_tax_so'):
            self.with_context(skip_check_tax_so=True).write({
                'order_line': lines_to_update
            })
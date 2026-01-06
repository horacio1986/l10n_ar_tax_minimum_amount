from odoo import models, api


class AccountMove(models.Model):
    _inherit = 'account.move'
    
    @api.onchange('invoice_line_ids', 'invoice_line_ids.price_subtotal')
    def _onchange_invoice_line_ids_minimum_tax(self):
        """
        Elimina o mantiene impuestos según el monto no imponible.
        Extiende la funcionalidad existente para facturas de venta.
        """
        if self.move_type not in ['out_invoice', 'out_refund']:
            return
        
        if self.state != 'draft':
            return
        
        # Calcular el total sin impuestos
        total_untaxed = sum(line.price_subtotal for line in self.invoice_line_ids)
        
        # Revisar cada línea de la factura
        for line in self.invoice_line_ids:
            taxes_to_remove = []
            
            # Revisar cada impuesto de la línea
            for tax in line.tax_ids:
                # Usar el campo nativo l10n_ar_non_taxable_amount
                if tax.l10n_ar_non_taxable_amount > 0:
                    # Si el total de la factura es menor al mínimo, marcar para eliminar
                    if total_untaxed < tax.l10n_ar_non_taxable_amount:
                        taxes_to_remove.append(tax.id)
            
            # Eliminar los impuestos que no cumplen el mínimo
            if taxes_to_remove:
                remaining_taxes = line.tax_ids.filtered(lambda t: t.id not in taxes_to_remove)
                line.tax_ids = remaining_taxes
    
    def _recompute_tax_lines(self, recompute_tax_base_amount=False):
        """
        Sobrescribe el método de recalculo de impuestos para aplicar
        la lógica del monto no imponible en facturas de venta.
        """
        # Aplicar la lógica del monto mínimo antes de recalcular
        for move in self:
            if move.move_type in ['out_invoice', 'out_refund'] and move.state == 'draft':
                total_untaxed = sum(line.price_subtotal for line in move.invoice_line_ids)
                
                for line in move.invoice_line_ids:
                    taxes_to_keep = line.tax_ids.filtered(
                        lambda t: t.l10n_ar_non_taxable_amount == 0 or total_untaxed >= t.l10n_ar_non_taxable_amount
                    )
                    if taxes_to_keep != line.tax_ids:
                        line.tax_ids = taxes_to_keep
        
        # Llamar al método original
        return super()._recompute_tax_lines(recompute_tax_base_amount)


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'
    
    @api.onchange('tax_ids')
    def _onchange_tax_ids_check_minimum(self):
        """
        Verifica al momento de agregar un impuesto si cumple con el monto no imponible.
        """
        if not self.move_id or self.move_id.move_type not in ['out_invoice', 'out_refund']:
            return
        
        total_untaxed = sum(line.price_subtotal for line in self.move_id.invoice_line_ids)
        
        for tax in self.tax_ids:
            if tax.l10n_ar_non_taxable_amount > 0 and total_untaxed < tax.l10n_ar_non_taxable_amount:
                # El impuesto no se aplicará porque no cumple el mínimo
                pass
from odoo import models, api


class AccountMove(models.Model):
    _inherit = 'account.move'
    
    def _recompute_tax_lines(self, recompute_tax_base_amount=False):
        """
        Sobrescribe el método de recalculo de impuestos para aplicar
        la lógica del monto no imponible en facturas de venta.
        """
        # Primero aplicar la lógica del monto mínimo
        for move in self:
            if move.move_type in ['out_invoice', 'out_refund'] and move.state == 'draft':
                total_untaxed = sum(line.price_subtotal for line in move.invoice_line_ids)
                
                for line in move.invoice_line_ids:
                    if not line.display_type:  # Solo líneas de producto
                        taxes_to_keep = []
                        for tax in line.tax_ids:
                            # Mantener el impuesto si no tiene monto mínimo o si cumple con él
                            if not tax.l10n_ar_non_taxable_amount or total_untaxed >= tax.l10n_ar_non_taxable_amount:
                                taxes_to_keep.append(tax.id)
                        
                        # Actualizar los impuestos si cambiaron
                        new_tax_ids = [(6, 0, taxes_to_keep)]
                        if line.tax_ids.ids != taxes_to_keep:
                            line.tax_ids = new_tax_ids
        
        # Llamar al método original
        return super()._recompute_tax_lines(recompute_tax_base_amount)
    
    def _inverse_amount_total(self):
        """
        Hook para recalcular cuando cambia el total
        """
        result = super()._inverse_amount_total()
        for move in self:
            if move.move_type in ['out_invoice', 'out_refund']:
                move._recompute_tax_lines()
        return result


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'
    
    @api.model_create_multi
    def create(self, vals_list):
        """
        Sobrescribe create para validar impuestos al crear líneas
        """
        lines = super().create(vals_list)
        
        # Agrupar líneas por factura
        moves_to_recompute = lines.move_id.filtered(
            lambda m: m.move_type in ['out_invoice', 'out_refund'] and m.state == 'draft'
        )
        
        for move in moves_to_recompute:
            move._recompute_tax_lines()
        
        return lines
    
    def write(self, vals):
        """
        Sobrescribe write para validar impuestos al modificar líneas
        """
        result = super().write(vals)
        
        # Si se modificaron precios o cantidades, recalcular
        if any(field in vals for field in ['price_unit', 'quantity', 'discount', 'tax_ids', 'product_id']):
            moves_to_recompute = self.move_id.filtered(
                lambda m: m.move_type in ['out_invoice', 'out_refund'] and m.state == 'draft'
            )
            
            for move in moves_to_recompute:
                move._recompute_tax_lines()
        
        return result
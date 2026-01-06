from odoo import models, api

class AccountMove(models.Model):
    _inherit = 'account.move'

    @api.model_create_multi
    def create(self, vals_list):
        # Creamos las facturas
        moves = super().create(vals_list)
        # Ejecutamos la validación de impuestos
        for move in moves:
            move._check_l10n_ar_tax_threshold()
        return moves

    def write(self, vals):
        res = super().write(vals)
        # Si se modificaron las líneas, re-evaluamos los impuestos
        if 'invoice_line_ids' in vals:
            for move in self:
                # Evitamos recursión infinita usando un flag en contexto
                if not self.env.context.get('skip_check_tax_threshold'):
                    move._check_l10n_ar_tax_threshold()
        return res

    def _check_l10n_ar_tax_threshold(self):
        """
        Verifica si la base total de la factura supera el umbral configurado
        en los impuestos y los agrega/quita dinámicamente.
        """
        for move in self:
            # Solo aplicamos en facturas de venta (y notas de crédito/débito)
            if move.move_type not in ('out_invoice', 'out_refund'):
                continue
            
            # 1. Calcular la Base Imponible Total (excluyendo impuestos)
            # Usamos price_subtotal que ya es la base sin impuestos
            total_base = sum(line.price_subtotal for line in move.invoice_line_ids)

            # 2. Buscar impuestos que tengan umbral configurado
            taxes_with_threshold = self.env['account.tax'].search([
                ('l10n_ar_non_taxable_amount', '>', 0),
                ('type_tax_use', '=', 'sale'),
                ('company_id', '=', move.company_id.id)
            ])
            
            if not taxes_with_threshold:
                continue

            lines_to_update = []

            # 3. Iterar líneas para ajustar
            for line in move.invoice_line_ids:
                if line.display_type not in ('product', False):
                    continue

                # Impuestos actuales en la línea
                current_taxes = line.tax_ids
                new_taxes = current_taxes

                # Obtenemos los impuestos que DEBERÍA tener el producto por defecto
                # Esto es crucial para saber si debemos "restaurar" el impuesto si superamos el monto
                product_taxes = line.product_id.taxes_id.filtered(lambda t: t.company_id == move.company_id)
                if line.account_id and not product_taxes:
                     # Fallback: si no hay producto, quizás mirar la cuenta contable o impuestos actuales
                     pass

                for tax in taxes_with_threshold:
                    threshold = tax.l10n_ar_non_taxable_amount

                    if total_base < threshold:
                        # CASO A: No llegamos al monto -> QUITAR impuesto
                        if tax in new_taxes:
                            new_taxes -= tax
                    else:
                        # CASO B: Superamos el monto -> AGREGAR impuesto
                        # Solo lo agregamos si el producto original lo lleva configurado
                        # o si ya estaba puesto manualmente (evitamos agregar impuestos a productos exentos)
                        if tax in product_taxes and tax not in new_taxes:
                            new_taxes |= tax

                # Solo escribimos si hubo cambios para optimizar rendimiento
                if new_taxes != current_taxes:
                    # Usamos el comando (6, 0, ids) para reemplazar many2many
                    lines_to_update.append((1, line.id, {'tax_ids': [(6, 0, new_taxes.ids)]}))

            # 4. Aplicar cambios masivamente
            if lines_to_update:
                # Usamos el contexto para evitar que este write dispare el método write del move otra vez
                move.with_context(skip_check_tax_threshold=True).write({
                    'invoice_line_ids': lines_to_update
                })
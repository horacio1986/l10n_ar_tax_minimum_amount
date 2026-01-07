from odoo import models, api, fields

class AccountMove(models.Model):
    _inherit = 'account.move'

    # -------------------------------------------------------------------------
    # 1. AL CREAR (DESDE VENTAS O MANUALMENTE)
    # -------------------------------------------------------------------------
    @api.model_create_multi
    def create(self, vals_list):
        # Dejamos que Odoo cree la factura estándar con todos sus defectos
        moves = super().create(vals_list)
        
        # Inmediatamente corregimos los impuestos
        for move in moves:
            move._check_l10n_ar_tax_threshold()
        return moves

    # -------------------------------------------------------------------------
    # 2. AL EDITAR O GUARDAR CAMBIOS
    # -------------------------------------------------------------------------
    def write(self, vals):
        res = super().write(vals)
        # Si cambiamos líneas, re-verificamos. 
        # Usamos 'skip_check...' para evitar bucles infinitos.
        if 'invoice_line_ids' in vals and not self.env.context.get('skip_check_tax_threshold'):
            for move in self:
                move._check_l10n_ar_tax_threshold()
        return res

    # -------------------------------------------------------------------------
    # 3. EN VIVO (VISUAL)
    # -------------------------------------------------------------------------
    @api.onchange('invoice_line_ids', 'fiscal_position_id')
    def _onchange_check_tax_threshold_ar(self):
        # Este método actualiza la vista mientras editas, antes de guardar
        self._check_l10n_ar_tax_threshold(manual_compute=False)

    # -------------------------------------------------------------------------
    # LÓGICA MAESTRA (BLINDADA)
    # -------------------------------------------------------------------------
    def _check_l10n_ar_tax_threshold(self, manual_compute=True):
        """
        Verifica el total y corrige impuestos.
        manual_compute=True: Calcula el total multiplicando precio*cantidad (Más seguro en 'create')
        manual_compute=False: Usa price_subtotal (Más rápido en 'onchange')
        """
        # Solo procesar facturas de venta (y notas de crédito/débito)
        if self.move_type not in ('out_invoice', 'out_refund'):
            return

        # Buscar impuestos con umbral configurado activo
        taxes_with_threshold = self.env['account.tax'].search([
            ('l10n_ar_non_taxable_amount', '>', 0),
            ('type_tax_use', '=', 'sale'),
            ('company_id', '=', self.company_id.id or self.env.company.id)
        ])
        
        if not taxes_with_threshold:
            return

        # --- PASO 1: CALCULAR BASE TOTAL ---
        total_base = 0.0
        
        # Filtramos líneas que no sean productos (notas, secciones)
        valid_lines = self.invoice_line_ids.filtered(lambda l: not l.display_type or l.display_type == 'product')

        if manual_compute:
            # CALCULO MANUAL: Vital cuando viene desde Ventas porque price_subtotal puede no estar listo
            for line in valid_lines:
                # Precio * Cantidad * (1 - Descuento)
                discount_factor = 1 - (line.discount or 0.0) / 100.0
                price = line.price_unit * line.quantity * discount_factor
                total_base += price
        else:
            # CALCULO ESTÁNDAR: Usamos el campo computado (para onchange)
            total_base = sum(line.price_subtotal for line in valid_lines)

        # --- PASO 2: APLICAR REGLAS ---
        lines_to_update = []
        
        for line in valid_lines:
            current_taxes = line.tax_ids
            new_taxes = current_taxes
            
            # Identificar qué impuestos lleva este producto por defecto
            product = line.product_id
            if not product:
                continue
                
            # Obtener impuestos base del producto para la compañía actual
            base_product_taxes = product.taxes_id.filtered(
                lambda t: t.company_id == (self.company_id or self.env.company)
            )
            
            # Aplicar mapeo de Posición Fiscal (Ej. Monotributista)
            if self.fiscal_position_id:
                target_product_taxes = self.fiscal_position_id.map_tax(base_product_taxes)
            else:
                target_product_taxes = base_product_taxes

            # Intersección: ¿Cuáles de los impuestos del producto son "con umbral"?
            taxes_threshold_for_this_line = target_product_taxes & taxes_with_threshold

            for tax in taxes_with_threshold:
                threshold = tax.l10n_ar_non_taxable_amount

                # REGLA 1: Total MENOR al umbral -> QUITAR
                if total_base < threshold:
                    if tax in new_taxes:
                        new_taxes -= tax
                
                # REGLA 2: Total MAYOR/IGUAL al umbral -> RESTAURAR
                # (Solo si el producto original lo llevaba)
                else:
                    if tax in taxes_threshold_for_this_line and tax not in new_taxes:
                        new_taxes |= tax

            # Si hubo cambios, preparamos la actualización
            if new_taxes != current_taxes:
                # Si estamos en memoria (onchange/newId), asignamos directo
                if isinstance(line.id, models.NewId) or not line.id:
                    line.tax_ids = new_taxes
                else:
                    # Si es un registro real (create/write), preparamos comando write masivo
                    lines_to_update.append((1, line.id, {'tax_ids': [(6, 0, new_taxes.ids)]}))

        # --- PASO 3: GUARDAR CAMBIOS MASIVOS ---
        if lines_to_update and not self.env.context.get('skip_check_tax_threshold'):
            self.with_context(skip_check_tax_threshold=True).write({
                'invoice_line_ids': lines_to_update
            })
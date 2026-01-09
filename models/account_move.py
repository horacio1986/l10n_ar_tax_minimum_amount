from odoo import models, api, fields

class AccountMove(models.Model):
    _inherit = 'account.move'

    # -------------------------------------------------------------------------
    # 1. SOBRESCRIBIMOS EL MÉTODO DE LA LOCALIZACIÓN ARGENTINA (EL CULPABLE)
    # -------------------------------------------------------------------------
    def _l10n_ar_recompute_fiscal_position_taxes(self):
        """
        Este método original de l10n_ar es el que agrega los impuestos a la fuerza
        basándose en la posición fiscal.
        Lo llamamos con super() para que haga su trabajo, e INMEDIATAMENTE después
        pasamos nuestra 'escoba' para quitar lo que no corresponda por monto.
        """
        # 1. Dejar que l10n_ar agregue las percepciones (el comportamiento original)
        super()._l10n_ar_recompute_fiscal_position_taxes()
        
        # 2. Corregir inmediatamente si el monto no supera el umbral
        for move in self:
            move._check_l10n_ar_tax_threshold(manual_compute=False)

    # -------------------------------------------------------------------------
    # 2. REFUERZO AL CONFIRMAR (POST)
    # -------------------------------------------------------------------------
    def _post(self, soft=True):
        # Primero dejamos que Odoo valide y timbre
        # Usamos el context freeze para evitar bucles si fuera necesario, 
        # aunque con el override de arriba ya debería bastar.
        res = super(AccountMove, self)._post(soft=soft)
        
        # Una última limpieza por si algún otro proceso (no l10n_ar) ensució algo
        for move in self:
            move._check_l10n_ar_tax_threshold(manual_compute=True)
            
        return res

    # -------------------------------------------------------------------------
    # 3. MÉTODOS ESTÁNDAR DE ODOO
    # -------------------------------------------------------------------------
    @api.model_create_multi
    def create(self, vals_list):
        moves = super().create(vals_list)
        for move in moves:
            move._check_l10n_ar_tax_threshold(manual_compute=True)
        return moves

    def write(self, vals):
        res = super().write(vals)
        if 'invoice_line_ids' in vals and not self.env.context.get('skip_check_tax_threshold'):
            for move in self:
                move._check_l10n_ar_tax_threshold()
        return res

    @api.onchange('invoice_line_ids', 'fiscal_position_id')
    def _onchange_check_tax_threshold_ar(self):
        self._check_l10n_ar_tax_threshold(manual_compute=False)

    # -------------------------------------------------------------------------
    # 4. LÓGICA DE LIMPIEZA
    # -------------------------------------------------------------------------
    def _check_l10n_ar_tax_threshold(self, manual_compute=True):
        if self.move_type not in ('out_invoice', 'out_refund'):
            return

        # Buscar impuestos con umbral
        taxes_with_threshold = self.env['account.tax'].search([
            ('l10n_ar_non_taxable_amount', '>', 0),
            ('type_tax_use', '=', 'sale'),
            ('company_id', '=', self.company_id.id or self.env.company.id)
        ])
        
        if not taxes_with_threshold:
            return

        # Calcular Base
        total_base = 0.0
        valid_lines = self.invoice_line_ids.filtered(lambda l: not l.display_type or l.display_type == 'product')

        if manual_compute:
            for line in valid_lines:
                discount_factor = 1 - (line.discount or 0.0) / 100.0
                price = line.price_unit * line.quantity * discount_factor
                total_base += price
        else:
            # Fallback a manual si subtotal es 0
            current_subtotal = sum(line.price_subtotal for line in valid_lines)
            if current_subtotal == 0 and valid_lines:
                 for line in valid_lines:
                    discount_factor = 1 - (line.discount or 0.0) / 100.0
                    total_base += line.price_unit * line.quantity * discount_factor
            else:
                total_base = current_subtotal

        # Aplicar reglas
        lines_to_update = []
        for line in valid_lines:
            current_taxes = line.tax_ids
            new_taxes = current_taxes
            
            product = line.product_id
            if not product: continue
                
            base_product_taxes = product.taxes_id.filtered(lambda t: t.company_id == (self.company_id or self.env.company))
            
            if self.fiscal_position_id:
                target_product_taxes = self.fiscal_position_id.map_tax(base_product_taxes)
            else:
                target_product_taxes = base_product_taxes

            taxes_threshold_for_this_line = target_product_taxes & taxes_with_threshold

            for tax in taxes_with_threshold:
                threshold = tax.l10n_ar_non_taxable_amount
                
                # REGLA: Menor al umbral -> QUITAR
                if total_base < threshold:
                    if tax in new_taxes:
                        new_taxes -= tax
                # REGLA: Mayor al umbral -> PONER
                else:
                    if tax in taxes_threshold_for_this_line and tax not in new_taxes:
                        new_taxes |= tax

            if new_taxes != current_taxes:
                if isinstance(line.id, models.NewId) or not line.id:
                    line.tax_ids = new_taxes
                else:
                    lines_to_update.append((1, line.id, {'tax_ids': [(6, 0, new_taxes.ids)]}))

        if lines_to_update and not self.env.context.get('skip_check_tax_threshold'):
            self.with_context(skip_check_tax_threshold=True).write({
                'invoice_line_ids': lines_to_update
            })
from odoo import models, fields, api


class AccountTax(models.Model):
    _inherit = 'account.tax'
    
    # Extender el campo existente para hacerlo visible también en ventas
    l10n_ar_non_taxable_amount = fields.Float(
        compute=False,  # Desactivar el compute para hacerlo editable siempre
        readonly=False,
        store=True,
    )
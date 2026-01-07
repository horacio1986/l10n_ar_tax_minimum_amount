from odoo import models, fields

class AccountTax(models.Model):
    _inherit = 'account.tax'
    
    l10n_ar_non_taxable_amount = fields.Float(
        string='Monto no imponible (Ventas)',
        default=0.0,
        help='Para ventas: El impuesto se aplicará SOLO si la base imponible total de la factura supera este monto.'
    )
from odoo import models, api

class SaleOrder(models.Model):
    _inherit = 'sale.order'

    def _create_invoices(self, grouped=False, final=False, date=None):
        """
        Sobrescribe la creación de facturas para aplicar la limpieza de impuestos
        COMO ÚLTIMO PASO, garantizando que anula cualquier re-cálculo de Odoo.
        """
        # 1. Dejar que Odoo cree las facturas y haga sus re-cálculos automáticos
        moves = super()._create_invoices(grouped=grouped, final=final, date=date)
        
        # 2. Iterar sobre las facturas creadas y limpiar "a la fuerza"
        for move in moves:
            # Forzamos el modo 'manual_compute=True' porque en este milisegundo 
            # exacto, a veces Odoo aún no ha guardado el 'price_subtotal' en base de datos.
            # Al poner manual_compute=True, calculamos (precio * cantidad) nosotros mismos.
            move.with_context(
                check_move_validity=False, # Evita validaciones bloqueantes
                skip_check_tax_threshold=False # Asegura que nuestro check se ejecute
            )._check_l10n_ar_tax_threshold(manual_compute=True)
            
        return moves
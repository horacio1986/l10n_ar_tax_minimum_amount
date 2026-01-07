{
    'name': 'Monto No Imponible para Impuestos de Venta',
    'version': '18.0.1.0.0',
    'category': 'Accounting/Localizations',
    'summary': 'Extiende el campo "Monto no imponible" para impuestos de venta',
    'description': """
        Este módulo extiende la funcionalidad del campo "Monto no imponible" 
        que existe para retenciones para que también funcione con impuestos de venta.
        
        El impuesto solo se aplicará si el total de la factura supera el monto configurado.
        
        Ideal para percepciones de IIBB, IVA u otros impuestos que tienen montos mínimos.
    """,
    'author': 'HDMSOFT',
    'developer': 'Horacio Montaño',
    'license': 'LGPL-3',
    'depends': [
        'account',
        'l10n_ar',  # Localización Argentina
        'l10n_ar_sale'
    ],
    'data': [
        'views/account_tax_views.xml',
    ],
    'installable': True,
    'auto_install': False,
    'application': False,
}
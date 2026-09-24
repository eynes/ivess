from odoo.tests import TransactionCase


class IvessAccountingSummaryTestCommon(TransactionCase):
    """Fixtures propias, sin pasar por ProductCommon.

    ProductCommon (base de AccountTestInvoicingCommon) crea productos de
    prueba genéricos que chocan con la customización de
    custom_ivess_product (exige una secuencia de "Nuevo" configurada en la
    categoría del producto). Como el asistente de cierre opera a nivel de
    account.move.line sin depender de productos ni de impuestos, alcanza
    con apuntes manuales balanceados sobre cuentas/diarios reales de la
    compañía.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        company = cls.env.company
        cls.currency = company.currency_id

        # Se crean las cuentas en vez de buscar unas preexistentes: esta
        # base de devel no tiene un plan de cuentas instalado.
        cls.receivable_account = cls.env["account.account"].create(
            {
                "code": "TEST.1.1.1",
                "name": "Deudores por Ventas - Test",
                "account_type": "asset_receivable",
                "reconcile": True,
            }
        )
        cls.revenue_account = cls.env["account.account"].create(
            {
                "code": "TEST.4.1.1",
                "name": "Ventas de Mercadería - Test",
                "account_type": "income",
            }
        )

        # Se crean ambos diarios en vez de buscar uno "de Ventas" existente:
        # esta base de datos de devel no tiene diarios type=sale/purchase
        # configurados, solo los específicos de la localización AR.
        cls.operational_journal = cls.env["account.journal"].create(
            {
                "name": "Diario Operativo - Test",
                "type": "general",
                "code": "TOPER",
                "company_id": company.id,
                "x_is_operational_journal": True,
                "due_date": "2020-01-01",
            }
        )
        cls.legal_journal = cls.env["account.journal"].create(
            {
                "name": "Diario de Refundición (Legal) - Test",
                "type": "general",
                "code": "TREFU",
                "company_id": company.id,
                "x_is_legal_journal": True,
                "due_date": "2020-01-01",
            }
        )
        cls.legal_debt_account = cls.receivable_account.copy(
            {
                "code": f"{cls.receivable_account.code}.LEGALTEST",
                "name": "Deudores por Ventas (Legal) - Test",
            }
        )
        cls.bridge_account = cls.env["account.account"].create(
            {
                "code": "TEST.1.1.1.PUENTE",
                "name": "Puente Cobrado en el Período - Test",
                "account_type": "asset_current",
            }
        )
        cls.receivable_account.x_legal_debt_account_id = cls.legal_debt_account
        cls.receivable_account.x_legal_bridge_account_id = cls.bridge_account

        cls.partner_a = cls.env["res.partner"].create({"name": "Cliente Test Alfa"})
        cls.partner_b = cls.env["res.partner"].create({"name": "Cliente Test Beta"})

    @classmethod
    def _create_receivable_move(cls, partner, amount, date, journal=None):
        """Crea y postea un apunte balanceado equivalente a una factura simple."""
        move = cls.env["account.move"].create(
            {
                "journal_id": (journal or cls.operational_journal).id,
                "date": date,
                "move_type": "entry",
                "line_ids": [
                    (
                        0,
                        0,
                        {
                            "account_id": cls.receivable_account.id,
                            "partner_id": partner.id,
                            "debit": amount,
                            "credit": 0.0,
                        },
                    ),
                    (
                        0,
                        0,
                        {
                            "account_id": cls.revenue_account.id,
                            "debit": 0.0,
                            "credit": amount,
                        },
                    ),
                ],
            }
        )
        move.action_post()
        return move

    def _receivable_line(self, move):
        return move.line_ids.filtered(
            lambda line: line.account_id == self.receivable_account
        )

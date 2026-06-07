from __future__ import annotations

import polars as pl

from projections.base_projector import BaseProjector


class FinancialProjector(BaseProjector):
    def project_invoices(self) -> None:
        invoices = self.read_events("InvoiceCreated")
        invoices = self.unpack_payload(invoices, [
            "invoice_id", "order_id", "customer_id", "amount", "due_date", "terms_days",
        ])
        invoices = invoices.with_columns(pl.col("amount").cast(pl.Float64))
        self.write(invoices, "invoices")

    def project_payments(self) -> None:
        captured = self.read_events("PaymentCaptured")
        captured = self.unpack_payload(captured, [
            "invoice_id", "customer_id", "amount", "payment_method",
        ])
        captured = captured.with_columns([
            pl.col("amount").cast(pl.Float64),
            pl.lit("paid").alias("status"),
        ])

        failed = self.read_events("PaymentFailed")
        failed = self.unpack_payload(failed, [
            "invoice_id", "customer_id", "amount", "attempt_number", "reason",
        ])
        failed = failed.with_columns([
            pl.col("amount").cast(pl.Float64),
            pl.lit("failed").alias("status"),
        ])

        payments = pl.concat([captured, failed], how="diagonal")
        self.write(payments, "payments")

    def project_credit_ledger(self) -> None:
        # Credit used = OrderCreated
        orders = self.read_events("OrderCreated")
        orders = self.unpack_payload(orders, ["customer_id", "total_value"])
        orders = orders.with_columns([
            pl.col("total_value").cast(pl.Float64).alias("amount"),
            pl.lit("debit").alias("transaction_type"),
        ])

        # Credit repaid = PaymentCaptured
        payments = self.read_events("PaymentCaptured")
        payments = self.unpack_payload(payments, ["customer_id", "amount"])
        payments = payments.with_columns([
            pl.col("amount").cast(pl.Float64),
            pl.lit("credit").alias("transaction_type"),
        ])

        # Write-offs
        writeoffs = self.read_events("CreditWrittenOff")
        writeoffs = self.unpack_payload(writeoffs, ["customer_id", "amount"])
        writeoffs = writeoffs.with_columns([
            pl.col("amount").cast(pl.Float64),
            pl.lit("writeoff").alias("transaction_type"),
        ])

        ledger = pl.concat([orders, payments, writeoffs], how="diagonal")
        ledger = (
            ledger
            .sort(["customer_id", "timestamp"])
            .with_columns(
                pl.when(pl.col("transaction_type") == "debit")
                .then(pl.col("amount"))
                .otherwise(-pl.col("amount"))
                .alias("signed_amount")
            )
            .with_columns(
                pl.col("signed_amount")
                .cum_sum()
                .over("customer_id")
                .alias("running_balance")
            )
        )
        self.write(ledger, "credit_ledger")

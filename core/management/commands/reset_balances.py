from decimal import Decimal
from uuid import UUID

from django.core.management.base import BaseCommand, CommandError
from django.db.models import Sum
from django.utils import timezone

from django.db import transaction
from core.models import Patient, Bill, Payment, User  # adjust app label if needed


class Command(BaseCommand):
    help = (
        "Zero out patient balances.\n"
        "- If balance > 0 (due): create Payments across oldest unpaid bills first.\n"
        "- If balance < 0 (credit): create an Adjustment bill to consume the credit.\n"
        "Dry-run by default. Use --commit to write changes."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--admin",
            help="Username to attribute created payments/bills to (optional).",
        )
        parser.add_argument(
            "--commit",
            action="store_true",
            help="Actually write changes (otherwise dry-run).",
        )
        parser.add_argument(
            "--verbose",
            action="store_true",
            help="Print detailed per-patient actions.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=None,
            help="Process only the first N patients (testing).",
        )
        parser.add_argument(
            "--patient",
            help="Limit to a single patient (UUID pk or file_number).",
        )

    def _resolve_patient(self, token: str):
        # Try UUID pk first
        try:
            _ = UUID(str(token))
            p = Patient.objects.filter(pk=token).first()
            if p:
                return p
        except Exception:
            pass
        # Fallback to file_number
        return Patient.objects.filter(file_number=token).first()

    def handle(self, *args, **opts):
        admin_user = None
        if opts["admin"]:
            try:
                admin_user = User.objects.get(username=opts["admin"])
            except User.DoesNotExist:
                raise CommandError(f"User '{opts['admin']}' not found.")

        # Build patient queryset
        if opts["patient"]:
            p = self._resolve_patient(opts["patient"])
            if not p:
                raise CommandError(f"Patient '{opts['patient']}' not found (UUID or file_number).")
            patients = Patient.objects.filter(pk=p.pk)
        else:
            patients = Patient.objects.all().order_by("created_at", "pk")
            if opts["limit"]:
                patients = patients[: opts["limit"]]

        dry_run = not opts["commit"]
        now_str = timezone.now().strftime("%Y-%m-%d %H:%M")

        touched = 0
        created_payments = 0
        created_adj_bills = 0

        # Only wrap in a single atomic block when actually writing
        ctx = transaction.atomic() if not dry_run else nullcontext()
        with ctx:
            for p in patients:
                billed = p.bills.aggregate(s=Sum("total_amount"))["s"] or Decimal("0")
                paid = Payment.objects.filter(bill__patient=p).aggregate(s=Sum("amount"))["s"] or Decimal("0")
                bal = billed - paid  # +ve = due, -ve = credit

                if bal == 0:
                    if opts["verbose"]:
                        self.stdout.write(f"[SKIP] {p} balance already 0")
                    continue

                touched += 1
                if opts["verbose"]:
                    self.stdout.write(f"[{p.id}] {p}  billed={billed}  paid={paid}  balance={bal}")

                if bal > 0:
                    # Clear dues by paying oldest unpaid bills
                    remaining = bal
                    bills = (
                        p.bills.annotate(paid_sum=Sum("payments__amount"))
                        .order_by("bill_date", "pk")
                    )

                    for b in bills:
                        b_paid = b.paid_sum or Decimal("0")
                        due = (b.total_amount or Decimal("0")) - b_paid
                        if due <= 0:
                            continue

                        take = min(remaining, due)
                        if take > 0:
                            if not dry_run:
                                Payment.objects.create(
                                    bill=b,
                                    amount=take,
                                    method="cash",
                                    received_by=admin_user,
                                )
                                # Keep Bill.paid_amount in sync if helper exists
                                if hasattr(b, "sync_paid_amount"):
                                    b.sync_paid_amount(save=True)

                            created_payments += 1
                            remaining -= take

                            if opts["verbose"]:
                                self.stdout.write(
                                    f"  + Payment {take} -> {b.bill_number} (remaining {remaining})"
                                )

                            if remaining <= 0:
                                break

                else:
                    # Consume credit with a one-shot Adjustment bill
                    credit = -bal
                    if not dry_run:
                        adj = Bill.objects.create(
                            patient=p,
                            bill_type="service",  # either type is fine for totals
                            subtotal=credit,
                            tax_amount=Decimal("0"),
                            discount_amount=Decimal("0"),
                            total_amount=credit,
                            remark=f"RESET_BALANCE consume credit @ {now_str}",
                            created_by=admin_user,
                        )
                        if hasattr(adj, "sync_paid_amount"):
                            adj.sync_paid_amount(save=True)

                    created_adj_bills += 1
                    if opts["verbose"]:
                        self.stdout.write(f"  + Adjustment bill {credit} to consume credit")

        # Summary
        mode = "DRY-RUN (no changes written)" if dry_run else "COMMITTED"
        self.stdout.write(
            self.style.SUCCESS(
                f"{mode}: patients_touched={touched}, payments_created={created_payments}, adjustment_bills_created={created_adj_bills}"
            )
        )

try:
    from contextlib import nullcontext
except ImportError:  # pragma: no cover
    class nullcontext:
        def __init__(self, enter_result=None):
            self.enter_result = enter_result
        def __enter__(self):
            return self.enter_result
        def __exit__(self, *excinfo):
            return False

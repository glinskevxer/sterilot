"""One object that opens the database and hands out the repositories.

Every command in the CLI wants two or three of them and none of them want to
know how the file is opened. Opening also migrates by default, because a
department that has to remember a separate upgrade step will not, and the first
sign of it will be a report that quietly misses a column.

An open that finds a database from a newer build refuses rather than migrating
forward, since this build does not know what those tables mean.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from sterilot.errors import IntegrityError
from sterilot.store.cart_repo import CartStore
from sterilot.store.catalog_repo import CatalogStore
from sterilot.store.container_repo import ContainerStore
from sterilot.store.cycle_repo import CycleStore, SpecResolver, standard_spec
from sterilot.store.db import Database
from sterilot.store.duty_repo import DutyStore
from sterilot.store.equipment_repo import EquipmentStore
from sterilot.store.indicator_repo import IndicatorStore
from sterilot.store.issue_repo import IssueStore
from sterilot.store.load_repo import LoadStore
from sterilot.store.loaner_repo import LoanerStore
from sterilot.store.maintenance_repo import MaintenanceStore
from sterilot.store.migrations import current_version, latest_version, migrate, problems
from sterilot.store.package_repo import PackageStore
from sterilot.store.quality_repo import QualityStore
from sterilot.store.repair_repo import RepairStore
from sterilot.store.schedule_repo import ScheduleStore
from sterilot.store.staff_repo import StaffStore
from sterilot.store.tray_repo import TrayStore
from sterilot.store.verification_repo import VerificationStore
from sterilot.store.washer_repo import WasherStore


@dataclass
class Store:
    """The whole record, opened once."""

    db: Database
    carts: CartStore
    catalog: CatalogStore
    containers: ContainerStore
    equipment: EquipmentStore
    duties: DutyStore
    trays: TrayStore
    washers: WasherStore
    verifications: VerificationStore
    cycles: CycleStore
    loads: LoadStore
    loaners: LoanerStore
    indicators: IndicatorStore
    issues: IssueStore
    quality: QualityStore
    maintenance: MaintenanceStore
    packages: PackageStore
    repairs: RepairStore
    schedule: ScheduleStore
    staff: StaffStore

    @classmethod
    def build(cls, db: Database, resolve_spec: SpecResolver = standard_spec) -> Store:
        cycles = CycleStore(db, resolve_spec)
        return cls(
            db=db,
            carts=CartStore(db),
            catalog=CatalogStore(db),
            containers=ContainerStore(db),
            equipment=EquipmentStore(db),
            duties=DutyStore(db),
            trays=TrayStore(db),
            washers=WasherStore(db),
            verifications=VerificationStore(db),
            cycles=cycles,
            loads=LoadStore(db, cycles),
            loaners=LoanerStore(db),
            indicators=IndicatorStore(db),
            issues=IssueStore(db),
            quality=QualityStore(db),
            maintenance=MaintenanceStore(db),
            packages=PackageStore(db),
            repairs=RepairStore(db),
            schedule=ScheduleStore(db),
            staff=StaffStore(db),
        )

    @classmethod
    def open(
        cls,
        path: Path | str,
        apply_migrations: bool = True,
        now: datetime | None = None,
        resolve_spec: SpecResolver = standard_spec,
    ) -> Store:
        db = Database.open(path)
        return cls._ready(db, apply_migrations, now, resolve_spec)

    @classmethod
    def in_memory(cls, resolve_spec: SpecResolver = standard_spec) -> Store:
        return cls._ready(Database.in_memory(), True, None, resolve_spec)

    @classmethod
    def _ready(
        cls,
        db: Database,
        apply_migrations: bool,
        now: datetime | None,
        resolve_spec: SpecResolver,
    ) -> Store:
        trouble = problems(db)
        if trouble:
            db.close()
            raise IntegrityError("the schema history does not add up", detail="; ".join(trouble))
        if apply_migrations:
            migrate(db, now)
        return cls.build(db, resolve_spec)

    @property
    def version(self) -> int:
        return current_version(self.db)

    @property
    def up_to_date(self) -> bool:
        return self.version == latest_version()

    def health(self) -> tuple[str, ...]:
        """Everything wrong with the file, before anybody trusts a report off it."""
        found: list[str] = list(problems(self.db))
        if not self.up_to_date:
            found.append(
                f"the database is at version {self.version}, this build wants {latest_version()}"
            )
            return tuple(found)
        found.extend(self.db.integrity_problems())
        if not self.quality.audit_trail().intact():
            found.append("the audit trail has a break in it")
        return tuple(found)

    def close(self) -> None:
        self.db.close()

    def __enter__(self) -> Store:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

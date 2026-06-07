from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import simpy
    from faker import Faker
    from store.event_store import DuckDBEventStore
    from store.shared_state import SharedSimulationState


class BootstrapProcess:
    """Runs at env.time=0 to generate historical events and spawn ongoing processes."""

    def __init__(
        self,
        env: "simpy.Environment",
        state: "SharedSimulationState",
        store: "DuckDBEventStore",
        config: dict,
        fake: "Faker",
    ) -> None:
        self.env = env
        self.state = state
        self.store = store
        self.config = config
        self.fake = fake

    def run(self):
        # Generate historical events for all initial customers
        from generators.bootstrap_engine import BootstrapEngine
        bootstrap = BootstrapEngine(
            customers=self.state.customers,
            skus=self.state.skus,
            store=self.store,
            config=self.config,
            fake=self.fake,
        )
        bootstrap.generate_history()
        self.store.flush()  # Flush bootstrap events before simulation starts

        # Spawn ongoing processes for all initial customers
        from processes.customer_order_process import CustomerOrderProcess
        from processes.customer_lifecycle_process import CustomerLifecycleProcess
        from processes.app_session_process import AppSessionProcess
        from processes.rep_visit_process import RepVisitProcess
        from processes.inventory_monitor_process import InventoryMonitorProcess

        for customer in self.state.customers.values():
            self.env.process(CustomerOrderProcess(
                self.env, customer, self.state, self.store, self.config
            ).run())
            self.env.process(CustomerLifecycleProcess(
                self.env, customer, self.state, self.store, self.config
            ).run())
            if customer.digital_active:
                self.env.process(AppSessionProcess(
                    self.env, customer, self.state, self.store, self.config
                ).run())

        for rep in self.state.reps.values():
            self.env.process(RepVisitProcess(
                self.env, rep, self.state, self.store, self.config
            ).run())

        for inv in self.state.skus.values():
            self.env.process(InventoryMonitorProcess(
                self.env, inv, self.state, self.store, self.config
            ).run())

        yield self.env.timeout(0)  # Required: yield at least once

from linuxautomaton import sp, sv


class IrqStateProvider(sp.StateProvider):
    def __init__(self, state):
        self.state = state
        self.irq = state.interrupts
        self.cpus = state.cpus
        self.tids = state.tids
        self.irq["hard_count"] = 0
        self.irq["soft_count"] = 0
        self.irq["hard-per-cpu"] = {}
        self.irq["soft-per-cpu"] = {}
        self.irq["raise-per-cpu"] = {}
        self.irq["names"] = {}
        self.irq["hard-irqs"] = {}
        self.irq["soft-irqs"] = {}
        self.irq["raise-latency"] = {}
        self.irq["irq-list"] = []
        cbs = {
            'irq_handler_entry': self._process_irq_handler_entry,
            'irq_handler_exit': self._process_irq_handler_exit,
            'softirq_entry': self._process_softirq_entry,
            'softirq_exit': self._process_softirq_exit,
            'softirq_raise': self._process_softirq_raise,
        }
        self._register_cbs(cbs)

    def process_event(self, ev):
        self._process_event_cb(ev)

    def init_irq(self):
        irq = {}
        irq["list"] = []
        irq["max"] = 0
        irq["min"] = -1
        irq["count"] = 0
        irq["total"] = 0
        irq["raise_max"] = 0
        irq["raise_min"] = -1
        irq["raise_count"] = 0
        irq["raise_total"] = 0
        return irq

    def entry(self, event, irqclass, idfield):
        cpu_id = event["cpu_id"]
        i = sv.IRQ()
        i.irqclass = irqclass
        i.start_ts = event.timestamp
        i.cpu_id = cpu_id
        i.nr = event[idfield]
        return i

    def _process_irq_handler_entry(self, event):
        cpu_id = event["cpu_id"]
        self.irq["names"][event["irq"]] = event["name"]
        self.irq["hard_count"] += 1
        i = self.entry(event, sv.IRQ.HARD_IRQ, "irq")
        self.irq["hard-per-cpu"][cpu_id] = i

    def _process_softirq_entry(self, event):
        cpu_id = event["cpu_id"]
        self.irq["soft_count"] += 1
        i = self.entry(event, sv.IRQ.SOFT_IRQ, "vec")
        self.irq["soft-per-cpu"][cpu_id] = i
        if cpu_id in self.irq["raise-per-cpu"].keys() and \
                self.irq["raise-per-cpu"][cpu_id] is not None and \
                self.irq["raise-per-cpu"][cpu_id][1] == event["vec"]:
                    i.raise_ts = self.irq["raise-per-cpu"][cpu_id][0]
                    self.irq["raise-per-cpu"][cpu_id] = None

    def compute_stats(self, irq_entry, i):
        duration = i.stop_ts - i.start_ts
        if duration > irq_entry["max"]:
            irq_entry["max"] = duration
        if irq_entry["min"] == -1 or duration < irq_entry["min"]:
            irq_entry["min"] = duration
        irq_entry["count"] += 1
        irq_entry["total"] += duration
        # compute raise latency if applicable
        if i.raise_ts == -1:
            return True
        latency = i.start_ts - i.raise_ts
        if latency > irq_entry["raise_max"]:
            irq_entry["raise_max"] = latency
        if irq_entry["raise_min"] == -1 or latency < irq_entry["raise_min"]:
            irq_entry["raise_min"] = latency
        irq_entry["raise_count"] += 1
        irq_entry["raise_total"] += latency
        return True

    def exit(self, event, idfield, per_cpu_key, irq_type):
        cpu_id = event["cpu_id"]
        if cpu_id not in self.irq[per_cpu_key].keys() or \
                self.irq[per_cpu_key][cpu_id] is None:
                    return
        i = self.irq[per_cpu_key][cpu_id]
        if i.nr != event[idfield]:
            self.irq[per_cpu_key][cpu_id] = None
            return
        i.stop_ts = event.timestamp
        if not i.nr in self.irq[irq_type].keys():
            self.irq[irq_type][i.nr] = self.init_irq()

        # filter out max/min
        duration = i.stop_ts - i.start_ts
        if hasattr(self.state, "max") and self.state.max is not None and \
                duration > self.state.max * 1000:
            return False
        if hasattr(self.state, "min") and self.state.min is not None and \
                duration < self.state.min * 1000:
            return False
        self.irq[irq_type][i.nr]["list"].append(i)
        self.compute_stats(self.irq[irq_type][i.nr], i)
        self.irq["irq-list"].append(i)
        return i

    def _process_irq_handler_exit(self, event):
        i = self.exit(event, "irq", "hard-per-cpu", "hard-irqs")
        if not i:
            return
        i.ret = event["ret"]

    def _process_softirq_exit(self, event):
        self.exit(event, "vec", "soft-per-cpu", "soft-irqs")

    def _process_softirq_raise(self, event):
        cpu_id = event["cpu_id"]
        self.irq["raise-per-cpu"][cpu_id] = ((event.timestamp, event["vec"]))

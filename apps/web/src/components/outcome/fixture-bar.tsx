"use client";

import { FlaskConical } from "lucide-react";
import { useEffect, useState } from "react";
import { GLOBAL_SCENARIOS, type GlobalScenario, getGlobalScenario, setGlobalScenario } from "@/lib/fixtures/transport";

/** Development-only control. Present only when the app runs on the fixture transport. */
export function FixtureBar() {
  const [scenario, setScenario] = useState<GlobalScenario>("healthy");
  useEffect(() => setScenario(getGlobalScenario()), []);

  return (
    <footer className="sticky bottom-0 z-30 border-t border-fixture/30 bg-shell">
      <div className="flex h-9 items-center gap-3 px-5 text-2xs">
        <FlaskConical aria-hidden className="size-3.5 text-fixture" />
        <span className="font-medium text-fixture">Fixture mode.</span>
        <span className="text-muted-foreground">
          All data on screen is synthetic and labeled FIXTURE. Nothing here counts as live execution.
        </span>
        <label className="ml-auto flex items-center gap-2 text-muted-foreground">
          Scenario
          <select
            value={scenario}
            onChange={(event) => {
              const next = event.target.value as GlobalScenario;
              setGlobalScenario(next);
              setScenario(next);
              window.location.reload();
            }}
            className="h-6 rounded-sm border border-input bg-raised px-1.5 text-2xs text-foreground"
          >
            {Object.entries(GLOBAL_SCENARIOS).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </label>
      </div>
    </footer>
  );
}

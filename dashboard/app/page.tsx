import snapshot from './data/status.json';

const pct = (value: number) => `${(100 * value).toFixed(1)}%`;
const fixed = (value: number, digits = 3) => value.toFixed(digits);

const hypotheses = [
  {
    id: 'H1',
    status: 'Not supported',
    endpoint: 'Prediction superiority',
    result: `Holm p ${fixed(snapshot.hypotheses.H1.holm_adjusted_pvalue, 4)}`,
    detail: `Model − temporal absolute error ${fixed(snapshot.hypotheses.H1.estimate_and_ci.estimate)}; 95% block-bootstrap CI ${fixed(snapshot.hypotheses.H1.estimate_and_ci.ci95[0])} to ${fixed(snapshot.hypotheses.H1.estimate_and_ci.ci95[1])}. The adjusted significance gate failed.`,
  },
  {
    id: 'H2',
    status: 'Not supported',
    endpoint: 'Selective safety',
    result: `Coverage ${pct(snapshot.hypotheses.H2.coverage)}`,
    detail: `Selective harm was lower, but coverage was 3/14 versus the preregistered 50% minimum and Holm p was ${fixed(snapshot.hypotheses.H2.holm_adjusted_pvalue, 4)}.`,
  },
  {
    id: 'H3',
    status: 'Gated—not run',
    endpoint: 'Operational value',
    result: 'No confirmatory test',
    detail: 'The protocol allows H3 only if H1 and H2 pass. They did not, so no operational-value claim was tested or inferred.',
  },
];

const benchmarkRows = [
  ['Deterministic rule', snapshot.benchmark.test_mae.deterministic_rule, 'Winner'],
  ['Action-conditional ridge', snapshot.benchmark.test_mae.action_conditional_ridge, 'No promotion'],
  ['Temporal persistence', snapshot.benchmark.test_mae.temporal_persistence, 'Comparator'],
] as const;

const evidenceStages = [
  ['Fixture', 'Software contracts and QA', 'complete'],
  ['Simulated', 'UERANSIM radio path', 'complete'],
  ['Sandbox-measured', '132 isolated intervention units', 'complete'],
  ['Hardware-measured', 'Identified private-5G hardware', 'pending'],
  ['Operator-validated', 'Independent operator trial', 'pending'],
] as const;

export default function Home() {
  return (
    <main className="min-h-screen bg-[#07111f] text-[#edf5f5]">
      <div className="mx-auto max-w-[1440px] px-5 pb-16 pt-6 sm:px-10 lg:px-14">
        <header className="flex items-center justify-between border-b border-white/10 pb-5">
          <div className="flex items-center gap-3">
            <span className="grid h-9 w-9 place-items-center rounded-full border border-[#5ce1e6]/50 bg-[#5ce1e6]/10 font-mono text-xs font-bold text-[#5ce1e6]">ST</span>
            <div>
              <p className="text-sm font-semibold tracking-[0.08em]">SafeTwin-5G</p>
              <p className="text-[10px] uppercase tracking-[0.2em] text-[#8da2b6]">Trustworthy autonomous networks</p>
            </div>
          </div>
          <div className="flex items-center gap-2 rounded-full border border-[#b8f34a]/25 bg-[#b8f34a]/[0.06] px-3 py-2 text-[11px] font-medium text-[#c9f879]">
            <span className="h-1.5 w-1.5 rounded-full bg-[#b8f34a] shadow-[0_0_12px_#b8f34a]" />
            Live actuation locked
          </div>
        </header>

        <section className="grid gap-8 border-b border-white/10 py-12 lg:grid-cols-[1.25fr_0.75fr] lg:py-16">
          <div>
            <p className="mb-5 font-mono text-xs uppercase tracking-[0.24em] text-[#5ce1e6]">Phase 6 decision · v1</p>
            <h1 className="max-w-4xl text-5xl font-semibold leading-[0.98] tracking-[-0.055em] sm:text-7xl">
              The baseline wins. <span className="text-[#b8f34a]">Safety holds.</span>
            </h1>
            <p className="mt-7 max-w-2xl text-base leading-7 text-[#9eb0c1] sm:text-lg">
              The expanded sandbox study is complete. Its learned twin did not clear the preregistered promotion gates, so the result is a scientifically complete no-go—not an unfinished experiment.
            </p>
          </div>

          <aside className="self-end rounded-[28px] border border-[#ffbf69]/25 bg-[#ffbf69]/[0.06] p-6 sm:p-8">
            <div className="flex items-start justify-between gap-4">
              <div>
                <p className="font-mono text-[11px] uppercase tracking-[0.18em] text-[#e9b567]">Model promotion</p>
                <p className="mt-3 text-5xl font-semibold tracking-[-0.05em] text-[#ffd08b]">NO-GO</p>
              </div>
              <span className="rounded-full border border-[#ffbf69]/30 px-3 py-1 font-mono text-[10px] uppercase tracking-[0.12em] text-[#ffd08b]">Fail closed</span>
            </div>
            <dl className="mt-8 grid grid-cols-2 gap-5 border-t border-[#ffbf69]/15 pt-5">
              <div><dt className="text-xs text-[#9eb0c1]">Offline eligible</dt><dd className="mt-1 text-2xl font-semibold">{snapshot.proposal_audit.eligible_count} / {snapshot.proposal_audit.proposal_count}</dd></div>
              <div><dt className="text-xs text-[#9eb0c1]">Model actions</dt><dd className="mt-1 text-2xl font-semibold">{snapshot.safety_lock.model_actions_applied}</dd></div>
            </dl>
          </aside>
        </section>

        <section className="grid grid-cols-2 gap-3 py-8 lg:grid-cols-4">
          {[
            ['Study units', snapshot.dataset.record_count],
            ['Telemetry samples', snapshot.dataset.telemetry_sample_count.toLocaleString()],
            ['Complete blocks', snapshot.dataset.assignment_block_count],
            ['Observed harmful actions', snapshot.dataset.harmful_action_count],
          ].map(([label, value]) => (
            <div key={label} className="rounded-2xl border border-white/[0.08] bg-white/[0.025] p-5">
              <p className="font-mono text-[10px] uppercase tracking-[0.15em] text-[#778da2]">{label}</p>
              <p className="mt-3 text-3xl font-semibold tracking-[-0.04em]">{value}</p>
            </div>
          ))}
        </section>

        <section className="border-t border-white/10 py-10">
          <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
            <div>
              <p className="font-mono text-[11px] uppercase tracking-[0.2em] text-[#5ce1e6]">Confirmatory gates</p>
              <h2 className="mt-2 text-2xl font-semibold tracking-[-0.03em]">Negative findings are final findings.</h2>
            </div>
            <p className="max-w-lg text-sm leading-6 text-[#8da2b6]">H1 and H2 missed preregistered gates after multiplicity correction. H3 therefore stayed gated, exactly as specified before analysis.</p>
          </div>
          <div className="grid gap-4 lg:grid-cols-3">
            {hypotheses.map((item) => (
              <article key={item.id} className="rounded-3xl border border-white/10 bg-white/[0.035] p-6">
                <div className="flex items-start justify-between gap-4">
                  <span className="font-mono text-sm font-bold text-[#5ce1e6]">{item.id}</span>
                  <span className="rounded-full border border-white/10 px-2.5 py-1 text-[10px] uppercase tracking-[0.12em] text-[#aab9c7]">{item.status}</span>
                </div>
                <p className="mt-8 text-xs uppercase tracking-[0.15em] text-[#778da2]">{item.endpoint}</p>
                <p className="mt-2 text-2xl font-semibold tracking-[-0.025em]">{item.result}</p>
                <p className="mt-4 text-sm leading-6 text-[#91a5b7]">{item.detail}</p>
              </article>
            ))}
          </div>
        </section>

        <section className="grid gap-8 border-t border-white/10 py-10 lg:grid-cols-[0.85fr_1.15fr]">
          <div>
            <p className="font-mono text-[11px] uppercase tracking-[0.2em] text-[#5ce1e6]">Locked test benchmark</p>
            <h2 className="mt-2 text-2xl font-semibold tracking-[-0.03em]">Simple rule beats the learned twin.</h2>
            <p className="mt-4 max-w-md text-sm leading-6 text-[#8da2b6]">MAE on {snapshot.benchmark.test_n} held-out units. The 90% conformal interval is finite at calibration n={snapshot.benchmark.conformal.calibration_n}; empirical test coverage is {pct(snapshot.benchmark.test_empirical_coverage.coverage)}.</p>
          </div>
          <div className="overflow-hidden rounded-3xl border border-white/10">
            <div className="grid grid-cols-[1fr_0.55fr_0.6fr] gap-4 border-b border-white/10 bg-white/[0.04] px-5 py-3 font-mono text-[9px] uppercase tracking-[0.14em] text-[#60768a]">
              <span>Method</span><span>Test MAE</span><span>Decision</span>
            </div>
            {benchmarkRows.map(([name, mae, decision]) => (
              <div key={name} className="grid grid-cols-[1fr_0.55fr_0.6fr] gap-4 border-b border-white/[0.07] px-5 py-5 last:border-b-0">
                <span className="text-sm">{name}</span>
                <span className="font-mono text-sm text-[#5ce1e6]">{fixed(mae)}</span>
                <span className="text-xs text-[#8da2b6]">{decision}</span>
              </div>
            ))}
          </div>
        </section>

        <section className="border-t border-white/10 py-10">
          <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
            <div>
              <p className="font-mono text-[11px] uppercase tracking-[0.2em] text-[#5ce1e6]">Proposal audit</p>
              <h2 className="mt-2 text-2xl font-semibold tracking-[-0.03em]">No model-selected action was executed.</h2>
            </div>
            <div className="flex gap-2 font-mono text-[10px]">
              <a className="rounded-full border border-white/10 px-3 py-2 text-[#8da2b6] hover:border-[#5ce1e6]/40 hover:text-[#5ce1e6]" href="/api/status">GET /api/status</a>
              <a className="rounded-full border border-white/10 px-3 py-2 text-[#8da2b6] hover:border-[#5ce1e6]/40 hover:text-[#5ce1e6]" href="/api/proposals">GET /api/proposals</a>
            </div>
          </div>
          <p className="mb-5 max-w-3xl text-sm leading-6 text-[#8da2b6]">These 14 rows are locked-test counterfactual evaluations. Historical experimental actions were separately approved and rolled back during data collection; they are not model executions.</p>
          <div className="overflow-hidden rounded-3xl border border-white/10">
            <div className="hidden grid-cols-[0.7fr_1.1fr_1.2fr_0.75fr] gap-4 border-b border-white/10 bg-white/[0.04] px-5 py-3 font-mono text-[9px] uppercase tracking-[0.14em] text-[#60768a] md:grid">
              <span>Split / fault</span><span>Candidate action</span><span>Gate reason</span><span>Offline decision</span>
            </div>
            {snapshot.proposal_audit.records.map((record) => (
              <article key={record.record_id} className="grid gap-3 border-b border-white/[0.07] px-5 py-4 last:border-b-0 md:grid-cols-[0.7fr_1.1fr_1.2fr_0.75fr] md:items-center md:gap-4">
                <div>
                  <p className="font-mono text-[9px] uppercase tracking-[0.14em] text-[#5ce1e6]">{record.split}</p>
                  <p className="mt-1 text-xs text-[#aab9c7]">{record.fault_type.replaceAll('_', ' ')}</p>
                </div>
                <div>
                  <p className="font-mono text-xs text-[#edf5f5]">{record.action_kind.replaceAll('_', ' ')}</p>
                  <p className="mt-1 text-[10px] text-[#60768a]">{record.action_arm.replaceAll('_', ' ')}</p>
                </div>
                <p className="text-xs leading-5 text-[#8da2b6]">{record.reasons.join(' · ')}</p>
                <div>
                  <span className={`rounded-full border px-2.5 py-1 font-mono text-[9px] uppercase tracking-[0.1em] ${record.decision.startsWith('eligible') ? 'border-[#b8f34a]/30 bg-[#b8f34a]/[0.06] text-[#c9f879]' : 'border-[#ffbf69]/25 bg-[#ffbf69]/[0.05] text-[#ffd08b]'}`}>{record.decision}</span>
                  <p className="mt-2 font-mono text-[9px] text-[#60768a]">{record.model_execution_status}</p>
                </div>
              </article>
            ))}
          </div>
        </section>

        <section className="grid gap-6 border-t border-white/10 pt-10 lg:grid-cols-[0.9fr_1.1fr]">
          <div>
            <p className="font-mono text-[11px] uppercase tracking-[0.2em] text-[#5ce1e6]">Evidence ladder</p>
            <h2 className="mt-2 text-2xl font-semibold tracking-[-0.03em]">Claims stop where measurement stops.</h2>
            <p className="mt-4 max-w-md text-sm leading-6 text-[#8da2b6]">Sandbox outcomes and simulated radio behavior do not establish hardware or operator performance.</p>
          </div>
          <ol className="space-y-2">
            {evidenceStages.map(([label, description, status], index) => (
              <li key={label} className="grid grid-cols-[34px_1fr_auto] items-center gap-3 rounded-2xl border border-white/[0.07] bg-white/[0.025] px-4 py-3">
                <span className={`grid h-7 w-7 place-items-center rounded-full font-mono text-[10px] ${status === 'complete' ? 'bg-[#5ce1e6]/15 text-[#5ce1e6]' : 'bg-white/[0.06] text-[#60768a]'}`}>{index + 1}</span>
                <div><p className="text-sm font-medium">{label}</p><p className="text-xs text-[#778da2]">{description}</p></div>
                <span className={`font-mono text-[9px] uppercase tracking-[0.12em] ${status === 'pending' ? 'text-[#60768a]' : 'text-[#b8f34a]'}`}>{status}</span>
              </li>
            ))}
          </ol>
        </section>

        <footer className="mt-12 flex flex-col gap-3 border-t border-white/10 pt-5 font-mono text-[10px] text-[#60768a] sm:flex-row sm:items-center sm:justify-between">
          <p>Source: {snapshot.source_run_id}</p>
          <p>Report SHA-256 · {snapshot.source_sha256.benchmark_report.slice(0, 12)}…</p>
        </footer>
      </div>
    </main>
  );
}

import snapshot from './data/status.json';

const hypotheses = [
  {
    id: 'H1', status: 'Not supported', endpoint: 'Effect estimation', result: 'Rule MAE 3.333',
    detail: 'The deterministic runbook remains the held-out winner. Alternative-action ATE is not identified.',
  },
  {
    id: 'H2', status: 'Not supported', endpoint: 'Selective safety', result: 'Coverage 0.000',
    detail: 'All six held-out proposals abstained. Selective harm and risk-coverage AUC remain undefined.',
  },
  {
    id: 'H3', status: 'Not tested', endpoint: 'Operational value', result: 'MTTR undefined',
    detail: 'No continuous SLA window or twin-assisted comparative sandbox policy is available yet.',
  },
];

const evidenceStages = [
  ['Fixture', 'Contract and software checks', 'complete'],
  ['Simulated', 'UERANSIM radio', 'complete'],
  ['Sandbox-measured', 'Fault, action and rollback', 'current'],
  ['Hardware-measured', 'Private-5G hardware', 'pending'],
  ['Operator-validated', 'Independent trial', 'pending'],
];

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
            <p className="mb-5 font-mono text-xs uppercase tracking-[0.24em] text-[#5ce1e6]">Benchmark decision · v0</p>
            <h1 className="max-w-4xl text-5xl font-semibold leading-[0.98] tracking-[-0.055em] sm:text-7xl">
              Evidence before <span className="text-[#b8f34a]">autonomy.</span>
            </h1>
            <p className="mt-7 max-w-2xl text-base leading-7 text-[#9eb0c1] sm:text-lg">
              A causal, uncertainty-aware network twin for safe private-5G/6G operations. Current results support continued sandbox research—not model promotion.
            </p>
          </div>

          <aside className="self-end rounded-[28px] border border-[#ffbf69]/25 bg-[#ffbf69]/[0.06] p-6 sm:p-8">
            <div className="flex items-start justify-between gap-4">
              <div>
                <p className="font-mono text-[11px] uppercase tracking-[0.18em] text-[#e9b567]">Promotion gate</p>
                <p className="mt-3 text-5xl font-semibold tracking-[-0.05em] text-[#ffd08b]">NO-GO</p>
              </div>
              <span className="rounded-full border border-[#ffbf69]/30 px-3 py-1 font-mono text-[10px] uppercase tracking-[0.12em] text-[#ffd08b]">Fail closed</span>
            </div>
            <dl className="mt-8 grid grid-cols-2 gap-5 border-t border-[#ffbf69]/15 pt-5">
              <div><dt className="text-xs text-[#9eb0c1]">Held-out proposals</dt><dd className="mt-1 text-2xl font-semibold">6 / 6 abstain</dd></div>
              <div><dt className="text-xs text-[#9eb0c1]">Actions applied</dt><dd className="mt-1 text-2xl font-semibold">0</dd></div>
            </dl>
          </aside>
        </section>

        <section className="py-10">
          <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
            <div>
              <p className="font-mono text-[11px] uppercase tracking-[0.2em] text-[#5ce1e6]">Scientific status</p>
              <h2 className="mt-2 text-2xl font-semibold tracking-[-0.03em]">Hypotheses remain unresolved</h2>
            </div>
            <p className="max-w-lg text-sm leading-6 text-[#8da2b6]">Undefined endpoints stay undefined. The simple rule wins; no positive result is inferred from abstention.</p>
          </div>
          <div className="grid gap-4 lg:grid-cols-3">
            {hypotheses.map((item) => (
              <article key={item.id} className="rounded-3xl border border-white/10 bg-white/[0.035] p-6 transition-colors hover:border-[#5ce1e6]/30">
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

        <section className="border-t border-white/10 py-10">
          <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
            <div>
              <p className="font-mono text-[11px] uppercase tracking-[0.2em] text-[#5ce1e6]">Proposal audit</p>
              <h2 className="mt-2 text-2xl font-semibold tracking-[-0.03em]">Every held-out proposal stopped safely.</h2>
            </div>
            <div className="flex gap-2 font-mono text-[10px]">
              <a className="rounded-full border border-white/10 px-3 py-2 text-[#8da2b6] hover:border-[#5ce1e6]/40 hover:text-[#5ce1e6]" href="/api/status">GET /api/status</a>
              <a className="rounded-full border border-white/10 px-3 py-2 text-[#8da2b6] hover:border-[#5ce1e6]/40 hover:text-[#5ce1e6]" href="/api/proposals">GET /api/proposals</a>
            </div>
          </div>
          <div className="overflow-hidden rounded-3xl border border-white/10">
            <div className="hidden grid-cols-[0.7fr_1.2fr_1.1fr_0.7fr] gap-4 border-b border-white/10 bg-white/[0.04] px-5 py-3 font-mono text-[9px] uppercase tracking-[0.14em] text-[#60768a] md:grid">
              <span>Split / fault</span><span>Candidate action</span><span>Gate reason</span><span>Outcome</span>
            </div>
            {snapshot.proposal_audit.records.map((record) => (
              <article key={record.record_id} className="grid gap-3 border-b border-white/[0.07] px-5 py-4 last:border-b-0 md:grid-cols-[0.7fr_1.2fr_1.1fr_0.7fr] md:items-center md:gap-4">
                <div>
                  <p className="font-mono text-[9px] uppercase tracking-[0.14em] text-[#5ce1e6]">{record.split}</p>
                  <p className="mt-1 text-xs text-[#aab9c7]">{record.fault_type.replaceAll('_', ' ')}</p>
                </div>
                <div>
                  <p className="font-mono text-xs text-[#edf5f5]">{record.action_kind}</p>
                  <p className="mt-1 truncate font-mono text-[9px] text-[#60768a]" title={record.record_id}>{record.record_id}</p>
                </div>
                <p className="text-xs leading-5 text-[#8da2b6]">{record.reasons.join(' · ')}</p>
                <div className="flex items-center justify-between gap-3 md:block">
                  <span className="rounded-full border border-[#b8f34a]/25 bg-[#b8f34a]/[0.06] px-2.5 py-1 font-mono text-[9px] uppercase tracking-[0.12em] text-[#c9f879]">{record.decision}</span>
                  <p className="mt-2 font-mono text-[9px] text-[#60768a]">{record.execution_status}</p>
                </div>
              </article>
            ))}
          </div>
        </section>

        <section className="grid gap-6 border-t border-white/10 pt-10 lg:grid-cols-[0.9fr_1.1fr]">
          <div>
            <p className="font-mono text-[11px] uppercase tracking-[0.2em] text-[#5ce1e6]">Evidence ladder</p>
            <h2 className="mt-2 text-2xl font-semibold tracking-[-0.03em]">Claims stop where measurement stops.</h2>
          </div>
          <ol className="space-y-2">
            {evidenceStages.map(([label, description, status], index) => (
              <li key={label} className="grid grid-cols-[34px_1fr_auto] items-center gap-3 rounded-2xl border border-white/[0.07] bg-white/[0.025] px-4 py-3">
                <span className={`grid h-7 w-7 place-items-center rounded-full font-mono text-[10px] ${status === 'current' ? 'bg-[#b8f34a] text-[#07111f]' : status === 'complete' ? 'bg-[#5ce1e6]/15 text-[#5ce1e6]' : 'bg-white/[0.06] text-[#60768a]'}`}>{index + 1}</span>
                <div><p className="text-sm font-medium">{label}</p><p className="text-xs text-[#778da2]">{description}</p></div>
                <span className={`font-mono text-[9px] uppercase tracking-[0.12em] ${status === 'pending' ? 'text-[#60768a]' : 'text-[#b8f34a]'}`}>{status}</span>
              </li>
            ))}
          </ol>
        </section>

        <footer className="mt-12 flex flex-col gap-3 border-t border-white/10 pt-5 font-mono text-[10px] text-[#60768a] sm:flex-row sm:items-center sm:justify-between">
          <p>Source: 20260824T054718Z-benchmark-report-v0</p>
          <p>Manifest SHA-256 · 2e09dd8dff29…f8059</p>
        </footer>
      </div>
    </main>
  );
}

import snapshot from '../../data/status.json';

export async function GET() {
  const proposalSummary = {
    proposal_count: snapshot.proposal_audit.proposal_count,
    abstain_count: snapshot.proposal_audit.abstain_count,
    applied_action_count: snapshot.proposal_audit.applied_action_count,
    live_sentinel_reject_count: snapshot.proposal_audit.live_sentinel_reject_count,
  };
  return Response.json(
    { ...snapshot, proposal_audit: proposalSummary },
    { headers: { 'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff' } },
  );
}

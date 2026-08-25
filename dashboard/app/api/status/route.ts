import snapshot from '../../data/status.json';

export async function GET() {
  const proposalSummary = {
    evaluation_mode: snapshot.proposal_audit.evaluation_mode,
    proposal_count: snapshot.proposal_audit.proposal_count,
    eligible_count: snapshot.proposal_audit.eligible_count,
    abstain_count: snapshot.proposal_audit.abstain_count,
    applied_action_count: snapshot.proposal_audit.applied_action_count,
  };
  return Response.json(
    { ...snapshot, proposal_audit: proposalSummary },
    { headers: { 'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff' } },
  );
}

import snapshot from '../../data/status.json';

export async function GET() {
  return Response.json(snapshot.proposal_audit, {
    headers: { 'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff' },
  });
}

// ============================================================================
// sportsLogos — URL deterministici dei loghi API-Football (media.api-sports.io)
// a partire dagli id numerici di lega/squadra (stessa fonte della dashboard,
// vedi components/dashboard/MatchesList.tsx). Stringa vuota se id assente:
// chi renderizza nasconde l'<img> (onError o guard), MAI placeholder rotti.
// ============================================================================
const API_MEDIA = 'https://media.api-sports.io/football';

export function leagueLogo(id?: number | null): string {
    return id ? `${API_MEDIA}/leagues/${id}.png` : '';
}

export function teamLogo(id?: number | null): string {
    return id ? `${API_MEDIA}/teams/${id}.png` : '';
}

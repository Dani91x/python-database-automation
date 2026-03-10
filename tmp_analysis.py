import json

with open('Betfair/mm_history.json', 'r', encoding='utf-8') as f:
    history = json.load(f)

poisson_bets = []
ml_bets = []

for day in history:
    if 'slots' in day:
        poisson_bets.extend(day['slots'])
    if 'ml_slots' in day:
        ml_bets.extend(day['ml_slots'])

with open('tmp_output.txt', 'w', encoding='utf-8') as out:
    out.write(f"Total days: {len(history)}\n")
    out.write(f"Total Poisson bets: {len(poisson_bets)}\n")
    out.write(f"Total ML bets: {len(ml_bets)}\n")
    
    def print_stats(name, bets):
        if not bets:
            out.write(f"\n{name} Stats: No bets\n")
            return
            
        wins = [b for b in bets if 'VINTO' in str(b.get('result', ''))]
        losses = [b for b in bets if 'PERSO' in str(b.get('result', ''))]
        pending = [b for b in bets if 'PENDING' in str(b.get('result', ''))]
        
        profit = sum(b.get('pnl', 0) for b in bets)
        avg_odds = sum(b.get('odds', 0) for b in bets) / len(bets) if bets else 0
        total_staked = sum(b.get('stake', 0) for b in bets)
        roi = (profit / total_staked * 100) if total_staked else 0
        
        out.write(f"\n{name} Stats:\n")
        out.write(f"  Matches: {len(bets)} (Wins: {len(wins)}, Losses: {len(losses)}, Pending: {len(pending)})\n")
        if (len(wins) + len(losses)) > 0:
            win_rate = len(wins)/(len(wins)+len(losses))*100
            out.write(f"  Win Rate: {win_rate:.2f}%\n")
        else:
            out.write("  Win Rate: N/A\n")
        out.write(f"  Avg Odds: {avg_odds:.2f}\n")
        out.write(f"  Profit: {profit:.2f} euro\n")
        out.write(f"  Total Staked: {total_staked:.2f} euro (ROI: {roi:.2f}%)\n")

    print_stats("POISSON", poisson_bets)
    print_stats("ML", ml_bets)

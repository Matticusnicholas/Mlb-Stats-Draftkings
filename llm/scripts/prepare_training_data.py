"""
Training Data Preparation for MLB Best Ball LLM

Generates instruction-tuning dataset from:
- Cutline rankings
- EV rankings
- Scoring rules
- Baseball/best ball strategy knowledge
"""

import json
import random
from pathlib import Path
from typing import List, Dict

# Paths
DATA_DIR = Path(__file__).parent.parent.parent / 'data'
OUTPUT_DIR = Path(__file__).parent.parent / 'training_data'


def load_json(path: Path) -> dict:
    """Load JSON file."""
    if path.exists():
        with open(path, 'r') as f:
            return json.load(f)
    return {}


def generate_ranking_qa(cutline_rankings: dict, ev_rankings: dict) -> List[Dict]:
    """Generate Q&A pairs about player rankings."""
    qa_pairs = []

    # Build EV lookup by name
    ev_by_name = {}
    for p in ev_rankings.get('rankings', []):
        ev_by_name[p['player_name'].lower()] = p['ev_rank']

    cutline_players = cutline_rankings.get('rankings', [])

    for player in cutline_players[:200]:  # Top 200 for training
        name = player['player_name']
        rank = player['rank']
        pos = player['position']
        team = player.get('team', 'Unknown')
        ev_rank = ev_by_name.get(name.lower(), 999)

        # Question about player rank
        qa_pairs.append({
            'instruction': f"What is {name}'s Cutline ranking?",
            'response': f"{name} is ranked #{rank} in Cutline rankings. He plays {pos} for {team}."
        })

        # Question about EV vs Cutline
        if ev_rank != 999:
            diff = rank - ev_rank
            if diff > 20:
                assessment = f"This is a significant VALUE - he's being undervalued by {diff} spots in consensus rankings."
            elif diff < -20:
                assessment = f"This is a FADE - he's being overvalued by {abs(diff)} spots compared to my projections."
            else:
                assessment = f"He's fairly valued with only a {abs(diff)} spot difference."

            qa_pairs.append({
                'instruction': f"Is {name} a value pick in Cutline drafts?",
                'response': f"{name} has an EV rank of {ev_rank} but a Cutline consensus rank of {rank}. {assessment}"
            })

        # Position-specific questions
        if pos == 'C':
            qa_pairs.append({
                'instruction': f"Should I draft {name} as my catcher?",
                'response': f"{name} is ranked #{rank} overall and is one of the catchers in the player pool. In Cutline, you need 2 catchers daily, so catcher is a premium position. {'He would be a strong C1 option.' if rank < 50 else 'He could be a solid C2 option.' if rank < 150 else 'He is a deeper catcher option.'}"
            })
        elif pos == 'P':
            qa_pairs.append({
                'instruction': f"What kind of pitcher is {name} for Cutline?",
                'response': f"{name} is ranked #{rank} in Cutline. {'He is an elite arm worth reaching for.' if rank < 50 else 'He is a solid starter who can anchor your pitching staff.' if rank < 150 else 'He is a depth arm who can provide innings and the occasional big week.'}"
            })

    return qa_pairs


def generate_scoring_qa() -> List[Dict]:
    """Generate Q&A pairs about Cutline scoring."""
    return [
        {
            'instruction': "How does Cutline scoring work for hitters?",
            'response': "Cutline hitter scoring: -1 per AB, +4 per Hit, +6 per HR, +2 per Run, +2 per RBI, +5 per SB. The -1/AB penalty means high-strikeout, low-average hitters are penalized. You want contact + power + speed."
        },
        {
            'instruction': "How does Cutline scoring work for pitchers?",
            'response': "Cutline pitcher scoring: +3 per IP, -1 per Hit allowed, -2 per ER, -1 per BB, +1 per K, +6 per Win, +8 per Save. Saves are worth +8 which is the highest in the industry - elite closers are very valuable."
        },
        {
            'instruction': "Why are saves so valuable in Cutline?",
            'response': "Saves are worth +8 points in Cutline - the highest value in any major best ball format. An elite closer getting 35+ saves adds 280+ points to your season. That's essentially free production if you can lock up a top closer."
        },
        {
            'instruction': "Does Cutline reward walks for hitters?",
            'response': "No! Cutline does NOT give points for walks. This is a key difference from other formats. It means OBP-first hitters who don't hit for average are less valuable. You want contact hitters who put the ball in play."
        },
        {
            'instruction': "What is the AB penalty in Cutline?",
            'response': "Hitters lose -1 point per AB in Cutline. This means every at-bat that doesn't result in a hit costs you. High-AB, low-average players (like Adam Dunn types) are penalized heavily. Quality over quantity."
        },
        {
            'instruction': "How valuable are home runs in Cutline?",
            'response': "Home runs are worth +6 points PLUS the +4 for the hit, +2 for the run, and +2 for the RBI = 14 total points minimum (more with runners on). HR hitters have massive weekly upside in best ball."
        },
        {
            'instruction': "How valuable are stolen bases in Cutline?",
            'response': "Stolen bases are worth +5 points in Cutline. Speed guys who swipe 30+ bags add 150+ points. Combined with runs scored, elite speedsters can be sneaky valuable even without power."
        },
        {
            'instruction': "What makes a good Cutline pitcher?",
            'response': "Ideal Cutline pitchers: 1) Innings eaters who go 6+ IP (+18 points minimum), 2) Low WHIP (fewer hits/walks allowed), 3) High K rate (+1 each), 4) On good teams (more win opportunities at +6 each), 5) Closers for saves (+8 each)."
        },
    ]


def generate_strategy_qa() -> List[Dict]:
    """Generate Q&A pairs about best ball strategy."""
    return [
        {
            'instruction': "What is the best draft strategy for Cutline?",
            'response': "Stack hitters early, pitchers late. Batters dominate Cutline scoring with higher ceilings. Draft 28-32 hitters to maximize weekly spike potential. Take 10-14 pitchers focusing on innings eaters and closers. Get one elite catcher early since you need 2 daily."
        },
        {
            'instruction': "How many pitchers should I draft in Cutline?",
            'response': "10-14 pitchers is the sweet spot. You need 9 pitcher slots daily but don't need massive depth since batters score more. Focus on workhorses who eat innings (Sandy Alcantara types) and elite closers (saves worth +8). Let pitchers fall to you."
        },
        {
            'instruction': "How many catchers should I draft in Cutline?",
            'response': "Draft 3-4 catchers. You need 2 catchers daily which creates scarcity. Lock up one elite catcher (Cal Raleigh, William Contreras tier) in rounds 2-5, then grab 2-3 depth options. The CI and UTIL slots can also start catchers for spike weeks."
        },
        {
            'instruction': "What is roster construction in Cutline?",
            'response': "Daily lineup: 2C, 1B, 2B, 3B, SS, MI, CI, 5OF, UTIL, 9P. Draft to maximize flexibility - 3+ at each infield spot (MI can be 2B/SS, CI can be 1B/3B), 8-10 OF, and stack bats. More hitters = more paths to optimal lineups each week."
        },
        {
            'instruction': "What are spike weeks in best ball?",
            'response': "Spike weeks are when your optimal lineup explodes for 700+ points. In best ball, you don't set lineups - the system picks your best scores. Having multiple high-upside hitters gives you more chances to hit these ceiling weeks. Stack volatile bats!"
        },
        {
            'instruction': "Should I draft for floor or ceiling in Cutline?",
            'response': "CEILING. Best ball is about maximizing your best weeks, not your worst. A player who scores 20/20/20/80 is better than 35/35/35/35 because best ball picks your top scores. Draft volatile, high-upside players."
        },
        {
            'instruction': "What is the UTIL slot strategy in Cutline?",
            'response': "UTIL can start any hitter including catchers. This means you can potentially start 3 catchers (2C + UTIL), 3 first basemen (1B + CI + UTIL), 3 second basemen (2B + MI + UTIL), etc. Stack positions to maximize spike week combinations."
        },
        {
            'instruction': "How do I find value in Cutline drafts?",
            'response': "Compare your own rankings to consensus ADP. When you rank a player significantly higher than consensus, that's a value pick - you're getting someone you like at a discount. Track EV rank vs Cutline rank to spot these edges."
        },
        {
            'instruction': "What is positional scarcity in Cutline?",
            'response': "Catcher is the scarcest position - you need 2 daily but there are few elite options. Prioritize C1 in rounds 2-5. Shortstop and 2B have depth. Outfield is deepest. Pitchers can be found late since batters dominate scoring."
        },
        {
            'instruction': "When should I draft pitchers in Cutline?",
            'response': "Wait on pitchers! You can get quality innings eaters in rounds 15-30. The only pitchers worth reaching for are elite aces (Skubal, Crochet) or elite closers. Let the field overdraft arms while you stack bats."
        },
    ]


def generate_general_baseball_qa() -> List[Dict]:
    """Generate general baseball knowledge Q&A."""
    return [
        {
            'instruction': "What stats matter most for hitters in fantasy?",
            'response': "The core 5x5 categories: AVG (or OBP), HR, RBI, Runs, SB. In points leagues like Cutline, focus on players who do multiple things - a .280 hitter with 25 HR, 80 RBI, 90 R, and 15 SB is elite. Avoid one-dimensional players."
        },
        {
            'instruction': "What is WHIP and why does it matter?",
            'response': "WHIP = (Walks + Hits) / Innings Pitched. It measures how many baserunners a pitcher allows per inning. In Cutline, each hit is -1 and each walk is -1, so low WHIP pitchers minimize negative points. Target WHIP under 1.20."
        },
        {
            'instruction': "What is a good K/9 rate for pitchers?",
            'response': "Elite: 10+ K/9 (Skubal, Crochet, Strider). Good: 8-10 K/9. Average: 6-8 K/9. In Cutline, each K is +1 point, so high-K pitchers have upside. But don't ignore innings - 7 IP with 6 K beats 4 IP with 8 K."
        },
        {
            'instruction': "What makes a player injury prone?",
            'response': "History matters - players with recurring injuries (hamstrings, obliques, backs) are risks. Mike Trout, for example, has missed significant time multiple seasons. In best ball, injured players give you zero points. Balance upside with durability."
        },
        {
            'instruction': "What is park factor in baseball?",
            'response': "Park factor measures how a stadium affects scoring. Coors Field (Rockies) inflates offense, while Oracle Park (Giants) suppresses it. Target hitters in hitter-friendly parks and pitchers in pitcher-friendly parks for better production."
        },
        {
            'instruction': "What is platoon advantage?",
            'response': "Most hitters perform better against opposite-handed pitchers (righties vs lefties, lefties vs righties). Platoon players only face favorable matchups, boosting their per-AB production. In best ball, platoon bats can provide value."
        },
        {
            'instruction': "What is batting order importance?",
            'response': "Lineup position affects counting stats. Leadoff hitters score more runs, 2-4 hitters get more RBI opportunities, 5-6 hitters often have power but fewer chances. A player moving up in the order is a positive for fantasy value."
        },
        {
            'instruction': "What is a two-start pitcher week?",
            'response': "In a given week, some starting pitchers get two starts due to schedule. Two starts = double the innings, Ks, and win chances. In best ball, identifying two-start pitchers helps maximize your weekly ceiling."
        },
    ]


def generate_comparison_qa(cutline_rankings: dict, ev_rankings: dict) -> List[Dict]:
    """Generate Q&A comparing players."""
    qa_pairs = []

    ev_by_name = {}
    for p in ev_rankings.get('rankings', []):
        ev_by_name[p['player_name'].lower()] = p['ev_rank']

    players = cutline_rankings.get('rankings', [])[:100]

    # Group by position
    by_pos = {}
    for p in players:
        pos = p['position']
        if pos not in by_pos:
            by_pos[pos] = []
        by_pos[pos].append(p)

    for pos, pos_players in by_pos.items():
        if len(pos_players) >= 2:
            p1, p2 = pos_players[0], pos_players[1]
            ev1 = ev_by_name.get(p1['player_name'].lower(), 999)
            ev2 = ev_by_name.get(p2['player_name'].lower(), 999)

            qa_pairs.append({
                'instruction': f"Who should I draft: {p1['player_name']} or {p2['player_name']}?",
                'response': f"Both are top {pos} options. {p1['player_name']} is Cutline rank #{p1['rank']} (EV: {ev1}), while {p2['player_name']} is #{p2['rank']} (EV: {ev2}). {'I prefer ' + p1['player_name'] + ' based on EV rankings.' if ev1 < ev2 else 'I prefer ' + p2['player_name'] + ' based on EV rankings.' if ev2 < ev1 else 'They are similarly valued.'}"
            })

    return qa_pairs


def format_for_training(qa_pairs: List[Dict]) -> List[Dict]:
    """Format Q&A pairs for instruction tuning."""
    formatted = []

    system_prompt = """You are an expert MLB fantasy baseball assistant specializing in best ball formats, particularly NFBC Cutline Championship. You have deep knowledge of:
- Cutline scoring rules and strategy
- Player rankings and projections
- Draft strategy and roster construction
- Baseball statistics and analytics
Provide helpful, accurate advice to help users win their best ball leagues."""

    for qa in qa_pairs:
        formatted.append({
            'system': system_prompt,
            'instruction': qa['instruction'],
            'response': qa['response']
        })

    return formatted


def main():
    """Generate training dataset."""
    print("Loading data files...")

    cutline_rankings = load_json(DATA_DIR / 'cutline_rankings.json')
    ev_rankings = load_json(DATA_DIR / 'cutline_ev_rankings.json')

    print(f"Loaded {len(cutline_rankings.get('rankings', []))} Cutline rankings")
    print(f"Loaded {len(ev_rankings.get('rankings', []))} EV rankings")

    all_qa = []

    # Generate different types of Q&A
    print("Generating ranking Q&A...")
    all_qa.extend(generate_ranking_qa(cutline_rankings, ev_rankings))

    print("Generating scoring Q&A...")
    all_qa.extend(generate_scoring_qa())

    print("Generating strategy Q&A...")
    all_qa.extend(generate_strategy_qa())

    print("Generating baseball knowledge Q&A...")
    all_qa.extend(generate_general_baseball_qa())

    print("Generating comparison Q&A...")
    all_qa.extend(generate_comparison_qa(cutline_rankings, ev_rankings))

    # Shuffle
    random.shuffle(all_qa)

    # Format for training
    formatted = format_for_training(all_qa)

    # Save
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_path = OUTPUT_DIR / 'training_data.json'

    with open(output_path, 'w') as f:
        json.dump(formatted, f, indent=2)

    print(f"\nGenerated {len(formatted)} training examples")
    print(f"Saved to: {output_path}")

    # Also save in JSONL format for some training frameworks
    jsonl_path = OUTPUT_DIR / 'training_data.jsonl'
    with open(jsonl_path, 'w') as f:
        for item in formatted:
            f.write(json.dumps(item) + '\n')

    print(f"Also saved JSONL format: {jsonl_path}")


if __name__ == '__main__':
    main()

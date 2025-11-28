"""
Mock Draft Simulator with AI Archetypes.

Simulates a 12-team snake draft with AI opponents using different
drafting strategies based on popular DraftKings MLB best ball metas.
"""
import json
import random
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
import logging

logger = logging.getLogger(__name__)


class DraftArchetype(Enum):
    """AI drafting strategy archetypes."""
    ADP_ANDY = "adp_andy"           # Follows ADP closely (±1 round)
    STARS_AND_SCRUBS = "stars_scrubs"  # Premium early, bargain late
    ZERO_PITCHER = "zero_pitcher"   # 8/8/4P strategy - loads up on bats
    ACE_HUNTER = "ace_hunter"       # Grabs elite pitchers rounds 3-6
    POSITION_SCARCITY = "pos_scarcity"  # Prioritizes C/SS early
    CONTRARIAN = "contrarian"       # Fades popular picks, targets value
    BALANCED = "balanced"           # Even position distribution
    USER = "user"                   # Human-controlled


@dataclass
class DraftPick:
    """Represents a single draft pick."""
    round_num: int
    pick_num: int
    overall_pick: int
    team_id: int
    player_id: int
    player_name: str
    position: str
    adp_rank: int


@dataclass
class DraftTeam:
    """Represents a team in the draft."""
    team_id: int
    name: str
    archetype: DraftArchetype
    roster: List[DraftPick] = field(default_factory=list)

    def get_position_counts(self) -> Dict[str, int]:
        """Get count of players by position."""
        counts = {'IF': 0, 'OF': 0, 'P': 0}
        for pick in self.roster:
            if pick.position in counts:
                counts[pick.position] += 1
        return counts

    def needs_position(self, position: str, targets: Dict[str, int]) -> bool:
        """Check if team still needs players at a position."""
        counts = self.get_position_counts()
        return counts.get(position, 0) < targets.get(position, 20)


@dataclass
class AvailablePlayer:
    """Player available to be drafted."""
    rank: int
    db_player_id: int
    player_name: str
    position: str
    team: str
    rotowire_id: int = 0


class MockDraftEngine:
    """
    Manages a 12-team snake draft simulation.
    """

    NUM_TEAMS = 12
    NUM_ROUNDS = 20

    # Position targets for different archetypes (established metas)
    # Most drafters take 5-7 pitchers for depth/streaming options
    ARCHETYPE_TARGETS = {
        DraftArchetype.ADP_ANDY: {'IF': 7, 'OF': 7, 'P': 6},      # Standard balanced build
        DraftArchetype.STARS_AND_SCRUBS: {'IF': 7, 'OF': 7, 'P': 6},  # Premium early + value late
        DraftArchetype.ZERO_PITCHER: {'IF': 7, 'OF': 6, 'P': 7},  # Wait on P, but still get depth
        DraftArchetype.ACE_HUNTER: {'IF': 6, 'OF': 6, 'P': 8},    # Heavy pitcher investment
        DraftArchetype.POSITION_SCARCITY: {'IF': 8, 'OF': 6, 'P': 6},  # Prioritize scarce positions
        DraftArchetype.CONTRARIAN: {'IF': 7, 'OF': 7, 'P': 6},    # Fade popular, find value
        DraftArchetype.BALANCED: {'IF': 7, 'OF': 7, 'P': 6},      # Even distribution
        DraftArchetype.USER: {'IF': 7, 'OF': 7, 'P': 6},          # Default for user
    }

    # Round preferences for archetypes (which rounds to take pitchers)
    PITCHER_ROUND_PREFS = {
        DraftArchetype.ADP_ANDY: list(range(1, 21)),  # Follows ADP strictly
        DraftArchetype.STARS_AND_SCRUBS: list(range(3, 21)),  # Bats first 2 rounds, then mix
        DraftArchetype.ZERO_PITCHER: list(range(10, 21)),  # Wait until round 10+
        DraftArchetype.ACE_HUNTER: [2, 3, 4, 5, 6, 7, 8, 9, 10],  # Early-mid pitcher focus
        DraftArchetype.POSITION_SCARCITY: list(range(8, 21)),  # Later pitchers
        DraftArchetype.CONTRARIAN: list(range(6, 21)),  # Mid-late, avoid early run
        DraftArchetype.BALANCED: list(range(4, 21)),  # Spread throughout
    }

    def __init__(self, user_position: int = 1):
        """
        Initialize draft engine.

        Args:
            user_position: User's draft position (1-12)
        """
        self.user_position = user_position
        self.teams: List[DraftTeam] = []
        self.available_players: List[AvailablePlayer] = []
        self.picks: List[DraftPick] = []
        self.current_round = 1
        self.current_pick = 1

        self._load_rankings()
        self._setup_teams()

    def _load_rankings(self):
        """Load ADP rankings from file."""
        rankings_path = Path(__file__).parent.parent.parent / 'data' / 'adp_rankings_2025.json'

        with open(rankings_path, 'r') as f:
            data = json.load(f)

        self.available_players = [
            AvailablePlayer(
                rank=p['rank'],
                db_player_id=p['db_player_id'],
                player_name=p['player_name'],
                position=p['position'],
                team=p['team'],
                rotowire_id=p.get('rotowire_id', 0)
            )
            for p in data['rankings']
        ]

        logger.info(f"Loaded {len(self.available_players)} players from rankings")

    def _setup_teams(self):
        """Set up 12 teams with random archetypes."""
        # Available archetypes for AI (excluding USER)
        ai_archetypes = [
            DraftArchetype.ADP_ANDY,
            DraftArchetype.ADP_ANDY,  # More common
            DraftArchetype.STARS_AND_SCRUBS,
            DraftArchetype.ZERO_PITCHER,
            DraftArchetype.ACE_HUNTER,
            DraftArchetype.POSITION_SCARCITY,
            DraftArchetype.CONTRARIAN,
            DraftArchetype.BALANCED,
            DraftArchetype.BALANCED,  # More common
        ]

        random.shuffle(ai_archetypes)

        for i in range(self.NUM_TEAMS):
            team_id = i + 1
            if team_id == self.user_position:
                archetype = DraftArchetype.USER
                name = "Your Team"
            else:
                archetype = ai_archetypes.pop() if ai_archetypes else DraftArchetype.BALANCED
                name = f"AI Team {team_id} ({archetype.value})"

            self.teams.append(DraftTeam(
                team_id=team_id,
                name=name,
                archetype=archetype
            ))

    def get_pick_order(self, round_num: int) -> List[int]:
        """Get pick order for a round (snake draft)."""
        order = list(range(1, self.NUM_TEAMS + 1))
        if round_num % 2 == 0:  # Even rounds go in reverse
            order.reverse()
        return order

    def get_overall_pick(self, round_num: int, pick_in_round: int) -> int:
        """Calculate overall pick number."""
        return (round_num - 1) * self.NUM_TEAMS + pick_in_round

    def get_current_team(self) -> DraftTeam:
        """Get the team currently on the clock."""
        order = self.get_pick_order(self.current_round)
        team_id = order[self.current_pick - 1]
        return self.teams[team_id - 1]

    def is_user_pick(self) -> bool:
        """Check if it's the user's turn to pick."""
        return self.get_current_team().archetype == DraftArchetype.USER

    def get_available_by_position(self, position: str) -> List[AvailablePlayer]:
        """Get available players at a specific position."""
        return [p for p in self.available_players if p.position == position]

    def get_adp_range_players(
        self,
        min_rank: int,
        max_rank: int,
        position: Optional[str] = None
    ) -> List[AvailablePlayer]:
        """Get available players within an ADP range."""
        players = self.available_players
        if position:
            players = [p for p in players if p.position == position]
        return [p for p in players if min_rank <= p.rank <= max_rank]

    def make_pick(self, player: AvailablePlayer) -> DraftPick:
        """Execute a draft pick."""
        if player not in self.available_players:
            raise ValueError(f"Player {player.player_name} is not available")

        team = self.get_current_team()
        overall = self.get_overall_pick(self.current_round, self.current_pick)

        pick = DraftPick(
            round_num=self.current_round,
            pick_num=self.current_pick,
            overall_pick=overall,
            team_id=team.team_id,
            player_id=player.db_player_id,
            player_name=player.player_name,
            position=player.position,
            adp_rank=player.rank
        )

        # Update state
        self.available_players.remove(player)
        team.roster.append(pick)
        self.picks.append(pick)

        # Advance to next pick
        self._advance_pick()

        return pick

    def _advance_pick(self):
        """Move to the next pick in the draft."""
        self.current_pick += 1
        if self.current_pick > self.NUM_TEAMS:
            self.current_pick = 1
            self.current_round += 1

    def is_draft_complete(self) -> bool:
        """Check if draft is finished."""
        return self.current_round > self.NUM_ROUNDS

    def ai_select_player(self, team: DraftTeam) -> AvailablePlayer:
        """
        AI selects a player based on archetype strategy.

        Returns the player the AI wants to draft.
        """
        archetype = team.archetype
        overall_pick = self.get_overall_pick(self.current_round, self.current_pick)
        targets = self.ARCHETYPE_TARGETS.get(archetype, {'IF': 8, 'OF': 8, 'P': 4})
        position_counts = team.get_position_counts()
        rounds_left = self.NUM_ROUNDS - self.current_round + 1

        # Calculate position needs
        needs = {
            'P': max(0, targets['P'] - position_counts['P']),
            'IF': max(0, targets['IF'] - position_counts['IF']),
            'OF': max(0, targets['OF'] - position_counts['OF'])
        }
        total_needs = sum(needs.values())

        # Calculate ADP window based on archetype
        if archetype == DraftArchetype.ADP_ANDY:
            adp_variance = 10
        elif archetype == DraftArchetype.CONTRARIAN:
            adp_variance = 25
        else:
            adp_variance = 15

        min_adp = max(1, overall_pick - adp_variance)
        max_adp = min(500, overall_pick + adp_variance * 2)

        # Get candidates within ADP range
        candidates = self.get_adp_range_players(min_adp, max_adp)

        if not candidates:
            candidates = self.available_players[:20]

        # CRITICAL: Force position filling when running low on rounds
        forced_position = None

        # Must fill pitchers if we need them and running out of time
        if needs['P'] > 0 and rounds_left <= needs['P'] + 1:
            forced_position = 'P'
        elif needs['IF'] > 0 and rounds_left <= needs['IF'] + 1:
            forced_position = 'IF'
        elif needs['OF'] > 0 and rounds_left <= needs['OF'] + 1:
            forced_position = 'OF'

        if forced_position:
            pos_candidates = [c for c in self.available_players if c.position == forced_position]
            if pos_candidates:
                # Take best available at that position
                return min(pos_candidates, key=lambda x: x.rank)

        # Get pitcher round preferences for this archetype
        pitcher_rounds = self.PITCHER_ROUND_PREFS.get(archetype, list(range(1, 21)))

        # Archetype-specific logic
        if archetype == DraftArchetype.ZERO_PITCHER:
            # Wait on pitchers until round 10+
            if self.current_round < 10:
                candidates = [c for c in candidates if c.position != 'P']
            elif needs['P'] > 0 and self.current_round >= 10:
                # Start mixing in pitchers after round 10
                pitcher_candidates = [c for c in candidates if c.position == 'P']
                if pitcher_candidates and random.random() < 0.5:
                    candidates = pitcher_candidates

        elif archetype == DraftArchetype.ACE_HUNTER:
            # Heavy pitcher investment - willing to reach for elite arms
            if self.current_round in pitcher_rounds and needs['P'] > 0:
                # Get ALL available pitchers, not just those in ADP window
                all_pitchers = [p for p in self.available_players if p.position == 'P']
                if all_pitchers and random.random() < 0.75:
                    # Take best available pitcher even if reaching
                    return min(all_pitchers, key=lambda x: x.rank)

        elif archetype == DraftArchetype.POSITION_SCARCITY:
            # Prioritize IF/C early for scarce positions
            if self.current_round <= 10 and needs['IF'] > 2:
                if_candidates = [c for c in candidates if c.position == 'IF']
                if if_candidates:
                    candidates = if_candidates

        elif archetype == DraftArchetype.STARS_AND_SCRUBS:
            # Pay up for premium players early
            if self.current_round <= 4:
                candidates = sorted(candidates, key=lambda x: x.rank)[:5]
            # Take pitchers in rounds 4-8 (willing to reach for aces)
            if 4 <= self.current_round <= 10 and needs['P'] > 0:
                all_pitchers = [p for p in self.available_players if p.position == 'P']
                if all_pitchers and random.random() < 0.35:
                    return min(all_pitchers, key=lambda x: x.rank)

        elif archetype in [DraftArchetype.ADP_ANDY, DraftArchetype.BALANCED]:
            # Spread pitcher picks throughout draft - willing to reach a bit
            pitcher_round_targets = [3, 6, 9, 12, 15, 18]
            if self.current_round in pitcher_round_targets and needs['P'] > 0:
                all_pitchers = [p for p in self.available_players if p.position == 'P']
                if all_pitchers and random.random() < 0.55:
                    return min(all_pitchers, key=lambda x: x.rank)

        elif archetype == DraftArchetype.CONTRARIAN:
            # Fade popular picks, take pitchers mid-draft when others go bats
            if 5 <= self.current_round <= 12 and needs['P'] > 0:
                all_pitchers = [p for p in self.available_players if p.position == 'P']
                if all_pitchers and random.random() < 0.45:
                    return min(all_pitchers, key=lambda x: x.rank)

        # Filter out positions we don't need
        if needs['P'] == 0:
            candidates = [c for c in candidates if c.position != 'P']
        if needs['IF'] == 0:
            candidates = [c for c in candidates if c.position != 'IF']
        if needs['OF'] == 0:
            candidates = [c for c in candidates if c.position != 'OF']

        if not candidates:
            # Fallback: take best available that we need
            for pos in ['IF', 'OF', 'P']:
                if needs[pos] > 0:
                    pos_candidates = [p for p in self.available_players if p.position == pos]
                    if pos_candidates:
                        return min(pos_candidates, key=lambda x: x.rank)
            # Ultimate fallback
            candidates = self.available_players[:5]

        # Sort by ADP
        candidates = sorted(candidates, key=lambda x: x.rank)

        # Add some randomness (don't always take best ADP)
        if len(candidates) > 3:
            weights = [1.0 / (i + 1) ** 0.5 for i in range(min(len(candidates), 8))]
            total = sum(weights)
            weights = [w / total for w in weights]

            r = random.random()
            cumulative = 0
            for i, w in enumerate(weights):
                cumulative += w
                if r <= cumulative:
                    return candidates[i]

        # Default: return best ADP available
        return min(candidates, key=lambda x: x.rank)

    def simulate_pick(self) -> Optional[DraftPick]:
        """
        Simulate a single pick (AI only).

        Returns None if it's the user's turn.
        """
        if self.is_draft_complete():
            return None

        team = self.get_current_team()

        if team.archetype == DraftArchetype.USER:
            return None  # User needs to pick

        player = self.ai_select_player(team)
        return self.make_pick(player)

    def simulate_until_user_pick(self) -> List[DraftPick]:
        """
        Simulate all picks until it's the user's turn.

        Returns list of picks made.
        """
        picks_made = []

        while not self.is_draft_complete():
            if self.is_user_pick():
                break

            pick = self.simulate_pick()
            if pick:
                picks_made.append(pick)

        return picks_made

    def user_make_pick(self, player_id: int) -> Optional[DraftPick]:
        """
        Make a pick for the user.

        Args:
            player_id: Database player ID to draft

        Returns:
            DraftPick if successful, None if not user's turn
        """
        if not self.is_user_pick():
            return None

        player = next(
            (p for p in self.available_players if p.db_player_id == player_id),
            None
        )

        if not player:
            raise ValueError(f"Player {player_id} is not available")

        return self.make_pick(player)

    def get_draft_state(self) -> Dict:
        """Get current draft state for UI."""
        team = self.get_current_team()

        return {
            'current_round': self.current_round,
            'current_pick': self.current_pick,
            'overall_pick': self.get_overall_pick(self.current_round, self.current_pick),
            'is_user_pick': self.is_user_pick(),
            'current_team': {
                'id': team.team_id,
                'name': team.name,
                'archetype': team.archetype.value,
                'roster': [
                    {
                        'round': p.round_num,
                        'player_name': p.player_name,
                        'position': p.position,
                        'adp': p.adp_rank
                    }
                    for p in team.roster
                ]
            },
            'is_complete': self.is_draft_complete(),
            'available_count': len(self.available_players),
            'recent_picks': [
                {
                    'round': p.round_num,
                    'pick': p.pick_num,
                    'overall': p.overall_pick,
                    'team': self.teams[p.team_id - 1].name,
                    'player': p.player_name,
                    'position': p.position,
                    'adp': p.adp_rank
                }
                for p in self.picks[-12:]  # Last round of picks
            ]
        }

    def get_user_roster(self) -> List[DraftPick]:
        """Get the user's drafted roster."""
        user_team = next(t for t in self.teams if t.archetype == DraftArchetype.USER)
        return user_team.roster

    def get_all_rosters(self) -> Dict[int, List[DraftPick]]:
        """Get all teams' rosters."""
        return {team.team_id: team.roster for team in self.teams}


def run_full_simulation(user_position: int = 1) -> MockDraftEngine:
    """
    Run a complete mock draft with AI making all picks.

    Useful for testing or simulating opponent rosters.
    """
    engine = MockDraftEngine(user_position=0)  # No user position

    # Override user team to be AI
    for team in engine.teams:
        if team.archetype == DraftArchetype.USER:
            team.archetype = DraftArchetype.BALANCED
            team.name = f"AI Team {team.team_id} (balanced)"

    while not engine.is_draft_complete():
        engine.simulate_pick()

    return engine

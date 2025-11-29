"""
NFBC Cutline Championship Draft Simulator.

Simulates a 10-team snake draft for NFBC Cutline format with:
- 42 roster spots per team (initial draft)
- Detailed position requirements (C, 1B, 2B, 3B, SS, MI, CI, OF, UTIL, P)
- Cutline-specific meta strategies
- Integration with Monte Carlo season simulation

Cutline Scoring:
- Hitters: (H * 4) + (R * 2) + (HR * 6) + (RBI * 2) + (SB * 5) - AB
- Pitchers: (IP * 3) - H - (ER * 2) - BB + SO + (W * 6) + (SV * 8)
"""
import json
import random
from typing import List, Dict, Optional, Tuple, Set
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
import logging

logger = logging.getLogger(__name__)


# ============================================================================
# NFBC Cutline Roster Configuration
# ============================================================================

# Daily lineup: 23 starters (14 hitters + 9 pitchers)
CUTLINE_LINEUP_SLOTS = {
    'C': 2,      # Catcher (2 required - key position)
    '1B': 1,     # First Base
    '2B': 1,     # Second Base
    '3B': 1,     # Third Base
    'SS': 1,     # Shortstop
    'MI': 1,     # Middle Infield (2B or SS)
    'CI': 1,     # Corner Infield (1B or 3B)
    'OF': 5,     # Outfield
    'UTIL': 1,   # Utility (any hitter)
    'P': 9,      # Pitchers (SP or RP)
}

# Draft configuration
CUTLINE_NUM_TEAMS = 10
CUTLINE_ROSTER_SIZE = 42  # Initial draft roster
CUTLINE_MAX_ROSTER = 46   # After FAAB periods
CUTLINE_NUM_ROUNDS = 42


class CutlinePosition(Enum):
    """Detailed position for Cutline eligibility."""
    C = "C"
    FIRST_BASE = "1B"
    SECOND_BASE = "2B"
    THIRD_BASE = "3B"
    SHORTSTOP = "SS"
    OUTFIELD = "OF"
    PITCHER = "P"
    UTILITY = "UTIL"


# Position eligibility mapping
CUTLINE_POSITION_ELIGIBLE = {
    'C': ['C'],
    '1B': ['1B'],
    '2B': ['2B'],
    '3B': ['3B'],
    'SS': ['SS'],
    'MI': ['2B', 'SS'],  # Middle Infield
    'CI': ['1B', '3B'],  # Corner Infield
    'OF': ['OF', 'LF', 'CF', 'RF'],
    'UTIL': ['C', '1B', '2B', '3B', 'SS', 'OF', 'LF', 'CF', 'RF', 'DH'],
    'P': ['P', 'SP', 'RP'],
}

# Map specific positions to categories
POSITION_TO_CATEGORY = {
    'C': 'C',
    '1B': '1B',
    '2B': '2B',
    '3B': '3B',
    'SS': 'SS',
    'LF': 'OF',
    'CF': 'OF',
    'RF': 'OF',
    'OF': 'OF',
    'DH': 'UTIL',
    'P': 'P',
    'SP': 'P',
    'RP': 'P',
}


class CutlineArchetype(Enum):
    """AI drafting strategy archetypes for Cutline format."""
    NFBC_CONSENSUS = "nfbc_consensus"    # Follows NFBC ADP closely
    CATCHER_EARLY = "catcher_early"       # Two catchers required - grab early
    RELIEVER_HUNTER = "reliever_hunter"   # Targets elite closers for saves
    POINTS_CHASER = "points_chaser"       # Pure points projection focus
    VARIANCE_MAX = "variance_max"         # High-upside ceiling plays
    VOLUME_BASED = "volume_based"         # Prioritizes playing time/IP
    BALANCED = "balanced"                 # Even distribution
    USER = "user"                         # Human-controlled


# ============================================================================
# Cutline Meta Strategies (based on scoring research)
# ============================================================================

CUTLINE_META_INSIGHTS = {
    'catcher_premium': """
        Two catchers required in Cutline creates massive scarcity.
        Top catchers provide outsized positional advantage.
        Target C1 in rounds 4-7, C2 by round 15.
    """,
    'saves_value': """
        Saves worth +8 points in Cutline (highest in industry).
        Elite closers like Clase, Diaz have massive floor.
        Saves provide guaranteed volume in best ball.
    """,
    'no_walks_penalty': """
        No points for walks in Cutline batting.
        Favors BA hitters over OBP types.
        Contact + power > patience.
    """,
    'ab_penalty': """
        -1 per AB means outs are penalized.
        High-AB low-AVG players hurt you.
        Prefer quality over quantity at bats.
    """,
    'pitcher_wins': """
        Wins worth +6 points - target pitchers on good teams.
        Run support matters for win expectation.
        Aces on playoff teams > aces on bad teams.
    """,
    'hr_bonus': """
        HR worth +6 on top of hit value (10 total points).
        Pure power guys have high weekly ceilings.
        Volatile power bats good for best ball variance.
    """
}


@dataclass
class CutlineDraftPick:
    """Represents a single draft pick in Cutline format."""
    round_num: int
    pick_num: int
    overall_pick: int
    team_id: int
    player_id: int
    player_name: str
    position: str  # Detailed position (C, 1B, 2B, 3B, SS, OF, P)
    team_abbr: str
    rank: int      # ADP/ranking
    ev_rank: int = 0  # Expected value rank


@dataclass
class CutlineTeam:
    """Represents a team in the Cutline draft."""
    team_id: int
    name: str
    archetype: CutlineArchetype
    roster: List[CutlineDraftPick] = field(default_factory=list)

    def get_position_counts(self) -> Dict[str, int]:
        """Get count of players by position category."""
        counts = {
            'C': 0, '1B': 0, '2B': 0, '3B': 0, 'SS': 0,
            'OF': 0, 'P': 0, 'UTIL': 0
        }
        for pick in self.roster:
            cat = POSITION_TO_CATEGORY.get(pick.position, 'UTIL')
            counts[cat] = counts.get(cat, 0) + 1
        return counts

    def get_roster_needs(self) -> Dict[str, int]:
        """Calculate remaining roster needs for optimal lineup."""
        counts = self.get_position_counts()

        # Target roster composition for 42 players:
        # Need depth at every position for best ball weekly optimization
        targets = {
            'C': 4,    # 2 start, need depth for 162 games
            '1B': 3,   # 1 start + CI eligible
            '2B': 4,   # 1 start + MI eligible
            '3B': 3,   # 1 start + CI eligible
            'SS': 4,   # 1 start + MI eligible
            'OF': 9,   # 5 start, most scarce
            'P': 14,   # 9 start, need SP depth + closers
            'UTIL': 1, # DH types
        }

        return {pos: max(0, targets[pos] - counts.get(pos, 0))
                for pos in targets}

    def can_fill_slot(self, position: str) -> bool:
        """Check if team can use a player at this position."""
        counts = self.get_position_counts()
        cat = POSITION_TO_CATEGORY.get(position, 'UTIL')

        # General roster limits
        max_at_position = {
            'C': 4, '1B': 4, '2B': 4, '3B': 4, 'SS': 4,
            'OF': 10, 'P': 15, 'UTIL': 3
        }

        return counts.get(cat, 0) < max_at_position.get(cat, 20)


@dataclass
class CutlinePlayer:
    """Player available for Cutline draft."""
    rank: int
    player_id: int
    player_name: str
    position: str      # Detailed position
    team: str
    ev_rank: int = 0
    bestball_score: float = 0.0
    projected_points: float = 0.0


class CutlineDraftEngine:
    """
    NFBC Cutline Championship Draft Simulator.

    10-team snake draft with 36 rounds.
    Detailed position eligibility and Cutline-specific strategies.
    """

    NUM_TEAMS = CUTLINE_NUM_TEAMS
    NUM_ROUNDS = CUTLINE_ROSTER_SIZE

    # Position target recommendations by round ranges
    POSITION_ROUND_TARGETS = {
        'early': {  # Rounds 1-6: Elite talent
            'C': [4, 5, 6],      # First catcher window
            'P': [3, 4, 5, 6],   # Ace pitchers
            'SS': [1, 2, 3],     # Elite SS (premium position)
        },
        'mid': {  # Rounds 7-18: Building depth
            'C': [12, 13, 14, 15],  # Second catcher
            'P': list(range(7, 19)),  # Rotation depth + closers
            'OF': list(range(7, 19)), # OF depth
        },
        'late': {  # Rounds 19-36: Upside/value
            'P': list(range(19, 37)),  # Streamers, closers, speculative arms
            'OF': list(range(25, 37)), # Upside OF bats
        }
    }

    # Archetype-specific drafting configurations
    ARCHETYPE_CONFIGS = {
        CutlineArchetype.NFBC_CONSENSUS: {
            'adp_variance': 8,
            'reach_threshold': 12,
            'catcher_rounds': [5, 6, 14, 15],
            'closer_priority': 0.3,
            'description': 'Follows NFBC ADP consensus'
        },
        CutlineArchetype.CATCHER_EARLY: {
            'adp_variance': 12,
            'reach_threshold': 18,
            'catcher_rounds': [3, 4, 10, 11],  # Aggressive on catchers
            'closer_priority': 0.2,
            'description': 'Prioritizes catchers early'
        },
        CutlineArchetype.RELIEVER_HUNTER: {
            'adp_variance': 10,
            'reach_threshold': 15,
            'catcher_rounds': [6, 7, 15, 16],
            'closer_priority': 0.6,  # Heavy closer investment
            'description': 'Targets elite closers for saves'
        },
        CutlineArchetype.POINTS_CHASER: {
            'adp_variance': 15,
            'reach_threshold': 20,
            'catcher_rounds': [5, 6, 14, 15],
            'closer_priority': 0.35,
            'description': 'Chases projected points regardless of position'
        },
        CutlineArchetype.VARIANCE_MAX: {
            'adp_variance': 20,
            'reach_threshold': 25,
            'catcher_rounds': [7, 8, 16, 17],
            'closer_priority': 0.25,
            'description': 'Maximizes upside and weekly ceilings'
        },
        CutlineArchetype.VOLUME_BASED: {
            'adp_variance': 10,
            'reach_threshold': 12,
            'catcher_rounds': [4, 5, 13, 14],
            'closer_priority': 0.4,
            'description': 'Prioritizes playing time and IP'
        },
        CutlineArchetype.BALANCED: {
            'adp_variance': 10,
            'reach_threshold': 15,
            'catcher_rounds': [5, 6, 14, 15],
            'closer_priority': 0.3,
            'description': 'Balanced position distribution'
        },
    }

    def __init__(self, user_position: int = 1):
        """
        Initialize Cutline draft engine.

        Args:
            user_position: User's draft position (1-10)
        """
        self.user_position = min(max(1, user_position), self.NUM_TEAMS)
        self.teams: List[CutlineTeam] = []
        self.available_players: List[CutlinePlayer] = []
        self.picks: List[CutlineDraftPick] = []
        self.current_round = 1
        self.current_pick = 1

        self._load_rankings()
        self._setup_teams()

        logger.info(f"Cutline draft initialized: User at position {user_position}")

    def _load_rankings(self):
        """Load player rankings with detailed positions.

        Merges Cutline-specific rankings with ADP fallback to ensure
        enough players for a complete draft (420+ for 10 teams x 42 rounds).
        Also loads proprietary EV rankings for value comparison.
        """
        data_dir = Path(__file__).parent.parent.parent / 'data'

        # Load primary Cutline rankings (draft order)
        cutline_path = data_dir / 'cutline_rankings.json'
        adp_path = data_dir / 'adp_rankings_2025.json'
        ev_path = data_dir / 'cutline_ev_rankings.json'

        cutline_data = None
        adp_data = None

        if cutline_path.exists():
            with open(cutline_path, 'r') as f:
                cutline_data = json.load(f)
                logger.info(f"Loaded {len(cutline_data.get('rankings', []))} Cutline rankings")

        if adp_path.exists():
            with open(adp_path, 'r') as f:
                adp_data = json.load(f)
                logger.info(f"Loaded {len(adp_data.get('rankings', []))} ADP rankings as fallback")

        if not cutline_data and not adp_data:
            raise FileNotFoundError("No rankings files found")

        # Load proprietary EV rankings (personal value assessment)
        ev_rankings_by_name = {}
        if ev_path.exists():
            with open(ev_path, 'r') as f:
                ev_data = json.load(f)
                for p in ev_data.get('rankings', []):
                    # Normalize name for matching
                    name_key = self._normalize_name(p['player_name'])
                    ev_rankings_by_name[name_key] = p['ev_rank']
                logger.info(f"Loaded {len(ev_rankings_by_name)} proprietary EV rankings")

        # Build player list - Cutline rankings first, then ADP fallback
        self.available_players = []
        seen_player_ids = set()
        seen_player_names = set()

        # Process Cutline rankings first (these are the authoritative Cutline ranks)
        if cutline_data:
            for p in cutline_data.get('rankings', []):
                position = p.get('position', 'UTIL')
                detailed_pos = self._get_detailed_position(p, position)

                # Generate unique ID from name if not provided
                player_id = p.get('db_player_id', p.get('player_id', 0))
                if player_id == 0:
                    player_id = hash(p['player_name'].lower()) & 0xFFFFFF

                # Estimate bestball_score from rank if not provided
                # Top players ~60, decreases by rank
                cutline_score = p.get('bestball_score', 0)
                if cutline_score == 0:
                    rank = p['rank']
                    cutline_score = max(65.0 - (rank * 0.08), 20.0)

                # Look up proprietary EV rank by normalized name
                name_key = self._normalize_name(p['player_name'])
                ev_rank = ev_rankings_by_name.get(name_key, 999)

                player = CutlinePlayer(
                    rank=p['rank'],
                    player_id=player_id,
                    player_name=p['player_name'],
                    position=detailed_pos,
                    team=p.get('team', ''),
                    ev_rank=ev_rank,  # Use proprietary EV rank
                    bestball_score=cutline_score,
                )
                self.available_players.append(player)
                seen_player_ids.add(player_id)
                seen_player_names.add(p['player_name'].lower())

        # Add ADP players not in Cutline rankings (for draft depth)
        if adp_data:
            next_rank = len(self.available_players) + 1
            for p in adp_data.get('rankings', []):
                player_id = p.get('db_player_id', p.get('player_id', 0))
                player_name = p['player_name'].lower()

                # Skip if already have this player
                if player_id in seen_player_ids or player_name in seen_player_names:
                    continue

                position = p.get('position', 'UTIL')
                detailed_pos = self._get_detailed_position(p, position)

                # Use EV rankings if available, otherwise estimate from ADP rank
                ev_rank, bb_score = ev_rankings.get(player_id, (999, 0))
                if bb_score == 0:
                    # Estimate a modest score for ADP-only players
                    bb_score = max(30.0 - (next_rank - 200) * 0.1, 20.0)

                player = CutlinePlayer(
                    rank=next_rank,
                    player_id=player_id,
                    player_name=p['player_name'],
                    position=detailed_pos,
                    team=p.get('team', ''),
                    ev_rank=ev_rank if ev_rank != 999 else next_rank + 200,
                    bestball_score=bb_score,
                )
                self.available_players.append(player)
                seen_player_ids.add(player_id)
                seen_player_names.add(player_name)
                next_rank += 1

        logger.info(f"Loaded {len(self.available_players)} total players for Cutline draft")

    def _normalize_name(self, name: str) -> str:
        """
        Normalize player name for matching between ranking systems.

        Handles:
        - Case normalization
        - Accent removal (José -> Jose)
        - Suffix variations (Jr., Jr, II, etc.)
        - Common name variations
        """
        import unicodedata

        # Lowercase
        name = name.lower().strip()

        # Remove accents (José -> Jose, Ramírez -> Ramirez)
        name = unicodedata.normalize('NFKD', name)
        name = ''.join(c for c in name if not unicodedata.combining(c))

        # Standardize suffixes
        name = name.replace(' jr.', ' jr').replace(' sr.', ' sr')
        name = name.replace(' ii', '').replace(' iii', '').replace(' iv', '')

        # Remove periods and extra spaces
        name = name.replace('.', '').replace("'", '')
        name = ' '.join(name.split())

        return name

    def _get_detailed_position(self, player_data: dict, simplified_pos: str) -> str:
        """
        Get detailed position from player data.

        Maps IF -> specific infield position (1B, 2B, 3B, SS)
        Uses player name patterns or defaults.
        """
        # If already detailed, use it
        if simplified_pos in ['C', '1B', '2B', '3B', 'SS', 'P', 'SP', 'RP']:
            return simplified_pos

        if simplified_pos in ['OF', 'LF', 'CF', 'RF']:
            return 'OF'

        if simplified_pos == 'P':
            return 'P'

        # For IF, try to determine specific position from name patterns
        # This is a fallback - ideally we'd have detailed position data
        name = player_data.get('player_name', '').lower()

        # Known position mappings for common players
        # (In production, this would come from database)
        known_positions = {
            'bobby witt': 'SS',
            'francisco lindor': 'SS',
            'corey seager': 'SS',
            'elly de la cruz': 'SS',
            'trea turner': 'SS',
            'wander franco': 'SS',
            'matt olson': '1B',
            'freddie freeman': '1B',
            'vladimir guerrero': '1B',
            'pete alonso': '1B',
            'jose ramirez': '3B',
            'manny machado': '3B',
            'rafael devers': '3B',
            'austin riley': '3B',
            'marcus semien': '2B',
            'ozzie albies': '2B',
            'ketel marte': '2B',
            'jose altuve': '2B',
        }

        for player_key, pos in known_positions.items():
            if player_key in name:
                return pos

        # Default IF to 2B (most common flex eligible)
        if simplified_pos == 'IF':
            return '2B'

        return 'UTIL'

    def _setup_teams(self):
        """Set up 10 teams with varied archetypes."""
        # Available archetypes for AI
        ai_archetypes = [
            CutlineArchetype.NFBC_CONSENSUS,
            CutlineArchetype.NFBC_CONSENSUS,  # More common
            CutlineArchetype.CATCHER_EARLY,
            CutlineArchetype.RELIEVER_HUNTER,
            CutlineArchetype.POINTS_CHASER,
            CutlineArchetype.VARIANCE_MAX,
            CutlineArchetype.VOLUME_BASED,
            CutlineArchetype.BALANCED,
            CutlineArchetype.BALANCED,
        ]

        random.shuffle(ai_archetypes)

        for i in range(self.NUM_TEAMS):
            team_id = i + 1
            if team_id == self.user_position:
                archetype = CutlineArchetype.USER
                name = "Your Team"
            else:
                archetype = ai_archetypes.pop() if ai_archetypes else CutlineArchetype.BALANCED
                name = f"Team {team_id} ({archetype.value})"

            self.teams.append(CutlineTeam(
                team_id=team_id,
                name=name,
                archetype=archetype
            ))

    def get_pick_order(self, round_num: int) -> List[int]:
        """Get pick order for a round (snake draft)."""
        order = list(range(1, self.NUM_TEAMS + 1))
        if round_num % 2 == 0:
            order.reverse()
        return order

    def get_overall_pick(self, round_num: int, pick_in_round: int) -> int:
        """Calculate overall pick number."""
        return (round_num - 1) * self.NUM_TEAMS + pick_in_round

    def get_current_team(self) -> CutlineTeam:
        """Get the team currently on the clock."""
        order = self.get_pick_order(self.current_round)
        team_id = order[self.current_pick - 1]
        return self.teams[team_id - 1]

    def is_user_pick(self) -> bool:
        """Check if it's the user's turn to pick."""
        return self.get_current_team().archetype == CutlineArchetype.USER

    def is_draft_complete(self) -> bool:
        """Check if draft is finished."""
        return self.current_round > self.NUM_ROUNDS

    def make_pick(self, player: CutlinePlayer) -> CutlineDraftPick:
        """Execute a draft pick."""
        if player not in self.available_players:
            raise ValueError(f"Player {player.player_name} is not available")

        team = self.get_current_team()
        overall = self.get_overall_pick(self.current_round, self.current_pick)

        pick = CutlineDraftPick(
            round_num=self.current_round,
            pick_num=self.current_pick,
            overall_pick=overall,
            team_id=team.team_id,
            player_id=player.player_id,
            player_name=player.player_name,
            position=player.position,
            team_abbr=player.team,
            rank=player.rank,
            ev_rank=player.ev_rank
        )

        self.available_players.remove(player)
        team.roster.append(pick)
        self.picks.append(pick)

        self._advance_pick()

        return pick

    def _advance_pick(self):
        """Move to the next pick in the draft."""
        self.current_pick += 1
        if self.current_pick > self.NUM_TEAMS:
            self.current_pick = 1
            self.current_round += 1

    def _check_adp_capture(self, overall_pick: int, team: CutlineTeam) -> Optional[CutlinePlayer]:
        """
        Check for major ADP falls - players dropping significantly below value.

        Cutline-specific: Prioritize catchers and closers that fall.
        """
        # Round-based value multiplier
        if self.current_round <= 5:
            round_mult = 2.0
            min_fall = 20
        elif self.current_round <= 12:
            round_mult = 1.5
            min_fall = 30
        elif self.current_round <= 24:
            round_mult = 1.2
            min_fall = 40
        else:
            round_mult = 1.0
            min_fall = 50

        best_capture = None
        best_value = 0

        needs = team.get_roster_needs()

        for player in self.available_players:
            fall = overall_pick - player.rank
            if fall < min_fall:
                continue

            pos_cat = POSITION_TO_CATEGORY.get(player.position, 'UTIL')

            # Position fit bonus
            if needs.get(pos_cat, 0) > 0:
                pos_mult = 1.0
            else:
                pos_mult = 0.6

            # Cutline-specific: Catchers and closers get bonus
            position_bonus = 1.0
            if player.position == 'C':
                position_bonus = 1.3  # Catchers are premium
            elif player.position in ['RP', 'P']:
                # Check if likely a closer (would need more data)
                position_bonus = 1.1

            value = fall * round_mult * pos_mult * position_bonus

            # Elite player bonus
            if player.rank <= 30:
                value *= 1.25
            elif player.rank <= 60:
                value *= 1.1

            if value > 60 and value > best_value:
                best_value = value
                best_capture = player

        return best_capture

    def _ai_needs_catcher(self, team: CutlineTeam, config: dict) -> bool:
        """Check if AI should prioritize a catcher this round."""
        counts = team.get_position_counts()
        catcher_rounds = config.get('catcher_rounds', [5, 6, 14, 15])

        # Need first catcher?
        if counts.get('C', 0) == 0 and self.current_round in catcher_rounds[:2]:
            return True

        # Need second catcher?
        if counts.get('C', 0) == 1 and self.current_round in catcher_rounds[2:]:
            return True

        # Emergency: must have 2 catchers by round 20
        if counts.get('C', 0) < 2 and self.current_round >= 20:
            return True

        return False

    def _ai_needs_closer(self, team: CutlineTeam, config: dict) -> bool:
        """Check if AI should prioritize a closer."""
        # Count RP/closers (simplified - would need more data)
        pitcher_count = team.get_position_counts().get('P', 0)
        closer_priority = config.get('closer_priority', 0.3)

        # More likely to grab closer in mid rounds
        if 8 <= self.current_round <= 20:
            return random.random() < closer_priority

        return False

    def ai_select_player(self, team: CutlineTeam) -> CutlinePlayer:
        """
        AI selects a player based on Cutline-specific strategy.
        """
        archetype = team.archetype
        config = self.ARCHETYPE_CONFIGS.get(archetype, self.ARCHETYPE_CONFIGS[CutlineArchetype.BALANCED])
        overall_pick = self.get_overall_pick(self.current_round, self.current_pick)

        needs = team.get_roster_needs()
        rounds_left = self.NUM_ROUNDS - self.current_round + 1

        # ============================================================
        # 1. Check for ADP capture opportunities
        # ============================================================
        capture = self._check_adp_capture(overall_pick, team)
        if capture:
            logger.debug(f"{team.name} ADP capture: {capture.player_name} "
                        f"(rank {capture.rank} at pick {overall_pick})")
            return capture

        # ============================================================
        # 2. Position-based targeting (Cutline meta)
        # ============================================================

        # Catcher priority (2 required, premium in Cutline)
        if self._ai_needs_catcher(team, config):
            catchers = [p for p in self.available_players if p.position == 'C']
            if catchers:
                # Get best available catcher within reach
                reach = config.get('reach_threshold', 15)
                reachable = [c for c in catchers if c.rank <= overall_pick + reach]
                if reachable:
                    return min(reachable, key=lambda x: x.rank)
                # If none in range, take best available
                return min(catchers, key=lambda x: x.rank)

        # Closer priority (Saves worth +8 in Cutline)
        if self._ai_needs_closer(team, config):
            # Would need RP classification - simplified here
            pass

        # ============================================================
        # 3. Standard ADP-based selection with variance
        # ============================================================

        adp_variance = config.get('adp_variance', 10)
        min_rank = max(1, overall_pick - adp_variance)
        max_rank = min(500, overall_pick + adp_variance * 2)

        candidates = [p for p in self.available_players
                     if min_rank <= p.rank <= max_rank]

        if not candidates:
            candidates = self.available_players[:30]

        # Filter by position needs (late rounds)
        if self.current_round >= 25:
            needed_positions = [pos for pos, need in needs.items() if need > 0]
            pos_filtered = [p for p in candidates
                          if POSITION_TO_CATEGORY.get(p.position, 'UTIL') in needed_positions]
            if pos_filtered:
                candidates = pos_filtered

        # ============================================================
        # 4. Force position filling when running out of rounds
        # ============================================================

        # Must have 2 catchers
        if needs.get('C', 0) > 0:
            c_needed = needs['C']
            if rounds_left <= c_needed + 2:
                catchers = [p for p in self.available_players if p.position == 'C']
                if catchers:
                    return min(catchers, key=lambda x: x.rank)

        # Need pitcher depth
        if needs.get('P', 0) > 0 and rounds_left <= needs['P'] + 1:
            pitchers = [p for p in self.available_players if p.position in ['P', 'SP', 'RP']]
            if pitchers:
                return min(pitchers, key=lambda x: x.rank)

        # ============================================================
        # 5. Final selection with slight randomness
        # ============================================================

        candidates = sorted(candidates, key=lambda x: x.rank)

        if len(candidates) > 3:
            # Weight toward better ADP but allow some variance
            weights = [1.0 / (i + 1) ** 0.5 for i in range(min(len(candidates), 6))]
            total = sum(weights)
            weights = [w / total for w in weights]

            r = random.random()
            cumulative = 0
            for i, w in enumerate(weights):
                cumulative += w
                if r <= cumulative:
                    return candidates[i]

        return min(candidates, key=lambda x: x.rank)

    def simulate_pick(self) -> Optional[CutlineDraftPick]:
        """Simulate a single AI pick."""
        if self.is_draft_complete():
            return None

        team = self.get_current_team()

        if team.archetype == CutlineArchetype.USER:
            return None

        player = self.ai_select_player(team)
        return self.make_pick(player)

    def simulate_until_user_pick(self) -> List[CutlineDraftPick]:
        """Simulate all picks until it's the user's turn."""
        picks_made = []

        while not self.is_draft_complete():
            if self.is_user_pick():
                break

            pick = self.simulate_pick()
            if pick:
                picks_made.append(pick)

        return picks_made

    def user_make_pick(self, player_id: int) -> Optional[CutlineDraftPick]:
        """Make a pick for the user."""
        if not self.is_user_pick():
            return None

        player = next(
            (p for p in self.available_players if p.player_id == player_id),
            None
        )

        if not player:
            raise ValueError(f"Player {player_id} is not available")

        return self.make_pick(player)

    def get_draft_state(self) -> Dict:
        """Get current draft state for UI."""
        team = self.get_current_team()
        user_team = next(t for t in self.teams if t.archetype == CutlineArchetype.USER)

        return {
            'format': 'cutline',
            'num_teams': self.NUM_TEAMS,
            'num_rounds': self.NUM_ROUNDS,
            'current_round': self.current_round,
            'current_pick': self.current_pick,
            'overall_pick': self.get_overall_pick(self.current_round, self.current_pick),
            'is_user_pick': self.is_user_pick(),
            'current_team': {
                'id': team.team_id,
                'name': team.name,
                'archetype': team.archetype.value,
                'position_counts': team.get_position_counts(),
                'roster': [
                    {
                        'round': p.round_num,
                        'player_id': p.player_id,
                        'player_name': p.player_name,
                        'position': p.position,
                        'team': p.team_abbr,
                        'rank': p.rank,
                        'ev_rank': p.ev_rank,
                    }
                    for p in team.roster
                ]
            },
            'user_roster': [
                {
                    'round': p.round_num,
                    'player_id': p.player_id,
                    'player_name': p.player_name,
                    'position': p.position,
                    'team': p.team_abbr,
                    'rank': p.rank,
                    'ev_rank': p.ev_rank,
                }
                for p in user_team.roster
            ],
            'user_position_counts': user_team.get_position_counts(),
            'user_needs': user_team.get_roster_needs(),
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
                    'rank': p.rank,
                }
                for p in self.picks[-10:]
            ],
            'lineup_requirements': CUTLINE_LINEUP_SLOTS,
        }

    def get_available_players_by_position(self, position: str = None) -> List[Dict]:
        """Get available players, optionally filtered by position."""
        players = self.available_players

        if position:
            if position in ['MI']:
                players = [p for p in players if p.position in ['2B', 'SS']]
            elif position in ['CI']:
                players = [p for p in players if p.position in ['1B', '3B']]
            elif position == 'UTIL':
                players = [p for p in players if p.position not in ['P', 'SP', 'RP']]
            else:
                cat = POSITION_TO_CATEGORY.get(position, position)
                players = [p for p in players
                          if POSITION_TO_CATEGORY.get(p.position, p.position) == cat]

        return [
            {
                'player_id': p.player_id,
                'player_name': p.player_name,
                'position': p.position,
                'team': p.team,
                'rank': p.rank,
                'ev_rank': p.ev_rank,
                'bestball_score': round(p.bestball_score, 2),
            }
            for p in sorted(players, key=lambda x: x.rank)
        ]

    def get_user_roster(self) -> List[CutlineDraftPick]:
        """Get the user's drafted roster."""
        user_team = next(t for t in self.teams if t.archetype == CutlineArchetype.USER)
        return user_team.roster

    def get_all_rosters(self) -> Dict[int, List[CutlineDraftPick]]:
        """Get all teams' rosters."""
        return {team.team_id: team.roster for team in self.teams}

    def export_roster_for_simulation(self) -> List[Dict]:
        """Export user roster in format for Monte Carlo simulation."""
        roster = self.get_user_roster()
        return [
            {
                'player_id': p.player_id,
                'player_name': p.player_name,
                'position': p.position,
                'team': p.team_abbr,
            }
            for p in roster
        ]


def run_cutline_simulation(user_position: int = 1) -> CutlineDraftEngine:
    """
    Run a complete Cutline draft with AI making all picks.
    """
    engine = CutlineDraftEngine(user_position=0)

    # Override user team to be AI
    for team in engine.teams:
        if team.archetype == CutlineArchetype.USER:
            team.archetype = CutlineArchetype.BALANCED
            team.name = f"Team {team.team_id} (balanced)"

    while not engine.is_draft_complete():
        engine.simulate_pick()

    return engine


if __name__ == "__main__":
    # Test the draft engine
    import sys

    logging.basicConfig(level=logging.INFO)

    print("NFBC Cutline Championship Draft Simulator")
    print("=" * 50)
    print(f"Teams: {CUTLINE_NUM_TEAMS}")
    print(f"Rounds: {CUTLINE_ROSTER_SIZE}")
    print(f"Lineup slots: {CUTLINE_LINEUP_SLOTS}")
    print()

    # Run a test simulation
    print("Running test simulation...")
    engine = run_cutline_simulation()

    print("\nDraft complete!")
    print(f"Total picks: {len(engine.picks)}")

    # Show sample roster
    for team in engine.teams[:3]:
        print(f"\n{team.name}:")
        print(f"  Position counts: {team.get_position_counts()}")
        print(f"  Top 5 picks:")
        for pick in team.roster[:5]:
            print(f"    R{pick.round_num}: {pick.player_name} ({pick.position}) - Rank {pick.rank}")

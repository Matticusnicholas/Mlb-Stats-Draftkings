"""
Main GUI window for MLB DraftKings Volatility Analyzer with Best Ball support.
"""
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from typing import List, Dict, Optional
import logging
import threading
import numpy as np

try:
    import customtkinter as ctk
    CTK_AVAILABLE = True
except ImportError:
    CTK_AVAILABLE = False
    print("CustomTkinter not available, using standard tkinter")

from ..database.db_manager import DatabaseManager
from ..analytics.volatility_analyzer import VolatilityAnalyzer
from ..analytics.weekly_analyzer import WeeklyAnalyzer
from ..analytics.roster_optimizer import RosterOptimizer

logger = logging.getLogger(__name__)


class MLBVolatilityGUI:
    """Main GUI application for MLB volatility analysis with Best Ball support."""

    def __init__(self, db_path: str = "data/mlb_stats.db"):
        """
        Initialize GUI application.

        Args:
            db_path: Path to database file
        """
        self.db = DatabaseManager(db_path)
        self.analyzer = VolatilityAnalyzer(self.db)
        self.weekly_analyzer = WeeklyAnalyzer(self.db)
        self.optimizer = RosterOptimizer(self.db)

        # Use customtkinter if available, else standard tkinter
        if CTK_AVAILABLE:
            ctk.set_appearance_mode("dark")
            ctk.set_default_color_theme("blue")
            self.root = ctk.CTk()
        else:
            self.root = tk.Tk()

        self.root.title("MLB DraftKings Best Ball Analyzer")
        self.root.geometry("1600x850")

        self.current_player_pool = []
        self.current_roster = None
        self.analysis_mode = "bestball"  # "bestball" or "daily"
        self.sort_states = {}  # Track sort state for each column: None, 'desc', 'asc'
        self.current_sort_column = None

        self._create_widgets()

    def _create_widgets(self):
        """Create and layout all GUI widgets."""
        # Main container
        main_container = ttk.Frame(self.root, padding="10")
        main_container.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_container.columnconfigure(1, weight=1)
        main_container.rowconfigure(1, weight=1)

        # Title
        title_label = ttk.Label(
            main_container,
            text="MLB DraftKings Best Ball Analyzer",
            font=("Arial", 18, "bold")
        )
        title_label.grid(row=0, column=0, columnspan=2, pady=10)

        # Left panel: Filters and controls
        left_panel = ttk.LabelFrame(main_container, text="Filters & Controls", padding="10")
        left_panel.grid(row=1, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), padx=(0, 5))

        self._create_filters(left_panel)

        # Right panel: Player list and roster
        right_panel = ttk.Frame(main_container)
        right_panel.grid(row=1, column=1, sticky=(tk.W, tk.E, tk.N, tk.S))
        right_panel.rowconfigure(0, weight=1)
        right_panel.rowconfigure(1, weight=1)
        right_panel.columnconfigure(0, weight=1)

        self._create_player_list(right_panel)
        self._create_roster_panel(right_panel)

        # Status bar
        self.status_var = tk.StringVar(value="Ready - Best Ball Mode (Rolling 7-Day Windows)")
        status_bar = ttk.Label(
            main_container,
            textvariable=self.status_var,
            relief=tk.SUNKEN,
            anchor=tk.W
        )
        status_bar.grid(row=2, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(5, 0))

    def _create_filters(self, parent):
        """Create filter controls."""
        row = 0

        # Analysis Mode Selector
        ttk.Label(parent, text="Analysis Mode:", font=("Arial", 11, "bold")).grid(
            row=row, column=0, sticky=tk.W, pady=5
        )
        row += 1

        self.mode_var = tk.StringVar(value="bestball")
        mode_frame = ttk.Frame(parent)
        mode_frame.grid(row=row, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=5)

        ttk.Radiobutton(
            mode_frame,
            text="Best Ball (Weekly)",
            variable=self.mode_var,
            value="bestball",
            command=self._on_mode_change
        ).pack(side=tk.LEFT, padx=5)

        ttk.Radiobutton(
            mode_frame,
            text="Daily Volatility",
            variable=self.mode_var,
            value="daily",
            command=self._on_mode_change
        ).pack(side=tk.LEFT, padx=5)
        row += 1

        # Separator
        ttk.Separator(parent, orient=tk.HORIZONTAL).grid(
            row=row, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=10
        )
        row += 1

        # Stats type
        ttk.Label(parent, text="Position Type:").grid(row=row, column=0, sticky=tk.W, pady=5)
        self.stats_type_var = tk.StringVar(value="batting")
        stats_type_combo = ttk.Combobox(
            parent,
            textvariable=self.stats_type_var,
            values=["batting", "pitching"],
            state="readonly",
            width=15
        )
        stats_type_combo.grid(row=row, column=1, sticky=(tk.W, tk.E), pady=5)
        row += 1

        # Minimum games
        ttk.Label(parent, text="Min Games:").grid(row=row, column=0, sticky=tk.W, pady=5)
        self.min_games_var = tk.IntVar(value=20)
        min_games_spin = ttk.Spinbox(parent, from_=5, to=100, textvariable=self.min_games_var, width=15)
        min_games_spin.grid(row=row, column=1, sticky=(tk.W, tk.E), pady=5)
        row += 1

        # Min threshold score (changes based on mode)
        self.threshold_label = ttk.Label(parent, text="Min BB Score:")
        self.threshold_label.grid(row=row, column=0, sticky=tk.W, pady=5)
        self.min_threshold_var = tk.DoubleVar(value=0.0)
        threshold_spin = ttk.Spinbox(
            parent,
            from_=0.0,
            to=100.0,
            increment=5.0,
            textvariable=self.min_threshold_var,
            width=15
        )
        threshold_spin.grid(row=row, column=1, sticky=(tk.W, tk.E), pady=5)
        row += 1

        # Sort by (changes based on mode)
        ttk.Label(parent, text="Sort By:").grid(row=row, column=0, sticky=tk.W, pady=5)
        self.sort_by_var = tk.StringVar(value="bestball_score")
        self.sort_combo = ttk.Combobox(
            parent,
            textvariable=self.sort_by_var,
            values=["bestball_score", "best_week", "tear3_rate", "tear4_rate", "boom_week_rate"],
            state="readonly",
            width=15
        )
        self.sort_combo.grid(row=row, column=1, sticky=(tk.W, tk.E), pady=5)
        row += 1

        # Load players button
        self.load_btn = ttk.Button(
            parent,
            text="Load Best Ball Players",
            command=self._load_player_pool
        )
        self.load_btn.grid(row=row, column=0, columnspan=2, pady=10, sticky=(tk.W, tk.E))
        row += 1

        # Separator
        ttk.Separator(parent, orient=tk.HORIZONTAL).grid(
            row=row, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=10
        )
        row += 1

        # Info section
        self.info_label = ttk.Label(
            parent,
            text="Best Ball Mode:\n• Rolling 7-day windows\n• TEAR metrics\n• Weekly ceilings",
            font=("Arial", 9),
            justify=tk.LEFT
        )
        self.info_label.grid(row=row, column=0, columnspan=2, pady=5, sticky=tk.W)
        row += 1

        # Separator
        ttk.Separator(parent, orient=tk.HORIZONTAL).grid(
            row=row, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=10
        )
        row += 1

        # Database stats
        ttk.Label(parent, text="Database Info", font=("Arial", 12, "bold")).grid(
            row=row, column=0, columnspan=2, pady=5
        )
        row += 1

        db_stats_btn = ttk.Button(
            parent,
            text="Show Database Stats",
            command=self._show_db_stats
        )
        db_stats_btn.grid(row=row, column=0, columnspan=2, pady=5, sticky=(tk.W, tk.E))
        row += 1

    def _on_mode_change(self):
        """Handle analysis mode change."""
        self.analysis_mode = self.mode_var.get()

        if self.analysis_mode == "bestball":
            self.threshold_label.config(text="Min BB Score:")
            self.sort_combo.configure(values=[
                "bestball_score", "useful_points_total", "useful_weeks_count", "useful_points_per_week",
                "best_week", "tear3_rate", "tear4_rate", "boom_week_rate"
            ])
            self.sort_by_var.set("bestball_score")
            self.load_btn.config(text="Load Best Ball Players")
            self.info_label.config(
                text="Best Ball Mode:\n• Rolling 7-day windows\n• USEFUL metrics (concentration)\n• TEAR hot streaks"
            )
            self.status_var.set("Best Ball Mode (Rolling 7-Day Windows)")

            # Update tree columns for Best Ball
            self._update_tree_columns_bestball()

        else:  # daily mode
            self.threshold_label.config(text="Min Variance Score:")
            self.sort_combo.configure(values=[
                "variance_score", "upside_score", "mean_points", "max_points", "boom_rate"
            ])
            self.sort_by_var.set("variance_score")
            self.load_btn.config(text="Load Player Pool")
            self.info_label.config(
                text="Daily Mode:\n• Game-by-game analysis\n• Standard deviation\n• Spike rates"
            )
            self.status_var.set("Daily Volatility Mode")

            # Update tree columns for Daily
            self._update_tree_columns_daily()

        # Clear current player pool
        self.current_player_pool = []
        for item in self.player_tree.get_children():
            self.player_tree.delete(item)

    def _update_tree_columns_bestball(self):
        """Update tree columns for Best Ball mode."""
        # Clear existing
        for item in self.player_tree.get_children():
            self.player_tree.delete(item)

        # Reconfigure columns - added Draft status
        self.player_tree.configure(columns=(
            "Draft", "Name", "BB Score", "Useful Pts", "Useful Wks", "Pts/Wk", "Best Week", "Boom%", "TEAR3", "TEAR4"
        ))

        # Set headings with click-to-sort
        self.player_tree.heading("Draft", text="☑", command=lambda: None)  # Click on row to toggle
        self.player_tree.heading("Name", text="Player Name",
                                command=lambda: self._sort_by_column("Name", 1, is_numeric=False))
        self.player_tree.heading("BB Score", text="BB Score",
                                command=lambda: self._sort_by_column("BB Score", 2))
        self.player_tree.heading("Useful Pts", text="Useful Pts",
                                command=lambda: self._sort_by_column("Useful Pts", 3))
        self.player_tree.heading("Useful Wks", text="Useful Wks",
                                command=lambda: self._sort_by_column("Useful Wks", 4))
        self.player_tree.heading("Pts/Wk", text="Pts/Wk",
                                command=lambda: self._sort_by_column("Pts/Wk", 5))
        self.player_tree.heading("Best Week", text="Best Week",
                                command=lambda: self._sort_by_column("Best Week", 6))
        self.player_tree.heading("Boom%", text="Boom%",
                                command=lambda: self._sort_by_column("Boom%", 7))
        self.player_tree.heading("TEAR3", text="TEAR3",
                                command=lambda: self._sort_by_column("TEAR3", 8))
        self.player_tree.heading("TEAR4", text="TEAR4",
                                command=lambda: self._sort_by_column("TEAR4", 9))

        # Set column widths (wider to accommodate percentile bars)
        self.player_tree.column("Draft", width=40, anchor="center")
        self.player_tree.column("Name", width=150)
        self.player_tree.column("BB Score", width=120)
        self.player_tree.column("Useful Pts", width=120)
        self.player_tree.column("Useful Wks", width=110)
        self.player_tree.column("Pts/Wk", width=110)
        self.player_tree.column("Best Week", width=120)
        self.player_tree.column("Boom%", width=110)
        self.player_tree.column("TEAR3", width=110)
        self.player_tree.column("TEAR4", width=110)

    def _update_tree_columns_daily(self):
        """Update tree columns for Daily mode."""
        # Clear existing
        for item in self.player_tree.get_children():
            self.player_tree.delete(item)

        # Reconfigure columns
        self.player_tree.configure(columns=(
            "Name", "Games", "Mean", "Std Dev", "Variance", "Upside", "Max", "Boom%"
        ))

        # Set headings with click-to-sort
        self.player_tree.heading("Name", text="Player Name",
                                command=lambda: self._sort_by_column("Name", 0, is_numeric=False))
        self.player_tree.heading("Games", text="Games",
                                command=lambda: self._sort_by_column("Games", 1))
        self.player_tree.heading("Mean", text="Mean Pts",
                                command=lambda: self._sort_by_column("Mean", 2))
        self.player_tree.heading("Std Dev", text="Std Dev",
                                command=lambda: self._sort_by_column("Std Dev", 3))
        self.player_tree.heading("Variance", text="Var Score",
                                command=lambda: self._sort_by_column("Variance", 4))
        self.player_tree.heading("Upside", text="Upside",
                                command=lambda: self._sort_by_column("Upside", 5))
        self.player_tree.heading("Max", text="Max Pts",
                                command=lambda: self._sort_by_column("Max", 6))
        self.player_tree.heading("Boom%", text="Boom %",
                                command=lambda: self._sort_by_column("Boom%", 7))

        # Set column widths (wider to accommodate percentile bars)
        self.player_tree.column("Name", width=150)
        self.player_tree.column("Games", width=90)
        self.player_tree.column("Mean", width=110)
        self.player_tree.column("Std Dev", width=110)
        self.player_tree.column("Variance", width=120)
        self.player_tree.column("Upside", width=110)
        self.player_tree.column("Max", width=110)
        self.player_tree.column("Boom%", width=110)

    def _create_player_list(self, parent):
        """Create player list view."""
        player_frame = ttk.LabelFrame(parent, text="Player Pool", padding="5")
        player_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), pady=(0, 5))
        player_frame.rowconfigure(0, weight=1)
        player_frame.columnconfigure(0, weight=1)

        # Create treeview (will be configured based on mode)
        # Use "tree headings" to show +/- expand buttons and data
        self.player_tree = ttk.Treeview(player_frame, show="tree headings", height=15)

        # Configure tree column (the one with +/- buttons)
        self.player_tree.column("#0", width=30, minwidth=30, stretch=False)  # Just enough for +/- button

        # Configure color tags for percentile-based coloring
        self._configure_color_tags()

        # Initial setup for Best Ball mode
        self._update_tree_columns_bestball()

        # Scrollbar
        scrollbar = ttk.Scrollbar(player_frame, orient=tk.VERTICAL, command=self.player_tree.yview)
        self.player_tree.configure(yscrollcommand=scrollbar.set)

        self.player_tree.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        scrollbar.grid(row=0, column=1, sticky=(tk.N, tk.S))

        # Store player data by tree item ID for expandable rows
        self.player_data_by_item = {}

        # Track drafted players
        self.drafted_players = set()

        # Single-click on Draft column to toggle draft status
        self.player_tree.bind("<Button-1>", self._handle_click)

        # Double-click to toggle expandable details
        self.player_tree.bind("<Double-1>", self._toggle_player_details)

        # Store expanded items
        self.expanded_items = set()

    def _configure_color_tags(self):
        """Configure color tags for percentile-based visualization."""
        # Gradient from blue (low) to white (mid) to red (high) like Baseball Savant
        # We'll use row-level background as a subtle base, but main visualization is in the bars
        self.player_tree.tag_configure('percentile_90_100', background='#ffe6e6')  # Very light red
        self.player_tree.tag_configure('percentile_80_90', background='#fff2f2')   # Lighter red
        self.player_tree.tag_configure('percentile_60_80', background='#fffafa')   # Very light
        self.player_tree.tag_configure('percentile_40_60', background='#ffffff')   # White
        self.player_tree.tag_configure('percentile_20_40', background='#f0f8ff')   # Very light blue
        self.player_tree.tag_configure('percentile_0_20', background='#e6f2ff')    # Light blue

        # Drafted player tag (gray fade with strikethrough look)
        self.player_tree.tag_configure('drafted', background='#d0d0d0', foreground='#666666')

    def _calculate_percentiles(self, column_index: int) -> Dict:
        """
        Calculate percentiles for a specific column.

        Args:
            column_index: Index of the column to calculate percentiles for

        Returns:
            Dictionary mapping item IDs to percentile values
        """
        values = []
        item_values = {}

        for item in self.player_tree.get_children():
            try:
                val_str = self.player_tree.item(item)['values'][column_index]
                # Convert to float, removing any non-numeric characters
                val = float(str(val_str).replace('%', '').replace(',', ''))
                values.append(val)
                item_values[item] = val
            except (ValueError, IndexError):
                continue

        if not values:
            return {}

        # Calculate percentile for each item
        values_array = np.array(values)
        percentiles = {}

        for item, val in item_values.items():
            # Calculate percentile (0-100)
            percentile = (np.sum(values_array <= val) / len(values_array)) * 100
            percentiles[item] = percentile

        return percentiles

    def _get_percentile_tag(self, percentile: float) -> str:
        """Get the appropriate color tag for a percentile value."""
        if percentile >= 90:
            return 'percentile_90_100'
        elif percentile >= 80:
            return 'percentile_80_90'
        elif percentile >= 60:
            return 'percentile_60_80'
        elif percentile >= 40:
            return 'percentile_40_60'
        elif percentile >= 20:
            return 'percentile_20_40'
        else:
            return 'percentile_0_20'

    def _create_percentile_bar(self, percentile: float) -> str:
        """
        Create a visual percentile bar using Unicode block characters.

        Args:
            percentile: Percentile value (0-100)

        Returns:
            String representation of the percentile bar
        """
        # Use block characters to create a 10-character bar
        # Full block: █, Light shade: ░
        bar_length = 10
        filled = int((percentile / 100) * bar_length)

        # Create color-coded bar using different characters
        # Higher percentile (red/hot) uses █, lower (blue/cold) uses different shades
        if percentile >= 80:
            # Hot/Red zone - solid blocks
            bar = '█' * filled + '░' * (bar_length - filled)
        elif percentile >= 60:
            # Warm zone - solid blocks
            bar = '▓' * filled + '░' * (bar_length - filled)
        elif percentile >= 40:
            # Middle zone - medium blocks
            bar = '▒' * filled + '░' * (bar_length - filled)
        else:
            # Cool/Blue zone - lighter blocks
            bar = '░' * filled + '·' * (bar_length - filled)

        return bar

    def _calculate_all_column_percentiles(self, numeric_column_indices: List[int]) -> Dict[int, Dict]:
        """
        Calculate percentiles for all numeric columns.

        Args:
            numeric_column_indices: List of column indices to calculate percentiles for

        Returns:
            Dictionary mapping column index to {item_id: percentile} dict
        """
        all_percentiles = {}

        for col_idx in numeric_column_indices:
            all_percentiles[col_idx] = self._calculate_percentiles(col_idx)

        return all_percentiles

    def _apply_percentile_bars_to_data(self, data: List[Dict], numeric_columns: Dict[str, int], value_keys: List[str]) -> List[tuple]:
        """
        Add percentile bars to player data for display.

        Args:
            data: List of player dictionaries
            numeric_columns: Dict mapping column index to whether it should have a bar
            value_keys: List of keys to extract from player dicts in order

        Returns:
            List of tuples ready for tree insertion with percentile bars
        """
        # First, collect all values for each numeric column to calculate percentiles
        column_values = {}
        for col_idx in numeric_columns:
            column_values[col_idx] = []

        # Extract values from data
        for player in data:
            for col_idx, key in enumerate(value_keys):
                if col_idx in numeric_columns:
                    try:
                        if key in player:
                            val = float(player[key])
                            column_values[col_idx].append(val)
                        else:
                            column_values[col_idx].append(0.0)
                    except (ValueError, TypeError):
                        column_values[col_idx].append(0.0)

        # Calculate percentiles for each column
        column_percentiles = {}
        for col_idx, values in column_values.items():
            if not values:
                continue
            values_array = np.array(values)
            column_percentiles[col_idx] = []

            for val in values:
                if len(values) > 1:
                    percentile = (np.sum(values_array <= val) / len(values_array)) * 100
                else:
                    percentile = 50
                column_percentiles[col_idx].append(percentile)

        # Build display rows with percentile bars
        display_rows = []
        for player_idx, player in enumerate(data):
            row_values = []
            for col_idx, key in enumerate(value_keys):
                # Handle draft placeholder
                if key == '_draft_placeholder':
                    row_values.append("")  # Empty draft checkbox initially
                elif col_idx in numeric_columns:
                    # Add value with percentile bar
                    if key in player:
                        val = player[key]
                        percentile = column_percentiles[col_idx][player_idx] if col_idx in column_percentiles else 50
                        bar = self._create_percentile_bar(percentile)

                        # Format number based on type
                        if isinstance(val, (int, float)):
                            if key == 'games_played' or key == 'longest_tear':
                                formatted = f"{int(val)}"
                            else:
                                formatted = f"{val:.1f}"
                        else:
                            formatted = str(val)

                        cell_text = f"{formatted} {bar}"
                        row_values.append(cell_text)
                    else:
                        row_values.append("N/A")
                else:
                    # Non-numeric column (like name)
                    row_values.append(player.get(key, ""))

            display_rows.append(tuple(row_values))

        return display_rows

    def _apply_percentile_colors(self, numeric_columns: List[int]):
        """
        Apply percentile-based row colors.

        Args:
            numeric_columns: List of column indices that contain numeric data
        """
        if not numeric_columns:
            return

        # Use the first numeric column for overall row coloring
        main_column = numeric_columns[0]
        percentiles = self._calculate_percentiles(main_column)

        for item, percentile in percentiles.items():
            tag = self._get_percentile_tag(percentile)
            self.player_tree.item(item, tags=(tag,))

    def _sort_by_column(self, column: str, column_index: int, is_numeric: bool = True):
        """
        Sort tree by column with toggle through: unsorted -> desc -> asc -> unsorted.

        Args:
            column: Column name
            column_index: Column index in values tuple
            is_numeric: Whether the column contains numeric data
        """
        # Determine next sort state
        current_state = self.sort_states.get(column)

        if current_state is None:
            new_state = 'desc'
        elif current_state == 'desc':
            new_state = 'asc'
        else:  # was 'asc'
            new_state = None

        # Reset all column headers
        for col in self.player_tree['columns']:
            heading_text = col
            if heading_text != "Name":  # Keep original name for Name column
                # Remove any existing sort indicators
                heading_text = col.replace(' ▼', '').replace(' ▲', '')
            self.player_tree.heading(col, text=heading_text)

        # Reset sort states for other columns
        if new_state is None:
            # Unsorted - restore original order
            self.sort_states = {}
            self.current_sort_column = None
            self._refresh_tree_display()
        else:
            # Apply new sort
            self.sort_states = {column: new_state}
            self.current_sort_column = column

            # Update header with indicator
            indicator = ' ▼' if new_state == 'desc' else ' ▲'
            self.player_tree.heading(column, text=column + indicator)

            # Sort the data
            items = []
            for item in self.player_tree.get_children():
                values = self.player_tree.item(item)['values']
                try:
                    if is_numeric:
                        # Extract numeric value from string that may contain percentile bar
                        val_str = str(values[column_index])
                        # Split by space and take first part (the number)
                        numeric_part = val_str.split()[0] if ' ' in val_str else val_str
                        sort_val = float(numeric_part.replace('%', '').replace(',', ''))
                    else:
                        sort_val = str(values[column_index])
                except (ValueError, IndexError):
                    sort_val = 0 if is_numeric else ""
                items.append((sort_val, item, values))

            # Sort
            reverse = (new_state == 'desc')
            items.sort(key=lambda x: x[0], reverse=reverse)

            # Reorder tree
            for index, (_, item, _) in enumerate(items):
                self.player_tree.move(item, '', index)

    def _refresh_tree_display(self):
        """Refresh tree display with current data and apply colors."""
        # Clear tree
        for item in self.player_tree.get_children():
            self.player_tree.delete(item)

        # Re-populate based on mode with percentile bars
        if self.analysis_mode == "bestball":
            value_keys = ['player_name', 'bestball_score', 'useful_points_total', 'useful_weeks_count',
                         'useful_points_per_week', 'best_week', 'boom_week_rate', 'tear3_rate', 'tear4_rate']
            numeric_cols = {1, 2, 3, 4, 5, 6, 7, 8}  # All columns except name

            display_rows = self._apply_percentile_bars_to_data(
                self.current_player_pool, numeric_cols, value_keys
            )

            for row in display_rows:
                self.player_tree.insert("", tk.END, values=row)

        else:
            value_keys = ['player_name', 'games_played', 'mean_points', 'std_dev',
                         'variance_score', 'upside_score', 'max_points', 'boom_rate']
            numeric_cols = {1, 2, 3, 4, 5, 6, 7}  # All columns except name

            display_rows = self._apply_percentile_bars_to_data(
                self.current_player_pool, numeric_cols, value_keys
            )

            for row in display_rows:
                self.player_tree.insert("", tk.END, values=row)

    def _create_roster_panel(self, parent):
        """Create roster display panel."""
        roster_frame = ttk.LabelFrame(parent, text="Player Details / Analysis", padding="5")
        roster_frame.grid(row=1, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        roster_frame.rowconfigure(0, weight=1)
        roster_frame.columnconfigure(0, weight=1)

        # Roster text widget
        self.roster_text = tk.Text(roster_frame, height=15, wrap=tk.WORD, font=("Courier", 9))
        roster_scrollbar = ttk.Scrollbar(
            roster_frame,
            orient=tk.VERTICAL,
            command=self.roster_text.yview
        )
        self.roster_text.configure(yscrollcommand=roster_scrollbar.set)

        self.roster_text.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        roster_scrollbar.grid(row=0, column=1, sticky=(tk.N, tk.S))

        # Export button
        export_btn = ttk.Button(
            roster_frame,
            text="Export to CSV",
            command=self._export_data
        )
        export_btn.grid(row=1, column=0, columnspan=2, pady=5)

    def _load_player_pool(self):
        """Load player pool based on mode and filters."""
        stats_type = self.stats_type_var.get()
        min_games = self.min_games_var.get()
        min_threshold = self.min_threshold_var.get()
        sort_by = self.sort_by_var.get()

        # Clear existing items
        for item in self.player_tree.get_children():
            self.player_tree.delete(item)

        if self.analysis_mode == "bestball":
            # Use threading for Best Ball (computationally intensive)
            self._load_bestball_threaded(stats_type, min_games, min_threshold, sort_by)
        else:
            # Daily mode is fast enough to run directly
            self._load_daily_pool(stats_type, min_games, min_threshold, sort_by)

    def _load_daily_pool(self, stats_type, min_games, min_threshold, sort_by):
        """Load daily volatility players (fast, no threading needed)."""
        try:
            self.status_var.set("Loading daily volatility players...")
            self.root.update()

            # Load daily volatility players
            self.current_player_pool = self.optimizer.get_player_pool(
                stats_type=stats_type,
                min_games=min_games,
                min_variance_score=min_threshold
            )

            # Sort
            self.current_player_pool.sort(key=lambda x: x.get(sort_by, 0), reverse=True)

            # Prepare data with percentile bars
            value_keys = ['player_name', 'games_played', 'mean_points', 'std_dev',
                         'variance_score', 'upside_score', 'max_points', 'boom_rate']
            numeric_cols = {1, 2, 3, 4, 5, 6, 7}  # All columns except name

            display_rows = self._apply_percentile_bars_to_data(
                self.current_player_pool, numeric_cols, value_keys
            )

            # Populate tree with percentile bars
            for row in display_rows:
                self.player_tree.insert("", tk.END, values=row)

            self.status_var.set(f"Loaded {len(self.current_player_pool)} players")

        except Exception as e:
            messagebox.showerror("Error", f"Failed to load player pool: {e}")
            self.status_var.set("Error loading players")
            logger.error(f"Error loading player pool: {e}")

    def _load_bestball_threaded(self, stats_type, min_games, min_threshold, sort_by):
        """Load Best Ball players in background thread with progress dialog."""
        # Create progress dialog
        progress_win = tk.Toplevel(self.root)
        progress_win.title("Loading Best Ball Players")
        progress_win.geometry("400x150")
        progress_win.resizable(False, False)

        # Center the window
        progress_win.transient(self.root)
        progress_win.grab_set()

        ttk.Label(progress_win, text="Calculating Best Ball metrics...", font=("Arial", 11)).pack(pady=10)

        self.progress_var = tk.StringVar(value="Starting...")
        progress_label = ttk.Label(progress_win, textvariable=self.progress_var)
        progress_label.pack(pady=5)

        self.progress_bar = ttk.Progressbar(progress_win, mode='determinate', length=350)
        self.progress_bar.pack(pady=10)

        cancel_btn = ttk.Button(progress_win, text="Cancel", command=lambda: setattr(self, 'cancel_loading', True))
        cancel_btn.pack(pady=5)

        self.cancel_loading = False

        def progress_callback(current, total, player_name):
            """Update progress from background thread."""
            if self.cancel_loading:
                return

            percent = (current / total) * 100
            self.root.after(0, lambda: self.progress_bar.configure(value=percent))
            self.root.after(0, lambda: self.progress_var.set(f"Processing {current}/{total}: {player_name}"))

        def load_in_background():
            """Background thread function."""
            try:
                # Load Best Ball players with progress callback
                player_pool = self.weekly_analyzer.get_top_bestball_players(
                    stats_type=stats_type,
                    min_games=min_games,
                    limit=500,
                    progress_callback=progress_callback
                )

                if self.cancel_loading:
                    self.root.after(0, lambda: self.status_var.set("Loading cancelled"))
                    self.root.after(0, progress_win.destroy)
                    return

                # Filter by threshold
                player_pool = [
                    p for p in player_pool
                    if p.get('bestball_score', 0) >= min_threshold
                ]

                # Sort
                player_pool.sort(key=lambda x: x.get(sort_by, 0), reverse=True)

                # Update GUI in main thread
                def update_gui():
                    try:
                        self.current_player_pool = player_pool

                        # Prepare data with percentile bars
                        # Add empty draft column at beginning
                        value_keys = ['_draft_placeholder', 'player_name', 'bestball_score', 'useful_points_total', 'useful_weeks_count',
                                     'useful_points_per_week', 'best_week', 'boom_week_rate', 'tear3_rate', 'tear4_rate']
                        numeric_cols = {2, 3, 4, 5, 6, 7, 8, 9}  # All columns except draft and name

                        display_rows = self._apply_percentile_bars_to_data(
                            self.current_player_pool, numeric_cols, value_keys
                        )

                        # Populate tree with percentile bars and store player data
                        self.player_data_by_item = {}  # Reset player data mapping
                        for i, row in enumerate(display_rows):
                            item_id = self.player_tree.insert("", tk.END, values=row)
                            self.player_data_by_item[item_id] = self.current_player_pool[i]

                        self.status_var.set(f"Loaded {len(self.current_player_pool)} Best Ball players")
                        progress_win.destroy()

                    except Exception as e:
                        logger.error(f"Error updating GUI: {e}")
                        progress_win.destroy()
                        messagebox.showerror("Error", f"Failed to update display: {e}")

                self.root.after(0, update_gui)

            except Exception as e:
                logger.error(f"Error in background thread: {e}")
                self.root.after(0, progress_win.destroy)
                self.root.after(0, lambda: messagebox.showerror("Error", f"Failed to load Best Ball players: {e}"))
                self.root.after(0, lambda: self.status_var.set("Error loading players"))

        # Start background thread
        thread = threading.Thread(target=load_in_background, daemon=True)
        thread.start()

    def _handle_click(self, event):
        """Handle single click - toggle draft status if clicking Draft column."""
        # Identify which column was clicked
        region = self.player_tree.identify("region", event.x, event.y)
        if region != "cell":
            return

        column = self.player_tree.identify_column(event.x)
        item = self.player_tree.identify_row(event.y)

        if not item:
            return

        # Check if clicked on Draft column (first column after tree column)
        if column == "#1":  # Draft column
            self._toggle_draft_status(item)
            return "break"  # Prevent default selection

    def _toggle_draft_status(self, item_id):
        """Toggle draft status for a player."""
        # Get current values
        values = list(self.player_tree.item(item_id)['values'])
        player_name = values[1]  # Name is second column now

        # Toggle drafted status
        if item_id in self.drafted_players:
            # Un-draft
            self.drafted_players.discard(item_id)
            values[0] = ""  # Clear checkbox
            self.player_tree.item(item_id, values=values, tags=())
        else:
            # Draft
            self.drafted_players.add(item_id)
            values[0] = "✓"  # Add checkmark
            self.player_tree.item(item_id, values=values, tags=('drafted',))

        print(f"{'Drafted' if item_id in self.drafted_players else 'Un-drafted'}: {player_name}")

    def _toggle_player_details(self, event):
        """Toggle expandable season stats below player row."""
        selection = self.player_tree.selection()
        if not selection:
            return

        item_id = selection[0]

        # Check if this item has children (already expanded)
        children = self.player_tree.get_children(item_id)

        if children:
            # Collapse - remove children
            for child in children:
                self.player_tree.delete(child)
            self.expanded_items.discard(item_id)
        else:
            # Expand - add season stats as child row
            player = self.player_data_by_item.get(item_id)
            if not player:
                return

            # Get total season stats
            session = self.db.get_session()
            try:
                from src.database.models import PlayerGame
                from sqlalchemy import func

                stats = session.query(
                    func.count(PlayerGame.id).label('games'),
                    func.sum(PlayerGame.dk_points).label('total_pts'),
                    func.avg(PlayerGame.dk_points).label('avg_pts'),
                    func.max(PlayerGame.dk_points).label('max_pts')
                ).filter(
                    PlayerGame.player_id == player['player_id'],
                    PlayerGame.stats_type == self.stats_type_var.get()
                ).first()

                if stats:
                    # Format season stats display
                    season_display = f"  ➤ Season: {stats.games} G, {stats.total_pts:.1f} Tot Pts, {stats.avg_pts:.1f} Avg, {stats.max_pts:.1f} Max"

                    # For pitchers, add start levels
                    if self.stats_type_var.get() == "pitching":
                        l1 = player.get('level1_starts', 0)
                        l2 = player.get('level2_starts', 0)
                        l3 = player.get('level3_starts', 0)
                        season_display += f"  |  L1: {l1}, L2: {l2}, L3: {l3} starts"

                    # Insert child row with season stats
                    self.player_tree.insert(item_id, tk.END, values=[season_display] + [""] * (len(self.player_tree['columns']) - 1))
                    self.expanded_items.add(item_id)

            finally:
                session.close()

    def _show_player_details(self, event):
        """Show detailed player statistics in right panel."""
        selection = self.player_tree.selection()
        if not selection:
            return

        # Get selected player
        item = self.player_tree.item(selection[0])
        player_name = item['values'][0]

        # Handle if clicked on child row (season stats)
        if player_name.strip().startswith("➤"):
            # Get parent item
            parent = self.player_tree.parent(selection[0])
            if parent:
                item = self.player_tree.item(parent)
                player_name = item['values'][0]

        # Find player in pool
        player = next((p for p in self.current_player_pool if p['player_name'] == player_name), None)

        if not player:
            return

        # Clear text widget
        self.roster_text.delete(1.0, tk.END)

        # Display based on mode
        if self.analysis_mode == "bestball":
            self.roster_text.insert(tk.END, "="*70 + "\n")
            self.roster_text.insert(tk.END, f"BEST BALL ANALYSIS: {player_name}\n")
            self.roster_text.insert(tk.END, "="*70 + "\n\n")

            self.roster_text.insert(tk.END, "BEST BALL SCORE:\n")
            self.roster_text.insert(tk.END, f"  Overall BB Score:      {player['bestball_score']:.1f} / 100\n\n")

            self.roster_text.insert(tk.END, "WEEKLY PERFORMANCE:\n")
            self.roster_text.insert(tk.END, f"  Best Week Ever:        {player['best_week']:.1f} pts\n")
            self.roster_text.insert(tk.END, f"  Top 3 Weeks Avg:       {player['top3_weeks_avg']:.1f} pts\n")
            self.roster_text.insert(tk.END, f"  Mean Weekly Points:    {player['mean_week_points']:.1f} pts\n\n")

            self.roster_text.insert(tk.END, "USEFUL POINTS (Starting-Worthy Weeks):\n")
            self.roster_text.insert(tk.END, f"  Total Useful Points:   {player.get('useful_points_total', 0):.1f} pts\n")
            self.roster_text.insert(tk.END, f"  Useful Weeks Count:    {player.get('useful_weeks_count', 0)} weeks\n")
            self.roster_text.insert(tk.END, f"  Pts/Useful Week:       {player.get('useful_points_per_week', 0):.1f} pts (concentration)\n")
            self.roster_text.insert(tk.END, f"  Useful Weeks:          {player.get('useful_weeks_pct', 0):.1f}% of all weeks\n")
            self.roster_text.insert(tk.END, f"  Efficiency:            {player.get('useful_efficiency', 0):.1f}% of points from useful weeks\n")
            self.roster_text.insert(tk.END, f"  Useful Threshold:      {player.get('useful_threshold', 0):.1f} pts (70th %ile league-wide)\n\n")

            self.roster_text.insert(tk.END, "BOOM WEEKS:\n")
            self.roster_text.insert(tk.END, f"  Boom Week Rate:        {player['boom_week_rate']:.1f}%\n\n")

            self.roster_text.insert(tk.END, "TEAR METRICS (Multi-Game Hot Streaks):\n")
            self.roster_text.insert(tk.END, f"  TEAR3 Rate:            {player['tear3_rate']:.1f} per 100 games\n")
            self.roster_text.insert(tk.END, f"  TEAR4 Rate:            {player['tear4_rate']:.1f} per 100 games\n")
            self.roster_text.insert(tk.END, f"  Longest Tear:          {player['longest_tear']} consecutive hot games\n\n")

            # Pitcher Start Levels (if pitching)
            if self.stats_type_var.get() == "pitching" and 'level1_starts' in player:
                self.roster_text.insert(tk.END, "START LEVELS (Elite Start Clustering):\n")
                self.roster_text.insert(tk.END, f"  Level 1 (Top 30%):     {player.get('level1_starts', 0)} starts ({player.get('level1_rate', 0):.1f}%)\n")
                self.roster_text.insert(tk.END, f"    Avg Points:          {player.get('level1_avg_pts', 0):.1f} pts\n")
                self.roster_text.insert(tk.END, f"  Level 2 (Top 20%):     {player.get('level2_starts', 0)} starts ({player.get('level2_rate', 0):.1f}%)\n")
                self.roster_text.insert(tk.END, f"    Avg Points:          {player.get('level2_avg_pts', 0):.1f} pts\n")
                self.roster_text.insert(tk.END, f"  Level 3 (Top 10%):     {player.get('level3_starts', 0)} starts ({player.get('level3_rate', 0):.1f}%)\n")
                self.roster_text.insert(tk.END, f"    Avg Points:          {player.get('level3_avg_pts', 0):.1f} pts\n\n")

            self.roster_text.insert(tk.END, "BEST BALL STRATEGY:\n")
            if player['bestball_score'] >= 70:
                self.roster_text.insert(tk.END, "  ★★★ ELITE - Top tier for Best Ball\n")
            elif player['bestball_score'] >= 60:
                self.roster_text.insert(tk.END, "  ★★ STRONG - Excellent weekly upside\n")
            elif player['bestball_score'] >= 50:
                self.roster_text.insert(tk.END, "  ★ SOLID - Good weekly potential\n")
            else:
                self.roster_text.insert(tk.END, "  SPECULATIVE - Lower weekly ceiling\n")

            if player['tear3_rate'] >= 30:
                self.roster_text.insert(tk.END, "  High TEAR ability - Goes on hot streaks!\n")

        else:  # daily mode
            self.roster_text.insert(tk.END, "="*70 + "\n")
            self.roster_text.insert(tk.END, f"PLAYER DETAILS: {player_name}\n")
            self.roster_text.insert(tk.END, "="*70 + "\n\n")

            self.roster_text.insert(tk.END, f"Games Played: {player['games_played']}\n\n")

            self.roster_text.insert(tk.END, "Performance Metrics:\n")
            self.roster_text.insert(tk.END, f"  Mean Points:    {player['mean_points']:.2f}\n")
            self.roster_text.insert(tk.END, f"  Std Deviation:  {player['std_dev']:.2f}\n")
            self.roster_text.insert(tk.END, f"  Max Points:     {player['max_points']:.2f}\n")
            self.roster_text.insert(tk.END, f"  95th %ile:      {player['percentile_95']:.2f}\n\n")

            self.roster_text.insert(tk.END, "Volatility Scores:\n")
            self.roster_text.insert(tk.END, f"  Variance Score: {player['variance_score']:.2f}\n")
            self.roster_text.insert(tk.END, f"  Upside Score:   {player['upside_score']:.2f}\n")
            self.roster_text.insert(tk.END, f"  Boom Rate:      {player['boom_rate']:.1f}%\n")
            self.roster_text.insert(tk.END, f"  Top 5 Games:    {player['top5_games_pct']:.1f}%\n")

    def _show_db_stats(self):
        """Show database statistics."""
        try:
            stats = self.db.get_database_stats()

            info = f"""
DATABASE STATISTICS

Games:
  Total Games: {stats['total_games']}
  Games Fetched: {stats['games_fetched']}

Players:
  Total Players: {stats['total_players']}
  Players with Volatility Data: {stats['players_with_volatility']}

Performances:
  Total Performances: {stats['total_player_games']}
  Batting Performances: {stats['batting_performances']}
  Pitching Performances: {stats['pitching_performances']}
            """

            messagebox.showinfo("Database Statistics", info)

        except Exception as e:
            messagebox.showerror("Error", f"Failed to get database stats: {e}")

    def _export_data(self):
        """Export current player pool to CSV."""
        if not self.current_player_pool:
            messagebox.showwarning("Warning", "No player pool to export")
            return

        filename = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")]
        )

        if filename:
            try:
                import csv

                with open(filename, 'w', newline='') as f:
                    if self.analysis_mode == "bestball":
                        fieldnames = ['player_name', 'bestball_score', 'best_week', 'top3_weeks_avg',
                                    'boom_week_rate', 'tear3_rate', 'tear4_rate', 'longest_tear']
                    else:
                        fieldnames = ['player_name', 'games_played', 'mean_points', 'std_dev',
                                    'variance_score', 'upside_score', 'max_points', 'boom_rate']

                    writer = csv.DictWriter(f, fieldnames=fieldnames)
                    writer.writeheader()

                    for player in self.current_player_pool:
                        row = {k: player.get(k, '') for k in fieldnames}
                        writer.writerow(row)

                messagebox.showinfo("Success", f"Data exported to {filename}")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to export data: {e}")

    def run(self):
        """Run the GUI application."""
        self.root.mainloop()


def main():
    """Main entry point for GUI."""
    app = MLBVolatilityGUI()
    app.run()


if __name__ == "__main__":
    main()

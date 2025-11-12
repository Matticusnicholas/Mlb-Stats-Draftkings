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
        self.root.geometry("1400x850")

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
                "bestball_score", "best_week", "tear3_rate", "tear4_rate", "boom_week_rate", "top3_weeks_avg"
            ])
            self.sort_by_var.set("bestball_score")
            self.load_btn.config(text="Load Best Ball Players")
            self.info_label.config(
                text="Best Ball Mode:\n• Rolling 7-day windows\n• TEAR metrics\n• Weekly ceilings"
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

        # Reconfigure columns
        self.player_tree.configure(columns=(
            "Name", "BB Score", "Best Week", "Top3 Avg", "Boom%", "TEAR3", "TEAR4", "Longest"
        ))

        # Set headings with click-to-sort
        self.player_tree.heading("Name", text="Player Name",
                                command=lambda: self._sort_by_column("Name", 0, is_numeric=False))
        self.player_tree.heading("BB Score", text="BB Score",
                                command=lambda: self._sort_by_column("BB Score", 1))
        self.player_tree.heading("Best Week", text="Best Week",
                                command=lambda: self._sort_by_column("Best Week", 2))
        self.player_tree.heading("Top3 Avg", text="Top3 Avg",
                                command=lambda: self._sort_by_column("Top3 Avg", 3))
        self.player_tree.heading("Boom%", text="Boom%",
                                command=lambda: self._sort_by_column("Boom%", 4))
        self.player_tree.heading("TEAR3", text="TEAR3",
                                command=lambda: self._sort_by_column("TEAR3", 5))
        self.player_tree.heading("TEAR4", text="TEAR4",
                                command=lambda: self._sort_by_column("TEAR4", 6))
        self.player_tree.heading("Longest", text="Longest",
                                command=lambda: self._sort_by_column("Longest", 7))

        # Set column widths
        self.player_tree.column("Name", width=150)
        self.player_tree.column("BB Score", width=80)
        self.player_tree.column("Best Week", width=90)
        self.player_tree.column("Top3 Avg", width=90)
        self.player_tree.column("Boom%", width=70)
        self.player_tree.column("TEAR3", width=70)
        self.player_tree.column("TEAR4", width=70)
        self.player_tree.column("Longest", width=70)

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

        # Set column widths
        self.player_tree.column("Name", width=150)
        self.player_tree.column("Games", width=60)
        self.player_tree.column("Mean", width=70)
        self.player_tree.column("Std Dev", width=70)
        self.player_tree.column("Variance", width=80)
        self.player_tree.column("Upside", width=70)
        self.player_tree.column("Max", width=70)
        self.player_tree.column("Boom%", width=70)

    def _create_player_list(self, parent):
        """Create player list view."""
        player_frame = ttk.LabelFrame(parent, text="Player Pool", padding="5")
        player_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), pady=(0, 5))
        player_frame.rowconfigure(0, weight=1)
        player_frame.columnconfigure(0, weight=1)

        # Create treeview (will be configured based on mode)
        self.player_tree = ttk.Treeview(player_frame, show="headings", height=15)

        # Configure color tags for percentile-based coloring
        self._configure_color_tags()

        # Initial setup for Best Ball mode
        self._update_tree_columns_bestball()

        # Scrollbar
        scrollbar = ttk.Scrollbar(player_frame, orient=tk.VERTICAL, command=self.player_tree.yview)
        self.player_tree.configure(yscrollcommand=scrollbar.set)

        self.player_tree.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        scrollbar.grid(row=0, column=1, sticky=(tk.N, tk.S))

        # Double-click to view details
        self.player_tree.bind("<Double-1>", self._show_player_details)

    def _configure_color_tags(self):
        """Configure color tags for percentile-based visualization."""
        # Percentile color scheme (higher is better = greener)
        self.player_tree.tag_configure('percentile_90_100', background='#2d5016')  # Dark green
        self.player_tree.tag_configure('percentile_75_90', background='#5a8c3a')   # Medium green
        self.player_tree.tag_configure('percentile_60_75', background='#8fbc5a')   # Light green
        self.player_tree.tag_configure('percentile_40_60', background='#d9e3c8')   # Very light green
        self.player_tree.tag_configure('percentile_25_40', background='#f5deb3')   # Light tan
        self.player_tree.tag_configure('percentile_0_25', background='#f5b7a8')    # Light red

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
        elif percentile >= 75:
            return 'percentile_75_90'
        elif percentile >= 60:
            return 'percentile_60_75'
        elif percentile >= 40:
            return 'percentile_40_60'
        elif percentile >= 25:
            return 'percentile_25_40'
        else:
            return 'percentile_0_25'

    def _apply_percentile_colors(self, numeric_columns: List[int]):
        """
        Apply percentile-based colors to all numeric columns.

        Args:
            numeric_columns: List of column indices that contain numeric data
        """
        if not numeric_columns:
            return

        # For simplicity, use the first numeric column for overall coloring
        # (typically the most important metric like BB Score or Variance Score)
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
                        sort_val = float(str(values[column_index]).replace('%', '').replace(',', ''))
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

        # Re-populate based on mode
        if self.analysis_mode == "bestball":
            for player in self.current_player_pool:
                self.player_tree.insert("", tk.END, values=(
                    player['player_name'],
                    f"{player['bestball_score']:.1f}",
                    f"{player['best_week']:.1f}",
                    f"{player['top3_weeks_avg']:.1f}",
                    f"{player['boom_week_rate']:.1f}",
                    f"{player['tear3_rate']:.1f}",
                    f"{player['tear4_rate']:.1f}",
                    f"{player['longest_tear']}"
                ))
            # Apply colors (columns 1-7 are numeric, column 0 is name)
            self._apply_percentile_colors([1])  # Use BB Score for coloring
        else:
            for player in self.current_player_pool:
                self.player_tree.insert("", tk.END, values=(
                    player['player_name'],
                    player['games_played'],
                    f"{player['mean_points']:.1f}",
                    f"{player['std_dev']:.1f}",
                    f"{player['variance_score']:.1f}",
                    f"{player['upside_score']:.1f}",
                    f"{player['max_points']:.1f}",
                    f"{player['boom_rate']:.1f}"
                ))
            # Apply colors (columns 1-7 are numeric, column 0 is name)
            self._apply_percentile_colors([4])  # Use Variance Score for coloring

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

            # Populate tree
            for player in self.current_player_pool:
                self.player_tree.insert("", tk.END, values=(
                    player['player_name'],
                    player['games_played'],
                    f"{player['mean_points']:.1f}",
                    f"{player['std_dev']:.1f}",
                    f"{player['variance_score']:.1f}",
                    f"{player['upside_score']:.1f}",
                    f"{player['max_points']:.1f}",
                    f"{player['boom_rate']:.1f}"
                ))

            # Apply percentile-based colors (Variance Score is column 4)
            self._apply_percentile_colors([4])

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

                        # Populate tree
                        for player in self.current_player_pool:
                            self.player_tree.insert("", tk.END, values=(
                                player['player_name'],
                                f"{player['bestball_score']:.1f}",
                                f"{player['best_week']:.1f}",
                                f"{player['top3_weeks_avg']:.1f}",
                                f"{player['boom_week_rate']:.1f}",
                                f"{player['tear3_rate']:.1f}",
                                f"{player['tear4_rate']:.1f}",
                                f"{player['longest_tear']}"
                            ))

                        # Apply percentile-based colors (BB Score is column 1)
                        self._apply_percentile_colors([1])

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

    def _show_player_details(self, event):
        """Show detailed player statistics."""
        selection = self.player_tree.selection()
        if not selection:
            return

        # Get selected player
        item = self.player_tree.item(selection[0])
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

            self.roster_text.insert(tk.END, "BOOM WEEKS:\n")
            self.roster_text.insert(tk.END, f"  Boom Week Rate:        {player['boom_week_rate']:.1f}%\n\n")

            self.roster_text.insert(tk.END, "TEAR METRICS (Multi-Game Hot Streaks):\n")
            self.roster_text.insert(tk.END, f"  TEAR3 Rate:            {player['tear3_rate']:.1f} per 100 games\n")
            self.roster_text.insert(tk.END, f"  TEAR4 Rate:            {player['tear4_rate']:.1f} per 100 games\n")
            self.roster_text.insert(tk.END, f"  Longest Tear:          {player['longest_tear']} consecutive hot games\n\n")

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

"""
Main GUI window for MLB DraftKings Volatility Analyzer.
"""
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from typing import List, Dict, Optional
import logging

try:
    import customtkinter as ctk
    CTK_AVAILABLE = True
except ImportError:
    CTK_AVAILABLE = False
    print("CustomTkinter not available, using standard tkinter")

from ..database.db_manager import DatabaseManager
from ..analytics.volatility_analyzer import VolatilityAnalyzer
from ..analytics.roster_optimizer import RosterOptimizer

logger = logging.getLogger(__name__)


class MLBVolatilityGUI:
    """Main GUI application for MLB volatility analysis."""

    def __init__(self, db_path: str = "data/mlb_stats.db"):
        """
        Initialize GUI application.

        Args:
            db_path: Path to database file
        """
        self.db = DatabaseManager(db_path)
        self.analyzer = VolatilityAnalyzer(self.db)
        self.optimizer = RosterOptimizer(self.db)

        # Use customtkinter if available, else standard tkinter
        if CTK_AVAILABLE:
            ctk.set_appearance_mode("dark")
            ctk.set_default_color_theme("blue")
            self.root = ctk.CTk()
        else:
            self.root = tk.Tk()

        self.root.title("MLB DraftKings Volatility Analyzer")
        self.root.geometry("1200x800")

        self.current_player_pool = []
        self.current_roster = None

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
            text="MLB DraftKings Volatility Analyzer",
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
        self.status_var = tk.StringVar(value="Ready")
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

        # Min variance score
        ttk.Label(parent, text="Min Variance Score:").grid(row=row, column=0, sticky=tk.W, pady=5)
        self.min_variance_var = tk.DoubleVar(value=0.0)
        variance_spin = ttk.Spinbox(
            parent,
            from_=0.0,
            to=100.0,
            increment=5.0,
            textvariable=self.min_variance_var,
            width=15
        )
        variance_spin.grid(row=row, column=1, sticky=(tk.W, tk.E), pady=5)
        row += 1

        # Sort by
        ttk.Label(parent, text="Sort By:").grid(row=row, column=0, sticky=tk.W, pady=5)
        self.sort_by_var = tk.StringVar(value="variance_score")
        sort_combo = ttk.Combobox(
            parent,
            textvariable=self.sort_by_var,
            values=["variance_score", "upside_score", "mean_points", "max_points", "boom_rate"],
            state="readonly",
            width=15
        )
        sort_combo.grid(row=row, column=1, sticky=(tk.W, tk.E), pady=5)
        row += 1

        # Load players button
        load_btn = ttk.Button(
            parent,
            text="Load Player Pool",
            command=self._load_player_pool
        )
        load_btn.grid(row=row, column=0, columnspan=2, pady=10, sticky=(tk.W, tk.E))
        row += 1

        # Separator
        ttk.Separator(parent, orient=tk.HORIZONTAL).grid(
            row=row, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=10
        )
        row += 1

        # Roster building
        ttk.Label(parent, text="Roster Building", font=("Arial", 12, "bold")).grid(
            row=row, column=0, columnspan=2, pady=5
        )
        row += 1

        # Optimization metric
        ttk.Label(parent, text="Optimize For:").grid(row=row, column=0, sticky=tk.W, pady=5)
        self.opt_metric_var = tk.StringVar(value="variance_score")
        opt_combo = ttk.Combobox(
            parent,
            textvariable=self.opt_metric_var,
            values=["variance_score", "upside_score"],
            state="readonly",
            width=15
        )
        opt_combo.grid(row=row, column=1, sticky=(tk.W, tk.E), pady=5)
        row += 1

        # Build roster button
        build_btn = ttk.Button(
            parent,
            text="Build Max Variance Roster",
            command=self._build_roster
        )
        build_btn.grid(row=row, column=0, columnspan=2, pady=10, sticky=(tk.W, tk.E))
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

    def _create_player_list(self, parent):
        """Create player list view."""
        player_frame = ttk.LabelFrame(parent, text="Player Pool", padding="5")
        player_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), pady=(0, 5))
        player_frame.rowconfigure(0, weight=1)
        player_frame.columnconfigure(0, weight=1)

        # Create treeview
        columns = ("Name", "Games", "Mean", "Std Dev", "Variance", "Upside", "Max", "Boom%")
        self.player_tree = ttk.Treeview(player_frame, columns=columns, show="headings", height=15)

        # Define headings
        self.player_tree.heading("Name", text="Player Name")
        self.player_tree.heading("Games", text="Games")
        self.player_tree.heading("Mean", text="Mean Pts")
        self.player_tree.heading("Std Dev", text="Std Dev")
        self.player_tree.heading("Variance", text="Var Score")
        self.player_tree.heading("Upside", text="Upside")
        self.player_tree.heading("Max", text="Max Pts")
        self.player_tree.heading("Boom%", text="Boom %")

        # Define column widths
        self.player_tree.column("Name", width=150)
        self.player_tree.column("Games", width=60)
        self.player_tree.column("Mean", width=70)
        self.player_tree.column("Std Dev", width=70)
        self.player_tree.column("Variance", width=80)
        self.player_tree.column("Upside", width=70)
        self.player_tree.column("Max", width=70)
        self.player_tree.column("Boom%", width=70)

        # Scrollbar
        scrollbar = ttk.Scrollbar(player_frame, orient=tk.VERTICAL, command=self.player_tree.yview)
        self.player_tree.configure(yscrollcommand=scrollbar.set)

        self.player_tree.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        scrollbar.grid(row=0, column=1, sticky=(tk.N, tk.S))

        # Double-click to view details
        self.player_tree.bind("<Double-1>", self._show_player_details)

    def _create_roster_panel(self, parent):
        """Create roster display panel."""
        roster_frame = ttk.LabelFrame(parent, text="Current Roster", padding="5")
        roster_frame.grid(row=1, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        roster_frame.rowconfigure(0, weight=1)
        roster_frame.columnconfigure(0, weight=1)

        # Roster text widget
        self.roster_text = tk.Text(roster_frame, height=15, wrap=tk.WORD)
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
            text="Export Roster",
            command=self._export_roster
        )
        export_btn.grid(row=1, column=0, columnspan=2, pady=5)

    def _load_player_pool(self):
        """Load player pool based on filters."""
        self.status_var.set("Loading player pool...")
        self.root.update()

        try:
            stats_type = self.stats_type_var.get()
            min_games = self.min_games_var.get()
            min_variance = self.min_variance_var.get()
            sort_by = self.sort_by_var.get()

            self.current_player_pool = self.optimizer.get_player_pool(
                stats_type=stats_type,
                min_games=min_games,
                min_variance_score=min_variance
            )

            # Sort
            self.current_player_pool.sort(key=lambda x: x.get(sort_by, 0), reverse=True)

            # Clear existing items
            for item in self.player_tree.get_children():
                self.player_tree.delete(item)

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

            self.status_var.set(f"Loaded {len(self.current_player_pool)} players")

        except Exception as e:
            messagebox.showerror("Error", f"Failed to load player pool: {e}")
            self.status_var.set("Error loading players")
            logger.error(f"Error loading player pool: {e}")

    def _build_roster(self):
        """Build optimal roster."""
        if not self.current_player_pool:
            messagebox.showwarning("Warning", "Please load player pool first")
            return

        self.status_var.set("Building roster...")
        self.root.update()

        try:
            opt_metric = self.opt_metric_var.get()

            self.current_roster = self.optimizer.build_max_variance_roster(
                self.current_player_pool,
                optimization_metric=opt_metric
            )

            self._display_roster()
            self.status_var.set("Roster built successfully")

        except Exception as e:
            messagebox.showerror("Error", f"Failed to build roster: {e}")
            self.status_var.set("Error building roster")
            logger.error(f"Error building roster: {e}")

    def _display_roster(self):
        """Display current roster in text widget."""
        if not self.current_roster:
            return

        self.roster_text.delete(1.0, tk.END)

        # Header
        self.roster_text.insert(tk.END, "=" * 60 + "\n")
        self.roster_text.insert(tk.END, "MAX VARIANCE ROSTER\n")
        self.roster_text.insert(tk.END, "=" * 60 + "\n\n")

        # Pitchers
        self.roster_text.insert(tk.END, "PITCHERS:\n")
        self.roster_text.insert(tk.END, "-" * 60 + "\n")
        for i, p in enumerate(self.current_roster.get('pitchers', []), 1):
            self.roster_text.insert(
                tk.END,
                f"{i}. {p['player_name']:<30} "
                f"Var: {p['variance_score']:.1f}  "
                f"Mean: {p['mean_points']:.1f}\n"
            )

        self.roster_text.insert(tk.END, "\n")

        # Batters
        self.roster_text.insert(tk.END, "BATTERS:\n")
        self.roster_text.insert(tk.END, "-" * 60 + "\n")
        for i, p in enumerate(self.current_roster.get('batters', []), 1):
            self.roster_text.insert(
                tk.END,
                f"{i}. {p['player_name']:<30} "
                f"Var: {p['variance_score']:.1f}  "
                f"Mean: {p['mean_points']:.1f}\n"
            )

        # Summary
        self.roster_text.insert(tk.END, "\n" + "=" * 60 + "\n")
        self.roster_text.insert(tk.END, "ROSTER SUMMARY:\n")
        self.roster_text.insert(tk.END, "=" * 60 + "\n")
        self.roster_text.insert(
            tk.END,
            f"Total Variance Score: {self.current_roster.get('total_variance_score', 0):.2f}\n"
        )
        self.roster_text.insert(
            tk.END,
            f"Total Upside Score: {self.current_roster.get('total_upside_score', 0):.2f}\n"
        )
        self.roster_text.insert(
            tk.END,
            f"Projected Mean Points: {self.current_roster.get('mean_projected_points', 0):.2f}\n"
        )
        self.roster_text.insert(
            tk.END,
            f"Projected Std Dev: {self.current_roster.get('std_dev', 0):.2f}\n"
        )

        # Upside evaluation
        upside_eval = self.optimizer.evaluate_roster_upside(self.current_roster)
        self.roster_text.insert(tk.END, "\nUPSIDE ANALYSIS:\n")
        self.roster_text.insert(tk.END, "-" * 60 + "\n")
        self.roster_text.insert(
            tk.END,
            f"Ceiling Projection (95th%): {upside_eval['ceiling_projection']:.2f}\n"
        )
        self.roster_text.insert(
            tk.END,
            f"Expected 90th Percentile: {upside_eval['expected_90th_percentile']:.2f}\n"
        )
        self.roster_text.insert(
            tk.END,
            f"Boom Probability: {upside_eval['boom_probability']:.1f}%\n"
        )

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

        if player:
            details = f"""
Player: {player['player_name']}
Games Played: {player['games_played']}

Performance Metrics:
  Mean Points: {player['mean_points']:.2f}
  Std Deviation: {player['std_dev']:.2f}
  Max Points: {player['max_points']:.2f}
  95th Percentile: {player['percentile_95']:.2f}

Volatility Scores:
  Variance Score: {player['variance_score']:.2f}
  Upside Score: {player['upside_score']:.2f}
  Boom Rate: {player['boom_rate']:.1f}%
  Top 5 Games: {player['top5_games_pct']:.1f}%
            """
            messagebox.showinfo(f"Player Details - {player_name}", details)

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

    def _export_roster(self):
        """Export roster to file."""
        if not self.current_roster:
            messagebox.showwarning("Warning", "No roster to export")
            return

        filename = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")]
        )

        if filename:
            try:
                with open(filename, 'w') as f:
                    f.write(self.roster_text.get(1.0, tk.END))
                messagebox.showinfo("Success", f"Roster exported to {filename}")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to export roster: {e}")

    def run(self):
        """Run the GUI application."""
        self.root.mainloop()


def main():
    """Main entry point for GUI."""
    app = MLBVolatilityGUI()
    app.run()


if __name__ == "__main__":
    main()

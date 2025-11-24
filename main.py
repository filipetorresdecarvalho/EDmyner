# main.py - Updated with embedded web browser tabs
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import threading
import time
import webbrowser
import urllib.parse

# For embedded web browsers
try:
    from tkinterweb import HtmlFrame
    BROWSER_AVAILABLE = True
except ImportError:
    BROWSER_AVAILABLE = False
    print("Warning: tkinterweb not installed. Web tabs will open external browser.")

from config import AppConfig
from tts_handler import TTSHandler
from journal_reader import JournalReader
from mining_stats import MiningStats
from detection_history import DetectionHistory
from event_processor import EventProcessor

class EliteMaterialScanner:
    """Main application class."""
    
    def __init__(self, root):
        self.root = root
        self.root.title(AppConfig.APP_NAME)
        self.root.geometry("1200x900")  # Larger for web content
        
        # Configure Elite Dangerous theme
        self._configure_theme()
        
        # Initialize components
        self.tts = TTSHandler()
        self.mining_stats = MiningStats()
        self.detection_history = DetectionHistory(AppConfig.HISTORY_JSON_FILE)
        
        # UI state
        self.log_path = tk.StringVar()
        self.local_system = tk.StringVar(value=AppConfig.DEFAULT_SYSTEM)
        self.cmdr_name = tk.StringVar(value=AppConfig.DEFAULT_COMMANDER)
        self.material_name = tk.StringVar(value=AppConfig.DEFAULT_MATERIAL)
        self.min_percentage = tk.StringVar(value=AppConfig.DEFAULT_MIN_PERCENTAGE)
        self.desired_sell_value = tk.StringVar(value=AppConfig.DEFAULT_SELL_VALUE)
        
        # Runtime state
        self.running = False
        self.engine_started = False
        self.journal_reader = None
        self.event_processor = None
        self.current_progress = 0.0
        self.stations_list = []
        
        # Web browser frames
        self.miners_frame = None
        self.inara_frame = None
        self.spansh_frame = None
        
        # Create UI
        self.create_ui()
        self.set_default_log_path()
    
    def _configure_theme(self):
        """Configure Elite Dangerous theme colors."""
        self.root.configure(bg=AppConfig.COLOR_ED_DARKER_BG)
        
        style = ttk.Style()
        style.theme_use('clam')
        
        # Configure colors for various widgets
        style.configure('TFrame', background=AppConfig.COLOR_ED_DARKER_BG)
        style.configure('TLabel', 
                       background=AppConfig.COLOR_ED_DARKER_BG, 
                       foreground=AppConfig.COLOR_ED_TEXT)
        style.configure('TButton',
                       background=AppConfig.COLOR_ED_ORANGE,
                       foreground=AppConfig.COLOR_ED_TEXT,
                       borderwidth=1)
        style.map('TButton',
                 background=[('active', AppConfig.COLOR_WARNING)])
        
        style.configure('TNotebook', 
                       background=AppConfig.COLOR_ED_DARKER_BG,
                       borderwidth=0)
        style.configure('TNotebook.Tab',
                       background=AppConfig.COLOR_ED_LIGHT_GRAY,
                       foreground=AppConfig.COLOR_ED_TEXT,
                       padding=[10, 5])
        style.map('TNotebook.Tab',
                 background=[('selected', AppConfig.COLOR_ED_ORANGE)])
        
        style.configure('Treeview',
                       background=AppConfig.COLOR_ED_DARK_BG,
                       foreground=AppConfig.COLOR_ED_TEXT,
                       fieldbackground=AppConfig.COLOR_ED_DARK_BG,
                       borderwidth=0)
        style.configure('Treeview.Heading',
                       background=AppConfig.COLOR_ED_ORANGE,
                       foreground=AppConfig.COLOR_ED_TEXT,
                       borderwidth=1)
        style.map('Treeview',
                 background=[('selected', AppConfig.COLOR_ED_ORANGE)])
        
        style.configure('TEntry',
                       fieldbackground=AppConfig.COLOR_ED_DARK_BG,
                       foreground=AppConfig.COLOR_ED_TEXT,
                       borderwidth=1)
        
        style.configure('TCombobox',
                       fieldbackground=AppConfig.COLOR_ED_DARK_BG,
                       foreground=AppConfig.COLOR_ED_TEXT,
                       borderwidth=1)
        
        style.configure('TLabelframe',
                       background=AppConfig.COLOR_ED_DARKER_BG,
                       foreground=AppConfig.COLOR_ED_ORANGE,
                       borderwidth=2)
        style.configure('TLabelframe.Label',
                       background=AppConfig.COLOR_ED_DARKER_BG,
                       foreground=AppConfig.COLOR_ED_ORANGE,
                       font=('Arial', 10, 'bold'))
        
        style.configure('TProgressbar',
                       background=AppConfig.COLOR_ED_ORANGE,
                       troughcolor=AppConfig.COLOR_ED_DARK_BG,
                       borderwidth=1)
    
    def create_ui(self):
        """Create user interface."""
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill='both', expand=True, padx=10, pady=10)
        
        # Create tabs
        self.tab_engine = ttk.Frame(self.notebook)
        self.tab_config = ttk.Frame(self.notebook)
        self.tab_scan = ttk.Frame(self.notebook)
        self.tab_stations = ttk.Frame(self.notebook)
        self.tab_miners = ttk.Frame(self.notebook)
        self.tab_inara = ttk.Frame(self.notebook)
        self.tab_spansh = ttk.Frame(self.notebook)
        
        self.notebook.add(self.tab_engine, text="⚙ Engine")
        self.notebook.add(self.tab_config, text="⚙ Config", state="disabled")
        self.notebook.add(self.tab_scan, text="📡 Scan", state="disabled")
        self.notebook.add(self.tab_stations, text="🚉 Stations", state="disabled")
        self.notebook.add(self.tab_miners, text="⛏ Miners Tool", state="disabled")
        self.notebook.add(self.tab_inara, text="📊 INARA", state="disabled")
        self.notebook.add(self.tab_spansh, text="🗺 Spansh", state="disabled")
        
        # Build each tab
        self.build_engine_tab()
        self.build_config_tab()
        self.build_scan_tab()
        self.build_stations_tab()
        self.build_miners_tab()
        self.build_inara_tab()
        self.build_spansh_tab()
        
        # Bind tab change event
        self.notebook.bind("<<NotebookTabChanged>>", self.on_tab_changed)
    
    def on_tab_changed(self, event):
        """Handle tab change event."""
        selected_tab = self.notebook.index(self.notebook.select())
        
        # Stations tab - reload stations
        if selected_tab == 3 and self.journal_reader:
            self.load_all_stations()
        
        # Miners Tool tab - load if not loaded
        elif selected_tab == 4 and self.miners_frame is None:
            self.load_miners_tool()
        
        # INARA tab - reload with current system
        elif selected_tab == 5:
            self.load_inara()
        
        # Spansh tab - reload with current system
        elif selected_tab == 6:
            self.load_spansh()
    
    def build_miners_tab(self):
        """Build Miners Tool tab with embedded browser."""
        frame = ttk.Frame(self.tab_miners)
        frame.pack(fill='both', expand=True)
        
        # Toolbar
        toolbar = ttk.Frame(frame)
        toolbar.pack(fill='x', padx=5, pady=5)
        
        ttk.Label(toolbar, text="⛏ MINERS TOOL - EDTools", 
                 font=("Arial", 11, "bold"),
                 foreground=AppConfig.COLOR_ED_ORANGE).pack(side='left', padx=5)
        
        ttk.Button(toolbar, text="🔄 Refresh", 
                  command=self.load_miners_tool).pack(side='right', padx=5)
        
        ttk.Button(toolbar, text="🌐 Open in Browser", 
                  command=lambda: webbrowser.open("https://edtools.cc/miner")).pack(side='right', padx=5)
        
        # Browser frame container
        self.miners_container = ttk.Frame(frame)
        self.miners_container.pack(fill='both', expand=True, padx=5, pady=5)
    
    def build_inara_tab(self):
        """Build INARA tab with embedded browser."""
        frame = ttk.Frame(self.tab_inara)
        frame.pack(fill='both', expand=True)
        
        # Toolbar
        toolbar = ttk.Frame(frame)
        toolbar.pack(fill='x', padx=5, pady=5)
        
        ttk.Label(toolbar, text="📊 INARA - Nearest Stations", 
                 font=("Arial", 11, "bold"),
                 foreground=AppConfig.COLOR_ED_ORANGE).pack(side='left', padx=5)
        
        self.inara_system_label = ttk.Label(toolbar, text="System: Unknown")
        self.inara_system_label.pack(side='left', padx=10)
        
        ttk.Button(toolbar, text="🔄 Refresh", 
                  command=self.load_inara).pack(side='right', padx=5)
        
        ttk.Button(toolbar, text="🌐 Open in Browser", 
                  command=self.open_inara_external).pack(side='right', padx=5)
        
        # Browser frame container
        self.inara_container = ttk.Frame(frame)
        self.inara_container.pack(fill='both', expand=True, padx=5, pady=5)
    
    def build_spansh_tab(self):
        """Build Spansh tab with embedded browser."""
        frame = ttk.Frame(self.tab_spansh)
        frame.pack(fill='both', expand=True)
        
        # Toolbar
        toolbar = ttk.Frame(frame)
        toolbar.pack(fill='x', padx=5, pady=5)
        
        ttk.Label(toolbar, text="🗺 SPANSH - System Search", 
                 font=("Arial", 11, "bold"),
                 foreground=AppConfig.COLOR_ED_ORANGE).pack(side='left', padx=5)
        
        self.spansh_system_label = ttk.Label(toolbar, text="System: Unknown")
        self.spansh_system_label.pack(side='left', padx=10)
        
        ttk.Button(toolbar, text="🔄 Refresh", 
                  command=self.load_spansh).pack(side='right', padx=5)
        
        ttk.Button(toolbar, text="🌐 Open in Browser", 
                  command=self.open_spansh_external).pack(side='right', padx=5)
        
        # Browser frame container
        self.spansh_container = ttk.Frame(frame)
        self.spansh_container.pack(fill='both', expand=True, padx=5, pady=5)
    
    def load_miners_tool(self):
        """Load Miners Tool website."""
        if not BROWSER_AVAILABLE:
            webbrowser.open("https://edtools.cc/miner")
            return
        
        # Clear previous frame
        if self.miners_frame:
            self.miners_frame.destroy()
        
        # Create new browser frame
        self.miners_frame = HtmlFrame(self.miners_container, 
                                      messages_enabled=False)
        self.miners_frame.pack(fill='both', expand=True)
        self.miners_frame.load_website("https://edtools.cc/miner")
    
    def load_inara(self):
        """Load INARA website for current system."""
        system = self.local_system.get()
        
        if system == AppConfig.DEFAULT_SYSTEM or not system:
            self.inara_system_label.config(text="⚠ System: Unknown - Start engine first")
            return
        
        self.inara_system_label.config(text=f"System: {system}")
        
        if not BROWSER_AVAILABLE:
            self.open_inara_external()
            return
        
        # Clear previous frame
        if self.inara_frame:
            self.inara_frame.destroy()
        
        # Create new browser frame
        encoded_system = urllib.parse.quote(system)
        url = f"https://inara.cz/elite/nearest-stations/?formBrief=1&ps=1&{encoded_system}"
        
        self.inara_frame = HtmlFrame(self.inara_container, 
                                    messages_enabled=False)
        self.inara_frame.pack(fill='both', expand=True)
        self.inara_frame.load_website(url)
    
    def load_spansh(self):
        """Load Spansh website for current system."""
        system = self.local_system.get()
        
        if system == AppConfig.DEFAULT_SYSTEM or not system:
            self.spansh_system_label.config(text="⚠ System: Unknown - Start engine first")
            return
        
        self.spansh_system_label.config(text=f"System: {system}")
        
        if not BROWSER_AVAILABLE:
            self.open_spansh_external()
            return
        
        # Clear previous frame
        if self.spansh_frame:
            self.spansh_frame.destroy()
        
        # Create new browser frame
        encoded_system = urllib.parse.quote(system)
        url = f"https://www.spansh.co.uk/search/{encoded_system}"
        
        self.spansh_frame = HtmlFrame(self.spansh_container, 
                                     messages_enabled=False)
        self.spansh_frame.pack(fill='both', expand=True)
        self.spansh_frame.load_website(url)
    
    def open_inara_external(self):
        """Open INARA in external browser."""
        system = self.local_system.get()
        if system == AppConfig.DEFAULT_SYSTEM:
            messagebox.showwarning("Warning", "Start engine first!")
            return
        url = f"https://inara.cz/elite/nearest-stations/?formBrief=1&ps=1&{urllib.parse.quote(system)}"
        webbrowser.open(url)
    
    def open_spansh_external(self):
        """Open Spansh in external browser."""
        system = self.local_system.get()
        if system == AppConfig.DEFAULT_SYSTEM:
            messagebox.showwarning("Warning", "Start engine first!")
            return
        url = f"https://www.spansh.co.uk/search/{urllib.parse.quote(system)}"
        webbrowser.open(url)
    
    def build_engine_tab(self):
        """Build Engine tab."""
        frame = ttk.Frame(self.tab_engine, padding="20")
        frame.pack(fill='both', expand=True)
        
        title = ttk.Label(frame, text="🚀 ELITE DANGEROUS LOG PATH", 
                         font=("Arial", 12, "bold"),
                         foreground=AppConfig.COLOR_ED_ORANGE)
        title.pack(pady=(20, 5))
        
        path_frame = ttk.Frame(frame)
        path_frame.pack(fill='x', pady=10)
        
        entry = tk.Entry(path_frame, textvariable=self.log_path, 
                        font=("Consolas", 9),
                        bg=AppConfig.COLOR_ED_DARK_BG,
                        fg=AppConfig.COLOR_ED_TEXT,
                        insertbackground=AppConfig.COLOR_ED_ORANGE,
                        relief='flat',
                        borderwidth=2)
        entry.pack(side='left', fill='x', expand=True, ipady=5)
        
        ttk.Button(path_frame, text="Browse", command=self.browse_path).pack(
            side='right', padx=(5, 0))
        
        start_btn = ttk.Button(frame, text="⚡ START ENGINE", command=self.start_engine)
        start_btn.pack(pady=30)
        
        self.engine_status = tk.Label(frame, 
            text="Configure log path and click START ENGINE",
            bg=AppConfig.COLOR_ED_DARKER_BG,
            fg=AppConfig.COLOR_ED_TEXT_DIM,
            font=("Arial", 9))
        self.engine_status.pack(pady=10)
    
    def build_config_tab(self):
        """Build Config tab."""
        frame = ttk.Frame(self.tab_config, padding="20")
        frame.pack(fill='both', expand=True)
        
        # Commander
        cmdr_label = ttk.Label(frame, text="👤 COMMANDER", 
                              font=("Arial", 11, "bold"),
                              foreground=AppConfig.COLOR_ED_ORANGE)
        cmdr_label.pack(pady=(10, 5), anchor='w')
        
        cmdr_entry = tk.Entry(frame, textvariable=self.cmdr_name, 
                             font=("Consolas", 10),
                             bg=AppConfig.COLOR_ED_DARK_BG,
                             fg=AppConfig.COLOR_ED_TEXT,
                             state="readonly",
                             relief='flat',
                             borderwidth=2)
        cmdr_entry.pack(fill='x', pady=5, ipady=3)
        
        # Local System with refresh button
        system_label_frame = ttk.Frame(frame)
        system_label_frame.pack(fill='x', pady=(20, 5))
        
        sys_label = ttk.Label(system_label_frame, text="🌍 LOCAL SYSTEM", 
                             font=("Arial", 11, "bold"),
                             foreground=AppConfig.COLOR_ED_ORANGE)
        sys_label.pack(side='left')
        
        ttk.Button(system_label_frame, text="🔄 Refresh", 
                  command=self.refresh_system).pack(side='right')
        
        system_entry = tk.Entry(frame, textvariable=self.local_system, 
                               font=("Consolas", 10),
                               bg=AppConfig.COLOR_ED_DARK_BG,
                               fg=AppConfig.COLOR_ED_TEXT,
                               state="readonly",
                               relief='flat',
                               borderwidth=2)
        system_entry.pack(fill='x', pady=5, ipady=3)
        
        # Scanner Configuration
        config_label = ttk.Label(frame, text="⚙ SCANNER CONFIGURATION", 
                                font=("Arial", 11, "bold"),
                                foreground=AppConfig.COLOR_ED_ORANGE)
        config_label.pack(pady=(30, 10), anchor='w')
        
        config_frame = ttk.Frame(frame)
        config_frame.pack(fill='x', pady=5)
        
        ttk.Label(config_frame, text="Material:").grid(row=0, column=0, sticky='w', padx=5)
        material_combo = ttk.Combobox(config_frame, textvariable=self.material_name, 
                                     values=AppConfig.MATERIALS, state="readonly", width=20)
        material_combo.grid(row=0, column=1, padx=5, sticky='w')
        
        ttk.Label(config_frame, text="Min %:").grid(row=1, column=0, sticky='w', padx=5, pady=(10,0))
        percent_entry = tk.Entry(config_frame, textvariable=self.min_percentage, width=10,
                                bg=AppConfig.COLOR_ED_DARK_BG,
                                fg=AppConfig.COLOR_ED_TEXT,
                                insertbackground=AppConfig.COLOR_ED_ORANGE,
                                relief='flat')
        percent_entry.grid(row=1, column=1, padx=5, sticky='w', pady=(10,0))
        percent_entry.bind('<KeyRelease>', self.validate_percentage)
        
        ttk.Label(config_frame, text="Desired Sell Value (Cr):").grid(
            row=2, column=0, sticky='w', padx=5, pady=(5,0))
        sell_value_entry = tk.Entry(config_frame, textvariable=self.desired_sell_value, width=15,
                                    bg=AppConfig.COLOR_ED_DARK_BG,
                                    fg=AppConfig.COLOR_ED_TEXT,
                                    insertbackground=AppConfig.COLOR_ED_ORANGE,
                                    relief='flat')
        sell_value_entry.grid(row=2, column=1, padx=5, sticky='w', pady=(5,0))
        sell_value_entry.bind('<KeyRelease>', self.validate_sell_value)
        
        help_label = tk.Label(frame, 
            text="💡 Sell value is used to estimate hourly profit based on mining rate",
            bg=AppConfig.COLOR_ED_DARKER_BG,
            fg=AppConfig.COLOR_ED_TEXT_DIM,
            font=("Arial", 8, "italic"))
        help_label.pack(pady=5, anchor='w')
    
    def build_scan_tab(self):
        """Build Scan tab."""
        frame = ttk.Frame(self.tab_scan, padding="20")
        frame.pack(fill='both', expand=True)
        
        self.start_button = ttk.Button(frame, text="▶ Start Scanning", 
                                      command=self.toggle_scanning)
        self.start_button.pack(pady=10)
        
        # Progress bar
        progress_frame = ttk.Frame(frame)
        progress_frame.pack(fill='x', pady=10)
        self.progress_bar = ttk.Progressbar(progress_frame, length=600, mode='determinate')
        self.progress_bar.pack()
        
        self.progress_label = tk.Label(progress_frame, text="0.0% - Waiting...",
                                      bg=AppConfig.COLOR_ED_DARKER_BG,
                                      fg=AppConfig.COLOR_ED_TEXT,
                                      font=("Arial", 10, "bold"))
        self.progress_label.pack(pady=5)
        
        self.status_label = tk.Label(frame, text="Ready to scan",
                                    bg=AppConfig.COLOR_ED_DARKER_BG,
                                    fg=AppConfig.COLOR_ED_TEXT_DIM,
                                    font=("Arial", 9))
        self.status_label.pack(pady=5)
        
        # Mining Statistics
        stats_frame = ttk.LabelFrame(frame, text="📊 MINING SESSION STATISTICS", padding="10")
        stats_frame.pack(fill='x', pady=15)
        stats_grid = ttk.Frame(stats_frame)
        stats_grid.pack(fill='x')
        
        ttk.Label(stats_grid, text="⛏ Rocks Mined:", font=("Arial", 9, "bold")).grid(
            row=0, column=0, sticky='w', padx=5)
        self.mined_count_label = tk.Label(stats_grid, text="0",
                                         bg=AppConfig.COLOR_ED_DARKER_BG,
                                         fg=AppConfig.COLOR_INFO,
                                         font=("Arial", 10, "bold"))
        self.mined_count_label.grid(row=0, column=1, sticky='w', padx=10)
        
        ttk.Label(stats_grid, text="💰 Est. Hourly Profit:", font=("Arial", 9, "bold")).grid(
            row=1, column=0, sticky='w', padx=5, pady=(5,0))
        self.hourly_profit_label = tk.Label(stats_grid, text="0 Cr/hr",
                                           bg=AppConfig.COLOR_ED_DARKER_BG,
                                           fg=AppConfig.COLOR_SUCCESS,
                                           font=("Arial", 10, "bold"))
        self.hourly_profit_label.grid(row=1, column=1, sticky='w', padx=10, pady=(5,0))
        
        ttk.Label(stats_grid, text="⏱ Session Duration:", font=("Arial", 9, "bold")).grid(
            row=2, column=0, sticky='w', padx=5)
        self.session_duration_label = tk.Label(stats_grid, text="0m 0s",
                                              bg=AppConfig.COLOR_ED_DARKER_BG,
                                              fg=AppConfig.COLOR_ED_TEXT,
                                              font=("Arial", 10))
        self.session_duration_label.grid(row=2, column=1, sticky='w', padx=10)
        
        ttk.Button(stats_frame, text="🔄 Reset Statistics", 
                  command=self.reset_stats).pack(pady=5)
        
        # History
        history_label = ttk.Label(frame, text="📜 DETECTION HISTORY (Above Threshold)", 
                                 font=("Arial", 10, "bold"),
                                 foreground=AppConfig.COLOR_ED_ORANGE)
        history_label.pack(pady=(20, 5))
        
        history_frame = ttk.Frame(frame)
        history_frame.pack(fill='both', expand=True, pady=5)
        
        columns = ("timestamp", "material", "percentage", "threshold")
        self.history_tree = ttk.Treeview(history_frame, columns=columns, 
                                        show='headings', height=8)
        
        self.history_tree.heading("timestamp", text="Timestamp")
        self.history_tree.heading("material", text="Material")
        self.history_tree.heading("percentage", text="Percentage")
        self.history_tree.heading("threshold", text="Threshold")
        
        self.history_tree.column("timestamp", width=150, anchor='center')
        self.history_tree.column("material", width=200, anchor='center')
        self.history_tree.column("percentage", width=120, anchor='center')
        self.history_tree.column("threshold", width=120, anchor='center')
        
        scrollbar = ttk.Scrollbar(history_frame, orient="vertical", 
                                 command=self.history_tree.yview)
        self.history_tree.configure(yscrollcommand=scrollbar.set)
        
        self.history_tree.pack(side='left', fill='both', expand=True)
        scrollbar.pack(side='right', fill='y')
        
        ttk.Button(frame, text="🗑 Clear History", command=self.clear_history).pack(pady=10)
    
    def build_stations_tab(self):
        """Build Stations tab."""
        frame = ttk.Frame(self.tab_stations, padding="20")
        frame.pack(fill='both', expand=True)
        
        # Header with refresh button
        header_frame = ttk.Frame(frame)
        header_frame.pack(fill='x', pady=(0, 20))
        
        title = ttk.Label(header_frame, text="🚉 STATIONS & FLEET CARRIERS", 
                         font=("Arial", 11, "bold"),
                         foreground=AppConfig.COLOR_ED_ORANGE)
        title.pack(side='left')
        
        ttk.Button(header_frame, text="🔄 Refresh", 
                  command=self.load_all_stations).pack(side='right')
        
        # Stations tree
        stations_frame = ttk.Frame(frame)
        stations_frame.pack(fill='both', expand=True, pady=5)
        
        columns = ("Type", "Name")
        self.stations_tree = ttk.Treeview(stations_frame, columns=columns, 
                                         show='headings', height=20)
        
        self.stations_tree.heading("Type", text="Type")
        self.stations_tree.heading("Name", text="Name")
        
        self.stations_tree.column("Type", width=150, anchor='center')
        self.stations_tree.column("Name", width=600, anchor='w')
        
        scrollbar = ttk.Scrollbar(stations_frame, orient="vertical", 
                                 command=self.stations_tree.yview)
        self.stations_tree.configure(yscrollcommand=scrollbar.set)
        
        self.stations_tree.pack(side='left', fill='both', expand=True)
        scrollbar.pack(side='right', fill='y')
        
        ttk.Button(frame, text="🗑 Clear Stations", 
                  command=self.clear_stations).pack(pady=10)
    
    # Event handlers
    def set_default_log_path(self):
        """Set default log path."""
        default_path = AppConfig.get_default_log_path()
        self.log_path.set(default_path)
    
    def browse_path(self):
        """Browse for log directory."""
        filename = filedialog.askdirectory(initialdir=self.log_path.get())
        if filename:
            self.log_path.set(filename)
    
    def start_engine(self):
        """Start engine and read journal."""
        if not self.log_path.get():
            messagebox.showerror("Error", "Log path not set!")
            return
        
        try:
            self.journal_reader = JournalReader(self.log_path.get())
            
            # Read commander and system
            cmdr = self.journal_reader.read_commander()
            system = self.journal_reader.read_current_system()
            
            if cmdr:
                self.cmdr_name.set(cmdr)
                print(f"Commander found: {cmdr}")
            if system:
                self.local_system.set(system)
                print(f"System found: {system}")
            
            if not cmdr and not system:
                messagebox.showwarning("Warning", 
                    "No commander or system found in journal. Journal may be empty.")
            
            self.engine_started = True
            self.engine_status.config(
                text=f"✅ Engine started! CMDR: {self.cmdr_name.get()}, System: {self.local_system.get()}", 
                fg=AppConfig.COLOR_SUCCESS)
            
            # Enable all tabs
            self.notebook.tab(1, state="normal")  # Config
            self.notebook.tab(2, state="normal")  # Scan
            self.notebook.tab(4, state="normal")  # Miners Tool
            self.notebook.tab(5, state="normal")  # INARA
            self.notebook.tab(6, state="normal")  # Spansh
            self.notebook.tab(0, state="disabled")  # Engine
            self.notebook.select(1)  # Switch to Config
            
            # Initialize event processor
            self.event_processor = EventProcessor(
                on_asteroid_found=self.on_asteroid_found,
                on_material_refined=self.on_material_refined,
                on_docked=self.on_docked,
                on_station_found=self.on_station_found
            )
            
            messagebox.showinfo("Success", "Engine started successfully!")
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed to start engine: {str(e)}")
            print(f"Engine start error: {str(e)}")
    
    def refresh_system(self):
        """Refresh current system from journal."""
        if not self.journal_reader:
            messagebox.showwarning("Warning", "Engine not started!")
            return
        
        system = self.journal_reader.read_current_system()
        if system:
            self.local_system.set(system)
            self.tts.speak(f"System updated to {system}")
            messagebox.showinfo("Success", f"System updated to: {system}")
        else:
            messagebox.showwarning("Warning", "No system found in journal")
    
    def toggle_scanning(self):
        """Toggle scanning on/off."""
        if not self.running:
            if not self.validate_inputs():
                return
            self.running = True
            self.start_button.config(text="⏸ Stop Scanning")
            self.status_label.config(text="✅ Scanning journal logs...", 
                                    fg=AppConfig.COLOR_SUCCESS)
            
            # Enable Stations tab
            self.notebook.tab(3, state="normal")
            
            threading.Thread(target=self.scan_loop, daemon=True).start()
        else:
            self.running = False
            self.start_button.config(text="▶ Start Scanning")
            self.status_label.config(text="⏸ Stopped", 
                                    fg=AppConfig.COLOR_WARNING)
    
    def scan_loop(self):
        """Main scanning loop."""
        while self.running:
            try:
                line = self.journal_reader.get_latest_line()
                if line:
                    self.event_processor.process_line(
                        line,
                        self.material_name.get(),
                        float(self.min_percentage.get())
                    )
                time.sleep(0.5)
            except Exception as e:
                print(f"Scan loop error: {str(e)}")
                time.sleep(2)
    
    def on_asteroid_found(self, material, proportion, min_pct, timestamp):
        """Handle asteroid found event."""
        self.update_progress(proportion, f"{material} detected")
        
        if proportion >= min_pct:
            self.mining_stats.add_refined_material(timestamp)
            entry = self.detection_history.add(material, proportion, min_pct)
            
            # Update UI
            self.root.after(0, lambda: self.history_tree.insert("", "end", values=(
                entry["timestamp"], entry["material"], 
                f"{entry['percentage']:.1f}%", f"{entry['threshold']:.1f}%")))
            
            # Speak
            message = f"{material} {proportion:.0f} percent!"
            self.tts.speak(message)
    
    def on_material_refined(self, material, timestamp):
        """Handle material refined event."""
        self.mining_stats.add_refined_material(timestamp)
        self.update_mining_display()
        self.root.after(0, lambda: self.status_label.config(
            text=f"✅ Refined {material} - Total: {self.mining_stats.mined_count}", 
            fg=AppConfig.COLOR_SUCCESS))
    
    def on_docked(self):
        """Handle docked event."""
        self.mining_stats.reset()
        self.update_mining_display()
        self.root.after(0, lambda: self.status_label.config(
            text="🚉 Docked - Stats reset", fg=AppConfig.COLOR_INFO))
        self.tts.speak("Docked")
    
    def on_station_found(self, station_type, name):
        """Handle station found event."""
        station_key = (station_type, name)
        if station_key not in self.stations_list:
            self.stations_list.append(station_key)
            self.root.after(0, lambda: self.stations_tree.insert("", "end", 
                                                                 values=(station_type, name)))
            self.tts.speak(f"Found {station_type}")
    
    def load_all_stations(self):
        """Load all stations from journal."""
        if not self.journal_reader:
            return
        
        # Clear current list
        self.stations_list.clear()
        for item in self.stations_tree.get_children():
            self.stations_tree.delete(item)
        
        # Load from journal
        stations = self.journal_reader.read_all_stations()
        for station_type, name in stations:
            station_key = (station_type, name)
            if station_key not in self.stations_list:
                self.stations_list.append(station_key)
                self.stations_tree.insert("", "end", values=(station_type, name))
        
        self.status_label.config(text=f"📊 Loaded {len(stations)} stations", 
                                fg=AppConfig.COLOR_INFO)
    
    def clear_stations(self):
        """Clear stations list."""
        self.stations_list.clear()
        for item in self.stations_tree.get_children():
            self.stations_tree.delete(item)
        self.status_label.config(text="🗑 Stations cleared", 
                                fg=AppConfig.COLOR_INFO)
    
    def update_progress(self, value, label_text):
        """Update progress bar."""
        self.root.after(0, lambda: self._update_progress_ui(value, label_text))
    
    def _update_progress_ui(self, value, label_text):
        """Update progress UI (main thread)."""
        try:
            self.progress_bar['value'] = value
            self.progress_label.config(text=f"{value:.1f}% - {label_text}")
            min_pct = float(self.min_percentage.get())
            color = AppConfig.COLOR_ERROR if value >= min_pct else AppConfig.COLOR_ED_TEXT
            self.progress_label.config(fg=color)
        except:
            pass
    
    def update_mining_display(self):
        """Update mining statistics display."""
        self.root.after(0, self._update_mining_ui)
    
    def _update_mining_ui(self):
        """Update mining UI (main thread)."""
        try:
            self.mined_count_label.config(text=str(self.mining_stats.mined_count))
            
            sell_value = int(self.desired_sell_value.get().replace(',', ''))
            hourly_profit = self.mining_stats.get_hourly_profit(sell_value)
            
            if hourly_profit > 0:
                self.hourly_profit_label.config(
                    text=f"{hourly_profit:,.0f} Cr/hr", fg=AppConfig.COLOR_SUCCESS)
            else:
                self.hourly_profit_label.config(text="0 Cr/hr", fg=AppConfig.COLOR_SUCCESS)
            
            minutes, seconds = self.mining_stats.get_session_duration()
            self.session_duration_label.config(text=f"{minutes}m {seconds}s")
        except:
            pass
    
    def reset_stats(self):
        """Reset mining statistics."""
        self.mining_stats.reset()
        self.update_mining_display()
        self.status_label.config(text="🔄 Statistics reset", fg=AppConfig.COLOR_INFO)
    
    def clear_history(self):
        """Clear detection history."""
        self.detection_history.clear()
        for item in self.history_tree.get_children():
            self.history_tree.delete(item)
        self.status_label.config(text="🗑 History cleared", fg=AppConfig.COLOR_INFO)
    
    def validate_percentage(self, event=None):
        """Validate percentage input."""
        try:
            value = self.min_percentage.get()
            if value:
                pct = float(value)
                if pct < 1:
                    self.min_percentage.set("1")
                elif pct > 99:
                    self.min_percentage.set("99")
        except:
            self.min_percentage.set(AppConfig.DEFAULT_MIN_PERCENTAGE)
    
    def validate_sell_value(self, event=None):
        """Validate sell value input."""
        try:
            value = self.desired_sell_value.get()
            if value:
                val = int(value.replace(',', ''))
                if val < 0:
                    self.desired_sell_value.set("0")
        except:
            self.desired_sell_value.set(AppConfig.DEFAULT_SELL_VALUE)
    
    def validate_inputs(self):
        """Validate all inputs."""
        if not self.material_name.get():
            messagebox.showerror("Error", "Select a material!")
            return False
        try:
            pct = float(self.min_percentage.get())
            if pct < 1 or pct > 99:
                messagebox.showerror("Error", "Percentage must be 1-99!")
                return False
        except:
            messagebox.showerror("Error", "Invalid percentage!")
            return False
        return True

if __name__ == "__main__":
    root = tk.Tk()
    app = EliteMaterialScanner(root)
    root.mainloop()

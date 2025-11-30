#!/usr/bin/env python3
"""
Elite Dangerous Log Reader Service - Refactored with centralized managers.
Background service that monitors Elite Dangerous journal files and populates database.

Features:
- Monitors journal directory for new/updated files
- Parses JSON journal entries
- Updates database with game state, ship status, asteroids, chat, etc.
- Runs as detached background process
- Heartbeat system for status monitoring
"""

import os
import sys
import time
import json
import logging
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any, List
import signal

from core.core_database import get_db, init_db


# Configure logging
DATA_DIR.mkdir(exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_READER_LOG),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ============================================================================
# JOURNAL FILE MONITOR
# ============================================================================
class JournalMonitor:
    """Monitors Elite Dangerous journal directory for new entries."""

    def __init__(self, journal_dir: str):
        self.journal_dir = Path(journal_dir)
        self.current_file: Optional[Path] = None
        self.file_handle: Optional[object] = None
        self.last_position = 0

        logger.info(f"Journal monitor initialized: {self.journal_dir}")

    def find_latest_journal(self) -> Optional[Path]:
        """Find the most recent journal file."""
        try:
            journal_files = list(self.journal_dir.glob("Journal.*.log"))
            if not journal_files:
                logger.warning("No journal files found")
                return None

            # Sort by modification time
            latest = max(journal_files, key=lambda f: f.stat().st_mtime)
            logger.info(f"Latest journal: {latest.name}")
            return latest
        except Exception as e:
            logger.error(f"Error finding journal: {e}")
            return None

    def open_journal(self, journal_file: Path) -> bool:
        """Open journal file for reading."""
        try:
            if self.file_handle:
                self.file_handle.close()

            self.current_file = journal_file
            self.file_handle = open(journal_file, 'r', encoding='utf-8')

            # Seek to end to only read new entries
            self.file_handle.seek(0, 2)
            self.last_position = self.file_handle.tell()

            logger.info(f"Opened journal: {journal_file.name}")
            return True
        except Exception as e:
            logger.error(f"Error opening journal: {e}")
            return False

    def check_for_new_file(self) -> bool:
        """Check if a newer journal file exists."""
        latest = self.find_latest_journal()
        if latest and latest != self.current_file:
            logger.info(f"New journal detected: {latest.name}")
            return self.open_journal(latest)
        return False

    def read_new_lines(self) -> List[str]:
        """Read new lines from current journal file."""
        if not self.file_handle:
            return []

        try:
            # Check for new file first
            self.check_for_new_file()

            # Read new content
            self.file_handle.seek(self.last_position)
            lines = self.file_handle.readlines()
            self.last_position = self.file_handle.tell()

            return [line.strip() for line in lines if line.strip()]
        except Exception as e:
            logger.error(f"Error reading journal: {e}")
            return []

    def close(self):
        """Close journal file handle."""
        if self.file_handle:
            self.file_handle.close()
            self.file_handle = None
            logger.info("Journal monitor closed")


# ============================================================================
# JOURNAL EVENT PROCESSOR
# ============================================================================
class JournalProcessor:
    """Processes journal events and updates database."""

    def __init__(self):
        self.db = get_db()
        self.config = load_config()
        logger.info("Journal processor initialized")

    def process_line(self, line: str) -> None:
        """Process a single journal line."""
        try:
            data = json.loads(line)
            event = data.get('event', '')

            # Route to appropriate handler
            handler = getattr(self, f'_handle_{event}', None)
            if handler:
                handler(data)
            else:
                # Log unhandled events at debug level
                logger.debug(f"Unhandled event: {event}")
        except json.JSONDecodeError as e:
            logger.error(f"JSON decode error: {e} | Line: {line[:100]}")
        except Exception as e:
            logger.error(f"Error processing line: {e} | Line: {line[:100]}")

    # ========================================================================
    # GAME STATE EVENTS
    # ========================================================================
    def _handle_LoadGame(self, data: Dict[str, Any]) -> None:
        """Handle LoadGame event (commander, ship, credits)."""
        try:
            commander = data.get('Commander', 'Unknown')
            ship = data.get('Ship', 'Unknown')
            credits = data.get('Credits', 0)

            self.db.update_game_state(commander_name=commander)
            self.db.update_ship_status(commander_credits=credits)

            logger.info(f"LoadGame: {commander} in {ship}, {credits:,} Cr")
        except Exception as e:
            logger.error(f"Error handling LoadGame: {e}")

    def _handle_Location(self, data: Dict[str, Any]) -> None:
        """Handle Location event (system change)."""
        try:
            system_name = data.get('StarSystem', 'Unknown')
            self.db.update_game_state(current_system=system_name)
            logger.info(f"Location: {system_name}")
        except Exception as e:
            logger.error(f"Error handling Location: {e}")

    def _handle_FSDJump(self, data: Dict[str, Any]) -> None:
        """Handle FSD jump (system change)."""
        try:
            system_name = data.get('StarSystem', 'Unknown')
            self.db.update_game_state(current_system=system_name)
            logger.info(f"FSDJump: {system_name}")
        except Exception as e:
            logger.error(f"Error handling FSDJump: {e}")

    def _handle_Docked(self, data: Dict[str, Any]) -> None:
        """Handle Docked event."""
        try:
            station = data.get('StationName', 'Unknown')
            system = data.get('StarSystem', 'Unknown')
            logger.info(f"Docked: {station} in {system}")
        except Exception as e:
            logger.error(f"Error handling Docked: {e}")

    # ========================================================================
    # SHIP STATUS EVENTS
    # ========================================================================
    def _handle_Loadout(self, data: Dict[str, Any]) -> None:
        """Handle Loadout event (ship info including cargo capacity)."""
        try:
            # Extract cargo capacity from modules
            cargo_capacity = 0
            modules = data.get('Modules', [])
            for module in modules:
                if 'CargoCapacity' in module:
                    cargo_capacity += module['CargoCapacity']

            if cargo_capacity > 0:
                self.db.update_ship_status(cargo_capacity=cargo_capacity)
                logger.info(f"Loadout: Cargo capacity {cargo_capacity}")
        except Exception as e:
            logger.error(f"Error handling Loadout: {e}")

    def _handle_Cargo(self, data: Dict[str, Any]) -> None:
        """Handle Cargo event (cargo hold contents)."""
        try:
            inventory = data.get('Inventory', [])

            # Count total cargo and limpets
            cargo_count = 0
            limpet_count = 0

            for item in inventory:
                name = item.get('Name', '').lower()
                count = item.get('Count', 0)

                if 'limpet' in name:
                    limpet_count += count
                else:
                    cargo_count += count

            self.db.update_ship_status(cargo_count=cargo_count, limpet_count=limpet_count)
            logger.info(f"Cargo: {cargo_count} items, {limpet_count} limpets")
        except Exception as e:
            logger.error(f"Error handling Cargo: {e}")

    def _handle_Materials(self, data: Dict[str, Any]) -> None:
        """Handle Materials event (raw/encoded/manufactured)."""
        # This tracks inventory materials, not directly used but logged
        try:
            raw_count = len(data.get('Raw', []))
            encoded_count = len(data.get('Encoded', []))
            manufactured_count = len(data.get('Manufactured', []))
            logger.debug(f"Materials: {raw_count} raw, {encoded_count} encoded, {manufactured_count} manufactured")
        except Exception as e:
            logger.error(f"Error handling Materials: {e}")

    # ========================================================================
    # MINING EVENTS
    # ========================================================================
    def _handle_ProspectedAsteroid(self, data: Dict[str, Any]) -> None:
        """Handle ProspectedAsteroid event (asteroid scan)."""
        try:
            materials = data.get('Materials', [])
            content = data.get('Content', 'Unknown')
            remaining = data.get('Remaining', 100.0)
            motherlode = data.get('MotherlodeAmount', 0)
            timestamp = data.get('timestamp', datetime.utcnow().isoformat())

            for material in materials:
                material_name = material.get('Name', 'Unknown')
                # Clean up material name (remove _Name suffix)
                if '_Name' in material_name:
                    material_name = material_name.replace('_Name', '')

                percentage = material.get('Proportion', 0.0) * 100

                # Determine if surface or deepcore
                is_surface = 1 if motherlode == 0 else 0
                is_deepcore = 1 if motherlode > 0 else 0
                is_motherlode = 1 if motherlode > 0 else 0

                # Insert into database
                cursor = self.db.connection.cursor()
                cursor.execute("""
                    INSERT INTO prospected_asteroids 
                    (timestamp, journal_timestamp, material_name, percentage, 
                     is_motherlode, content_level, is_surface, is_deepcore, remaining, processed)
                    VALUES (CURRENT_TIMESTAMP, ?, ?, ?, ?, ?, ?, ?, ?, 0)
                """, (timestamp, material_name, percentage, is_motherlode, 
                      content, is_surface, is_deepcore, remaining))
                self.db.connection.commit()

                logger.info(f"Prospected: {material_name} {percentage:.1f}% ({'Deepcore' if is_deepcore else 'Surface'})")
        except Exception as e:
            logger.error(f"Error handling ProspectedAsteroid: {e}")

    def _handle_MiningRefined(self, data: Dict[str, Any]) -> None:
        """Handle MiningRefined event (material collected)."""
        try:
            material_name = data.get('Type', 'Unknown')
            if '_Name' in material_name:
                material_name = material_name.replace('_Name', '')

            timestamp = data.get('timestamp', datetime.utcnow().isoformat())

            cursor = self.db.connection.cursor()
            cursor.execute("""
                INSERT INTO refined_materials 
                (timestamp, journal_timestamp, material_name, material_type)
                VALUES (CURRENT_TIMESTAMP, ?, ?, 'mining')
            """, (timestamp, material_name))
            self.db.connection.commit()

            logger.info(f"Refined: {material_name}")
        except Exception as e:
            logger.error(f"Error handling MiningRefined: {e}")

    # ========================================================================
    # FSS / DISCOVERY EVENTS
    # ========================================================================
    def _handle_FSSSignalDiscovered(self, data: Dict[str, Any]) -> None:
        """Handle FSS signal discovered (stations, fleet carriers)."""
        try:
            signal_name = data.get('SignalName', 'Unknown')
            signal_type = data.get('SignalName_Localised', signal_name)
            is_station = data.get('IsStation', False)
            system_address = data.get('SystemAddress', 0)
            timestamp = data.get('timestamp', datetime.utcnow().isoformat())

            # Get current system
            state = self.db.get_game_state()
            system_name = state.get('current_system', 'Unknown')

            # Check if it's a fleet carrier
            if 'FleetCarrier' in signal_type or signal_name.endswith(')'):
                self.db.add_fleet_carrier(signal_name, system_address, system_name, timestamp)
                logger.info(f"Fleet Carrier discovered: {signal_name}")
            elif is_station:
                self.db.add_fss_signal(signal_name, signal_type, is_station, 
                                      system_address, system_name, timestamp)
                logger.info(f"Station discovered: {signal_name}")
        except Exception as e:
            logger.error(f"Error handling FSSSignalDiscovered: {e}")

    # ========================================================================
    # CHAT / COMMUNICATION EVENTS
    # ========================================================================
    def _handle_ReceiveText(self, data: Dict[str, Any]) -> None:
        """Handle ReceiveText event (chat messages)."""
        try:
            self.db.add_chat_message(data)

            channel = data.get('Channel', 'unknown')
            sender = data.get('From_Localised', 'Unknown')
            message = data.get('Message_Localised', '')[:50]

            logger.info(f"Chat [{channel}] {sender}: {message}...")
        except Exception as e:
            logger.error(f"Error handling ReceiveText: {e}")

    # ========================================================================
    # CREDITS / ECONOMY EVENTS
    # ========================================================================
    def _handle_MarketSell(self, data: Dict[str, Any]) -> None:
        """Handle MarketSell event (commodity sales, updates credits)."""
        try:
            total_sale = data.get('TotalSale', 0)
            item = data.get('Type', 'Unknown')
            count = data.get('Count', 0)

            # Update credits (need to get current and add)
            status = self.db.get_ship_status()
            current_credits = status.get('commander_credits', 0)
            new_credits = current_credits + total_sale

            self.db.update_ship_status(commander_credits=new_credits)
            logger.info(f"MarketSell: {count}x {item} for {total_sale:,} Cr (Total: {new_credits:,} Cr)")
        except Exception as e:
            logger.error(f"Error handling MarketSell: {e}")

    def _handle_MarketBuy(self, data: Dict[str, Any]) -> None:
        """Handle MarketBuy event (commodity purchases, updates credits)."""
        try:
            total_cost = data.get('TotalCost', 0)
            item = data.get('Type', 'Unknown')
            count = data.get('Count', 0)

            # Update credits
            status = self.db.get_ship_status()
            current_credits = status.get('commander_credits', 0)
            new_credits = current_credits - total_cost

            self.db.update_ship_status(commander_credits=new_credits)
            logger.info(f"MarketBuy: {count}x {item} for {total_cost:,} Cr (Total: {new_credits:,} Cr)")
        except Exception as e:
            logger.error(f"Error handling MarketBuy: {e}")

    def _handle_SellExplorationData(self, data: Dict[str, Any]) -> None:
        """Handle exploration data sales."""
        try:
            base_value = data.get('BaseValue', 0)
            bonus = data.get('Bonus', 0)
            total = base_value + bonus

            # Update credits
            status = self.db.get_ship_status()
            current_credits = status.get('commander_credits', 0)
            new_credits = current_credits + total

            self.db.update_ship_status(commander_credits=new_credits)
            logger.info(f"Exploration sold: {total:,} Cr (Total: {new_credits:,} Cr)")
        except Exception as e:
            logger.error(f"Error handling SellExplorationData: {e}")


# ============================================================================
# LOG READER SERVICE
# ============================================================================
class LogReaderService:
    """Main log reader service coordinator."""

    def __init__(self, journal_dir: str):
        self.journal_dir = journal_dir
        self.monitor = JournalMonitor(journal_dir)
        self.processor = JournalProcessor()
        self.running = False
        self.scan_interval = 0.5  # seconds

        # Setup signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

        logger.info(f"Log reader service initialized: {journal_dir}")

    def _signal_handler(self, signum, frame):
        """Handle shutdown signals."""
        logger.info(f"Received signal {signum}, shutting down...")
        self.stop()

    def start(self) -> None:
        """Start the log reader service."""
        try:
            logger.info("Starting log reader service...")

            # Find and open latest journal
            latest_journal = self.monitor.find_latest_journal()
            if not latest_journal:
                logger.error("No journal files found, exiting")
                return

            if not self.monitor.open_journal(latest_journal):
                logger.error("Failed to open journal, exiting")
                return

            # Update service status in database
            self.processor.db.update_service_status(
                is_running=1,
                pid=os.getpid(),
                last_heartbeat=datetime.utcnow().isoformat(),
                journal_file=str(latest_journal),
                scan_interval=self.scan_interval
            )

            self.running = True
            logger.info("Log reader service started successfully")

            # Main loop
            self._run_loop()
        except Exception as e:
            logger.error(f"Error starting service: {e}")
            self.stop()

    def _run_loop(self) -> None:
        """Main processing loop."""
        heartbeat_counter = 0
        heartbeat_interval = 10  # Update every 10 iterations

        while self.running:
            try:
                # Read new lines from journal
                lines = self.monitor.read_new_lines()

                # Process each line
                for line in lines:
                    self.processor.process_line(line)

                # Update heartbeat periodically
                heartbeat_counter += 1
                if heartbeat_counter >= heartbeat_interval:
                    self.processor.db.update_service_status(
                        last_heartbeat=datetime.utcnow().isoformat()
                    )
                    heartbeat_counter = 0

                # Sleep between scans
                time.sleep(self.scan_interval)
            except KeyboardInterrupt:
                logger.info("Keyboard interrupt received")
                break
            except Exception as e:
                logger.error(f"Error in main loop: {e}")
                time.sleep(1)  # Prevent tight error loop

    def stop(self) -> None:
        """Stop the log reader service."""
        logger.info("Stopping log reader service...")
        self.running = False

        # Update database
        try:
            self.processor.db.update_service_status(
                is_running=0,
                last_heartbeat=datetime.utcnow().isoformat()
            )
        except Exception as e:
            logger.error(f"Error updating service status: {e}")

        # Close monitor
        self.monitor.close()

        logger.info("Log reader service stopped")


# ============================================================================
# MAIN ENTRY POINT
# ============================================================================
def main():
    """Main entry point."""
    # Get journal directory from command line or use default
    if len(sys.argv) > 1:
        journal_dir = sys.argv[1]
    else:
        # Default Windows path
        journal_dir = os.path.join(
            os.path.expanduser("~"),
            "Saved Games",
            "Frontier Developments",
            "Elite Dangerous"
        )

    logger.info("="*60)
    logger.info("ED Log Reader Service Starting")
    logger.info("="*60)
    logger.info(f"Journal directory: {journal_dir}")
    logger.info(f"Log file: {LOG_READER_LOG}")
    logger.info(f"PID: {os.getpid()}")
    logger.info("="*60)

    # Verify directory exists
    if not os.path.isdir(journal_dir):
        logger.error(f"Journal directory does not exist: {journal_dir}")
        sys.exit(1)

    # Create and start service
    service = LogReaderService(journal_dir)
    service.start()

    logger.info("ED Log Reader Service Exiting")


if __name__ == "__main__":
    main()

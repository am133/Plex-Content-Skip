import tkinter as tk
from tkinter import ttk, StringVar, messagebox
from datetime import timedelta
from plexapi.server import PlexServer
from plexapi.alert import AlertListener
from dotenv import load_dotenv
import os
import time
import requests
import json

# Load environment variables
load_dotenv()

# Plex server details
PLEX_SERVER_URL = os.getenv("PLEX_SERVER_URL")
PLEX_TOKEN = os.getenv("PLEX_TOKEN")
BACKEND_URL = "http://127.0.0.1:8000"  # Your FastAPI backend


def format_time(milliseconds):
    """Convert milliseconds to HH:MM:SS format."""
    seconds = milliseconds // 1000
    return str(timedelta(seconds=seconds))


class PlexViewer:
    def __init__(self):
        self.plex = PlexServer(PLEX_SERVER_URL, PLEX_TOKEN)
        self.sessions = {}
        self.selected_session_key = None
        self.alert_listener = None
        self.last_view_offset = 0
        self.last_update_time = 0
        self.playback_state = 'stopped'
        self.current_duration = 0

        # Timestamp marking
        self.start_timestamp = None
        self.current_media_type = None
        self.current_media_info = {}

    def fetch_active_sessions(self):
        """Fetch active sessions from Plex."""
        self.sessions = {}
        try:
            sessions = self.plex.sessions()
            for session in sessions:
                player = session.players[0]  # Assume one player per session
                session_key = str(session.sessionKey)
                self.sessions[session_key] = {
                    'sessionKey': session_key,
                    'machineIdentifier': player.machineIdentifier,
                    'title': session.title,
                    'state': player.state,
                    'viewOffset': session.viewOffset,
                    'duration': session.duration,
                    'product': player.product,
                    'platform': player.platform,
                    'player': player.title
                }
        except Exception as e:
            self.update_error(f"Error fetching sessions: {e}")

    def create_label_dialog(self, start_time, end_time):
        """Create a dialog for label input."""
        dialog = tk.Toplevel(self.root)
        dialog.title("Add Timestamp Label")
        dialog.geometry("400x200")
        dialog.transient(self.root)  # Make dialog modal
        dialog.grab_set()  # Make dialog modal

        # Center the dialog
        dialog.geometry("+%d+%d" % (
            self.root.winfo_x() + self.root.winfo_width() / 2 - 200,
            self.root.winfo_y() + self.root.winfo_height() / 2 - 100))

        # Create a frame with padding
        frame = ttk.Frame(dialog, padding="20")
        frame.pack(fill=tk.BOTH, expand=True)

        # Show selected time range
        ttk.Label(
            frame,
            text=f"Selected Range:\n{format_time(start_time)} - {format_time(end_time)}",
            font=('Arial', 10)
        ).pack(pady=(0, 10))

        # Label input
        ttk.Label(
            frame,
            text="Enter a label for this timestamp (optional):",
            font=('Arial', 10)
        ).pack(pady=(0, 5))

        label_var = tk.StringVar()
        entry = ttk.Entry(frame, textvariable=label_var, width=40)
        entry.pack(pady=(0, 20))
        entry.focus()  # Put cursor in entry field

        def submit():
            dialog.result = label_var.get()
            dialog.destroy()

        def cancel():
            dialog.result = None
            dialog.destroy()

        # Button frame
        button_frame = ttk.Frame(frame)
        button_frame.pack(fill=tk.X, pady=(0, 10))

        # Submit button
        submit_btn = ttk.Button(button_frame, text="Save", command=submit)
        submit_btn.pack(side=tk.RIGHT, padx=5)

        # Cancel button
        cancel_btn = ttk.Button(button_frame, text="Cancel", command=cancel)
        cancel_btn.pack(side=tk.RIGHT, padx=5)

        # Handle enter key
        entry.bind('<Return>', lambda e: submit())
        dialog.bind('<Escape>', lambda e: cancel())

        dialog.wait_window()  # Wait for the dialog to close
        return getattr(dialog, 'result', None)

    def mark_end_timestamp(self):
        """Mark the current position as end timestamp and send range to backend."""
        if not self.start_timestamp:
            messagebox.showerror("Error", "Please set a start timestamp first")
            return

        if self.playback_state == 'playing':
            elapsed_time = time.time() - self.last_update_time
            current_offset = self.last_view_offset + int(elapsed_time * 1000)
        else:
            current_offset = self.last_view_offset

        if current_offset <= self.start_timestamp:
            messagebox.showerror("Error", "End timestamp must be after start timestamp")
            return

        # Show dialog to get label
        label = self.create_label_dialog(self.start_timestamp, current_offset)

        # If user didn't cancel
        if label is not None:
            self.send_timestamps_to_backend(self.start_timestamp, current_offset, label)

    def send_timestamps_to_backend(self, start_time, end_time, label=None):
        """Send timestamp range to backend server."""
        if not self.current_media_type or not self.current_media_info:
            messagebox.showerror("Error", "No media selected")
            return

        timestamp_data = {
            "timestamps": [{
                "start_time": start_time / 1000,  # Convert to seconds
                "end_time": end_time / 1000,
                "label": label if label and label.strip() else None
            }]
        }

        try:
            if self.current_media_type == 'episode':
                endpoint = f"{BACKEND_URL}/tv-shows/add-timestamps/"
                data = {
                    **timestamp_data,
                    "show_name": self.current_media_info['show_name'],
                    "season": str(self.current_media_info['season']),
                    "episode_number": str(self.current_media_info['episode']),
                    "title": self.current_media_info['title']
                }
            else:  # movie
                endpoint = f"{BACKEND_URL}/movies/add-timestamps/"
                data = {
                    **timestamp_data,
                    "title": self.current_media_info['title']
                }

            response = requests.post(endpoint, json=data)
            response.raise_for_status()

            messagebox.showinfo("Success", "Timestamp range saved successfully!")
            self.start_timestamp = None  # Reset start timestamp
            self.update_timestamp_buttons()

            # Refresh timestamps display after saving
            self.fetch_existing_timestamps(self.sessions[self.selected_session_key])

        except requests.exceptions.RequestException as e:
            messagebox.showerror("Error", f"Failed to save timestamp range: {str(e)}")

    def create_session_section(self, parent):
        """Create the session selection section."""
        session_frame = ttk.LabelFrame(parent, text="Active Sessions", padding="10")
        session_frame.pack(fill=tk.X, pady=(0, 10))

        self.session_var = StringVar(self.root)
        self.session_var.set("Select a session")
        self.session_menu = ttk.OptionMenu(session_frame, self.session_var, "Select a session")
        self.session_menu.pack(fill=tk.X)

    def create_media_info_section(self, parent):
        """Create the media information section."""
        info_frame = ttk.LabelFrame(parent, text="Media Information", padding="10")
        info_frame.pack(fill=tk.X, pady=(0, 10))

        ttk.Label(info_frame, textvariable=self.title_var,
                  font=('Arial', 14, 'bold')).pack(fill=tk.X)
        ttk.Label(info_frame, textvariable=self.subtitle_var,
                  font=('Arial', 11)).pack(fill=tk.X, pady=(5, 0))
        ttk.Label(info_frame, textvariable=self.status_var,
                  font=('Arial', 12)).pack(fill=tk.X, pady=(10, 0))

    def create_playback_section(self, parent):
        """Create the playback progress section."""
        progress_frame = ttk.LabelFrame(parent, text="Playback Progress", padding="10")
        progress_frame.pack(fill=tk.X, pady=(0, 10))

        # Progress bar
        ttk.Progressbar(progress_frame, variable=self.progress_var,
                        maximum=100, length=400).pack(fill=tk.X, pady=(0, 5))

        # Time information
        time_frame = ttk.Frame(progress_frame)
        time_frame.pack(fill=tk.X)
        ttk.Label(time_frame, textvariable=self.time_var).pack(side=tk.LEFT)
        ttk.Label(time_frame, textvariable=self.remaining_var).pack(side=tk.RIGHT)

    def create_timestamp_section(self, parent):
        """Create the timestamp controls and display section."""
        timestamp_frame = ttk.LabelFrame(parent, text="Timestamps", padding="10")
        timestamp_frame.pack(fill=tk.BOTH, expand=True)

        # Controls
        controls_frame = ttk.Frame(timestamp_frame)
        controls_frame.pack(fill=tk.X, pady=(0, 10))

        self.start_button = ttk.Button(
            controls_frame,
            text="Mark Start",
            command=self.mark_start_timestamp
        )
        self.start_button.pack(side=tk.LEFT, padx=5)

        self.end_button = ttk.Button(
            controls_frame,
            text="Mark End",
            command=self.mark_end_timestamp,
            state='disabled'
        )
        self.end_button.pack(side=tk.LEFT, padx=5)

        ttk.Label(controls_frame, textvariable=self.timestamp_status_var,
                  font=('Arial', 10)).pack(side=tk.LEFT, padx=5)

        # Timestamp list
        list_frame = ttk.Frame(timestamp_frame)
        list_frame.pack(fill=tk.BOTH, expand=True)

        # Create scrollable frame for timestamps
        canvas = tk.Canvas(list_frame)
        scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=canvas.yview)
        self.scrollable_frame = ttk.Frame(canvas)

        self.scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )

        canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")


    def mark_start_timestamp(self):
        """Mark the current position as start timestamp."""
        if self.playback_state == 'playing':
            elapsed_time = time.time() - self.last_update_time
            current_offset = self.last_view_offset + int(elapsed_time * 1000)
        else:
            current_offset = self.last_view_offset

        self.start_timestamp = current_offset
        self.update_timestamp_buttons()
        self.timestamp_status_var.set(f"Start timestamp set: {format_time(current_offset)}")



    def update_timestamp_buttons(self):
        """Update the state of timestamp buttons."""
        if self.start_timestamp is None:
            self.end_button.config(state='disabled')
            self.start_button.config(state='normal')
        else:
            self.end_button.config(state='normal')
            self.start_button.config(state='disabled')

    def alert_callback(self, data):
        """Handle alerts for the selected session."""
        for notification in data.get('PlaySessionStateNotification', []):
            if str(notification.get('sessionKey')) == self.selected_session_key:
                state = notification.get('state')
                view_offset = notification.get('viewOffset', 0)
                metadata_key = notification.get('key')

                # Update state and time offset
                self.last_view_offset = view_offset
                self.last_update_time = time.time()
                self.playback_state = state

                # Fetch metadata
                try:
                    item = self.plex.fetchItem(metadata_key)
                    self.current_duration = getattr(item, 'duration', 0)
                    self.update_media_info(item)
                except Exception as e:
                    self.update_error(f"Error fetching metadata: {e}")

    def error_callback(self, error):
        """Handle alert listener errors."""
        self.update_error(f"Connection Error: {error}")

    def update_media_info(self, item):
        """Update the media information display."""
        media_type = getattr(item, 'type', 'Unknown')
        self.current_media_type = media_type

        if media_type == 'episode':
            show_name = getattr(item, 'grandparentTitle', 'Unknown Show')
            season = getattr(item, 'parentIndex', 'Unknown Season')
            episode = getattr(item, 'index', 'Unknown Episode')
            title = getattr(item, 'title', 'Unknown Title')

            self.current_media_info = {
                'show_name': show_name,
                'season': season,
                'episode': episode,
                'title': title
            }

            self.title_var.set(f"{show_name}")
            self.subtitle_var.set(f"Season {season}, Episode {episode} - {title}")

        elif media_type == 'movie':
            title = getattr(item, 'title', 'Unknown Movie')
            year = getattr(item, 'year', '')

            self.current_media_info = {
                'title': title
            }

            self.title_var.set(f"{title}")
            self.subtitle_var.set(f"Movie ({year})" if year else "Movie")

        self.update_playback_status()

    def update_playback_status(self):
        """Update the playback status display."""
        state_text = {
            'playing': '▶️ Playing',
            'paused': '⏸️ Paused',
            'stopped': '⏹️ Stopped'
        }.get(self.playback_state, self.playback_state.capitalize())

        self.status_var.set(state_text)

    def update_progress(self):
        """Update the progress bar and time labels."""
        if self.playback_state == 'playing':
            elapsed_time = time.time() - self.last_update_time
            current_offset = self.last_view_offset + int(elapsed_time * 1000)
        else:
            current_offset = self.last_view_offset

        if self.current_duration > 0:
            progress = (current_offset / self.current_duration) * 100
            self.progress_var.set(progress)

            time_remaining = self.current_duration - current_offset
            self.time_var.set(f"{format_time(current_offset)} / {format_time(self.current_duration)}")
            self.remaining_var.set(f"Remaining: {format_time(time_remaining)}")

    def fetch_existing_timestamps(self, session_data):
        """Fetch existing timestamps for the current media from backend."""
        try:
            # Determine media type and create request data
            if hasattr(self, 'current_media_type') and self.current_media_type == 'episode':
                endpoint = f"{BACKEND_URL}/tv-shows/get-timestamps/"
                data = {
                    "show_name": self.current_media_info['show_name'],
                    "season": str(self.current_media_info['season']),
                    "episode_number": str(self.current_media_info['episode']),
                    "title": self.current_media_info['title']
                }
            else:
                endpoint = f"{BACKEND_URL}/movies/get-timestamps/"
                data = {
                    "title": session_data['title']
                }

            response = requests.post(endpoint, json=data)
            response.raise_for_status()
            timestamps_data = response.json()

            # Just update the display - no timestamps is a normal state
            self.display_timestamps(timestamps_data.get('timestamps', []))

        except requests.exceptions.RequestException as e:
            # Only show error if it's a connection/server error, not for 404
            if not isinstance(e, requests.exceptions.HTTPError) or e.response.status_code != 404:
                self.update_error(f"Failed to fetch timestamps: {str(e)}")

    def display_timestamps(self, timestamps):
        """Display existing timestamps in the scrollable frame."""
        # Clear existing timestamps
        for widget in self.scrollable_frame.winfo_children():
            widget.destroy()

        if not timestamps:
            ttk.Label(
                self.scrollable_frame,
                text="No timestamps saved yet",
                font=('Arial', 10, 'italic'),
                foreground='gray'
            ).pack(fill=tk.X, padx=5, pady=10)
            return

        # Add each timestamp range
        for i, ts in enumerate(timestamps):
            frame = ttk.Frame(self.scrollable_frame)
            frame.pack(fill=tk.X, padx=5, pady=2)

            # Format times for display
            start_time = format_time(int(ts['start_time'] * 1000))
            end_time = format_time(int(ts['end_time'] * 1000))

            # Create label with timestamp info
            label_text = f"Range {i + 1}: {start_time} - {end_time}"
            if ts.get('label'):
                label_text += f" ({ts['label']})"

            ttk.Label(frame, text=label_text, font=('Arial', 10)).pack(side=tk.LEFT)

    def update_error(self, message):
        """Update the error message display."""
        self.error_var.set(message)
        # Clear error message after 5 seconds
        self.root.after(5000, lambda: self.error_var.set(""))

    def start_alert_listener(self):
        """Start listening to alerts for the selected session."""
        if self.alert_listener:
            self.alert_listener.stop()
        self.alert_listener = AlertListener(
            server=self.plex,
            callback=self.alert_callback,
            callbackError=self.error_callback
        )
        self.alert_listener.start()

    def stop_alert_listener(self):
        """Stop the alert listener."""
        if self.alert_listener:
            self.alert_listener.stop()


    def run(self):
        """Run the GUI for session selection and monitoring."""
        self.root = tk.Tk()
        self.root.title("Plex Playback Monitor")
        self.root.geometry("600x700")  # Made wider and taller
        self.root.configure(bg='#f0f0f0')

        # Create and configure variables
        self.title_var = StringVar(self.root)
        self.subtitle_var = StringVar(self.root)
        self.status_var = StringVar(self.root)
        self.time_var = StringVar(self.root)
        self.remaining_var = StringVar(self.root)
        self.error_var = StringVar(self.root)
        self.progress_var = tk.DoubleVar(self.root)
        self.timestamp_status_var = StringVar(self.root)

        # Create main container with padding
        container = ttk.Frame(self.root, padding="20")
        container.pack(fill=tk.BOTH, expand=True)

        # Create sections with visual separation
        self.create_session_section(container)
        ttk.Separator(container, orient='horizontal').pack(fill=tk.X, pady=15)

        self.create_media_info_section(container)
        ttk.Separator(container, orient='horizontal').pack(fill=tk.X, pady=15)

        self.create_playback_section(container)
        ttk.Separator(container, orient='horizontal').pack(fill=tk.X, pady=15)

        self.create_timestamp_section(container)

        # Error message at the bottom
        self.error_frame = ttk.Frame(container)
        self.error_frame.pack(fill=tk.X, pady=(15, 0))
        self.error_label = ttk.Label(
            self.error_frame,
            textvariable=self.error_var,
            foreground='red',
            wraplength=550  # Allow wrapping for long error messages
        )
        self.error_label.pack(fill=tk.X)

        def select_session(session_key):
            """Handle session selection."""
            self.selected_session_key = session_key
            session_data = self.sessions[session_key]
            self.session_var.set(session_data['title'])

            # Initialize playback state
            self.playback_state = session_data['state']
            self.last_view_offset = session_data['viewOffset']
            self.current_duration = session_data['duration']
            self.last_update_time = time.time()

            # Get current playing sessions
            try:
                sessions = self.plex.sessions()
                for session in sessions:
                    if str(session.sessionKey) == session_key:
                        # Found the correct session
                        self.current_media_type = session.type

                        # Update media info and UI
                        self.update_media_info(session)

                        # Reset timestamp markers
                        self.start_timestamp = None
                        self.update_timestamp_buttons()

                        # Start monitoring and fetch timestamps
                        self.start_alert_listener()
                        self.fetch_existing_timestamps(session_data)
                        break

            except Exception as e:
                self.update_error(f"Error fetching media info: {str(e)}")
                print(f"Debug - Error details: {e}")

        def update_ui():
            """Update the UI periodically."""
            self.fetch_active_sessions()

            # Update the dropdown menu
            menu = self.session_menu["menu"]
            menu.delete(0, "end")
            for session_key, session_data in self.sessions.items():
                menu.add_command(
                    label=f"{session_data['title']} ({session_data['player']})",
                    command=lambda key=session_key: select_session(key)
                )

            self.update_progress()
            self.root.after(1000, update_ui)

        # Start updating UI
        update_ui()
        self.root.mainloop()
        self.stop_alert_listener()

if __name__ == "__main__":
    viewer = PlexViewer()
    viewer.run()
import tkinter as tk
from tkinter import ttk, StringVar, messagebox
from datetime import timedelta
from plexapi.server import PlexServer
from plexapi.alert import AlertListener
from dotenv import load_dotenv
import os
import time
import requests
from plexapi.client import PlexClient

# Load environment variables
load_dotenv()

# Plex server details
PLEX_SERVER_URL = os.getenv("PLEX_SERVER_URL")
PLEX_TOKEN = os.getenv("PLEX_TOKEN")
BACKEND_URL = "http://127.0.0.1:8000"  # Your FastAPI backend
CLIENT_URL = os.getenv("PLEX_CLIENT_URL")
CLIENT_ID = os.getenv("PLEX_CLIENT_ID")


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
        self.recently_skipped = set()
        self.buffer_seconds = None  # Will be initialized in run()

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

    def create_edit_dialog(self, timestamp_data):
        """Create a dialog for editing timestamp data."""
        dialog = tk.Toplevel(self.root)
        dialog.title("Edit Timestamp")
        dialog.geometry("400x250")
        dialog.transient(self.root)
        dialog.grab_set()

        # Center the dialog
        dialog.geometry("+%d+%d" % (
            self.root.winfo_x() + self.root.winfo_width() / 2 - 200,
            self.root.winfo_y() + self.root.winfo_height() / 2 - 125))

        frame = ttk.Frame(dialog, padding="20")
        frame.pack(fill=tk.BOTH, expand=True)

        # Convert seconds to HH:MM:SS format
        start_time_str = format_time(int(timestamp_data['start_time'] * 1000))
        end_time_str = format_time(int(timestamp_data['end_time'] * 1000))

        # Start time
        ttk.Label(frame, text="Start Time (HH:MM:SS):").pack(pady=(0, 5))
        start_var = tk.StringVar(value=start_time_str)
        start_entry = ttk.Entry(frame, textvariable=start_var)
        start_entry.pack(pady=(0, 10))

        # End time
        ttk.Label(frame, text="End Time (HH:MM:SS):").pack(pady=(0, 5))
        end_var = tk.StringVar(value=end_time_str)
        end_entry = ttk.Entry(frame, textvariable=end_var)
        end_entry.pack(pady=(0, 10))

        # Label
        ttk.Label(frame, text="Label (optional):").pack(pady=(0, 5))
        label_var = tk.StringVar(value=timestamp_data.get('label', ''))
        label_entry = ttk.Entry(frame, textvariable=label_var)
        label_entry.pack(pady=(0, 20))



        def time_to_seconds(time_str):
            """Convert HH:MM:SS to seconds."""
            try:
                h, m, s = map(int, time_str.split(':'))
                return h * 3600 + m * 60 + s
            except ValueError:
                raise ValueError("Invalid time format. Please use HH:MM:SS")

        def submit():
            try:
                # Convert HH:MM:SS to seconds
                start_seconds = time_to_seconds(start_var.get())
                end_seconds = time_to_seconds(end_var.get())

                if end_seconds <= start_seconds:
                    messagebox.showerror("Error", "End time must be after start time")
                    return

                dialog.result = {
                    'start_time': float(start_seconds),
                    'end_time': float(end_seconds),
                    'label': label_var.get() if label_var.get().strip() else None
                }
                dialog.destroy()
            except ValueError as e:
                messagebox.showerror("Error", str(e))

        def cancel():
            dialog.result = None
            dialog.destroy()

        # Button frame
        button_frame = ttk.Frame(frame)
        button_frame.pack(fill=tk.X, pady=(0, 10))

        submit_btn = ttk.Button(button_frame, text="Save", command=submit)
        submit_btn.pack(side=tk.RIGHT, padx=5)

        cancel_btn = ttk.Button(button_frame, text="Cancel", command=cancel)
        cancel_btn.pack(side=tk.RIGHT, padx=5)

        dialog.wait_window()
        return getattr(dialog, 'result', None)

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

    def create_buffer_section(self, parent):
        """Create the buffer input section."""
        buffer_frame = ttk.Frame(parent)
        buffer_frame.pack(fill=tk.X, pady=(0, 10))

        ttk.Label(buffer_frame, text="Skip Buffer (seconds):").pack(side=tk.LEFT, padx=(0, 5))
        buffer_entry = ttk.Entry(buffer_frame, textvariable=self.buffer_seconds, width=5)
        buffer_entry.pack(side=tk.LEFT)

        # Add validation to ensure only numbers are entered
        def validate_buffer(value):
            if value == "":
                return True
            try:
                float(value)
                return True
            except ValueError:
                return False

        vcmd = (buffer_frame.register(validate_buffer), '%P')
        buffer_entry.configure(validate='key', validatecommand=vcmd)

    def force_refresh_timestamps(self):
        """Force a refresh of the timestamps display."""
        if self.selected_session_key and self.sessions:
            print("Forcing timestamp refresh")  # Debug print
            session_data = self.sessions[self.selected_session_key]
            response = self.fetch_existing_timestamps(session_data)
            if response and 'timestamps' in response:
                self.display_timestamps(response['timestamps'])
                # Force the GUI to update
                self.scrollable_frame.update_idletasks()
                return True
        return False

    def edit_timestamp(self, index, timestamp_data):
        """Edit an existing timestamp."""
        edited_data = self.create_edit_dialog(timestamp_data)
        if edited_data is None:
            return

        try:
            if self.current_media_type == 'movie':
                endpoint = f"{BACKEND_URL}/movies/update-timestamp/"
                params = {"title": self.current_media_info['title']}

                update_data = {
                    "index": index,
                    "start_time": float(edited_data['start_time']),
                    "end_time": float(edited_data['end_time']),
                    "label": edited_data['label']
                }
                response = requests.post(endpoint, params=params, json=update_data)
            else:  # TV show
                endpoint = f"{BACKEND_URL}/tv-shows/update-timestamp/"

                # Include all required parameters
                params = {
                    "show_name": self.current_media_info['show_name'],
                    "season": str(self.current_media_info['season']),
                    "episode_number": str(self.current_media_info['episode']),
                    "index": index,
                    "start_time": float(edited_data['start_time']),
                    "end_time": float(edited_data['end_time']),
                    "label": edited_data['label'] if edited_data.get('label') else None
                }

                print(f"Sending TV show update request with params: {params}")
                response = requests.post(endpoint, params=params)

            response.raise_for_status()
            response_data = response.json()

            if response_data.get('timestamps'):
                self.display_timestamps(response_data['timestamps'])

                # Restart skip monitoring with updated timestamps
                if self.is_active_client():
                    session_data = self.sessions[self.selected_session_key]
                    self.monitor_and_skip_timestamps(session_data, response_data['timestamps'])

                messagebox.showinfo("Success", "Timestamp updated successfully!")
            else:
                self.fetch_existing_timestamps(self.sessions[self.selected_session_key])

        except requests.exceptions.RequestException as e:
            error_msg = str(e)
            if hasattr(e, 'response') and e.response is not None:
                try:
                    error_details = e.response.json()
                    error_msg = error_details.get('detail', str(e))
                except:
                    pass
            messagebox.showerror("Error", f"Failed to update timestamp: {error_msg}")
            print(f"Debug - Update error details: {e}")

    # Update the delete_timestamp method's movie section
    def delete_timestamp(self, index):
        """Delete an existing timestamp."""
        if not messagebox.askyesno("Confirm Delete", "Are you sure you want to delete this timestamp?"):
            return

        try:
            if self.current_media_type == 'episode':
                endpoint = f"{BACKEND_URL}/tv-shows/delete-timestamp/"
                data = {
                    "show_name": self.current_media_info['show_name'],
                    "season": str(self.current_media_info['season']),
                    "episode_number": str(self.current_media_info['episode']),
                    "title": self.current_media_info['title'],
                    "index": index
                }
            else:  # movie
                endpoint = f"{BACKEND_URL}/movies/delete-timestamp/"
                data = {
                    "title": self.current_media_info['title'],
                    "index": index
                }

            response = requests.post(endpoint, json=data)
            response.raise_for_status()

            messagebox.showinfo("Success", "Timestamp deleted successfully!")
            self.fetch_existing_timestamps(self.sessions[self.selected_session_key])

        except requests.exceptions.RequestException as e:
            messagebox.showerror("Error", f"Failed to delete timestamp: {str(e)}")



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

    def is_active_client(self):
        """Check if the current session belongs to the target client."""
        if not self.selected_session_key or not self.sessions:
            return False

        session_data = self.sessions.get(self.selected_session_key)
        if not session_data:
            return False

        # You can modify these values based on your setup or move to env variables
        target_client_id = CLIENT_ID
        return session_data['machineIdentifier'] == target_client_id

    def verify_client_connection(self):
        """Debug method to verify client connection."""
        try:
            client = PlexClient(
                identifier=CLIENT_ID,
                baseurl=CLIENT_URL,
                token=PLEX_TOKEN
            )

            print(f"Client connection test:")
            print(f"- Client title: {client.title}")

            # Check current sessions
            current_sessions = self.plex.sessions()
            matching_session = None

            for session in current_sessions:
                if str(session.sessionKey) == self.selected_session_key:
                    matching_session = session
                    break

            if matching_session:
                print(f"- Session found")
                print(f"- Playback state: {matching_session.players[0].state}")
                print(f"- Current position: {matching_session.viewOffset / 1000:.2f}s")
                return True
            else:
                print("- No matching session found")
                return False

        except Exception as e:
            print(f"Client connection test failed: {e}")
            return False

    def monitor_and_skip_timestamps(self, session_data, timestamps):
        """Monitor playback and automatically skip marked timestamp ranges."""
        try:
            client = PlexClient(
                identifier=CLIENT_ID,
                baseurl=CLIENT_URL,
                token=PLEX_TOKEN
            )
            print(f"Connected to client: {client.title}")

            # Keep track of recently skipped timestamps to prevent double-skipping
            self.recently_skipped = set()

            def check_and_skip():
                """Check current playback position and skip if in a timestamp range."""
                try:
                    # Get current buffer value
                    try:
                        buffer_value = float(self.buffer_seconds.get())
                    except ValueError:
                        buffer_value = 0  # Default to no buffer if invalid value

                    # Always use the most recent view offset when checking position
                    if self.playback_state == 'playing':
                        elapsed_time = time.time() - self.last_update_time
                        current_position_ms = self.last_view_offset + int(elapsed_time * 1000)
                    else:
                        current_position_ms = self.last_view_offset

                    current_position_seconds = current_position_ms / 1000

                    # Check each timestamp range
                    for ts in timestamps:
                        # Apply buffer to start and end times
                        start_time = ts['start_time'] - buffer_value
                        end_time = ts['end_time'] + buffer_value

                        # Create a unique identifier for this skip point
                        skip_id = f"{start_time}-{end_time}"

                        # If we're in or just about to enter a timestamp range
                        if (start_time <= current_position_seconds <= end_time and
                                skip_id not in self.recently_skipped):

                            print(f"Attempting to skip from {current_position_seconds:.2f}s to {end_time:.2f}s")

                            try:
                                # Send seek command to client
                                seek_position = int(end_time * 1000)
                                client.seekTo(seek_position)
                                print(f"Seek command sent to position {end_time}s")

                                # Add to recently skipped and schedule removal
                                self.recently_skipped.add(skip_id)
                                self.root.after(2000, lambda: self.recently_skipped.discard(skip_id))

                                # Update UI
                                label = ts.get('label', 'unnamed section')
                                self.update_status(f"Auto-skipped {label}")

                                # Update our internal position tracking
                                self.last_view_offset = seek_position
                                self.last_update_time = time.time()

                            except Exception as seek_error:
                                print(f"Error during seek: {seek_error}")

                    # Schedule next check
                    self.root.after(250, check_and_skip)

                except Exception as e:
                    print(f"Check and skip error: {str(e)}")
                    self.root.after(1000, check_and_skip)

            # Start the monitoring
            print("Starting skip monitoring")
            check_and_skip()

        except Exception as e:
            error_msg = f"Failed to setup auto-skip monitoring: {str(e)}"
            print(error_msg)
            self.update_error(error_msg)

    def alert_callback(self, data):
        """Handle alerts for the selected session."""
        for notification in data.get('PlaySessionStateNotification', []):
            # Check if this is our target client
            if notification.get('clientIdentifier') == CLIENT_ID:  # Your client ID
                state = notification.get('state')
                view_offset = notification.get('viewOffset', 0)
                metadata_key = notification.get('key')

                # Always update the view offset and time when we get a notification
                self.last_view_offset = view_offset
                self.last_update_time = time.time()
                self.playback_state = state

                print(f"Alert: State={state}, ViewOffset={view_offset}ms")

                # Update metadata if needed
                try:
                    item = self.plex.fetchItem(metadata_key)
                    self.current_duration = getattr(item, 'duration', 0)
                    self.update_media_info(item)
                except Exception as e:
                    self.update_error(f"Error fetching metadata: {e}")

    def update_progress(self):
        """Update the progress bar and time labels."""
        try:
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

        except Exception as e:
            print(f"Error updating progress: {e}")

        # Schedule next update
        self.root.after(1000, self.update_progress)

    def update_status(self, message):
        """Update status message temporarily."""
        original_status = self.status_var.get()
        self.status_var.set(message)
        # Reset back to original status after 3 seconds
        self.root.after(3000, lambda: self.status_var.set(original_status))

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

            # Update display
            self.display_timestamps(timestamps_data.get('timestamps', []))

            # Return the data for use in auto-skip
            return timestamps_data

        except requests.exceptions.RequestException as e:
            if not isinstance(e, requests.exceptions.HTTPError) or e.response.status_code != 404:
                self.update_error(f"Failed to fetch timestamps: {str(e)}")
            return None

    def display_timestamps(self, timestamps):
        """Display existing timestamps in the scrollable frame with edit/delete controls."""
        print("Displaying timestamps:", timestamps)  # Debug print

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

            # Create button frame for edit/delete buttons
            button_frame = ttk.Frame(frame)
            button_frame.pack(side=tk.RIGHT)

            # Add edit and delete buttons
            ttk.Button(
                button_frame,
                text="Edit",
                command=lambda idx=i, data=ts: self.edit_timestamp(idx, data),
                style='Small.TButton'
            ).pack(side=tk.RIGHT, padx=2)

            ttk.Button(
                button_frame,
                text="Delete",
                command=lambda idx=i: self.delete_timestamp(idx),
                style='Small.TButton'
            ).pack(side=tk.RIGHT, padx=2)

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
        self.root.geometry("600x700")
        self.root.configure(bg='#f0f0f0')

        # Configure style after creating root window
        style = ttk.Style()
        style.configure('Small.TButton', padding=3)

        # Create and configure variables
        self.buffer_seconds = StringVar(self.root, value="2")  # Initialize buffer_seconds here
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

        # Add buffer section here
        self.create_buffer_section(container)
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
            wraplength=550
        )
        self.error_label.pack(fill=tk.X)

        # Start updating UI
        self.update_ui()
        self.root.mainloop()
        self.stop_alert_listener()
    def update_ui(self):
        """Update the UI periodically."""
        self.fetch_active_sessions()

        # Update the dropdown menu
        menu = self.session_menu["menu"]
        menu.delete(0, "end")
        for session_key, session_data in self.sessions.items():
            menu.add_command(
                label=f"{session_data['title']} ({session_data['player']})",
                command=lambda key=session_key: self.select_session(key)
            )

        self.update_progress()
        self.root.after(1000, self.update_ui)

    def select_session(self, session_key):
        """Handle session selection."""
        self.selected_session_key = session_key
        session_data = self.sessions[session_key]

        print("Verifying client connection...")
        is_connected = self.verify_client_connection()
        print(f"Client connected: {is_connected}")

        self.session_var.set(session_data['title'])

        # Initialize playback state
        self.playback_state = session_data['state']
        self.last_view_offset = session_data['viewOffset']
        self.current_duration = session_data['duration']
        self.last_update_time = time.time()

        try:
            sessions = self.plex.sessions()
            for session in sessions:
                if str(session.sessionKey) == session_key:
                    self.current_media_type = session.type
                    self.update_media_info(session)
                    self.start_timestamp = None
                    self.update_timestamp_buttons()
                    self.start_alert_listener()

                    # Fetch timestamps and setup auto-skip if available
                    try:
                        response = self.fetch_existing_timestamps(session_data)
                        if response and 'timestamps' in response:
                            self.monitor_and_skip_timestamps(session_data, response['timestamps'])
                    except Exception as e:
                        self.update_error(f"Error setting up auto-skip: {str(e)}")
                    break

        except Exception as e:
            self.update_error(f"Error fetching media info: {str(e)}")
            print(f"Debug - Error details: {e}")

if __name__ == "__main__":
    viewer = PlexViewer()
    viewer.run()
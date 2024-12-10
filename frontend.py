from plexapi.server import PlexServer
import tkinter as tk
from tkinter import StringVar, ttk
import time
import requests
from dotenv import load_dotenv
import os

# Load environment variables from the .env file
load_dotenv()

# Plex server details
PLEX_SERVER_URL = os.getenv("PLEX_SERVER_URL")
PLEX_TOKEN = os.getenv("PLEX_TOKEN")


class TimestampRange:
    def __init__(self):
        self.start_time = None
        self.end_time = None
        self.label = ""

    def is_complete(self):
        return self.start_time is not None and self.end_time is not None

    def clear(self):
        self.start_time = None
        self.end_time = None
        self.label = ""


class PlaybackTimer:
    def __init__(self):
        self.is_playing = False
        self.last_plex_time = 0
        self.last_plex_update = 0

    def start(self):
        self.is_playing = True

    def pause(self):
        self.is_playing = False

    def resume(self):
        self.is_playing = True

    def get_current_time(self):
        if not self.is_playing:
            return self.last_plex_time

        time_since_update = time.time() - self.last_plex_update
        return self.last_plex_time + time_since_update

    def sync_with_plex(self, plex_time):
        self.last_plex_time = plex_time
        self.last_plex_update = time.time()


class PlexViewer:
    def __init__(self):
        self.plex = PlexServer(PLEX_SERVER_URL, PLEX_TOKEN)
        self.selected_session = None
        self.sessions = {}
        self.timers = {}
        self.last_api_check = 0
        self.api_check_interval = 10
        self.current_timestamp_range = TimestampRange()

    def send_timestamps_to_backend(self, session, timestamp_range):
        """Send the timestamp range to the backend."""
        try:
            if not timestamp_range.is_complete():
                print("Timestamp range is not complete")
                return

            # Create timestamp data with start and end times
            timestamp_data = {
                "start_time": timestamp_range.start_time,
                "end_time": timestamp_range.end_time,
                "label": timestamp_range.label if timestamp_range.label else None
            }

            # Determine if it's a TV show or movie
            if session.get("show_name"):
                endpoint = "http://127.0.0.1:8000/tv-shows/add-timestamps/"
                payload = {
                    "show_name": session["show_name"],
                    "season": session["season"],
                    "episode_number": session["episode_number"],
                    "title": session["title"],
                    "timestamps": [timestamp_data]
                }
            else:
                endpoint = "http://127.0.0.1:8000/movies/add-timestamps/"
                payload = {
                    "title": session["title"],
                    "timestamps": [timestamp_data]
                }

            response = requests.post(
                endpoint,
                json=payload,
                timeout=5
            )

            if response.status_code == 200:
                print(f"Timestamp range sent successfully: {response.json()}")
                return True
            else:
                print(f"Failed to send timestamp range: {response.status_code} - {response.text}")
                return False

        except Exception as e:
            print(f"Error sending timestamp range to backend: {e}")
            return False

    def fetch_timestamps_from_backend(self, title, show_name=None, season=None, episode_number=None):
        """Fetch timestamp ranges for the given media from the backend."""
        try:
            if show_name:
                endpoint = "http://127.0.0.1:8000/tv-shows/get-timestamps/"
                payload = {
                    "title": title,
                    "show_name": show_name,
                    "season": season,
                    "episode_number": episode_number
                }
            else:
                endpoint = "http://127.0.0.1:8000/movies/get-timestamps/"
                payload = {"title": title}

            response = requests.post(
                endpoint,
                json=payload,
                timeout=5
            )

            if response.status_code == 200:
                data = response.json()
                print(f"Retrieved timestamps for '{title}': {data['timestamps']}")
                return data['timestamps']
            elif response.status_code == 404:
                print(f"No timestamps found for '{title}'")
                return []
            else:
                print(f"Error fetching timestamps: {response.status_code} - {response.text}")
                return []
        except Exception as e:
            print(f"Exception during backend call: {e}")
            return []

    def query_sessions(self):
        """Query Plex for active sessions and update timers."""
        try:
            current_sessions = {}
            for session in self.plex.sessions():
                session_key = session.sessionKey

                if session.type == "episode":
                    show_name = session.grandparentTitle
                    season = session.parentTitle
                    episode_number = f"Episode {session.index}"
                    title = f"{show_name} - {season} {episode_number}"
                else:
                    title = session.title

                timestamps = self.fetch_timestamps_from_backend(title)

                current_sessions[session_key] = {
                    "title": title,
                    "player": session.player.title,
                    "duration": session.duration / 1000,
                    "viewOffset": session.viewOffset / 1000,
                    "state": session.player.state,
                    "timestamps": timestamps,
                }

                if session_key not in self.timers:
                    self.timers[session_key] = PlaybackTimer()

                timer = self.timers[session_key]
                if session.player.state == 'playing' and not timer.is_playing:
                    timer.resume()
                elif session.player.state == 'paused' and timer.is_playing:
                    timer.pause()

                timer.sync_with_plex(session.viewOffset / 1000)

            self.sessions = current_sessions
            ended_sessions = [k for k in self.timers.keys() if k not in current_sessions]
            for session_key in ended_sessions:
                del self.timers[session_key]

        except Exception as e:
            print(f"Error querying sessions: {e}")

    def format_time(self, seconds):
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        seconds = int(seconds % 60)
        return f"{hours:02}:{minutes:02}:{seconds:02}"

    def run(self):
        def update_ui():
            current_time = time.time()

            if current_time - self.last_api_check >= self.api_check_interval:
                self.query_sessions()
                self.last_api_check = current_time

                session_menu["menu"].delete(0, "end")
                for session_key, session_data in self.sessions.items():
                    session_menu["menu"].add_command(
                        label=f"{session_data['title']} ({session_data['player']})",
                        command=lambda s=session_key: select_session(s)
                    )

            if self.selected_session and self.selected_session in self.sessions:
                session = self.sessions[self.selected_session]
                timer = self.timers[self.selected_session]

                current_time = timer.get_current_time()
                progress = (current_time / session["duration"]) * 100

                title_label.config(
                    text=f"Now Playing: {session['title']} ({session['player']})"
                )
                progress_label.config(text=f"Progress: {progress:.2f}%")
                playback_label.config(
                    text=f"Time: {self.format_time(current_time)} / {self.format_time(session['duration'])}"
                )
                state_label.config(text=f"State: {session['state'].capitalize()}")

                # Update timestamp range status
                range_status = "Timestamp Range Status:\n"
                if self.current_timestamp_range.start_time is not None:
                    range_status += f"Start: {self.format_time(self.current_timestamp_range.start_time)}\n"
                else:
                    range_status += "Start: Not set\n"

                if self.current_timestamp_range.end_time is not None:
                    range_status += f"End: {self.format_time(self.current_timestamp_range.end_time)}"
                else:
                    range_status += "End: Not set"

                range_status_label.config(text=range_status)

                # Display existing timestamps
                if session["timestamps"]:
                    timestamp_text = "Saved Ranges:\n"
                    for ts in session["timestamps"]:
                        start = self.format_time(ts['start_time'])
                        end = self.format_time(ts['end_time'])
                        label = ts.get('label', '')
                        timestamp_text += f"{start} - {end}"
                        if label:
                            timestamp_text += f" ({label})"
                        timestamp_text += "\n"
                    timestamp_label.config(text=timestamp_text)
                else:
                    timestamp_label.config(text="No saved ranges")

            else:
                title_label.config(text="No active playback")
                progress_label.config(text="")
                playback_label.config(text="Waiting for playback...")
                state_label.config(text="")
                timestamp_label.config(text="")
                range_status_label.config(text="")

            root.after(100, update_ui)

        def select_session(session_key):
            self.selected_session = session_key
            session_var.set(f"{self.sessions[session_key]['title']} ({self.sessions[session_key]['player']})")
            self.current_timestamp_range.clear()

        def set_start_time():
            if self.selected_session and self.selected_session in self.sessions:
                timer = self.timers[self.selected_session]
                self.current_timestamp_range.start_time = timer.get_current_time()

        def set_end_time():
            if self.selected_session and self.selected_session in self.sessions:
                timer = self.timers[self.selected_session]
                self.current_timestamp_range.end_time = timer.get_current_time()

        def save_timestamp_range():
            if self.selected_session and self.selected_session in self.sessions:
                if not self.current_timestamp_range.is_complete():
                    print("Please set both start and end times")
                    return

                # Get the label from the entry field
                self.current_timestamp_range.label = label_entry.get()

                # Send to backend
                session = self.sessions[self.selected_session]
                if self.send_timestamps_to_backend(session, self.current_timestamp_range):
                    self.current_timestamp_range.clear()
                    label_entry.delete(0, tk.END)
            else:
                print("No session selected or session not available")

        # Create main window
        root = tk.Tk()
        root.title("Plex Playback Viewer")
        root.geometry("800x600")

        # Create main frame
        main_frame = ttk.Frame(root, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # Dropdown menu
        session_var = StringVar(root)
        session_var.set("Select your session")
        session_menu = tk.OptionMenu(main_frame, session_var, [])
        session_menu.pack(fill=tk.X, pady=5)

        # Labels
        title_label = ttk.Label(main_frame, text="Waiting for playback...", font=("Arial", 16))
        title_label.pack(pady=5)

        progress_label = ttk.Label(main_frame, text="")
        progress_label.pack(pady=5)

        playback_label = ttk.Label(main_frame, text="Time: 00:00:00 / 00:00:00")
        playback_label.pack(pady=5)

        state_label = ttk.Label(main_frame, text="")
        state_label.pack(pady=5)

        # Timestamp range controls frame
        range_frame = ttk.LabelFrame(main_frame, text="Timestamp Range Controls", padding="5")
        range_frame.pack(fill=tk.X, pady=10)

        # Range control buttons
        button_frame = ttk.Frame(range_frame)
        button_frame.pack(fill=tk.X, pady=5)

        start_button = ttk.Button(button_frame, text="Set Start Time", command=set_start_time)
        start_button.pack(side=tk.LEFT, padx=5)

        end_button = ttk.Button(button_frame, text="Set End Time", command=set_end_time)
        end_button.pack(side=tk.LEFT, padx=5)

        # Label entry
        label_frame = ttk.Frame(range_frame)
        label_frame.pack(fill=tk.X, pady=5)

        ttk.Label(label_frame, text="Label:").pack(side=tk.LEFT, padx=5)
        label_entry = ttk.Entry(label_frame)
        label_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)

        save_button = ttk.Button(range_frame, text="Save Timestamp Range", command=save_timestamp_range)
        save_button.pack(pady=5)

        # Range status display
        range_status_label = ttk.Label(main_frame, text="")
        range_status_label.pack(pady=5)

        # Existing timestamps display
        timestamp_label = ttk.Label(main_frame, text="")
        timestamp_label.pack(pady=5)

        # Start update loop
        update_ui()
        root.mainloop()


if __name__ == "__main__":
    viewer = PlexViewer()
    viewer.run()
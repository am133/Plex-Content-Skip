from plexapi.server import PlexServer
import tkinter as tk
from tkinter import StringVar
import time
import requests  # Ensure the requests library is imported
from dotenv import load_dotenv
import os

# Load environment variables from the .env file
load_dotenv()

# Plex server details
PLEX_SERVER_URL = os.getenv("PLEX_SERVER_URL")
PLEX_TOKEN = os.getenv("PLEX_TOKEN")

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

        # Calculate time since last Plex update
        time_since_update = time.time() - self.last_plex_update
        return self.last_plex_time + time_since_update

    def sync_with_plex(self, plex_time):
        """Update timer with latest Plex time"""
        self.last_plex_time = plex_time
        self.last_plex_update = time.time()

class PlexViewer:
    def __init__(self):
        self.plex = PlexServer(PLEX_SERVER_URL, PLEX_TOKEN)
        self.selected_session = None
        self.sessions = {}
        self.timers = {}  # Dictionary to store timers for each session
        self.last_api_check = 0
        self.api_check_interval = 10  # Check Plex API every 10 seconds

    def send_timestamps_to_backend(self, session):
        """Send the current playback details to the backend."""
        try:
            # Create timestamp data with just the viewOffset
            timestamp_data = {
                "viewOffset": float(session["viewOffset"])  # Convert to float
            }

            # Determine if it's a TV show or movie based on show_name presence
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

            # Send the POST request
            response = requests.post(
                endpoint,
                json=payload,
                timeout=5
            )

            if response.status_code == 200:
                print(f"Timestamps sent successfully: {response.json()}")
            else:
                print(f"Failed to send timestamps: {response.status_code} - {response.text}")

        except Exception as e:
            print(f"Error sending timestamps to backend: {e}")

    def fetch_timestamps_from_backend(self, title, show_name=None, season=None, episode_number=None):
        """Fetch timestamps for the given media from the backend."""
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

                # Determine whether the session is a TV show or a movie
                if session.type == "episode":
                    show_name = session.grandparentTitle
                    season = session.parentTitle
                    episode_number = f"Episode {session.index}"
                    title = f"{show_name} - {season} {episode_number}"
                elif session.type == "movie":
                    title = session.title
                else:
                    title = session.title

                # Fetch timestamps from the backend
                timestamps = self.fetch_timestamps_from_backend(title)

                # Update session details
                current_sessions[session_key] = {
                    "title": title,
                    "player": session.player.title,
                    "duration": session.duration / 1000,  # Convert to seconds
                    "viewOffset": session.viewOffset / 1000,  # Convert to seconds
                    "state": session.player.state,
                    "timestamps": timestamps,  # Include timestamps
                }

                # Create or update timer for this session
                if session_key not in self.timers:
                    self.timers[session_key] = PlaybackTimer()

                # Update timer state
                timer = self.timers[session_key]
                if session.player.state == 'playing' and not timer.is_playing:
                    timer.resume()
                elif session.player.state == 'paused' and timer.is_playing:
                    timer.pause()

                # Always sync with Plex time
                timer.sync_with_plex(session.viewOffset / 1000)

            # Clean up ended sessions
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

            # Check if it's time to query Plex API
            if current_time - self.last_api_check >= self.api_check_interval:
                self.query_sessions()
                self.last_api_check = current_time

                # Update dropdown options
                session_menu["menu"].delete(0, "end")
                for session_key, session_data in self.sessions.items():
                    session_menu["menu"].add_command(
                        label=f"{session_data['title']} ({session_data['player']})",
                        command=lambda s=session_key: select_session(s)
                    )

            # Update display for selected session
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

                # Display timestamps
                if session["timestamps"]:
                    formatted_timestamps = [
                        f"{self.format_time(ts['viewOffset'])}"
                        for ts in session["timestamps"]
                    ]
                    timestamp_label.config(text=f"Timestamps: {', '.join(formatted_timestamps)}")
                else:
                    timestamp_label.config(text="No timestamps available")
            else:
                title_label.config(text="No active playback")
                progress_label.config(text="")
                playback_label.config(text="Waiting for playback...")
                state_label.config(text="")
                timestamp_label.config(text="")

            # Update UI frequently for smooth timer display
            root.after(100, update_ui)

        def select_session(session_key):
            self.selected_session = session_key
            session_var.set(f"{self.sessions[session_key]['title']} ({self.sessions[session_key]['player']})")

        def send_timestamp():
            if self.selected_session and self.selected_session in self.sessions:
                session = self.sessions[self.selected_session]
                self.send_timestamps_to_backend(session)
            else:
                print("No session selected or session not available")

        # Create main window
        root = tk.Tk()
        root.title("Plex Playback Viewer")
        root.geometry("700x400")  # Adjust height to accommodate the button

        # Dropdown menu
        session_var = StringVar(root)
        session_var.set("Select your session")
        session_menu = tk.OptionMenu(root, session_var, [])
        session_menu.config(width=50, font=("Arial", 12))
        session_menu.pack(pady=20)

        # Labels
        title_label = tk.Label(root, text="Waiting for playback...", font=("Arial", 16))
        title_label.pack(pady=10)

        progress_label = tk.Label(root, text="", font=("Arial", 14))
        progress_label.pack(pady=5)

        playback_label = tk.Label(root, text="Time: 00:00:00 / 00:00:00", font=("Arial", 14))
        playback_label.pack(pady=10)

        state_label = tk.Label(root, text="", font=("Arial", 14))
        state_label.pack(pady=10)

        timestamp_label = tk.Label(root, text="", font=("Arial", 14))
        timestamp_label.pack(pady=10)

        # Button to send timestamps
        send_timestamp_button = tk.Button(
            root,
            text="Send Timestamp to Backend",
            font=("Arial", 12),
            command=send_timestamp
        )
        send_timestamp_button.pack(pady=10)

        # Start update loop
        update_ui()
        root.mainloop()

if __name__ == "__main__":
    viewer = PlexViewer()
    viewer.run()
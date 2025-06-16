import tkinter
from tkinter import filedialog
import customtkinter
import httpx
import asyncio
import threading
import subprocess
import os
import json
import sys
import shutil
import re
from PIL import Image, ImageTk

# --- Configuration ---
API_BASE_URL = 'https://spotify-one-lime.vercel.app'  # Your Vercel API URL
SAVE_DIR = "spotify_downloads"
COOKIES_FILE_PATH = "./conf/cookies.txt"

class App(customtkinter.CTk):
    def __init__(self):
        super().__init__()

        # --- Window Setup ---
        self.title("Spotify Downloader")
        self.geometry("700x700")
        customtkinter.set_appearance_mode("dark")
        customtkinter.set_default_color_theme("green")

        try:
            if os.path.exists("icon.png"):
                self.icon_image = ImageTk.PhotoImage(Image.open("icon.png"))
                self.iconphoto(True, self.icon_image)
        except Exception as e:
            print(f"Error setting window icon: {e}")

        self.ffmpeg_path = self.get_ffmpeg_path()
        os.makedirs(SAVE_DIR, exist_ok=True)
        os.makedirs(os.path.dirname(COOKIES_FILE_PATH), exist_ok=True)

        # --- Queue and State Management ---
        self.download_queue = []
        self.active_process = None
        self.queue_lock = threading.Lock()
        self.is_processing_queue = False
        self.shutdown_event = threading.Event()
        self.song_list_visible = True
        
        self.protocol("WM_DELETE_WINDOW", self.on_closing)


        # --- Main Frame ---
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(4, weight=1)

        # --- Header ---
        header_frame = customtkinter.CTkFrame(self, corner_radius=0, fg_color="transparent")
        header_frame.grid(row=0, column=0, sticky="ew", padx=20, pady=20)
        header_frame.grid_columnconfigure(1, weight=1)
        
        try:
            if os.path.exists("icon.png"):
                im = Image.open("icon.png").resize((40, 40))
                self.logo_image = ImageTk.PhotoImage(im)
                logo_label = customtkinter.CTkLabel(header_frame, image=self.logo_image, text="")
                logo_label.grid(row=0, column=0, padx=(0, 15))
        except Exception as e:
            print(f"Could not load header logo: {e}")

        self.header_label = customtkinter.CTkLabel(header_frame, text="Spotify & YouTube Downloader", font=customtkinter.CTkFont(size=24, weight="bold"))
        self.header_label.grid(row=0, column=1, sticky="w")
        
        # --- URL Input Frame ---
        self.url_frame = customtkinter.CTkFrame(self)
        self.url_frame.grid(row=1, column=0, padx=20, pady=(0, 10), sticky="ew")
        self.url_frame.grid_columnconfigure(0, weight=1)

        self.url_entry = customtkinter.CTkEntry(self.url_frame, placeholder_text="Paste Spotify or YouTube link here...", height=40, font=customtkinter.CTkFont(size=14))
        self.url_entry.grid(row=0, column=0, padx=10, pady=10, sticky="ew")

        self.search_button = customtkinter.CTkButton(self.url_frame, text="Search", height=40, font=customtkinter.CTkFont(size=16, weight="bold"), command=self.start_search_thread)
        self.search_button.grid(row=0, column=1, padx=(0,5), pady=10)
        
        self.ffmpeg_button = customtkinter.CTkButton(self.url_frame, text="Set FFmpeg", height=40, command=self.prompt_for_ffmpeg_path, fg_color="gray50", hover_color="gray30")
        self.ffmpeg_button.grid(row=0, column=2, padx=(0, 10), pady=10)

        # --- Analysis & Progress Frame ---
        self.progress_frame = customtkinter.CTkFrame(self)
        self.progress_frame.grid(row=2, column=0, padx=20, pady=5, sticky="ew")
        self.progress_frame.grid_columnconfigure(0, weight=1)

        self.analysis_textbox = customtkinter.CTkTextbox(self.progress_frame, height=70, font=customtkinter.CTkFont(family="Arial", size=12), wrap="word", border_width=1)
        self.analysis_textbox.grid(row=0, column=0, columnspan=2, padx=10, pady=(10, 5), sticky="ew")
        self.update_analysis_text("Analysis results will appear here...")
        
        # New frame for progress bar and cancel button
        self.bar_cancel_frame = customtkinter.CTkFrame(self.progress_frame, fg_color="transparent")
        self.bar_cancel_frame.grid(row=1, column=0, columnspan=2, padx=10, pady=5, sticky="ew")
        self.bar_cancel_frame.grid_columnconfigure(0, weight=1)

        self.progress_bar = customtkinter.CTkProgressBar(self.bar_cancel_frame, progress_color="#1DB954")
        self.progress_bar.set(0)
        self.progress_bar.grid(row=0, column=0, sticky="ew")
        
        self.cancel_button = customtkinter.CTkButton(self.bar_cancel_frame, text="Cancel", width=80, command=self.cancel_all_downloads, fg_color="red", hover_color="#C0392B")
        self.cancel_button.grid(row=0, column=1, padx=(10,0))


        self.status_label = customtkinter.CTkLabel(self.progress_frame, text="", anchor="w")
        self.status_label.grid(row=2, column=0, columnspan=2, padx=10, pady=(0, 10), sticky="ew")
        
        if not self.ffmpeg_path: self.set_status("WARNING: FFmpeg not found.", "orange")
        else: self.set_status(f"FFmpeg found.", "green")

        # --- Library Toggle ---
        self.toggle_frame = customtkinter.CTkFrame(self, fg_color="transparent")
        self.toggle_frame.grid(row=3, column=0, padx=20, pady=(10,0), sticky="ew")
        self.toggle_button = customtkinter.CTkButton(self.toggle_frame, text="Hide Library", command=self.toggle_song_list)
        self.toggle_button.pack(side="left")

        # --- Downloaded Songs List ---
        self.song_list_frame = customtkinter.CTkScrollableFrame(self, label_text="Downloaded Songs", label_font=customtkinter.CTkFont(size=16, weight="bold"))
        self.song_list_frame.grid(row=4, column=0, padx=20, pady=5, sticky="nsew")

        self.load_downloaded_songs()

    def get_ffmpeg_path(self):
        ffmpeg_exe = "ffmpeg.exe" if sys.platform == "win32" else "ffmpeg"
        script_dir = os.path.dirname(sys.executable if getattr(sys, 'frozen', False) else os.path.abspath(__file__))
        local_ffmpeg_path = os.path.join(script_dir, ffmpeg_exe)
        return local_ffmpeg_path if os.path.exists(local_ffmpeg_path) else shutil.which("ffmpeg")

    def prompt_for_ffmpeg_path(self):
        filepath = filedialog.askopenfilename(title="Select FFmpeg Executable")
        if filepath and "ffmpeg" in os.path.basename(filepath).lower():
            self.ffmpeg_path = filepath
            self.set_status(f"FFmpeg path set: {self.ffmpeg_path}", "green")
        elif filepath:
            self.set_status("Warning: Selected file might not be FFmpeg.", "orange")
            
    def toggle_song_list(self):
        if self.song_list_visible:
            self.song_list_frame.grid_remove()
            self.toggle_button.configure(text="Show Library")
            self.song_list_visible = False
        else:
            self.song_list_frame.grid()
            self.toggle_button.configure(text="Hide Library")
            self.song_list_visible = True

    def start_search_thread(self):
        threading.Thread(target=lambda: asyncio.run(self.handle_search_press()), daemon=True).start()

    async def handle_search_press(self):
        url = self.url_entry.get()
        if not url: self.set_status("Please paste a link.", "orange"); return

        self.set_search_button_state(state="disabled", text="Searching...")
        self.set_status("Identifying link type...")
        
        try:
            if "spotify.com" in url:
                self.set_status("Spotify link detected. Contacting API...")
                async with httpx.AsyncClient() as client:
                    response = await client.get(f"{API_BASE_URL}/api/spotify?spotifyUrl={url}", timeout=45.0)
                    response.raise_for_status()
                    data = response.json()
                
                if isinstance(data, list): tracks = data
                elif isinstance(data, dict) and 'tracks' in data: tracks = data['tracks']
                else: raise ValueError("API response format not recognized.")

                if not tracks: raise ValueError("API did not return any tracks.")
                self.show_playlist_modal(tracks)
            elif "youtube.com" in url or "youtu.be" in url:
                self.set_status("YouTube link detected. Getting title...")
                title_command = ["yt-dlp", "--get-title", url]
                process = subprocess.run(title_command, capture_output=True, text=True, encoding='utf-8', errors='ignore')
                title = process.stdout.strip() or "YouTube Video"
                
                mock_track = {'videoId': url, 'name': title, 'artist': None}
                self.add_tracks_to_queue([mock_track], 'bestaudio/best', 1) # Default to 1 fragment for single YouTube links
            else:
                raise ValueError("Link is not a valid Spotify or YouTube URL.")
                
        except Exception as e:
            self.set_status(f"Error: {e}", "red")
        finally:
             self.set_search_button_state(state="normal", text="Search")

    def show_playlist_modal(self, tracks):
        playlist_window = customtkinter.CTkToplevel(self)
        playlist_window.title("Playlist Tracks")
        playlist_window.geometry("600x550")
        
        playlist_window.transient(self)
        playlist_window.grab_set()
        
        top_frame = customtkinter.CTkFrame(playlist_window)
        top_frame.pack(fill="x", padx=10, pady=10)
        top_frame.grid_columnconfigure(1, weight=1)
        top_frame.grid_columnconfigure(3, weight=1)

        customtkinter.CTkLabel(top_frame, text="Size Limit:").grid(row=0, column=0, padx=(0,5))
        format_options = ['< 15 MB (Default)', '< 50 MB', '< 75 MB', '< 100 MB', '< 150 MB']
        format_menu = customtkinter.CTkOptionMenu(top_frame, values=format_options)
        format_menu.grid(row=0, column=1, padx=(0,10), sticky="ew")

        customtkinter.CTkLabel(top_frame, text="Download Parts:").grid(row=0, column=2, padx=(10,5))
        fragments_menu = customtkinter.CTkOptionMenu(top_frame, values=["1", "2", "3", "5", "10"])
        fragments_menu.grid(row=0, column=3, sticky="ew")

        scrollable_frame = customtkinter.CTkScrollableFrame(playlist_window, label_text=f"{len(tracks)} Tracks Found")
        scrollable_frame.pack(expand=True, fill="both", padx=10, pady=(0,10))

        track_vars = []
        for track in tracks:
            var = tkinter.StringVar(value="off")
            checkbox = customtkinter.CTkCheckBox(scrollable_frame, text=f"{track.get('artist', 'N/A')} - {track.get('name', 'N/A')}", variable=var, onvalue=json.dumps(track), offvalue="off")
            checkbox.pack(anchor="w", padx=10, pady=5)
            track_vars.append(var)
        
        button_frame = customtkinter.CTkFrame(playlist_window)
        button_frame.pack(fill="x", padx=10, pady=10)
        button_frame.grid_columnconfigure((0, 1, 2), weight=1)

        def toggle_all(select=True):
            for i, var in enumerate(track_vars): var.set(json.dumps(tracks[i]) if select else "off")

        select_all_btn = customtkinter.CTkButton(button_frame, text="Select All", command=lambda: toggle_all(True))
        select_all_btn.grid(row=0, column=0, padx=5, sticky="ew")

        deselect_all_btn = customtkinter.CTkButton(button_frame, text="Deselect All", command=lambda: toggle_all(False))
        deselect_all_btn.grid(row=0, column=1, padx=5, sticky="ew")
        
        def on_add_to_queue_click():
            selected_tracks = [json.loads(var.get()) for var in track_vars if var.get() != "off"]
            size_limit_str = format_menu.get()
            size_mb = int(re.search(r'\d+', size_limit_str).group())
            format_string = f"bestaudio[filesize<{size_mb}M]/bestaudio"
            fragments = int(fragments_menu.get())

            if selected_tracks:
                self.add_tracks_to_queue(selected_tracks, format_string, fragments)
                playlist_window.destroy()

        add_to_queue_button = customtkinter.CTkButton(button_frame, text="Add to Queue", command=on_add_to_queue_click)
        add_to_queue_button.grid(row=0, column=2, padx=5, sticky="ew")

    def add_tracks_to_queue(self, tracks, format_string, fragments):
        with self.queue_lock:
            tracks_to_add = []
            for track in tracks:
                sanitized_name = re.sub(r'[\\/*?:"<>|]', "", track.get('name', 'Unknown'))
                artist = track.get('artist')
                
                if artist and artist != 'N/A':
                    sanitized_artist = re.sub(r'[\\/*?:"<>|]', "", artist)
                    filename = f"{sanitized_artist} - {sanitized_name}.mp3"
                else:
                    filename = f"{sanitized_name}.mp3"
                
                filepath = os.path.join(SAVE_DIR, filename)
                
                if not os.path.exists(filepath):
                    track['format_string'] = format_string
                    track['final_filename'] = filename
                    track['fragments'] = fragments
                    tracks_to_add.append(track)
                else:
                    print(f"Skipping existing file: {filename}")

            if tracks_to_add:
                self.download_queue.extend(tracks_to_add)
                self.set_status(f"Added {len(tracks_to_add)} new tracks. {len(self.download_queue)} total pending.")
                self.start_queue_processing_if_not_running()
            else:
                self.set_status("All selected tracks already exist.", "green")


    def start_queue_processing_if_not_running(self):
        if not self.is_processing_queue:
            self.is_processing_queue = True
            threading.Thread(target=self.process_download_queue, daemon=True).start()

    def process_download_queue(self):
        self.is_processing_queue = True
        
        initial_queue_size = len(self.download_queue)
        completed_count = 0
        
        while len(self.download_queue) > 0:
            if self.shutdown_event.is_set(): break
                
            with self.queue_lock:
                track = self.download_queue.pop(0)
            
            self._download_worker(track)
            
            completed_count += 1
            progress = completed_count / initial_queue_size
            self.after(0, self.progress_bar.set, progress)

        self.is_processing_queue = False
        if not self.shutdown_event.is_set():
            self.set_status("Download queue finished!", "green")
            
    def _download_worker(self, track):
        thread_id = threading.get_ident()
        
        with self.queue_lock:
            self.active_process = None

        try:
            final_filename = track['final_filename']
            self.set_status(f"Downloading: {final_filename.replace('.mp3', '')} ({len(self.download_queue)} left)")
            
            if not self.ffmpeg_path:
                self.set_status("Error: FFmpeg not found.", "red"); return

            youtube_url = track.get('videoId') if 'youtube.com' not in track.get('videoId', '') else track.get('videoId')
            if not youtube_url:
                self.set_status(f"Skipping {track.get('name')}: No YouTube ID.", "orange"); return
            
            temp_output_template = os.path.join(SAVE_DIR, f"{track.get('videoId')}.%(ext)s")

            command = [
                "yt-dlp", "--ffmpeg-location", self.ffmpeg_path,
                "--cookies", COOKIES_FILE_PATH, "-f", track['format_string'], "-x",
                "--audio-format", "mp3", "--concurrent-fragments", str(track.get('fragments', 1)),
                "--output", temp_output_template, youtube_url,
            ]
            
            process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8', errors='ignore', bufsize=1)
            with self.queue_lock:
                self.active_process = process
            
            self.update_analysis_text(f"Name: {final_filename.replace('.mp3', '')}\nSize: Pending...")
            
            for line in iter(process.stdout.readline, ''):
                if self.shutdown_event.is_set():
                    process.terminate(); break
            process.wait()

            if self.shutdown_event.is_set():
                print(f"Download cancelled for {track['final_filename']}"); return

            temp_filepath = os.path.join(SAVE_DIR, f"{track.get('videoId')}.mp3")
            final_filepath = os.path.join(SAVE_DIR, final_filename)

            if process.returncode == 0 and os.path.exists(temp_filepath):
                shutil.move(temp_filepath, final_filepath)
                self.after(0, self.load_downloaded_songs)
            else:
                self.set_status(f"Failed to download {track.get('name')}", "red")

        except Exception as e:
            self.set_status(f"Error downloading {track.get('name')}: {e}", "red")
        finally:
            with self.queue_lock:
                self.active_process = None
        
    def load_downloaded_songs(self):
        for widget in self.song_list_frame.winfo_children(): widget.destroy()
        try:
            files = os.listdir(SAVE_DIR)
            mp3_files = sorted([f for f in files if f.endswith('.mp3')])

            if not mp3_files:
                customtkinter.CTkLabel(self.song_list_frame, text="No songs downloaded yet.").pack(pady=20); return

            for filename in mp3_files:
                display_name = filename.replace('.mp3', '')
                song_frame = customtkinter.CTkFrame(self.song_list_frame)
                song_frame.pack(fill="x", padx=5, pady=5)
                song_frame.grid_columnconfigure(0, weight=1)
                customtkinter.CTkLabel(song_frame, text=display_name, anchor="w").grid(row=0, column=0, padx=10, pady=10, sticky="ew")
                customtkinter.CTkButton(song_frame, text="▶ Play", width=70, command=lambda p=os.path.join(SAVE_DIR, filename): self.play_song(p)).grid(row=0, column=1, padx=10, pady=5)
        
        except Exception as e:
            self.set_status(f"Error loading songs: {e}", "red")
            
    def play_song(self, path):
        try:
            if sys.platform == "win32": os.startfile(path)
            elif sys.platform == "darwin": subprocess.call(("open", path))
            else: subprocess.call(("xdg-open", path))
        except Exception as e:
            self.set_status(f"Could not play file: {e}", "red")

    def set_status(self, text, color="gray"):
        def _update(): self.status_label.configure(text=text, text_color=color)
        self.after(0, _update)

    def set_search_button_state(self, state, text=None):
        def _update(): self.search_button.configure(state=state, text=text or self.search_button.cget("text"))
        self.after(0, _update)
        
    def update_analysis_text(self, text):
        def _update():
            self.analysis_textbox.configure(state="normal")
            self.analysis_textbox.delete("0.0", "end")
            self.analysis_textbox.insert("0.0", text)
            self.analysis_textbox.configure(state="disabled")
        self.after(0, _update)

    def on_closing(self):
        print("Closing application...")
        self.shutdown_event.set()
        with self.queue_lock:
            if self.active_process:
                self.active_process.terminate()
            self.download_queue.clear()
        self.destroy()

    def cancel_all_downloads(self):
        print("Cancelling all downloads...")
        self.set_status("Cancelling all downloads...", "orange")
        self.shutdown_event.set()
        with self.queue_lock:
            if self.active_process:
                self.active_process.terminate()
            self.download_queue.clear()
        
        self.is_processing_queue = False
        self.shutdown_event = threading.Event()
        self.set_status("Downloads cancelled.", "orange")
        self.after(0, self.progress_bar.set, 0)
        self.after(0, self.percentage_label.configure, {"text":"0%"})


if __name__ == "__main__":
    app = App()
    app.mainloop()

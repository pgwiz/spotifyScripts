import streamlit as st
import httpx
import asyncio
import subprocess
import os
import json
import re
import shutil
from zipfile import ZipFile

# --- Configuration ---
API_BASE_URL = 'https://spotify-one-lime.vercel.app'
COOKIES_FILE_PATH = "cookies.txt"

# --- PROXY CONFIGURATION ---
# The base URL of your custom Node.js application-level proxy.
# This will be used to wrap all YouTube URLs.
PROXY_BASE_URL = "https://territorial-klara-pgwiz-43ae3de3.koyeb.app"


def get_ffmpeg_path():
    """Check for ffmpeg executable in the system's PATH."""
    return shutil.which("ffmpeg")


async def fetch_spotify_data(spotify_url):
    """Fetches track data from the Spotify API."""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{API_BASE_URL}/api/spotify?spotifyUrl={spotify_url}", timeout=45.0)
            response.raise_for_status()
            data = response.json()
            if isinstance(data, list):
                return data
            elif isinstance(data, dict) and 'tracks' in data:
                return data['tracks']
            return None
    except httpx.RequestError as e:
        st.error(f"Error connecting to the Spotify API: {e}")
        return None


def download_track(track, save_dir, ffmpeg_path):
    """
    Downloads a single track using yt-dlp.
    It wraps the YouTube URL with the proxy URL to bypass restrictions.
    """
    try:
        # Sanitize track name and artist for a valid filename
        sanitized_name = re.sub(r'[\\/*?:"<>|]', "", track.get('name', 'Unknown'))
        artist = track.get('artist')
        if artist and artist != 'N/A':
            sanitized_artist = re.sub(r'[\\/*?:"<>|]', "", artist)
            filename = f"{sanitized_artist} - {sanitized_name}.mp3"
        else:
            filename = f"{sanitized_name}.mp3"

        filepath = os.path.join(save_dir, filename)

        if os.path.exists(filepath):
            return filepath, f"Skipped: {filename} (already exists)"

        # Construct the full YouTube URL from the video ID
        video_id = track.get('videoId')
        if not video_id:
            return None, f"Skipped: {track.get('name')} (no YouTube ID found)"
        youtube_url = f"https://www.youtube.com/watch?v={video_id}"

        # --- MODIFIED PROXY LOGIC ---
        # "Wrap" the YouTube URL with your proxy's URL.
        # This sends the request to your proxy first.
        download_url = f"{PROXY_BASE_URL}/{youtube_url}"
        st.info(f"Using proxy: {PROXY_BASE_URL}")

        temp_output_template = os.path.join(save_dir, f"{video_id}.%(ext)s")

        # Build the yt-dlp command. Note the ABSENCE of the --proxy flag.
        command = [
            "yt-dlp",
            "--ffmpeg-location", ffmpeg_path,
            "-f", "bestaudio/best",
            "-x",
            "--audio-format", "mp3",
        ]

        # Add cookies argument if cookies.txt exists
        if os.path.exists(COOKIES_FILE_PATH):
            command.extend(["--cookies", COOKIES_FILE_PATH])

        # Add the output template and the final (wrapped) URL
        command.extend([
            "--output", temp_output_template,
            download_url,  # This is the URL that points to your proxy
        ])
        
        # --- END OF MODIFICATION ---

        process = subprocess.run(command, capture_output=True, text=True, encoding='utf-8', errors='ignore')

        if process.returncode == 0:
            temp_filepath = os.path.join(save_dir, f"{video_id}.mp3")
            if os.path.exists(temp_filepath):
                shutil.move(temp_filepath, filepath)
                return filepath, f"Downloaded: {filename}"
        
        error_message = process.stderr or "Unknown error"
        return None, f"Failed: {filename}\nError: {error_message.strip()}"
    except Exception as e:
        return None, f"Error downloading {track.get('name', 'Unknown')}: {e}"


def main():
    st.set_page_config(page_title="Music Downloader", page_icon="🎵", layout="centered")

    st.title("🎵 Spotify & YouTube Downloader")
    st.markdown("Paste a Spotify or YouTube link below to download the audio.")
    
    st.info(f"""
    **Using Proxy:** All downloads are routed through `{PROXY_BASE_URL}` to improve success rates.  
    **Cookies:** For age-restricted content, place a `cookies.txt` file in the app's root directory.
    """)

    if 'download_dir' not in st.session_state:
        st.session_state.download_dir = f"temp_downloads_{os.urandom(8).hex()}"
        os.makedirs(st.session_state.download_dir, exist_ok=True)

    ffmpeg_path = get_ffmpeg_path()
    if not ffmpeg_path:
        st.error("FFmpeg not found. Please ensure FFmpeg is installed and in your system's PATH. (Add `ffmpeg` to packages.txt if deploying on Streamlit Cloud).")
        return

    url = st.text_input("Enter Spotify or YouTube URL:", "")

    if st.button("Download"):
        if not url:
            st.warning("Please enter a URL.")
            return

        with st.spinner("Fetching track information..."):
            if "spotify.com" in url:
                tracks = asyncio.run(fetch_spotify_data(url))
                if not tracks:
                    st.error("Could not retrieve track list from Spotify link.")
                    return
            elif "youtube.com" in url or "youtu.be" in url:
                try:
                    info_command = ["yt-dlp", "--get-title", "--get-id", url]
                    process = subprocess.run(info_command, capture_output=True, text=True, encoding='utf-8', errors='ignore')
                    title, video_id = process.stdout.strip().split('\n')
                    tracks = [{'videoId': video_id, 'name': title or "YouTube Video", 'artist': 'N/A'}]
                except Exception as e:
                    st.error(f"Failed to get YouTube video details: {e}")
                    return
            else:
                st.error("Please enter a valid Spotify or YouTube URL.")
                return

        if tracks:
            st.info(f"Found {len(tracks)} track(s). Starting download...")
            
            progress_bar = st.progress(0)
            status_text = st.empty()
            downloaded_files = []

            for i, track in enumerate(tracks):
                filepath, message = download_track(track, st.session_state.download_dir, ffmpeg_path)
                status_text.text(message)
                if filepath:
                    downloaded_files.append(filepath)
                progress_bar.progress((i + 1) / len(tracks))
            
            if downloaded_files:
                st.success("All downloads complete!")
                
                if len(downloaded_files) > 1:
                    with st.spinner("Compressing files into a zip archive..."):
                        zip_path = os.path.join(st.session_state.download_dir, "downloaded_music.zip")
                        with ZipFile(zip_path, 'w') as zipf:
                            for file in downloaded_files:
                                zipf.write(file, os.path.basename(file))
                    
                    with open(zip_path, "rb") as f:
                        st.download_button(
                            label="Download All as ZIP",
                            data=f,
                            file_name="downloaded_music.zip",
                            mime="application/zip"
                        )
                else:
                    single_file_path = downloaded_files[0]
                    with open(single_file_path, "rb") as f:
                        st.download_button(
                            label=f"Download {os.path.basename(single_file_path)}",
                            data=f,
                            file_name=os.path.basename(single_file_path),
                            mime="audio/mpeg"
                        )
            else:
                st.warning("No files were downloaded.")

    st.markdown("---")
    st.markdown("Created with ❤️ using Streamlit")

if __name__ == "__main__":
    main()

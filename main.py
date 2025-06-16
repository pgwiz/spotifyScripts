import streamlit as st
import httpx
import asyncio
import subprocess
import os
import json
import re
import shutil
from zipfile import ZipFile
from yt_dlp import YoutubeDL

# --- Configuration ---
API_BASE_URL = 'https://spotify-one-lime.vercel.app'
COOKIES_FILE_PATH = "cookies.txt"

# --- PROXY CONFIGURATION ---
# The URL of your new standard HTTP/HTTPS forward proxy.
PROXY_URL = "https://territorial-klara-pgwiz-43ae3de3.koyeb.app"


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
    Downloads a single track using the yt-dlp Python library,
    routing all traffic through the specified proxy.
    """
    try:
        # Sanitize track name and artist for a valid final filename
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

        # Construct the direct YouTube URL from the video ID
        video_id = track.get('videoId')
        if not video_id:
            return None, f"Skipped: {track.get('name')} (no YouTube ID found)"
        youtube_url = f"https://www.youtube.com/watch?v={video_id}"
        
        temp_output_template = os.path.join(save_dir, f"{video_id}.%(ext)s")
        
        # --- MODIFIED: Use yt-dlp's native proxy option ---
        ydl_opts = {
            'format': 'bestaudio/best',
            'outtmpl': temp_output_template,
            'ffmpeg_location': ffmpeg_path,
            'extractaudio': True,
            'audioformat': 'mp3',
            'proxy': PROXY_URL, # Tell yt-dlp to use the forward proxy
            'cookiefile': COOKIES_FILE_PATH if os.path.exists(COOKIES_FILE_PATH) else None,
            'quiet': True,
            'no_warnings': True,
        }

        # Perform the download. yt-dlp will handle the proxy connection.
        with YoutubeDL(ydl_opts) as ydl:
            ydl.download([youtube_url])

        # Rename the downloaded file to the final, sanitized name
        temp_filepath = os.path.join(save_dir, f"{video_id}.mp3")
        if os.path.exists(temp_filepath):
            shutil.move(temp_filepath, filepath)
            return filepath, f"Downloaded: {filename}"
        else:
            raise FileNotFoundError("yt-dlp did not produce the expected file.")
        
    except Exception as e:
        return None, f"Error downloading '{track.get('name', 'Unknown')}': {e}"


def main():
    st.set_page_config(page_title="Music Downloader", page_icon="🎵", layout="centered")

    st.title("🎵 Spotify & YouTube Downloader")
    st.markdown("Paste a Spotify or YouTube link below to download the audio.")
    
    st.info(f"""
    **Using Proxy:** All downloads are routed through `{PROXY_URL}`.
    **Cookies:** For age-restricted content, place a `{COOKIES_FILE_PATH}` file in the app's root directory.
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
                    # Use the proxy for fetching info as well, for consistency
                    ydl_opts = {'quiet': True, 'no_warnings': True, 'proxy': PROXY_URL}
                    with YoutubeDL(ydl_opts) as ydl:
                        info = ydl.extract_info(url, download=False)
                        video_id = info.get('id')
                        title = info.get('title')
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

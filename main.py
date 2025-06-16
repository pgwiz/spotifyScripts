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
API_BASE_URL = 'https://spotify-one-lime.vercel.app'  # Your Vercel API URL

def get_ffmpeg_path():
    """Check for ffmpeg executable."""
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
            else:
                return None
    except httpx.RequestError as e:
        st.error(f"Error connecting to the API: {e}")
        return None

def download_track(track, save_dir, ffmpeg_path):
    """Downloads a single track using yt-dlp."""
    try:
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

        youtube_url = track.get('videoId')
        if not youtube_url:
            return None, f"Skipped: {track.get('name')} (no YouTube ID found)"

        temp_output_template = os.path.join(save_dir, f"{track.get('videoId')}.%(ext)s")
        
        command = [
            "yt-dlp",
            "--ffmpeg-location", ffmpeg_path,
            "-f", "bestaudio/best",
            "-x",
            "--audio-format", "mp3",
            "--output", temp_output_template,
            youtube_url,
        ]

        process = subprocess.run(command, capture_output=True, text=True, encoding='utf-8', errors='ignore')
        
        if process.returncode == 0:
            temp_filepath = os.path.join(save_dir, f"{track.get('videoId')}.mp3")
            if os.path.exists(temp_filepath):
                shutil.move(temp_filepath, filepath)
                return filepath, f"Downloaded: {filename}"
        
        return None, f"Failed: {filename}\n{process.stderr}"
    except Exception as e:
        return None, f"Error downloading {track.get('name', 'Unknown')}: {e}"

def main():
    st.set_page_config(page_title="Music Downloader", page_icon="🎵", layout="centered")

    st.title("🎵 Spotify & YouTube Downloader")
    st.markdown("Paste a Spotify or YouTube link below to download the audio.")

    if 'download_dir' not in st.session_state:
        st.session_state.download_dir = f"temp_downloads_{os.urandom(8).hex()}"
        os.makedirs(st.session_state.download_dir, exist_ok=True)

    ffmpeg_path = get_ffmpeg_path()
    if not ffmpeg_path:
        st.error("FFmpeg not found. Please ensure FFmpeg is installed and in your system's PATH.")
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
                    title_command = ["yt-dlp", "--get-title", url]
                    process = subprocess.run(title_command, capture_output=True, text=True, encoding='utf-8', errors='ignore')
                    title = process.stdout.strip() or "YouTube Video"
                    video_id_command = ["yt-dlp", "--get-id", url]
                    process = subprocess.run(video_id_command, capture_output=True, text=True, encoding='utf-8', errors='ignore')
                    video_id = process.stdout.strip()
                    tracks = [{'videoId': video_id, 'name': title, 'artist': 'N/A'}]
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


def cleanup():
    """Remove the temporary download directory."""
    if 'download_dir' in st.session_state and os.path.exists(st.session_state.download_dir):
        shutil.rmtree(st.session_state.download_dir)
        del st.session_state.download_dir

if __name__ == "__main__":
    try:
        main()
    finally:
        # This part for cleanup might not run as expected in Streamlit's execution model.
        # A manual cleanup or a scheduled task might be better for a deployed app.
        pass

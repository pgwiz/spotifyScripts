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
DOWNLOADS_DIR = "downloads"


def get_ffmpeg_path():
    """Check for ffmpeg executable in the system's PATH."""
    return shutil.which("ffmpeg")


async def fetch_spotify_data(spotify_url):
    """Fetches track data from the Spotify API."""
    try:
        async with httpx.AsyncClient() as client:
            # Use the API to get the track list from a Spotify URL
            api_url = f"{API_BASE_URL}/api/spotify?spotifyUrl={spotify_url}"
            response = await client.get(api_url, timeout=45.0)
            response.raise_for_status()
            data = response.json()

            # The API returns tracks in different structures, handle both
            tracks = data.get("tracks", []) if isinstance(data, dict) else data
            if tracks:
                # Return a list of full YouTube URLs for yt-dlp
                return [f"https://www.youtube.com/watch?v={track['videoId']}" for track in tracks if track.get('videoId')]
            return None
    except httpx.RequestError as e:
        st.error(f"Error connecting to the API service: {e}")
        return None
    except (json.JSONDecodeError, KeyError) as e:
        st.error(f"Error parsing the API response: {e}")
        return None


def download_youtube_urls(urls_to_download, save_dir, ffmpeg_path):
    """
    Downloads a list of YouTube URLs using the yt-dlp command-line tool.
    This function contains the core download logic.
    """
    try:
        if not urls_to_download:
            return None, "No valid YouTube URLs were provided to download."

        # Base command for yt-dlp
        command = [
            "yt-dlp",
            # Add headers to emulate a browser request, which can help bypass restrictions
            "--add-header", "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "--add-header", "Referer: https://www.youtube.com/",

            # Add format selection with a 15MB filesize limit
            "-f", "bestaudio[filesize<15M]/best",
            # Add ffmpeg location
            "--ffmpeg-location", ffmpeg_path,
            # Add audio extraction options
            "-x",
            "--audio-format", "mp3",
            # Define the output template
            "--output", os.path.join(save_dir, "%(title)s.%(ext)s"),
        ]

        # Add cookies argument if a cookies.txt file exists in the directory
        if os.path.exists(COOKIES_FILE_PATH):
            command.extend(["--cookies", COOKIES_FILE_PATH])

        # Add all the YouTube URLs to the command
        command.extend(urls_to_download)

        # Execute the command
        process = subprocess.run(command, capture_output=True, text=True, encoding='utf-8', errors='ignore')

        if process.returncode != 0:
            # If yt-dlp fails, return its error message for debugging
            error_message = process.stderr or "An unknown error occurred with yt-dlp."
            st.error(f"Download failed: {error_message.strip()}")
            return None, f"Download failed. See error details above."
        
        # If successful, find the list of downloaded files
        downloaded_files = [os.path.join(save_dir, f) for f in os.listdir(save_dir) if f.endswith('.mp3')]
        if not downloaded_files:
            return None, "Download process finished, but no new audio files were found. They might have been filtered by quality settings."
            
        return downloaded_files, f"Successfully downloaded {len(downloaded_files)} track(s)."

    except Exception as e:
        st.error(f"A critical error occurred during the download process: {e}")
        return None, "A critical error occurred."


def main():
    st.set_page_config(page_title="Music Downloader", page_icon="�", layout="centered")

    st.title("🎵 Spotify & YouTube Downloader")
    st.markdown("Paste a Spotify or YouTube link below to download the audio.")
    
    st.info(f"""
    **Downloads are sent directly with browser headers to improve success.**
    **Cookies:** For age-restricted content, place a `cookies.txt` file in the app's root directory.
    """)

    # Ensure a download directory exists for this session
    if 'download_dir' not in st.session_state:
        session_id = str(os.urandom(8).hex())
        st.session_state.download_dir = os.path.join(DOWNLOADS_DIR, session_id)
        os.makedirs(st.session_state.download_dir, exist_ok=True)
    
    save_dir = st.session_state.download_dir

    ffmpeg_path = get_ffmpeg_path()
    if not ffmpeg_path:
        st.error("FFmpeg not found. Please ensure FFmpeg is installed and in your system's PATH. (Add `ffmpeg` to packages.txt if deploying on Streamlit Cloud).")
        return

    url = st.text_input("Enter Spotify or YouTube URL:", "")

    if st.button("Download"):
        if not url:
            st.warning("Please enter a URL.")
            return

        with st.spinner("Processing link..."):
            if "spotify.com" in url:
                youtube_urls = asyncio.run(fetch_spotify_data(url))
                if not youtube_urls:
                    st.error("Could not get a list of YouTube URLs from the Spotify link.")
                    return
            elif "youtube.com" in url or "youtu.be" in url:
                youtube_urls = [url] # It's a single YouTube link
            else:
                st.error("Please enter a valid Spotify or YouTube URL.")
                return

        with st.spinner(f"Downloading {len(youtube_urls)} track(s)... This may take a while."):
            downloaded_files, message = download_youtube_urls(youtube_urls, save_dir, ffmpeg_path)
            st.info(message)
        
        if downloaded_files:
            st.success("All downloads are complete!")
            
            if len(downloaded_files) > 1:
                # If there are multiple files, offer them as a single zip archive
                with st.spinner("Compressing files into a zip archive..."):
                    zip_path = os.path.join(save_dir, "downloaded_music.zip")
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
                # If there's only one file, offer it directly
                single_file_path = downloaded_files[0]
                with open(single_file_path, "rb") as f:
                    st.download_button(
                        label=f"Download {os.path.basename(single_file_path)}",
                        data=f,
                        file_name=os.path.basename(single_file_path),
                        mime="audio/mpeg"
                    )

    st.markdown("---")
    st.markdown("Created with ❤️ using Streamlit")


if __name__ == "__main__":
    # Ensure the base downloads directory exists
    if not os.path.exists(DOWNLOADS_DIR):
        os.makedirs(DOWNLOADS_DIR)
    main()

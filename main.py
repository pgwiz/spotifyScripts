import streamlit as st
import httpx
import asyncio
import subprocess
import os
import json
import re
import shutil
import time
import random
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


def download_single_youtube_url(url_to_download, save_dir, ffmpeg_path, progress_bar, status_text):
    """
    Downloads a single YouTube URL and updates a Streamlit progress bar in real-time.
    """
    try:
        if not url_to_download:
            return None, "No valid YouTube URL was provided."

        # Base command for yt-dlp
        command = [
            "yt-dlp",
            # Add headers to emulate a browser request
            "--add-header", "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "--add-header", "Referer: https://www.youtube.com/",
            # Add format selection with a 15MB filesize limit
            "-f", "bestaudio[filesize<15M]/best",
            # Add ffmpeg location
            "--ffmpeg-location", ffmpeg_path,
            # Add audio extraction options
            "-x", "--audio-format", "mp3",
            # Define the output template
            "--output", os.path.join(save_dir, "%(title)s.%(ext)s"),
            # Ensure progress is output to stdout
            "--progress",
        ]

        # Add cookies argument if a cookies.txt file exists
        if os.path.exists(COOKIES_FILE_PATH):
            command.extend(["--cookies", COOKIES_FILE_PATH])

        # Add the URL to the command
        command.append(url_to_download)

        # Execute the command using Popen to capture output in real-time
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding='utf-8',
            errors='ignore'
        )

        downloaded_file_path = None
        
        if process.stdout:
            for line in iter(process.stdout.readline, ""):
                if not line:
                    break
                
                # Update the status text with the raw yt-dlp output
                status_text.text(line.strip())
                
                # Search for the download percentage
                match = re.search(r"\[download\]\s+([0-9.]+)%", line)
                if match:
                    percentage = float(match.group(1))
                    progress_bar.progress(percentage / 100.0)
                
                # Capture the final file path after conversion
                if '[ExtractAudio]' in line and 'Destination:' in line:
                    downloaded_file_path = line.split('Destination: ')[1].strip()

        process.wait()

        if process.returncode != 0:
            error_message = f"Download failed for {url_to_download}."
            st.warning(error_message)
            return None, error_message

        # Verify the file exists
        if downloaded_file_path and os.path.exists(downloaded_file_path):
             return [downloaded_file_path], "Successfully downloaded track."
        
        # Fallback if the path wasn't captured but files exist
        found_files = [os.path.join(save_dir, f) for f in os.listdir(save_dir) if f.endswith('.mp3')]
        if found_files:
            return found_files, "Successfully downloaded track(s)."
            
        return None, "Download process finished, but no output file was found."

    except Exception as e:
        st.error(f"A critical error occurred during the download process: {e}")
        return None, "A critical error occurred."


def main():
    st.set_page_config(page_title="Music Downloader", page_icon="🎵", layout="centered")

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
        
        st.info(f"Found {len(youtube_urls)} track(s). Starting download process...")
        
        all_downloaded_files = []
        
        # Placeholders for dynamic UI elements
        overall_progress_text = st.empty()
        overall_progress_bar = st.progress(0)
        song_progress_placeholder = st.empty()
        status_text_placeholder = st.empty()


        for i, single_url in enumerate(youtube_urls):
            overall_progress_text.text(f"Overall Progress: Track {i+1} of {len(youtube_urls)}")
            
            # Create a container for the current song's progress UI
            with song_progress_placeholder.container():
                st.write(f"Downloading: {single_url}")
                song_progress_bar = st.progress(0)

            # Pass a list containing just one URL to the download function
            downloaded_files, message = download_single_youtube_url(single_url, save_dir, ffmpeg_path, song_progress_bar, status_text_placeholder)
            
            if downloaded_files:
                all_downloaded_files.extend(downloaded_files)

            # Update overall progress
            overall_progress_bar.progress((i + 1) / len(youtube_urls))

            # Add a random delay to avoid rate-limiting
            if i < len(youtube_urls) - 1:
                delay = random.uniform(3, 7) # Wait for 3 to 7 seconds
                time.sleep(delay)
        
        # Clear the dynamic UI elements after the loop
        overall_progress_text.empty()
        song_progress_placeholder.empty()
        status_text_placeholder.empty()

        if all_downloaded_files:
            st.success("All downloads are complete!")
            
            if len(all_downloaded_files) > 1:
                # If there are multiple files, offer them as a single zip archive
                with st.spinner("Compressing files into a zip archive..."):
                    zip_path = os.path.join(save_dir, "downloaded_music.zip")
                    with ZipFile(zip_path, 'w') as zipf:
                        for file in all_downloaded_files:
                            zipf.write(file, os.path.basename(file))
                
                with open(zip_path, "rb") as f:
                    st.download_button(
                        label="Download All as ZIP",
                        data=f,
                        file_name="downloaded_music.zip",
                        mime="application/zip"
                    )
            elif all_downloaded_files:
                # If there's only one file, offer it directly
                single_file_path = all_downloaded_files[0]
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

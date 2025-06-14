import os
import random
import subprocess
import re # Import for regular expressions
import sys # Import for sys.stdout.write and sys.stdout.flush
from concurrent.futures import ThreadPoolExecutor
from pymediainfo import MediaInfo
import ffmpeg # This is for the ffmpeg-python library

# =============================================================================
# Section 1: MP4 Length Checker (Originally from MP4LengthChecker.py)
# Utilizes pymediainfo to accurately determine the duration of a video file.
# =============================================================================

def get_mp4_duration_mediainfo(filepath: str) -> float | None:
    """
    Checks the length (duration) of an MP4 file using pymediainfo.

    This function is robust and uses the MediaInfo library (via pymediainfo)
    to parse media file metadata. It can handle various video formats,
    though it specifically warns if the file doesn't have an MP4 extension.

    Args:
        filepath (str): The absolute or relative path to the MP4 file.

    Returns:
        float: The duration of the MP4 file in seconds.
        None: If the file is not found, an error occurs during processing,
              or no duration information can be extracted.
    """
    if not os.path.exists(filepath):
        print(f"Error: File not found at '{filepath}'")
        return None

    if not filepath.lower().endswith(('.mp4', '.m4v')):
        print(f"Warning: The file '{filepath}' does not appear to be an MP4 file, "
              "but MediaInfo will attempt to process it anyway.")

    try:
        media_info = MediaInfo.parse(filepath)

        for track in media_info.tracks:
            if track.track_type == 'Video' and track.duration is not None:
                return float(track.duration / 1000)
            elif track.track_type == 'General' and track.duration is not None:
                return float(track.duration / 1000)

        print(f"Could not find duration information for '{filepath}'")
        return None

    except Exception as e:
        print(f"Error processing file '{filepath}' with MediaInfo: {e}")
        print("Ensure the MediaInfo program is installed and accessible in your system's PATH.")
        return None


# =============================================================================
# Section 2: Satisfying Video Generator (Originally from satisfyingGeneratorcode2.py)
# Handles converting and combining multiple short video clips into a single
# background video, ensuring it meets a target duration.
# =============================================================================

def generate_variables(num_vars: int) -> dict[str, int]:
    """
    Generates a dictionary of unique random numbers (1-99) for a given count.
    Used for selecting 'Clip (X).mp4' files.
    """
    if not isinstance(num_vars, int) or num_vars < 1:
        raise ValueError("num_vars must be a positive integer")
    if num_vars > 99:
        raise ValueError("num_vars cannot be greater than 99, to ensure unique numbers between 1 and 99")

    generated_numbers = set()
    variables = {}
    for i in range(1, num_vars + 1):
        variable_name = f"var_{i}"
        while True:
            random_number = random.randint(1, 99)
            if random_number not in generated_numbers:
                generated_numbers.add(random_number)
                variables[variable_name] = random_number
                break
    return variables


def convert_video_format(input_file: str, output_file: str,
                         target_format: str = "mp4", video_codec: str = "libx264",
                         audio_codec: str = "aac", frame_width: int = 1080,
                         frame_height: int = 1920, frame_rate: float = 29.97,
                         bitrate: str = "6M", preset_val: str = "veryfast") -> str | None:
    """
    Converts a single video file to a specified format and resolution using FFmpeg.
    """
    command = [
        "ffmpeg", "-y",
        "-i", input_file,
        "-c:v", video_codec,
        "-c:a", audio_codec,
        "-vf", f"scale={frame_width}:{frame_height}",
        "-r", str(frame_rate),
        "-b:v", bitrate,
        "-pix_fmt", "yuv420p",
        "-preset", preset_val,
        output_file
    ]

    try:
        # Note: For individual clip conversions in parallel, a detailed progress bar
        # per clip would be complex to display. We'll just show completion here.
        subprocess.run(command, check=True, capture_output=True, text=True)
        print(f"[✓] Converted {os.path.basename(input_file)} -> {os.path.basename(output_file)}")
        return output_file
    except subprocess.CalledProcessError as e:
        print(f"[✗] Conversion failed for {os.path.basename(input_file)}\nError: {e.stderr}")
        return None


def convert_video_format_parallel(input_files: list[str], target_format: str = "mp4",
                                  frame_width: int = 1080, frame_height: int = 1920,
                                  frame_rate: float = 30, bitrate: str = "6M",
                                  max_workers: int = 4, preset_val: str = "veryfast") -> list[str]:
    """
    Converts multiple video files in parallel using `convert_video_format`.
    """
    futures = []
    converted_files = []

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        for i, input_file in enumerate(input_files):
            output_file = f"temp_clip_{i}.{target_format}"
            future = executor.submit(
                convert_video_format,
                input_file, output_file, target_format,
                "libx264", "aac", frame_width, frame_height,
                frame_rate, bitrate, preset_val
            )
            futures.append((future, output_file))

        for future, output_file in futures:
            result = future.result()
            if result:
                converted_files.append(result)
            else:
                print(f"[!] Skipping {os.path.basename(output_file)} due to error.")

    return converted_files


def select_clips_for_duration(target_duration: float, clips_dir: str = "Clips",
                              min_clip_length: float = 2.0) -> list[str]:
    """
    Selects random video clips from a directory until their combined duration
    meets or exceeds the specified target duration.
    """
    selected_clips = []
    total_duration = 0.0

    clip_files = [f for f in os.listdir(clips_dir) if f.lower().endswith(".mp4")]
    random.shuffle(clip_files)

    for clip_file in clip_files:
        clip_path = os.path.join(clips_dir, clip_file)
        try:
            probe = ffmpeg.probe(clip_path)
            duration = float(probe['format']['duration'])

            if duration >= min_clip_length:
                selected_clips.append(clip_path)
                total_duration += duration
                if total_duration >= target_duration:
                    break
        except Exception as e:
            print(f"[!] Failed to read duration for {os.path.basename(clip_file)} (using FFprobe): {e}")

    if total_duration < target_duration:
        print(f"⚠️ Warning: Not enough clips ({total_duration:.2f}s) to meet the target duration ({target_duration:.2f}s).")
    return selected_clips


def _parse_ffmpeg_progress(process, total_duration, frame_rate, description="Processing"):
    """
    Parses FFmpeg's stderr output to display a real-time progress bar.

    Args:
        process (subprocess.Popen): The FFmpeg subprocess object.
        total_duration (float): The total duration of the video being processed in seconds.
        frame_rate (float): The frame rate of the video.
        description (str): A string to describe the current operation in the progress bar.
    """
    frame_re = re.compile(r"frame=\s*(\d+)") # Regex to capture frame number

    prev_progress_line_length = 0
    total_frames = int(total_duration * frame_rate) if frame_rate > 0 else 0

    for line in process.stderr:
        line = line.decode(sys.getdefaultencoding(), errors='ignore').strip()

        frame_match = frame_re.search(line)

        if frame_match:
            current_frame = int(frame_match.group(1))

            progress_percent = (current_frame / total_frames) * 100 if total_frames > 0 else 0

            progress_line = f"\r{description}: {current_frame}/{total_frames} frames ({progress_percent:.2f}%)"
            sys.stdout.write(progress_line.ljust(prev_progress_line_length))
            sys.stdout.flush()
            prev_progress_line_length = len(progress_line)

    sys.stdout.write("\n")
    sys.stdout.flush()


def combine_videos_for_duration(target_duration: float, output_filename: str = "combinedVideos.mp4",
                                clips_dir: str = "Clips", frame_width: int = 1080,
                                frame_height: int = 1920, frame_rate: float = 29.97,
                                bitrate: str = "6M", preset_val: str = "veryfast", crf_val: int = 23) -> None:
    """
    Selects clips to match a target duration, converts them, and then combines them
    into a single output video using FFmpeg's concat demuxer, with a progress bar.
    """
    input_files = select_clips_for_duration(target_duration, clips_dir=clips_dir)

    if not input_files:
        print("Error: No valid input files were selected for background generation.")
        return

    print("🔄 Converting selected background video clips in parallel...")
    converted_files = convert_video_format_parallel(
        input_files,
        target_format="mp4",
        frame_width=frame_width,
        frame_height=frame_height,
        frame_rate=frame_rate,
        bitrate=bitrate,
        max_workers=min(8, len(input_files)),
        preset_val=preset_val
    )

    if not converted_files:
        print("❌ No background videos were successfully converted.")
        return

    input_list_filename = "temp_background_input_files.txt"
    output_path = os.path.abspath(output_filename)

    try:
        with open(input_list_filename, "w") as f:
            for converted_file in converted_files:
                f.write(f"file '{converted_file}'\n")
    except Exception as e:
        print(f"❌ Could not create input list file for background combination: {e}")
        return

    print(f"🎬 Combining {len(converted_files)} background video clips into {os.path.basename(output_path)}...")
    command = [
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0",
        "-i", input_list_filename,
        "-c:v", "libx264",
        "-preset", preset_val,
        "-crf", str(crf_val),
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-b:a", "128k",
        "-r", str(frame_rate),
        "-b:v", bitrate,
        "-avoid_negative_ts", "make_zero",
        output_path
    ]

    try:
        # Use subprocess.Popen to get real-time output for progress bar
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        _parse_ffmpeg_progress(process, target_duration, frame_rate, description="Combining background videos") # Pass frame_rate

        # Wait for the process to complete and check its return code
        stdout, stderr = process.communicate()
        if process.returncode != 0:
            print(f"❌ FFmpeg command failed during background combination:\n{stderr.decode()}")
        else:
            print(f"✅ Successfully combined background videos into {os.path.basename(output_path)}")
    except FileNotFoundError:
        print("Error: ffmpeg not found. Please ensure it is installed and in your system's PATH.")
    except Exception as e:
        print(f"An unexpected error occurred during background video combination: {e}")
    finally:
        if os.path.exists(input_list_filename):
            os.remove(input_list_filename)
        for f in converted_files:
            if os.path.exists(f):
                os.remove(f)


# =============================================================================
# Section 3: Green Screen Combiner (Originally from greenscreen.py)
# Uses FFmpeg's chromakey filter to overlay a green screen foreground onto a
# background video, matching the output length to the foreground.
# =============================================================================

def combine_green_screen_foreground_length(foreground_video: str, background_video: str,
                                           output_video: str = "combined_video.mp4",
                                           key_color: str = "0x00FF00", similarity: str = "0.3",
                                           preset_val: str = "veryfast", crf_val: int = 23,
                                           frame_rate: float = 29.97) -> None: # Added frame_rate
    """
    Combines two videos using FFmpeg's chromakey filter with a progress bar.
    The output video's length will be trimmed to match the foreground video's duration.
    """
    if not os.path.exists(foreground_video):
        print(f"Error: Foreground video '{foreground_video}' not found.")
        return
    if not os.path.exists(background_video):
        print(f"Error: Background video '{background_video}' not found.")
        return

    try:
        # Get the exact duration of the foreground video using ffprobe
        probe_cmd = [
            "ffprobe",
            "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            foreground_video
        ]
        probe_result = subprocess.run(probe_cmd, capture_output=True, text=True, check=True)
        foreground_duration_str = probe_result.stdout.strip()
        foreground_duration = float(foreground_duration_str)

        ffmpeg_cmd = [
            "ffmpeg", "-y",
            "-i", foreground_video,
            "-i", background_video,
            "-filter_complex",
            f"[0:v]chromakey={key_color}:{similarity}[fg];"
            f"[1:v]trim=end={foreground_duration},setpts=PTS-STARTPTS[bg_trimmed];"
            f"[bg_trimmed][fg]overlay[out]",
            "-map", "[out]",
            "-map", "0:a?",
            "-c:v", "libx264", # Explicitly setting codec, important for preset/crf
            "-preset", preset_val,
            "-crf", str(crf_val),
            "-pix_fmt", "yuv420p", # Ensure pix_fmt is set
            "-c:a", "copy",
            "-t", str(foreground_duration),
            output_video
        ]

        print(f"🧪 Applying green screen effect and combining videos into {os.path.basename(output_video)}...")
        # Use subprocess.Popen to get real-time output for progress bar
        process = subprocess.Popen(ffmpeg_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        _parse_ffmpeg_progress(process, foreground_duration, frame_rate, description="Applying green screen") # Pass frame_rate

        # Wait for the process to complete and check its return code
        stdout, stderr = process.communicate()
        if process.returncode != 0:
            print(f"❌ Error during ffmpeg processing:\n{stderr.decode()}")
        else:
            print(f"✅ Successfully combined '{os.path.basename(foreground_video)}' and '{os.path.basename(background_video)}' "
                  f"(trimmed to foreground length) into '{os.path.basename(output_video)}'.")
            print(f"You can now play '{os.path.basename(output_video)}'.")

    except FileNotFoundError:
        print("Error: ffmpeg or ffprobe could not be found. Please ensure they are installed and in your system's PATH.")
    except ValueError:
        print("Error: Could not parse the duration of the foreground video (ffprobe output invalid).")
    except Exception as e:
        print(f"An unexpected error occurred during green screen combination: {e}")


# =============================================================================
# Section 4: Main Pipeline (Originally from full_pipeline.py)
# Orchestrates the entire process: duration check -> background generation -> green screen merge.
# =============================================================================

def main():
    """
    Main function to run the complete video processing pipeline.
    It takes a green screen foreground video, generates a background video
    of matching length, and then combines them.
    """
    script_dir = os.path.dirname(__file__)

    # ✅ Ask user which background folder to use
    print("\n📁 Available background categories: Clips, Gameplay, Gameplay 2, Gameplay 3")
    selected_category = input("Enter background category to use (default is 'Clips'): ").strip()
    if not selected_category:
        selected_category = "Clips"

    clips_dir_path = os.path.join(script_dir, selected_category)
    if not os.path.exists(clips_dir_path):
        print(f"❌ Error: Selected background category '{selected_category}' does not exist at path: {clips_dir_path}")
        return

    foreground_video = os.path.join(script_dir, "foreground.mp4")
    background_output = os.path.join(script_dir, "background_combined.mp4")
    final_output = os.path.join(script_dir, "final_output.mp4")

    print(f"\n🎥 Step 1: Checking duration of the foreground video: {os.path.basename(foreground_video)}")
    duration = get_mp4_duration_mediainfo(foreground_video)

    if duration is None:
        print("❌ Pipeline aborted: Could not determine the duration of the foreground video.")
        return

    print(f"⏱️ Foreground video duration: {duration:.2f} seconds")

    current_preset = "veryfast"
    current_crf = 23
    target_frame_rate = 30.0

    print(f"\n🎲 Step 2: Generating background video using clips from '{selected_category}'...")

    combine_videos_for_duration(
        target_duration=duration,
        output_filename=background_output,
        clips_dir=clips_dir_path,
        frame_width=1080,
        frame_height=1920,
        frame_rate=target_frame_rate,
        bitrate="6M",
        preset_val=current_preset,
        crf_val=current_crf
    )

    if not os.path.exists(background_output):
        print("❌ Pipeline aborted: Background video was not successfully generated.")
        return

    print(f"\n🧪 Step 3: Applying green screen effect...")
    combine_green_screen_foreground_length(
        foreground_video=foreground_video,
        background_video=background_output,
        output_video=final_output,
        preset_val=current_preset,
        crf_val=current_crf,
        frame_rate=target_frame_rate
    )

    if os.path.exists(final_output):
        print(f"\n✅ Pipeline completed successfully! Final output saved as: '{os.path.basename(final_output)}'")
    else:
        print("\n❌ Pipeline failed: Final output video was not created.")


# Entry point for the script
if __name__ == "__main__":
    main()

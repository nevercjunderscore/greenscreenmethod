from fastapi import FastAPI, UploadFile, Form
import shutil
import os
from greenv7 import get_mp4_duration_mediainfo, combine_videos_for_duration, combine_green_screen_foreground_length

app = FastAPI()

@app.post("/generate")
async def generate_final_video(
    foreground: UploadFile,
    category: str = Form("Clips")
):
    # Save uploaded foreground
    foreground_path = "foreground.mp4"
    with open(foreground_path, "wb") as f:
        shutil.copyfileobj(foreground.file, f)

    # Check duration
    duration = get_mp4_duration_mediainfo(foreground_path)
    if duration is None:
        return {"error": "Could not determine duration of foreground video."}

    clips_dir = category if os.path.exists(category) else "Clips"
    background_output = "background_combined.mp4"
    final_output = "final_output.mp4"

    # Generate background
    combine_videos_for_duration(
        target_duration=duration,
        output_filename=background_output,
        clips_dir=clips_dir
    )

    # Apply green screen
    combine_green_screen_foreground_length(
        foreground_video=foreground_path,
        background_video=background_output,
        output_video=final_output
    )

    # Return result path
    return {"message": "Video generated", "output": final_output}

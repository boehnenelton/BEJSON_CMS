"""
Library:      lib_av_manager.py
Family:       System
Jurisdiction: ["BEJSON_LIBRARIES", "PY"]
Status:       OFFICIAL
Author:       Elton Boehnen
Version:      2.0.1 OFFICIAL
            MFDB Version: 1.31
Format_Creator: Elton Boehnen
Date:         2026-05-18
Description:  Handler for system-level audio and video asset orchestration.
"""

import os
import subprocess
import json
import base64

class AVManager:
    def __init__(self, ffmpeg_path="ffmpeg"):
        self.ffmpeg = ffmpeg_path

    def run_command(self, args):
        try:
            # Secure execution: list-based arguments, shell=False
            result = subprocess.run(args, capture_output=True, text=True, check=False)
            if result.returncode != 0:
                return False, result.stderr
            return True, result.stdout
        except Exception as e:
            return False, str(e)

    def get_info(self, input_file):
        args = ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", "-show_streams", input_file]
        success, output = self.run_command(args)
        if success:
            return json.loads(output)
        return None

    def process_with_preset(self, input_file, output_file, preset):
        info = self.get_info(input_file)
        if not info: return False, "Could not probe file."
        
        has_video = any(s.get("codec_type") == "video" for s in info.get("streams", []))
        v_codec = preset.get("v_codec", "libx264")
        a_codec = preset.get("a_codec", "copy")
        crf = preset.get("crf")
        scale = preset.get("scale")
        extra = preset.get("extra", "")
        
        args = [self.ffmpeg, "-y", "-i", input_file]
        
        if has_video:
            args.extend(["-c:v", v_codec])
            if crf: args.extend(["-crf", str(crf)])
            if scale: args.extend(["-vf", f"scale={scale}"])
        
        args.extend(["-c:a", a_codec])
        
        if extra:
            # Simple space-based split for extra flags
            args.extend(extra.split())
            
        args.append(output_file)
        return self.run_command(args)

    def split_file(self, input_file, output_pattern, segment_time=300):
        """Splits file into N-minute segments (default 5m/300s)."""
        args = [
            self.ffmpeg, "-y", "-i", input_file,
            "-f", "segment", "-segment_time", str(segment_time),
            "-reset_timestamps", "1", "-c", "copy", output_pattern
        ]
        return self.run_command(args)

    def to_base64(self, input_file):
        """Converts file to a Base64 string."""
        try:
            with open(input_file, "rb") as f:
                return True, base64.b64encode(f.read()).decode("utf-8")
        except Exception as e:
            return False, str(e)

    def create_slideshow(self, image_file, audio_file, output_file, preset):
        """Combines a static image and audio into a space-efficient video."""
        v_codec = preset.get("v_codec", "libx264")
        a_codec = preset.get("a_codec", "aac")
        crf = preset.get("crf", 30)
        scale = preset.get("scale", "854:480") # Default to 480p for space
        
        args = [
            self.ffmpeg, "-y", "-loop", "1", "-i", image_file,
            "-i", audio_file, "-c:v", v_codec, "-crf", str(crf),
            "-vf", f"scale={scale},format=yuv420p", "-c:a", a_codec,
            "-shortest", output_file
        ]
        return self.run_command(args)

if __name__ == "__main__":
    print("AV Manager Library - v1.5 OFFICIAL [SECURITY HARDENED]")

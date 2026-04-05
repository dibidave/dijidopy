import os
from datetime import datetime, timezone, timedelta
from pydub import AudioSegment
import pygame
import argparse

def parse_timestamp(timestamp_str):
    print(timestamp_str)
    # Split the string into date/time and milliseconds
    datetime_part, milliseconds_part = timestamp_str.split('.')
    
    # Parse the main part of the datetime
    dt = datetime.strptime(datetime_part, "%Y%m%dT%H%M%S")
    
    # Add milliseconds
    milliseconds = int(milliseconds_part[:-1])  # Remove 'Z' and convert to int
    
    # Combine and set timezone to UTC
    return dt.replace(microsecond=milliseconds*1000, tzinfo=timezone.utc)


def process_audio_files(folder, start_timestamp, output_file=None):
    files = [f for f in os.listdir(folder) if f.endswith('.mp3')]
    audio_segments = []

    start_time = parse_timestamp(start_timestamp)

    for file in files:
        prefix, timestamp_str = file.split('_')
        file_start_time = parse_timestamp(timestamp_str.split('.')[0] + "." + timestamp_str.split('.')[1])
        
        audio = AudioSegment.from_mp3(os.path.join(folder, file))
        duration = len(audio) / 1000  # Duration in seconds
        file_end_time = file_start_time + timedelta(seconds=duration)

        if file_end_time > start_time:
            offset = max(0, (file_start_time - start_time).total_seconds() * 1000)
            trim_start = max(0, (start_time - file_start_time).total_seconds() * 1000)
            
            trimmed_audio = audio[trim_start:]
            audio_segments.append((offset, trimmed_audio))

    if not audio_segments:
        print("No audio files found that extend past the specified timestamp.")
        return
    
    # Print how many audio segments were detected
    print(f"Detected {len(audio_segments)} audio segments.")

    # Sort segments by offset
    audio_segments.sort(key=lambda x: x[0])

    # Find the latest end time
    end_time = max(offset + len(audio) for offset, audio in audio_segments)

    # Create a silent base track
    combined = AudioSegment.silent(duration=end_time)

    # Overlay all audio segments
    for offset, audio in audio_segments:
        combined = combined.overlay(audio, position=int(offset))

    if output_file:
        combined.export(output_file, format="mp3")
        print(f"Combined audio saved to {output_file}")
    else:
        return combined

def play_audio(audio):
    pygame.mixer.init()
    pygame.mixer.music.load(audio.export(format="mp3"))
    pygame.mixer.music.play()

    while pygame.mixer.music.get_busy():
        pygame.time.Clock().tick(10)

def main():
    parser = argparse.ArgumentParser(description="Process and play interleaved audio files.")
    parser.add_argument("folder", help="Folder containing the audio files")
    parser.add_argument("timestamp", help="Start timestamp in format YYYYMMDDTHHMMSS.sssZ")
    parser.add_argument("--output", help="Output file name (optional)")
    args = parser.parse_args()

    if args.output:
        process_audio_files(args.folder, args.timestamp, args.output)
    else:
        audio = process_audio_files(args.folder, args.timestamp)
        if audio:
            play_audio(audio)

if __name__ == "__main__":
    main()
#!/usr/bin/python3

import subprocess
import tempfile
import json
import os
import sys

# try https://audible-converter.ml or audible-activator
activation_bytes = "deadbeef"

try:
	aax_file = sys.argv[1]
	outdir = sys.argv[2]
except:
	print(f"Usage: {sys.argv[0]} AAX_FILE OUTPUT_DIR")
	sys.exit(1)

m4b_tmpfile = tempfile.NamedTemporaryFile(suffix=".m4b")
m4b_file = m4b_tmpfile.name

print("Decrypting AAX to M4B")
subprocess.check_output(["ffmpeg", "-hide_banner", "-y", "-activation_bytes", activation_bytes, "-i", aax_file, "-activation_bytes", activation_bytes, "-c", "copy", m4b_file])

if not os.path.exists(outdir):
	os.mkdir(outdir)

print("Extracting logo")
logo_file = os.path.join(outdir, "logo.png")
if os.path.exists(logo_file):
	os.unlink(logo_file)
subprocess.check_call(["ffmpeg", "-loglevel", "error", "-i", m4b_file, "-map", "0:v", "-frames:v", "1", logo_file])

chapters = json.loads(subprocess.check_output(["ffprobe", "-loglevel", "error", m4b_file, "-show_chapters", "-print_format", "json"]))['chapters']

ogg_file_list = []

i = 1
for chapter in chapters:
	print(f"Transcoding chapter {i}/{len(chapters)}")
	filename = "%03i.ogg" % i
	ogg_file = os.path.join(outdir, filename)
	ogg_file_list.append(filename)
	if os.path.exists(ogg_file):
		os.unlink(ogg_file)
	subprocess.check_call(["ffmpeg", "-loglevel", "error", "-i", m4b_file, "-map", "0:a", "-c:a", "libopus", "-b:a", "48k", "-ss", chapter['start_time'], "-to", chapter['end_time'], ogg_file])
	i += 1

print("Writing playlist")
playlist_file = os.path.join(outdir, "playlist.m3u")
with open(playlist_file, 'w') as playlist:
	playlist.write("\n".join(ogg_file_list))
	playlist.write("\n")

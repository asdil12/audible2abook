#!/usr/bin/python3

import subprocess
import tempfile
import json
import os
import re
import sys
import multiprocessing
from queue import Queue
from threading import Thread

# try https://audible-converter.ml or audible-activator
activation_bytes = "deadbeef"

subprocess.check_output(['which', 'ffmpeg'])
subprocess.check_output(['which', 'ffprobe'])
subprocess.check_output(['which', 'mediainfo'])

def get_metadata(aax_file):
	m = json.loads(subprocess.check_output(['ffprobe', '-v', 'quiet', '-print_format', 'json', '-show_format', aax_file]))
	o = {
		'author': m['format']['tags']['artist'],
		'title': m['format']['tags']['title'],
		'description': m['format']['tags']['comment'],
		'date': m['format']['tags']['date'],
		'lang': 'de'
	}
	n = subprocess.check_output(['mediainfo', aax_file])
	for line in n.decode('utf-8').split("\n"):
		if line.startswith('nrt '):
			o['narrator'] = line.split(':')[1].strip()
	return o

def try_capitalize(s, ref):
	""" This will try to capitalize s by looking at ref to see how the
	    works are capitalized there. First char will always be capital. """
	i = iter(s.capitalize().split(' '))
	t = [next(i)] # first word is already processed
	ref = " ".join(ref.split(' ')[1:]) # strip first word
	for w in i:
		try:
			t.append(re.search(w, ref, re.IGNORECASE)[0])
		except TypeError:
			try:
				w = w.replace('ae', 'ä').replace('oe', 'ö').replace('ue', 'ü')
				t.append(re.search(w, ref, re.IGNORECASE)[0])
			except TypeError:
				t.append(w)
	return " ".join(t)


try:
	aax_file = sys.argv[1]
	outdir = sys.argv[2]
except:
	try:
		aax_file = sys.argv[1]
		m = get_metadata(aax_file)
		author = m['author'].lower().replace(' ', '_')
		title = m['title'].lower()
		if ':' in title:
			if re.search(r"[0-9]", title):
				title, series = [s.strip() for s in title.split(':')]
				series = series.replace('-serie', '')
				title = f"{series}_{title}"
			else:
				title = title.replace(':', '')
		title = title.replace(' ', '_').replace("'", "").replace('_-_', '_')
		title = title.replace('ä', 'ae').replace('ö', 'oe').replace('ü', 'ue').replace('ß', 'ss')
		print(f"Abook name hint: {author}.{title}.{m['lang']}")
		os._exit(0)
	except:
		raise
		print(f"Usage: {sys.argv[0]} AAX_FILE OUTPUT_DIR")
		sys.exit(1)

if aax_file.endswith('.m4b'):
	m4b_file = aax_file
else:
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

q = Queue(maxsize=1)

def encode_chapters():
	while True:
		chapter, ogg_file = q.get()
		if os.path.exists(ogg_file):
			os.unlink(ogg_file)
		subprocess.check_call(["ffmpeg", "-loglevel", "error", "-i", m4b_file, "-map", "0:a", "-c:a", "libopus", "-b:a", "48k", "-ss", chapter['start_time'], "-to", chapter['end_time'], ogg_file])
		q.task_done()

threads = []
for i in range(multiprocessing.cpu_count()):
	print(f"Starting encoder thread #{i}")
	t = Thread(target=encode_chapters, daemon=True)
	threads.append(t)
	t.start()

chapter_offset = int(os.environ.get('CHAPTER_OFFSET', '1').strip())
i = chapter_offset
for chapter in chapters:
	print(f"Transcoding chapter {i}/{len(chapters)+chapter_offset-1}")
	filename = "%03i.ogg" % i
	ogg_file = os.path.join(outdir, filename)
	ogg_file_list.append(filename)
	q.put([chapter, ogg_file])
	i += 1

q.join()
print("Transcoding finished")

print("Writing playlist")
playlist_file = os.path.join(outdir, "playlist.m3u")
with open(playlist_file, 'w') as playlist:
	playlist.write("\n".join(ogg_file_list))
	playlist.write("\n")

print("Writing metadata")
author, title, lang = os.path.basename(outdir.strip('/')).split('.')
author = author.replace('_', ' ').title()
title = title.replace('_', ' ')

series = []
ms = re.match(r"([^0-9]+)([0-9]+) ([^0-9]+)", title)
if ms:
	series = [ms.group(1) + f"#{int(ms.group(2))}"]
	title = ms.group(3)

lang = lang.replace('de', 'German')
lang = lang.replace('en', 'English')

j = {"metadata": {
	"title": title,
	"authors": [author],
	"series": series,
	"language": lang
}}

m = get_metadata(aax_file)
if 'narrator' in m:
	j['metadata']['narrators'] = [m['narrator']]
if not 'Chapter' in m['description'] and len(m['description']) > 20:
	j['metadata']["description"] = m['description']
j['metadata']["publishedYear"] = m['date']
j['metadata']["authors"] = [a.strip() for a in m['author'].split(',')] # overwrite: sometimes names have special chars
j['metadata']['title'] = try_capitalize(j['metadata']['title'], m['title'])
if j['metadata']['series']:
	j['metadata']['series'] = [try_capitalize(s, m['title']) for s in j['metadata']['series']]

# subtitle: str
# isbn: str
# asin: str
# explicit: bool
# abridged: bool

json.dump(j, open(os.path.join(outdir, "metadata.json"), "w"), indent=2)

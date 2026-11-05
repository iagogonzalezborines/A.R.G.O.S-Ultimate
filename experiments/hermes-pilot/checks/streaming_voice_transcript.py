import json,sys,re,subprocess
from pathlib import Path
from faster_whisper import WhisperModel
p=Path('/home/tyrant/.local/share/argos-hermes-pilot');r=p/'ui-workbench/reports/streaming-voice';model=WhisperModel('base',download_root='/home/tyrant/.local/share/argos/models/whisper',device='cpu',compute_type='int8',cpu_threads=2,local_files_only=True)
rows=[]
for name in ['plain-1.wav','compiled-1.wav']:
 f=r/name;segments,_=model.transcribe(str(f),language='en',beam_size=3,word_timestamps=True,vad_filter=False);words=[];text=''
 for segment in segments:text+=segment.text;words += [{'word':w.word,'start':w.start,'end':w.end} for w in segment.words]
 normalized=lambda s:re.sub('[^a-z ]',' ',s.lower()).split()
 end=normalized(text)[-4:];row={'sample':name,'text':text,'words':words,'ending_retained':end==['for','the','next','task']};rows.append(row);print(json.dumps(row),flush=True)
(r/'transcript-check.json').write_text(json.dumps(rows,indent=2)+'\n')

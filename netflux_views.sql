create or replace view kairos.v_netflux_media_queue as 

select
m.id as media_id,
concat(inputpath,'/','',medianame,ext) as inputmedia,
concat(outputpath,'/','','publicdomain','/',parentfolder,'/',medianame,'/',medianame,'.mp4') as outputmedia
from kairos.netflux_queue q

left outer join kairos.netflux_queue_media m 
on q.id = m.id_key
where m.active is null and mp4_conversion is null


create or replace view kairos.v_netflux_media_ffprobe as 

select
m.id as media_id,
concat(inputpath,'/','',medianame,ext) as inputmedia,
concat(outputpath,'/','','publicdomain','/',parentfolder,'/',medianame,'/',medianame,'.mp4') as outputmedia
from kairos.netflux_queue q

left outer join kairos.netflux_queue_media m 
on q.id = m.id_key
where m.active = 0 and mp4_conversion = 1 and ffprobe_metadata is null

create or replace view kairos.v_netflux_media_subtitle_pgs_to_png as 
select
m.id as media_id,
concat(inputpath,'/','',medianame,ext) as inputmedia,
concat(outputpath,'/','','publicdomain','/',parentfolder,'/',medianame,'/','pgs_png','/') as outputpngs
from kairos.netflux_queue q

left outer join kairos.netflux_queue_media m 
on q.id = m.id_key

where subtitle_pgs_to_png is null


create or replace view kairos.v_netflux_media_parakeet as 
select 
m.id as media_id,
concat(inputpath,'/','',medianame,ext) as inputmedia,
concat(outputpath,'/','','publicdomain','/',parentfolder,'/',medianame,'/','wav','/',medianame,'.wav') as outputwav

from kairos.netflux_queue q

left outer join kairos.netflux_queue_media m 
on q.id = m.id_key

where m.active = 0 and mp4_conversion = 1
and m.subtitle_pgs_to_png = 0
and m.subtitle_extract_wav is null

-- left outer join kairos.netflux_ffprobe ff 
-- on m.id = ff.media_id_key
-- 
-- left outer join kairos.netflux_transcriptions t 
-- on m.id = t.media_id_key

create or replace view kairos.v_netflux_media_parakeet_wav_transcription as 
select 
m.id as media_id,
concat(outputpath,'/','','publicdomain','/',parentfolder,'/',medianame,'/','wav','/',medianame,'.wav') as inputwav

from kairos.netflux_queue q

left outer join kairos.netflux_queue_media m 
on q.id = m.id_key

where m.active = 0 and mp4_conversion = 1
and m.subtitle_pgs_to_png = 0
and m.subtitle_extract_wav = 1
and subtitle_wav_transcribe is null

with vtt as (
SELECT
  media_id_key,
  CONCAT(
    'WEBVTT\n\n',
    GROUP_CONCAT(
      CONCAT(start_ts, ' --> ', end_ts, '\n', textranscript, '\n\n')
      ORDER BY segmentstart
      SEPARATOR ''
    )
  ) AS vtt
FROM (
  SELECT
    media_id_key,
    textranscript,
    segmentstart,
    CONCAT(
      LPAD(FLOOR(segmentstart / 3600), 2, '0'), ':',
      LPAD(FLOOR(MOD(segmentstart, 3600) / 60), 2, '0'), ':',
      LPAD(MOD(FLOOR(segmentstart), 60), 2, '0'), '.',
      LPAD(FLOOR(MOD(segmentstart, 1) * 1000), 3, '0')
    ) AS start_ts,
    CONCAT(
      LPAD(FLOOR(segmentend / 3600), 2, '0'), ':',
      LPAD(FLOOR(MOD(segmentend, 3600) / 60), 2, '0'), ':',
      LPAD(MOD(FLOOR(segmentend), 60), 2, '0'), '.',
      LPAD(FLOOR(MOD(segmentend, 1) * 1000), 3, '0')
    ) AS end_ts
  FROM kairos.netflux_transcriptions
) t
GROUP BY media_id_key
)
select 
m.id as media_id,
concat(outputpath,'/','','publicdomain','/',parentfolder,'/',medianame,'/',medianame,'.vtt') as inputwav,
v.vtt

from kairos.netflux_queue q

left outer join kairos.netflux_queue_media m 
on q.id = m.id_key

left outer join vtt v 
on m.id = v.media_id_key

where v.media_id_key is not null

with ffprobe  as (
select 
id,
JSON_LENGTH(ffprobe_json_source_video, '$.chapters') AS chapter_count,
JSON_UNQUOTE(JSON_EXTRACT(ffprobe_json_source_video, '$.format.size')) / POWER(1024, 3) as input_sizeGB,
JSON_UNQUOTE(JSON_EXTRACT(ffprobe_json_output_video, '$.format.size')) / POWER(1024, 3) as output_sizeGB,
DATE_FORMAT(SEC_TO_TIME(JSON_UNQUOTE(JSON_EXTRACT(ffprobe_json_source_video, '$.format.duration'))), '%H:%i:%s') as HHmmSS,
JSON_EXTRACT(ffprobe_json_source_video, '$.streams[0].width') as width,
JSON_EXTRACT(ffprobe_json_source_video, '$.streams[0].height') as height,
JSON_UNQUOTE(JSON_EXTRACT(ffprobe_json_source_video, '$.streams[0].display_aspect_ratio')) as display_aspect_ratio
FROM kairos.netflux_ffprobe

)

select 
*

from kairos.netflux_queue q 
left outer join kairos.netflux_queue_media m 
on q.id = m.id_key

left outer join kairos.netflux_transcriptions t 
on m.ID = t.media_id_key



select 
q.ID as id_queue,
q.inputpath,
q.outputpath,
q.category,
q.category_sub,
q.active as active_queue,
m.ID as id_media,
m.medianame,
m.id_key as id_key_media,
m.parentfolder,
m.active as active_media,
m.ext,
m.mp4_conversion,
ffprobe_metadata,
subtitle_pgs_to_png,
subtitle_png_to_vtt,
ff.ID as id_ffprobe,
ffprobe_json_source_video,
ff.media_id_key,
ffprobe_json_output_video,
textranscript,
segmentend,
segementstart
from kairos.netflux_queue q

left outer join kairos.netflux_queue_media m 
on q.id = m.id_key

left outer join kairos.netflux_ffprobe ff 
on m.id = ff.media_id_key

left outer join kairos.netflux_transcriptions t 
on m.id = t.media_id_key

where m.active = 0 and mp4_conversion = 1
and m.subtitle_pgs_to_png = 0


-- select * from kairos.netflux_queue
-- select * from kairos.netflux_queue_media
-- select * from kairos.netflux_ffprobe
-- select * from kairos.netflux_transcriptions limit 10
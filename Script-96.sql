with ffprobe  as (
select 
file_id,
JSON_LENGTH(ffprobe_json_source_video, '$.chapters') AS chapter_count,
JSON_UNQUOTE(JSON_EXTRACT(ffprobe_json_source_video, '$.format.size')) / POWER(1024, 3) as input_sizeGB,
JSON_UNQUOTE(JSON_EXTRACT(ffprobe_json_output_video, '$.format.size')) / POWER(1024, 3) as output_sizeGB,
DATE_FORMAT(SEC_TO_TIME(JSON_UNQUOTE(JSON_EXTRACT(ffprobe_json_source_video, '$.format.duration'))), '%H:%i:%s') as HHmmSS,
JSON_EXTRACT(ffprobe_json_source_video, '$.streams[0].width') as width,
JSON_EXTRACT(ffprobe_json_source_video, '$.streams[0].height') as height,
JSON_UNQUOTE(JSON_EXTRACT(ffprobe_json_source_video, '$.streams[0].display_aspect_ratio')) as display_aspect_ratio
FROM kairos.netflux_ffprobe

)

select  * from kairos.netflux_ingestion_queue q 
left outer join ffprobe f 
on q.ID = f.file_id


-- select * from kairos.netflux_ffprobe

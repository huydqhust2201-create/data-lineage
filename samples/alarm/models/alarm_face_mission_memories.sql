{{ config(
    materialized='table',
    schema='analytics'
) }}

WITH face_alarms AS (
    -- CTE 1: Lấy các báo thức cấu hình Face Mission
    SELECT
        a.alarmId,
        a.userId,
        a.label AS alarm_label,
        fmc.requiredHoldDurationSec,
        fmc.backgroundImageUri
    FROM {{ ref('Alarm') }} a
    JOIN {{ ref('AlarmFaceMissionConfig') }} fmc ON a.alarmId = fmc.alarmId
    WHERE a.missionType = 'SMILE_AND_OPEN_EYES' AND a.isEnabled = true
),
alarm_execution_history AS (
    -- CTE 2: Lấy lịch sử đổ chuông và tắt báo thức, tính thời gian phản ứng tắt báo thức
    SELECT
        ah.alarmHistoryId,
        ah.alarmId,
        ah.snoozeCount,
        ah.dismissalTime,
        ah.firstRingTime,
        (CAST(EXTRACT(EPOCH FROM ah.dismissalTime) AS DOUBLE) - CAST(EXTRACT(EPOCH FROM ah.firstRingTime) AS DOUBLE)) AS reaction_time_sec
    FROM {{ ref('AlarmHistory') }} ah
    WHERE ah.isDismissed = true
),
captured_memories AS (
    -- CTE 3: Kết hợp ảnh kỷ niệm chụp được khi tắt báo thức
    SELECT
        p.pictureId,
        p.alarmHistoryId,
        p.userId,
        p.imageUri,
        p.description AS picture_desc
    FROM {{ ref('Picture') }} p
    WHERE p.imageUri IS NOT NULL
),
user_alarm_metrics AS (
    -- CTE 4: Tính toán hiệu suất trung bình và tổng điểm tích lũy của user
    SELECT
        fa.userId,
        fa.alarmId,
        fa.alarm_label,
        fa.requiredHoldDurationSec,
        fa.backgroundImageUri,
        aeh.reaction_time_sec,
        aeh.snoozeCount,
        cm.imageUri,
        cm.picture_desc
    FROM face_alarms fa
    JOIN alarm_execution_history aeh ON fa.alarmId = aeh.alarmId
    JOIN captured_memories cm ON aeh.alarmHistoryId = cm.alarmHistoryId
),
ranked_user_memories AS (
    -- CTE 5: Xếp hạng các bức ảnh kỷ niệm dựa trên phản ứng tắt báo thức nhanh nhất
    SELECT
        uam.userId,
        uam.alarm_label,
        uam.requiredHoldDurationSec,
        uam.backgroundImageUri,
        uam.reaction_time_sec,
        uam.imageUri,
        uam.picture_desc,
        RANK() OVER (
            PARTITION BY uam.userId
            ORDER BY uam.reaction_time_sec ASC, uam.snoozeCount ASC
        ) as memory_rank
    FROM user_alarm_metrics uam
)
-- SELECT cuối cùng: Kết hợp với thông tin UserStats để xuất ra báo cáo xếp hạng kỷ niệm
SELECT
    u.username AS user_name,
    us.totalPoints AS total_points,
    us.currentStreak AS current_streak,
    rum.alarm_label AS alarm_name,
    rum.requiredHoldDurationSec AS hold_duration,
    rum.reaction_time_sec AS best_reaction_time,
    rum.imageUri AS memory_image_uri,
    rum.picture_desc AS memory_description
FROM ranked_user_memories rum
JOIN {{ ref('UserStats') }} us ON rum.userId = us.userId
JOIN {{ ref('User') }} u ON rum.userId = u.userId
WHERE rum.memory_rank = 1
ORDER BY us.totalPoints DESC;